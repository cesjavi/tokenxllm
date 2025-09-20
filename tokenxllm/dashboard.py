# Backend: FastAPI (main.py)
# ----------------------------------------------
# Place this file at: backend/main.py

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os, json, asyncio
from decimal import Decimal, getcontext
from dotenv import load_dotenv

from starknet_py.net.full_node_client import FullNodeClient
from starknet_py.net.client_models import Call
from starknet_py.net.account.account import Account
from starknet_py.net.signer.stark_curve_signer import KeyPair
from starknet_py.hash.selector import get_selector_from_name

getcontext().prec = 80

app = FastAPI(title="tokenxllm API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"]
    ,allow_headers=["*"]
)

# ---------- Utils ----------

def _h(x: str) -> int:
    x = x.strip()
    return int(x, 16) if x.startswith("0x") else int(x)

def _to_u256(n: int) -> tuple[int, int]:
    return n & ((1 << 128) - 1), n >> 128

def _from_u256(low: int, high: int) -> int:
    return (high << 128) + low

async def _load_client_and_account():
    load_dotenv()
    rpc = os.environ["RPC_URL"]
    aic = os.environ["AIC_ADDR"]
    um  = os.environ["UM_ADDR"]

    client = FullNodeClient(node_url=rpc)
    chain_id = await client.get_chain_id()

    # read from accounts file if PRIVATE_KEY not set
    private_key = os.getenv("PRIVATE_KEY")
    account_addr = os.getenv("ACCOUNT_ADDRESS")
    if (not private_key) or ("<" in private_key) or (private_key == "0x"):
        path = os.getenv("ACCOUNTS_FILE") or os.path.expanduser("~/.starknet_accounts/starknet_open_zeppelin_accounts.json")
        name = os.getenv("ACCOUNT_NAME") or "dev"
        with open(path, "r") as f:
            data = json.load(f)
        acct = None
        for net_key in ("alpha-sepolia","sepolia","SN_SEPOLIA","Sepolia"):
            if isinstance(data.get(net_key), dict) and isinstance(data[net_key].get(name), dict):
                acct = data[net_key][name]
                break
        if not acct:
            raise RuntimeError("Account not found in accounts file")
        private_key = acct.get("private_key") or acct.get("privateKey")
        account_addr = acct.get("address") or acct.get("account_address")

    key_pair = KeyPair.from_private_key(_h(private_key))
    account = Account(client=client, address=_h(account_addr), key_pair=key_pair, chain=chain_id)
    return client, account, aic, um

async def _call_u256(client: FullNodeClient, addr_hex: str, fn: str, calldata: list[int]) -> int:
    call = Call(to_addr=_h(addr_hex), selector=get_selector_from_name(fn), calldata=calldata)
    res = await client.call_contract(call)
    if len(res) != 2:
        raise RuntimeError(f"{fn} returned {len(res)} felts, expected 2")
    return _from_u256(res[0], res[1])

async def _call_u64(client: FullNodeClient, addr_hex: str, fn: str, calldata: list[int]) -> int:
    call = Call(to_addr=_h(addr_hex), selector=get_selector_from_name(fn), calldata=calldata)
    res = await client.call_contract(call)
    if len(res) != 1:
        raise RuntimeError(f"{fn} returned {len(res)} felts, expected 1")
    return res[0]

async def _invoke(account: Account, to_addr_hex: str, fn: str, calldata: list[int]) -> str:
    call = Call(to_addr=_h(to_addr_hex), selector=get_selector_from_name(fn), calldata=calldata)
    if hasattr(account, "execute_v3"):
        tx = await account.execute_v3(calls=[call], auto_estimate=True)
    else:
        tx = await account.execute(calls=[call], version=3, auto_estimate=True)
    await account.client.wait_for_tx(tx.transaction_hash)
    return hex(tx.transaction_hash)

# ---------- Schemas ----------
class ApproveIn(BaseModel):
    amount: Decimal
class AuthorizeIn(BaseModel):
    units: int
class MintIn(BaseModel):
    amount: Decimal
    to: str | None = None

