"""JOB C — read-only PnL summary posted to Slack."""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).parent


def _load(name: str, default):
    path = ROOT / name
    return json.loads(path.read_text()) if path.exists() else default


def _parse(ts: str) -> datetime:
    dt = datetime.fromisoformat(ts)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _age(ts: str, now: datetime) -> str:
    minutes = int((now - _parse(ts)).total_seconds() // 60)
    if minutes < 1:
        return "just now"
    if minutes < 60:
        return f"{minutes}m ago"
    return f"{minutes // 60}h {minutes % 60:02d}m ago"


def build_message() -> str:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=24)

    portfolio = _load("portfolio.json", {})
    history = portfolio.get("equity_history", [])
    starting_cash = portfolio.get("starting_cash", 10_000.0)
    equity = history[-1]["equity"] if history else starting_cash

    past = [h for h in history if _parse(h["ts"]) <= cutoff]
    equity_24h_ago = past[-1]["equity"] if past else starting_cash

    pnl_24h = equity - equity_24h_ago
    pnl_all = equity - starting_cash

    trades = _load("paper_trades.json", [])
    trades_24h = [t for t in trades if _parse(t["closed_at"]) > cutoff]
    realized_24h = sum(t["pnl"] for t in trades_24h)

    signals = _load("signals.json", [])
    signals_24h = [s for s in signals if _parse(s["ts"]) > cutoff]
    new_24h = sum(1 for s in signals_24h if s["type"] == "NEW")
    closed_24h = sum(1 for s in signals_24h if s["type"] == "CLOSED")

    open_positions = portfolio.get("open_positions", {})
    traders = _load("active_wallets.json", {}).get("top_traders", [])

    lines = [
        f"*📈 Copytrade report — {now:%Y-%m-%d %H:%M} UTC*",
        "",
        f"*Portfolio:* `${equity:,.2f}`  (24h ago: `${equity_24h_ago:,.2f}`)",
        f"*24h PnL:* `{pnl_24h:+,.2f}` USD  (`{pnl_24h / equity_24h_ago * 100:+.2f}%`)",
        f"*All-time:* `{pnl_all:+,.2f}` USD  (`{pnl_all / starting_cash * 100:+.2f}%`)"
        f"  — start `${starting_cash:,.0f}`",
        "",
        "*Last 24h activity:*",
        f"• Signals: {new_24h} NEW, {closed_24h} CLOSED",
        f"• Closed paper trades: {len(trades_24h)}  (realized PnL: `{realized_24h:+,.2f}` USD)",
        f"• Open positions: {len(open_positions)}",
        "",
        "*Last activity:*",
    ]

    if signals:
        s = signals[-1]
        lines.append(
            f"• Last signal: {_age(s['ts'], now)} — {s['type']} {s['side']} {s['coin']} "
            f"({s['trader'][:10]}...)"
        )
    else:
        lines.append("• Last signal: none yet")

    if trades:
        t = trades[-1]
        lines.append(
            f"• Last paper trade closed: {_age(t['closed_at'], now)} — "
            f"{t['side']} {t['coin']} PnL `{t['pnl']:+,.2f}` USD"
        )
    else:
        lines.append("• Last paper trade closed: none yet")

    lines += ["", f"*Following:* {len(traders)} traders"]

    if open_positions:
        lines += ["", "*Open positions:*"]
        for p in list(open_positions.values())[:10]:
            lines.append(
                f"• {p['side']} {p['coin']}  size=`{p['size']:.4f}`  "
                f"entry=`${p['entry_price']:,.4f}`  x{p['leverage']}"
            )
        if len(open_positions) > 10:
            lines.append(f"• … and {len(open_positions) - 10} more")

    return "\n".join(lines)


def main() -> int:
    message = build_message()

    if os.environ.get("DRY_RUN"):
        print(message)
        return 0

    webhook = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook:
        print("ERROR: SLACK_WEBHOOK_URL not set", file=sys.stderr)
        return 1

    resp = requests.post(webhook, json={"text": message}, timeout=20)
    resp.raise_for_status()
    print("Report posted to Slack")
    return 0


if __name__ == "__main__":
    sys.exit(main())
