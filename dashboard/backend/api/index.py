from __future__ import annotations

import asyncio
import json
import os
import time
from decimal import Decimal, InvalidOperation, getcontext
from functools import lru_cache
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# starknet_py xxx
from starknet_py.net.full_node_client import FullNodeClient  # type: ignore
try:
    from starknet_py.net.client_models import Call  # type: ignore
except Exception:
    from starknet_py.net.models import Call  # type: ignore
from starknet_py.net.account.account import Account  # type: ignore
from starknet_py.net.signer.stark_curve_signer import KeyPair  # type: ignore
from starknet_py.hash.selector import get_selector_from_name  # type: ignore
from starknet_py.hash.storage import get_storage_var_address  # type: ignore

load_dotenv()
getcontext().prec = 80

RPC_URL    = os.getenv("RPC_URL", "https://starknet-sepolia.public.blastapi.io/rpc/v0_9")
AIC_ADDR_H = (os.getenv("AIC_ADDR") or "").strip()
UM_ADDR_H  = (os.getenv("UM_ADDR")  or "").strip()
DECIMALS   = int(os.getenv("AIC_DECIMALS", "18"))


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_decimal(name: str, default: Decimal) -> Decimal:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return Decimal(raw.strip())
    except InvalidOperation:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw.strip())
    except ValueError:
        return default


FAUCET_ENABLED = _env_bool("FAUCET_ENABLED", False)
FAUCET_AMOUNT_AIC = _env_decimal("FAUCET_AMOUNT_AIC", Decimal("50"))
FAUCET_COOLDOWN_SECONDS = max(_env_int("FAUCET_COOLDOWN_SECONDS", 86_400), 0)


DEFAULT_ACCOUNTS_FILE = os.path.expanduser("~/.starknet_accounts/starknet_open_zeppelin_accounts.json")

_RPC_CLIENT: FullNodeClient | None = None
_ACCOUNT: Account | None = None
_ACCOUNT_LOCK = asyncio.Lock()

_FAUCET_LAST_CLAIMS: dict[str, float] = {}
_FAUCET_LOCK = asyncio.Lock()

# Storage slots (compatibles con tu contrato original)
_FREE_QUOTA_KEY = get_storage_var_address("UsageManager_free_quota_per_epoch")
_PRICE_PER_UNIT_BASE_KEY = get_storage_var_address("UsageManager_price_per_unit_wei")

# -------------------- utils --------------------


def _current_timestamp() -> float:
    return time.time()


def _h(x: str | int) -> int:
    if isinstance(x, int):
        return x
    s = str(x).strip()
    return int(s, 16) if s.startswith("0x") else int(s)

def _from_u256(lo: int, hi: int) -> int:
    return (hi << 128) + lo

def _to_u256(value: int) -> tuple[int, int]:
    low = value & ((1 << 128) - 1)
    high = value >> 128
    return low, high

def _as_hex(value: int) -> str:
    return hex(value)

def _rpc_client() -> FullNodeClient:
    global _RPC_CLIENT
    if _RPC_CLIENT is None:
        _RPC_CLIENT = FullNodeClient(node_url=RPC_URL)
    return _RPC_CLIENT

def _clean_str(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None

def _load_from_accounts_file() -> tuple[str | None, str | None]:
    path = _clean_str(os.getenv("ACCOUNTS_FILE")) or DEFAULT_ACCOUNTS_FILE
    name = _clean_str(os.getenv("ACCOUNT_NAME")) or "dev"
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None, None

    for net_key in ("alpha-sepolia", "sepolia", "SN_SEPOLIA", "Sepolia"):
        entry = data.get(net_key) if isinstance(data, dict) else None
        if isinstance(entry, dict):
            acct = entry.get(name)
            if isinstance(acct, dict):
                priv = acct.get("private_key") or acct.get("privateKey")
                addr = acct.get("address") or acct.get("account_address")
                if priv and addr:
                    return str(priv), str(addr)

    # búsqueda profunda por si el json tiene otra forma
    def find_account(obj: Any) -> tuple[str | None, str | None] | None:
        if isinstance(obj, dict):
            lowered = {k.lower(): k for k in obj.keys()}
            if any(k in lowered for k in ("private_key", "privatekey")) and "address" in lowered:
                priv_key = obj.get(lowered.get("private_key") or lowered.get("privatekey"))
                addr_val = obj.get(lowered["address"])
                if priv_key and addr_val:
                    return str(priv_key), str(addr_val)
            for val in obj.values():
                found = find_account(val)
                if found:
                    return found
        elif isinstance(obj, list):
            for item in obj:
                found = find_account(item)
                if found:
                    return found
        return None

    result = find_account(data)
    return result if result else (None, None)


def _split_env_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]

