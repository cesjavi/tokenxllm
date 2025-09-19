import { appConfig } from "./config";
import {
  approve,
  authorize,
  getAllowance,
  getBackendConfig,
  getBalance,
  getEpoch,
  getUsedUnits,
  mint,
} from "./services/backend";
import { connectWallet, getProvider } from "./clients/starknet";

let backendConfig = null;
let writesEnabled = false;

function byId(id) {
  return document.getElementById(id);
}

function setText(id, value) {
  const el = byId(id);
  if (el) {
    el.textContent = value;
  }
}

function readValue(id) {
  const el = byId(id);
  return el ? el.value.trim() : "";
}

function decimalsToStep(decimals) {
  if (!Number.isFinite(decimals) || decimals <= 0) {
    return "1";
  }
  return `0.${"0".repeat(Math.max(0, Math.trunc(decimals) - 1))}1`;
}

function formatJson(data) {
  return JSON.stringify(data, null, 2);
}

function formatBalanceResponse(data) {
  if (!data) {
    return "No balance data";
  }
  return [`wei: ${data.balance_wei}`, `AIC: ${data.balance_AIC}`].join("\n");
}

function formatAllowanceResponse(data) {
  if (!data) {
    return "No allowance data";
  }
  return [`wei: ${data.allowance_wei}`, `AIC: ${data.allowance_AIC}`].join("\n");
}

function formatUsageResponse(used, epoch) {
  if (!used && !epoch) {
    return "No usage data";
  }
  const parts = [];
  if (used) {
    parts.push(`used_units: ${used.used_units}`);
  }
  if (epoch) {
    parts.push(`epoch_id: ${epoch.epoch_id}`);
  }
  return parts.join("\n");
}

function displaySignerAddress(address) {
  setText("signerAddress", address || "Not configured");
}

function applyWriteAvailability(enabled) {
  writesEnabled = Boolean(enabled);
  const buttons = ["btnApprove", "btnAuthorize", "btnMint"]
    .map((id) => byId(id))
    .filter(Boolean);

  buttons.forEach((button) => {
    button.disabled = !writesEnabled;
    if (writesEnabled) {
      button.removeAttribute("title");
    } else {
      button.setAttribute("title", "Backend writes are disabled");
    }
  });

  setText("writesEnabled", writesEnabled ? "Yes" : "No");
}

function applyBackendConfig(config) {
  backendConfig = config ?? null;
  const signerAddress = backendConfig?.account_address || "";
  applyWriteAvailability(Boolean(backendConfig?.writes_enabled));
  displaySignerAddress(signerAddress);
}

async function preloadBackendConfig() {
  try {
    const config = await getBackendConfig();
    applyBackendConfig(config);
  } catch (error) {
    applyBackendConfig(null);
    console.warn("Failed to load backend config", error);
  }
}

function ensureWritesAreEnabled() {
  if (!writesEnabled) {
    alert("Writes are disabled on the backend. Configure signer credentials first.");
    return false;
  }
  return true;
}

function updateEnvironmentSection() {
  setText("backendUrl", appConfig.backendUrl || "Not configured");
  setText("rpcUrl", appConfig.rpcUrl || "Not configured");
  setText("aicAddress", appConfig.aicAddress || "Not configured");
  setText("umAddress", appConfig.umAddress || "Not configured");
  setText("decimals", String(appConfig.decimals));
  applyWriteAvailability(writesEnabled);
  displaySignerAddress(backendConfig?.account_address || "");

  // Instantiate the Starknet provider when the RPC is available so imports are exercised.
  if (appConfig.rpcUrl) {
    getProvider();
  }
}

function exposeStarknetHelpers() {
  if (typeof window === "undefined") {
    return;
  }

  window.tokenxllm = {
    ...(window.tokenxllm ?? {}),
    connectWallet,
    getProvider,
  };
}

