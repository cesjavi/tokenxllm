# Flujo de gasto: cuota gratis vs. AIC

Este documento resume cómo el contrato `UsageManager` decide entre consumir la cuota gratuita y cobrar en el token AIC cuando un usuario autoriza uso (`authorize_usage`).

## Datos iniciales

Al desplegar el contrato se configuran:

- `token`: dirección del ERC-20 que se usará para cobrar (AIC).
- `treasury`: cuenta que recibe los pagos.
- `free_quota_per_epoch`: unidades gratis disponibles por usuario en cada época.
- `price_per_unit_wei`: precio en wei del AIC por unidad excedida.
- `epoch_seconds`: duración de cada época para resetear el contador de uso.
- `admin`: dirección autorizada para cambiar precio y cuota gratuita.

Estos parámetros quedan guardados en storage en el constructor.【F:src/contracts/usage/UsageManager.cairo†L33-L60】

## Proceso al autorizar uso

Cuando un usuario ejecuta `authorize_usage(units)` el contrato:

1. Calcula la época actual (`epoch_id`) a partir del timestamp del bloque y `epoch_seconds`.
2. Lee cuántas unidades ya usó el llamante en esa época (`used`).
3. Consulta la cuota gratis total (`free_quota`).
4. Actualiza el acumulado (`new_used = used + units`).
5. Determina cuánta cuota gratis queda disponible (`free_remaining`).
6. Calcula las unidades pagas: `paid_units = max(0, units - free_remaining)`.

Estos pasos se realizan antes de cualquier transferencia.【F:src/contracts/usage/UsageManager.cairo†L88-L99】

Si `paid_units` es mayor que cero:

7. Multiplica `paid_units` por el `price_per_unit_wei` para obtener `total_cost`.
8. Invoca `transfer_from` del token AIC para mover `total_cost` desde la billetera del usuario hacia el `treasury`.

Finalmente se guarda el nuevo uso acumulado para esa época.【F:src/contracts/usage/UsageManager.cairo†L100-L115】

## ¿Quién paga realmente?

El contrato `UsageManager` no tiene saldo propio; sólo orquesta una transferencia `transfer_from` del token configurado. Eso significa que el **usuario** que llama `authorize_usage` es quien paga el AIC cuando se queda sin cuota gratis. Para que la transferencia funcione, el usuario tuvo que aprobar previamente (`approve`) al `UsageManager` para gastar AIC en su nombre. Este flujo se describe en el README del proyecto dentro del "Flujo típico":

1. (Opcional) `mint` para obtener más AIC.
2. `approve` para autorizar al UsageManager a usar cierta cantidad de AIC.
3. `authorize` para consumir unidades; si superás la cuota gratis, el contrato hace `transfer_from` hacia el tesoro.

【F:README.md†L264-L270】

Así, cuando se termina lo gratis el débito sale de la cuenta del usuario aprobante y va al `treasury`. El contrato sólo ejecuta la transferencia condicionada y actualiza el contador de uso por época.