@lru_cache(maxsize=1)
def _signer_credentials() -> dict[str, Any] | None:
    priv = _clean_str(os.getenv("PRIVATE_KEY"))
    addr = _clean_str(os.getenv("ACCOUNT_ADDRESS"))
    if priv and "<" in priv:
        priv = None

    if not priv or not addr:
        priv_file, addr_file = _load_from_accounts_file()
        priv = priv or priv_file
        addr = addr or addr_file

    if not priv or not addr:
        return None

    try:
        priv_int = _h(priv)
        addr_int = _h(addr)
    except ValueError:
        return None

    return {"private_key": priv_int, "address": addr_int, "address_hex": _as_hex(addr_int)}

def _writes_enabled() -> bool:
    return _signer_credentials() is not None

def _account_address_hex() -> str | None:
    creds = _signer_credentials()
    return creds.get("address_hex") if creds else None

# -------------------- starknet helpers --------------------
async def _get_storage_value(addr_hex: str, key: int) -> int:
    cli = _rpc_client()
    contract_address = _h(addr_hex)
    try:
        value = await cli.get_storage_at(
            contract_address=contract_address, key=key, block_number="latest"
        )
    except TypeError:
        value = await cli.get_storage_at(contract_address=contract_address, key=key)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"get_storage_at failed: {type(exc).__name__}: {exc!r}"
        ) from exc

    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return _h(value)
    raise HTTPException(status_code=502, detail="Unsupported storage value type")


async def _read(addr_hex: str, fn: str, calldata: list[int]) -> list[int]:
    cli = _rpc_client()
    call = Call(to_addr=_h(addr_hex), selector=get_selector_from_name(fn), calldata=calldata)
    try:
        return await cli.call_contract(call=call, block_id="latest")
    except TypeError:
        return await cli.call_contract(call=call)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"call_contract failed: {type(exc).__name__}: {exc!r}"
        ) from exc



async def _read_free_quota(addr_hex: str) -> int:
    return await _get_storage_value(addr_hex, _FREE_QUOTA_KEY)

async def _read_price_per_unit(addr_hex: str) -> int:
    low = await _get_storage_value(addr_hex, _PRICE_PER_UNIT_BASE_KEY)
    high = await _get_storage_value(addr_hex, _PRICE_PER_UNIT_BASE_KEY + 1)
    return _from_u256(low, high)

async def _get_account() -> Account:
    creds = _signer_credentials()
    if not creds:
        raise HTTPException(status_code=400, detail="Writes are not configured on the backend")

    global _ACCOUNT
    if _ACCOUNT and _ACCOUNT.address == creds["address"]:
        return _ACCOUNT

    async with _ACCOUNT_LOCK:
        if _ACCOUNT and _ACCOUNT.address == creds["address"]:
            return _ACCOUNT
        client = _rpc_client()
        chain_id = await client.get_chain_id()
        key_pair = KeyPair.from_private_key(creds["private_key"])
        _ACCOUNT = Account(client=client, address=creds["address"], key_pair=key_pair, chain=chain_id)
        return _ACCOUNT

def _tokens_to_wei(amount: Decimal, decimals: int = DECIMALS) -> int:
    scale = Decimal(10) ** decimals
    try:
        scaled = amount * scale
        if scaled % 1 != 0:
            raise HTTPException(
                status_code=400,
                detail=f"Amount has more precision than supported ({decimals} decimals)",
            )
    except InvalidOperation as exc:
        raise HTTPException(status_code=400, detail=f"Invalid decimal amount: {exc}") from exc
    return int(scaled)


