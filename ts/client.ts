import { PoolStateClient, RequestPoolState } from "./generated_ts_proto/pools";
import * as grpc from '@grpc/grpc-js';

async function testGrpcClient() {
  const client = new PoolStateClient('localhost:50051', grpc.credentials.createInsecure());

  const request = RequestPoolState.create(
    {poolAddress: "AB1eu2L1Jr3nfEft85AuD2zGksUbam1Kr8MR3uM2sjwt"}
  );

  client.getPoolState(request, (err, response) => {
    console.log(response, err)
  });
}

testGrpcClient();
