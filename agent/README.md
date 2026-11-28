# Brightwater alert review agent

An AI assistant built with Anthropic's [Claude Agent SDK](https://code.claude.com/docs/en/agent-sdk/python) for the Brightwater Market alert review queue. One agent, three jobs:

| Role | Who it's for | What it does |
| --- | --- | --- |
| `store-manager` | Store managers | Shows what to review first, explains why an alert is ranked where it is, and offers draft notes on what to check |
| `analyst` | Product team | Answers plain-English questions about the alert data |
| `district-summary` | Dana and district managers | Writes a short weekly summary: review rates, high-risk alerts, stores to follow up with |

Every number the agent gives comes from the alert spreadsheet through its tools, not from the AI's memory. The agent is read-only: it can't mark alerts, change files, or browse the web.

## Setup (once)

You need Python 3.10 or newer and an Anthropic API key from https://console.anthropic.com/.

```bash
cd agent
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env              # then paste your API key into .env
```

The agent reads `Brightwater_Exceptions_Aug-Oct_2026.xlsx` from the repository root. To use a file somewhere else, set `BRIGHTWATER_DATA` in `.env`.

## Running it

```bash
# Store manager: start with this week's queue for a store, then ask follow-ups
python main.py --role store-manager --store S057

# Analyst: ask one question
python main.py --role analyst --ask "Which alert type is least often a real problem?"

# District summary for Dana
python main.py --role district-summary --district D7
```

Without `--ask`, the agent keeps the conversation going: type a follow-up, or press Enter on an empty line to quit.

**Try asking:**
- "Why is A105590 a High alert, and what should I check?"
- "Which stores rush more than half their reviews?"
- "What share of price overrides under $50 were real problems?"
- "How did D6 compare with the other districts over the 8 weeks?"

## Checking it works

```bash
python test_agent.py
```

This runs 7 checks against the numbers in the write-up (queue order for S057, the D7 review rate, price overrides under $50, and so on). It needs no API key.

## Files

| File | Purpose |
| --- | --- |
| `main.py` | The agent: roles, instructions and the conversation loop |
| `tools.py` | The six tools the agent can call |
| `brightwater_data.py` | Loads and cleans the spreadsheet; every figure is calculated here |
| `test_agent.py` | Checks the tools against the write-up's numbers |

## Notes

- The data is fictional, from an APM take-home assessment (Aug 31 – Oct 25, 2026).
- The "what to check" notes are a draft. The next release plans to agree real review criteria with Brightwater loss prevention.
- Data rules: duplicate rows removed (11,563 alerts); S119 and S120 belong to D8; a review of 30 seconds or less counts as rushed.
