"""Self-check for the polling set: entries follow the shortlist, exits follow what we hold."""

from job_positions import polling_addresses


def _pos(trader, coin):
    return {"trader": trader, "coin": coin, "side": "LONG"}


def test_shortlist_only_when_flat():
    addresses, entries = polling_addresses(["a", "b"], {})
    assert addresses == ["a", "b"]
    assert entries == {"a", "b"}


def test_dropped_trader_still_polled_while_held():
    held = {"x:BTC:LONG": _pos("x", "BTC")}
    addresses, entries = polling_addresses(["a", "b"], held)
    assert "x" in addresses, "a trader we still hold must keep being polled"
    assert "x" not in entries, "but must not open new positions"


def test_held_trader_not_duplicated_when_also_shortlisted():
    held = {"a:BTC:LONG": _pos("a", "BTC")}
    addresses, _ = polling_addresses(["a", "b"], held)
    assert addresses == ["a", "b"]
    assert len(addresses) == len(set(addresses))


def test_shortlist_order_preserved_and_extras_appended():
    held = {"z:ETH:SHORT": _pos("z", "ETH"), "y:SOL:LONG": _pos("y", "SOL")}
    addresses, _ = polling_addresses(["b", "a"], held)
    assert addresses[:2] == ["b", "a"], "shortlist keeps its ranking order"
    assert addresses[2:] == ["y", "z"], "held-only traders appended, sorted"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("all checks passed")
