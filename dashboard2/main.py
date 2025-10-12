from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starknet_py.net.full_node_client import FullNodeClient
from starknet_py.net.account.account import Account
from starknet_py.net.signer.stark_curve_signer import KeyPair
from starknet_py.net.client_models import Call
from starknet_py.hash.selector import get_selector_from_name
from starknet_py.cairo.felt import encode_shortstring
import os
from dotenv import load_dotenv
from pathlib import Path
import asyncio
from types import SimpleNamespace

load_dotenv()

app = FastAPI(title="TokenXLLM Dashboard")

# Configuración de templates
templates_dir = Path(__file__).parent / "templates"
templates_dir.mkdir(exist_ok=True)
templates = Jinja2Templates(directory=str(templates_dir))

# Configuración de Starknet
RPC_URL = os.getenv("STARKNET_RPC_URL", "https://starknet-sepolia.public.blastapi.io/rpc/v0_9")
ADMIN_PRIVATE_KEY = os.getenv("ADMIN_PRIVATE_KEY")
ADMIN_ADDRESS = os.getenv("ADMIN_ADDRESS")
TOKEN_ADDRESS = int(os.getenv("TOKEN_ADDRESS", "0x0"), 16)
USAGE_MANAGER_ADDRESS = int(os.getenv("USAGE_MANAGER_ADDRESS", "0x0"), 16)
TREASURY_ADDRESS = int(os.getenv("TREASURY_ADDRESS", "0x0"), 16)

client = FullNodeClient(node_url=RPC_URL)
try:
    from starknet_py.net.client_models import ResourceBounds, ResourceBoundsMapping
except Exception:
    ResourceBounds = ResourceBoundsMapping = None

# Lock para transacciones
_TX_LOCK = asyncio.Lock()

async def _build_resource_bounds(account: Account, calls: list):
    """
    Arma ResourceBoundsMapping para V3 usando la estimación automática de starknet_py.
    """
    if ResourceBounds is None or ResourceBoundsMapping is None:
        raise RuntimeError("ResourceBounds* no disponible en tu starknet_py (requerido para V3).")

    try:
        # Dejar que starknet_py estime automáticamente
        est = await account.estimate_fee(calls=calls)
        
        # Obtener el precio actual del gas desde el bloque
        try:
            block = await account.client.get_block("latest")
            if hasattr(block, "l1_gas_price") and block.l1_gas_price:
                l1_gas_price = int(block.l1_gas_price.price_in_wei)
            else:
                l1_gas_price = int(1e11)
        except:
            l1_gas_price = int(1e11)
        
        # Extraer gas consumido de la estimación
        if hasattr(est, 'gas_consumed'):
            gas_amount = int(est.gas_consumed)
        elif hasattr(est, 'overall_fee'):
            # Estimar gas desde el fee total
            gas_amount = int(est.overall_fee / l1_gas_price) if l1_gas_price > 0 else 200000
        else:
            gas_amount = 200000
        
        # Aplicar multiplicador generoso para cubrir fluctuaciones
        l1_gas_amount = int(gas_amount * 5)
        l2_gas_amount = int(gas_amount * 5)
        l1_data_amount = int(gas_amount * 5)
        
        # Usar el precio actual con multiplicador
        max_price = int(l1_gas_price * 3)
        
        print(f"Estimated gas: {gas_amount}, l1_price: {l1_gas_price}, using: amount={l1_gas_amount}, price={max_price}")
        
        # Intentar con l1_data_gas primero
        try:
            return ResourceBoundsMapping(
                l1_gas=ResourceBounds(max_amount=l1_gas_amount, max_price_per_unit=max_price),
                l2_gas=ResourceBounds(max_amount=l2_gas_amount, max_price_per_unit=1),
                l1_data_gas=ResourceBounds(max_amount=l1_data_amount, max_price_per_unit=max_price),
            )
        except TypeError:
            # Fallback sin l1_data_gas
            return ResourceBoundsMapping(
                l1_gas=ResourceBounds(max_amount=l1_gas_amount, max_price_per_unit=max_price),
                l2_gas=ResourceBounds(max_amount=l2_gas_amount, max_price_per_unit=1),
            )
            
    except Exception as e:
        print(f"Error in estimate_fee: {e}, using safe defaults")
        # Defaults muy generosos si todo falla
        default_amount = 1000000  # 1M gas units
        default_price = int(2e11)  # 200 Gwei
        
        try:
            return ResourceBoundsMapping(
                l1_gas=ResourceBounds(max_amount=default_amount, max_price_per_unit=default_price),
                l2_gas=ResourceBounds(max_amount=default_amount, max_price_per_unit=1),
                l1_data_gas=ResourceBounds(max_amount=default_amount, max_price_per_unit=default_price),
            )
        except TypeError:
            return ResourceBoundsMapping(
                l1_gas=ResourceBounds(max_amount=default_amount, max_price_per_unit=default_price),
                l2_gas=ResourceBounds(max_amount=default_amount, max_price_per_unit=1),
            )


