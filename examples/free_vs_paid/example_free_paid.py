#!/usr/bin/env python3
"""Demonstrate the free-versus-paid behaviour of UsageManager.authorize_usage."""

import argparse
import asyncio
import os
from decimal import Decimal, getcontext

from starknet_py.hash.storage import get_storage_var_address

from tokenxllm.tokenxllm import (
    call_u64,
    call_u256,
    do_authorize,
    make_client_and_account,
    resolve_address,
    req,
    h,
)

getcontext().prec = 60


def format_tokens(value: int, scale: Decimal) -> str:
    return f"{Decimal(value) / scale:f}"


async def read_free_quota(client, usage_manager_hex: str) -> int:
    key = get_storage_var_address("UsageManager_free_quota_per_epoch")
    return await client.get_storage_at(contract_address=h(usage_manager_hex), key=key)


async def read_price_per_unit(client, usage_manager_hex: str) -> int:
    base_key = get_storage_var_address("UsageManager_price_per_unit_wei")
    low = await client.get_storage_at(contract_address=h(usage_manager_hex), key=base_key)
    high = await client.get_storage_at(contract_address=h(usage_manager_hex), key=base_key + 1)
    return (high << 128) + low


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Call authorize_usage twice to show how free quota and paid transfers interact."
    )
    parser.add_argument(
        "--free-call-units",
        type=int,
        default=None,
        help="Units for the first (free) authorize_usage call. Default: stays within remaining free quota.",
    )
    parser.add_argument(
        "--paid-call-units",
        type=int,
        default=None,
        help="Units for the second (paid) authorize_usage call. Default: exceeds the free quota.",
    )
    args = parser.parse_args()

    client, account = await make_client_and_account()
    print(f"Signer account: 0x{account.address:064x}")

    owner_hex = resolve_address(None)
    if owner_hex.lower() != f"0x{account.address:064x}".lower():
        print(f"Resolved address for usage tracking: {owner_hex}")

    aic_addr = req("AIC_ADDR")
    um_addr = req("UM_ADDR")
    decimals = int(os.getenv("AIC_DECIMALS", "18"))
    scale = Decimal(10) ** decimals

    free_quota = await read_free_quota(client, um_addr)
    price_per_unit_wei = await read_price_per_unit(client, um_addr)
    price_per_unit_tokens = Decimal(price_per_unit_wei) / scale

    print(f"Free quota per epoch: {free_quota} units")
    print(
        "Price per paid unit: "
        f"{price_per_unit_wei} wei ({format_tokens(price_per_unit_wei, scale)} AIC)"
    )

    used_before = await call_u64(client, um_addr, "used_in_current_epoch", [h(owner_hex)])
    allowance_before = await call_u256(
        client, aic_addr, "allowance", [h(owner_hex), h(um_addr)]
    )

    free_remaining_before = max(free_quota - used_before, 0)
    print(
        "used_in_current_epoch before: "
        f"{used_before} units (free remaining: {free_remaining_before})"
    )
    print(
        "Allowance before: "
        f"{allowance_before} wei ({format_tokens(allowance_before, scale)} AIC)"
    )

    if args.free_call_units is not None:
        free_call_units = args.free_call_units
    else:
        if free_remaining_before == 0:
            raise RuntimeError(
                "No free quota remaining in the current epoch. "
                "Pass --free-call-units to override or wait for the next epoch."
            )
        free_call_units = min(free_remaining_before, max(free_quota // 2, 1))

    if free_call_units < 0:
        raise ValueError("free-call-units must be non-negative")
    if free_call_units > free_remaining_before:
        print(
            "Warning: first call requests more units than the remaining free quota. "
            "The demo may not show a purely free call."
        )

    print(
        f"\nCalling authorize_usage({free_call_units}) for the free-quota scenario..."
    )
    await do_authorize(free_call_units)

    used_after_free = await call_u64(
        client, um_addr, "used_in_current_epoch", [h(owner_hex)]
    )
    allowance_after_free = await call_u256(
        client, aic_addr, "allowance", [h(owner_hex), h(um_addr)]
    )

    used_delta_free = used_after_free - used_before
    allowance_delta_free = allowance_before - allowance_after_free

    print(
        "After first call: "
        f"used={used_after_free} (delta {used_delta_free}), "
        f"allowance delta={allowance_delta_free} wei"
    )
    if allowance_delta_free == 0:
        print("As expected, the free portion did not consume any allowance.")
    else:
        print(
            "Warning: allowance changed during the free call (check your quota configuration)."
        )

    free_remaining_after_free = max(free_quota - used_after_free, 0)

    if args.paid_call_units is not None:
        paid_call_units = args.paid_call_units
    else:
        paid_call_units = free_quota + max(free_quota // 2, 1)

    if paid_call_units <= free_remaining_after_free:
        paid_call_units = free_remaining_after_free + 1
        print(
            "Adjusted paid-call-units to "
            f"{paid_call_units} to exceed remaining free quota."
        )

    if paid_call_units < 0:
        raise ValueError("paid-call-units must be non-negative")

    print(f"\nCalling authorize_usage({paid_call_units}) for the paid scenario...")
    await do_authorize(paid_call_units)

    used_after_paid = await call_u64(
        client, um_addr, "used_in_current_epoch", [h(owner_hex)]
    )
    allowance_after_paid = await call_u256(
        client, aic_addr, "allowance", [h(owner_hex), h(um_addr)]
    )

    used_delta_paid_call = used_after_paid - used_after_free
    allowance_delta_paid = allowance_after_free - allowance_after_paid

    free_consumed_second = min(paid_call_units, free_remaining_after_free)
    paid_units = paid_call_units - free_consumed_second
    expected_cost = price_per_unit_wei * paid_units

    print(
        "After second call: "
        f"used={used_after_paid} (delta {used_delta_paid_call}), "
        f"allowance delta={allowance_delta_paid} wei"
    )
    print(
        "Paid units in second call: "
        f"{paid_units} (free carried over: {free_consumed_second})"
    )
    print(
        "Expected cost: "
        f"{expected_cost} wei ({format_tokens(expected_cost, scale)} AIC)"
    )
    if allowance_delta_paid == expected_cost:
        print("Allowance drop matches the on-chain price configuration.")
    else:
        print(
            "Warning: allowance delta does not match the expected paid cost. "
            "Double-check the quota and price configuration."
        )

    print(
        "\nFinal allowance: "
        f"{allowance_after_paid} wei ({format_tokens(allowance_after_paid, scale)} AIC)"
    )
    print(f"Final used_in_current_epoch: {used_after_paid} units")
    print(
        "\nYou can re-run `python tokenxllm/tokenxllm.py used` and "
        "`python tokenxllm/tokenxllm.py allowance` to cross-check the values above."
    )


if __name__ == "__main__":
    asyncio.run(main())
