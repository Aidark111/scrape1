# Part 3 — Automation Pipeline Design

## Overview

A recurring competitive intelligence system that a growth team could check every Monday morning.
6 automated steps, 1 human-reviewed step.

## Pipeline Steps

### Automated

1. **Scraper orchestration** (Prefect free tier or cron + Python)
   - Reddit every 6h, YouTube daily, Twitter daily
   - Retries and rate-limit handling are already built into the scrapers

2. **Deduplication + date filtering** (pandas)
   - Dedup by post_id / video_id, filter date >= 2023-01-01
   - Pure data operation, runs inline after each scraper

3. **Content classification + feature tagging** (keyword rules)
   - Uses the classifiers already built into each scraper
   - ~80% accuracy, sufficient for trend-level analysis

4. **Sentiment scoring** (VADER / nltk)
   - No API key, runs locally, fast
   - Compound score is good enough for trend detection

5. **Chart generation + weekly report** (matplotlib / seaborn)
   - v1 descriptive, v2 sentiment, v3 virality — all run as Python scripts
   - Scheduled Sunday night, charts ready for Monday morning

6. **Anomaly detection + alerts** (z-score on rolling 4-week window)
   - Runs after each scrape
   - Triggers: volume spike > 3x, sentiment drop > 0.3, single post > 1K upvotes
   - Delivered via Slack webhook to #growth-intelligence

### Human-reviewed

7. **Insight interpretation + strategy** (growth team, Monday morning)
   - Connecting data patterns to business actions requires context and judgment
   - The pipeline surfaces signals; humans decide what to do with them

## Cost Estimates

| Component | Current | At 10x scale |
|---|---|---|
| Reddit | $0 (public JSON, no key) | $0 (OAuth is free) |
| YouTube | $0 (free tier, 10K units/day) | $0-50/mo (paid quota) |
| Twitter | $0 (Selenium) | $100/mo (X API Basic) |
| Analysis | ~2 min compute | ~5 min compute |
| Storage | ~50 MB/month | ~200 MB/month |
| **Total** | **$0-5/mo** | **$100-150/mo** |

## Alert Design

| Signal | Trigger | Priority |
|---|---|---|
| Volume spike | 24h volume > 3x the 4-week average | High |
| Sentiment crash | Weekly sentiment drops > 0.3 from average | High |
| Viral breakout | Single post > 1,000 upvotes in 24h | Medium |
| New creator entry | YouTube channel >100K subs posts first Claude video | Medium |
| Competitor surge | Competitor mentions in Claude posts spike 2x | Low |

## Tool Recommendations

- **Orchestrator**: Prefect (free tier, Python-native, simple DAGs) over Airflow (too heavy for this scale)
- **Storage**: Local CSV/Parquet now, S3 at 10x scale
- **Alerting**: Slack webhooks (free, instant, team-visible)
- **Monitoring**: Prefect dashboard for pipeline health; custom z-score script for data anomalies