def _wei_to_tokens_str(amount_wei: int, decimals: int = DECIMALS) -> str:
    if decimals <= 0:
        return format(Decimal(amount_wei), "f")

    scale = Decimal(10) ** decimals
    decimal_value = Decimal(amount_wei) / scale
    return format(decimal_value, "f")


def _format_decimal(amount: Decimal) -> str:
    return format(amount, "f")


def _safe_faucet_amount_wei() -> int:
    try:
        return _tokens_to_wei(FAUCET_AMOUNT_AIC, DECIMALS)
    except HTTPException:
        return 0


def _normalize_faucet_key(value: str) -> str:
    return value.strip().lower()


async def _invoke(to_addr_hex: str, fn: str, calldata: list[int]) -> str:
    account = await _get_account()
    call = Call(to_addr=_h(to_addr_hex), selector=get_selector_from_name(fn), calldata=calldata)
    try:
        if hasattr(account, "execute_v3"):
            tx = await account.execute_v3(calls=[call], auto_estimate=True)
        else:
            tx = await account.execute(calls=[call], version=3, auto_estimate=True)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to submit transaction: {exc!r}") from exc

    tx_hash = getattr(tx, "hash", None) or getattr(tx, "transaction_hash", None)
    return hex(tx_hash) if isinstance(tx_hash, int) else str(tx_hash)

def _require_env_addr(v: str, name: str) -> str:
    if not v:
        raise HTTPException(status_code=400, detail=f"{name} not configured")
    return v


async def _build_faucet_info(address: str | None = None) -> FaucetInfo:
    amount_wei = _safe_faucet_amount_wei()
    cooldown_seconds = max(int(FAUCET_COOLDOWN_SECONDS), 0)
    enabled = bool(FAUCET_ENABLED) and amount_wei > 0
    writes_enabled = _writes_enabled()
    seconds_remaining: int | None = None
    last_claim_timestamp: int | None = None

    if address:
        normalized = _normalize_faucet_key(address)
        async with _FAUCET_LOCK:
            last_claim = _FAUCET_LAST_CLAIMS.get(normalized)
        if last_claim is not None:
            last_claim_timestamp = int(last_claim)
            now = _current_timestamp()
            remaining = cooldown_seconds - (now - last_claim)
            if remaining > 0:
                seconds_remaining = int(remaining)
            else:
                seconds_remaining = 0

    return FaucetInfo(
        enabled=enabled,
        writes_enabled=writes_enabled,
        amount_AIC=_format_decimal(FAUCET_AMOUNT_AIC),
        amount_wei=str(amount_wei),
        cooldown_seconds=cooldown_seconds,
        seconds_remaining=seconds_remaining,
        last_claim_timestamp=last_claim_timestamp,
    )

# -------------------- FastAPI --------------------

_ALLOWED_ORIGINS = ["http://localhost:5173"]
for origin in _split_env_list(os.getenv("DASHBOARD_PUBLIC_URL")):
    if origin not in _ALLOWED_ORIGINS:
        _ALLOWED_ORIGINS.append(origin)

app = FastAPI(title="tokenxllm backend", version="0.2.0")
# Permitir localhost (Vite 5173) y los orígenes configurados en DASHBOARD_PUBLIC_URL
app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
class SetFreeQuotaBody(BaseModel):
    new_quota: int  # u64 en Cairo

class SetPriceBody(BaseModel):
    price_AIC: Decimal = Field(..., gt=0)  # precio por unidad en AIC

class ApproveRequest(BaseModel):
    amount: Decimal = Field(..., gt=0)
    spender: str | None = None

class AuthorizeRequest(BaseModel):
    units: int = Field(..., gt=0)

class MintRequest(BaseModel):
    to: str = Field(..., min_length=1)
    amount: Decimal = Field(..., gt=0)


class FaucetInfo(BaseModel):
    enabled: bool
    writes_enabled: bool
    amount_AIC: str
    amount_wei: str
    cooldown_seconds: int
    seconds_remaining: int | None = None
    last_claim_timestamp: int | None = None


