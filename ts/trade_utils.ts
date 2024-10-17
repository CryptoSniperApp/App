import * as web3 from "@solana/web3.js";
import { Connection, PublicKey, Keypair } from "@solana/web3.js";
import base58 from "bs58";
import * as spl from '@solana/spl-token';
import { Environment, FixedSide, Moonshot } from '@wen-moon-ser/moonshot-sdk';
import {
    ComputeBudgetProgram,
    TransactionMessage,
    VersionedTransaction,
} from '@solana/web3.js';
import * as dotenv from 'dotenv';
import BN from "bn.js";
import AmmImpl from '@mercurial-finance/dynamic-amm-sdk';
import { base64 } from "@project-serum/anchor/dist/cjs/utils/bytes";
import { NATIVE_MINT } from '@solana/spl-token'
import { swapTokensOnJupiter } from "./jupiter_dex";
import { ResponseError } from "@jup-ag/api";


export async function getTokenAmountInWallet(
    connection: Connection,
    tokenAccountAddress: string,
): Promise<number | null> {
    const balance = await connection.getTokenAccountBalance(new PublicKey(tokenAccountAddress), 'confirmed');
    return balance.value.uiAmount;
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
    commitment: web3.Commitment = 'recent',
    // commitment: web3.Commitment = 'processed',
    // commitment: web3.Commitment = 'singleGossip',
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
    const token = moonshot.Token({ mintAddress: mintAddress });
    let curvePos;
    try {
        curvePos = await token.getCurvePosition();
        console.log('Current position of the curve: ', curvePos);
    } catch (error) {
        console.log('Error getting curve position: ', error);
        let start = Date.now();
        let res = null;

        try {
            res = await swapTokensOnJupiter(
                connection,
                mintAddress,
                NATIVE_MINT.toBase58(),
                amount,
                slippageBps,
                "SELL",
                decimals,
                kp
            )
        } catch (error) {
            if (error instanceof ResponseError && error.response.status === 400) {
                console.error("Ошибка в Jupiter: ", error);
            } else {
                console.error("Произошла ошибка:", error);
            }
        }

        if (!res) {
            let poolAddress = await getPoolByMintMeteora(mintAddress);
            if (!poolAddress) {
                throw new Error('No pool on meteora found');
            }
            let taken;
            [res, taken] = await swapMeteoraTokens(
                connection,
                new PublicKey(poolAddress.pool_address),
                "SELL",
                amount,
                kp,
                slippageBps,
                50,
                200_000,
                commitment
            )

            if (!res) {
                throw new Error('Error swapping tokens');
            }
            return [res, taken];
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

    const blockhash = await connection.getLatestBlockhash({ commitment: commitment });
    let trans = new TransactionMessage({
        payerKey: creator.publicKey,
        recentBlockhash: blockhash.blockhash,
        instructions: [priorityIx, ...ixs],
    });
    const messageV0 = trans.compileToV0Message();
    const transaction = new VersionedTransaction(messageV0);

    transaction.sign([creator]);
    let start = Date.now();
    let txHash: string = "";

    txHash = await connection.sendTransaction(transaction, {
        skipPreflight: true,
        maxRetries: 50,
        preflightCommitment: commitment,
    });

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

        if (amount != null && amount == 5 * (10 ** 9)   ) {
            try {
                await swapTokens(
                    connection,
                    "SELL",
                    accountInfo.account.data["parsed"]["info"]["mint"],
                    process.env.WALLET_MOONSHOT_PRIVATE_KEY as string,
                    amount / (10 ** 9),
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
    price_usd: number,
    price_sol: number,
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

    let tokenData = response.data?.[0];
    if (!tokenData) {
        return null;
    }
    
    let amount = tokenData.pool_token_amounts[0] / tokenData.pool_token_amounts[1];
    let p = {
        mint: tokenData.pool_token_mints[1],
        pool_address: tokenData.pool_address,
        price_usd: amount * await getSolPrice(),
        price_sol: amount,
        decimals: tokenData.lp_decimal,
    }
    return p;
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
        price_usd: amount * await getSolPrice(),
        price_sol: amount,
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
    commitment: web3.Commitment = 'max',
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
        let swapAmount_ = otherTokenPriceInSol * swapAmount * (10 ** solMint.decimals);
        swapQuote = pool.getSwapQuote(
            solMint.address,
            new BN(swapAmount_),
            slippage,
        );
    } else if (txType == "SELL") {
        inTokenMint = otherMint;

        if (swapAmount === 0) {
            let ata = await getAssociatedTokenAccount(inTokenMint.address.toBase58(), kp.publicKey.toBase58());
            let balance = await getTokenAmountInWallet(connection, ata.toBase58());
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

    const priorityIx = ComputeBudgetProgram.setComputeUnitPrice({
        microLamports: microLamports,
    });

    const blockhash = await connection.getLatestBlockhash({ commitment: commitment });
    let trans = new TransactionMessage({
        payerKey: kp.publicKey,
        recentBlockhash: blockhash.blockhash,
        instructions: [priorityIx, ...swapTx.instructions],
    });
    const messageV0 = trans.compileToV0Message();
    const transaction = new VersionedTransaction(messageV0);

    transaction.sign([kp]);

    let uintarrayTx = transaction.serialize();
    let encodedTx = base64.encode(Buffer.from(uintarrayTx));

    const swapResult = await connection.sendEncodedTransaction(encodedTx, {
        skipPreflight: true,
        maxRetries: maxRetries,
        preflightCommitment: commitment,
    });
    console.log("Time taken", Date.now() - start);
    console.log("Swap result", swapResult);

    try {
        const latestBlockHash = await connection.getLatestBlockhash();
        await connection.confirmTransaction(
            {
                blockhash: latestBlockHash.blockhash,
                lastValidBlockHeight: latestBlockHash.lastValidBlockHeight,
                signature: swapResult,
            }
        )
    } catch (error) {
        console.log('Error confirming transaction in [swapMeteoraTokens]: ', error);
    }

    return [swapResult, Date.now() - start];
}



async function test() {
    let privateKey = process.env.WALLET_MOONSHOT_PRIVATE_KEY as string;
    let kp = Keypair.fromSecretKey(base58.decode(privateKey));
    
    let mint = 'EBTGkVzn779pknFXayJbechuswtRqqdu4gzN8WEqnebZ';
    const connection = new Connection(process.env.MOONSHOT_RPC_ENDPOINT as string, "confirmed");
    // const connection = new Connection('https://api.mainnet-beta.solana.com', 'confirmed');

    // let resp = await connection.getAccountInfo(new PublicKey(mint));
    // let resp = await connection.getSlot('confirmed');
    // console.log('resp', resp);
    // return;

    // let tx = await connection.getTransaction(
    //     '5pa53kAp2WuWaomskZ1ZvtDv1hDsSSRzFHvjLQ41x1uUv7bZk9BF3ZE3aac4qN2KreLmeJrLGdsFNZfmPL2SA4Av',
    //     {
    //         commitment: 'finalized',
    //     }
    // )
    // console.log(tx);
    // console.log(await getTokenAmountInWallet());
    // await closeTokenAccount(
    //     "3EVfjiD4vCchVmnSD72iB8K5NSbUt9U4vgdJ3YDJUMxF",
    //     kp,
    //     connection,
    //     kp.publicKey,
    //     kp.publicKey
    // );
    // await sellAll(connection, kp);
}


export const privateKey = process.env.WALLET_MOONSHOT_PRIVATE_KEY as string;
export const kp = Keypair.fromSecretKey(base58.decode(privateKey));


// test();
