import { Connection, Keypair, PublicKey } from "@solana/web3.js";
import { LIQUIDITY_STATE_LAYOUT_V4 } from "@raydium-io/raydium-sdk";
import * as pools from "./generated_ts_proto/pools";
import * as grpc from '@grpc/grpc-js';
import * as trade_utils from './trade_utils';
import bs58 from "bs58";
import * as dotenv from 'dotenv';
import * as wallet_utils from './wallet_utils';
import { web3 } from "@project-serum/anchor";
import { ConnectionSolanaPool } from "./connection_pool";

dotenv.config();
const connection = new Connection("https://api.mainnet-beta.solana.com", "confirmed");

interface PoolInfo {
  success: boolean;
  baseVault?: string;
  quoteVault?: string;
  baseDecimal?: number;
  quoteDecimal?: number;
  baseTokenAddress?: string,
  quoteTokenAddress?: string,
  baseMint?: string,
  quoteMint?: string,
  error?: string
}


export const connPool = new ConnectionSolanaPool();


export async function parsePoolInfo(poolData: Buffer): Promise<PoolInfo> {
  try {
    if (!poolData) return { "success": false };
    const poolState = LIQUIDITY_STATE_LAYOUT_V4.decode(poolData);
    const baseDecimal = Number(poolState.baseDecimal.toString());
    const quoteDecimal = Number(poolState.quoteDecimal.toString());

    const baseTokenAmount = await connection.getTokenAccountBalance(
      poolState.baseVault
    );
    const quoteTokenAmount = await connection.getTokenAccountBalance(
      poolState.quoteVault
    );
    {}

    return {
      "success": true,
      "baseVault": baseTokenAmount.value.uiAmountString,
      "quoteVault": quoteTokenAmount.value.uiAmountString,
      "baseDecimal": baseDecimal,
      "quoteDecimal": quoteDecimal,
      "baseTokenAddress": poolState.baseVault.toString(),
      "quoteTokenAddress": poolState.quoteVault.toString(),
      "baseMint": poolState.baseMint.toString(),
      "quoteMint": poolState.quoteMint.toString(),
    }
  } catch (err) {
    return { "success": false, "error": `${err}` }
  }
}


const server = new grpc.Server();
const impl: pools.PoolStateServer = {
  async getPoolState(
    call: grpc.ServerUnaryCall<pools.RequestPoolState, pools.RequestPoolState>, 
    callback: grpc.sendUnaryData<pools.ResponsePoolStateOperation>
  ): Promise<void> {
    var data = await parsePoolInfo(Buffer.from(call.request.poolData));
    var responseData: any = {};

    if (data.success) {
      let resp = pools.ResponsePoolState.create({
        baseDecimal: data.baseDecimal,
        baseTokenAddress: data.baseTokenAddress,
        baseTokenAmount: data.baseVault,
  
        quoteDecimal: data.quoteDecimal,
        quoteTokenAddress: data.quoteTokenAddress,
        quoteTokenAmount: data.quoteVault,

        baseMint: data.baseMint,
        quoteMint: data.quoteMint,
      });
      responseData.data = resp;
    }
    else {
      let resp = pools.ErrorMesssage.create({error: data.error});
      responseData.error = resp;
    }
    callback(null, pools.ResponsePoolStateOperation.create(responseData));
  }
}

