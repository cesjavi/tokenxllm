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
    monkeypatch.setattr(main, "_FAUCET_LAST_CLAIMS", {})


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


def test_config_includes_faucet(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "FAUCET_ENABLED", True)
    monkeypatch.setattr(main, "FAUCET_COOLDOWN_SECONDS", 3600)
    monkeypatch.setattr(main, "FAUCET_AMOUNT_AIC", Decimal("123.45"))
    monkeypatch.setattr(main, "_writes_enabled", lambda: True)
    monkeypatch.setattr(main, "_account_address_hex", lambda: "0xbeef")

    payload = asyncio.run(main.config())
    faucet = payload.get("faucet")
    assert faucet is not None
    assert faucet["enabled"] is True
    assert faucet["writes_enabled"] is True
    assert faucet["cooldown_seconds"] == 3600
    assert faucet["amount_AIC"] == "123.45"
    expected_wei = str(main._tokens_to_wei(Decimal("123.45"), main.DECIMALS))
    assert faucet["amount_wei"] == expected_wei


def test_faucet_request_requires_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "FAUCET_ENABLED", True)
    monkeypatch.setattr(main, "FAUCET_COOLDOWN_SECONDS", 10)
    monkeypatch.setattr(main, "FAUCET_AMOUNT_AIC", Decimal("1"))
    monkeypatch.setattr(main, "_writes_enabled", lambda: False)

    with pytest.raises(main.HTTPException) as excinfo:
        asyncio.run(main.faucet_request(main.FaucetRequest(to="0x1")))

    assert excinfo.value.status_code == 400


def test_faucet_request_enforces_cooldown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "FAUCET_ENABLED", True)
    monkeypatch.setattr(main, "FAUCET_COOLDOWN_SECONDS", 120)
    monkeypatch.setattr(main, "FAUCET_AMOUNT_AIC", Decimal("5"))
    monkeypatch.setattr(main, "_writes_enabled", lambda: True)

    current_time = {"value": 1000.0}

    def fake_now() -> float:
        return current_time["value"]

    monkeypatch.setattr(main, "_current_timestamp", fake_now)

    tx_calls: list[tuple[str, str, list[int]]] = []

    async def fake_invoke(addr: str, fn: str, calldata: list[int]) -> str:
        tx_calls.append((addr, fn, calldata))
        return "0xdead"

    monkeypatch.setattr(main, "_invoke", fake_invoke)

    request = main.FaucetRequest(to="0x123")

    expected_amount = main._tokens_to_wei(Decimal("5"), main.DECIMALS)
    expected_lo, expected_hi = main._to_u256(expected_amount)

    first_response = asyncio.run(main.faucet_request(request))
    assert first_response["tx_hash"] == "0xdead"
    assert first_response["seconds_remaining"] == main.FAUCET_COOLDOWN_SECONDS
    assert tx_calls == [("0xabc", "mint", [main._h("0x123"), expected_lo, expected_hi])]

    stored = main._FAUCET_LAST_CLAIMS.get("0x123".lower())
    assert stored == pytest.approx(1000.0)

    current_time["value"] = 1000.0 + main.FAUCET_COOLDOWN_SECONDS - 1

    with pytest.raises(main.HTTPException) as excinfo:
        asyncio.run(main.faucet_request(request))

    assert excinfo.value.status_code == 429
    detail = excinfo.value.detail
    assert isinstance(detail, dict)
    assert detail["seconds_remaining"] > 0
    assert main._FAUCET_LAST_CLAIMS.get("0x123".lower()) == pytest.approx(1000.0)

    current_time["value"] = 1000.0 + main.FAUCET_COOLDOWN_SECONDS + 1
    second_response = asyncio.run(main.faucet_request(request))
    assert second_response["tx_hash"] == "0xdead"
    assert tx_calls == [
        ("0xabc", "mint", [main._h("0x123"), expected_lo, expected_hi]),
        ("0xabc", "mint", [main._h("0x123"), expected_lo, expected_hi]),
    ]
    assert main._FAUCET_LAST_CLAIMS.get("0x123".lower()) == pytest.approx(current_time["value"])
