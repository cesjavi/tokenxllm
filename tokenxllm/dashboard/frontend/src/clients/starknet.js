// clients/starknet.js
// Funciona con o sin get-starknet, sin require() y sin top-level await.

let cachedProvider = null;

function pickFirstAccount(obj) {
  const acc =
    obj?.account ||
    (Array.isArray(obj?.accounts) && obj.accounts.length ? obj.accounts[0] : null) ||
    obj?.selectedAccount ||
    null;

  const address =
    acc?.address ||
    obj?.selectedAddress ||
    obj?.selectedAccountAddress ||
    null;

  return { account: acc || null, address: address || null };
}

async function loadGetStarknet() {
  // Intenta cargar get-starknet si está instalado; soporta default o named export.
  try {
    const m = await import('get-starknet');
    return m.getStarknet || m.default || null;
  } catch {
    return null;
  }
}

export function getProvider() {
  if (cachedProvider) return cachedProvider;

  // Fallback a inyectados
  const w = typeof window !== 'undefined' ? window : {};
  cachedProvider =
    w.starknet ||
    w.starknet_argentX ||
    w.argentX ||
    w.starknet_braavos ||
    w.braavos ||
    null;

  return cachedProvider;
}

export async function connectWallet() {
  // 1) Prefer get-starknet si existe
  const getStarknet = await loadGetStarknet();
  if (getStarknet) {
    const sn = getStarknet();          // handler
    await sn.enable({ showModal: true }); // abre modal y expone cuenta
    const { account, address } = pickFirstAccount(sn);
    if (!address) throw new Error('La billetera no expuso ninguna cuenta.');
    return { wallet: sn, account, address };
  }

  // 2) Fallback a proveedores inyectados
  const provider = getProvider();
  if (!provider) {
    throw new Error('No se encontró un proveedor de Starknet. Instala Argent X o Braavos.');
  }

  // Algunos exponen request, otros enable
  if (typeof provider.request === 'function') {
    try {
      await provider.request({ type: 'starknet_requestAccounts' });
    } catch {
      try {
        await provider.request({ method: 'wallet_requestAccounts' });
      } catch {
        if (typeof provider.enable === 'function') {
          await provider.enable();
        }
      }
    }
  } else if (typeof provider.enable === 'function') {
    await provider.enable();
  }

  const { account, address } = pickFirstAccount(provider);
  if (!address) throw new Error('No se pudo obtener la dirección de la cuenta.');
  return { wallet: provider, account, address };
}
