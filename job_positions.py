"""JOB B — every 5 min. Poll positions, diff, emit signals, run the paper engine."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import fetch_positions
import notes
import paper_engine

ROOT = Path(__file__).parent
LOG_FILE = ROOT / "logs" / "job_positions.log"
STATE_DIR = ROOT / "state"
ACTIVE_WALLETS = ROOT / "active_wallets.json"
SIGNALS_FILE = ROOT / "signals.json"


def log(msg: str) -> None:
    line = f"[{datetime.now(timezone.utc).isoformat()}] {msg}"
    print(line)
    LOG_FILE.parent.mkdir(exist_ok=True)
    with LOG_FILE.open("a") as f:
        f.write(line + "\n")


def _by_key(positions: list[dict]) -> dict[str, dict]:
    return {f"{p['coin']}:{p['side']}": p for p in positions}


def polling_addresses(shortlist: list[str], open_positions: dict) -> tuple[list[str], set[str]]:
    """Poll the shortlist plus anyone whose position we still hold.

    A trader who drops off the shortlist stops being polled, so their exit never
    produces a CLOSED signal and the paper position stays open forever with its
    margin locked. Entries still come from the shortlist only — we follow current
    winners in, but we follow whoever we copied out.
    """
    held = {p["trader"] for p in open_positions.values()}
    entries = set(shortlist)
    return shortlist + sorted(held - entries), entries


def main() -> int:
    if not ACTIVE_WALLETS.exists():
        log("active_wallets.json missing — Job A hasn't run yet, skipping")
        return 0

    shortlist = [t["address"] for t in json.loads(ACTIVE_WALLETS.read_text())["top_traders"]]
    portfolio = paper_engine.load_portfolio()
    addresses, entry_allowed = polling_addresses(shortlist, portfolio["open_positions"])
    log(f"Polling {len(shortlist)} shortlisted + {len(addresses) - len(shortlist)} held-only traders")

    STATE_DIR.mkdir(exist_ok=True)
    signals = json.loads(SIGNALS_FILE.read_text()) if SIGNALS_FILE.exists() else []
    new_signals = []

    for addr in addresses:
        try:
            state = fetch_positions.get_open_positions(addr)
        except Exception as exc:
            log(f"poll failed for {addr}: {exc}")
            continue

        state_file = STATE_DIR / f"{addr}.json"
        prior = json.loads(state_file.read_text())["positions"] if state_file.exists() else []
        curr_by_key, prior_by_key = _by_key(state["positions"]), _by_key(prior)
        ts = datetime.now(timezone.utc).isoformat()

        for key, p in curr_by_key.items():
            if key not in prior_by_key and addr in entry_allowed:
                new_signals.append({"ts": ts, "trader": addr, "type": "NEW", **p})
        for key, p in prior_by_key.items():
            if key not in curr_by_key:
                new_signals.append({"ts": ts, "trader": addr, "type": "CLOSED", **p})

        state_file.write_text(json.dumps(state, indent=2))

    if new_signals:
        signals.extend(new_signals)
        SIGNALS_FILE.write_text(json.dumps(signals, indent=2))
    log(f"{len(new_signals)} new signals")

    try:
        applied = paper_engine.apply_new_signals()
        log(f"Paper engine applied {len(applied)} signals")
    except Exception as exc:
        log(f"paper engine failed: {exc}")
        applied = []

    if new_signals:
        lines = [f"{len(new_signals)} signals ({len(applied)} applied to the paper book)"]
        for s in new_signals:
            lines.append(
                f"{s['type']} {s['side']} {s['coin']} x{s['leverage']} — {s['trader'][:10]}..."
            )
        portfolio = paper_engine.load_portfolio()
        if portfolio["equity_history"]:
            equity = portfolio["equity_history"][-1]["equity"]
            start = portfolio["starting_cash"]
            lines.append(
                f"Portfolio: ${equity:,.2f} ({(equity - start) / start * 100:+.2f}%)"
            )
        notes.append_entry("Position poll (Job B)", lines)

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        log(f"FAILED: {exc}")
        raise
