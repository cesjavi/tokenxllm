import { RpcProvider } from "starknet";
import { connect } from "starknetkit";
import { appConfig } from "../config";

let provider;

export function getProvider() {
  if (!provider && appConfig.rpcUrl) {
    provider = new RpcProvider({ nodeUrl: appConfig.rpcUrl });
  }
  return provider;
}

export async function connectWallet(options = {}) {
  return connect({
    modalMode: "neverAsk",
    dappName: "TokenXLLM Dashboard",
    ...options,
  });
}