async def send_calls(calls: list):
    """
    Envia 'calls' usando auto_estimate=True (el método más confiable).
    """
    # Obtener la cuenta con chain_id correcto
    account = await get_account_async()
    
    async with _TX_LOCK:
        # Función interna para ejecutar con la versión apropiada
        async def _do_execute(use_v3_first: bool = True):
            try:
                nonce = await account.get_nonce()
            except:
                nonce = None
            
            if use_v3_first and hasattr(account, "execute_v3"):
                if nonce is not None:
                    return await account.execute_v3(calls=calls, auto_estimate=True, nonce=nonce)
                else:
                    return await account.execute_v3(calls=calls, auto_estimate=True)
            
            # Fallback a execute con version=1
            if hasattr(account, "execute"):
                if nonce is not None:
                    return await account.execute(calls=calls, version=1, auto_estimate=True, nonce=nonce)
                else:
                    return await account.execute(calls=calls, auto_estimate=True)
            
            # Fallback a execute_v1
            if hasattr(account, "execute_v1"):
                try:
                    est = await account.estimate_fee(calls=calls)
                    max_fee = int(est.overall_fee * 5)
                except:
                    max_fee = int(1e15)
                return await account.execute_v1(calls=calls, max_fee=max_fee)
            
            raise RuntimeError("No se encontró un método válido para ejecutar transacciones")
        
        # Primer intento
        try:
            try:
                tx = await _do_execute(use_v3_first=True)
            except Exception as exc:
                msg = str(exc).lower()
                # Si falla por versión v3, probar v1 directamente
                if any(s in msg for s in ("unsupported_tx_version", "invalid transaction version", "v3")):
                    tx = await _do_execute(use_v3_first=False)
                else:
                    raise
        except Exception as exc:
            msg = str(exc).lower()
            # Retry UNA VEZ si es nonce inválido
            if "invalid transaction nonce" in msg or ("nonce" in msg and "invalid" in msg):
                try:
                    tx = await _do_execute(use_v3_first=hasattr(account, "execute_v3"))
                except Exception as exc2:
                    raise HTTPException(status_code=502, detail=f"Failed to submit transaction (nonce-retry): {exc2!r}") from exc2
            else:
                raise HTTPException(status_code=502, detail=f"Failed to submit transaction: {exc!r}") from exc
        
        # Obtener el hash de la transacción
        tx_hash = getattr(tx, "hash", None) or getattr(tx, "transaction_hash", None)
        if isinstance(tx_hash, int):
            tx_hash_int = tx_hash
        else:
            tx_hash_int = int(str(tx_hash), 16) if isinstance(tx_hash, str) else tx_hash
        
        # Esperar a que la transacción sea aceptada
        await account.client.wait_for_tx(tx_hash_int)
        
        print(f"Transaction successful: {hex(tx_hash_int)}")
        return SimpleNamespace(transaction_hash=tx_hash_int)
    
