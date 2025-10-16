# Análisis y sugerencias de mejora

## CLI `tokenxllm.py`

1. **Centralizar la carga de configuración**.
   - Hoy cada función invoca `load_dotenv()` y lee variables de entorno por separado, lo que puede producir resultados inconsistentes si el archivo `.env` cambia durante la ejecución o si se llama a la librería desde otro proceso. Extraer una capa de configuración (por ejemplo, una `dataclass` con los campos `rpc_url`, direcciones y claves) permitiría cargar una sola vez y validar al inicio.【F:tokenxllm.py†L13-L97】

2. **Validaciones de entrada más explícitas**.
   - `tokens_to_wei` convierte cualquier valor a `Decimal` sin controlar si es negativo o si excede los 256 bits. Agregar verificaciones y mensajes de error legibles ayudaría a detectar parámetros inválidos antes de enviar una transacción.【F:tokenxllm.py†L23-L31】

3. **Reutilizar clientes y cuentas**.
   - Cada comando crea un `FullNodeClient` nuevo y, en operaciones de escritura, también un `Account`. Reutilizar clientes dentro de una misma ejecución o permitir inyectarlos facilitaría testear el CLI y evitaría reconexiones innecesarias al nodo.【F:tokenxllm.py†L43-L121】【F:tokenxllm.py†L139-L183】

4. **Manejo de errores y reporting**.
   - Las funciones como `invoke` confían en `auto_estimate=True` pero no capturan excepciones para mostrar detalles de fallos (por ejemplo, `StarknetErrorCode.INSUFFICIENT_FUNDS`). Incorporar bloques `try/except` alrededor de las llamadas de red y estandarizar los mensajes en español ayudaría al diagnóstico durante la operación.【F:tokenxllm.py†L105-L183】

5. **Extensión del CLI**.
   - Actualmente el comando `epoch` solo devuelve el ID. Aprovechar la misma llamada para mostrar el consumo actual del usuario (si se pasa `--address`) y los parámetros del contrato (`free_quota`, `price`) reduciría la cantidad de comandos necesarios para auditar el estado del Usage Manager.【F:tokenxllm.py†L158-L183】

## Contrato `UsageManager`

1. **Prevención de overflow en cálculos de uso**.
   - El cálculo `let new_used: u64 = used + units;` puede desbordar si la suma supera `2^64-1`. Usar `core::traits::TryInto` o la utilería `u128_from_felt252` para operar en `u128`/`u256` y luego validar que el resultado cabe en `u64` eliminaría este riesgo.【F:src/contracts/usage/UsageManager.cairo†L62-L70】

2. **Chequeos en el precio total**.
   - `let total_cost: u256 = price * paid_256;` multiplica dos `u256` sin verificar overflow. Considerar un helper que devuelva `(result, overflow)` o usar bibliotecas de aritmética segura para garantizar que los valores no se truncarán silenciosamente.【F:src/contracts/usage/UsageManager.cairo†L75-L90】

3. **Eventos para auditoría**.
   - El contrato no emite eventos al autorizar uso ni al actualizar parámetros administrativos. Emitir eventos (por ejemplo, `UsageAuthorized` con `paid_units` y `cost`) facilitaría el monitoreo off-chain y la integración con el dashboard.【F:src/contracts/usage/UsageManager.cairo†L62-L104】

4. **Control de `epoch_seconds`**.
   - La división `ts / self.epoch_seconds.read()` asume que `epoch_seconds` es distinto de cero, pero no se valida ni en el constructor ni en setters. Añadir una aserción en el constructor y en `set_free_quota_per_epoch`/`set_price_per_unit_wei` (o un setter específico) evitaría estados inválidos.【F:src/contracts/usage/UsageManager.cairo†L39-L61】

5. **Parámetros ajustables granularmente**.
   - Los métodos administrativos exigen que el `caller` sea exactamente `admin`. Para un modelo operativo con múltiples operadores podría añadirse una lista de operadores o un rol de `pauser` para emergencias, similar al patrón de `AccessControl`. Esto reduciría la dependencia de una sola clave.【F:src/contracts/usage/UsageManager.cairo†L96-L104】

## Contrato `AIC` (ERC-20)

1. **Funciones de lectura CamelCase duplicadas**.
   - El contrato expone tanto `balance_of`/`balanceOf` como `total_supply`/`totalSupply`. Documentar la razón o consolidar a una sola interfaz evita duplicidad y reduce el coste de mantenimiento.【F:src/contracts/erc20/AIC.cairo†L59-L92】

2. **Soporte para `permit` (EIP-2612 equivalente)**.
   - Añadir un flujo `permit` para firmar aprobaciones fuera de la cadena reduciría el número de transacciones necesarias para usuarios que operan con el Usage Manager. Esto requiere almacenar `nonces` y validar firmas, pero brinda una UX mucho más fluida.【F:src/contracts/erc20/AIC.cairo†L93-L138】

3. **Límites de acuñación**.
   - `mint` solo verifica que el caller sea el `owner`. Considerar límites diarios o la posibilidad de delegar minting a un `MinterRole` controlado por un multisig puede reforzar la seguridad operativa.【F:src/contracts/erc20/AIC.cairo†L123-L138】

## Pipeline y pruebas

1. **Pruebas automatizadas**.
   - No hay suites de pruebas visibles (ni en Cairo ni en Python). Agregar tests en `tests/` que cubran transferencias básicas del ERC-20 y escenarios de autorización con cuotas gratuitas daría más confianza antes de desplegar.【F:tests†L1-L1】

2. **Integración con CI**.
   - El repositorio incluye scripts de despliegue, pero no un workflow de GitHub Actions. Incorporar un workflow que ejecute `scarb test` y pruebas de la CLI (por ejemplo, con `pytest` usando `pytest-asyncio`) automatiza la validación en cada push.

