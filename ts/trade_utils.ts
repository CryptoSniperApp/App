import * as web3 from "@solana/web3.js";
import { Connection, PublicKey, Keypair } from "@solana/web3.js";
import base58 from "bs58";
import * as spl from '@solana/spl-token';
import { BaseAnchorProvider, Environment, FixedSide, Moonshot, programId, tokenLaunchpadIdlV1 } from '@wen-moon-ser/moonshot-sdk';
import { ComputeBudgetProgram } from '@solana/web3.js';
import BN from "bn.js";
import AmmImpl from '@mercurial-finance/dynamic-amm-sdk';
import { NATIVE_MINT } from '@solana/spl-token'
import { swapTokensOnJupiter } from "./jupiter_dex";
import { ResponseError } from "@jup-ag/api";
import { ConnectionSolanaPool } from "./connection_pool";
import { Program } from "@coral-xyz/anchor";
import { withTimeout } from "./main";


export async function getTokenAmountInWallet(
    connection: Connection,
    tokenAccountAddress: string,
): Promise<number | null> {
    const balance = await connection.getTokenAccountBalance(new PublicKey(tokenAccountAddress), 'confirmed');
    return balance.value.uiAmount;
}


class MyAnchorProviderV1 extends BaseAnchorProvider<any> {
    constructor(connectionStr: string, confirmOptions: any) {
        super(connectionStr, tokenLaunchpadIdlV1, programId, confirmOptions);
    }
    get version() {
        return 'V1';
    }

    setConnection(connection: Connection) {
        (this as any)._connection = connection;
        (this as any).setProvider();
        (this as any)._program = new Program(this.IDL, this.PROGRAM_ID);        
    }
}


export async function swapTokens(
    connection: Connection,
    txType: "BUY" | "SELL",
    mintAddress: string,
    privKeyWallet: string,
    amount: number,
    slippageBps: number | null = null,
    microLamports: number | null = null,
    decimals: number | null = null,
    // commitment: web3.Commitment = 'recent',
    commitment: web3.Commitment = 'confirmed',
    // commitment: web3.Commitment = 'processed',
    // commitment: web3.Commitment = 'singleGossip',
    confirmTransaction: boolean = true,
): Promise<[string, number]> {
    if (!slippageBps) {
        slippageBps = 500;
    }
    if (!microLamports) {
        microLamports = 200_000;
    }
    if (!decimals) {
        decimals = 9;
    }

    let rpcUrl = connection.rpcEndpoint;
    const moonshot = new Moonshot({
        rpcUrl,
        environment: Environment.MAINNET,
    });
    (moonshot.provider as any)._connection = connection;
    (moonshot.provider as any).setProvider();
    // let provider = new MyAnchorProviderV1(rpcUrl, {
    //     commitment: 'confirmed',
    // });
    // provider.setConnection(connection);
    // moonshot.provider = provider;

    const token = moonshot.Token({ mintAddress: mintAddress });
    let curvePos;
    try {
        curvePos = await token.getCurvePosition();
        console.log('Current position of the curve: ', curvePos);
    } catch (error) {
        console.log('Error getting curve position: ', error);
        let start = Date.now();
        let res: any;

        let meteoraPoolAddress;
        for (let i = 0; i < 10; i++) {
            try {
                meteoraPoolAddress = await getPoolByMintMeteora(mintAddress)
                console.log('meteoraPoolAddress', meteoraPoolAddress);
                break;
            } catch {
                continue;
            }
        }

        if (meteoraPoolAddress) {
            let taken;
            console.log('swapMeteoraTokens');
            [res, taken] = await swapMeteoraTokens(
                connection,
                new PublicKey(meteoraPoolAddress.pool_address),
                txType,
                amount,
                kp,
                slippageBps / 100,
                50,
                200_000,
                commitment,
                confirmTransaction,
            )

            if (!res) {
                throw new Error('Error swapping tokens');
            }
            return [res, taken];
        }
        

        try {
            if (amount === 0) {
                let ata = await getAssociatedTokenAccount(mintAddress, kp.publicKey.toBase58());
                amount = await getTokenAmountInWallet(connection, ata.toBase58()) as number;
            }
            console.log('swapTokensOnJupiter');
            res = await swapTokensOnJupiter(
                connection,
                txType == "BUY" ? NATIVE_MINT.toBase58() : mintAddress,
                txType == "BUY" ? mintAddress : NATIVE_MINT.toBase58(),
                amount,
                slippageBps / 100,
                txType,
                decimals,
                kp,
                commitment,
                confirmTransaction
            )
        } catch (error) {
            if (error instanceof ResponseError && error.response.status === 400) {
                console.error("Ошибка в Jupiter: ", error);
            } else {
                console.error("Произошла ошибка:", error);
            }
        }

        return [res, Date.now() - start];
    }
    const creator = Keypair.fromSecretKey(base58.decode(privKeyWallet));
    const tokenAmount = BigInt(Math.round(amount * (10 ** decimals)));
    
    const collateralAmount = await token.getCollateralAmountByTokens({
        tokenAmount,
        tradeDirection: txType,
        curvePosition: curvePos
    });

    let fixedSide: FixedSide;
    if (txType == "BUY") {
        fixedSide = FixedSide.OUT;
    } else {
        fixedSide = FixedSide.IN;
    }

    const { ixs } = await token.prepareIxs({
        slippageBps: slippageBps,
        creatorPK: creator.publicKey.toBase58(),
        tokenAmount,
        collateralAmount,
        tradeDirection: txType,
        fixedSide: fixedSide,
    });

    const priorityIx = ComputeBudgetProgram.setComputeUnitPrice({
        microLamports: microLamports,
    });

    let start = Date.now();

    let t = new web3.Transaction();
    t.add(priorityIx, ...ixs);
    t.recentBlockhash = (await connection.getLatestBlockhash()).blockhash;
    t.sign(creator);

    let txHash;
    if (confirmTransaction) {
        txHash = await web3.sendAndConfirmTransaction(connection, t, [creator], {
            commitment: commitment,
        });
    } else {
        txHash = await connection.sendRawTransaction(t.serialize(), {
            skipPreflight: true,
            maxRetries: 20,
            preflightCommitment: commitment,
        });
    }

    let taken = Date.now() - start;
    console.log('Transaction time taken: ', taken, 'ms');
    console.log(`${txType} Transaction Hash:`, txHash);
    return [txHash, taken];
}


