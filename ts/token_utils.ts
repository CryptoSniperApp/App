import { Connection, PublicKey } from "@solana/web3.js";
import { Metaplex, isSft } from "@metaplex-foundation/js";
import axios from "axios";


export async function getTokenRawMetadata(connection: Connection, mint: PublicKey) {
    let metaplex = Metaplex.make(connection);
    const metadata = await metaplex.nfts().findByMint({ mintAddress: mint });
    return metadata;
}


type Website = {
    url: string;
    title: string;
}

type Social = {
    url: string;
    type: string;
}


type TokenSummaryMetadata = {
    name: string;
    symbol: string;
    decimals: number;
    image: string;
    description: string;
    websites?: Website[];
    socials?: Social[];
}


export async function getTokenSummaryMetadata(connection: Connection, mint: PublicKey) {
    let rawMetadata = await getTokenRawMetadata(connection, mint);
    

    if (!isSft(rawMetadata)) {
        throw new Error("Not an SFT");
    }

    let resp = await axios.get(rawMetadata.uri);
    let dexScreenerInfo = resp.data;
    console.log(dexScreenerInfo);

    let summary: TokenSummaryMetadata = {
        name: rawMetadata.name,
        symbol: rawMetadata.symbol,
        decimals: rawMetadata.mint.decimals,
        image: dexScreenerInfo.image,
        description: dexScreenerInfo.description,
        websites: [],
        socials: [],
    }

    dexScreenerInfo.socials.forEach((social: any) => {
        summary.socials?.push({
            url: social.url,
            type: social.type,
        });
    });

    dexScreenerInfo.websites.forEach((website: any) => {
        summary.websites?.push({
            url: website.url,
            title: website.label,
        });
    });

    return summary;
}


async function test() {
    let connection = new Connection("https://api.mainnet-beta.solana.com", "confirmed");
    let mint = new PublicKey("Hwjdpnxx3eRhgW99Z3AdH1hpRks8NSc7kH8MCAXBV9yd");
    let metadata = await getTokenSummaryMetadata(connection, mint);
    console.log(metadata);
}

// test();