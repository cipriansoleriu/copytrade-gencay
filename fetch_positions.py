"""Hyperliquid per-wallet position and fill readers."""

import requests

INFO_URL = "https://api.hyperliquid.xyz/info"
SIDE_MAP = {"B": "BUY", "A": "SELL"}


def _post(payload: dict):
    resp = requests.post(
        INFO_URL,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()


def get_open_positions(address: str) -> dict:
    data = _post({"type": "clearinghouseState", "user": address})
    positions = []
    for entry in data.get("assetPositions", []):
        p = entry["position"]
        szi = float(p["szi"])
        if szi == 0:
            continue
        positions.append(
            {
                "coin": p["coin"],
                "side": "LONG" if szi > 0 else "SHORT",
                "size": abs(szi),
                "entry_price": float(p["entryPx"]),
                "position_value_usd": float(p["positionValue"]),
                "leverage": p["leverage"]["value"],
                "unrealized_pnl": float(p["unrealizedPnl"]),
                "liquidation_price": float(p["liquidationPx"] or 0),
            }
        )
    return {
        "account_value": float(data["marginSummary"]["accountValue"]),
        "positions": positions,
        "timestamp_ms": data["time"],
    }


def get_recent_fills(address: str, limit: int = 50) -> list[dict]:
    fills = _post({"type": "userFills", "user": address})
    return [
        {
            "coin": f["coin"],
            "side": SIDE_MAP.get(f["side"], f["side"]),
            "price": float(f["px"]),
            "size": float(f["sz"]),
            "time_ms": f["time"],
            "closed_pnl": float(f.get("closedPnl", 0)),
        }
        for f in fills[:limit]
    ]


if __name__ == "__main__":
    import sys

    print(get_open_positions(sys.argv[1]))
