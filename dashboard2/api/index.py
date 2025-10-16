# api/index.py
from __future__ import annotations

import os
import asyncio
from functools import lru_cache
from typing import Optional

from fastapi import FastAPI, HTTPException, Body, Query
from fastapi.middleware.cors import CORSMiddleware

# starknet_py
from starknet_py.net.full_node_client import FullNodeClient
from starknet_py.net.account.account import Account
from starknet_py.net.signer.stark_curve_signer import KeyPair
from starknet_py.net.client_models import Call
from starknet_py.hash.selector import get_selector_from_name

# ---------- Config ----------
RPC_URL = os.getenv("STARKNET_RPC_URL", "https://starknet-sepolia.public.blastapi.io/rpc/v0_9")
ADMIN_PRIVATE_KEY = os.getenv("ADMIN_PRIVATE_KEY")
ADMIN_ADDRESS = os.getenv("ADMIN_ADDRESS")
TOKEN_ADDRESS_HEX = os.getenv("TOKEN_ADDRESS", "0x0")
USAGE_MANAGER_ADDRESS_HEX = os.getenv("USAGE_MANAGER_ADDRESS", "0x0")
TREASURY_ADDRESS_HEX = os.getenv("TREASURY_ADDRESS", "0x0")

# parse addrs hex -> int (tolerante)
def _to_int(x: str) -> int:
    try:
        x = x.strip()
        return int(x, 16) if x.startswith("0x") else int(x)
    except Exception:
        return 0

TOKEN_ADDRESS = _to_int(TOKEN_ADDRESS_HEX)
USAGE_MANAGER_ADDRESS = _to_int(USAGE_MANAGER_ADDRESS_HEX)
TREASURY_ADDRESS = _to_int(TREASURY_ADDRESS_HEX)

# ---------- App ----------
app = FastAPI(title="TokenXLLM API")

# (No hace falta CORS si frontend y API están en el mismo dominio de Vercel,
# pero dejarlo abierto no molesta y ayuda si probás desde localhost)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------- Lazy singletons (import-safe para Vercel) ----------
@lru_cache(maxsize=1)
def get_client() -> FullNodeClient:
    # Se crea recién cuando se usa en un request
    return FullNodeClient(node_url=RPC_URL)

async def _get_chain_id() -> int:
    return await get_client().get_chain_id()

async def _get_admin_account() -> Optional[Account]:
    """
    Devuelve Account admin si hay ENV válidas; None si no están configuradas.
    No levanta errores en import (solo cuando se usa).
    """
    if not ADMIN_PRIVATE_KEY or not ADMIN_ADDRESS:
        return None

    # parse key/address
    try:
        priv = int(ADMIN_PRIVATE_KEY, 16) if str(ADMIN_PRIVATE_KEY).startswith("0x") else int(ADMIN_PRIVATE_KEY)
        addr = int(ADMIN_ADDRESS, 16) if str(ADMIN_ADDRESS).startswith("0x") else int(ADMIN_ADDRESS)
    except Exception:
        # variables mal formateadas
        return None

    chain_id = await _get_chain_id()
    kp = KeyPair.from_private_key(priv)
    return Account(client=get_client(), address=addr, key_pair=kp, chain=chain_id)

# --------- Utils starknet ---------
def u256_to_int(values: list[int]) -> int:
    if not values:
        return 0
    if len(values) == 1:
        return int(values[0])
    return int(values[0]) + (int(values[1]) << 128)

async def call_contract(contract_address: int, function_name: str, calldata: list[int] | None = None) -> list[int]:
    try:
        return await get_client().call_contract(
            call=Call(
                to_addr=contract_address,
                selector=get_selector_from_name(function_name),
                calldata=calldata or [],
            ),
            block_number="latest",
        )
    except Exception as e:
        # En serverless preferimos no explotar: devolvemos []
        print(f"[call_contract] {function_name} failed: {e}")
        return []

_TX_LOCK = asyncio.Lock()

async def send_calls(calls: list[Call]) -> str:
    """
    Envía transacciones usando la cuenta admin (si está configurada).
    Devuelve el tx_hash (hex string). Lanza HTTPException si no hay admin.
    """
    account = await _get_admin_account()
    if not account:
        raise HTTPException(status_code=501, detail="Cuenta admin no configurada en el backend")

    async with _TX_LOCK:
        # Intento v3 → fallback v1
        try:
            try:
                tx = await account.execute_v3(calls=calls, auto_estimate=True)
            except Exception:
                tx = await account.execute(calls=calls, version=1, auto_estimate=True)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Fallo al enviar transacción: {exc}") from exc

        tx_hash = getattr(tx, "hash", None) or getattr(tx, "transaction_hash", None)
        # Esperar a que la cadena lo acepte (opcional: podés omitir en serverless si te preocupa el timeout)
        try:
            tx_hash_int = int(tx_hash, 16) if isinstance(tx_hash, str) else int(tx_hash)
            await account.client.wait_for_tx(tx_hash_int)
        except Exception:
            pass

        return tx_hash if isinstance(tx_hash, str) else hex(int(tx_hash))

