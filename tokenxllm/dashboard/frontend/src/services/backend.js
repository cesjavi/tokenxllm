import { appConfig, assertBackendConfigured } from "../config";

async function request(path, options = {}) {
  assertBackendConfigured();

  const headers = { ...(options.headers ?? {}) };
  if (options.body && !("Content-Type" in headers)) {
    headers["Content-Type"] = "application/json";
  }

  const response = await fetch(`${appConfig.backendUrl}${path}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || response.statusText);
  }

  const text = await response.text();
  return text ? JSON.parse(text) : undefined;
}

export function getBackendConfig() {
  return request("/config");
}

export function getBalance(userAddress) {
  return request(`/balance?user=${encodeURIComponent(userAddress)}`);
}

export function getAllowance(ownerAddress, spenderAddress) {
  return request(
    `/allowance?owner=${encodeURIComponent(ownerAddress)}&spender=${encodeURIComponent(
      spenderAddress,
    )}`,
  );
}

export function getUsedUnits(userAddress) {
  return request(`/used?user=${encodeURIComponent(userAddress)}`);
}

export function getEpoch() {
  return request(`/epoch`);
}

export function approve(amount) {
  return request(`/approve`, {
    method: "POST",
    body: JSON.stringify({ amount }),
  });
}

export function authorize(units) {
  return request(`/authorize`, {
    method: "POST",
    body: JSON.stringify({ units }),
  });
}

export function mint(to, amount) {
  return request(`/mint`, {
    method: "POST",
    body: JSON.stringify({ to, amount }),
  });
}
