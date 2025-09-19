import { connect, disconnect } from "https://cdn.jsdelivr.net/npm/starknetkit@1.0.15/+esm";

const state = {
  apiBase: determineBaseUrl(),
  config: null,
  wallet: null,
  account: null,
  address: null,
};

const elements = {
  config: document.getElementById("config"),
  walletAddr: document.getElementById("walletAddr"),
  backendBase: document.getElementById("backendBase"),
  userAddr: document.getElementById("userAddr"),
  txlog: document.getElementById("txlog"),
  balance: document.getElementById("balance"),
  allowance: document.getElementById("allowance"),
  usage: document.getElementById("usage"),
  btnConnect: document.getElementById("btnConnect"),
  btnDisconnect: document.getElementById("btnDisconnect"),
  btnRefresh: document.getElementById("btnRefresh"),
  btnApprove: document.getElementById("btnApprove"),
  btnAuthorize: document.getElementById("btnAuthorize"),
  approveAmount: document.getElementById("approveAmount"),
  authUnits: document.getElementById("authUnits"),
};

elements.backendBase.textContent = state.apiBase;
updateWalletUi(false);

function determineBaseUrl(){
  const override = window.APP_BACKEND_BASE;
  if(override){ return normalizeBase(String(override)); }
  if(window.location.protocol === "file:"){ return "http://localhost:8000"; }
  const port = window.location.port;
  if(port && port !== "8000"){ return `${window.location.protocol}//${window.location.hostname}:8000`; }
  return normalizeBase(window.location.origin || "http://localhost:8000");
}

function normalizeBase(url){
  return url.replace(/\/+$/, "");
}

async function api(path, opts){
  const url = `${state.apiBase}${path}`;
  const res = await fetch(url, opts);
  if(!res.ok){
    const text = await res.text();
    throw new Error(text || `${res.status} ${res.statusText}`);
  }
  return res.json();
}

function setText(el, value){
  el.textContent = value;
}

function formatError(err){
  if(err instanceof Error){ return err.message; }
  if(typeof err === "string"){ return err; }
  try{ return JSON.stringify(err); }
  catch(_){ return String(err); }
}

async function loadConfig(){
  try{
    const cfg = await api("/config");
    state.config = cfg;
    setText(elements.config, JSON.stringify(cfg, null, 2));
    return cfg;
  }catch(err){
    setText(elements.config, `config error: ${formatError(err)}`);
    throw err;
  }
}

async function ensureConfig(){
  if(state.config){ return state.config; }
  return loadConfig();
}

function updateWalletUi(connected){
  if(connected){
    const chain = state.wallet?.chainId ?? "unknown";
    setText(elements.walletAddr, `${state.address}\nchain: ${chain}`);
    setText(elements.userAddr, state.address || "");
  }else{
    setText(elements.walletAddr, "Not connected");
    setText(elements.userAddr, "—");
  }
  elements.btnDisconnect.classList.toggle("hidden", !connected);
  [elements.btnRefresh, elements.btnApprove, elements.btnAuthorize].forEach(btn => {
    if(btn){ btn.disabled = !connected; }
  });
}

async function attemptAutoConnect(){
  try{
    const result = await connect({ modalMode: "neverAsk" });
    if(result && result.wallet){
      applyWallet(result.wallet);
    }
  }catch(err){
    console.warn("auto connect failed", err);
  }
}

function applyWallet(wallet){
  state.wallet = wallet;
  state.account = wallet.account;
  state.address = wallet.selectedAddress || wallet.account?.address || null;
  updateWalletUi(true);
  refreshData().catch(() => {});
}

function clearWallet(){
  state.wallet = null;
  state.account = null;
  state.address = null;
  updateWalletUi(false);
}

async function refreshData(){
  try{
    ensureWallet();
  }catch(_){
    alert("Connect your wallet first");
    return;
  }
  let cfg;
  try{
    cfg = await ensureConfig();
  }catch(err){
    setText(elements.balance, formatError(err));
    return;
  }
  const user = encodeURIComponent(state.address);
  try{
    const bal = await api(`/balance?user=${user}`);
    setText(elements.balance, `wei: ${bal.balance_wei}\nAIC: ${bal.balance_AIC}`);
  }catch(err){
    setText(elements.balance, `balance error: ${formatError(err)}`);
  }
  if(cfg.um_addr){
    try{
      const spender = encodeURIComponent(cfg.um_addr);
      const [allowance, used, epoch] = await Promise.all([
        api(`/allowance?owner=${user}&spender=${spender}`),
        api(`/used?user=${user}`),
        api(`/epoch`),
      ]);
      setText(elements.allowance, `wei: ${allowance.allowance_wei}\nAIC: ${allowance.allowance_AIC}`);
      setText(elements.usage, `used_units: ${used.used_units}\nepoch_id: ${epoch.epoch_id}`);
    }catch(err){
      setText(elements.allowance, `allowance error: ${formatError(err)}`);
      setText(elements.usage, `usage error: ${formatError(err)}`);
    }
  }else{
    setText(elements.allowance, "UM_ADDR not configured");
    setText(elements.usage, "UM_ADDR not configured");
  }
}