export async function createTokenAccount(
    mintAddress: string,
    walletPublicKey: string,
    connection: Connection,
    signerKeyPair: Keypair,
    ata: PublicKey | null = null
): Promise<string> {
    if (ata == null) {
        ata = await spl.getAssociatedTokenAddress(
            new web3.PublicKey(mintAddress), // mint
            new web3.PublicKey(walletPublicKey), // owner
            false // allow owner off curve
        );
    }

    let tx = new web3.Transaction();
    tx.add(
        spl.createAssociatedTokenAccountInstruction(
            new web3.PublicKey(walletPublicKey), // payer
            ata, // ata
            new web3.PublicKey(walletPublicKey), // owner
            new web3.PublicKey(mintAddress) // mint
        )
    );

    const signature = await web3.sendAndConfirmTransaction(connection, tx, [signerKeyPair]);
    console.log(`createTokenAccount tx: ${signature}`);
    return signature;
}


export async function closeTokenAccount(
    tokenAccountAddress: string,
    feePayer: Keypair,
    connection: Connection,
    destinationPublicKey: PublicKey,
    ownerPublicKey: PublicKey
): Promise<string> {
    let tx = new web3.Transaction().add(
        spl.createCloseAccountInstruction(
          new PublicKey(tokenAccountAddress), // token account which you want to close
          destinationPublicKey, // destination
          ownerPublicKey, // owner of token account
        ),
    );
    

    let start = Date.now();
    const signature = await web3.sendAndConfirmTransaction(connection, tx, [
        feePayer,
        feePayer,
    ])
    // owner of token account
    console.log(`closeTokenAccount tx: ${signature}. taken ${Date.now() - start} ms`);
    return signature;
}


export async function getAssociatedTokenAccount(
    mintAddress: string,
    walletPublicKey: string     
): Promise<PublicKey> {
    let ata = await spl.getAssociatedTokenAddress(
        new PublicKey(mintAddress),
        new PublicKey(walletPublicKey),
        false
    );
    return ata;
}


async function sellAll(connection: Connection, kp: Keypair) {
    let accounts = await connection.getParsedTokenAccountsByOwner(
        kp.publicKey, { programId: spl.TOKEN_PROGRAM_ID },
        'confirmed'
    )
    console.log('accounts', accounts);
    accounts.value.forEach(async (accountInfo) => {
    // for (let accountInfo of accounts.value) {
        let amount = accountInfo.account.data["parsed"]["info"]["tokenAmount"]["amount"];
        console.log(`pubkey: ${accountInfo.pubkey.toBase58()}`);
        console.log(`mint: ${accountInfo.account.data["parsed"]["info"]["mint"]}`);
        console.log(
          `owner: ${accountInfo.account.data["parsed"]["info"]["owner"]}`,
        );
        console.log(
          `decimals: ${accountInfo.account.data["parsed"]["info"]["tokenAmount"]["decimals"]}`,
        );
        console.log(
          `amount: ${amount}`,
        );
        console.log("====================");

        if (amount != null && amount !== 0 && amount < 50 ) {
            try {
                await swapTokens(
                    connection,
                    "SELL",
                    accountInfo.account.data["parsed"]["info"]["mint"],
                    base58.encode(kp.secretKey),
                    amount / web3.LAMPORTS_PER_SOL,
                    500,
                    50_000,
                    9,
                    'confirmed'
                )
            } catch (error) {
                console.error(error);
            }
        }
        if ( `${amount}` !== "0" ) {
            return;
        }
        await closeTokenAccount(
            accountInfo.pubkey.toBase58(),
            kp,
            connection,
            kp.publicKey,
            kp.publicKey
        );
    });
}


