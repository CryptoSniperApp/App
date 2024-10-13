import { PoolStateClient, RequestPoolState } from "./generated_ts_proto/pools";
import * as grpc from '@grpc/grpc-js';
import * as web3 from "@solana/web3.js";
import { Connection, PublicKey, Keypair } from "@solana/web3.js";
import base58 from "bs58";
import * as spl from '@solana/spl-token';
import { TOKEN_PROGRAM_ID } from '@solana/spl-token';
import { Environment, FixedSide, Moonshot } from '@wen-moon-ser/moonshot-sdk';
import {
  ComputeBudgetProgram,
  TransactionMessage,
  VersionedTransaction,
} from '@solana/web3.js';

const PRIVKEY = process.env.WALLET_MOONSHOT_PRIVATE_KEY as string;
const KEYPAIR = Keypair.fromSecretKey(base58.decode(PRIVKEY));
const PUBKEY = KEYPAIR.publicKey.toBase58();
const MINT = new PublicKey("3XCGL6zVxhDK2cyRK9ktRrFVqNdcJpmSuiGYbkHfxgTX");


async function runTransaction(
  connection: Connection,
  txType: "BUY" | "SELL",
  mintAddress: string, 
  privKeyWallet: string, 
  amount: number, 
  slippageBps: number = 500, 
  microLamports: number = 200_000, 
) {
  let rpcUrl = connection.rpcEndpoint;
  const moonshot = new Moonshot({
    rpcUrl,
    environment: Environment.DEVNET,
    chainOptions: {
      solana: { confirmOptions: { commitment: 'confirmed' } },
    },
  });

  const token = moonshot.Token({mintAddress: mintAddress});

  // const curvePos = await token.getCurvePosition();
  // console.log('Current position of the curve: ', curvePos); // Prints the current curve position

  const creator = Keypair.fromSecretKey(base58.decode(privKeyWallet));
  console.log('Creator: ', creator.publicKey.toBase58());

  const tokenAmount = BigInt(amount*1000000000); // Buy <amount> * 10^9 tokens

  // Buy example
  const collateralAmount = await token.getCollateralAmountByTokens({
    tokenAmount,
    tradeDirection: txType,
  });

  // TODO: debug this. a compilation process instructions data is in progress
  const { ixs } = await token.prepareIxs({
    slippageBps: slippageBps,
    creatorPK: creator.publicKey.toBase58(),
    tokenAmount,
    collateralAmount,
    tradeDirection: txType,
    fixedSide: FixedSide.OUT, // This means you will get exactly the token amount and slippage is applied to collateral amount
  });
  
  const priorityIx = ComputeBudgetProgram.setComputeUnitPrice({
    microLamports: microLamports,
  });

  const blockhash = await connection.getLatestBlockhash('confirmed');
  let trans = new TransactionMessage({
    payerKey: creator.publicKey,
    recentBlockhash: blockhash.blockhash,
    instructions: [priorityIx, ...ixs],
  });
  const messageV0 = trans.compileToV0Message();
  const transaction = new VersionedTransaction(messageV0);

  transaction.sign([creator]);
  let start = Date.now();
  const txHash = await connection.sendTransaction(transaction, {
    skipPreflight: false,
    maxRetries: 0,
    preflightCommitment: 'confirmed',
  });
  console.log('Transaction time taken: ', Date.now() - start, 'ms');
  console.log('Buy Transaction Hash:', txHash);
}


async function createTokenAccount(mintAddress: string, walletPublicKey: string, connection: Connection): Promise<string> {
  let ata = await spl.getAssociatedTokenAddress(
    new web3.PublicKey(mintAddress), // mint
    new web3.PublicKey(walletPublicKey), // owner
    false // allow owner off curve
  );
  console.log(`ata: ${ata.toBase58()}`);

  let tx = new web3.Transaction();
  tx.add(
    spl.createAssociatedTokenAccountInstruction(
      new web3.PublicKey(walletPublicKey), // payer
      ata, // ata
      new web3.PublicKey(walletPublicKey), // owner
      new web3.PublicKey(mintAddress) // mint
    )
  );

  const signature = await web3.sendAndConfirmTransaction(connection, tx, [KEYPAIR]);
  console.log(`createTokenAccount tx: ${signature}`);
  return signature;
}


