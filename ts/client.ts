import { PoolStateClient, RequestPoolState } from "./generated_ts_proto/pools";
import * as grpc from '@grpc/grpc-js';
import { Connection, PublicKey } from "@solana/web3.js";

async function testGrpcClient() {

  const connection = new Connection("https://api.mainnet-beta.solana.com", "confirmed");
  let data = await connection.getAccountInfo(new PublicKey("HvAqakZgurMR2br1eGWPU6EeFcxzmeW8n6Mn7ejEf3DV"));
  if (!data) {return}

  const client = new PoolStateClient('localhost:50051', grpc.credentials.createInsecure());
  const request = RequestPoolState.create({poolData: data.data});

  client.getPoolState(request, (err, response) => {
    console.log(response, err)
  });
}

testGrpcClient();