async def get_account_async():
    """Crea cuenta de administrador de forma asíncrona con chain_id correcto"""
    if not ADMIN_PRIVATE_KEY or not ADMIN_ADDRESS:
        raise ValueError("ADMIN_PRIVATE_KEY y ADMIN_ADDRESS no configurados")
    
    # Asegurarse de que la private key sea un entero
    try:
        if isinstance(ADMIN_PRIVATE_KEY, str):
            priv_key_int = int(ADMIN_PRIVATE_KEY.strip(), 16) if ADMIN_PRIVATE_KEY.strip().startswith('0x') else int(ADMIN_PRIVATE_KEY.strip())
        else:
            priv_key_int = int(ADMIN_PRIVATE_KEY)
    except ValueError as e:
        raise ValueError(f"Invalid ADMIN_PRIVATE_KEY format: {e}")
    
    # Asegurarse de que la address sea un entero
    try:
        if isinstance(ADMIN_ADDRESS, str):
            addr_int = int(ADMIN_ADDRESS.strip(), 16) if ADMIN_ADDRESS.strip().startswith('0x') else int(ADMIN_ADDRESS.strip())
        else:
            addr_int = int(ADMIN_ADDRESS)
    except ValueError as e:
        raise ValueError(f"Invalid ADMIN_ADDRESS format: {e}")
    
    # Obtener chain_id del cliente
    chain_id = await client.get_chain_id()
    
    key_pair = KeyPair.from_private_key(priv_key_int)
    
    return Account(
        client=client,
        address=addr_int,
        key_pair=key_pair,
        chain=chain_id
    )

def get_account():
    """Crea cuenta de administrador (versión sync para compatibilidad)"""
    if not ADMIN_PRIVATE_KEY or not ADMIN_ADDRESS:
        raise ValueError("ADMIN_PRIVATE_KEY y ADMIN_ADDRESS no configurados")
    
    # Asegurarse de que la private key sea un entero
    try:
        if isinstance(ADMIN_PRIVATE_KEY, str):
            priv_key_int = int(ADMIN_PRIVATE_KEY.strip(), 16) if ADMIN_PRIVATE_KEY.strip().startswith('0x') else int(ADMIN_PRIVATE_KEY.strip())
        else:
            priv_key_int = int(ADMIN_PRIVATE_KEY)
    except ValueError as e:
        raise ValueError(f"Invalid ADMIN_PRIVATE_KEY format: {e}")
    
    # Asegurarse de que la address sea un entero
    try:
        if isinstance(ADMIN_ADDRESS, str):
            addr_int = int(ADMIN_ADDRESS.strip(), 16) if ADMIN_ADDRESS.strip().startswith('0x') else int(ADMIN_ADDRESS.strip())
        else:
            addr_int = int(ADMIN_ADDRESS)
    except ValueError as e:
        raise ValueError(f"Invalid ADMIN_ADDRESS format: {e}")
    
    key_pair = KeyPair.from_private_key(priv_key_int)
    
    # Usar chain_id de Sepolia testnet
    return Account(
        client=client,
        address=addr_int,
        key_pair=key_pair,
        chain=0x534e5f5345504f4c4941  # Sepolia chain ID en hex
    )

def felt_to_string(felt: int) -> str:
    """Convierte felt252 a string"""
    if felt == 0:
        return ""
    hex_str = hex(felt)[2:]
    if len(hex_str) % 2:
        hex_str = '0' + hex_str
    try:
        return bytes.fromhex(hex_str).decode('utf-8', errors='ignore').rstrip('\x00')
    except:
        return hex(felt)

def u256_to_int(values: list) -> int:
    """Convierte u256 (low, high) a int"""
    if len(values) >= 2:
        return values[0] + (values[1] << 128)
    return values[0] if values else 0

