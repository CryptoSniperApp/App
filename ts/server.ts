import { Connection, PublicKey } from "@solana/web3.js";
import {
  LIQUIDITY_STATE_LAYOUT_V4,
} from "@raydium-io/raydium-sdk";
import BN from "bn.js";
import { ErrorMesssage, RequestPoolState, ResponsePoolState, PoolStateService, PoolStateServer, ResponsePoolStateOperation } from "./generated_ts_proto/pools";
import * as grpc from '@grpc/grpc-js';


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


interface Error {
  success: boolean;
  error: string
}


export async function parsePoolInfo(poolAddress: string): Promise<PoolInfo> {
  try {
    const connection = new Connection("https://api.mainnet-beta.solana.com", "confirmed");
    const info = await connection.getAccountInfo(new PublicKey(poolAddress));
    if (!info) return { "success": false };
    const poolState = LIQUIDITY_STATE_LAYOUT_V4.decode(info.data);
    const baseDecimal = poolState.baseDecimal.toNumber();
    const quoteDecimal = poolState.quoteDecimal.toNumber();

    const baseTokenAmount = await connection.getTokenAccountBalance(
      poolState.baseVault
    );
    const quoteTokenAmount = await connection.getTokenAccountBalance(
      poolState.quoteVault
    );

    const denominator = new BN(10).pow(poolState.baseDecimal);

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
const impl: PoolStateServer = {
  async getPoolState(call: grpc.ServerUnaryCall<RequestPoolState, RequestPoolState>, callback: grpc.sendUnaryData<ResponsePoolStateOperation>): Promise<void> {
    var data = await parsePoolInfo(call.request.poolAddress);
    var responseData: any = {}

    if (data.success) {
      let resp = ResponsePoolState.create({
        baseDecimal: data.baseDecimal,
        baseTokenAddress: data.baseTokenAddress,
        baseTokenAmount: data.baseVault,
  
        quoteDecimal: data.quoteDecimal,
        quoteTokenAddress: data.quoteTokenAddress,
        quoteTokenAmount: data.quoteVault,
  
        poolAddress: call.request.poolAddress,

        baseMint: data.baseMint,
        quoteMint: data.quoteMint,
      });
      responseData["data"] = resp;
    }
    else {
      let resp = ErrorMesssage.create({error: data.error});
      responseData["error"] = resp;
    }
    callback(null, ResponsePoolStateOperation.create(responseData));
  }
}


server.bindAsync('0.0.0.0:50051', grpc.ServerCredentials.createInsecure(), (error, port) => {
  server.addService(PoolStateService, impl)
  if (error) {
    throw error
  }
  console.log(`gRPC server started on port ${port}`);
});