async function closeTokenAccount(
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


async function getTokenAccount(mintAddress: string, walletPublicKey: string): Promise<PublicKey> {
  let data = await spl.getAssociatedTokenAddress(
    new PublicKey(mintAddress),
    new PublicKey(walletPublicKey),
    false
  );
  return data;
}



async function testMoonshotSDK() {
  const connection = new Connection("https://api.mainnet-beta.solana.com", "confirmed");
  let mintAddress = "3xvEbWLVi9eZfqCRoDZ38JHPdWcqywvGat4K6BPasbp4";
  await runTransaction(connection, "SELL", mintAddress, PRIVKEY, 1);
  // let tokenAccount = await getTokenAccount(mintAddress, KEYPAIR.publicKey.toBase58());
  // await closeTokenAccount(
  //   tokenAccount.toBase58(),
  //   KEYPAIR,
  //   connection,
  //   KEYPAIR.publicKey,
  //   KEYPAIR.publicKey
  // );
  return;
  await closeTokenAccount(
    "BZqy3XkTSj33YpRaLxYAF9jDBaX1GP8geWk5FpmRAKP3",
    KEYPAIR,
    connection,
    KEYPAIR.publicKey,
    KEYPAIR.publicKey
  );
  // await runTransaction("SELL", mintAddress, PRIVKEY, 98);
  return;
  // let start = Date.now();
  // const rpcUrl = 'https://api.mainnet-beta.solana.com';

  // const moonshot = new Moonshot({
  //   rpcUrl,
  //   environment: Environment.MAINNET,
  //   chainOptions: {
  //     solana: { confirmOptions: { commitment: 'confirmed' } },
  //   },
  // });

  // const token = moonshot.Token({
  //   mintAddress: MINT.toString(),
  // });

  // const curvePos = await token.getCurvePosition();
  // console.log('Current position of the curve: ', curvePos); // Prints the current curve position
  // // return

  // // make sure creator has funds
  // let rawAmount = 0.99;
  // const tokenAmount = BigInt(rawAmount*1000000000);
  
  // // Buy example
  // const collateralAmount = await token.getCollateralAmountByTokens({
  //   tokenAmount,
  //   tradeDirection: 'SELL',
  // });
  // // console.log('collateralAmount: ', collateralAmount);
  // // return
  // const creator = KEYPAIR;
  // console.log('Creator: ', creator.publicKey.toBase58());
  // const { ixs } = await token.prepareIxs({
  //   slippageBps: 500,
  //   creatorPK: creator.publicKey.toBase58(),
  //   tokenAmount,
  //   collateralAmount,
  //   tradeDirection: 'SELL',
  //   fixedSide: FixedSide.IN, // This means you will pay exactly the token amount slippage is applied to collateral amount
  // });

  // const priorityIx = ComputeBudgetProgram.setComputeUnitPrice({
  //   microLamports: 200_000,
  // });

  // const blockhash = await connection.getLatestBlockhash('confirmed');
  // const messageV0 = new TransactionMessage({
  //   payerKey: creator.publicKey,
  //   recentBlockhash: blockhash.blockhash,
  //   instructions: [priorityIx, ...ixs],
  // }).compileToV0Message();

  // const transaction = new VersionedTransaction(messageV0);

  // transaction.sign([creator]);
  // const txHash = await connection.sendTransaction(transaction, {
  //   skipPreflight: false,
  //   maxRetries: 0,
  //   preflightCommitment: 'confirmed',
  // });

  // console.log('Sell Transaction Hash:', txHash);
  // console.log('Time taken: ', Date.now() - start, 'ms');
}


async function testMoonshot() {
  console.log("testMoonshot");

  const connection = new Connection("https://api.mainnet-beta.solana.com", "confirmed");

  // encoded:
  // {
  //   "data": {
  //     "type": {
  //       "defined": "TradeParams"
  //     },
  //     "data": {
  //       "tokenAmount": {
  //         "type": "u64",
  //         "data": "34000000000"
  //       },
  //       "collateralAmount": {
  //         "type": "u64",
  //         "data": "985"
  //       },
  //       "fixedSide": {
  //         "type": "u8",
  //         "data": 1
  //       },
  //       "slippageBps": {
  //         "type": "u64",
  //         "data": "1000"
  //       }
  //     }
  //   }
  // }
  // decoded: vdt/007mYe4A1I7qBwAAANADAAAAAAAABwAAAAAAAAACAAAAAAAAAKeTyEOKfDEA1oZC5sOh6tkGTd3tOQKYBZTvqUjtiZVY2dkYi6fblUEGm4hX/quBhPtof2NGGMA12sQ53BrrO1WYoPAAAAAAAT8Esq5g8GHIQdAVAakMMXo1ZOMZ7OBZsXZBh/5e5zLvAAUAAAB0cmFkZQ==
  // transaction: 4tjz5XFgAn9jKXtbQHLPDzCFdLCZmvx4mMyE2GRapu6fuq8qU5J1pSSnCUdu2CNhoowsJXFh2ouhG7famTEBNvEN


  var resp = await connection.getTransaction(
    "2nq3dec8QmxHk464X7GRYocojjZAryP9JuHsvGzp97Gre1fGpB1rqWFp5fj1X7QGnyABA6cY799GLL9Tp9Dtej1h",
    {
      commitment: "confirmed",
      maxSupportedTransactionVersion: 0,
    }
  );
  console.log(resp?.meta?.logMessages);
  return;
}

async function testGrpcClient() {
  // await testMoonshot();
  await testMoonshotSDK();
  return;
  const connection = new Connection("https://api.mainnet-beta.solana.com", "confirmed");
  let data = await connection.getAccountInfo(new PublicKey("HvAqakZgurMR2br1eGWPU6EeFcxzmeW8n6Mn7ejEf3DV"));
  console.log(data);
  if (!data) {return}

  // const client = new PoolStateClient('localhost:50051', grpc.credentials.createInsecure());
  // const request = RequestPoolState.create({poolData: data.data});

  // client.getPoolState(request, (err, response) => {
  //   console.log(response, err)
  // });
}


// function encodeData() {
//   class TradeParams {
//     constructor({ tokenAmount, collateralAmount, fixedSide, slippageBps }) {
//       this.tokenAmount = tokenAmount;
//       this.collateralAmount = collateralAmount;
//       this.fixedSide = fixedSide;
//       this.slippageBps = slippageBps;
//     }
//   }
  
//   // Определите схему сериализации
//   const schema = new Map([
//     [TradeParams, {
//       kind: 'struct',
//       fields: [
//         ['tokenAmount', 'u64'],
//         ['collateralAmount', 'u64'],
//         ['fixedSide', 'u8'],
//         ['slippageBps', 'u64'],
//       ],
//     }]
//   ]);
  
//   // Пример JSON объекта
//   const tradeParams = new TradeParams({
//     tokenAmount: BigInt("1119149001113311"),
//     collateralAmount: BigInt("34000000"),
//     fixedSide: 1,
//     slippageBps: BigInt("5000"),
//   });
  
//   // Сериализация в бинарные данные
//   const serializedData = borsh.serialize(schema, tradeParams);
  
//   // Кодирование в base58 или base64
//   const base58Encoded = base58.encode(serializedData); // Для base58
//   const base64Encoded = Buffer.from(serializedData).toString('base64'); // Для base64
  
//   console.log(base58Encoded);
//   console.log(base64Encoded);
// }


testGrpcClient();
