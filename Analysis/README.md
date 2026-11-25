# Brightwater analysis files

| File | What it is |
| --- | --- |
| `brightwater_analysis.py` | Reproduces every number in the write-up from the assessment spreadsheet. Run: `python brightwater_analysis.py Brightwater_Exceptions_Aug-Oct_2026.xlsx` |
| `Brightwater_Analysis_Results.xlsx` | The script's output: one sheet per finding, plus data quality, tiers, success baselines, price-override thresholds and review-judgment consistency |
| `uat_checks.py` | Automated QA and UAT checks run against the prototype in a browser |
| `uat-test-copy.html` | The prototype with five QA test alerts added (store S999) for the tie and unknown-type checks |

Rules used throughout: duplicates removed (11,563 alerts); S119 and S120 counted as D8; a review of 30 seconds or less counts as rushed; tiers are High = manual card entry and no-receipt refund, Medium = post-void and employee discount, Low = price override.
