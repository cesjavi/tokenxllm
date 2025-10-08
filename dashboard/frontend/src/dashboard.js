import { uint256 } from "starknet";
import { appConfig } from "./config.js";
import {
  approve as approveBackend,
  authorize as authorizeBackend,
  getAllowance,
  getBackendConfig,
  getBalance,
  getEpoch,
  getFreeQuota,
  getFaucetInfo,
  getUsedUnits,
  mint,
  requestFaucet,
} from "./services/backend.js";
import { connectWallet, getProvider } from "./clients/starknet.js";

let backendConfig = null;
let writesEnabled = false;
let activeUserAddress = "";

const tabState = {
  active: "overview",
};

const USAGE_STORAGE_KEY = "tokenxllm.usageAddresses";

const usageStatsState = {
  addresses: [],
  entries: new Map(),
  isLoading: false,
  epochId: null,
  epochUpdatedAt: null,
  epochError: "",
};

const freeQuotaState = {
  total: null,
  remaining: null,
};

const usageState = {
  usedUnits: null,
};

const paidConsumption = {
  units: 0,
  costWei: 0n,
  costKnown: true,
};

let latestPricePerUnitWei = null;

let connectedWallet = null;
let connectedWalletAccount = null;
let connectedWalletAddress = "";

const faucetState = {
  backendEnabled: true,
  writesEnabled: true,
  amountAIC: "50",
  amountWei: "",
  cooldownSeconds: null,
  secondsRemaining: null,
  lastClaimTimestamp: null,
  message: "",
  error: "",
};

function byId(id) {
  return document.getElementById(id);
}

function hasOwn(obj, prop) {
  return Object.prototype.hasOwnProperty.call(obj, prop);
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

function normalizeHexAddress(value) {
  if (value === null || value === undefined) {
    return "";
  }

  if (typeof value === "string") {
    const trimmed = value.trim();
    if (!trimmed) {
      return "";
    }
    if (trimmed.startsWith("0x") || trimmed.startsWith("0X")) {
      return trimmed;
    }
    try {
      return `0x${BigInt(trimmed).toString(16)}`;
    } catch (error) {
      return trimmed;
    }
  }

  if (typeof value === "bigint") {
    return `0x${value.toString(16)}`;
  }

  if (typeof value === "number") {
    if (!Number.isFinite(value)) {
      return "";
    }
    return `0x${value.toString(16)}`;
  }

  if (typeof value === "object" && value !== null && "toString" in value) {
    try {
      return normalizeHexAddress(value.toString());
    } catch (error) {
      return "";
    }
  }

  return "";
}

function getActiveWalletAccount() {
  if (connectedWalletAccount && typeof connectedWalletAccount.execute === "function") {
    return connectedWalletAccount;
  }

  const wallet = connectedWallet;
  if (!wallet) {
    return null;
  }

  if (typeof wallet.execute === "function") {
    return wallet;
  }

  if (wallet.account && typeof wallet.account.execute === "function") {
    connectedWalletAccount = wallet.account;
    return connectedWalletAccount;
  }

  if (wallet.selectedAccount && typeof wallet.selectedAccount.execute === "function") {
    connectedWalletAccount = wallet.selectedAccount;
    return connectedWalletAccount;
  }

  if (Array.isArray(wallet.accounts)) {
    const candidate = wallet.account || wallet.accounts.find((acc) => acc && typeof acc.execute === "function");
    if (candidate && typeof candidate.execute === "function") {
      connectedWalletAccount = candidate;
      return connectedWalletAccount;
    }
  }

  return null;
}

function requireConfiguredAddress(rawValue, label) {
  const normalized = normalizeHexAddress(rawValue);
  if (!normalized) {
    throw new Error(`${label} no está configurado.`);
  }
  return normalized;
}

function setUserAddressValue(address) {
  const input = byId("userAddr");
  if (input) {
    input.value = address;
  }
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

function formatLocalDatetime(value) {
  if (value === null || value === undefined) {
    return "—";
  }
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric <= 0) {
    return "—";
  }
  try {
    const date = new Date(numeric);
    if (Number.isNaN(date.getTime())) {
      return "—";
    }
    return date.toLocaleString();
  } catch (error) {
    return "—";
  }
}

function formatUnits(value) {
  if (value === null || value === undefined) {
    return "N/D";
  }
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return "N/D";
  }
  return numeric.toLocaleString();
}

function parseAmountToWei(value, decimals) {
  if (typeof value !== "string") {
    value = value === undefined || value === null ? "" : String(value);
  }

  const trimmed = value.trim();
  if (!trimmed) {
    throw new Error("Ingresa un monto válido.");
  }

  if (!/^\d+(?:\.\d+)?$/.test(trimmed)) {
    throw new Error("El monto debe ser un número decimal positivo.");
  }

  const [wholePart, decimalPart = ""] = trimmed.split(".");
  if (!/^\d+$/.test(wholePart) || !/^\d*$/.test(decimalPart)) {
    throw new Error("El monto contiene caracteres inválidos.");
  }

  const allowedDecimals = Number.isFinite(decimals) && decimals > 0 ? Math.trunc(decimals) : 0;
  if (decimalPart.length > allowedDecimals) {
    throw new Error(`El monto no puede tener más de ${allowedDecimals} decimales.`);
  }

  const padded = decimalPart.padEnd(Math.max(allowedDecimals, 0), "0");
  const combined = `${wholePart}${padded}`.replace(/^0+(?=\d)/, "");
  return BigInt(combined || "0");
}

