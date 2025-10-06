const sanitize = (value) => (typeof value === "string" ? value.trim() : value);

const env = (() => {
  try {
    return (import.meta && import.meta.env) || {};
  } catch (error) {
    return {};
  }
})();

const parsedDecimals = (() => {
  const raw = sanitize(env.VITE_DECIMALS);
  if (raw === undefined || raw === null || raw === "") {
    return undefined;
  }
  const decimals = Number(raw);
  return Number.isFinite(decimals) ? decimals : undefined;
})();

export const appConfig = {
  // Forzamos relativo para que pase por el proxy de Vercel
  backendUrl: import.meta.env.VITE_BACKEND_URL || '/api',
  rpcUrl: import.meta.env.VITE_RPC_URL || '',
  aicAddress: import.meta.env.VITE_AIC_ADDRESS || '',
  umAddress: import.meta.env.VITE_UM_ADDRESS || '',
  decimals: Number(import.meta.env.VITE_DECIMALS ?? 18),
};

// Acepta absoluta (http/https) o relativa que empiece con "/"
export function assertBackendConfigured() {
  const u = appConfig.backendUrl;
  if (!u) throw new Error('backendUrl not configured');
  if (!/^https?:\/\//i.test(u) && !u.startsWith('/')) {
    throw new Error('backendUrl must be absolute (http...) or start with "/"');
  }
}