const tokensImpl: pools.TokensSolanaServer = {
  async swapTokens(
    call: grpc.ServerUnaryCall<pools.RequestSwapTokens, pools.RequestSwapTokens>, 
    callback: grpc.sendUnaryData<pools.ResponseSwapTokens>
  ): Promise<void> {
    let connection = connPool.getConnectionWithProxy();
    let resp;
    try {
      let req = call.request;
      let kp = Keypair.fromSecretKey(bs58.decode(req.privateKey));
      req.amount = Math.round(req.amount);

      let slippage: number | null = null;
      let microlamports: number | null = null;

      if (req.slippage !== 0) {
        slippage = req.slippage;
      }
      if (req.microlamports !== 0) {
        microlamports = req.microlamports;
      }

      if (req.swapAll == true && req.transactionType == "SELL") {
        if (req.tokenAccountAddress == "") {
          let tokenAccountAddress = await trade_utils.getAssociatedTokenAccount(
            req.mint,
            kp.publicKey.toBase58()
          )

          req.tokenAccountAddress = tokenAccountAddress.toString();
        }

        let balance = await trade_utils.getTokenAmountInWallet(
          connection,
          req.tokenAccountAddress
        );
        if (balance) {
          req.amount = balance;
        }

      }
      var decimals;

      if (req.decimal === 0 || !req.decimal) {
        try {
          let info = await connection.getParsedAccountInfo(
            new PublicKey(req.mint),
            "confirmed"
          )
          if (info) {
            let parsed = info.value?.data as any;
            decimals = parsed.parsed.info.decimals;
          }
        } catch (error) {
          console.error(`we got an error when try to get token decimals for mint: ${req.mint}. error: ${error}`)
        }
      } else {
        decimals = req.decimal;
      }
      
      let txHash: string = "";
      let taken: number | null = null;
      
      [txHash, taken] = await trade_utils.swapTokens(
        connection, 
        req.transactionType as "BUY" | "SELL", 
        req.mint,
        req.privateKey,
        req.amount, 
        slippage,
        microlamports,
        decimals
      )

      if (req.closeAccount == true) {
        try {
          let resp = await trade_utils.closeTokenAccount(
            req.tokenAccountAddress,
            kp,
            connection,
            kp.publicKey,
            kp.publicKey
          )
          console.log(`closed token account for mint: ${req.mint}. txHash: ${resp}`)
        } catch (error: any) {
          console.error(`we got an error when try to close token account for mint: ${req.mint}. error: ${error}. trace: ${error.stack}`)
        }
      }

      resp = pools.ResponseSwapTokens.create({
        txSignature: txHash,
        msTimeTaken: taken ? taken.toString() : "",
        success: true
      });

    } catch (error: any) {
      console.error(`we got an error when try to swap tokens. error: ${error}. mint: ${call.request.mint}`)
      resp = pools.ResponseSwapTokens.create({
        txSignature: "",
        msTimeTaken: "",
        success: false,
        error: `${error.stack}`
      });
    }

    callback(null, resp);
  },
  async createTokenAccount(
    call: grpc.ServerUnaryCall<pools.CreateTokenAccount, pools.CreateTokenAccount>, 
    callback: grpc.sendUnaryData<pools.ResponseCreateTokenAccount>
  ): Promise<void> {
    let response;
    let connection = connPool.getConnectionWithProxy();
    try {
      let ataPublicKey: PublicKey | null = null;

      if (!call.request.ataPublicKey || call.request.ataPublicKey == "") {
        ataPublicKey = null;
      } else {
        ataPublicKey = new PublicKey(call.request.ataPublicKey);
      }

      let signer = Keypair.fromSecretKey(bs58.decode(call.request.privateKey));
      let resp = await trade_utils.createTokenAccount(
        call.request.mint,
        signer.publicKey.toBase58(),
        connection,
        signer,
        ataPublicKey
      )

      response = pools.ResponseCreateTokenAccount.create({
        txSignature: resp,
        success: true
      });
    } catch (error) {
      console.error(`we got an error when try to create token account. error: ${error}. mint: ${call.request.mint}`)
      response = pools.ResponseCreateTokenAccount.create({
        success: false
      });
    }
    
    callback(null, response);
  },

  async getAssociatedTokenAccount(
    call: grpc.ServerUnaryCall<pools.GetAssociatedTokenAccount, pools.GetAssociatedTokenAccount>, 
    callback: grpc.sendUnaryData<pools.ResponseGetAssociatedTokenAccount>
  ): Promise<void> {
    let resp;
    try {
      resp = await trade_utils.getAssociatedTokenAccount(
        call.request.mintAddress,
        call.request.walletPublicKey
      )

      resp = pools.ResponseGetAssociatedTokenAccount.create({
        ataPublicKey: resp.toString(),
        success: true
      });
    } catch (error) {
      console.error(`we got an error when try to get associated token account. error: ${error}. mint: ${call.request.mintAddress}`)
      resp = pools.ResponseGetAssociatedTokenAccount.create({
        success: false
      });
    }

    callback(null, resp);
  },
  async closeTokenAccount(
    call: grpc.ServerUnaryCall<pools.CloseTokenAccount, pools.CloseTokenAccount>, 
    callback: grpc.sendUnaryData<pools.ResponseCloseTokenAccount>
  ): Promise<void> {
    let resp;
    try {
      let req = call.request;
      let connection = connPool.getConnectionWithProxy();

      let signer = Keypair.fromSecretKey(bs58.decode(req.walletPrivateKey));
      resp = await trade_utils.closeTokenAccount(
        req.tokenAccountAddress,
        signer,
        connection,
        signer.publicKey,
        signer.publicKey
    )

      resp = pools.ResponseCloseTokenAccount.create({
        txSignature: resp,
        success: true
    });
    } catch (error) {
      console.error(`we got an error when try to close token account. error: ${error}. address: ${call.request.tokenAccountAddress}`)
      resp = pools.ResponseCloseTokenAccount.create({
        success: false
      });
    }

    callback(null, resp);
  },
  async transferSolToWallets(
    call: grpc.ServerUnaryCall<pools.TransferSolToWallets, pools.TransferSolToWallets>, 
    callback: grpc.sendUnaryData<pools.ResponseRpcOperation>
  ): Promise<void> {
    // let connection = connPool.getChainstackConnection();
    let connection = connPool.getConnectionWithProxy();
    let payerWallet = Keypair.fromSecretKey(bs58.decode(call.request.payerPrivateKey));
    let response;
    console.log(`amountsWallets: ${Object.values(call.request.walletsAmounts)}`);

    let amounts: { [key: string]: number } = {};
    for (let [key, value] of Object.entries(call.request.walletsAmounts)) {
      amounts[key] = Math.round(value * web3.LAMPORTS_PER_SOL);
    }

    try {
      let [txHash, taken] = await wallet_utils.transferSolToWallets(
        connection,
        payerWallet,
        amounts
      )
      response = pools.ResponseRpcOperation.create({
        success: true,
        rawData: `${txHash}`,
        msTimeTaken: taken.toString()
      })
    } catch (error: any) {
      response = pools.ResponseRpcOperation.create({
        success: false,
        rawData: `error: ${error}. traceback: ${error.stack}`,
        msTimeTaken: ""
      });
    }

    callback(null, response);
  },
  async receiveSolFromWallets(
    call: grpc.ServerUnaryCall<pools.ReceiveSolFromWallets, pools.ReceiveSolFromWallets>, 
    callback: grpc.sendUnaryData<pools.ResponseRpcOperation>
  ): Promise<void> {
    let destination = call.request.destinationWalletPublicKey;
    let response;

    let promises = [];
    try {
      for (let [wallet, amount] of Object.entries(call.request.walletsDatas)) {
        let connection = connPool.getConnectionWithProxy();
        let kp = Keypair.fromSecretKey(bs58.decode(wallet));
        // console.log(`transfer sol from wallet ${kp.publicKey.toBase58()} to wallet: ${destination}. amount: ${amount}`);
        promises.push(wallet_utils.transferSol(connection, kp, amount, destination));
      }

      let start = new Date();
      let res = await Promise.all(promises);
      let end = new Date();
      response = pools.ResponseRpcOperation.create({
        success: true,
        rawData: JSON.stringify(res),
        msTimeTaken: `${end.getTime() - start.getTime()}`
      });
    } catch (error: any) {
      response = pools.ResponseRpcOperation.create({
        success: false,
        rawData: `error: ${error}. traceback: ${error.stack}`,
        msTimeTaken: ""
      });
    }

    callback(null, response);
  }
}

server.bindAsync('0.0.0.0:50051', grpc.ServerCredentials.createInsecure(), (error, port) => {
  server.addService(pools.PoolStateService, impl);
  server.addService(pools.TokensSolanaService, tokensImpl);
  if (error) {
    throw error
  }

  console.log(`${error} gRPC server started on port ${port}`);
});