# --------- Rutas JSON (sin prefijo /api) ----------

@app.get("/config")
async def api_config():
    return {
        "rpc_url": RPC_URL,
        "aic_addr": hex(TOKEN_ADDRESS),
        "um_addr": hex(USAGE_MANAGER_ADDRESS),
        "treasury_addr": hex(TREASURY_ADDRESS),
        "account_address": ADMIN_ADDRESS,  # str o None
    }

@app.get("/epoch")
async def api_epoch():
    r = await call_contract(USAGE_MANAGER_ADDRESS, "get_epoch_id")
    return {"epoch_id": int(r[0]) if r else 0}

@app.get("/balance")
async def api_balance(user: str = Query(..., description="Dirección 0x...")):
    try:
        user_int = int(user, 16)
    except Exception:
        raise HTTPException(status_code=400, detail="user inválido (esperado 0x...)")

    bal = await call_contract(TOKEN_ADDRESS, "balanceOf", [user_int])
    dec = await call_contract(TOKEN_ADDRESS, "decimals")
    decimals = int(dec[0]) if dec else 18
    value = u256_to_int(bal) if bal else 0
    return {"user": user, "balance_wei": value, "balance_AIC": value / (10 ** decimals)}

@app.get("/free_quota")
async def api_free_quota(user: Optional[str] = Query(None)):
    quota = await call_contract(USAGE_MANAGER_ADDRESS, "get_free_quota_per_epoch")
    price = await call_contract(USAGE_MANAGER_ADDRESS, "get_price_per_unit_wei")

    used = 0
    if user:
        try:
            used_r = await call_contract(USAGE_MANAGER_ADDRESS, "used_in_current_epoch", [int(user, 16)])
            used = int(used_r[0]) if used_r else 0
        except Exception:
            used = 0

    dec = await call_contract(TOKEN_ADDRESS, "decimals")
    decimals = int(dec[0]) if dec else 18
    price_wei = u256_to_int(price) if price else 0

    free_quota = int(quota[0]) if quota else 0
    free_remaining = max(0, free_quota - used)

    return {
        "free_quota": free_quota,
        "used_units": used,
        "free_remaining": free_remaining,
        "price_per_unit_wei": str(price_wei),  # el front divide por 1e18
    }

# ----- Acciones que requieren admin -----

@app.post("/mint")
async def api_mint(body: dict = Body(...)):
    address = body.get("to")
    amount = body.get("amount")
    if not address or amount is None:
        raise HTTPException(status_code=400, detail="Faltan parámetros (to, amount)")

    dec = await call_contract(TOKEN_ADDRESS, "decimals")
    decimals = int(dec[0]) if dec else 18
    amount_wei = int(float(amount) * (10 ** decimals))
    low = amount_wei & ((1 << 128) - 1)
    high = amount_wei >> 128

    try:
        to_int = int(address, 16)
    except Exception:
        raise HTTPException(status_code=400, detail="Dirección inválida (0x...)")

    tx = Call(to_addr=TOKEN_ADDRESS, selector=get_selector_from_name("mint"), calldata=[to_int, low, high])
    tx_hash = await send_calls([tx])
    return {"tx_hash": tx_hash}

@app.post("/set_price")
async def api_set_price(body: dict = Body(...)):
    # el front envía { "price_AIC": number }
    price = body.get("price_AIC")
    if price is None:
        raise HTTPException(status_code=400, detail="Falta price_AIC")

    dec = await call_contract(TOKEN_ADDRESS, "decimals")
    decimals = int(dec[0]) if dec else 18
    price_wei = int(float(price) * (10 ** decimals))
    low = price_wei & ((1 << 128) - 1)
    high = price_wei >> 128

    tx = Call(
        to_addr=USAGE_MANAGER_ADDRESS,
        selector=get_selector_from_name("set_price_per_unit_wei"),
        calldata=[low, high],
    )
    tx_hash = await send_calls([tx])
    return {"tx_hash": tx_hash}

@app.post("/set_free_quota")
async def api_set_free_quota(body: dict = Body(...)):
    new_quota = body.get("new_quota")
    if new_quota is None:
        raise HTTPException(status_code=400, detail="Falta new_quota")

    tx = Call(
        to_addr=USAGE_MANAGER_ADDRESS,
        selector=get_selector_from_name("set_free_quota_per_epoch"),
        calldata=[int(new_quota)],
    )
    tx_hash = await send_calls([tx])
    return {"tx_hash": tx_hash}
