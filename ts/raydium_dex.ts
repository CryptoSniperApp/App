import { Raydium, SwapSide, TxVersion, parseTokenAccountResp } from '@raydium-io/raydium-sdk-v2'
import { Connection, Keypair, PublicKey, clusterApiUrl } from '@solana/web3.js'
import { TOKEN_PROGRAM_ID, TOKEN_2022_PROGRAM_ID } from '@solana/spl-token'
import bs58 from 'bs58'
import { ApiV3PoolInfoStandardItem, AmmV4Keys, AmmRpcData } from '@raydium-io/raydium-sdk-v2'
import BN from 'bn.js'
import { AMM_V4, AMM_STABLE, DEVNET_PROGRAM_ID } from '@raydium-io/raydium-sdk-v2'
import Decimal from 'decimal.js'
import { NATIVE_MINT } from '@solana/spl-token'
import * as web3 from '@solana/web3.js'

let privateKey = process.env.WALLET_MOONSHOT_PRIVATE_KEY as string;
export const owner: Keypair = Keypair.fromSecretKey(bs58.decode(privateKey));
// export const connection = new Connection(process.env.MOONSHOT_RPC_ENDPOINT as string);
export const connection = new Connection('https://api.mainnet-beta.solana.com');
export const txVersion = TxVersion.V0
const cluster = 'mainnet'


const VALID_PROGRAM_ID = new Set([
    AMM_V4.toBase58(),
    AMM_STABLE.toBase58(),
    DEVNET_PROGRAM_ID.AmmV4.toBase58(),
    DEVNET_PROGRAM_ID.AmmStable.toBase58(),
])
  
export const isValidAmm = (id: string) => VALID_PROGRAM_ID.has(id)

let raydium: Raydium | undefined
export const initSdk = async (params?: { loadToken?: boolean }) => {
  if (raydium) return raydium
  console.log(`connect to rpc ${connection.rpcEndpoint} in ${cluster}`)
  raydium = await Raydium.load({
    owner,
    connection,
    cluster,
    disableFeatureCheck: true,
    disableLoadToken: !params?.loadToken,
    blockhashCommitment: 'finalized',
    // urlConfigs: {
    //   BASE_HOST: '<API_HOST>', // api url configs, currently api doesn't support devnet
    // },
  })

  /**
   * By default: sdk will automatically fetch token account data when need it or any sol balace changed.
   * if you want to handle token account by yourself, set token account data after init sdk
   * code below shows how to do it.
   * note: after call raydium.account.updateTokenAccount, raydium will not automatically fetch token account
   */

  /*  
  raydium.account.updateTokenAccount(await fetchTokenAccountData())
  connection.onAccountChange(owner.publicKey, async () => {
    raydium!.account.updateTokenAccount(await fetchTokenAccountData())
  })
  */

  return raydium
}

export const fetchTokenAccountData = async () => {
  const solAccountResp = await connection.getAccountInfo(owner.publicKey)
  const tokenAccountResp = await connection.getTokenAccountsByOwner(owner.publicKey, { programId: TOKEN_PROGRAM_ID })
  const token2022Req = await connection.getTokenAccountsByOwner(owner.publicKey, { programId: TOKEN_2022_PROGRAM_ID })
  const tokenAccountData = parseTokenAccountResp({
    owner: owner.publicKey,
    solAccountResp,
    tokenAccountResp: {
      context: tokenAccountResp.context,
      value: [...tokenAccountResp.value, ...token2022Req.value],
    },
  })
  return tokenAccountData
}


/**
 * 
 * combination of swapSolToToken and swapIn:
 * 
 * swapSolToToken = true, swapIn = false -> SWAP SOL TO TOKEN (BUY)
 * swapSolToToken = false, swapIn = true -> SWAP TOKEN TO SOL (SELL)
 * 
 * @param swapSolToToken set to true if swapping sol to token
 * @param swapIn set to true if swapping in
 */