function toUint256(value){
  const mask = (1n << 128n) - 1n;
  const lo = value & mask;
  const hi = value >> 128n;
  return [lo.toString(), hi.toString()];
}

function parseUnits(value, decimals){
  const trimmed = String(value ?? "").trim();
  if(!trimmed){ throw new Error("Enter an amount"); }
  if(!/^\d*(\.\d*)?$/.test(trimmed)){ throw new Error("Invalid amount format"); }
  const [wholeRaw, fracRaw = ""] = trimmed.split(".");
  const base = 10n ** BigInt(decimals);
  const whole = wholeRaw ? BigInt(wholeRaw) : 0n;
  const fracPadded = (fracRaw + "0".repeat(decimals)).slice(0, decimals);
  const fraction = fracPadded ? BigInt(fracPadded) : 0n;
  return whole * base + fraction;
}

function ensureWallet(){
  if(!state.wallet || !state.account || !state.address){
    throw new Error("Connect your wallet first");
  }
  return state.wallet;
}

async function doApprove(){
  let wallet;
  try{
    wallet = ensureWallet();
  }catch(err){
    setText(elements.txlog, formatError(err));
    return;
  }
  let cfg;
  try{
    cfg = await ensureConfig();
  }catch(err){
    setText(elements.txlog, `config error: ${formatError(err)}`);
    return;
  }
  if(!cfg.aic_addr || !cfg.um_addr){
    setText(elements.txlog, "AIC_ADDR/UM_ADDR not configured");
    return;
  }
  try{
    const decimals = cfg.decimals ?? 18;
    const weiAmount = parseUnits(elements.approveAmount.value, decimals);
    const [lo, hi] = toUint256(weiAmount);
    const { transaction_hash } = await wallet.account.execute({
      contractAddress: cfg.aic_addr,
      entrypoint: "approve",
      calldata: [cfg.um_addr, lo, hi],
    });
    setText(elements.txlog, `approve tx: ${transaction_hash}`);
  }catch(err){
    setText(elements.txlog, `approve error: ${formatError(err)}`);
  }
}

async function doAuthorize(){
  let wallet;
  try{
    wallet = ensureWallet();
  }catch(err){
    setText(elements.txlog, formatError(err));
    return;
  }
  let cfg;
  try{
    cfg = await ensureConfig();
  }catch(err){
    setText(elements.txlog, `config error: ${formatError(err)}`);
    return;
  }
  if(!cfg.um_addr){
    setText(elements.txlog, "UM_ADDR not configured");
    return;
  }
  const unitsRaw = String(elements.authUnits.value ?? "").trim();
  if(!unitsRaw){
    setText(elements.txlog, "Enter units to authorize");
    return;
  }
  let units;
  try{
    units = BigInt(unitsRaw);
  }catch(err){
    setText(elements.txlog, `Invalid units: ${formatError(err)}`);
    return;
  }
  if(units < 0n){
    setText(elements.txlog, "Units must be non-negative");
    return;
  }
  try{
    const { transaction_hash } = await wallet.account.execute({
      contractAddress: cfg.um_addr,
      entrypoint: "authorize_usage",
      calldata: [units.toString()],
    });
    setText(elements.txlog, `authorize tx: ${transaction_hash}`);
  }catch(err){
    setText(elements.txlog, `authorize error: ${formatError(err)}`);
  }
}

elements.btnConnect.addEventListener("click", async () => {
  try{
    const result = await connect({ modalMode: "alwaysAsk" });
    if(result && result.wallet){
      applyWallet(result.wallet);
    }
  }catch(err){
    setText(elements.txlog, `wallet error: ${formatError(err)}`);
  }
});

elements.btnDisconnect.addEventListener("click", async () => {
  try{
    await disconnect({ clearLastWallet: true });
  }catch(err){
    console.warn("disconnect error", err);
  }
  clearWallet();
});

document.getElementById("btnConfig").addEventListener("click", () => {
  loadConfig().catch(() => {});
});

elements.btnRefresh.addEventListener("click", () => {
  refreshData();
});

elements.btnApprove.addEventListener("click", () => {
  doApprove();
});

elements.btnAuthorize.addEventListener("click", () => {
  doAuthorize();
});

loadConfig().catch(() => {});
attemptAutoConnect();
