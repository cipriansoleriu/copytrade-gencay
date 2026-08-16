# copytrade

Adaptive paper copy-trading on Hyperliquid.

Every day the leaderboard is re-scored and the top 5 traders become the follow list.
Every 5 minutes their open positions are polled; new and closed positions become
signals, which a paper engine executes against a $10,000 mock portfolio
(5% of cash per signal, 3x leverage cap, 5 bps slippage). Every 30 minutes a PnL
summary is posted to Slack.

No real money. See `CLAUDE.md` for the full spec, scoring logic and decision log.

## Jobs

| Script | Cadence | Does |
|---|---|---|
| `job_daily.py` | daily | leaderboard → filter + score → `active_wallets.json` |
| `job_positions.py` | every 5 min | poll positions → diff → `signals.json` → paper trades |
| `daily_report.py` | every 30 min | portfolio → Slack |

Runs as three GitHub Actions workflows, triggered by cron-job.org via
`workflow_dispatch`. State files are committed back to `main` so runs share
continuity.

## Local

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

python3 job_daily.py
python3 job_positions.py
python3 paper_engine.py summary
DRY_RUN=1 python3 daily_report.py
```
