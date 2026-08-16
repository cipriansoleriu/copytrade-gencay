"""Filter + score the leaderboard, write the follow list."""

import json
import math
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
OUTPUT_FILE = ROOT / "active_wallets.json"

TOP_N = 5
FILTERS = {
    "min_account_value": 100_000,
    "min_30d_volume": 5_000_000,
    # Without a weekly floor, week_edge_bps explodes on near-zero week volume:
    # $20 traded against $94k of mark-to-market gain scores 47,008,630 bps and
    # swamps every other term, ranking the least active wallet first.
    "min_7d_volume": 100_000,
    "min_30d_pnl": 50_000,
    "max_abs_day_roi": 5.0,
    "max_day_share_of_month": 0.8,
}


def latest_snapshot() -> Path:
    today = DATA_DIR / f"leaderboard_{datetime.now(timezone.utc):%Y-%m-%d}.json"
    if today.exists():
        return today
    snapshots = sorted(DATA_DIR.glob("leaderboard_*.json"))
    if not snapshots:
        raise FileNotFoundError("no leaderboard snapshot in data/ — run fetch_leaderboard first")
    return snapshots[-1]


def _windows(row: dict) -> dict:
    return {name: stats for name, stats in row.get("windowPerformances", [])}


def score_trader(row: dict) -> dict | None:
    w = _windows(row)
    if not {"day", "week", "month"} <= w.keys():
        return None

    account_value = float(row["accountValue"])
    day_pnl, day_roi = float(w["day"]["pnl"]), float(w["day"]["roi"])
    week_pnl, week_vlm = float(w["week"]["pnl"]), float(w["week"]["vlm"])
    month_pnl, month_vlm = float(w["month"]["pnl"]), float(w["month"]["vlm"])

    if account_value < FILTERS["min_account_value"]:
        return None
    if month_vlm < FILTERS["min_30d_volume"]:
        return None
    if week_vlm < FILTERS["min_7d_volume"]:
        return None
    if month_pnl < FILTERS["min_30d_pnl"]:
        return None
    if day_pnl <= 0 or week_pnl <= 0:
        return None
    if day_pnl >= FILTERS["max_day_share_of_month"] * month_pnl:
        return None
    if abs(day_roi) > FILTERS["max_abs_day_roi"]:
        return None

    month_edge_bps = month_pnl / month_vlm * 10_000
    week_edge_bps = week_pnl / week_vlm * 10_000 if week_vlm else 0.0

    return {
        "address": row["ethAddress"],
        "account_value": account_value,
        "day_pnl": day_pnl,
        "day_roi": day_roi,
        "week_pnl": week_pnl,
        "week_roi": float(w["week"]["roi"]),
        "month_pnl": month_pnl,
        "month_roi": float(w["month"]["roi"]),
        "month_volume": month_vlm,
        "month_edge_bps": month_edge_bps,
        "week_edge_bps": week_edge_bps,
        "score": month_edge_bps * 2.0 + week_edge_bps + math.log10(max(month_pnl, 1)),
    }


def main() -> dict:
    rows = json.loads(latest_snapshot().read_text())["leaderboardRows"]
    scored = [s for s in (score_trader(r) for r in rows) if s]
    scored.sort(key=lambda s: s["score"], reverse=True)

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "filters": FILTERS,
        "top_traders": scored[:TOP_N],
    }
    OUTPUT_FILE.write_text(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    out = main()
    for i, t in enumerate(out["top_traders"], 1):
        print(
            f"#{i} {t['address'][:10]}... acc=${t['account_value']:,.0f} "
            f"month=${t['month_pnl']:,.0f} edge={t['month_edge_bps']:.0f}bps"
        )