async def call_contract(contract_address: int, function_name: str, calldata: list = None):
    """Llama a una función de contrato (view)"""
    try:
        result = await client.call_contract(
            call=Call(
                to_addr=contract_address,
                selector=get_selector_from_name(function_name),
                calldata=calldata or []
             ),
            block_number="latest"
        )
        return result
    except Exception as e:
        print(f"Error calling {function_name}: {e}")
        return []


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Dashboard principal"""
    
    try:
        # Llamadas al token
        name_result = await call_contract(TOKEN_ADDRESS, "name")
        symbol_result = await call_contract(TOKEN_ADDRESS, "symbol")
        decimals_result = await call_contract(TOKEN_ADDRESS, "decimals")
        supply_result = await call_contract(TOKEN_ADDRESS, "totalSupply")
        treasury_balance_result = await call_contract(TOKEN_ADDRESS, "balanceOf", [TREASURY_ADDRESS])
        
        # Procesar datos del token
        token_name = felt_to_string(name_result[0]) if name_result else "Unknown"
        token_symbol = felt_to_string(symbol_result[0]) if symbol_result else "???"
        decimals = decimals_result[0] if decimals_result else 18
        total_supply = u256_to_int(supply_result) if supply_result else 0
        treasury_balance = u256_to_int(treasury_balance_result) if treasury_balance_result else 0
        
        # Llamadas al UsageManager
        epoch_result = await call_contract(USAGE_MANAGER_ADDRESS, "get_epoch_id")
        quota_result = await call_contract(USAGE_MANAGER_ADDRESS, "get_free_quota_per_epoch")
        price_result = await call_contract(USAGE_MANAGER_ADDRESS, "get_price_per_unit_wei")
        
        current_epoch = epoch_result[0] if epoch_result else 0
        free_quota = quota_result[0] if quota_result else 0
        price_per_unit = u256_to_int(price_result) if price_result else 0
        
        data = {
            "token_name": token_name,
            "token_symbol": token_symbol,
            "decimals": decimals,
            "total_supply": total_supply / (10 ** decimals),
            "current_epoch": current_epoch,
            "free_quota": free_quota,
            "price_per_unit": price_per_unit / (10 ** decimals),
            "treasury_balance": treasury_balance / (10 ** decimals),
            "token_address": hex(TOKEN_ADDRESS),
            "usage_manager_address": hex(USAGE_MANAGER_ADDRESS),
            "treasury_address": hex(TREASURY_ADDRESS)
        }
        
    except Exception as e:
        data = {
            "error": str(e),
            "token_address": hex(TOKEN_ADDRESS) if TOKEN_ADDRESS else "Not configured",
            "usage_manager_address": hex(USAGE_MANAGER_ADDRESS) if USAGE_MANAGER_ADDRESS else "Not configured",
            "treasury_address": hex(TREASURY_ADDRESS) if TREASURY_ADDRESS else "Not configured"
        }
    
    return templates.TemplateResponse("dashboard.html", {"request": request, **data})

@app.post("/mint")
async def mint_tokens(address: str = Form(...), amount: float = Form(...)):
    """Mintea tokens a una dirección"""
    try:
        # Decimales
        decimals_result = await call_contract(TOKEN_ADDRESS, "decimals")
        decimals = decimals_result[0] if decimals_result else 18

        # Cantidad a u256
        amount_wei = int(amount * (10 ** decimals))
        low = amount_wei & ((1 << 128) - 1)
        high = amount_wei >> 128

        # Tx
        tx_calldata = [int(address, 16), low, high]
        tx = Call(to_addr=TOKEN_ADDRESS, selector=get_selector_from_name("mint"), calldata=tx_calldata)
        resp = await send_calls([tx])
        
        return RedirectResponse(url="/?success=mint", status_code=303)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/approve")
async def approve_tokens(spender: str = Form(...), amount: float = Form(...)):
    """Aprueba tokens para un spender"""
    try:
        # Obtener decimales
        decimals_result = await call_contract(TOKEN_ADDRESS, "decimals")
        decimals = decimals_result[0] if decimals_result else 18
        
        # Convertir cantidad
        amount_wei = int(amount * (10 ** decimals))
        low = amount_wei & ((1 << 128) - 1)
        high = amount_wei >> 128
        
        # Crear llamada
        tx = Call(to_addr=TOKEN_ADDRESS, selector=get_selector_from_name("approve"), calldata=[int(spender, 16), low, high])
        resp = await send_calls([tx])
        
        return RedirectResponse(url="/?success=approve", status_code=303)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/authorize")
async def authorize_usage(units: int = Form(...)):
    """Autoriza uso de unidades"""
    try:
        # Crear llamada
        tx = Call(to_addr=USAGE_MANAGER_ADDRESS, selector=get_selector_from_name("authorize_usage"), calldata=[units])
        resp = await send_calls([tx])
        
        return RedirectResponse(url="/?success=authorize", status_code=303)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/set_price")
async def set_price(price: float = Form(...)):
    """Actualiza el precio por unidad"""
    try:
        # Obtener decimales
        decimals_result = await call_contract(TOKEN_ADDRESS, "decimals")
        decimals = decimals_result[0] if decimals_result else 18
        
        # Convertir precio
        price_wei = int(price * (10 ** decimals))
        low = price_wei & ((1 << 128) - 1)
        high = price_wei >> 128
        
        # Crear llamada
        tx = Call(to_addr=USAGE_MANAGER_ADDRESS, selector=get_selector_from_name("set_price_per_unit_wei"), calldata=[low, high])
        resp = await send_calls([tx])
        
        return RedirectResponse(url="/?success=price_updated", status_code=303)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/set_quota")
async def set_quota(quota: int = Form(...)):
    """Actualiza la cuota gratis por época"""
    try:
        # Crear llamada
        tx = Call(to_addr=USAGE_MANAGER_ADDRESS, selector=get_selector_from_name("set_free_quota_per_epoch"), calldata=[quota])
        resp = await send_calls([tx])
        
        return RedirectResponse(url="/?success=quota_updated", status_code=303)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/check_balance/{address}")
async def check_balance(address: str):
    """Consulta balance de una dirección"""
    try:
        balance_result = await call_contract(TOKEN_ADDRESS, "balanceOf", [int(address, 16)])
        decimals_result = await call_contract(TOKEN_ADDRESS, "decimals")
        
        balance = u256_to_int(balance_result) if balance_result else 0
        decimals = decimals_result[0] if decimals_result else 18
        
        return {
            "address": address,
            "balance": balance / (10 ** decimals),
            "balance_wei": balance
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/check_usage/{address}")
async def check_usage(address: str):
    """Consulta uso actual de una dirección"""
    try:
        used_result = await call_contract(
            USAGE_MANAGER_ADDRESS, 
            "used_in_current_epoch", 
            [int(address, 16)]
        )
        quota_result = await call_contract(USAGE_MANAGER_ADDRESS, "get_free_quota_per_epoch")
        
        used = used_result[0] if used_result else 0
        quota = quota_result[0] if quota_result else 0
        
        return {
            "address": address,
            "used_units": used,
            "free_quota": quota,
            "remaining_free": max(0, quota - used)
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# Template HTML
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TokenXLLM Dashboard</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container { max-width: 1200px; margin: 0 auto; }
        .header {
            background: white;
            padding: 30px;
            border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            margin-bottom: 30px;
        }
        .header h1 { color: #667eea; margin-bottom: 10px; }
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .stat-card {
            background: white;
            padding: 25px;
            border-radius: 15px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        }
        .stat-card h3 { color: #666; font-size: 14px; margin-bottom: 10px; text-transform: uppercase; }
        .stat-card .value { color: #667eea; font-size: 28px; font-weight: bold; }
        .stat-card .subtitle { color: #999; margin-top: 5px; font-size: 14px; }
        .actions {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
        }
        .action-card {
            background: white;
            padding: 25px;
            border-radius: 15px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        }
        .action-card h2 { color: #667eea; margin-bottom: 20px; font-size: 20px; }
        .form-group { margin-bottom: 15px; }
        .form-group label { display: block; margin-bottom: 5px; color: #666; font-weight: 500; }
        .form-group input {
            width: 100%;
            padding: 12px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 14px;
            transition: border-color 0.3s;
        }
        .form-group input:focus {
            outline: none;
            border-color: #667eea;
        }
        button {
            width: 100%;
            padding: 12px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s;
        }
        button:hover { transform: translateY(-2px); box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4); }
        button:active { transform: translateY(0); }
        .alert {
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
        }
        .alert-success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
        .alert-error { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
        .address-info {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
            font-size: 12px;
            color: #666;
            word-break: break-all;
            line-height: 1.8;
        }
        .query-section {
            background: white;
            padding: 25px;
            border-radius: 15px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
            margin-top: 30px;
        }
        .query-section h2 { color: #667eea; margin-bottom: 20px; }
        .query-form { display: flex; gap: 10px; margin-bottom: 20px; }
        .query-form input { flex: 1; }
        .query-form button { flex: 0 0 150px; }
        .result-box {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            margin-top: 15px;
            font-family: monospace;
            font-size: 12px;
            display: none;
        }
        .result-box.show { display: block; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚀 TokenXLLM Dashboard</h1>
            <p>Gestión de tokens y uso del sistema en Starknet</p>
        </div>

        {% if error %}
        <div class="alert alert-error">
            <strong>⚠️ Error:</strong> {{ error }}
        </div>
        {% endif %}

        <div class="address-info">
            <strong>🪙 Token:</strong> {{ token_address }}<br>
            <strong>⚙️ Usage Manager:</strong> {{ usage_manager_address }}<br>
            <strong>💰 Treasury:</strong> {{ treasury_address }}
        </div>

        {% if not error %}
        <div class="stats">
            <div class="stat-card">
                <h3>Token</h3>
                <div class="value">{{ token_symbol }}</div>
                <div class="subtitle">{{ token_name }}</div>
            </div>
            <div class="stat-card">
                <h3>Total Supply</h3>
                <div class="value">{{ "%.2f"|format(total_supply) }}</div>
                <div class="subtitle">{{ token_symbol }}</div>
            </div>
            <div class="stat-card">
                <h3>Treasury Balance</h3>
                <div class="value">{{ "%.2f"|format(treasury_balance) }}</div>
                <div class="subtitle">{{ token_symbol }}</div>
            </div>
            <div class="stat-card">
                <h3>Current Epoch</h3>
                <div class="value">{{ current_epoch }}</div>
                <div class="subtitle">Época actual</div>
            </div>
            <div class="stat-card">
                <h3>Free Quota</h3>
                <div class="value">{{ free_quota }}</div>
                <div class="subtitle">unidades/época</div>
            </div>
            <div class="stat-card">
                <h3>Price per Unit</h3>
                <div class="value">{{ "%.4f"|format(price_per_unit) }}</div>
                <div class="subtitle">{{ token_symbol }}/unidad</div>
            </div>
        </div>

        <div class="actions">
            <div class="action-card">
                <h2>💰 Mint Tokens</h2>
                <form method="post" action="/mint">
                    <div class="form-group">
                        <label>Dirección destino</label>
                        <input type="text" name="address" placeholder="0x..." required>
                    </div>
                    <div class="form-group">
                        <label>Cantidad</label>
                        <input type="number" name="amount" step="0.01" placeholder="100.00" required>
                    </div>
                    <button type="submit">Mint Tokens</button>
                </form>
            </div>

            <div class="action-card">
                <h2>✅ Aprobar Tokens</h2>
                <form method="post" action="/approve">
                    <div class="form-group">
                        <label>Spender (UsageManager)</label>
                        <input type="text" name="spender" value="{{ usage_manager_address }}" required>
                    </div>
                    <div class="form-group">
                        <label>Cantidad</label>
                        <input type="number" name="amount" step="0.01" placeholder="1000.00" required>
                    </div>
                    <button type="submit">Aprobar</button>
                </form>
            </div>

            <div class="action-card">
                <h2>🎯 Autorizar Uso</h2>
                <form method="post" action="/authorize">
                    <div class="form-group">
                        <label>Unidades a consumir</label>
                        <input type="number" name="units" placeholder="50" required>
                    </div>
                    <button type="submit">Autorizar Uso</button>
                </form>
            </div>

            <div class="action-card">
                <h2>💵 Configurar Precio</h2>
                <form method="post" action="/set_price">
                    <div class="form-group">
                        <label>Nuevo precio por unidad</label>
                        <input type="number" name="price" step="0.0001" placeholder="1.0000" required>
                    </div>
                    <button type="submit">Actualizar Precio</button>
                </form>
            </div>

            <div class="action-card">
                <h2>🎁 Configurar Cuota Gratis</h2>
                <form method="post" action="/set_quota">
                    <div class="form-group">
                        <label>Nueva cuota por época</label>
                        <input type="number" name="quota" placeholder="100" required>
                    </div>
                    <button type="submit">Actualizar Cuota</button>
                </form>
            </div>
        </div>
        {% endif %}
    </div>
</body>
</html>
"""

# Guardar template
@app.on_event("startup")
async def create_template():
    template_path = templates_dir / "dashboard.html"
    with open(template_path, "w", encoding="utf-8") as f:
        f.write(HTML_TEMPLATE)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)