class FaucetRequest(BaseModel):
    to: str = Field(..., min_length=1)
class SendRequest(BaseModel):
    to: str
    amount: Decimal  # en AIC
class AirdropRequest(BaseModel):
    to: str
    amount: Decimal  # en AIC (con DECIMALS)    
@app.get("/")
async def root():
    return {"message": "TokenXLLM Backend API", "version": "0.2.0", "status": "running"}
@app.post("/set_free_quota")
async def set_free_quota(body: SetFreeQuotaBody):
    um = _require_env_addr(UM_ADDR_H, "UM_ADDR")
    q = int(body.new_quota)
    if q < 0 or q > 2**64 - 1:
        raise HTTPException(status_code=400, detail="new_quota fuera de rango u64")
    tx_hash = await _invoke(um, "set_free_quota_per_epoch", [q])
    return {"tx_hash": tx_hash, "new_quota": q}

@app.post("/set_price")
async def set_price(body: SetPriceBody):
    um = _require_env_addr(UM_ADDR_H, "UM_ADDR")
    amount_wei = _tokens_to_wei(body.price_AIC, DECIMALS)  # p.ej. 0.01 -> 10^16 si 18 dec
    lo, hi = _to_u256(amount_wei)
    tx_hash = await _invoke(um, "set_price_per_unit_wei", [lo, hi])
    return {"tx_hash": tx_hash, "price_wei": str(amount_wei)}

@app.post("/airdrop")
async def airdrop(body: AirdropRequest):
    aic = _require_env_addr(AIC_ADDR_H, "AIC_ADDR")
    # convierte a u256 (wei con DECIMALS)
    amount_wei = _tokens_to_wei(body.amount, DECIMALS)
    lo, hi = _to_u256(amount_wei)
    # si sos owner, esto pasa; si no, revierte con 'OWNER'
    tx_hash = await _invoke(aic, "mint", [_h(body.to), lo, hi])
    return {"tx_hash": tx_hash}
  
@app.get("/health")
async def health():
    return {"ok": True}

@app.get("/config")
async def config():
    faucet_info = await _build_faucet_info()
    return {
        "rpc_url": RPC_URL,
        "aic_addr": AIC_ADDR_H or None,
        "um_addr": UM_ADDR_H or None,
        "decimals": DECIMALS,
        "writes_enabled": _writes_enabled(),
        "account_address": _account_address_hex(),
        "faucet": faucet_info.model_dump(),
    }

@app.get("/balance")
async def balance(user: str):
    aic = _require_env_addr(AIC_ADDR_H, "AIC_ADDR")
    lo, hi = (await _read(aic, "balance_of", [_h(user)]) + [0, 0])[:2]
    wei = _from_u256(lo, hi)
    return {
        "balance_wei": str(wei),
        "balance_AIC": _wei_to_tokens_str(wei, DECIMALS),
    }

@app.get("/allowance")
async def allowance(owner: str, spender: str):
    aic = _require_env_addr(AIC_ADDR_H, "AIC_ADDR")
    lo, hi = (await _read(aic, "allowance", [_h(owner), _h(spender)]) + [0, 0])[:2]
    wei = _from_u256(lo, hi)
    return {
        "allowance_wei": str(wei),
        "allowance_AIC": _wei_to_tokens_str(wei, DECIMALS),
    }

@app.get("/used")
async def used(user: str):
    um = _require_env_addr(UM_ADDR_H, "UM_ADDR")
    (val,) = (await _read(um, "used_in_current_epoch", [_h(user)]) + [0])[:1]
    return {"used_units": int(val)}

@app.get("/free_quota")
async def free_quota(user: str | None = None):
    um = _require_env_addr(UM_ADDR_H, "UM_ADDR")
    total = await _read_free_quota(um)
    price = await _read_price_per_unit(um)

    resp: dict[str, Any] = {
        "free_quota": int(total),
        "price_per_unit_wei": str(price),
    }
    if user:
        (used_val,) = (await _read(um, "used_in_current_epoch", [_h(user)]) + [0])[:1]
        used_units = int(used_val)
        remaining = max(int(total) - used_units, 0)
        resp.update({"user": user, "used_units": used_units, "free_remaining": remaining})
    return resp

