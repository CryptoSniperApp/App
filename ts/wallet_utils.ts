import * as web3 from "@solana/web3.js";
import * as spl from "@solana/spl-token";
import { getAssociatedTokenAccount } from "./trade_utils";
import { bs58 } from "@project-serum/anchor/dist/cjs/utils/bytes";

export async function transferToken(
    connection: web3.Connection, 
    payerWallet: web3.Keypair, 
    mint: string, 
    amount: number,
    destinationWalletsAddress: string[]
) {
    let start = Date.now();
    let tx = new web3.Transaction();

    let sourceAta = await getAssociatedTokenAccount(
        mint,
        payerWallet.publicKey.toBase58(),
    )

    for (let destinationWalletAddress of destinationWalletsAddress) {
        tx.add(
            spl.createTransferInstruction(
                new web3.PublicKey(sourceAta),
                new web3.PublicKey(destinationWalletAddress),
                payerWallet.publicKey,
                amount,
            )
        )
    }

    let res = await web3.sendAndConfirmTransaction(
        connection,
        tx,
        [payerWallet],
    )

    return [res, Date.now() - start];
}

    
export async function transferSolToWallets(
    connection: web3.Connection,
    payerWallet: web3.Keypair,
    amountsWallets: object
): Promise<[string, number]> {
    let start = Date.now();
    let tx = new web3.Transaction();

    for (let [wallet, amount] of Object.entries(amountsWallets)) {
        console.log(`wallet: ${wallet}, amount: ${amount}`);
        tx.add(
            web3.SystemProgram.transfer({
                fromPubkey: payerWallet.publicKey,
                toPubkey: new web3.PublicKey(wallet),
                lamports: amount,
            })
        )
    }

    let res = await web3.sendAndConfirmTransaction(
        connection,
        tx,
        [payerWallet],
    )

    return [res, Date.now() - start];
}


export async function transferSol(
    connection: web3.Connection,
    payerWallet: web3.Keypair,
    amount: number,
    destination: string,
) {
    let start = Date.now();
    let tx = new web3.Transaction();

    if (amount === 0) {
        amount = await connection.getBalance(payerWallet.publicKey);
    }

    console.log(`transfer sol from wallet ${payerWallet.publicKey.toBase58()} to wallet: ${destination}. amount: ${amount}`);
    tx.add(
        web3.SystemProgram.transfer({
            fromPubkey: payerWallet.publicKey,
            toPubkey: new web3.PublicKey(destination),
            lamports: amount,
        })
    )
    tx.recentBlockhash = (await connection.getLatestBlockhash()).blockhash;
    tx.feePayer = payerWallet.publicKey;

    let fee = await connection.getFeeForMessage(tx.compileMessage());
    tx.instructions[0] = web3.SystemProgram.transfer({
        fromPubkey: payerWallet.publicKey,
        toPubkey: new web3.PublicKey(destination),
        lamports: amount - (fee.value as number),
    })
    
    let res = await web3.sendAndConfirmTransaction(
        connection,
        tx,
        [payerWallet],
    )

    return [res, Date.now() - start];
}


export async function transferAllSol(
    connection: web3.Connection,
    payerWallet: web3.Keypair,
    destination: string,
) {
    let amount = await connection.getBalance(payerWallet.publicKey);
    return await transferSol(
        connection, 
        payerWallet, 
        amount / web3.LAMPORTS_PER_SOL,
        destination
    );
}


async function test() {
    // let connPool = new ConnectionSolanaPool()
    // let connection = connPool.getConnectionWithProxy();
    let connection = new web3.Connection(web3.clusterApiUrl("mainnet-beta"));
    // let res = await connection.getLatestBlockhash();
    // console.log(res);

    let amount_send = Math.round(0.005 * web3.LAMPORTS_PER_SOL);
    let payerWallet = web3.Keypair.fromSecretKey(bs58.decode(process.env.WALLET_MOONSHOT_PRIVATE_KEY as string));
    // let [res, taken] = await transferSolToWallets(connection, payerWallet, {
    //     "GoyQaVccEUrMByWsDTQNS1AkRGMuJDozH15kephjSKg9": amount_send
    // });
    // console.log(`res: ${res}, taken: ${taken}`);
    let sender = web3.Keypair.fromSecretKey(bs58.decode("2DwTDxioWTuoDvB2TentaM2A4YR4uZ6jweocimDf4YUB2zoefp9EaEXzJvKzWFzEuD98gTywuSmjtfMQSQCNCn46"));
    let amount = await connection.getBalance(sender.publicKey);
    console.log(`amount: ${amount}`);
    // let amount = Math.round(0.004 * web3.LAMPORTS_PER_SOL) - 1000;
    // // console.log(`sender: ${sender.publicKey.toBase58()}`);
    
    let [res, taken] = await transferSol(connection, sender, 0, payerWallet.publicKey.toBase58());
    console.log(`res: ${res}, taken: ${taken}`);
}

// test();