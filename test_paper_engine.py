"""Self-check for the money path: slippage direction, PnL signs, cash accounting."""

import tempfile
from pathlib import Path

import paper_engine as pe


def test_slippage_direction():
    assert pe.apply_slippage(100.0, "LONG") > 100.0
    assert pe.apply_slippage(100.0, "SHORT") < 100.0


def test_long_profit_and_cash():
    portfolio = pe.load_portfolio()
    cash_before = portfolio["cash"]
    signal = {"trader": "0xabc", "coin": "BTC", "side": "LONG", "leverage": 10}

    position = pe.open_position(portfolio, signal, 100.0)
    assert position["leverage"] == pe.MAX_LEVERAGE, "leverage must be capped"
    assert position["margin"] == cash_before * pe.POSITION_PCT
    assert portfolio["cash"] == cash_before - position["margin"]

    trade = pe.close_position(portfolio, {**signal, "type": "CLOSED"}, 110.0)
    assert trade["pnl"] > 0, "LONG into a higher mark must profit"
    assert portfolio["open_positions"] == {}
    assert portfolio["cash"] > cash_before


def test_short_profit_and_loss():
    portfolio = pe.load_portfolio()
    signal = {"trader": "0xabc", "coin": "ETH", "side": "SHORT", "leverage": 1}

    pe.open_position(portfolio, signal, 100.0)
    assert pe.close_position(portfolio, signal, 90.0)["pnl"] > 0

    pe.open_position(portfolio, signal, 100.0)
    assert pe.close_position(portfolio, signal, 110.0)["pnl"] < 0


def test_round_trip_at_flat_price_loses_slippage_only():
    portfolio = pe.load_portfolio()
    cash_before = portfolio["cash"]
    signal = {"trader": "0xabc", "coin": "SOL", "side": "LONG", "leverage": 1}

    pe.open_position(portfolio, signal, 100.0)
    pe.close_position(portfolio, signal, 100.0)

    loss = cash_before - portfolio["cash"]
    assert 0 < loss < cash_before * pe.POSITION_PCT * 0.01, "flat round trip costs ~10 bps"


def test_equity_matches_cash_when_flat():
    portfolio = pe.load_portfolio()
    assert pe.compute_equity(portfolio, {}) == portfolio["cash"]


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        pe.PORTFOLIO_FILE = Path(tmp) / "portfolio.json"
        pe.TRADES_FILE = Path(tmp) / "paper_trades.json"
        pe.SIGNALS_FILE = Path(tmp) / "signals.json"

        for name, fn in sorted(globals().items()):
            if name.startswith("test_"):
                fn()
                print(f"ok  {name}")
    print("all checks passed")