# ---------- Endpoints ----------
@app.get("/api/status")
async def status():
    client, account, aic, um = await _load_client_and_account()
    owner_hex = os.getenv("ACCOUNT_ADDRESS")
    if not owner_hex:
        # recover owner from accounts file
        path = os.getenv("ACCOUNTS_FILE") or os.path.expanduser("~/.starknet_accounts/starknet_open_zeppelin_accounts.json")
        name = os.getenv("ACCOUNT_NAME") or "dev"
        with open(path, "r") as f:
            data = json.load(f)
        owner_hex = (data.get("alpha-sepolia",{}).get(name,{}).get("address")
                     or data.get("sepolia",{}).get(name,{}).get("address"))
    owner = _h(owner_hex)

    balance = await _call_u256(client, aic, "balance_of", [owner])
    allowance = await _call_u256(client, aic, "allowance", [owner, _h(um)])
    used = await _call_u64(client, um, "used_in_current_epoch", [owner])
    epoch = await _call_u64(client, um, "get_epoch_id", [])

    return {
        "owner": owner_hex,
        "aic": aic,
        "um": um,
        "balance_wei": str(balance),
        "balance": str(Decimal(balance) / (Decimal(10) ** 18)),
        "allowance_wei": str(allowance),
        "allowance": str(Decimal(allowance) / (Decimal(10) ** 18)),
        "used_units": used,
        "epoch_id": epoch,
    }

@app.post("/api/approve")
async def approve(body: ApproveIn):
    client, account, aic, um = await _load_client_and_account()
    amt_wei = int(body.amount * (10 ** 18))
    low, high = _to_u256(amt_wei)
    txh = await _invoke(account, aic, "approve", [_h(um), low, high])
    return {"tx_hash": txh}

@app.post("/api/authorize")
async def authorize(body: AuthorizeIn):
    client, account, aic, um = await _load_client_and_account()
    txh = await _invoke(account, um, "authorize_usage", [int(body.units)])
    return {"tx_hash": txh}

@app.post("/api/mint")
async def mint(body: MintIn):
    client, account, aic, um = await _load_client_and_account()
    to_hex = body.to or os.getenv("ACCOUNT_ADDRESS")
    if not to_hex:
        raise HTTPException(status_code=400, detail="Missing 'to' and ACCOUNT_ADDRESS not set")
    amt_wei = int(body.amount * (10 ** 18)); low, high = _to_u256(amt_wei)
    txh = await _invoke(account, aic, "mint", [_h(to_hex), low, high])
    return {"tx_hash": txh}

# Run: uvicorn main:app --reload --port 8000


# Backend .env (backend/.env)
# ----------------------------------------------
# RPC_URL=https://starknet-sepolia.public.blastapi.io/rpc/v0_9
# AIC_ADDR=0x06ddaf09636ceb526485c55b93c48c70f2a1728ad223743aaf08c21362ae7d9e
# UM_ADDR=0x04515dc0c7ccb8c2816cd95ca16db10eb3c8071dafea05414fd078c4dc41473a
# ACCOUNT_NAME=dev
# ACCOUNTS_FILE=/home/cesar/.starknet_accounts/starknet_open_zeppelin_accounts.json
# # Optional (if you want to override):
# # PRIVATE_KEY=0x...
# # ACCOUNT_ADDRESS=0x...


# Backend requirements.txt
# ----------------------------------------------
# fastapi
# uvicorn
# python-dotenv
# starknet-py
# pydantic


# Frontend: Vite + React + Tailwind (src/App.tsx)
# ----------------------------------------------
# Create a Vite app (React + TS), then replace src/App.tsx and src/index.css as below.
# Also set VITE_API_BASE in frontend/.env to point to backend (e.g., http://localhost:8000)

