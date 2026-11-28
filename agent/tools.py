"""
The agent's tools. Each one calls a function in brightwater_data.py and hands Claude the
result as JSON, so every figure Claude quotes comes from the spreadsheet, not from memory.

These are plain async functions; main.py registers them with the Agent SDK. Keeping them
separate means they can be tested without the SDK or an API key (see test_agent.py).
"""
from __future__ import annotations

import json
from typing import Any

import brightwater_data as data


def _reply(result: Any) -> dict[str, Any]:
    """Wrap a result in the format the Agent SDK expects from a tool."""
    return {"content": [{"type": "text", "text": json.dumps(result, default=str)}]}


def _safe(fn, *args, **kwargs) -> dict[str, Any]:
    try:
        return _reply(fn(*args, **kwargs))
    except Exception as exc:  # report the problem to Claude instead of crashing the session
        return _reply({"error": f"{type(exc).__name__}: {exc}"})


# Each entry: (tool name, description for Claude, input schema, handler)

async def get_store_queue(args: dict[str, Any]) -> dict[str, Any]:
    return _safe(data.store_queue, args["store_id"].upper(), int(args.get("week") or 8))


async def explain_alert(args: dict[str, Any]) -> dict[str, Any]:
    return _safe(data.explain_alert, args["alert_id"].upper())


async def get_store_summary(args: dict[str, Any]) -> dict[str, Any]:
    return _safe(data.store_summary, args["store_id"].upper())


async def get_district_summary(args: dict[str, Any]) -> dict[str, Any]:
    return _safe(data.district_summary, args["district"].upper(), int(args.get("last_weeks") or 8))


async def query_alerts(args: dict[str, Any]) -> dict[str, Any]:
    return _safe(data.query_alerts, **{k: v for k, v in args.items() if v not in (None, "")})


async def get_chain_overview(args: dict[str, Any]) -> dict[str, Any]:
    return _safe(data.chain_overview)


TOOL_SPECS = [
    ("get_store_queue",
     "Get one store's alerts for a week (1-8; 8 = Oct 19-25, 2026) in the new review order: "
     "High, Medium, Low, then highest dollar amount, then oldest. Use it to say what a manager should review first.",
     {"type": "object", "properties": {"store_id": {"type": "string", "description": "e.g. S057"},
                                       "week": {"type": "integer", "minimum": 1, "maximum": 8}},
      "required": ["store_id"]},
     get_store_queue),
    ("explain_alert",
     "Get the full details of one alert: tier and reason, how often that alert type is a real problem, "
     "the cashier's other alerts, and draft notes on what to check.",
     {"type": "object", "properties": {"alert_id": {"type": "string", "description": "e.g. A105590"}},
      "required": ["alert_id"]},
     explain_alert),
    ("get_store_summary",
     "Get how well one store keeps up over 8 weeks: review rate, real (over 30 second) review rate, "
     "rushed reviews, confirmed issues, and results by tier.",
     {"type": "object", "properties": {"store_id": {"type": "string"}}, "required": ["store_id"]},
     get_store_summary),
    ("get_district_summary",
     "Get review rates for every store in a district (D1-D8), compared with other districts, "
     "plus the stores most worth a follow-up.",
     {"type": "object", "properties": {"district": {"type": "string", "description": "D1 to D8"},
                                       "last_weeks": {"type": "integer", "minimum": 1, "maximum": 8}},
      "required": ["district"]},
     get_district_summary),
    ("query_alerts",
     "Answer a data question with one metric, optionally filtered and grouped. "
     "Metrics: alerts, review_rate, real_review_rate, confirmed_rate_when_reviewed, confirmed_issues, "
     "confirmed_dollars, rushed_share_of_reviews, median_amount. "
     "Group by: district, store_id, alert_type, tier, week, reviewer_role, status. "
     "Alert types: No-receipt refund, Manual card entry, Post-void, Employee discount, Price override.",
     {"type": "object", "properties": {
         "metric": {"type": "string"}, "group_by": {"type": "string"},
         "district": {"type": "string"}, "store_id": {"type": "string"},
         "alert_type": {"type": "string"}, "tier": {"type": "string", "enum": ["High", "Medium", "Low"]},
         "week_from": {"type": "integer"}, "week_to": {"type": "integer"},
         "min_amount": {"type": "number"}, "max_amount": {"type": "number"}},
      "required": ["metric"]},
     query_alerts),
    ("get_chain_overview",
     "Get headline numbers for all 120 stores over the 8 weeks (Aug 31 - Oct 25, 2026).",
     {"type": "object", "properties": {}},
     get_chain_overview),
]