function formatTxHash(value) {
  if (value === null || value === undefined) {
    return "";
  }

  if (typeof value === "string") {
    if (value.startsWith("0x") || value.startsWith("0X")) {
      return value;
    }
    try {
      return `0x${BigInt(value).toString(16)}`;
    } catch (error) {
      return value;
    }
  }

  if (typeof value === "bigint") {
    return `0x${value.toString(16)}`;
  }

  if (typeof value === "number" && Number.isFinite(value)) {
    return `0x${value.toString(16)}`;
  }

  return "";
}

function buildWalletTxResponse(result) {
  const hash =
    result?.transaction_hash ??
    result?.transactionHash ??
    result?.hash ??
    result?.transactionHashHex ??
    null;

  const txHash = formatTxHash(hash);
  if (!txHash) {
    return { tx_hash: "" };
  }

  return { tx_hash: txHash };
}

function parseOptionalNumber(value) {
  if (value === null || value === undefined) {
    return null;
  }
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function inferUsedUnits(usedResponse, freeQuotaResponse) {
  if (usedResponse && hasOwn(usedResponse, "used_units")) {
    const direct = parseOptionalNumber(usedResponse.used_units);
    if (direct !== null) {
      return direct;
    }
  }

  if (freeQuotaResponse && hasOwn(freeQuotaResponse, "used_units")) {
    const hinted = parseOptionalNumber(freeQuotaResponse.used_units);
    if (hinted !== null) {
      return hinted;
    }
  }

  if (freeQuotaResponse) {
    const total = hasOwn(freeQuotaResponse, "free_quota")
      ? parseOptionalNumber(freeQuotaResponse.free_quota)
      : null;
    const remaining = hasOwn(freeQuotaResponse, "free_remaining")
      ? parseOptionalNumber(freeQuotaResponse.free_remaining)
      : null;

    if (total !== null && remaining !== null) {
      return Math.max(total - remaining, 0);
    }
  }

  return null;
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

function formatUsageResponse(used, epoch, freeQuota) {
  if (!used && !epoch && !freeQuota) {
    return "No usage data";
  }
  const parts = [];
  if (used && typeof used.used_units !== "undefined") {
    parts.push(`used_units: ${used.used_units}`);
  }
  if (epoch) {
    parts.push(`epoch_id: ${epoch.epoch_id}`);
  }
  if (freeQuota) {
    if (typeof freeQuota.free_quota !== "undefined") {
      parts.push(`free_quota: ${freeQuota.free_quota}`);
    }
    if (typeof freeQuota.free_remaining !== "undefined") {
      parts.push(`free_remaining: ${freeQuota.free_remaining}`);
    }
  }
  return parts.join("\n");
}

function formatWeiAmount(wei) {
  if (wei === null || wei === undefined) {
    return "0";
  }
  try {
    const decimalsValue = Number(appConfig.decimals);
    const decimals = Number.isFinite(decimalsValue) ? Math.max(Math.trunc(decimalsValue), 0) : 0;
    const base = 10n ** BigInt(decimals);
    const weiBig = BigInt(wei);
    const negative = weiBig < 0n;
    const absWei = negative ? -weiBig : weiBig;
    if (decimals === 0) {
      return `${negative ? "-" : ""}${absWei.toString()}`;
    }
    const intPart = absWei / base;
    let frac = (absWei % base).toString().padStart(decimals, "0");
    frac = frac.replace(/0+$/, "");
    const body = frac ? `${intPart}.${frac}` : intPart.toString();
    return negative ? `-${body}` : body;
  } catch (error) {
    return String(wei);
  }
}

function formatDuration(seconds) {
  if (!Number.isFinite(seconds)) {
    return "N/D";
  }
  const totalSeconds = Math.max(0, Math.round(seconds));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const secs = totalSeconds % 60;
  const parts = [];
  if (hours) {
    parts.push(`${hours}h`);
  }
  if (minutes) {
    parts.push(`${minutes}m`);
  }
  if (parts.length === 0 || secs) {
    parts.push(`${secs}s`);
  }
  return parts.join(" ");
}

function formatTimestamp(ts) {
  if (!Number.isFinite(ts) || ts <= 0) {
    return "Sin datos";
  }
  try {
    const date = new Date(Number(ts) * 1000);
    if (Number.isNaN(date.getTime())) {
      return "Sin datos";
    }
    return date.toLocaleString();
  } catch (error) {
    return "Sin datos";
  }
}

function updateFreeQuotaDisplay() {
  const element = byId("freeQuotaInfo");
  if (!element) {
    return;
  }

  if (freeQuotaState.total === null) {
    element.textContent = "Sin datos";
    return;
  }

  if (freeQuotaState.remaining === null || !activeUserAddress) {
    element.textContent = `${freeQuotaState.total} unidades`;
    return;
  }

  element.textContent = `${freeQuotaState.remaining} / ${freeQuotaState.total} unidades`;
}

function updatePaidUsageDisplay() {
  const element = byId("paidUsageInfo");
  if (!element) {
    return;
  }

  const unitsText = paidConsumption.units;
  let costText;

  if (!unitsText) {
    costText = latestPricePerUnitWei !== null ? "0 AIC" : "N/D";
  } else if (paidConsumption.costKnown) {
    costText = `${formatWeiAmount(paidConsumption.costWei)} AIC`;
  } else {
    costText = "N/D";
  }

  element.textContent = `${unitsText} / ${costText}`;
}

function faucetIsUsable() {
  const cooldownActive = faucetState.secondsRemaining !== null && faucetState.secondsRemaining > 0;
  return writesEnabled && faucetState.backendEnabled && faucetState.writesEnabled && !cooldownActive;
}

function setFaucetMessage(message) {
  faucetState.message = message || "";
  faucetState.error = "";
  updateFaucetDisplay();
}

function setFaucetError(message) {
  faucetState.error = message || "";
  updateFaucetDisplay();
}

function applyFaucetInfo(info) {
  if (!info || typeof info !== "object") {
    return;
  }

  if (hasOwn(info, "enabled")) {
    faucetState.backendEnabled = Boolean(info.enabled);
  }
  if (hasOwn(info, "writes_enabled")) {
    faucetState.writesEnabled = Boolean(info.writes_enabled);
  }
  if (hasOwn(info, "amount_AIC") && info.amount_AIC !== undefined && info.amount_AIC !== null) {
    faucetState.amountAIC = String(info.amount_AIC);
  }
  if (hasOwn(info, "amount_wei") && info.amount_wei !== undefined && info.amount_wei !== null) {
    faucetState.amountWei = String(info.amount_wei);
  }
  if (hasOwn(info, "cooldown_seconds")) {
    const raw = Number(info.cooldown_seconds);
    faucetState.cooldownSeconds = Number.isFinite(raw) ? Math.max(0, Math.trunc(raw)) : null;
  }
  if (hasOwn(info, "seconds_remaining")) {
    const value = info.seconds_remaining;
    if (value === null || value === undefined) {
      faucetState.secondsRemaining = null;
    } else {
      const parsed = Number(value);
      faucetState.secondsRemaining = Number.isFinite(parsed) ? Math.max(0, Math.trunc(parsed)) : null;
    }
  }
  if (hasOwn(info, "last_claim_timestamp")) {
    const value = info.last_claim_timestamp;
    if (value === null || value === undefined) {
      faucetState.lastClaimTimestamp = null;
    } else {
      const parsed = Number(value);
      faucetState.lastClaimTimestamp = Number.isFinite(parsed) && parsed > 0 ? parsed : null;
    }
  }

  updateFaucetDisplay();
}

function updateFaucetDisplay() {
  const statusElement = byId("faucetEnabled");
  if (statusElement) {
    let statusText;
    if (!faucetState.backendEnabled) {
      statusText = "Deshabilitado" + (faucetState.backendEnabled === false ? " en backend" : "");
    } else if (!writesEnabled) {
      statusText = "Sin credenciales";
    } else if (!faucetState.writesEnabled) {
      statusText = "Falta configurar";
    } else {
      statusText = faucetState.secondsRemaining && faucetState.secondsRemaining > 0 ? "En cooldown" : "Disponible";
    }
    statusElement.textContent = statusText;
  }

  const amountText = faucetState.amountAIC ? `${faucetState.amountAIC} AIC` : "N/D";
  setText("faucetAmount", amountText);

  const cooldownText = faucetState.cooldownSeconds === null ? "N/D" : formatDuration(faucetState.cooldownSeconds);
  setText("faucetCooldown", cooldownText);

  let remainingText;
  if (faucetState.secondsRemaining === null) {
    remainingText = faucetState.backendEnabled ? "Desconocido" : "N/D";
  } else if (faucetState.secondsRemaining <= 0) {
    remainingText = "Disponible";
  } else {
    remainingText = formatDuration(faucetState.secondsRemaining);
  }
  setText("faucetRemaining", remainingText);

  setText("faucetLastClaim", formatTimestamp(faucetState.lastClaimTimestamp));

  const statusLog = byId("faucetStatus");
  if (statusLog) {
    const message = faucetState.error ? `Error: ${faucetState.error}` : faucetState.message;
    statusLog.textContent = message || "";
  }

  const button = byId("btnFaucet");
  if (button) {
    const cooldownActive = faucetState.secondsRemaining !== null && faucetState.secondsRemaining > 0;
    const usable = faucetIsUsable();
    button.disabled = !usable;

    if (!writesEnabled) {
      button.setAttribute("title", "Backend writes are disabled");
    } else if (!faucetState.backendEnabled) {
      button.setAttribute("title", "El faucet está deshabilitado en el backend");
    } else if (!faucetState.writesEnabled) {
      button.setAttribute("title", "Configura las credenciales del faucet en el backend");
    } else if (cooldownActive) {
      button.setAttribute("title", "Debes esperar al cooldown del faucet");
    } else {
      button.removeAttribute("title");
    }
  }
}

async function refreshFaucetState(address) {
  const target = (address ?? readValue("faucetAddress") ?? activeUserAddress ?? "").trim();

  try {
    const info = await getFaucetInfo(target || undefined);
    if (faucetState.error) {
      faucetState.error = "";
    }
    applyFaucetInfo(info);
    return info;
  } catch (error) {
    const message = error?.message || String(error);
    setFaucetError(message);
    return null;
  }
}

function resetPaidTracking() {
  paidConsumption.units = 0;
  paidConsumption.costWei = 0n;
  paidConsumption.costKnown = true;
  updatePaidUsageDisplay();
}

function setActiveUserAddress(address) {
  const previous = activeUserAddress;
  const normalized = (address || "").trim();
  if (normalized === activeUserAddress) {
    return;
  }

  activeUserAddress = normalized;
  usageState.usedUnits = null;
  freeQuotaState.remaining = null;
  resetPaidTracking();
  updateFreeQuotaDisplay();

  const faucetInput = byId("faucetAddress");
  if (faucetInput && (!faucetInput.value || faucetInput.value.trim() === previous)) {
    faucetInput.value = normalized;
  }
}

function applyFreeQuotaResponse(freeQuota, used) {
  if (freeQuota && freeQuota.free_quota !== undefined) {
    const total = Number(freeQuota.free_quota);
    freeQuotaState.total = Number.isFinite(total) ? total : null;
  }

  if (freeQuota && freeQuota.free_remaining !== undefined) {
    const remaining = Number(freeQuota.free_remaining);
    freeQuotaState.remaining = Number.isFinite(remaining) ? remaining : null;
  } else if (activeUserAddress && freeQuotaState.total !== null && usageState.usedUnits !== null) {
    const remaining = Math.max(freeQuotaState.total - usageState.usedUnits, 0);
    freeQuotaState.remaining = Number.isFinite(remaining) ? remaining : null;
  }

  if (freeQuota && freeQuota.used_units !== undefined) {
    const usedUnits = Number(freeQuota.used_units);
    usageState.usedUnits = Number.isFinite(usedUnits) ? usedUnits : usageState.usedUnits;
  }

  if (used && used.used_units !== undefined) {
    const usedUnits = Number(used.used_units);
    usageState.usedUnits = Number.isFinite(usedUnits) ? usedUnits : usageState.usedUnits;
  }

  if (freeQuota && freeQuota.price_per_unit_wei !== undefined) {
    try {
      latestPricePerUnitWei = BigInt(freeQuota.price_per_unit_wei);
    } catch (error) {
      latestPricePerUnitWei = null;
    }
  }

  updateFreeQuotaDisplay();
  updatePaidUsageDisplay();
}

async function fetchFreeQuotaSnapshot(userAddress) {
  const [used, freeQuota] = await Promise.all([
    getUsedUnits(userAddress),
    getFreeQuota(userAddress),
  ]);
  applyFreeQuotaResponse(freeQuota, used);
  return { used, freeQuota };
}

function displaySignerAddress(address) {
  setText("signerAddress", address || "Not configured");
}

function setButtonState(buttonId, enabled, disabledMessage) {
  const button = byId(buttonId);
  if (!button) {
    return;
  }

  button.disabled = !enabled;
  if (!enabled && disabledMessage) {
    button.setAttribute("title", disabledMessage);
  } else {
    button.removeAttribute("title");
  }
}

function updateActionButtonsState() {
  const walletReady = Boolean(getActiveWalletAccount());
  const backendReady = Boolean(writesEnabled);
  const usageEnabled = walletReady || backendReady;

  const usageDisabledMessage = usageEnabled
    ? ""
    : "Conecta una billetera o configura credenciales en el backend.";

  setButtonState("btnSpendFree", usageEnabled, usageDisabledMessage);
  setButtonState("btnAuthorize", usageEnabled, usageDisabledMessage);
  setButtonState("btnApprove", usageEnabled, usageDisabledMessage);

  const mintDisabledMessage = "Backend writes are disabled";
  setButtonState("btnMint", backendReady, mintDisabledMessage);
}

function applyWriteAvailability(enabled) {
  writesEnabled = Boolean(enabled);
  setText("writesEnabled", writesEnabled ? "Yes" : "No");
  updateActionButtonsState();
  updateFaucetDisplay();
}

function applyBackendConfig(config) {
  backendConfig = config ?? null;
  const signerAddress = backendConfig?.account_address || "";
  applyWriteAvailability(Boolean(backendConfig?.writes_enabled));
  if (backendConfig?.faucet) {
    applyFaucetInfo(backendConfig.faucet);
  }
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

  try {
    await refreshFaucetState();
  } catch (error) {
    console.warn("Failed to refresh faucet info", error);
  }
}

function ensureBackendWritesEnabled() {
  if (!writesEnabled) {
    alert("Las escrituras en el backend están deshabilitadas. Configura las credenciales primero.");
    return false;
  }
  return true;
}

function ensureUsageSigner() {
  if (getActiveWalletAccount()) {
    return "wallet";
  }
  if (writesEnabled) {
    return "backend";
  }
  alert("Conecta una billetera o configura credenciales de backend para enviar transacciones.");
  return null;
}

async function approveWithWallet(amountInput, spenderOverride) {
  const account = getActiveWalletAccount();
  if (!account) {
    throw new Error("Conecta una billetera compatible para firmar transacciones.");
  }

  const tokenAddress = requireConfiguredAddress(appConfig.aicAddress, "La dirección del token AIC");
  const spenderAddress = requireConfiguredAddress(
    spenderOverride || appConfig.umAddress,
    "La dirección del UsageManager",
  );

  const decimals = Number.isFinite(appConfig.decimals) ? Number(appConfig.decimals) : 18;
  const amountWei = parseAmountToWei(amountInput, decimals);
  if (amountWei <= 0n) {
    throw new Error("El monto debe ser mayor a cero.");
  }

  const amountU256 = uint256.bnToUint256(amountWei);
  const call = {
    contractAddress: tokenAddress,
    entrypoint: "approve",
    calldata: [
      spenderAddress,
      amountU256.low.toString(),
      amountU256.high.toString(),
    ],
  };

  const result = await account.execute(call);
  return buildWalletTxResponse(result);
}

async function authorizeWithWallet(units) {
  const account = getActiveWalletAccount();
  if (!account) {
    throw new Error("Conecta una billetera compatible para firmar transacciones.");
  }

  const umAddress = requireConfiguredAddress(appConfig.umAddress, "La dirección del UsageManager");
  const callBase = {
    contractAddress: umAddress,
    entrypoint: "authorize_usage",
  };

  try {
    const result = await account.execute({ ...callBase, calldata: [units.toString()] });
    return buildWalletTxResponse(result);
  } catch (error) {
    const message = (error?.message || String(error)).toLowerCase();
    if (
      message.includes("entrypoint") ||
      message.includes("calldata") ||
      message.includes("invalid")
    ) {
      const encoded = uint256.bnToUint256(BigInt(units.toString()));
      const fallbackCall = {
        ...callBase,
        calldata: [encoded.low.toString(), encoded.high.toString()],
      };
      const fallbackResult = await account.execute(fallbackCall);
      return buildWalletTxResponse(fallbackResult);
    }
    throw error;
  }
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
  const freeSpendInput = byId("freeSpendUnits");

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

  if (freeSpendInput) {
    freeSpendInput.step = "1";
    if (!freeSpendInput.value) {
      freeSpendInput.value = "100";
    }
  }
}

function switchTab(targetKey) {
  if (!targetKey) {
    return;
  }

  tabState.active = targetKey;
  const buttons = document.querySelectorAll("[data-tab-target]");
  buttons.forEach((button) => {
    const tab = button.getAttribute("data-tab-target");
    if (tab === targetKey) {
      button.classList.add("is-active");
      button.setAttribute("aria-selected", "true");
      button.removeAttribute("tabindex");
    } else {
      button.classList.remove("is-active");
      button.setAttribute("aria-selected", "false");
      button.setAttribute("tabindex", "-1");
    }
  });

  const panels = document.querySelectorAll("[data-tab-panel]");
  panels.forEach((panel) => {
    const tab = panel.getAttribute("data-tab-panel");
    if (tab === targetKey) {
      panel.classList.add("is-active");
      panel.removeAttribute("hidden");
    } else {
      panel.classList.remove("is-active");
      panel.setAttribute("hidden", "true");
    }
  });
}

function initTabs() {
  const buttons = document.querySelectorAll("[data-tab-target]");
  buttons.forEach((button) => {
    button.addEventListener("click", () => {
      const target = button.getAttribute("data-tab-target");
      if (target) {
        switchTab(target);
      }
    });
  });
  switchTab(tabState.active);
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

  setActiveUserAddress(userAddress);
  setText("balance", "Loading...");
  setText("allowance", "Loading...");
  setText("usage", "Loading...");
  setText("freeQuotaInfo", "Actualizando...");

  try {
    const [balance, used, epoch, freeQuota] = await Promise.all([
      getBalance(userAddress),
      getUsedUnits(userAddress),
      getEpoch(),
      getFreeQuota(userAddress),
    ]);

    applyFreeQuotaResponse(freeQuota, used);
    setText("balance", formatBalanceResponse(balance));
    setText("usage", formatUsageResponse(used, epoch, freeQuota));
    await refreshFaucetState(userAddress);

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
    freeQuotaState.total = null;
    freeQuotaState.remaining = null;
    setText("freeQuotaInfo", String(error));
    setFaucetError(String(error));
  }
}

async function handleConnectWallet() {
  try {
    const connection = await connectWallet();
    const address =
      connection?.wallet?.account?.address ??
      connection?.wallet?.selectedAccountAddress ??
      connection?.account?.address ??
      connection?.selectedAccountAddress ??
      connection?.selectedAddress ??
      connection?.address;

    const normalized = normalizeHexAddress(address);
    if (!normalized) {
      alert("No se pudo obtener la dirección de la billetera conectada.");
      return;
    }

    connectedWallet = connection?.wallet || null;
    connectedWalletAccount =
      connection?.account ||
      connection?.wallet?.account ||
      connection?.wallet?.selectedAccount ||
      null;
    connectedWalletAddress = normalized;
    updateActionButtonsState();

    setUserAddressValue(normalized);
    setActiveUserAddress(normalized);
    await handleRefresh();
  } catch (error) {
    console.warn("Failed to connect wallet", error);
    const message = error?.message || String(error);
    alert(`No se pudo conectar la billetera: ${message}`);
  }
}

async function handleApprove() {
  const signer = ensureUsageSigner();
  if (!signer) {
    return;
  }

  const value = readValue("approveAmount");
  if (!value) {
    alert("Ingresa un monto para aprobar.");
    return;
  }

  try {
    let response;
    if (signer === "wallet") {
      response = await approveWithWallet(value);
    } else {
      const amount = Number(value);
      if (!Number.isFinite(amount) || amount <= 0) {
        alert("Enter a valid amount to approve");
        return;
      }
      response = await approveBackend(amount);
    }

    setText("txlog", `approve tx: ${response.tx_hash}`);
    await handleRefresh();
  } catch (error) {
    setText("txlog", `approve error: ${error}`);
  }
}

async function handleSpendFree() {
  const signer = ensureUsageSigner();
  if (!signer) {
    return;
  }

  const userAddress = readValue("userAddr");
  if (!userAddress) {
    alert("Conecta tu billetera o ingresa una dirección antes de gastar.");
    return;
  }

  const unitsValue = readValue("freeSpendUnits");
  const units = Number.parseInt(unitsValue, 10);
  if (!Number.isInteger(units) || units <= 0) {
    alert("Ingresa una cantidad de unidades válida para gastar.");
    return;
  }

  setActiveUserAddress(userAddress);

  if (signer === "wallet" && connectedWalletAddress) {
    const normalizedUser = normalizeHexAddress(userAddress).toLowerCase();
    const normalizedWallet = connectedWalletAddress.toLowerCase();
    if (normalizedUser && normalizedUser !== normalizedWallet) {
      const proceed = window.confirm(
        `Vas a firmar con ${connectedWalletAddress}, pero el campo de usuario contiene ${normalizedUser}. ¿Continuar igualmente?`,
      );
      if (!proceed) {
        return;
      }
    }
  }

  let remaining = freeQuotaState.remaining;
  let total = freeQuotaState.total;

  try {
    setText("freeQuotaInfo", "Actualizando...");
    const snapshot = await fetchFreeQuotaSnapshot(userAddress);
    remaining = freeQuotaState.remaining;
    total = freeQuotaState.total;
    setText("usage", formatUsageResponse(snapshot.used, null, snapshot.freeQuota));
  } catch (error) {
    const message = error?.message || String(error);
    freeQuotaState.total = null;
    freeQuotaState.remaining = null;
    setText("freeQuotaInfo", message);
    alert(`No se pudo actualizar la cuota gratuita: ${message}`);
    return;
  }

  const safeRemaining = Number.isFinite(remaining) ? remaining : 0;
  const safeTotal = Number.isFinite(total) ? total : 0;
  const paidUnits = Math.max(units - safeRemaining, 0);

  let estimatedCostWei = null;
  if (paidUnits > 0 && latestPricePerUnitWei !== null) {
    estimatedCostWei = latestPricePerUnitWei * BigInt(paidUnits);
  }

  if (paidUnits > 0) {
    const costText =
      estimatedCostWei !== null
        ? `${formatWeiAmount(estimatedCostWei)} AIC`
        : "sin datos de costo";
    const confirmMessage = [
      `La cuota gratuita restante es de ${safeRemaining} unidades (de ${safeTotal}).`,
      `Vas a gastar ${units} unidades, de las cuales ${paidUnits} serían pagadas${
        estimatedCostWei !== null ? ` (~${costText}).` : "."
      }`,
      "¿Deseas continuar?",
    ].join("\n");

    if (!window.confirm(confirmMessage)) {
      return;
    }
  }

  try {
    const response =
      signer === "wallet" ? await authorizeWithWallet(units) : await authorizeBackend(units);
    setText("txlog", `gasto gratis tx: ${response.tx_hash}`);

    if (paidUnits > 0) {
      paidConsumption.units += paidUnits;
      if (estimatedCostWei !== null) {
        paidConsumption.costWei += estimatedCostWei;
      } else {
        paidConsumption.costKnown = false;
      }
      updatePaidUsageDisplay();
    }

    await handleRefresh();
  } catch (error) {
    setText("txlog", `gasto gratis error: ${error}`);
  }
}

async function handleAuthorize() {
  const signer = ensureUsageSigner();
  if (!signer) {
    return;
  }
  const userAddress = readValue("userAddr");
  const value = readValue("authUnits");
  const units = Number.parseInt(value, 10);
  if (!Number.isInteger(units) || units <= 0) {
    alert("Enter a valid number of units to authorize");
    return;
  }

  if (signer === "wallet" && connectedWalletAddress && userAddress) {
    const normalizedUser = normalizeHexAddress(userAddress).toLowerCase();
    const normalizedWallet = connectedWalletAddress.toLowerCase();
    if (normalizedUser && normalizedUser !== normalizedWallet) {
      const proceed = window.confirm(
        `Vas a firmar con ${connectedWalletAddress}, pero el campo de usuario contiene ${normalizedUser}. ¿Continuar igualmente?`,
      );
      if (!proceed) {
        return;
      }
    }
  }

  try {
    const response =
      signer === "wallet" ? await authorizeWithWallet(units) : await authorizeBackend(units);
    setText("txlog", `authorize tx: ${response.tx_hash}`);
  } catch (error) {
    setText("txlog", `authorize error: ${error}`);
  }
}

async function handleMint() {
  if (!ensureBackendWritesEnabled()) {
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

async function handleRequestFaucet() {
  if (!ensureBackendWritesEnabled()) {
    return;
  }

  const addressInput = readValue("faucetAddress") || readValue("userAddr");
  const address = addressInput.trim();

  if (!address) {
    alert("Ingresá una dirección para reclamar el faucet.");
    return;
  }

  setFaucetMessage("Solicitando faucet...");

  try {
    const response = await requestFaucet(address);
    setFaucetMessage(`Faucet tx: ${response.tx_hash}`);
    await refreshFaucetState(address);
  } catch (error) {
    let message = error?.message || String(error);
    try {
      const parsed = JSON.parse(message);
      const detail = parsed?.detail;
      if (detail) {
        if (typeof detail === "string") {
          message = detail;
        } else if (detail.error) {
          const seconds = Number(detail.seconds_remaining);
          const extra = Number.isFinite(seconds) ? ` (${formatDuration(seconds)} restantes)` : "";
          message = `${detail.error}${extra}`;
        } else {
          message = JSON.stringify(detail);
        }
      }
    } catch (parseError) {
      // ignore malformed JSON
    }

    setFaucetError(message);
    await refreshFaucetState(address);
  }
}

function saveUsageAddresses() {
  if (typeof window === "undefined" || !window.localStorage) {
    return;
  }
  try {
    const payload = usageStatsState.addresses.map((address) => {
      const entry = usageStatsState.entries.get(address);
      return {
        address,
        label: entry?.label ?? "",
      };
    });
    window.localStorage.setItem(USAGE_STORAGE_KEY, JSON.stringify(payload));
  } catch (error) {
    console.warn("Failed to persist usage addresses", error);
  }
}

function addUsageAddress(address, label = "", options) {
  const opts = options ?? {};
  const normalized = normalizeHexAddress(address);
  if (!normalized) {
    return { added: false, normalized: "" };
  }

  const trimmedLabel = (label || "").trim();
  let added = false;
  let entry = usageStatsState.entries.get(normalized);
  if (!entry) {
    entry = {
      address: normalized,
      label: trimmedLabel,
      usedUnits: null,
      freeQuota: null,
      freeRemaining: null,
      paidUnits: null,
      lastUpdated: null,
      error: "",
      loading: false,
    };
    usageStatsState.entries.set(normalized, entry);
    usageStatsState.addresses.push(normalized);
    added = true;
  } else if (trimmedLabel && entry.label !== trimmedLabel) {
    entry.label = trimmedLabel;
  }

  if (!opts.silent) {
    saveUsageAddresses();
    renderUsageStatsTable();
  }

  return { added, normalized };
}

function removeUsageAddress(address) {
  const normalized = normalizeHexAddress(address);
  if (!normalized) {
    return;
  }
  const index = usageStatsState.addresses.indexOf(normalized);
  if (index === -1) {
    return;
  }
  usageStatsState.addresses.splice(index, 1);
  usageStatsState.entries.delete(normalized);
  saveUsageAddresses();
  renderUsageStatsTable();
}

function clearUsageAddressesState() {
  usageStatsState.addresses = [];
  usageStatsState.entries.clear();
  saveUsageAddresses();
  renderUsageStatsTable();
}

function loadUsageAddresses() {
  if (typeof window === "undefined" || !window.localStorage) {
    return;
  }
  try {
    const raw = window.localStorage.getItem(USAGE_STORAGE_KEY);
    if (!raw) {
      return;
    }
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      return;
    }
    parsed.forEach((item) => {
      if (!item || typeof item !== "object") {
        return;
      }
      const address = normalizeHexAddress(item.address);
      if (!address) {
        return;
      }
      const label = typeof item.label === "string" ? item.label : "";
      addUsageAddress(address, label, { silent: true });
    });
  } catch (error) {
    console.warn("Failed to load saved usage addresses", error);
  }
  renderUsageStatsTable();
}

function updateUsageEpochDisplay() {
  const element = byId("usageEpochInfo");
  if (!element) {
    return;
  }

  element.classList.remove("error");

  if (usageStatsState.epochId !== null) {
    const timestamp = usageStatsState.epochUpdatedAt
      ? ` (actualizado ${formatLocalDatetime(usageStatsState.epochUpdatedAt)})`
      : "";
    element.textContent = `Época actual: ${usageStatsState.epochId}${timestamp}`;
    return;
  }

  if (usageStatsState.epochError) {
    element.textContent = `No se pudo obtener la época actual: ${usageStatsState.epochError}`;
    element.classList.add("error");
    return;
  }

  element.textContent = "Época actual: sin datos";
}

function renderUsageStatsTable() {
  const tbody = byId("usageStatsBody");
  if (!tbody) {
    return;
  }

  if (!usageStatsState.addresses.length) {
    const emptyRow = document.createElement("tr");
    emptyRow.className = "usage-empty";
    const cell = document.createElement("td");
    cell.colSpan = 9;
    cell.textContent = "Agregá una dirección para comenzar a monitorear el uso.";
    emptyRow.appendChild(cell);
    tbody.replaceChildren(emptyRow);
    return;
  }

  const fragment = document.createDocumentFragment();
  usageStatsState.addresses.forEach((address) => {
    const entry = usageStatsState.entries.get(address) ?? {
      address,
      label: "",
      usedUnits: null,
      freeQuota: null,
      freeRemaining: null,
      paidUnits: null,
      lastUpdated: null,
      error: "",
      loading: false,
    };

    const row = document.createElement("tr");

    const aliasCell = document.createElement("td");
    aliasCell.textContent = entry.label || "—";
    row.appendChild(aliasCell);

    const addressCell = document.createElement("td");
    const addressCode = document.createElement("code");
    addressCode.textContent = address;
    addressCell.appendChild(addressCode);
    row.appendChild(addressCell);

    const usedCell = document.createElement("td");
    usedCell.className = "numeric";
    usedCell.textContent = formatUnits(entry.usedUnits);
    row.appendChild(usedCell);

    const remainingCell = document.createElement("td");
    remainingCell.className = "numeric";
    remainingCell.textContent = formatUnits(entry.freeRemaining);
    row.appendChild(remainingCell);

    const quotaCell = document.createElement("td");
    quotaCell.className = "numeric";
    quotaCell.textContent = formatUnits(entry.freeQuota);
    row.appendChild(quotaCell);

    const paidCell = document.createElement("td");
    paidCell.className = "numeric";
    paidCell.textContent = formatUnits(entry.paidUnits);
    row.appendChild(paidCell);

    const updatedCell = document.createElement("td");
    updatedCell.textContent = entry.lastUpdated ? formatLocalDatetime(entry.lastUpdated) : "—";
    row.appendChild(updatedCell);

    const statusCell = document.createElement("td");
    const status = document.createElement("span");
    status.classList.add("usage-status");
    if (entry.loading) {
      status.classList.add("usage-status-loading");
      status.textContent = "Actualizando…";
    } else if (entry.error) {
      status.classList.add("usage-status-error");
      status.textContent = entry.error;
    } else if (entry.lastUpdated) {
      status.classList.add("usage-status-ok");
      status.textContent = "Actualizado";
    } else {
      status.classList.add("usage-status-muted");
      status.textContent = "Sin datos";
    }
    statusCell.appendChild(status);
    row.appendChild(statusCell);

    const actionsCell = document.createElement("td");
    const removeButton = document.createElement("button");
    removeButton.type = "button";
    removeButton.className = "link-button usage-remove";
    removeButton.dataset.action = "remove-usage";
    removeButton.dataset.address = address;
    removeButton.textContent = "Quitar";
    actionsCell.appendChild(removeButton);
    row.appendChild(actionsCell);

    fragment.appendChild(row);
  });

  tbody.replaceChildren(fragment);
}

async function refreshUsageStats() {
  if (!usageStatsState.addresses.length) {
    alert("Agregá al menos una dirección para actualizar las estadísticas.");
    return;
  }

  usageStatsState.isLoading = true;
  usageStatsState.epochError = "";
  usageStatsState.addresses.forEach((address) => {
    const entry = usageStatsState.entries.get(address);
    if (entry) {
      entry.loading = true;
    }
  });
  renderUsageStatsTable();

  try {
    const epoch = await getEpoch();
    const epochId = epoch && hasOwn(epoch, "epoch_id") ? parseOptionalNumber(epoch.epoch_id) : null;
    usageStatsState.epochId = epochId;
    usageStatsState.epochUpdatedAt = Date.now();
    usageStatsState.epochError = epochId === null ? "" : usageStatsState.epochError;
  } catch (error) {
    usageStatsState.epochId = null;
    usageStatsState.epochUpdatedAt = Date.now();
    usageStatsState.epochError = error?.message || String(error);
  }

  updateUsageEpochDisplay();

  await Promise.all(
    usageStatsState.addresses.map(async (address) => {
      const entry = usageStatsState.entries.get(address);
      if (!entry) {
        return;
      }
      try {
        const [used, freeQuota] = await Promise.all([getUsedUnits(address), getFreeQuota(address)]);
        const usedUnits = inferUsedUnits(used, freeQuota);
        const freeQuotaTotal = freeQuota && hasOwn(freeQuota, "free_quota")
          ? parseOptionalNumber(freeQuota.free_quota)
          : null;
        const freeRemaining = freeQuota && hasOwn(freeQuota, "free_remaining")
          ? parseOptionalNumber(freeQuota.free_remaining)
          : null;

        let paidUnits = null;
        if (usedUnits !== null && freeQuotaTotal !== null) {
          paidUnits = Math.max(usedUnits - freeQuotaTotal, 0);
        }

        entry.usedUnits = usedUnits;
        entry.freeQuota = freeQuotaTotal;
        entry.freeRemaining = freeRemaining;
        entry.paidUnits = paidUnits;
        entry.error = "";
        entry.lastUpdated = Date.now();
      } catch (error) {
        entry.usedUnits = null;
        entry.freeQuota = null;
        entry.freeRemaining = null;
        entry.paidUnits = null;
        entry.error = error?.message || String(error);
        entry.lastUpdated = Date.now();
      } finally {
        entry.loading = false;
      }
    }),
  );

  usageStatsState.isLoading = false;
  updateUsageEpochDisplay();
  renderUsageStatsTable();
}

function handleAddUsageAddress() {
  const addressInput = byId("usageAddressInput");
  const labelInput = byId("usageAddressLabel");
  if (!addressInput) {
    return;
  }

  const { value } = addressInput;
  const label = labelInput ? labelInput.value : "";
  if (!value || !value.trim()) {
    alert("Ingresá una dirección para agregarla al monitoreo.");
    return;
  }

  const { added, normalized } = addUsageAddress(value, label);
  if (!normalized) {
    alert("La dirección ingresada no es válida.");
    return;
  }

  if (labelInput) {
    labelInput.value = "";
  }

  addressInput.value = "";
  if (!added) {
    alert("La dirección ya estaba en la lista. Actualizamos el alias si correspondía.");
  }
}

function handleRefreshUsageStats() {
  void refreshUsageStats();
}

function handleClearUsageStats() {
  if (!usageStatsState.addresses.length) {
    return;
  }
  if (window.confirm("¿Querés quitar todas las direcciones monitoreadas?")) {
    clearUsageAddressesState();
    updateUsageEpochDisplay();
  }
}

function handleUsageTableClick(event) {
  const target = event.target;
  if (!(target instanceof HTMLElement)) {
    return;
  }
  const button = target.closest("[data-action=\"remove-usage\"]");
  if (!button) {
    return;
  }
  const address = button.getAttribute("data-address");
  if (address) {
    removeUsageAddress(address);
  }
}

function handleUsageInputKey(event) {
  if (event.key === "Enter") {
    event.preventDefault();
    handleAddUsageAddress();
  }
}

function attachEventHandlers() {
  const configButton = byId("btnConfig");
  const refreshButton = byId("btnRefresh");
  const approveButton = byId("btnApprove");
  const authorizeButton = byId("btnAuthorize");
  const mintButton = byId("btnMint");
  const connectButton = byId("btnConnectWallet");
  const spendButton = byId("btnSpendFree");
  const userInput = byId("userAddr");
  const faucetButton = byId("btnFaucet");
  const faucetInput = byId("faucetAddress");
  const usageAddButton = byId("btnAddUsageAddress");
  const usageRefreshButton = byId("btnRefreshUsageStats");
  const usageClearButton = byId("btnClearUsageStats");
  const usageAddressInput = byId("usageAddressInput");
  const usageLabelInput = byId("usageAddressLabel");
  const usageTableBody = byId("usageStatsBody");

  configButton?.addEventListener("click", handleLoadConfig);
  refreshButton?.addEventListener("click", handleRefresh);
  connectButton?.addEventListener("click", handleConnectWallet);
  spendButton?.addEventListener("click", handleSpendFree);
  approveButton?.addEventListener("click", handleApprove);
  authorizeButton?.addEventListener("click", handleAuthorize);
  mintButton?.addEventListener("click", handleMint);
  faucetButton?.addEventListener("click", handleRequestFaucet);
  userInput?.addEventListener("change", () => {
    setActiveUserAddress(readValue("userAddr"));
  });
  faucetInput?.addEventListener("change", () => {
    void refreshFaucetState(readValue("faucetAddress"));
  });
  usageAddButton?.addEventListener("click", handleAddUsageAddress);
  usageRefreshButton?.addEventListener("click", handleRefreshUsageStats);
  usageClearButton?.addEventListener("click", handleClearUsageStats);
  usageTableBody?.addEventListener("click", handleUsageTableClick);
  usageAddressInput?.addEventListener("keydown", handleUsageInputKey);
  usageLabelInput?.addEventListener("keydown", handleUsageInputKey);
}

function init() {
  initTabs();
  updateEnvironmentSection();
  configureFormDefaults();
  updateFreeQuotaDisplay();
  updatePaidUsageDisplay();
  updateFaucetDisplay();
  loadUsageAddresses();
  updateUsageEpochDisplay();
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
