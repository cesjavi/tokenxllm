1) Requisitos

En Ubuntu WSL (22.04):

sudo apt update
sudo apt install -y git curl jq build-essential python3-venv python3-pip


Herramientas Starknet

Scarb (compilador Cairo + gestor del proyecto)

Starknet Foundry – sncast (declarar/desplegar/llamar)

Si ya las tenés y scarb --version y sncast --version responden, podés saltar esto.

2) Código del proyecto

Si ya tenés el repo, entrá a su carpeta. Si no:

git clone <tu_repo> tokenxllm
cd tokenxllm/tokenxllm


Estructura relevante:

src/contracts/erc20/AIC.cairo
src/contracts/usage/UsageManager.cairo
tokenxllm.py                 # CLI en Python
dashboard/backend/main.py    # FastAPI
dashboard/frontend/index.html

3) Compilar contratos
# Compilar en release (tu forma preferida)
scarb --release build

# Copiar artefactos al nombre que usa sncast 0.49
cp -f target/release/tokenxllm.starknet_artifacts.json target/release/starknet_artifacts.json

# Ver nombres de contratos (deberían salir "AIC" y "UsageManager")
jq -r '.contracts[] | .name' target/release/starknet_artifacts.json

4) Variables útiles (Sepolia)
export RPC_URL="https://starknet-sepolia.public.blastapi.io/rpc/v0_9"

# Ruta del archivo de cuentas OZ (usado por sncast)
export ACC_FILE="$HOME/.starknet_accounts/starknet_open_zeppelin_accounts.json"

# Nombre de cuenta dentro de ese archivo (vos usaste 'dev')
export ACCOUNT="dev"

# Tu address (el dueño/tesorería y quien firma las TX)
export OWNER_ADDR="0x522570db5197d282febafea3538ff2deacfaf49ec85a86e30bbe45af6f7c90"


Asegurate que en ~/.starknet_accounts/starknet_open_zeppelin_accounts.json tu cuenta dev esté en alpha-sepolia.

5) Declarar y desplegar AIC

Declarar:

sncast --account "$ACCOUNT" --accounts-file "$ACC_FILE" \
  declare --url "$RPC_URL" \
  --package tokenxllm \
  --contract-name AIC


Desplegar (constructor: name, symbol, decimals, owner):

Podés pasar AIC como short string o en hex 0x414943. Ejemplo con hex:

export AIC_NAME_HEX="0x414943"
sncast --account "$ACCOUNT" --accounts-file "$ACC_FILE" \
  deploy --url "$RPC_URL" \
  --class-hash <CLASS_HASH_QUE_SALIO_EN_DECLARE> \
  --constructor-calldata $AIC_NAME_HEX $AIC_NAME_HEX 18 "$OWNER_ADDR"


Anotá la dirección que imprime. Por ejemplo (tu despliegue previo):

AIC_ADDR = 0x06ddaf09636ceb526485c55b93c48c70f2a1728ad223743aaf08c21362ae7d9e

6) Declarar y desplegar UsageManager

Declarar:

sncast --account "$ACCOUNT" --accounts-file "$ACC_FILE" \
  declare --url "$RPC_URL" \
  --package tokenxllm \
  --contract-name UsageManager


Desplegar (constructor: token, treasury, free_quota, price_lo, price_hi, epoch_seconds, admin):

sncast --account "$ACCOUNT" --accounts-file "$ACC_FILE" \
  deploy --url "$RPC_URL" \
  --class-hash <CLASS_HASH_UM> \
  --constructor-calldata \
    "$AIC_ADDR" "$OWNER_ADDR" \
    2000 10000000000000000 0 \
    86400 "$OWNER_ADDR"


Anotá la dirección (tu despliegue previo):

UM_ADDR = 0x04515dc0c7ccb8c2816cd95ca16db10eb3c8071dafea05414fd078c4dc41473a

7) (Opcional) Probar con sncast
# Mint sólo owner
sncast --account "$ACCOUNT" --accounts-file "$ACC_FILE" send --url "$RPC_URL" \
  --contract-address "$AIC_ADDR" --function mint \
  --calldata "$OWNER_ADDR" 1000000000000000000 0

# Aprobar → UM (90 AIC en wei)
sncast --account "$ACCOUNT" --accounts-file "$ACC_FILE" send --url "$RPC_URL" \
  --contract-address "$AIC_ADDR" --function approve \
  --calldata "$UM_ADDR" 90000000000000000000 0

# Autorizar uso (3000 unidades)
sncast --account "$ACCOUNT" --accounts-file "$ACC_FILE" send --url "$RPC_URL" \
  --contract-address "$UM_ADDR" --function authorize_usage \
  --calldata 3000

# Lecturas
sncast call --url "$RPC_URL" --contract-address "$UM_ADDR" --function used_in_current_epoch --calldata "$OWNER_ADDR"
sncast call --url "$RPC_URL" --contract-address "$AIC_ADDR" --function balance_of --calldata "$OWNER_ADDR"

8) CLI en Python (tokenxllm.py)

En la raíz del proyecto:

python3 -m venv venv
source venv/bin/activate
pip install -U pip
pip install -r requirements.txt   # si no existe, instalá: starknet_py==0.20.1 python-dotenv


Variables (en .env junto al script o exportadas):

RPC_URL=https://starknet-sepolia.public.blastapi.io/rpc/v0_9
AIC_ADDR=0x06ddaf09636ceb526485c55b93c48c70f2a1728ad223743aaf08c21362ae7d9e
UM_ADDR=0x04515dc0c7ccb8c2816cd95ca16db10eb3c8071dafea05414fd078c4dc41473a
AIC_DECIMALS=18

