import os
from fastapi import FastAPI, HTTPException
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware

# starknet_py: sólo lo usamos para lecturas (RPC)
from starknet_py.net.full_node_client import FullNodeClient  # type: ignore
try:
    from starknet_py.net.client_models import Call  # type: ignore
except Exception:
    from starknet_py.net.models import Call  # type: ignore
from starknet_py.hash.selector import get_selector_from_name  # type: ignore

load_dotenv()

RPC_URL    = os.getenv("RPC_URL", "https://starknet-sepolia.public.blastapi.io/rpc/v0_9")
AIC_ADDR_H = os.getenv("AIC_ADDR", "").strip()
UM_ADDR_H  = os.getenv("UM_ADDR", "").strip()
DECIMALS   = int(os.getenv("AIC_DECIMALS", "18"))

def _h(x: str | int) -> int:
    if isinstance(x, int):
        return x
    s = str(x).strip()
    return int(s, 16) if s.startswith("0x") else int(s)

def _from_u256(lo: int, hi: int) -> int:
    return (hi << 128) + lo

def _rpc_client() -> FullNodeClient:
    return FullNodeClient(node_url=RPC_URL)

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
        "writes_enabled": False,
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
