import os, re, subprocess
from typing import Any
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
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

# Para invocar con sncast
SNCAST_BIN   = os.getenv("SNCAST_BIN", "sncast")
SNCAST_ACCT  = os.getenv("SNCAST_ACCOUNT", "dev")
SNCAST_FILE  = os.getenv("SNCAST_ACCOUNTS_FILE", os.path.expanduser("~/.starknet_accounts/starknet_open_zeppelin_accounts.json"))

def _h(x: str | int) -> int:
    if isinstance(x, int): return x
    s = str(x).strip()
    return int(s, 16) if s.startswith("0x") else int(s)

def _to_u256(n: int) -> tuple[int,int]:
    return (n & ((1<<128)-1), n >> 128)

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

def _sncast_invoke(contract_addr_hex: str, fn: str, raw_calldata: list[str]) -> str:
    args = [
        SNCAST_BIN,
        "--account", SNCAST_ACCT,
        "--accounts-file", SNCAST_FILE,
        "invoke",
        "--url", RPC_URL,
        "--contract-address", contract_addr_hex,
        "--function", fn,
        "--calldata", *raw_calldata,
    ]
    proc = subprocess.run(args, capture_output=True, text=True)
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    if proc.returncode != 0:
        raise HTTPException(status_code=500, detail=f"sncast invoke failed: {out.strip()[:800]}")
    m = re.search(r"(?:Transaction Hash|transaction_hash)\s*:\s*(0x[0-9a-fA-F]+)", out)
    if not m:
        raise HTTPException(status_code=500, detail=f"tx hash not found in sncast output: {out.strip()[:800]}")
    return m.group(1)

app = FastAPI(title="tokenxllm backend", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5500","http://127.0.0.1:5500","null","*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
)

class Approve(BaseModel):
    amount: float

class Authorize(BaseModel):
    units: int

class Mint(BaseModel):
    to: str
    amount: float

@app.get("/health")
async def health(): return {"ok": True}

@app.get("/config")
async def config():
    return {
        "rpc_url": RPC_URL,
        "aic_addr": AIC_ADDR_H or None,
        "um_addr":  UM_ADDR_H  or None,
        "decimals": DECIMALS,
        "writes_enabled": bool(SNCAST_ACCT and SNCAST_FILE),
    }

@app.get("/balance")
async def balance(user: str):
    aic = _require_env_addr(AIC_ADDR_H, "AIC_ADDR")
    lo, hi = (await _read(aic, "balance_of", [_h(user)]) + [0,0])[:2]
    wei = _from_u256(lo, hi)
    return {"balance_wei": str(wei), "balance_AIC": float(wei)/(10**DECIMALS)}

@app.get("/allowance")
async def allowance(owner: str, spender: str):
    aic = _require_env_addr(AIC_ADDR_H, "AIC_ADDR")
    lo, hi = (await _read(aic, "allowance", [_h(owner), _h(spender)]) + [0,0])[:2]
    wei = _from_u256(lo, hi)
    return {"allowance_wei": str(wei), "allowance_AIC": float(wei)/(10**DECIMALS)}

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
async def approve(body: Approve):
    aic = _require_env_addr(AIC_ADDR_H, "AIC_ADDR")
    um  = _require_env_addr(UM_ADDR_H,  "UM_ADDR")
    amount_wei = int(body.amount * (10**DECIMALS))
    lo, hi = _to_u256(amount_wei)
    txh = _sncast_invoke(aic, "approve", [um, str(lo), str(hi)])
    return {"tx_hash": txh}

@app.post("/authorize")
async def authorize(body: Authorize):
    um = _require_env_addr(UM_ADDR_H, "UM_ADDR")
    txh = _sncast_invoke(um, "authorize_usage", [str(int(body.units))])
    return {"tx_hash": txh}

@app.post("/mint")
async def mint(body: Mint):
    aic = _require_env_addr(AIC_ADDR_H, "AIC_ADDR")
    amount_wei = int(body.amount * (10**DECIMALS))
    lo, hi = _to_u256(amount_wei)
    txh = _sncast_invoke(aic, "mint", [body.to, str(lo), str(hi)])
    return {"tx_hash": txh}
#0x522570db5197d282febafea3538ff2deacfaf49ec85a86e30bbe45af6f7c90