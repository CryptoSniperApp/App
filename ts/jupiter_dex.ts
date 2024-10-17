import {
QuoteGetRequest,
QuoteResponse,
SwapResponse,
createJupiterApiClient,
} from "@jup-ag/api";
import { Keypair, VersionedTransaction, Transaction } from "@solana/web3.js";
import { Wallet } from "@project-serum/anchor";
import bs58 from "bs58";
import {
    BlockhashWithExpiryBlockHeight,
    Connection,
    TransactionExpiredBlockheightExceededError,
    VersionedTransactionResponse,
} from "@solana/web3.js";
import promiseRetry from "promise-retry";


type TransactionSenderAndConfirmationWaiterArgs = {
    connection: Connection;
    serializedTransaction: Buffer;
    blockhashWithExpiryBlockHeight: BlockhashWithExpiryBlockHeight;
};
const wait = (time: number) => new Promise((resolve) => setTimeout(resolve, time));
const SEND_OPTIONS = {
    skipPreflight: true,
};

export async function transactionSenderAndConfirmationWaiter({
    connection,
    serializedTransaction,
    blockhashWithExpiryBlockHeight,
}: TransactionSenderAndConfirmationWaiterArgs): Promise<VersionedTransactionResponse | null> {
const txid = await connection.sendRawTransaction(
    serializedTransaction,
    SEND_OPTIONS
);

const controller = new AbortController();
const abortSignal = controller.signal;

const abortableResender = async () => {
    while (true) {
    await wait(2_000);
    if (abortSignal.aborted) return;
    try {
        await connection.sendRawTransaction(
        serializedTransaction,
        SEND_OPTIONS
        );
    } catch (e) {
        console.warn(`Failed to resend transaction: ${e}`);
    }
    }
};

try {
    abortableResender();
    const lastValidBlockHeight =
    blockhashWithExpiryBlockHeight.lastValidBlockHeight - 150;

    // this would throw TransactionExpiredBlockheightExceededError
    await Promise.race([
    connection.confirmTransaction(
        {
        ...blockhashWithExpiryBlockHeight,
        lastValidBlockHeight,
        signature: txid,
        abortSignal,
        },
        "confirmed"
    ),
    new Promise(async (resolve) => {
        // in case ws socket died
        while (!abortSignal.aborted) {
        await wait(2_000);
        const tx = await connection.getSignatureStatus(txid, {
            searchTransactionHistory: false,
        });
        if (tx?.value?.confirmationStatus === "confirmed") {
            resolve(tx);
        }
        }
    }),
    ]);
} catch (e) {
    if (e instanceof TransactionExpiredBlockheightExceededError) {
    // we consume this error and getTransaction would return null
    return null;
    } else {
    // invalid state from web3.js
    throw e;
    }
} finally {
    controller.abort();
}

// in case rpc is not synced yet, we add some retries
const response = promiseRetry(
    async (retry) => {
    const response = await connection.getTransaction(txid, {
        commitment: "confirmed",
        maxSupportedTransactionVersion: 0,
    });
    if (!response) {
        retry(response);
    }
    return response;
    },
    {
    retries: 5,
    minTimeout: 1e3,
    }
);

return response;
}


export function getSignature(
  transaction: Transaction | VersionedTransaction
): string {
  const signature =
    "signature" in transaction
      ? transaction.signature
      : transaction.signatures[0];
  if (!signature) {
    throw new Error(
      "Missing transaction signature, the transaction was not signed by the fee payer"
    );
  }
  return bs58.encode(signature);
}
console.error(process.env.MOONSHOT_RPC_ENDPOINT);

// Make sure that you are using your own RPC endpoint.
// const connection = new Connection("https://api.mainnet-beta.solana.com");
const connection = new Connection(process.env.MOONSHOT_RPC_ENDPOINT as string);
const jupiterQuoteApi = createJupiterApiClient();


export async function swapTokensOnJupiter(
    connection: Connection,
    inputMint: string,
    outputMint: string,
    amount: number,
    slippageBps: number,
    swapMode: "BUY" | "SELL",
    decimals: number,
    kp: Keypair
) {
    const params: QuoteGetRequest = {
        inputMint: inputMint,
        outputMint: outputMint,
        amount: amount * (10 ** decimals),
        // autoSlippage: true,
        // autoSlippageCollisionUsdValue: 1_000,
        maxAutoSlippageBps: slippageBps * 100,
        minimizeSlippage: true,
        onlyDirectRoutes: false,
        asLegacyTransaction: false,
        swapMode: swapMode === "BUY" ? "ExactOut" : "ExactIn"
    };
    console.log("params", params);
    // get quote
    const quote = await jupiterQuoteApi.quoteGet(params);
    console.log("quote", quote);
    if (!quote) {
        throw new Error("unable to quote");
    }

    let wallet = new Wallet(kp);
    const swapObj = await getSwapObj(wallet, quote);


    // Serialize the transaction
    const swapTransactionBuf = Buffer.from(swapObj.swapTransaction, "base64");
    var transaction = VersionedTransaction.deserialize(swapTransactionBuf);

    // Sign the transaction
    transaction.sign([wallet.payer]);
    const signature = getSignature(transaction);

    // We first simulate whether the transaction would be successful
    const { value: simulatedTransactionResponse } =
        await connection.simulateTransaction(transaction, {
            replaceRecentBlockhash: true,
            commitment: "processed",
        });
    const { err, logs } = simulatedTransactionResponse;

    if (err) {
        console.error("Simulation Error:");
        console.error({ err, logs });
        return;
    }   

    const serializedTransaction = Buffer.from(transaction.serialize());
    const blockhash = transaction.message.recentBlockhash;

    const transactionResponse = await transactionSenderAndConfirmationWaiter({
        connection,
        serializedTransaction,
        blockhashWithExpiryBlockHeight: {
        blockhash,
        lastValidBlockHeight: swapObj.lastValidBlockHeight,
        },
    });

    // If we are not getting a response back, the transaction has not confirmed.
    if (!transactionResponse) {
        console.error("Transaction not confirmed");
        return;
    }

    if (transactionResponse.meta?.err) {
        console.error(transactionResponse.meta?.err);
    }

    console.log(`https://solscan.io/tx/${signature}`);
    return signature;
}


