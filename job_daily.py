"""JOB A — once a day. Leaderboard -> shortlist."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import analyze_wallets
import fetch_leaderboard
import fetch_positions
import notes

ROOT = Path(__file__).parent
LOG_FILE = ROOT / "logs" / "job_daily.log"
ACTIVE_WALLETS = ROOT / "active_wallets.json"


def log(msg: str) -> None:
    line = f"[{datetime.now(timezone.utc).isoformat()}] {msg}"
    print(line)
    LOG_FILE.parent.mkdir(exist_ok=True)
    with LOG_FILE.open("a") as f:
        f.write(line + "\n")


def main() -> int:
    prior = []
    if ACTIVE_WALLETS.exists():
        prior = [t["address"] for t in json.loads(ACTIVE_WALLETS.read_text())["top_traders"]]

    payload = fetch_leaderboard.fetch()
    rows = len(payload.get("leaderboardRows", []))
    fetch_leaderboard.save_snapshot(payload)
    log(f"Leaderboard fetched: {rows} traders")

    result = analyze_wallets.main()
    top = result["top_traders"]
    log(f"Shortlist updated: {len(top)} traders")

    current = [t["address"] for t in top]
    added = [a for a in current if a not in prior]
    removed = [a for a in prior if a not in current]

    lines = [f"Leaderboard: {rows} traders fetched, {len(top)} shortlisted"]
    if not prior:
        lines.append("Shortlist change: first shortlist (no prior run)")
    else:
        lines.append(f"Shortlist change: +{len(added)} new, -{len(removed)} dropped")
        for a in added:
            lines.append(f"  +{a}")
        for a in removed:
            lines.append(f"  -{a}")

    for i, t in enumerate(top, 1):
        lines.append(
            f"#{i} {t['address'][:10]}... acc=${t['account_value']:,.0f} "
            f"month=${t['month_pnl']:,.0f} edge={t['month_edge_bps']:.0f}bps"
        )

    lines.append("Current positions across the shortlist:")
    for t in top:
        addr = t["address"]
        try:
            state = fetch_positions.get_open_positions(addr)
        except Exception as exc:  # network hiccup shouldn't fail the shortlist
            log(f"position snapshot failed for {addr}: {exc}")
            lines.append(f"  {addr[:10]}... position snapshot unavailable")
            continue
        positions = state["positions"]
        if not positions:
            lines.append(f"  {addr[:10]}... no open positions")
        else:
            detail = ", ".join(f"{p['side']} {p['coin']} x{p['leverage']}" for p in positions)
            lines.append(f"  {addr[:10]}... {len(positions)} positions: {detail}")

    notes.append_entry("Daily refresh (Job A)", lines)
    log("NOTES.md updated")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        log(f"FAILED: {exc}")
        raise
