"""
Brightwater alert review agent (Claude Agent SDK, Python).

One agent, three jobs. Pick a role when you start it:
  store-manager     Helps a store manager work their queue: what to review first, why an alert
                    is ranked where it is, and what to check.
  analyst           Answers plain-English questions about the alert data.
  district-summary  Writes a weekly summary for Dana and district managers.

Examples:
  python main.py --role store-manager --store S057
  python main.py --role analyst --ask "Which alert type is least often a real problem?"
  python main.py --role district-summary --district D7
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
    create_sdk_mcp_server,
    tool,
)

from tools import TOOL_SPECS

SERVER = "brightwater"  # tool names become mcp__brightwater__<tool>

COMMON = """You work for the company that makes Brightwater Market's loss-prevention product.
Brightwater has 120 stores in 8 districts. Every price override, no-receipt refund, post-void,
employee discount and manual card entry is flagged as an alert, and a manager marks each one
"Confirmed issue" or "No issue".

Rules:
- Get every number from your tools. Never estimate or invent figures. If a tool can't answer, say so.
- Tiers: High = manual card entry, no-receipt refund. Medium = post-void, employee discount.
  Low = price override. Queue order: tier, then highest dollar amount, then oldest.
- A review of 30 seconds or less counts as "rushed"; a "real review" is longer than 30 seconds.
- The data covers Aug 31 - Oct 25, 2026 (8 weeks). Week 8 is Oct 19-25.
- Write plainly, without jargon. Be brief. Use short lists or small tables only when they help.
- You can't mark alerts or change anything. You give information and advice; people decide.
"""

ROLES = {
    "store-manager": COMMON + """
You are helping a store manager during their weekly review session. Their time is limited, so:
- Start with what to review first (use get_store_queue), High alerts before anything else.
- When they ask about an alert, use explain_alert: give the reason for its tier, how often that type
  turns out to be real, anything notable about the cashier, and the draft notes on what to check.
  Say that the "what to check" notes are a draft, not official policy.
- Never tell them an alert is or isn't a real problem. That is their judgment.
- Encourage a real look at High alerts rather than a quick click.
""",
    "analyst": COMMON + """
You answer questions about the alert data for the product team.
- Use query_alerts for counts and rates, and the summary tools for stores, districts or the chain.
- Show the key number first, then one line on what it means. Mention any filters you used.
- If a question needs a metric or grouping the tools don't offer, say what you can answer instead.
- Separate what the data shows from what it can't show (for example, why a district reviews less).
""",
    "district-summary": COMMON + """
You write a short weekly summary for Dana (Director of Loss Prevention) and a district manager.
Use get_district_summary (last_weeks=1 for the latest week, 8 for the full period) and
get_chain_overview for comparison. Structure:
1. One-sentence headline with the district's review rate vs. other districts.
2. High-tier alerts: what share got reviewed.
3. Stores to follow up with, and why (lowest review rate, most rushed reviews).
4. One suggested next step.
Keep it under 200 words. Be factual and fair to the stores; don't speculate about causes.
""",
}


def build_options(role: str) -> ClaudeAgentOptions:
    tools = [tool(name, desc, schema)(handler) for name, desc, schema, handler in TOOL_SPECS]
    server = create_sdk_mcp_server(name=SERVER, version="1.0.0", tools=tools)
    return ClaudeAgentOptions(
        system_prompt=ROLES[role],
        mcp_servers={SERVER: server},
        allowed_tools=[f"mcp__{SERVER}__{name}" for name, *_ in TOOL_SPECS],
        # Keep the agent read-only and focused: no file, shell or web access.
        disallowed_tools=["Bash", "Read", "Write", "Edit", "Glob", "Grep",
                          "NotebookEdit", "WebFetch", "WebSearch"],
        model=os.environ.get("BRIGHTWATER_MODEL"),  # optional; uses the SDK default if unset
        max_turns=12,
    )


def opening_prompt(args: argparse.Namespace) -> str | None:
    if args.ask:
        return args.ask
    if args.role == "store-manager" and args.store:
        return f"I'm the manager of store {args.store.upper()}. What should I review first this week?"
    if args.role == "district-summary" and args.district:
        return f"Write this week's summary for district {args.district.upper()}."
    return None


def load_env_file(path: str = os.path.join(os.path.dirname(__file__), ".env")) -> None:
    """Read KEY=value lines from agent/.env, if it exists, without overriding real environment variables."""
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())


async def ask(client: ClaudeSDKClient, prompt: str) -> None:
    await client.query(prompt)
    async for message in client.receive_response():
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    print(block.text)
        elif isinstance(message, ResultMessage) and message.is_error:
            print(f"\n[The agent stopped early: {message.subtype}]")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Brightwater alert review agent")
    parser.add_argument("--role", choices=ROLES, default="store-manager")
    parser.add_argument("--store", help="store ID for the store-manager role, e.g. S057")
    parser.add_argument("--district", help="district for the district-summary role, e.g. D7")
    parser.add_argument("--ask", help="ask one question and exit")
    args = parser.parse_args()

    load_env_file()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("Set ANTHROPIC_API_KEY first (see README.md).")

    first = opening_prompt(args)
    async with ClaudeSDKClient(options=build_options(args.role)) as client:
        if first:
            print(f"> {first}\n")
            await ask(client, first)
        if args.ask:
            return
        print("\nAsk a follow-up, or press Enter on an empty line to quit.")
        while True:
            try:
                prompt = input("\n> ").strip()
            except (EOFError, KeyboardInterrupt):
                prompt = ""
            if not prompt:
                break
            await ask(client, prompt)


if __name__ == "__main__":
    asyncio.run(main())