import React, { useEffect, useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

type Status = {
  owner: string;
  aic: string;
  um: string;
  balance_wei: string;
  balance: string;
  allowance_wei: string;
  allowance: string;
  used_units: number;
  epoch_id: number;
};

export default function App() {
  const [status, setStatus] = useState<Status | null>(null);
  const [loading, setLoading] = useState(false);
  const [amount, setAmount] = useState("100");
  const [units, setUnits] = useState("1000");
  const [tx, setTx] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function fetchStatus() {
    try {
      setLoading(true);
      const r = await fetch(`${API_BASE}/api/status`);
      const j = await r.json();
      setStatus(j);
    } catch (e: any) {
      setErr(e.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  async function postJSON(path: string, body: any) {
    setErr(null); setTx(null);
    const r = await fetch(`${API_BASE}${path}`, { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify(body)});
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    return r.json();
  }

  async function doApprove() {
    try {
      const j = await postJSON("/api/approve", { amount: Number(amount) });
      setTx(j.tx_hash); await fetchStatus();
    } catch (e: any) { setErr(e.message || String(e)); }
  }

  async function doAuthorize() {
    try {
      const j = await postJSON("/api/authorize", { units: Number(units) });
      setTx(j.tx_hash); await fetchStatus();
    } catch (e: any) { setErr(e.message || String(e)); }
  }

  useEffect(() => { fetchStatus(); const t = setInterval(fetchStatus, 10000); return () => clearInterval(t); }, []);

  return (
    <div className="min-h-screen bg-gray-50 text-gray-900 p-6">
      <div className="max-w-5xl mx-auto">
        <h1 className="text-3xl font-bold mb-6">tokenxllm Monitor</h1>

        {err && (
          <div className="mb-4 p-3 rounded-lg bg-red-100 text-red-800">{err}</div>
        )}
        {tx && (
          <div className="mb-4 p-3 rounded-lg bg-green-100 text-green-800">
            Tx sent: <a className="underline" href={`https://sepolia.starkscan.co/tx/${tx}`} target="_blank" rel="noreferrer">{tx}</a>
          </div>
        )}

        <div className="grid gap-4 grid-cols-1 md:grid-cols-2">
          <Card title="Owner">
            <Mono>{status?.owner}</Mono>
          </Card>
          <Card title="Epoch">
            <div className="text-3xl font-semibold">{status?.epoch_id ?? "-"}</div>
          </Card>
          <Card title="AIC Balance">
            <div className="text-3xl font-semibold">{loading?"…":(status?.balance ?? "-")}</div>
            <div className="text-xs text-gray-500">wei: {status?.balance_wei}</div>
          </Card>
          <Card title="Allowance to UM">
            <div className="text-3xl font-semibold">{loading?"…":(status?.allowance ?? "-")}</div>
            <div className="text-xs text-gray-500">wei: {status?.allowance_wei}</div>
          </Card>
          <Card title="Used units (current epoch)">
            <div className="text-3xl font-semibold">{status?.used_units ?? "-"}</div>
          </Card>
          <Card title="Contracts">
            <div className="text-sm">AIC: <Mono>{status?.aic}</Mono></div>
            <div className="text-sm">UM: <Mono>{status?.um}</Mono></div>
          </Card>
        </div>

        <div className="mt-8 grid gap-4 grid-cols-1 md:grid-cols-2">
          <ActionCard title="Approve">
            <label className="text-sm">Amount (AIC)</label>
            <input value={amount} onChange={e=>setAmount(e.target.value)} className="mt-1 w-full border rounded-lg p-2" />
            <button onClick={doApprove} className="mt-3 px-4 py-2 rounded-xl bg-black text-white">Approve</button>
          </ActionCard>
          <ActionCard title="Authorize Usage">
            <label className="text-sm">Units</label>
            <input value={units} onChange={e=>setUnits(e.target.value)} className="mt-1 w-full border rounded-lg p-2" />
            <button onClick={doAuthorize} className="mt-3 px-4 py-2 rounded-xl bg-black text-white">Authorize</button>
          </ActionCard>
        </div>
      </div>
    </div>
  );
}

function Card({title, children}:{title:string, children:React.ReactNode}){
  return (
    <div className="bg-white rounded-2xl shadow p-4">
      <div className="text-xs uppercase tracking-wide text-gray-500 mb-2">{title}</div>
      {children}
    </div>
  );
}
function ActionCard({title, children}:{title:string, children:React.ReactNode}){
  return (
    <div className="bg-white rounded-2xl shadow p-4">
      <div className="text-sm font-semibold mb-3">{title}</div>
      {children}
    </div>
  );
}
function Mono({children}:{children:React.ReactNode}){
  return <span className="font-mono break-all">{children}</span>;
}


# Frontend Tailwind setup
# ----------------------------------------------
# 1) npm create vite@latest tokenxllm-web -- --template react-ts
# 2) cd tokenxllm-web && npm i && npm i -D tailwindcss postcss autoprefixer && npx tailwindcss init -p
# 3) tailwind.config.js ->
#   export default {
#     content: ["./index.html","./src/**/*.{ts,tsx}"],
#     theme: { extend: {} },
#     plugins: [],
#   }
# 4) src/index.css ->
#   @tailwind base; @tailwind components; @tailwind utilities;
# 5) src/App.tsx -> (replace with file above)
# 6) .env -> VITE_API_BASE=http://localhost:8000
# 7) npm run dev


# How to run (WSL)
# ----------------------------------------------
# Backend
#   cd backend
#   python -m venv venv && source venv/bin/activate
#   pip install -r requirements.txt
#   cp .env.example .env   # or create .env using values above
#   uvicorn main:app --reload --port 8000
# Frontend
#   cd tokenxllm-web
#   npm run dev
