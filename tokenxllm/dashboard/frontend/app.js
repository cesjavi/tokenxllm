async function api(base, path, opts){
  const r = await fetch(`${base}${path}`, opts);
  if(!r.ok){ throw new Error(await r.text()); }
  return r.json();
}
function v(id){ return document.getElementById(id).value.trim(); }
function set(id, txt){ document.getElementById(id).textContent = txt; }

document.getElementById("btnConfig").onclick = async () => {
  const base = v("baseUrl");
  try { set("config", JSON.stringify(await api(base,"/config"), null, 2)); }
  catch(e){ set("config", String(e)); }
};

document.getElementById("btnRefresh").onclick = async () => {
  const base = v("baseUrl"), user = v("userAddr");
  if(!user){ alert("Enter your address"); return; }
  try{
    const cfg = await api(base, "/config");
    const bal = await api(base, `/balance?user=${user}`);
    set("balance", `wei: ${bal.balance_wei}\nAIC: ${bal.balance_AIC}`);
    if(cfg.um_addr){
      const al = await api(base, `/allowance?owner=${user}&spender=${cfg.um_addr}`);
      const used = await api(base, `/used?user=${user}`);
      const ep = await api(base, `/epoch`);
      set("allowance", `wei: ${al.allowance_wei}\nAIC: ${al.allowance_AIC}`);
      set("usage", `used_units: ${used.used_units}\nepoch_id: ${ep.epoch_id}`);
    }else{
      set("allowance", "UM_ADDR not configured");
      set("usage", "UM_ADDR not configured");
    }
  }catch(e){ set("balance", String(e)); }
};

document.getElementById("btnApprove").onclick = async () => {
  const base = v("baseUrl"), amount = parseFloat(v("approveAmount"));
  try{
    const r = await api(base, "/approve", {method:"POST", headers:{'Content-Type':'application/json'}, body: JSON.stringify({amount})});
    set("txlog", `approve tx: ${r.tx_hash}`);
  }catch(e){ set("txlog", `approve error: ${e}`); }
};

document.getElementById("btnAuthorize").onclick = async () => {
  const base = v("baseUrl"), units = parseInt(v("authUnits"),10);
  try{
    const r = await api(base, "/authorize", {method:"POST", headers:{'Content-Type':'application/json'}, body: JSON.stringify({units})});
    set("txlog", `authorize tx: ${r.tx_hash}`);
  }catch(e){ set("txlog", `authorize error: ${e}`); }
};

document.getElementById("btnMint").onclick = async () => {
  const base = v("baseUrl"), to = v("mintTo"), amount = parseFloat(v("mintAmount"));
  try{
    const r = await api(base, "/mint", {method:"POST", headers:{'Content-Type':'application/json'}, body: JSON.stringify({to, amount})});
    set("txlog", `mint tx: ${r.tx_hash}`);
  }catch(e){ set("txlog", `mint error: ${e}`); }
};
