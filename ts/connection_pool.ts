import { Connection } from "@solana/web3.js";
import * as web3 from "@solana/web3.js";
import axios, { AxiosInstance } from "axios";
import { HttpsProxyAgent } from "hpagent";


export async function axiosFetchWithRetries(
    axiosObject: AxiosInstance,
    input: string | URL | globalThis.Request,
    init?: RequestInit,
    retryAttempts = 5,
  ): Promise<Response> {
    let attempt = 0;
  
    // Adding default headers
    if (!init || !init.headers) {
      init = {
        headers: {
          "Content-Type": "application/json",
        },
        ...init,
      };
    }
  
    while (attempt < retryAttempts) {
      try {
        let axiosHeaders = {};
  
        axiosHeaders = Array.from(new Headers(init.headers).entries()).reduce(
          (acc: any, [key, value]) => {
            acc[key] = value;
            return acc;
          },
          {}
        );
  
        const axiosConfig = {
          data: init.body,
          headers: axiosHeaders,
          method: init.method,
          baseURL: input.toString(),
          validateStatus: (status: any) => true,
        };
  
        const axiosResponse = await axiosObject.request(axiosConfig);
  
        const { data, status, statusText, headers } = axiosResponse;
  
        // Mapping headers from axios to fetch format
        const headersArray: [string, string][] = Object.entries(headers).map(
          ([key, value]) => [key, value]
        );
  
        const fetchHeaders = new Headers(headersArray);
  
        const response = new Response(JSON.stringify(data), {
          status,
          statusText,
          headers: fetchHeaders,
        });
  
        // Comment the above lines and uncomment the following one to switch from axios to fetch
        // const response = await fetch(input, init);
  
        // Traffic might get routed to backups or node restarts or if anything throws a 502, retry
        if (response.status === 502) {
          console.log("Retrying due to 502");
  
          attempt++;
  
          // Backoff to avoid hammering the server
          await new Promise<void>((resolve) =>
            setTimeout(resolve, 100 * attempt)
          );
  
          continue;
        }
        return Promise.resolve(response);
      } catch (e) {
        // console.log(`Retrying due to error ${e}`, e);
  
        attempt++;
        continue;
      }
    }
  
    return Promise.reject("Max retries reached");
  }
  


export class ConnectionSolanaPool {
    private connection: Connection | null;
    private chainstackConnection: Connection | null;
  
    constructor() {
      this.connection = null;
      this.chainstackConnection = null;
    }  
  
    getChainstackConnection() {
      let c = new Connection(process.env.MOONSHOT_RPC_ENDPOINT as string, "recent");
      this.chainstackConnection = c;
      
      return this.chainstackConnection;
    }
  
    getConnectionWithProxy() {
      let proxyUrl = process.env.PROXY_URL as string;
      let agent = new HttpsProxyAgent({ proxy: proxyUrl});
      let axiosObject = axios.create({
          httpsAgent: agent,
      });
      
      let rpc = web3.clusterApiUrl("mainnet-beta");
      let connection = new web3.Connection(rpc, {
        async fetch(input, init?) {
            // console.log("Fetching: ", input, "init: ", init);
            return await axiosFetchWithRetries(axiosObject, input, init);
        }
      });
  
      return connection;
    }
  }
  