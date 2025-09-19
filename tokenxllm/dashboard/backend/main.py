import asyncio
import json
import os
from decimal import Decimal, InvalidOperation, getcontext
from functools import lru_cache
from typing import Any

from fastapi import FastAPI, HTTPException
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# starknet_py: sólo lo usamos para lecturas (RPC)
from starknet_py.net.full_node_client import FullNodeClient  # type: ignore
try:
    from starknet_py.net.client_models import Call  # type: ignore
except Exception:
    from starknet_py.net.models import Call  # type: ignore
from starknet_py.net.account.account import Account  # type: ignore
from starknet_py.net.signer.stark_curve_signer import KeyPair  # type: ignore
from starknet_py.hash.selector import get_selector_from_name  # type: ignore

load_dotenv()

getcontext().prec = 80

RPC_URL    = os.getenv("RPC_URL", "https://starknet-sepolia.public.blastapi.io/rpc/v0_9")
AIC_ADDR_H = os.getenv("AIC_ADDR", "").strip()
UM_ADDR_H  = os.getenv("UM_ADDR", "").strip()
DECIMALS   = int(os.getenv("AIC_DECIMALS", "18"))
DEFAULT_ACCOUNTS_FILE = os.path.expanduser("~/.starknet_accounts/starknet_open_zeppelin_accounts.json")

_RPC_CLIENT: FullNodeClient | None = None
_ACCOUNT: Account | None = None
_ACCOUNT_LOCK = asyncio.Lock()

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
    except FileNotFoundError:
        return None, None
    except json.JSONDecodeError:
        return None, None

    for net_key in ("alpha-sepolia", "sepolia", "SN_SEPOLIA", "Sepolia"):
        entry = data.get(net_key)
        if isinstance(entry, dict):
            acct = entry.get(name)
            if isinstance(acct, dict):
                priv = acct.get("private_key") or acct.get("privateKey")
                addr = acct.get("address") or acct.get("account_address")
                if priv and addr:
                    return str(priv), str(addr)

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
    if result:
        return result
    return None, None

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

    return {
        "private_key": priv_int,
        "address": addr_int,
        "address_hex": _as_hex(addr_int),
    }

def _writes_enabled() -> bool:
    return _signer_credentials() is not None

def _account_address_hex() -> str | None:
    creds = _signer_credentials()
    return creds.get("address_hex") if creds else None

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
        try:
            chain_id = await client.get_chain_id()
        except Exception as exc:  # pragma: no cover - network failure
            raise HTTPException(status_code=502, detail=f"Failed to fetch chain id: {exc}") from exc

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
    except InvalidOperation as exc:  # pragma: no cover - invalid decimal arithmetic
        raise HTTPException(status_code=400, detail=f"Invalid decimal amount: {exc}") from exc
    return int(scaled)

async def _invoke(to_addr_hex: str, fn: str, calldata: list[int]) -> str:
    account = await _get_account()
    call = Call(to_addr=_h(to_addr_hex), selector=get_selector_from_name(fn), calldata=calldata)
    try:
        if hasattr(account, "execute_v3"):
            tx = await account.execute_v3(calls=[call], auto_estimate=True)
        else:
            tx = await account.execute(calls=[call], auto_estimate=True)
    except Exception as exc:  # pragma: no cover - provider/account failure
        raise HTTPException(status_code=502, detail=f"Failed to submit transaction: {exc}") from exc

    tx_hash = getattr(tx, "hash", None) or getattr(tx, "transaction_hash", None)
    if isinstance(tx_hash, int):
        return hex(tx_hash)
    return str(tx_hash)

async def _read(addr_hex: str, fn: str, calldata: list[int]) -> list[int]:
    cli = _rpc_client()
    call = Call(to_addr=_h(addr_hex), selector=get_selector_from_name(fn), calldata=calldata)
    try:
        return await cli.call_contract(call=call, block_number="latest")
    except TypeError:
        return await cli.call_contract(call=call)

def _require_env_addr(v: str, name: str) -> str:
    if not v:
        raise HTTPException(status_code=400, detail=f"{name} not configured")
    return v

app = FastAPI(title="tokenxllm backend", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5500", "http://127.0.0.1:5500", "null", "*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
)

class ApproveRequest(BaseModel):
    amount: Decimal = Field(..., gt=0)
    spender: str | None = None


class AuthorizeRequest(BaseModel):
    units: int = Field(..., gt=0)


class MintRequest(BaseModel):
    to: str = Field(..., min_length=1)
    amount: Decimal = Field(..., gt=0)


@app.get("/health")
async def health():
    return {"ok": True}

@app.get("/config")
async def config():
    return {
        "rpc_url": RPC_URL,
        "aic_addr": AIC_ADDR_H or None,
        "um_addr": UM_ADDR_H or None,
        "decimals": DECIMALS,
        "writes_enabled": _writes_enabled(),
        "account_address": _account_address_hex(),
    }

@app.get("/balance")
async def balance(user: str):
    aic = _require_env_addr(AIC_ADDR_H, "AIC_ADDR")
    lo, hi = (await _read(aic, "balance_of", [_h(user)]) + [0, 0])[:2]
    wei = _from_u256(lo, hi)
    return {"balance_wei": str(wei), "balance_AIC": float(wei) / (10 ** DECIMALS)}

@app.get("/allowance")
async def allowance(owner: str, spender: str):
    aic = _require_env_addr(AIC_ADDR_H, "AIC_ADDR")
    lo, hi = (await _read(aic, "allowance", [_h(owner), _h(spender)]) + [0, 0])[:2]
    wei = _from_u256(lo, hi)
    return {"allowance_wei": str(wei), "allowance_AIC": float(wei) / (10 ** DECIMALS)}

@app.get("/used")
async def used(user: str):
    um = _require_env_addr(UM_ADDR_H, "UM_ADDR")
    (val,) = (await _read(um, "used_in_current_epoch", [_h(user)]) + [0])[:1]
    return {"used_units": int(val)}

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
    low, high = _to_u256(amount_wei)
    tx_hash = await _invoke(aic, "approve", [_h(spender_hex), low, high])
    return {"tx_hash": tx_hash}


@app.post("/authorize")
async def authorize(body: AuthorizeRequest):
    um = _require_env_addr(UM_ADDR_H, "UM_ADDR")
    tx_hash = await _invoke(um, "authorize_usage", [int(body.units)])
    return {"tx_hash": tx_hash}


@app.post("/mint")
async def mint(body: MintRequest):
    aic = _require_env_addr(AIC_ADDR_H, "AIC_ADDR")
    amount_wei = _tokens_to_wei(body.amount, DECIMALS)
    low, high = _to_u256(amount_wei)
    tx_hash = await _invoke(aic, "mint", [_h(body.to), low, high])
    return {"tx_hash": tx_hash}
