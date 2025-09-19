# Free vs Paid Usage Walkthrough

This example shows how to observe the free quota and paid transfer behaviour of the `UsageManager` contract. It assumes you already deployed the contracts and configured the CLI described in the project README.

## Prerequisites

Before running the script:

1. Deploy the AIC ERC-20 token and the `UsageManager` contract, noting the deployed addresses.
2. Mint AIC to the account that will sign the transactions and approve the `UsageManager` to spend enough tokens to cover the paid portion of the demo. The helper CLI exposes convenient commands:
   ```bash
   python tokenxllm/tokenxllm.py mint --amount 100          # optional, only owner can mint
   python tokenxllm/tokenxllm.py approve --amount 90        # allow UM to pull 90 AIC (wei)
   python tokenxllm/tokenxllm.py allowance                  # verify the allowance in wei and tokens
   ```
3. Set the environment variables consumed by `tokenxllm.py` (they can live in a `.env` file):
   ```bash
   export RPC_URL=...
   export AIC_ADDR=0x...
   export UM_ADDR=0x...
   export ACCOUNT_ADDRESS=0x...
   export PRIVATE_KEY=0x...
   export AIC_DECIMALS=18
   ```
   The `ACCOUNT_ADDRESS`/`PRIVATE_KEY` pair (or an entry in `~/.starknet_accounts/...`) must have an allowance configured for the `UsageManager` contract.

## Recap of the contract rules

`UsageManager.authorize_usage` tracks usage per account and epoch. For each call the contract:

- Reads the caller's `used_in_current_epoch` and the configured `free_quota_per_epoch`.
- Computes the remaining free units and splits the requested `units` between free and paid portions.
- Transfers `paid_units * price_per_unit_wei` from the caller to the treasury using `AIC.transfer_from` when the paid portion is greater than zero.
- Stores the new usage total for `(caller, epoch)` so subsequent calls can see the updated consumption.

See [`src/contracts/usage/UsageManager.cairo`](../../tokenxllm/src/contracts/usage/UsageManager.cairo) for the full implementation.

## Running the walkthrough

1. Inspect the current usage and allowance for your account:
   ```bash
   python tokenxllm/tokenxllm.py used
   python tokenxllm/tokenxllm.py allowance
   ```
   The example expects some free quota to remain in the current epoch so it can demonstrate both behaviours. If the free quota is exhausted, wait for the next epoch or lower the first call's units with the `--free-call-units` flag.
2. Run the example script (it defaults to one free-sized call followed by a paid call that exceeds the free quota):
   ```bash
   python examples/free_vs_paid/example_free_paid.py
   ```
   You can override the unit counts if you need to adapt to your own quota configuration:
   ```bash
   python examples/free_vs_paid/example_free_paid.py --free-call-units 500 --paid-call-units 2500
   ```
3. Check the usage tracker again to verify the changes made by the script:
   ```bash
   python tokenxllm/tokenxllm.py used
   ```
   The script prints the allowance deltas so you can confirm that the first call did not consume allowance while the second call triggered the ERC-20 `transfer_from` for the paid units.

