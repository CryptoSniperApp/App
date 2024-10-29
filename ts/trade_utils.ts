import * as web3 from "@solana/web3.js";
import { Connection, PublicKey, Keypair } from "@solana/web3.js";
import base58 from "bs58";
import * as spl from '@solana/spl-token';
import { AnchorProviderV1, BaseAnchorProvider, Environment, FixedSide, Moonshot, programId, tokenLaunchpadIdlV1 } from '@wen-moon-ser/moonshot-sdk';
import { ComputeBudgetProgram } from '@solana/web3.js';
import BN from "bn.js";
import AmmImpl from '@mercurial-finance/dynamic-amm-sdk';
import { NATIVE_MINT } from '@solana/spl-token'
import { swapTokensOnJupiter } from "./jupiter_dex";
import { ResponseError } from "@jup-ag/api";
import { ConnectionSolanaPool } from "./connection_pool";
import { withTimeout } from "./main";
import * as anchor from "@coral-xyz/anchor";
import { base64 } from "@coral-xyz/anchor/dist/cjs/utils/bytes";


export async function getTokenAmountInWallet(
    connection: Connection,
    tokenAccountAddress: string,
): Promise<number | null> {
    const balance = await connection.getTokenAccountBalance(new PublicKey(tokenAccountAddress), 'confirmed');
    return balance.value.uiAmount;
}


export class MyAnchorProviderV1 extends BaseAnchorProvider<any> {
    constructor(connectionStr: string, confirmOptions: any) {
        super(connectionStr, tokenLaunchpadIdlV1, programId, confirmOptions);
    }
    get version() {
        return 'V1';
    }

    setConnection(connection: Connection) {
        (this as any)._connection = connection;
        (this as any).setProvider();
        (this as any)._program = new anchor.Program(this.IDL, this.PROGRAM_ID, {connection: connection });
    }
}


export async function confirmTransactionStatus(
    connection: web3.Connection, tx: string, commitment: web3.Commitment, timeout: number = 120_000
) {
    var success = false;
    let promise = async () => {
        var resp = await connection.getSignatureStatuses([tx], {searchTransactionHistory: false});
        while (resp.value[0]?.confirmationStatus !== commitment) {
            try {
                resp = await connection.getSignatureStatuses([tx], {searchTransactionHistory: false});
            } catch (error: any) {
                console.log(`error ${error}. stack: ${error.stack}`)
            }
        }
        if (resp.value[0].confirmationStatus === commitment) {
            success = true
        }
    }
    await withTimeout(promise(), timeout)
    return success
}


export interface SwapTokenArgs {
    connection: Connection;
    txType: "BUY" | "SELL";
    mintAddress: string;
    privKeyWallet: string;
    amount: number;
    slippageBps?: number | null;
    microLamports?: number | null;
    decimals?: number | null;
    commitment?: web3.Commitment;
    confirmTransaction?: boolean;
    confirmBuyOperation?: boolean;
    token_on_moonshot?: boolean;
    blockHash?: null | string;
    lastValidBlockHeight?: null | number;
}