type POOL_INFO = {
    mint: string,
    pool_address: string,
    decimals: number,
}


async function getSolPrice() {
    let url = new URL('https://api.coingecko.com/api/v3/simple/price');
    url.searchParams.append('ids', 'solana');
    url.searchParams.append('vs_currencies', 'usd');
    let headers = {
        'accept': 'application/json',
    };
    let resp = await fetch(url, { headers });
    let response = await resp.json();
    return response.solana.usd;
}


async function getPoolByMintMeteora(mint: string): Promise<null | POOL_INFO> {
    let url = new URL('https://amm-v2.meteora.ag/pools/search');
    url.searchParams.append('page', '0');
    url.searchParams.append('size', '100');
    url.searchParams.append('filter', mint);
    let headers = {
        'accept': 'application/json',
    };

    let resp = await fetch(url, { headers });
    let response = await resp.json();

    for (let tokenData of response.data) {
        // let tokenData = response.data?.[0];
        if (!tokenData) {
            continue;
        }
        
        let amount = tokenData.pool_token_amounts[0] / tokenData.pool_token_amounts[1];

        if (!amount) {
            continue;
        }

        let p = {
            mint: tokenData.pool_token_mints[1],
            pool_address: tokenData.pool_address,
            decimals: tokenData.lp_decimal,
        }
        return p;
    }
    return null;
}


async function getPoolByMintRaydium(mint: string): Promise<null | POOL_INFO> {
    let url = new URL('https://api-v3.raydium.io/pools/info/mint');
    url.searchParams.append('mint1', mint);
    url.searchParams.append('poolType', 'all');
    url.searchParams.append('poolSortField', 'default');
    url.searchParams.append('sortType', 'desc');
    url.searchParams.append('pageSize', '1000');
    url.searchParams.append('page', '1');

    let headers = {
        'accept': 'application/json',
    };
    let resp = await fetch(url, { headers });
    let response = await resp.json();
    let tokenData = response.data?.data?.[0];
    if (!tokenData || tokenData.mintA.address !== mint && tokenData.mintB.address !== mint) {
        return null;
    }
    let amount = tokenData.mintAmountB / tokenData.mintAmountA;
    let mintInPool = tokenData.mintA.address === mint ? tokenData.mintA : tokenData.mintB;
    let p = {
        mint: mintInPool.address,
        pool_address: tokenData.id,
        decimals: mintInPool.decimals,
    }
    return p;
}


