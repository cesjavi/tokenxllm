import asyncio
from decimal import Decimal
from pathlib import Path
import sys

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import main  # type: ignore  # noqa: E402


LARGE_DECIMAL = Decimal("123456789012345678901234567890.123456789012345678")
EXPECTED_DECIMAL_STR = str(LARGE_DECIMAL)


def _decimal_to_wei_parts(value: Decimal) -> tuple[int, int, int]:
    amount_wei = main._tokens_to_wei(value, main.DECIMALS)
    low, high = main._to_u256(amount_wei)
    return amount_wei, low, high


@pytest.fixture(autouse=True)
def _stub_required_addresses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "_require_env_addr", lambda _value, _name: "0xabc")


def test_balance_large_value_precision(monkeypatch: pytest.MonkeyPatch) -> None:
    amount_wei, low, high = _decimal_to_wei_parts(LARGE_DECIMAL)

    async def fake_read(addr: str, fn: str, calldata: list[int]) -> list[int]:
        assert fn == "balance_of"
        assert calldata == [1]
        return [low, high]

    monkeypatch.setattr(main, "_read", fake_read)

    payload = asyncio.run(main.balance("0x1"))
    assert payload["balance_wei"] == str(amount_wei)
    assert payload["balance_AIC"] == EXPECTED_DECIMAL_STR
    assert isinstance(payload["balance_AIC"], str)
    assert Decimal(payload["balance_AIC"]) == LARGE_DECIMAL


def test_allowance_large_value_precision(monkeypatch: pytest.MonkeyPatch) -> None:
    amount_wei, low, high = _decimal_to_wei_parts(LARGE_DECIMAL)

    async def fake_read(addr: str, fn: str, calldata: list[int]) -> list[int]:
        assert fn == "allowance"
        assert calldata == [1, 2]
        return [low, high]

    monkeypatch.setattr(main, "_read", fake_read)

    payload = asyncio.run(main.allowance("0x1", "0x2"))
    assert payload["allowance_wei"] == str(amount_wei)
    assert payload["allowance_AIC"] == EXPECTED_DECIMAL_STR
    assert isinstance(payload["allowance_AIC"], str)
    assert Decimal(payload["allowance_AIC"]) == LARGE_DECIMAL
