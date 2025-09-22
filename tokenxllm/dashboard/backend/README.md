Run with uvicorn after filling .env (copy from .env.example).

## Environment variables

| Name | Description |
| --- | --- |
| `RPC_URL` | Starknet RPC endpoint. |
| `AIC_ADDR` | Address of the AIC ERC-20 contract. |
| `UM_ADDR` | Address of the UsageManager contract. |
| `AIC_DECIMALS` | Decimal precision for the AIC token. |
| `ACCOUNT_ADDRESS` / `PRIVATE_KEY` | Optional pair used to enable write operations from the dashboard. |
| `DASHBOARD_PUBLIC_URL` | Optional comma-separated list of additional CORS origins. Set this to the public URL that serves the frontend (e.g. `https://your-dashboard.vercel.app`). |

### Deploying on Vercel

If you host the backend on Vercel, add an Environment Variable named `DASHBOARD_PUBLIC_URL` with the public domain of your deployed frontend (e.g. `https://your-dashboard.vercel.app`). This ensures the backend accepts requests from the production dashboard while keeping CORS restrictions in place.
