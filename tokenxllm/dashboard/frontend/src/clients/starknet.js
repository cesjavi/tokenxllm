import { appConfig } from "../config.js";

let provider;

let starknetModulesPromise;

function loadStarknetModules() {
  if (!starknetModulesPromise) {
    starknetModulesPromise = (async () => {
      try {
        const [starknet, starknetkit] = await Promise.all([
          import("starknet"),
          import("starknetkit"),
        ]);
        return { RpcProvider: starknet.RpcProvider, connect: starknetkit.connect };
      } catch (error) {
        console.warn(
          "Starknet libraries are unavailable; wallet features are disabled.",
          error,
        );
        return { RpcProvider: null, connect: null };
      }
    })();
  }

  return starknetModulesPromise;
}

function ensureProviderInitialized() {
  if (provider || !appConfig.rpcUrl) {
    return;
  }

  loadStarknetModules().then(({ RpcProvider }) => {
    if (!provider && RpcProvider) {
      provider = new RpcProvider({ nodeUrl: appConfig.rpcUrl });
    }
  });
}

export function getProvider() {
  ensureProviderInitialized();
  return provider;
}

export async function connectWallet(options = {}) {
  const { connect } = await loadStarknetModules();
  if (typeof connect !== "function") {
    throw new Error(
      "Wallet connection is not available in this environment. Include the Starknet libraries to enable it.",
    );
  }

  return connect({
    modalMode: "neverAsk",
    dappName: "TokenXLLM Dashboard",
    ...options,
  });
}