async function getQuote() {
    // basic params
    // const params: QuoteGetRequest = {
    //   inputMint: "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn",
    //   outputMint: "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So",
    //   amount: 35281,
    //   slippageBps: 50,
    //   onlyDirectRoutes: false,
    //   asLegacyTransaction: false,
    // }

    // auto slippage w/ minimizeSlippage params
    const params: QuoteGetRequest = {
        inputMint: "43uhykFm8Y9gLvHrWs7r7w1HCKu6vikDi7j394FaSfNz",
        outputMint: "So11111111111111111111111111111111111111112",
        amount: 1 * (10 ** 9), // 0.1 SOL
        autoSlippage: true,
        autoSlippageCollisionUsdValue: 1_000,
        maxAutoSlippageBps: 1000, // 10%
        minimizeSlippage: true,
        onlyDirectRoutes: false,
        asLegacyTransaction: false,
        swapMode: "ExactIn"
    };
    // get quote
    const quote = await jupiterQuoteApi.quoteGet(params);

    if (!quote) {
        throw new Error("unable to quote");
    }
    return quote;
}

async function getSwapObj(wallet: Wallet, quote: QuoteResponse) {
    // Get serialized transaction
    const swapObj = await jupiterQuoteApi.swapPost({
        swapRequest: {
            quoteResponse: quote,
            userPublicKey: wallet.publicKey.toBase58(),
            dynamicComputeUnitLimit: true,
            prioritizationFeeLamports: "auto",
        },
    });
    return swapObj;
}

async function flowQuoteAndSwap() {
    let privateKey = process.env.WALLET_MOONSHOT_PRIVATE_KEY as string;
    const wallet = new Wallet(
        Keypair.fromSecretKey(bs58.decode(privateKey))
    );

    console.log("Wallet:", wallet.publicKey.toBase58());

    const quote = await getQuote();
    console.dir(quote, { depth: null });
    const swapObj = await getSwapObj(wallet, quote);
    console.dir(swapObj, { depth: null });
    
    // Serialize the transaction
    const swapTransactionBuf = Buffer.from(swapObj.swapTransaction, "base64");
    var transaction = VersionedTransaction.deserialize(swapTransactionBuf);

    // Sign the transaction
    transaction.sign([wallet.payer]);
    const signature = getSignature(transaction);

    // We first simulate whether the transaction would be successful
    const { value: simulatedTransactionResponse } =
        await connection.simulateTransaction(transaction, {
            replaceRecentBlockhash: true,
            commitment: "processed",
        });
    const { err, logs } = simulatedTransactionResponse;

    if (err) {
        // Simulation error, we can check the logs for more details
        // If you are getting an invalid account error, make sure that you have the input mint account to actually swap from.
        console.error("Simulation Error:");
        console.error({ err, logs });
        return;
    }   

    const serializedTransaction = Buffer.from(transaction.serialize());
    const blockhash = transaction.message.recentBlockhash;

    const transactionResponse = await transactionSenderAndConfirmationWaiter({
        connection,
        serializedTransaction,
        blockhashWithExpiryBlockHeight: {
        blockhash,
        lastValidBlockHeight: swapObj.lastValidBlockHeight,
        },
    });

    // If we are not getting a response back, the transaction has not confirmed.
    if (!transactionResponse) {
        console.error("Transaction not confirmed");
        return;
    }

    if (transactionResponse.meta?.err) {
        console.error(transactionResponse.meta?.err);
    }

    console.log(`https://solscan.io/tx/${signature}`);
}

async function main() {
    // await flowQuoteAndSwap();

    let inputMint = "So11111111111111111111111111111111111111112";
    // let inputMint = "41upazdWAgLjfCkLGQwGDgj2knovnpPyr4q2ZVNjifLz";
    
    let outputMint = "41upazdWAgLjfCkLGQwGDgj2knovnpPyr4q2ZVNjifLz";
    // let outputMint = "So11111111111111111111111111111111111111112";
    let amount = 5;
    let slippage = 5;
    let swapMode = "BUY";
    let decimals = 9;
    let kp = Keypair.fromSecretKey(bs58.decode(process.env.WALLET_MOONSHOT_PRIVATE_KEY as string));
    // const connection = new Connection(process.env.MOONSHOT_RPC_ENDPOINT as string, "processed");
    const connection = new Connection("https://api.mainnet-beta.solana.com");
    await swapTokensOnJupiter(
        connection,
        inputMint,
        outputMint,
        amount,
        slippage,
        swapMode as "BUY" | "SELL",
        decimals,
        kp
    );
}

// main();