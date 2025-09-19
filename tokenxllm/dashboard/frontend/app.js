async function api(base, path, opts){
  const r = await fetch(`${base}${path}`, opts);
  if(!r.ok){ throw new Error(await r.text()); }
  return r.json();
}
function v(id){ return document.getElementById(id).value.trim(); }
function set(id, txt){ document.getElementById(id).textContent = txt; }
function setTxLog(content, opts = {}){
  const el = document.getElementById("txlog");
  if(opts.html){ el.innerHTML = content; }
  else{ el.textContent = content; }
}
function errMsg(e){ return (e && e.message) ? e.message : String(e); }

let cachedConfig = null;
let cachedConfigBase = null;

async function ensureConfig(base, opts = {}){
  if(!base){ throw new Error("Configura primero la URL del backend"); }
  const force = Boolean(opts.force);
  if(force || !cachedConfig || cachedConfigBase !== base){
    cachedConfig = await api(base, "/config");
    cachedConfigBase = base;
  }
  return cachedConfig;
}

const TX_STAGES = [
  { label: "firmando…", delay: 0 },
  { label: "enviando…", delay: 500 },
  { label: "confirmando…", delay: 1200 },
];

function delay(ms){ return new Promise(res => setTimeout(res, ms)); }

async function withTxLifecycle(actionLabel, op){
  let cancelled = false;
  const stagePromise = (async () => {
    for(const stage of TX_STAGES){
      if(cancelled) break;
      if(stage.delay){ await delay(stage.delay); if(cancelled) break; }
      setTxLog(`${actionLabel} - ${stage.label}`);
    }
  })();
  try{
    const result = await op();
    cancelled = true;
    await stagePromise;
    return result;
  }catch(e){
    cancelled = true;
    await stagePromise;
    throw e;
  }
}

function detectNetworkMeta(rpcUrl){
  const url = (rpcUrl || "").toLowerCase();
  if(url.includes("mainnet")){
    return { label: "Mainnet", starkscan: "https://starkscan.co/tx/", voyager: "https://voyager.online/tx/" };
  }
  if(url.includes("goerli") || url.includes("testnet")){
    return { label: "Goerli", starkscan: "https://goerli.starkscan.co/tx/", voyager: "https://goerli.voyager.online/tx/" };
  }
  if(url.includes("sepolia")){
    return { label: "Sepolia", starkscan: "https://sepolia.starkscan.co/tx/", voyager: "https://sepolia.voyager.online/tx/" };
  }
  return { label: "Starknet", starkscan: "https://starkscan.co/tx/", voyager: "https://voyager.online/tx/" };
}

function explorerLinks(txHash, cfg){
  const meta = detectNetworkMeta(cfg && cfg.rpc_url);
  const links = [
    `<a href="${meta.starkscan}${txHash}" target="_blank" rel="noreferrer">StarkScan (${meta.label})</a>`,
    `<a href="${meta.voyager}${txHash}" target="_blank" rel="noreferrer">Voyager (${meta.label})</a>`
  ];
  return { label: meta.label, html: links.join(" · ") };
}

function decimalToWei(value, decimals){
  if(value == null) return 0n;
  const str = String(value).trim();
  if(!str){ return 0n; }
  const negative = str.startsWith("-");
  const sanitized = negative ? str.slice(1) : str;
  const parts = sanitized.split(".");
  const intPart = parts[0] || "0";
  const fracRaw = parts[1] || "";
  const frac = (fracRaw + "0".repeat(decimals)).slice(0, decimals);
  const base = 10n ** BigInt(decimals);
  const wei = BigInt(intPart || "0") * base + BigInt(frac || "0");
  return negative ? -wei : wei;
}

function formatWeiAmount(wei, decimals, maxFractionDigits = 6){
  const base = 10n ** BigInt(decimals);
  const negative = wei < 0n;
  const absWei = negative ? -wei : wei;
  const intPart = absWei / base;
  let frac = (absWei % base).toString().padStart(decimals, "0");
  if(maxFractionDigits >= 0){ frac = frac.slice(0, maxFractionDigits); }
  frac = frac.replace(/0+$/, "");
  const body = frac ? `${intPart}.${frac}` : intPart.toString();
  return negative ? `-${body}` : body;
}

function computeEstimatedCostWei(units, cfg){
  const decimals = Number(cfg && cfg.decimals != null ? cfg.decimals : 18);
  const unitsBig = BigInt(units);
  if(unitsBig <= 0n) return 0n;
  if(cfg && cfg.estimated_cost_per_unit_wei){
    try{ return BigInt(cfg.estimated_cost_per_unit_wei) * unitsBig; }
    catch(_){ /* ignore */ }
  }
  if(cfg && cfg.price_per_unit_wei){
    try{ return BigInt(cfg.price_per_unit_wei) * unitsBig; }
    catch(_){ /* ignore */ }
  }
  if(cfg && (cfg.estimated_cost_per_unit_AIC || cfg.cost_per_unit_AIC)){
    const perUnit = cfg.estimated_cost_per_unit_AIC || cfg.cost_per_unit_AIC;
    const perUnitWei = decimalToWei(perUnit, decimals);
    if(perUnitWei > 0n){ return perUnitWei * unitsBig; }
  }
  // Sin información adicional asumimos 1 token completo por unidad.
  const base = 10n ** BigInt(decimals);
  return unitsBig * base;
}

