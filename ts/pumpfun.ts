import {
    BorshCoder,
    AnchorProvider,
    Wallet
} from "@coral-xyz/anchor";
import { bs58 } from "@coral-xyz/anchor/dist/cjs/utils/bytes";
import { Connection, Keypair, LAMPORTS_PER_SOL, PublicKey } from "@solana/web3.js";
import * as pumpfun from "pumpdotfun-sdk";
import { ConnectionSolanaPool } from "./connection_pool";
import { getAssociatedTokenAccount, getTokenAmountInWallet } from "./trade_utils";


function getSdk(privateKey: string, connection: Connection) {
    let kp = Keypair.fromSecretKey(bs58.decode(privateKey))
    let wallet = new Wallet(kp)
    let provider = new AnchorProvider(connection, wallet, {})
    return new pumpfun.PumpFunSDK(provider)
}


export async function decodePumpFunBuyEvent(programData: string) {
    let privateKey = process.env.WALLET_MOONSHOT_PRIVATE_KEY;
    if (!privateKey) {
        throw new Error("WALLET_MOONSHOT_PRIVATE_KEY is not set")
    }
    let connection = new Connection(
        "https://api.mainnet-beta.solana.com",
        "confirmed"
    )

    let sdk = getSdk(privateKey, connection)
    let coder: BorshCoder = (sdk.program as any)._coder
    let args = coder.events.decode(programData as any);
    if (args?.data.solAmount) {
        args.data.solAmount = (args?.data.solAmount as any).toNumber()
    }
    if (args?.data.tokenAmount) {
        args.data.tokenAmount = (args?.data.tokenAmount as any).toNumber()
    }
    
    return args;
}


export async function swap(
    connection: Connection, 
    privateKey: string, 
    txType: "BUY" | "SELL", 
    mintAddress: string, 
    amount: number,
    slippageBps: number = 500,
    unitLimit: number = 150_000,
    unitPrice: number = 7_666_666
) {
    let sdk = getSdk(privateKey, connection);
    let kp = Keypair.fromSecretKey(bs58.decode(privateKey))
    console.log(`${txType}: ${new Date()}`)
    if (txType === "BUY") {
        let error;
        for (let i = 0; i <= 3; i++) {
            try {
                let result = await sdk.buy(
                    kp, 
                    new PublicKey(mintAddress), 
                    BigInt(Math.round(amount * LAMPORTS_PER_SOL)), 
                    BigInt(slippageBps),
                    {
                        unitLimit,
                        unitPrice,
                    }
                )
                return result
            } catch (e) {
                console.log(e)
                error = e as Error
                await new Promise(resolve => setTimeout(resolve, 1000))
            }
        }       
        throw error

    } else if (txType === "SELL") {
        if (amount === 0) {
            let ata = await getAssociatedTokenAccount(
                mintAddress,
                kp.publicKey.toBase58()
            )
            amount = await getTokenAmountInWallet(
                connection, 
                ata.toBase58()
            ) as number
            if (!amount) {
                throw new Error(`not mint in wallet ${mintAddress}`)
            }
        }
        let result = await sdk.sell(
            kp, 
            new PublicKey(mintAddress), 
            BigInt(Math.round(amount * Math.pow(10, pumpfun.DEFAULT_DECIMALS))),
            BigInt(slippageBps),
            {
                unitLimit,
                unitPrice,
            }
        )
        return result
    }
    throw new Error("Invalid transaction type")
}


const main = async () => {
    let connection = new ConnectionSolanaPool().getConnectionWithProxy();
    let mintAddress = "3KFqXYXwsSocsLBTKK9thH11bVGRcP2yKxLaC3Vkpump"
    // let ata = await getAssociatedTokenAccount(
    //     mintAddress,
    //     Keypair.fromSecretKey(bs58.decode(process.env.WALLET_MOONSHOT_PRIVATE_KEY as string)).publicKey.toBase58()
    // )
    // console.log(ata)
    // let amount = await getTokenAmountInWallet(
    //     connection, 
    //     ata.toBase58()
    // )
    // let amount = 0.0000005
    // console.log(amount)
    // let result = await swap(
    //     connection, 
    //     process.env.WALLET_MOONSHOT_PRIVATE_KEY as string, 
    //     "BUY", 
    //     mintAddress,
    //     amount,
    // )
    // console.log(result)
    let decoded = await decodePumpFunBuyEvent("vdt/007mYe7dQ5u7DicD8/VNBXs6JjtcwNXeymnolwliNFgHvQOd6WIPCcUAAAAARv+iCk46AAAAvCAET2kopqmFLAvYcz7Of12gwRaEq8sEw0NAQkMoZyShdCBnAAAAAJuB4RsJAAAAI4TtPlXsAgCb1b0fAgAAACPs2vLD7QEA")
    console.log(decoded)
};

// main();