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

The backend runs as a standalone FastAPI service. To host it on Vercel:

1. Create a **separate** Vercel project from the `dashboard/backend` directory.
2. Set the build command to `pip install -r requirements.txt` and the run command to `uvicorn main:app` (Vercel automatically wraps it as a serverless function).
3. Add the environment variables listed above (at minimum `RPC_URL`, `AIC_ADDR`, `UM_ADDR`, `AIC_DECIMALS`).
4. Define `DASHBOARD_PUBLIC_URL` with the public domain(s) of your frontend (comma separated if you have multiple). They will be appended to the CORS allow-list together with `http://localhost:5173` for local development.

> Because the backend exposes private write operations when `ACCOUNT_ADDRESS`/`PRIVATE_KEY` are present, avoid committing those values. Configure them directly in the Vercel dashboard if you need to enable writes.

Once the backend deployment succeeds, update the frontend environment variable `VITE_BACKEND_URL` so that the dashboard points to the newly created API.
