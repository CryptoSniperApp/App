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
    // commitment: web3.Commitment = 'recent',
    // commitment: web3.Commitment = 'processed',
    commitment: web3.Commitment = 'singleGossip',
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
        // chainOptions: {
        //     solana: { confirmOptions: { commitment: 'max' } },
        // },
    });
    const token = moonshot.Token({ mintAddress: mintAddress });

    const curvePos = await token.getCurvePosition();
    console.log('Current position of the curve: ', curvePos); // Prints the current curve position

    const creator = Keypair.fromSecretKey(base58.decode(privKeyWallet));
    const tokenAmount = BigInt(Math.round(amount * (10 ** decimals)));
    
    const collateralAmount = await token.getCollateralAmountByTokens({
        tokenAmount,
        tradeDirection: txType,
        curvePosition: curvePos
    });

    // TODO: debug this. a compilation process instructions data is in progress
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
    const signature = await spl.closeAccount(
        connection,
        feePayer,
        new PublicKey(tokenAccountAddress),
        destinationPublicKey,
        ownerPublicKey
    );
    console.log(`closeTokenAccount tx: ${signature}`);
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


// function calculateSlippage(
//     balance: number,
//     tokenPrice: number,
//     desiredAmount: number,
//     slippageBps: number
//   ) {
//     // Преобразуем проскальзывание из базисных пунктов в десятичное значение
//     const slippageDecimal = slippageBps / 10000;
  
//     // Рассчитываем максимальную и минимальную стоимость с учетом проскальзывания
//     const maxCost = desiredAmount * tokenPrice * (1 + slippageDecimal);
//     const minCost = desiredAmount * tokenPrice * (1 - slippageDecimal);
  
//     // Проверяем, достаточно ли баланса для выполнения транзакции
//     if (balance < minCost) {
//       throw new Error("Недостаточно средств для выполнения транзакции с учетом проскальзывания.");
//     }
  
//     return {
//       maxCost,
//       minCost,
//     };
//   }


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

        // if (amount != null && amount >= 1) {
        //     try {
        //         await swapTokens(
        //             connection,
        //             "SELL",
        //             accountInfo.account.data["parsed"]["info"]["mint"],
        //             process.env.WALLET_MOONSHOT_PRIVATE_KEY as string,
        //             amount / (10 ** 9),
        //             500,
        //             50_000,
        //             9,
        //             'confirmed'
        //         )
        //     } catch (error) {
        //         console.error(error);
        //     }
        // }
        if ( amount !== "0" ) {
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


async function test() {
    let privateKey = process.env.WALLET_MOONSHOT_PRIVATE_KEY as string;
    let kp = Keypair.fromSecretKey(base58.decode(privateKey));
    // let kp = Keypair.fromSecretKey(base58.decode("37umEJq7z4rsDJwt8DkG5FWsud7oX1iuGzy4iK8wp5qS5E8w6Sv95rpREJdvPF9kC7PCsHEQy3Eqcs39nR8Ee3Pt"));

    let mint = 'HWKZt3KL2itEgxHozAbzy7LwFpVFHp777JdpwpfNfGnG';
    const connection = new Connection(process.env.MOONSHOT_RPC_ENDPOINT as string, 'confirmed');
    // const connection = new Connection('https://api.mainnet-beta.solana.com', 'confirmed');
    
    // let resp = await connection.getParsedAccountInfo(new PublicKey(mint));
    // console.log(connection.rpcEndpoint);
    
    // return;

    // token

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
    await sellAll(connection, kp);
    return;
    // let amount = 930;

    // if (amount == null) {
    //     console.log('No tokens in wallet');
    //     return;
    // }

    // console.log('amount', amount);
    
    // await swapTokens(
    //     connection,
    //     "BUY",
    //     mint,
    //     privateKey,
    //     amount,
    //     500,
    //     200_000
    // )
    // await swapTokens(
    //     connection,
    //     "SELL",
    //     mint,
    //     privateKey,
    //     amount,
    //     500,
    //     200_000
    // )

}

// test();

  