export async function swapTokens({
    connection,
    txType,
    mintAddress,
    privKeyWallet,
    amount,
    slippageBps = null,
    microLamports = null,
    decimals = null,
    commitment = 'confirmed',
    confirmTransaction = true,
    confirmBuyOperation = false,
    token_on_moonshot = false,
    blockHash = null,
    lastValidBlockHeight = null
}: SwapTokenArgs): Promise<[string[], number]> {
    if (!slippageBps) {
        slippageBps = 500;
    }
    if (!microLamports) {
        microLamports = 100_000;
    }
    if (!decimals) {
        decimals = 9;
    }
    if (!blockHash || !lastValidBlockHeight) {
        let block = await connection.getLatestBlockhash();
        blockHash = block.blockhash;
        lastValidBlockHeight = block.lastValidBlockHeight;
    }

    let kp = Keypair.fromSecretKey(base58.decode(privKeyWallet));
    let rpcUrl = connection.rpcEndpoint;
    const moonshot = new Moonshot({
        rpcUrl,
        environment: Environment.MAINNET,
    });

    let provider = new MyAnchorProviderV1(rpcUrl, {
        commitment: 'confirmed',
    });
    provider.setConnection(connection);
    moonshot.provider = provider;

    if (txType === "SELL" && amount === 0) {
        let ata = await getAssociatedTokenAccount(mintAddress, kp.publicKey.toBase58());
        amount = await getTokenAmountInWallet(connection, ata.toBase58()) as number;
    }

    const token = moonshot.Token({ mintAddress: mintAddress });
    let curvePos: bigint | null = null;
    
    let getCurvePosition = async () => {
        if (txType === "BUY") {
            for (let i = 0; i < 15; i++) {
                try {
                    curvePos = await token.getCurvePosition();
                    break;
                } catch (error: any)  { 
                    if (!token_on_moonshot) {
                        throw error
                    }
                    console.log(`${error}. ${error.stack}`)
                    await new Promise(res => setTimeout(res, 1500));
                }
            }
        }
        if (!curvePos) {
            curvePos = await token.getCurvePosition();
        }

        console.log('Current position of the curve: ', curvePos);
    }

    try {
        if (!token_on_moonshot) {
            await getCurvePosition();
        }
    } catch (error) {
        console.log('Error getting curve position: ', error);
        let start = Date.now();
        let res: any;
        
        try {
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
            console.error("Ошибка в Jupiter: ", error);
            let meteoraPoolAddress;
            for (let i = 0; i < 10; i++) {
                try {
                    meteoraPoolAddress = await getPoolByMintMeteora(mintAddress)
                    console.log('meteoraPoolAddress', meteoraPoolAddress);
                    break;
                } catch (error: any) {
                    console.log(`get error on meteoraPoolAddress ${error}. stack: ${error.stack}`);
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
        }

        return [res, Date.now() - start];
    }
    const creator = Keypair.fromSecretKey(base58.decode(privKeyWallet));
    const tokenAmount = BigInt(Math.round(amount * (10 ** decimals)));
    
    var collateralAmount: bigint;
    if (txType === "BUY") {
        collateralAmount = BigInt(400000000);
        slippageBps = 500;
    } else {
        collateralAmount = BigInt(0);
        slippageBps = 5000;
    }

    let fixedSide: FixedSide;
    if (txType == "BUY") {
        fixedSide = FixedSide.OUT;  
    } else {
        fixedSide = FixedSide.IN;
    }

    var ixsValue: any[] = [];
    let getIxsPromise = async () => {
        let { ixs } = await token.prepareIxs({
            slippageBps: slippageBps,
            creatorPK: creator.publicKey.toBase58(),
            tokenAmount,
            collateralAmount,
            tradeDirection: txType,
            fixedSide: fixedSide,
        })
        ixsValue = ixs
    }

    let updateBlockHash = async () => {
        let response = await connection.getLatestBlockhash();
        blockHash = response.blockhash;
        lastValidBlockHeight = response.lastValidBlockHeight;
    }

    var promises: any[] = [
        getIxsPromise()
    ];

    if (!blockHash || !lastValidBlockHeight) {
        promises.push(updateBlockHash())
    }

    var ata: any;
    if (txType === "BUY") {
        let getAtaPromise = async () => {
            let response = await spl.getAssociatedTokenAddress(
                new PublicKey(mintAddress),
                kp.publicKey,
            )
            ata = response.toBase58();
        }
        promises.push(getAtaPromise())
    }

    await Promise.all(promises);
    let start = Date.now();

    let sendTransaction = async (blockHash: string, lastValidBlockHeight: number) => {
        let instructions;
        if (txType === "BUY") {
            instructions = [
                spl.createAssociatedTokenAccountInstruction(
                    kp.publicKey,
                    new PublicKey(ata),
                    kp.publicKey,
                    new PublicKey(mintAddress)
                ), ...ixsValue
            ]
        } else {
            instructions = [...ixsValue]
        }

        let msg = new web3.TransactionMessage({
            payerKey: kp.publicKey,
            instructions: [
                ComputeBudgetProgram.setComputeUnitPrice({
                    microLamports: microLamports,
                }), 
                ...instructions
            ],
            recentBlockhash: blockHash,
        }).compileToV0Message();
        let t = new web3.VersionedTransaction(msg);
        t.sign([creator]);

        let lastError = null;
        let signatures: string[] = [];

        let send = async (transaction: web3.VersionedTransaction) => {
            let response;
            try {
                console.log(`send transaction at ${new Date()}`)
                response = await connection.sendRawTransaction(transaction.serialize(), {
                    skipPreflight: true,
                    maxRetries: 5,
                    preflightCommitment: commitment,
                });
            } catch (error) {
                lastError = error;
                console.log(lastError)
                return;
            }
            signatures.push(response);
            console.log(`Transaction ${response} sended successfully`);
        }

        let promises: any[] = [];
        let transactions: web3.VersionedTransaction[] = [];
        let percents;

        if (txType == "BUY") {
            percents = [1, 5, 10];
            // transactions = [];
            
        } else {
            percents = [1, 2];
            // transactions = [t]
        }

        for (let percent of percents) {
            let msg = new web3.TransactionMessage({
                payerKey: kp.publicKey,
                instructions: [
                    ComputeBudgetProgram.setComputeUnitPrice({
                        microLamports: microLamports * percent,
                    }), 
                    ...instructions
                ],
                recentBlockhash: blockHash,
            }).compileToV0Message();
            let t = new web3.VersionedTransaction(msg);
            t.sign([creator]);
            transactions.push(t)
        }

        transactions.forEach((transaction) => {promises.push(send(transaction))})
        await Promise.all(promises);

        if (lastError) {
            throw lastError
        }

        return signatures;
    }

    let txHashs = [];
    while (!blockHash || !lastValidBlockHeight) {
        await updateBlockHash();
    }

    if ((confirmBuyOperation && txType === "BUY") || confirmTransaction) {
        var attempt = 0;
        while (attempt < 3) {
            attempt++;
            try {
                let signatures = await sendTransaction(blockHash, lastValidBlockHeight);
                let confirmedSignatures: string[] = [];
                let timeout = 120_000;

                let promises = signatures.map((sig) => {
                    let promise = async () => {
                        try {
                            let res = await withTimeout(
                                connection.confirmTransaction({
                                    blockhash: blockHash as string,
                                    lastValidBlockHeight: lastValidBlockHeight as number,
                                    signature: sig,
                                }, "confirmed"), 
                                timeout,
                            )
                            // let res = await confirmTransactionStatus(connection, sig, commitment);
                            if (res) {
                                confirmedSignatures.push(sig)
                            }
                        } catch (error) {
                            if (`${error}`.includes("Timeout after")) {
                                // похуй
                                confirmedSignatures.push(sig)
                            }
                        }
                    }
                    return promise();
                })
                
                await Promise.all(promises);
                txHashs.push(...confirmedSignatures);
                break

            } catch (error: any) {
                console.info(
                    `error when confirm transaction on ${txType}
                    Moonshot: ${error}. trace ${error.stack}`
                )
                await Promise.all([
                    new Promise(res => setTimeout(res, 1500)),
                    updateBlockHash()
                ]);
            }
        }
        if (txHashs.length === 0) {
            throw new Error(`error when sending transaction on ${txType}`)
        }
    } else {
        let signatures = await sendTransaction(blockHash, lastValidBlockHeight);
        txHashs.push(...signatures);
    }

    let taken = Date.now() - start;
    console.log('Transaction time taken: ', taken, 'ms');
    console.log(`${txType} Transaction Hashes:`, txHashs);
    return [txHashs, taken];
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
    var att = 0;
    let promises: any[] = [];

    for (let accountInfo of accounts.value) {
        let amount = accountInfo.account.data["parsed"]["info"]["tokenAmount"]["amount"];
        let decimals = accountInfo.account.data["parsed"]["info"]["tokenAmount"]["decimals"];
        console.log(`pubkey: ${accountInfo.pubkey.toBase58()}`);
        console.log(`mint: ${accountInfo.account.data["parsed"]["info"]["mint"]}`);
        console.log(
            `owner: ${accountInfo.account.data["parsed"]["info"]["owner"]}`,
        );
        console.log(
            `decimals: ${decimals}`,
        );
        console.log(
            `amount: ${amount}`,
        );
        console.log("====================");

        att++;
        if (att > 15) {
            continue;
        }
        if (amount != null && `${amount}` !== "0" && amount < 50_000 * (10 ** decimals)) {
            try {
                let promise = swapTokens({
                    connection,
                    txType: "SELL",
                    mintAddress: accountInfo.account.data["parsed"]["info"]["mint"],
                    privKeyWallet: base58.encode(kp.secretKey),
                    amount: amount / web3.LAMPORTS_PER_SOL,
                    slippageBps: 500,
                    microLamports: 50_000,
                    decimals: 9,
                    commitment: 'confirmed',
                    confirmBuyOperation: true,
                    confirmTransaction: true
                })
                promises.push(promise)
            } catch (error) {
                console.error(error);
            }
        }
        if (`${amount}` !== "0") {
            continue;
        }
        // console.log(att);
        let promise = closeTokenAccount(
            accountInfo.pubkey.toBase58(),
            kp,
            connection,
            kp.publicKey,
            kp.publicKey
        );
        promises.push(promise);
    };

    await Promise.all(promises)
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
                // let wallet = new anchor.Wallet(kp);
                // let provider = new anchor.AnchorProvider(connection, wallet, {
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


function decodeMoonshotProgramTradeData(programData: string) {
    let b = base64.decode(programData)
    let provider = new AnchorProviderV1(web3.clusterApiUrl("mainnet-beta"));
    let result = (provider.program.coder.events as any).decode(b);
    return result;
}


async function test() {
    var privateKey = process.env.WALLET_MOONSHOT_PRIVATE_KEY as string;
    let chainStackRpcEndpoint = process.env.MOONSHOT_RPC_ENDPOINT as string;
    let kp = Keypair.fromSecretKey(base58.decode(privateKey));
    // console.log(kp.publicKey.toBase58());
    // return;
    let connection = new ConnectionSolanaPool().getConnectionWithProxy();
    (connection as any).proxy = true;

    // let connection = new Connection(web3.clusterApiUrl("mainnet-beta"), "confirmed");
    // let latestBlockhash = await connection.getLatestBlockhash();
    // console.log(connection);
    // return

    // let mint = '8jayusxKifrCnx1b5hUAyxyyPhXQsyxpNN62pQsZBGB6';

    var mint = '8jayusxKifrCnx1b5hUAyxyyPhXQsyxpNN62pQsZBGB6';
    mint = '3SqaeJ6bhEQNRod5wJyDYyq6N28Wwz2jcEM5J8H9Rp9q';
    mint = '41upazdWAgLjfCkLGQwGDgj2knovnpPyr4q2ZVNjifLz'

    // let ata = await getAssociatedTokenAccount(mint, kp.publicKey.toBase58());
    // let amount = await getTokenAmountInWallet(connection, ata.toBase58()) as number;
    // console.log(amount);

    // let result = await swapTokens(connection, "BUY", mint, privateKey, 100);
    // console.log(result);

    // metaplex.nfts().findByMint({ mintAddress: new PublicKey(mint) })
    // let res = await swapTokens(connection, "BUY", mint, privateKey, 10)
    // console.log(res);

    // let mint = '696bjiNHJnVf5fubr5e2CbqY1iKG4en3vzhpXaYLK6Fa'; // raydium

    // let res = await spl.getTokenMetadata(connection, new PublicKey(mint));
    // console.log(res);

    // let rpcUrl = process.env.MOONSHOT_RPC_ENDPOINT as string;
    // const connection = new Connection(rpcUrl, "confirmed");

    // let promises = [];
    // console.log('started');
    // let start = Date.now();
    // for (let i = 0; i < 1; i++) {
    //     promises.push(swapTokens(
    //         connection,
    //         "BUY",
    //         mint,
    //         privateKey, 
    //         15,
    //         1000, 800_000
    //     ));
    // }
    // await Promise.all(promises);
    // console.log('Main time taken', Date.now() - start);

    mint = 'JEGUQELAy86jBRuJsQjHbMJrWvHTfSWvuRuF7jiuaLdN';

    let doFunc = async (session: web3.Connection) => {
        let blockhash = await connection.getLatestBlockhash();
        let loc = (session as any).location;

        let start = new Date()
        console.log(`[${loc}] time start`, start)

        await swapTokens({
            connection,
            txType: "BUY",
            mintAddress: mint,
            privKeyWallet: privateKey, 
            amount: 5,
            token_on_moonshot: true,
            blockHash: blockhash.blockhash,
            lastValidBlockHeight: blockhash.lastValidBlockHeight + 10,
            confirmBuyOperation: true
        })
        console.log(`[${loc}] time taken`, (new Date() as any) - (start as any))
    };
    let proxies = [
        
    ];
    // let mainStart = Date.now();
    // console.log(`start script at ${new Date()}`)
    // await Promise.all([
    //     proxies.map((proxy) => {
    //         let conn: any = new ConnectionSolanaPool().getConnectionWithProxy(proxy);
            
    //         if (proxy.includes('e7ilIB4iF38l')) {
    //             conn.location = 'США (New York)'
    //         } else if (proxy.includes('IlFyCbnXF0Dx')) {
    //             conn.location = 'Япония (Tokyo)'
    //         } else if (proxy.includes('KL0hdzLAC3HL')) {
    //             conn.location = 'Великобритания England London'
    //         } else if (proxy.includes('KaB4wgmqc5Qc')) {
    //             conn.location = 'Германия Rheinland-Pfalz'
    //         } else {
    //             throw new Error(proxy)
    //         }
        
    //         return doFunc(conn)
    //     })
    // ])
    // console.log(`Main time taken ${Date.now() - mainStart}`)

    await sellAll(connection, kp);
}


export const privateKey = process.env.WALLET_MOONSHOT_PRIVATE_KEY as string;
// export const kp = Keypair.fromSecretKey(base58.decode(privateKey));


// test();