async function swapMeteoraTokens(
    connection: Connection,
    poolAddress: PublicKey, 
    txType: "BUY" | "SELL", 
    swapAmount: number, 
    kp: Keypair,
    slippage: number = 3, 
    maxRetries: number = 50,
    microLamports: number = 200_000,
    commitment: web3.Commitment = 'confirmed',
    confirmTransaction: boolean = false,
): Promise<[string, number]> {
    const pool = await AmmImpl.create(connection, poolAddress);
    let poolInfo = pool.poolInfo;

    let solMint = pool.tokenAMint.address.toBase58() === NATIVE_MINT.toBase58() 
    ? pool.tokenAMint 
    : pool.tokenBMint;
    let solAmount = solMint === pool.tokenAMint 
    ? poolInfo.tokenAAmount.toNumber() / (10 ** solMint.decimals) 
    : poolInfo.tokenBAmount.toNumber() / (10 ** solMint.decimals);

    let otherMint = solMint === pool.tokenAMint ? pool.tokenBMint : pool.tokenAMint;  
    let otherAmount = otherMint === pool.tokenAMint 
    ? poolInfo.tokenAAmount.div(new BN(10).pow(new BN(otherMint.decimals))).toNumber() 
    : poolInfo.tokenBAmount.div(new BN(10).pow(new BN(otherMint.decimals))).toNumber();

    var swapQuote;
    var inTokenMint;

    if (txType == "BUY") {
        inTokenMint = solMint;

        let otherTokenPriceInSol = solAmount / otherAmount;
        let swapAmount_ = otherTokenPriceInSol * (swapAmount + 0.15) * (10 ** solMint.decimals);
        console.log('swapAmount meteora', swapAmount_);
        swapQuote = pool.getSwapQuote(
            solMint.address,
            new BN(swapAmount_),
            slippage,
        );
    } else if (txType == "SELL") {
        inTokenMint = otherMint;

        var ata = await getAssociatedTokenAccount(inTokenMint.address.toBase58(), kp.publicKey.toBase58());
        let balance = await getTokenAmountInWallet(connection, ata.toBase58());
        if (swapAmount === 0 || (balance && swapAmount && balance < swapAmount)) {
            if (balance) {
                swapAmount = balance;
            }
        }

        swapQuote = pool.getSwapQuote(
            otherMint.address,
            new BN(swapAmount * (10 ** otherMint.decimals)),
            slippage,
        );
    } else {
        throw new Error('Invalid txType');
    }

    console.log('swapQuote', swapQuote);
    var start = Date.now();
    const swapTx = await pool.swap(
        kp.publicKey,
        inTokenMint.address,
        swapQuote.swapInAmount,
        swapQuote.minSwapOutAmount
    );
    swapTx.sign(kp);

    // const priorityIx = ComputeBudgetProgram.setComputeUnitPrice({
    //     microLamports: microLamports,
    // });

    const sendTransaction = async () => {
        var attempts = 0;
        var swapResult = "";
        while (attempts < 5) {
            attempts++;
            try {
                // let wallet = new Wallet(kp);
                // let provider = new AnchorProvider(connection, wallet, {
                //     commitment: commitment,
                //     skipPreflight: true,
                // });
                // const swapResult = await provider.sendAndConfirm(swapTx);
                swapResult = await connection.sendRawTransaction(
                    swapTx.serialize(),
                    {
                        skipPreflight: true,
                        maxRetries: maxRetries,
                        preflightCommitment: commitment,
                    }
                );
                console.log("Time taken", Date.now() - start);
                console.log("Swap result", swapResult);
    
                if (confirmTransaction) {
                    try {
                        let latestBlockhash = await connection.getLatestBlockhash();
                        await connection.confirmTransaction({
                            blockhash: latestBlockhash.blockhash,
                            lastValidBlockHeight: latestBlockhash.lastValidBlockHeight,
                            signature: swapResult,
                        }, commitment);
                    } catch (error) {
                        console.log('Error confirming transaction in [swapMeteoraTokens]: ', error);
                        // continue;
                    }
                }
    
            } catch (error) {
                console.log('Error sending transaction in [swapMeteoraTokens]: ', error);
                continue;
            }
        
            return [swapResult, Date.now() - start];
        }
        if (swapResult !== "") {
            return [swapResult, Date.now() - start];
        }
    }

    let res = await withTimeout(sendTransaction(), 65000);

    let [swapResult, taken] = res as [string, number];
    if (swapResult === "") {
        throw new Error('Failed to send transaction in [swapMeteoraTokens]');
    }
    return [swapResult, taken];
}



async function test() {
    let privateKey = process.env.WALLET_MOONSHOT_PRIVATE_KEY as string;
    let chainStackRpcEndpoint = process.env.MOONSHOT_RPC_ENDPOINT as string;
    let kp = Keypair.fromSecretKey(base58.decode(privateKey));
    let connection = new ConnectionSolanaPool().getConnectionWithProxy();

    // let mint = '8jayusxKifrCnx1b5hUAyxyyPhXQsyxpNN62pQsZBGB6';
    let mint = '8jayusxKifrCnx1b5hUAyxyyPhXQsyxpNN62pQsZBGB6';
    // let result = await swapTokens(connection, "BUY", mint, privateKey, 100);
    // console.log(result);
    
    // metaplex.nfts().findByMint({ mintAddress: new PublicKey(mint) })
    // let res = await swapTokens(connection, "BUY", mint, privateKey, 10)
    // console.log(res);
    
    // let mint = '696bjiNHJnVf5fubr5e2CbqY1iKG4en3vzhpXaYLK6Fa'; // raydium

    // let res = await spl.getTokenMetadata(connection, new PublicKey(mint));
    // console.log(res);

    // // let rpcUrl = process.env.MOONSHOT_RPC_ENDPOINT as string;

    // const connection = new Connection(rpcUrl, "confirmed");

    let promises = [];
    let start = Date.now();
    for (let i = 0; i < 10; i++) {
        promises.push(swapTokens(
            connection,
            "BUY",
            mint,
            privateKey, 
            100,
        ));
    }
    await Promise.all(promises);
    console.log('Main time taken', Date.now() - start);

    // await sellAll(connection, kp);
}


export const privateKey = process.env.WALLET_MOONSHOT_PRIVATE_KEY as string;
export const kp = Keypair.fromSecretKey(base58.decode(privateKey));


// test();