document.getElementById("btnConfig").onclick = async () => {
  const base = v("baseUrl");
  try{
    const cfg = await ensureConfig(base, {force: true});
    set("config", JSON.stringify(cfg, null, 2));
  }catch(e){
    set("config", errMsg(e));
  }
};

document.getElementById("btnRefresh").onclick = async () => {
  const base = v("baseUrl"), user = v("userAddr");
  if(!user){ alert("Enter your address"); return; }
  try{
    const cfg = await ensureConfig(base);
    const userEnc = encodeURIComponent(user);
    const bal = await api(base, `/balance?user=${userEnc}`);
    set("balance", `wei: ${bal.balance_wei}\nAIC: ${bal.balance_AIC}`);
    if(cfg.um_addr){
      const spenderEnc = encodeURIComponent(cfg.um_addr);
      const al = await api(base, `/allowance?owner=${userEnc}&spender=${spenderEnc}`);
      const used = await api(base, `/used?user=${userEnc}`);
      const ep = await api(base, `/epoch`);
      set("allowance", `wei: ${al.allowance_wei}\nAIC: ${al.allowance_AIC}`);
      set("usage", `used_units: ${used.used_units}\nepoch_id: ${ep.epoch_id}`);
    }else{
      set("allowance", "UM_ADDR not configured");
      set("usage", "UM_ADDR not configured");
    }
  }catch(e){ set("balance", errMsg(e)); }
};

document.getElementById("btnApprove").onclick = async () => {
  const base = v("baseUrl"), amount = parseFloat(v("approveAmount"));
  if(!Number.isFinite(amount) || amount <= 0){
    setTxLog("Ingresa un monto válido para aprobar.");
    return;
  }
  try{
    const cfg = await ensureConfig(base);
    const result = await withTxLifecycle("Aprobación", () => api(
      base,
      "/approve",
      {method:"POST", headers:{'Content-Type':'application/json'}, body: JSON.stringify({amount})}
    ));
    const links = explorerLinks(result.tx_hash, cfg);
    setTxLog(
      `<div>Aprobación enviada (${links.label}).</div>` +
      `<div>Tx: <code>${result.tx_hash}</code></div>` +
      `<div>${links.html}</div>`,
      {html:true}
    );
  }catch(e){ setTxLog(`approve error: ${errMsg(e)}`); }
};

document.getElementById("btnAuthorize").onclick = async () => {
  const base = v("baseUrl"), units = parseInt(v("authUnits"),10), user = v("userAddr");
  if(!user){
    setTxLog("Ingresa tu dirección para validar la allowance antes de autorizar.");
    return;
  }
  if(!Number.isFinite(units) || units <= 0){
    setTxLog("Ingresa una cantidad de unidades válida para autorizar.");
    return;
  }
  try{
    const cfg = await ensureConfig(base);
    if(!cfg.um_addr){
      setTxLog("UM_ADDR no está configurada en el backend; no es posible autorizar.");
      return;
    }
    const ownerEnc = encodeURIComponent(user);
    const spenderEnc = encodeURIComponent(cfg.um_addr);
    const allowance = await api(base, `/allowance?owner=${ownerEnc}&spender=${spenderEnc}`);
    if(!allowance || allowance.allowance_wei == null){
      setTxLog("No se pudo recuperar la allowance desde el backend.");
      return;
    }
    let allowanceWei;
    try{ allowanceWei = BigInt(allowance.allowance_wei); }
    catch(_){
      setTxLog("La allowance recibida es inválida.");
      return;
    }
    const decimals = Number(cfg && cfg.decimals != null ? cfg.decimals : 18);
    if(allowanceWei <= 0n){
      setTxLog("La allowance actual es 0 AIC. Realiza un approve antes de autorizar.");
      return;
    }
    const estimatedCostWei = computeEstimatedCostWei(units, cfg);
    if(estimatedCostWei > allowanceWei){
      const allowanceTxt = formatWeiAmount(allowanceWei, decimals);
      const costTxt = formatWeiAmount(estimatedCostWei, decimals);
      setTxLog(`Allowance insuficiente (${allowanceTxt} AIC) frente al costo estimado (${costTxt} AIC). Ejecuta un approve mayor antes de autorizar.`);
      return;
    }
    const result = await withTxLifecycle("Autorización", () => api(
      base,
      "/authorize",
      {method:"POST", headers:{'Content-Type':'application/json'}, body: JSON.stringify({units})}
    ));
    const links = explorerLinks(result.tx_hash, cfg);
    setTxLog(
      `<div>Autorización enviada (${links.label}).</div>` +
      `<div>Tx: <code>${result.tx_hash}</code></div>` +
      `<div>${links.html}</div>`,
      {html:true}
    );
  }catch(e){ setTxLog(`authorize error: ${errMsg(e)}`); }
};

document.getElementById("btnMint").onclick = async () => {
  const base = v("baseUrl"), to = v("mintTo"), amount = parseFloat(v("mintAmount"));
  try{
    const r = await api(base, "/mint", {method:"POST", headers:{'Content-Type':'application/json'}, body: JSON.stringify({to, amount})});
    setTxLog(`mint tx: ${r.tx_hash}`);
  }catch(e){ setTxLog(`mint error: ${errMsg(e)}`); }
};
