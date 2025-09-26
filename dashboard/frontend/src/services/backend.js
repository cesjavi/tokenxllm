// src/services/backend.js
import { appConfig } from "../config.js";

// Base URL: usa appConfig.backendUrl o default '/api' (proxy en Vercel)
const BASE = ((appConfig?.backendUrl ?? "/api") + "").replace(/\/+$/, "");

// Helper para armar URL con path seguro
function joinUrl(path) {
  const p = path.startsWith("/") ? path : `/${path}`;
  return `${BASE}${p}`;
}

async function request(path, options = {}) {
  const url = joinUrl(path);

  const headers = { accept: "application/json", ...(options.headers ?? {}) };
  // Solo seteamos Content-Type si hay body y no lo definieron
  if (options.body && !("content-type" in Object.keys(headers).reduce((h, k) => (h[k.toLowerCase()] = headers[k], h), {}))) {
    headers["Content-Type"] = "application/json";
  }

  const res = await fetch(url, { ...options, headers });

  // Intenta parsear el error del backend para dar un mensaje útil
  if (!res.ok) {
    const txt = await res.text().catch(() => "");
    try {
      const j = txt ? JSON.parse(txt) : null;
      const detail = j?.detail ?? j?.error ?? j;
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail ?? { status: res.status }));
    } catch {
      throw new Error(txt || res.statusText);
    }
  }

  // Parse de respuesta según Content-Type
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) return res.json();
  const text = await res.text();
  return text ? text : undefined;
}

/* ===== Endpoints ===== */

export const getBackendConfig = () => request("/config");

export const getBalance = (userAddress) =>
  request(`/balance?user=${encodeURIComponent(userAddress)}`);

export const getAllowance = (ownerAddress, spenderAddress) =>
  request(`/allowance?owner=${encodeURIComponent(ownerAddress)}&spender=${encodeURIComponent(spenderAddress)}`);

export const getUsedUnits = (userAddress) =>
  request(`/used?user=${encodeURIComponent(userAddress)}`);

export const getFreeQuota = (userAddress) => {
  const q = userAddress ? `?user=${encodeURIComponent(userAddress)}` : "";
  return request(`/free_quota${q}`);
};

export const getEpoch = () => request(`/epoch`);

export const approve = (amount) =>
  request(`/approve`, {
    method: "POST",
    body: JSON.stringify({ amount }),
  });

export const authorize = (units) =>
  request(`/authorize`, {
    method: "POST",
    body: JSON.stringify({ units }),
  });

export const mint = (to, amount) =>
  request(`/mint`, {
    method: "POST",
    body: JSON.stringify({ to, amount }),
  });

export const getFaucetInfo = (address) => {
  const q = address ? `?address=${encodeURIComponent(address)}` : "";
  return request(`/faucet${q}`);
};

// Si tu backend espera {to: "..."} dejalo así; si espera {address: "..."},
// cambiá la clave a { address }
export const requestFaucet = (address) =>
  request(`/faucet`, {
    method: "POST",
    body: JSON.stringify({ to: address }),
  });
