const sanitize = (value) => (typeof value === "string" ? value.trim() : value);

const parsedDecimals = (() => {
  const raw = sanitize(import.meta.env.VITE_DECIMALS);
  if (raw === undefined || raw === null || raw === "") {
    return undefined;
  }
  const decimals = Number(raw);
  return Number.isFinite(decimals) ? decimals : undefined;
})();

export const appConfig = {
  backendUrl: sanitize(import.meta.env.VITE_BACKEND_URL) || "",
  rpcUrl: sanitize(import.meta.env.VITE_RPC_URL) || "",
  aicAddress: sanitize(import.meta.env.VITE_AIC_ADDR) || "",
  umAddress: sanitize(import.meta.env.VITE_UM_ADDR) || "",
  decimals: parsedDecimals ?? 18,
};

export function assertBackendConfigured() {
  if (!appConfig.backendUrl) {
    throw new Error("VITE_BACKEND_URL is not configured");
  }
}
