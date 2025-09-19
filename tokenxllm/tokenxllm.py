import os, argparse, asyncio, json
from decimal import Decimal, getcontext
from dotenv import load_dotenv

from starknet_py.net.full_node_client import FullNodeClient
from starknet_py.net.client_models import Call
from starknet_py.net.account.account import Account
from starknet_py.net.signer.stark_curve_signer import KeyPair
from starknet_py.hash.selector import get_selector_from_name

getcontext().prec = 80

def req(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Missing env var: {name}")
    return v

def h(x: str) -> int:
    x = x.strip()
    return int(x, 16) if x.startswith("0x") else int(x)

def to_u256(n: int) -> tuple[int, int]:
    return n & ((1 << 128) - 1), n >> 128

def from_u256(low: int, high: int) -> int:
    return (high << 128) + low

def tokens_to_wei(tokens: str | float | int, decimals: int = 18) -> int:
    d = Decimal(str(tokens)); scale = Decimal(10) ** decimals
    return int(d * scale)

def load_from_accounts_file():
    path = os.getenv("ACCOUNTS_FILE") or os.path.expanduser("~/.starknet_accounts/starknet_open_zeppelin_accounts.json")
    name = os.getenv("ACCOUNT_NAME") or "dev"
    if not os.path.exists(path):
        return None, None
    with open(path, "r") as f:
        data = json.load(f)

    # 1) forma típica: data["alpha-sepolia"][name]
    for net_key in ("alpha-sepolia", "sepolia", "SN_SEPOLIA", "Sepolia"):
        if isinstance(data.get(net_key), dict) and isinstance(data[net_key].get(name), dict):
            acct = data[net_key][name]
            priv = acct.get("private_key") or acct.get("privateKey")
            addr = acct.get("address") or acct.get("account_address")
            if priv and addr:
                return priv, addr

    # 2) buscar recursivamente un dict con private_key & address (fallback robusto)
    def find_account(obj):
        if isinstance(obj, dict):
            keys = {k.lower() for k in obj.keys()}
            if ("private_key" in keys or "privatekey" in keys) and "address" in keys:
                return obj
            for v in obj.values():
                r = find_account(v)
                if r: return r
        elif isinstance(obj, list):
            for v in obj:
                r = find_account(v)
                if r: return r
        return None

    acct = find_account(data)
    if acct:
        priv = acct.get("private_key") or acct.get("privateKey")
        addr = acct.get("address") or acct.get("account_address")
        return priv, addr
    return None, None

def make_client() -> FullNodeClient:
    load_dotenv()
    rpc = req("RPC_URL")
    return FullNodeClient(node_url=rpc)

def resolve_address(target_address: str | None, *, required: bool = True) -> str | None:
    load_dotenv()
    if target_address:
        return target_address

    addr_env = os.getenv("ACCOUNT_ADDRESS")
    if addr_env:
        return addr_env

    _, addr_file = load_from_accounts_file()
    if addr_file:
        return addr_file

    if required:
        raise RuntimeError("Falta ACCOUNT_ADDRESS (o no se pudo deducir del ACCOUNTS_FILE).")

    return None

async def make_client_and_account():
    client = make_client()
    chain_id = await client.get_chain_id()

    priv = os.getenv("PRIVATE_KEY")
    addr_env = os.getenv("ACCOUNT_ADDRESS")

    # Si falta PRIVATE_KEY o es placeholder, leemos de accounts file
    if (not priv) or ("<" in priv):
        priv_file, addr_file = load_from_accounts_file()
        if not priv_file:
            raise RuntimeError("No PRIVATE_KEY y no pude leer la clave del ACCOUNTS_FILE. Seteá PRIVATE_KEY o ACCOUNTS_FILE+ACCOUNT_NAME.")
        priv = priv_file
        if not addr_env and addr_file:
            addr_env = addr_file

    if not addr_env:
        raise RuntimeError("Falta ACCOUNT_ADDRESS (o no se pudo deducir del ACCOUNTS_FILE).")

    account_address = h(addr_env)
    private_key_int = h(priv)

    key_pair = KeyPair.from_private_key(private_key_int)
    account = Account(client=client, address=account_address, key_pair=key_pair, chain=chain_id)
    return client, account

async def call_u256(client: FullNodeClient, addr_hex: str, fn: str, calldata: list[int]) -> int:
    call = Call(to_addr=h(addr_hex), selector=get_selector_from_name(fn), calldata=calldata)
    res = await client.call_contract(call)
    if len(res) != 2:
        raise RuntimeError(f"{fn} returned {len(res)} felts, expected 2 for u256")
    return from_u256(res[0], res[1])

async def call_u64(client: FullNodeClient, addr_hex: str, fn: str, calldata: list[int]) -> int:
    call = Call(to_addr=h(addr_hex), selector=get_selector_from_name(fn), calldata=calldata)
    res = await client.call_contract(call)
    if len(res) != 1:
        raise RuntimeError(f"{fn} returned {len(res)} felts, expected 1")
    return res[0]

async def invoke(account: Account, to_addr_hex: str, fn: str, calldata: list[int]):
    call = Call(to_addr=h(to_addr_hex), selector=get_selector_from_name(fn), calldata=calldata)
    if hasattr(account, "execute_v3"):
        tx = await account.execute_v3(calls=[call], auto_estimate=True)
    else:
        tx = await account.execute(calls=[call], auto_estimate=True)
    await account.client.wait_for_tx(tx.transaction_hash)
    return tx.transaction_hash

async def do_balance(target_address: str | None):
    client = make_client()
    owner = resolve_address(target_address)
    aic = req("AIC_ADDR")
    bal_wei = await call_u256(client, aic, "balance_of", [h(owner)])
    print("balance_wei:", bal_wei)
    print("balance_AIC:", Decimal(bal_wei) / (Decimal(10) ** 18))

async def do_used(target_address: str | None):
    client = make_client()
    owner = resolve_address(target_address)
    um = req("UM_ADDR")
    used = await call_u64(client, um, "used_in_current_epoch", [h(owner)])
    print("used_units:", used)

async def do_allowance(target_address: str | None):
    client = make_client()
    owner = resolve_address(target_address)
    aic = req("AIC_ADDR"); um = req("UM_ADDR")
    allow_wei = await call_u256(client, aic, "allowance", [h(owner), h(um)])
    print("allowance_wei:", allow_wei)
    print("allowance_AIC:", Decimal(allow_wei) / (Decimal(10) ** 18))

async def do_approve(amount_tokens: str):
    _, account = await make_client_and_account()
    aic = req("AIC_ADDR"); um = req("UM_ADDR")
    amt_wei = tokens_to_wei(amount_tokens, 18); low, high = to_u256(amt_wei)
    tx_hash = await invoke(account, aic, "approve", [h(um), low, high])
    print("approve_tx:", hex(tx_hash))

async def do_mint(amount_tokens: str, to_addr: str | None):
    _, account = await make_client_and_account()
    aic = req("AIC_ADDR"); to = resolve_address(to_addr)
    amt_wei = tokens_to_wei(amount_tokens, 18); low, high = to_u256(amt_wei)
    tx_hash = await invoke(account, aic, "mint", [h(to), low, high])
    print("mint_tx:", hex(tx_hash))

async def do_authorize(units: int):
    _, account = await make_client_and_account()
    um = req("UM_ADDR")
    tx_hash = await invoke(account, um, "authorize_usage", [int(units)])
    print("authorize_usage_tx:", hex(tx_hash))

async def do_epoch(target_address: str | None):
    client = make_client()
    um = req("UM_ADDR")
    resolved = resolve_address(target_address, required=False)
    if resolved:
        print("address:", resolved)
    eid = await call_u64(client, um, "get_epoch_id", [])
    print("epoch_id:", eid)

def main():
    parser = argparse.ArgumentParser(prog="tokenxllm")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_bal = sub.add_parser("balance");   p_bal.add_argument("--address", default=None)
    p_used = sub.add_parser("used");      p_used.add_argument("--address", default=None)
    p_allow = sub.add_parser("allowance");p_allow.add_argument("--address", default=None)
    p_epoch = sub.add_parser("epoch");    p_epoch.add_argument("--address", default=None)
    p_app = sub.add_parser("approve");   p_app.add_argument("--amount", required=True)
    p_mint = sub.add_parser("mint");     p_mint.add_argument("--amount", required=True); p_mint.add_argument("--to", default=None)
    p_auth = sub.add_parser("authorize");p_auth.add_argument("--units", required=True, type=int)
    args = parser.parse_args()

    if args.cmd == "balance":      asyncio.run(do_balance(args.address))
    elif args.cmd == "used":       asyncio.run(do_used(args.address))
    elif args.cmd == "allowance":  asyncio.run(do_allowance(args.address))
    elif args.cmd == "approve":    asyncio.run(do_approve(args.amount))
    elif args.cmd == "mint":       asyncio.run(do_mint(args.amount, args.to))
    elif args.cmd == "authorize":  asyncio.run(do_authorize(args.units))
    elif args.cmd == "epoch":      asyncio.run(do_epoch(args.address))

if __name__ == "__main__":
    main()
