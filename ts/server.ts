import { Connection } from "@solana/web3.js";
import { LIQUIDITY_STATE_LAYOUT_V4 } from "@raydium-io/raydium-sdk";
import { ErrorMesssage, RequestPoolState, ResponsePoolState, ResponsePoolStateOperation, PoolStateService } from "./generated_ts_proto/pools";
import * as grpc from '@grpc/grpc-js';

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


interface Error {
  success: boolean;
  error: string
}


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
const impl = {
  async getPoolState(call: grpc.ServerUnaryCall<RequestPoolState, RequestPoolState>, callback: grpc.sendUnaryData<ResponsePoolStateOperation>): Promise<void> {
    var data = await parsePoolInfo(Buffer.from(call.request.poolData));
    var responseData: any = {};

    if (data.success) {
      let resp = ResponsePoolState.create({
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
      let resp = ErrorMesssage.create({error: data.error});
      responseData.error = resp;
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