@app.get("/epoch")
async def epoch():
    um = _require_env_addr(UM_ADDR_H, "UM_ADDR")
    (val,) = (await _read(um, "get_epoch_id", []) + [0])[:1]
    return {"epoch_id": int(val)}

@app.post("/approve")
async def approve(body: ApproveRequest):
    aic = _require_env_addr(AIC_ADDR_H, "AIC_ADDR")
    spender_hex = body.spender or _require_env_addr(UM_ADDR_H, "UM_ADDR")
    amount_wei = _tokens_to_wei(body.amount, DECIMALS)
    lo, hi = _to_u256(amount_wei)
    tx_hash = await _invoke(aic, "approve", [_h(spender_hex), lo, hi])
    return {"tx_hash": tx_hash}

@app.post("/authorize")
async def authorize(body: AuthorizeRequest):
    um = _require_env_addr(UM_ADDR_H, "UM_ADDR")
    units = int(body.units)
    # primero intentá felt
    try:
        return {"tx_hash": await _invoke(um, "authorize_usage", [units])}
    except HTTPException as e:
        # si fue ENTRYPOINT o calldata mismatch, probá u256
        if "ENTRYPOINT" in str(e.detail) or "calldata" in str(e.detail) or "invalid" in str(e.detail).lower():
            lo, hi = _to_u256(units)
            return {"tx_hash": await _invoke(um, "authorize_usage", [lo, hi])}
        raise


@app.post("/mint")
async def mint(body: MintRequest):
    aic = _require_env_addr(AIC_ADDR_H, "AIC_ADDR")
    amount_wei = _tokens_to_wei(body.amount, DECIMALS)
    lo, hi = _to_u256(amount_wei)
    tx_hash = await _invoke(aic, "mint", [_h(body.to), lo, hi])
    return {"tx_hash": tx_hash}


@app.get("/faucet", response_model=FaucetInfo)
async def faucet(address: str | None = None):
    return await _build_faucet_info(address)


@app.post("/faucet")
async def faucet_request(body: FaucetRequest):
    info = await _build_faucet_info(body.to)
    if not info.enabled:
        raise HTTPException(status_code=404, detail="Faucet is disabled")
    if not info.writes_enabled:
        raise HTTPException(status_code=400, detail="Writes are not configured on the backend")

    aic = _require_env_addr(AIC_ADDR_H, "AIC_ADDR")
    amount_wei = _safe_faucet_amount_wei()
    if amount_wei <= 0:
        raise HTTPException(status_code=400, detail="Faucet amount must be greater than zero")

    cooldown_seconds = info.cooldown_seconds
    now = _current_timestamp()
    normalized = _normalize_faucet_key(body.to)
    last_claim: float | None = None

    async with _FAUCET_LOCK:
        last_claim = _FAUCET_LAST_CLAIMS.get(normalized)
        if last_claim is not None:
            elapsed = now - last_claim
            if elapsed < cooldown_seconds:
                remaining = int(max(cooldown_seconds - elapsed, 0))
                raise HTTPException(
                    status_code=429,
                    detail={
                        "error": "Faucet cooldown active",
                        "seconds_remaining": remaining,
                    },
                )
        _FAUCET_LAST_CLAIMS[normalized] = now

    try:
        lo, hi = _to_u256(amount_wei)
        tx_hash = await _invoke(aic, "mint", [_h(body.to), lo, hi])
    except Exception:
        async with _FAUCET_LOCK:
            if last_claim is None:
                if _FAUCET_LAST_CLAIMS.get(normalized) == now:
                    _FAUCET_LAST_CLAIMS.pop(normalized, None)
            else:
                if _FAUCET_LAST_CLAIMS.get(normalized) == now:
                    _FAUCET_LAST_CLAIMS[normalized] = last_claim
        raise

    return {
        "tx_hash": tx_hash,
        "amount_AIC": _format_decimal(FAUCET_AMOUNT_AIC),
        "amount_wei": str(amount_wei),
        "cooldown_seconds": cooldown_seconds,
        "seconds_remaining": cooldown_seconds,
    }
