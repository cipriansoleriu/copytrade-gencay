"""Mock execution engine. No real money."""

import json
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).parent
PORTFOLIO_FILE = ROOT / "portfolio.json"
TRADES_FILE = ROOT / "paper_trades.json"
SIGNALS_FILE = ROOT / "signals.json"

STARTING_CASH = 10_000.0
POSITION_PCT = 0.05
SLIPPAGE_BPS = 5
MAX_LEVERAGE = 3


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(path: Path, default):
    return json.loads(path.read_text()) if path.exists() else default


def get_mark_prices() -> dict[str, float]:
    resp = requests.post(
        "https://api.hyperliquid.xyz/info",
        json={"type": "allMids"},
        headers={"Content-Type": "application/json"},
        timeout=20,
    )
    resp.raise_for_status()
    return {coin: float(px) for coin, px in resp.json().items()}


def load_portfolio() -> dict:
    return _load(
        PORTFOLIO_FILE,
        {
            "cash": STARTING_CASH,
            "starting_cash": STARTING_CASH,
            "open_positions": {},
            "equity_history": [],
            "last_processed_signal_index": -1,
        },
    )


def save_portfolio(portfolio: dict) -> None:
    PORTFOLIO_FILE.write_text(json.dumps(portfolio, indent=2))


def position_key(signal: dict) -> str:
    return f"{signal['trader']}:{signal['coin']}:{signal['side']}"


def apply_slippage(mark: float, side: str) -> float:
    """LONG fills above mid, SHORT below."""
    bps = SLIPPAGE_BPS / 10_000
    return mark * (1 + bps) if side == "LONG" else mark * (1 - bps)


def open_position(portfolio: dict, signal: dict, mark: float) -> dict | None:
    key = position_key(signal)
    if key in portfolio["open_positions"]:
        return None

    leverage = min(int(float(signal.get("leverage") or 1)), MAX_LEVERAGE)
    leverage = max(leverage, 1)
    notional = portfolio["cash"] * POSITION_PCT * leverage
    margin = notional / leverage
    if margin > portfolio["cash"] or notional <= 0:
        return None

    fill_price = apply_slippage(mark, signal["side"])
    position = {
        "trader": signal["trader"],
        "coin": signal["coin"],
        "side": signal["side"],
        "size": notional / fill_price,
        "entry_price": fill_price,
        "notional": notional,
        "margin": margin,
        "leverage": leverage,
        "opened_at": _now(),
    }
    portfolio["open_positions"][key] = position
    portfolio["cash"] -= margin
    return position


def close_position(portfolio: dict, signal: dict, mark: float) -> dict | None:
    position = portfolio["open_positions"].pop(position_key(signal), None)
    if position is None:
        return None

    exit_price = apply_slippage(mark, "SHORT" if position["side"] == "LONG" else "LONG")
    if position["side"] == "LONG":
        pnl = (exit_price - position["entry_price"]) * position["size"]
    else:
        pnl = (position["entry_price"] - exit_price) * position["size"]

    portfolio["cash"] += position["margin"] + pnl
    trade = {
        **position,
        "exit_price": exit_price,
        "closed_at": _now(),
        "pnl": pnl,
        "pnl_pct": pnl / position["margin"] * 100 if position["margin"] else 0.0,
    }
    trades = _load(TRADES_FILE, [])
    trades.append(trade)
    TRADES_FILE.write_text(json.dumps(trades, indent=2))
    return trade


def compute_equity(portfolio: dict, marks: dict[str, float]) -> float:
    equity = portfolio["cash"]
    for position in portfolio["open_positions"].values():
        mark = marks.get(position["coin"])
        if mark is None:
            equity += position["margin"]
            continue
        if position["side"] == "LONG":
            unrealized = (mark - position["entry_price"]) * position["size"]
        else:
            unrealized = (position["entry_price"] - mark) * position["size"]
        equity += position["margin"] + unrealized
    return equity


def apply_new_signals() -> list[dict]:
    signals = _load(SIGNALS_FILE, [])
    portfolio = load_portfolio()
    start = portfolio.get("last_processed_signal_index", -1) + 1
    marks = get_mark_prices()

    applied = []
    for signal in signals[start:]:
        mark = marks.get(signal["coin"])
        if mark is None:
            continue
        if signal["type"] == "NEW":
            result = open_position(portfolio, signal, mark)
        elif signal["type"] == "CLOSED":
            result = close_position(portfolio, signal, mark)
        else:
            result = None
        if result:
            applied.append({"type": signal["type"], **result})

    portfolio["last_processed_signal_index"] = len(signals) - 1
    equity = compute_equity(portfolio, marks)
    portfolio["equity_history"].append(
        {"ts": _now(), "equity": equity, "cash": portfolio["cash"]}
    )
    save_portfolio(portfolio)
    return applied


def summary() -> None:
    portfolio = load_portfolio()
    marks = get_mark_prices()
    equity = compute_equity(portfolio, marks)
    start = portfolio["starting_cash"]
    print(f"Equity:   ${equity:,.2f}  ({(equity - start) / start * 100:+.2f}%)")
    print(f"Cash:     ${portfolio['cash']:,.2f}")
    print(f"Open:     {len(portfolio['open_positions'])} positions")
    for key, p in portfolio["open_positions"].items():
        mark = marks.get(p["coin"], p["entry_price"])
        print(
            f"  {p['side']:5} {p['coin']:6} size={p['size']:.4f} "
            f"entry=${p['entry_price']:,.4f} mark=${mark:,.4f} x{p['leverage']}"
        )
    print(f"Closed:   {len(_load(TRADES_FILE, []))} paper trades")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "summary":
        summary()
    else:
        print(f"Applied {len(apply_new_signals())} signals")