export async function swapRaydiumTokens(
    poolAddress: PublicKey, 
    swapAmount: BN, 
    swapSolToToken: boolean,
    swapIn: boolean = true,
    slippage: number = 0.05, 
    microLamports: number = 200_000,
    sendAndConfirm: boolean = true
): Promise<[string, number] | undefined> {
    const raydium = await initSdk()
    const poolId = poolAddress.toBase58();

    let poolInfo: ApiV3PoolInfoStandardItem | undefined
    let poolKeys: AmmV4Keys | undefined
    let rpcData: AmmRpcData

    const data = await raydium.api.fetchPoolById({ ids: poolId })
    poolInfo = data[0] as ApiV3PoolInfoStandardItem

    if (!poolInfo) {
        return;
    }

    let solMint = poolInfo?.mintA.address === NATIVE_MINT.toBase58() ? poolInfo.mintA.address : poolInfo.mintB.address;
    let otherMint = solMint === poolInfo.mintA.address ? poolInfo.mintB.address : poolInfo.mintA.address;
    
    let inputMint = swapSolToToken ? solMint : otherMint;
    console.log("inputMint", inputMint);

    poolKeys = await raydium.liquidity.getAmmPoolKeys(poolId)
    rpcData = await raydium.liquidity.getRpcPoolInfo(poolId)
    
    const [baseReserve, quoteReserve, status] = [rpcData.baseReserve, rpcData.quoteReserve, rpcData.status.toNumber()]
  
    if (poolInfo.mintA.address !== inputMint && poolInfo.mintB.address !== inputMint)
      throw new Error('input mint does not match pool')
  
    const baseIn = inputMint === poolInfo.mintA.address
    const [mintIn, mintOut] = baseIn ? [poolInfo.mintA, poolInfo.mintB] : [poolInfo.mintB, poolInfo.mintA]

    var amountIn: BN;
    var amountOut: BN;
    var fixedSide: SwapSide;
    var out;

    if (swapIn) {
        out = raydium.liquidity.computeAmountOut({
            poolInfo: {
              ...poolInfo,
              baseReserve,
              quoteReserve,
              status,
              version: 4,
            },
            amountIn: new BN(swapAmount),
            mintIn: mintIn.address,
            mintOut: mintOut.address,
            slippage: slippage,
        })
        amountIn = new BN(swapAmount);
        amountOut = out.minAmountOut;
        fixedSide = 'in'
    } else {
        out = raydium.liquidity.computeAmountIn({
            poolInfo: {
              ...poolInfo,
              baseReserve,
              quoteReserve,
              status,
              version: 4,
            },
            amountOut: new BN(swapAmount),
            mintIn: mintIn.address,
            mintOut: mintOut.address,
            slippage: slippage, // range: 1 ~ 0.0001, means 100% ~ 0.01%
          })
        amountIn = out.maxAmountIn;
        amountOut = new BN(swapAmount)
        fixedSide = 'out'
    }
    console.log("amountIn", amountIn);
    console.log("amountOut", amountOut);
    console.log("fixedSide", fixedSide);
    console.log("mintIn", mintIn);
    console.log("mintOut", mintOut);

    const startSwap = Date.now();
    const { execute } = await raydium.liquidity.swap({
        poolInfo,
        poolKeys,
        amountIn: amountIn,
        amountOut: amountOut,
        fixedSide: fixedSide,
        inputMint: mintIn.address,
        txVersion,

        config: {
            inputUseSolBalance: true, // default: true, if you want to use existed wsol token account to pay token in, pass false
            outputUseSolBalance: true, // default: true, if you want to use existed wsol token account to receive token out, pass false
            associatedOnly: true, // default: true, if you want to use ata only, pass true
        },

        computeBudgetConfig: {
            // units: 600000,
            microLamports: microLamports,
        },
    })

    const { txId } = await execute({ sendAndConfirm: sendAndConfirm })
    return [txId, Date.now() - startSwap];
}


async function main() {
    const poolAddress = new PublicKey("9DJrGmVqHxejzErYsc4LwCSaeAePXH1pCxUzLJVNfV77");
    
    const swapAmount = new BN(20 * (10 ** 9));
    const swapSolToToken = true;
    await swapRaydiumTokens(
        poolAddress, 
        swapAmount, 
        false, // FOR SELL
        true, 
        // true, // FOR BUY
        // false,
    );
}

