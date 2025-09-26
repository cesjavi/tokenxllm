import { appConfig } from "./config.js";
import {
  approve,
  authorize,
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

const faucetState = {
  backendEnabled: true,
  writesEnabled: false,
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
      statusText = "Deshabilitado";
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

function applyWriteAvailability(enabled) {
  writesEnabled = Boolean(enabled);
  const buttons = ["btnApprove", "btnAuthorize", "btnMint", "btnSpendFree", "btnFaucet"]
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

async function handleSpendFree() {
  if (!ensureWritesAreEnabled()) {
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
    const response = await authorize(units);
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

async function handleRequestFaucet() {
  if (!ensureWritesAreEnabled()) {
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
}

function init() {
  updateEnvironmentSection();
  configureFormDefaults();
  updateFreeQuotaDisplay();
  updatePaidUsageDisplay();
  updateFaucetDisplay();
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