# Sólo si vas a firmar con el CLI:
ACCOUNT_ADDRESS=0x522570db5197d282febafea3538ff2deacfaf49ec85a86e30bbe45af6f7c90
PRIVATE_KEY=0x<tu_privada_hex>


Usos:

python tokenxllm.py balance
python tokenxllm.py allowance
python tokenxllm.py approve --amount 100
python tokenxllm.py authorize --units 3000
python tokenxllm.py used
python tokenxllm.py epoch

Ejemplo paso a paso del flujo de cuota gratis vs pagada:

```
python examples/free_vs_paid/example_free_paid.py
```

El directorio `examples/free_vs_paid/` incluye una guía con los requisitos y
cómo interpretar los cambios en `used_in_current_epoch` y la `allowance`.

9) Dashboard – Backend (FastAPI)
cd dashboard/backend
python3 -m venv venv
source venv/bin/activate
pip install -U pip
pip install fastapi uvicorn "starknet_py==0.20.1" python-dotenv

# .env
cat > .env << 'EOF'
RPC_URL=https://starknet-sepolia.public.blastapi.io/rpc/v0_9
AIC_ADDR=0x06ddaf09636ceb526485c55b93c48c70f2a1728ad223743aaf08c21362ae7d9e
UM_ADDR=0x04515dc0c7ccb8c2816cd95ca16db10eb3c8071dafea05414fd078c4dc41473a
AIC_DECIMALS=18
# Opcional: lista separada por comas de orígenes permitidos además de localhost
DASHBOARD_PUBLIC_URL=https://tu-dashboard.vercel.app
# Para habilitar botones de escritura (approve/authorize/mint):
ACCOUNT_ADDRESS=0x522570db5197d282febafea3538ff2deacfaf49ec85a86e30bbe45af6f7c90
PRIVATE_KEY=0x<tu_privada_hex>
# Faucet opcional
FAUCET_ENABLED=true
FAUCET_AMOUNT_AIC=50
FAUCET_COOLDOWN_SECONDS=86400
EOF

uvicorn main:app --host 0.0.0.0 --port 8000


Tip: si no ponés ACCOUNT_ADDRESS/PRIVATE_KEY, writes_enabled=false y el front puede deshabilitar acciones que firman.

Si habilitás el faucet:

- La cuenta configurada en ACCOUNT_ADDRESS/PRIVATE_KEY debe ser la dueña del AIC para poder mintear.
- Enviá algo de ETH de Sepolia a esa cuenta para cubrir fees.
- Los parámetros se leen en `/faucet` (GET) y el reclamo se hace con `POST /faucet` enviando `{ "to": "0x..." }`.
- El backend aplica un cooldown por address basado en `FAUCET_COOLDOWN_SECONDS`.
- El endpoint `/config` incluye un bloque `faucet` con esta información para el dashboard.

10) Dashboard – Frontend

Desde Windows o Ubuntu (en carpeta dashboard/frontend):

# Servir el HTML por HTTP (evita “TypeError: Failed to fetch” del esquema file://)
cd dashboard/frontend
python3 -m http.server 5500

En el dashboard verás una tarjeta "Faucet" con el estado actual, el monto por reclamo y el cooldown restante para la dirección ingresada. El botón "Reclamar faucet" usa el backend para mintear el monto configurado (si el faucet está habilitado y no estás en cooldown).


Abrí en el navegador:

http://localhost:5500/index.html


En el campo Backend Base URL poné:

http://localhost:8000


→ Load Config
→ ingresá Your Address con tu OWNER_ADDR
→ Refresh.

Los botones Approve / Authorize / Mint funcionarán si el backend tiene writes_enabled=true (es decir, si cargaste ACCOUNT_ADDRESS y PRIVATE_KEY en el .env del backend).

11) Flujo típico

Mint (opcional): aumentar AIC del owner.

Approve: dar allowance desde AIC → UM (p.ej. 100 AIC).

Authorize: consumir N unidades; si superás la free_quota, UM hace transfer_from del AIC al treasury.

Refresh: ver balance, allowance y used/epoch.

12) Problemas comunes (y soluciones)

TypeError: Failed to fetch en el front
→ Serví index.html por HTTP (no abrir como file://), y verificá que el backend esté en http://localhost:8000.

400 Missing .env parameter
→ Falta ACCOUNT_ADDRESS o PRIVATE_KEY en el .env del backend para firmar transacciones. Cargalos o deshabilitá las acciones de escritura.

ClientError: Invalid block id en el backend
→ Usá starknet_py==0.20.1 y RPC_URL con .../rpc/v0_9. Reiniciá el backend.

Invalid transaction nonce / “nonce out of date”
→ Esperá unos segundos y reintentá. La versión del backend ya solicita nonce explícito.

sncast: “Profile not found/Account not found”
→ Usá --account <nombre> y --accounts-file <ruta>, y revisá que esté bajo la red alpha-sepolia.

Class not declared al deploy
→ A veces la declaración tarda en estar finalizada. Esperá y reintentá el deploy.

13) Seguridad y despliegue

No expongas el backend con writes_enabled=true a internet.

Limitá CORS (allow_origins) a tu dominio.

Si desplegás el backend en Vercel, agregá en **Settings → Environment Variables** una variable `DASHBOARD_PUBLIC_URL` con el dominio público de tu frontend (por ejemplo `https://tu-dashboard.vercel.app`). También podés listar varios orígenes separados por comas si necesitás más de un dominio.

Considerá .env fuera del repo y rotación periódica de claves.

Para producción, podés armar docker-compose (nginx + backend) o portar el frontend a una SPA y firmar con ArgentX/Braavos en el navegador (el backend quedaría sólo para lecturas).