function configureFormDefaults() {
  const approveInput = byId("approveAmount");
  const mintInput = byId("mintAmount");
  const authInput = byId("authUnits");

  const step = decimalsToStep(appConfig.decimals);
  if (approveInput) {
    approveInput.step = step;
    if (!approveInput.value) {
      approveInput.value = "100";
    }
  }

  if (mintInput) {
    mintInput.step = step;
    if (!mintInput.value) {
      mintInput.value = "50";
    }
  }

  if (authInput && !authInput.value) {
    authInput.value = "3000";
  }
}

async function handleLoadConfig() {
  try {
    const config = await getBackendConfig();
    applyBackendConfig(config);
    setText(
      "config",
      formatJson({
        env: {
          backendUrl: appConfig.backendUrl,
          rpcUrl: appConfig.rpcUrl,
          aicAddress: appConfig.aicAddress,
          umAddress: appConfig.umAddress,
          decimals: appConfig.decimals,
        },
        backend: config,
      }),
    );
  } catch (error) {
    applyBackendConfig(null);
    setText("config", String(error));
  }
}

async function handleRefresh() {
  const userAddress = readValue("userAddr");
  if (!userAddress) {
    alert("Enter your address");
    return;
  }

  setText("balance", "Loading...");
  setText("allowance", "Loading...");
  setText("usage", "Loading...");

  try {
    const [balance, used, epoch] = await Promise.all([
      getBalance(userAddress),
      getUsedUnits(userAddress),
      getEpoch(),
    ]);

    setText("balance", formatBalanceResponse(balance));
    setText("usage", formatUsageResponse(used, epoch));

    if (appConfig.umAddress) {
      const allowance = await getAllowance(userAddress, appConfig.umAddress);
      setText("allowance", formatAllowanceResponse(allowance));
    } else {
      setText("allowance", "UM address not configured");
    }
  } catch (error) {
    setText("balance", String(error));
    setText("allowance", String(error));
    setText("usage", String(error));
  }
}

async function handleApprove() {
  if (!ensureWritesAreEnabled()) {
    return;
  }
  const value = readValue("approveAmount");
  const amount = Number(value);
  if (!Number.isFinite(amount) || amount <= 0) {
    alert("Enter a valid amount to approve");
    return;
  }

  try {
    const response = await approve(amount);
    setText("txlog", `approve tx: ${response.tx_hash}`);
  } catch (error) {
    setText("txlog", `approve error: ${error}`);
  }
}

async function handleAuthorize() {
  if (!ensureWritesAreEnabled()) {
    return;
  }
  const value = readValue("authUnits");
  const units = Number.parseInt(value, 10);
  if (!Number.isInteger(units) || units <= 0) {
    alert("Enter a valid number of units to authorize");
    return;
  }

  try {
    const response = await authorize(units);
    setText("txlog", `authorize tx: ${response.tx_hash}`);
  } catch (error) {
    setText("txlog", `authorize error: ${error}`);
  }
}

async function handleMint() {
  if (!ensureWritesAreEnabled()) {
    return;
  }
  const to = readValue("mintTo");
  const value = readValue("mintAmount");
  const amount = Number(value);
  if (!to) {
    alert("Enter a destination address to mint");
    return;
  }

  if (!Number.isFinite(amount) || amount <= 0) {
    alert("Enter a valid mint amount");
    return;
  }

  try {
    const response = await mint(to, amount);
    setText("txlog", `mint tx: ${response.tx_hash}`);
  } catch (error) {
    setText("txlog", `mint error: ${error}`);
  }
}

function attachEventHandlers() {
  const configButton = byId("btnConfig");
  const refreshButton = byId("btnRefresh");
  const approveButton = byId("btnApprove");
  const authorizeButton = byId("btnAuthorize");
  const mintButton = byId("btnMint");

  configButton?.addEventListener("click", handleLoadConfig);
  refreshButton?.addEventListener("click", handleRefresh);
  approveButton?.addEventListener("click", handleApprove);
  authorizeButton?.addEventListener("click", handleAuthorize);
  mintButton?.addEventListener("click", handleMint);
}

function init() {
  updateEnvironmentSection();
  configureFormDefaults();
  exposeStarknetHelpers();
  attachEventHandlers();
  preloadBackendConfig();
}

export function initDashboard() {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
}
