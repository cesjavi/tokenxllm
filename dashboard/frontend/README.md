# TokenXLLM Dashboard (frontend)

This frontend is a [Vite](https://vitejs.dev/) application that communicates with the TokenXLLM backend and Starknet smart contracts.

## Environment variables

Copy the example file and adjust it for your deployment:

```bash
cp .env.example .env
```

| Variable | Description |
| --- | --- |
| `VITE_BACKEND_URL` | Base URL of the TokenXLLM backend REST API (e.g. `http://localhost:8000`). |
| `VITE_RPC_URL` | Starknet RPC endpoint used to initialise the `starknet.js` provider. |
| `VITE_AIC_ADDR` | Address of the AIC token contract. |
| `VITE_UM_ADDR` | Address of the Usage Manager (UM) contract. |
| `VITE_DECIMALS` | Decimals used by the AIC token (commonly `18`). |

> The `VITE_` prefix is required so that Vite exposes the value to the browser bundle.

## Install dependencies

```bash
cd dashboard/frontend
npm install
```

## Run the dashboard locally

```bash
npm run dev
```

This starts the Vite development server (default port `5173`) with hot module replacement.

## Build for production

```bash
npm run build
npm run preview
```

The `build` command outputs static assets to `dist/`. Use `npm run preview` to serve the production build locally.

## Deploying to Vercel

You can deploy the frontend as a static site:

1. Create a new Vercel project using the `dashboard/frontend` folder as the root.
2. Set the build command to `npm run build` and the output directory to `dist`.
3. Define the environment variables that start with `VITE_` (at least `VITE_BACKEND_URL`, `VITE_RPC_URL`, `VITE_AIC_ADDR`, `VITE_UM_ADDR` and `VITE_DECIMALS`). Vercel will expose them at build time.
4. Point `VITE_BACKEND_URL` to the URL where you host the FastAPI backend (local testing, another Vercel project, Railway, Render, etc.).

> The frontend and backend must be deployed as separate projects. Once the backend is live, add its public URL to `VITE_BACKEND_URL` and trigger a new frontend build.
