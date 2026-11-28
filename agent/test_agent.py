"""
Checks the agent's tools against the numbers in the take-home write-up.
Runs without an API key or the Agent SDK:  python test_agent.py   (or: pytest test_agent.py)
"""
import asyncio
import json

import tools


def call(handler, **args):
    result = asyncio.run(handler(args))
    return json.loads(result["content"][0]["text"])


def test_queue_order_matches_uat_1():
    q = call(tools.get_store_queue, store_id="s057")
    assert q["counts_by_tier"] == {"High": 5, "Medium": 1, "Low": 6}
    assert [a["amount"] for a in q["alerts"][:6]] == [195.39, 195.26, 147.96, 108.36, 20.56, 57.22]


def test_low_tier_order_matches_uat_4():
    q = call(tools.get_store_queue, store_id="S057")
    assert [a["amount"] for a in q["alerts"] if a["tier"] == "Low"] == [36.40, 34.54, 26.39, 18.89, 13.48, 9.74]


def test_explain_alert_gives_rate_and_guidance():
    e = call(tools.explain_alert, alert_id="A105590")
    assert e["tier"] == "High" and e["how_often_this_type_is_real"] == 0.313
    assert "keyed" in e["draft_what_to_check"]


def test_chain_overview_matches_findings():
    o = call(tools.get_chain_overview)
    assert o["alerts"] == 11563
    assert o["review_rate"] == 0.504
    assert o["confirmed_rate_by_type"]["Price override"] == 0.035


def test_district_gap_matches_finding_1():
    d = call(tools.get_district_summary, district="D7")
    assert d["district_review_rate"] == 0.169 and d["stores"] == 15


def test_query_price_override_threshold():
    q = call(tools.query_alerts, metric="alerts", alert_type="Price override", max_amount=50)
    assert q["result"] == 3869


def test_bad_input_returns_error_not_crash():
    assert "error" in call(tools.query_alerts, metric="nonsense")
    assert "error" in call(tools.explain_alert, alert_id="A0")
    assert "error" in call(tools.get_store_summary, store_id="S999")


if __name__ == "__main__":
    tests = [f for name, f in sorted(globals().items()) if name.startswith("test_")]
    for t in tests:
        t()
        print(f"passed  {t.__name__}")
    print(f"\nAll {len(tests)} checks passed.")
