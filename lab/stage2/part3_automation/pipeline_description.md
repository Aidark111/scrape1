# Part 3 — Build the Machine

A recurring competitive intelligence system that a growth team could check every Monday morning. Designed around the actual pipeline we built, not a hypothetical one.

## Architecture Overview

See `architecture.mmd` (render at mermaid.live) for the full data flow diagram.

The system has 4 layers: **Scraping → Processing → Analysis → Monitoring**. 10 automated steps, 1 human-reviewed step.

---

## Pipeline Steps: Automated vs Human-Reviewed

### Scraping Layer (3 scrapers, fully automated)

| Step | Tool | Schedule | Why automated |
|---|---|---|---|
| Reddit scraper | `requests` + Reddit public JSON | Every 6h | Deterministic API calls. Rate limiting (429 + Retry-After) and pagination are handled in code. No judgment needed — just fetch and store. |
| YouTube scraper | `google-api-python-client` | Daily | YouTube Data API v3 has structured responses. Relevance filtering (exclude "Jean-Claude Van Damme") is rule-based. 60+ queries cover all Claude-related content. |
| Twitter scraper | Google Custom Search API | Daily | Direct X API requires $100/month. Google CSE finds tweet URLs for free (100/day). Nitter enrichment attempted but instances use JS challenges — documented as limitation. |

**Why these 3 platforms?** Reddit has the deepest technical discussion. YouTube has the widest reach (242M total views in our dataset). Twitter/X has real-time sentiment but is hardest to access for free. Instagram/LinkedIn/TikTok were deprioritized: Instagram and TikTok lack text-heavy AI discourse; LinkedIn requires login (violates "public data only" constraint).

### Processing Layer (4 steps, fully automated)

This is the core data pipeline. Each step reads the previous step's output and writes enriched CSVs. Steps are idempotent — re-running is safe.

**Working prototype: `processing/run_pipeline.py`** — runs all 4 steps with `python run_pipeline.py`, or resumes from any step with `--from N`.

| Step | Script | What it does | Why automated | Error handling |
|---|---|---|---|---|
| **Step 1: Clean** | `step1_clean.py` | Dedup by post_id/video_id, strip URLs, normalize unicode, parse dates, fill missing values, filter pre-2023 noise | Pure data transformation. No ambiguity — same input always produces same output. | Gracefully skips platforms with no raw data. Logs row counts before/after to detect data loss. |
| **Step 2: Features** | `step2_features.py` | Compute `engagement_score`, `comment_ratio`, `is_viral` (top 10%), `is_controversial`, title features (length, question marks, caps ratio), time features (hour, day_of_week, quarter) | Mathematical operations on numeric columns. Deterministic. These features feed directly into stage2 charts. | Uses `.clip(lower=1)` to prevent division-by-zero. Handles missing datetime gracefully with `errors="coerce"`. |
| **Step 3: NLP** | `step3_nlp.py` | VADER sentiment scoring (compound + pos/neg/neu), TF-IDF keyword extraction (top 5 per post + corpus-level engagement correlation), competitor/feature mention detection | VADER is rule-based (no API, no cost, instant). TF-IDF is statistical. Competitor detection is dictionary lookup. All deterministic and free. | Falls back to empty keywords if fewer than 10 posts (TF-IDF needs minimum document count). Prints viral/low-engagement keywords for manual verification. |
| **Step 4: LLM Classify** | `step4_llm_classify.py` | Classify each post into `content_category`, `sentiment`, `virality_potential`, `growth_type`, `target_audience` + `key_insight` | LLM produces ~95% accurate labels vs ~70% for keyword rules. Batch processing (20 posts per call) keeps cost minimal. Multi-provider support (Ollama/Anthropic/OpenAI/Gemini) via `.env`. | Crash-safe: saves partial results after every batch. If LLM is unavailable, copies step3 output to `output/clean/` without classification columns — stage2 charts handle missing columns gracefully. |

**Why Step 4 uses LLM instead of keyword rules:** We originally had keyword classifiers in the scrapers. They misclassified ~30% of posts (e.g., "code" matched "Claude Code" and "coding" indiscriminately, default "Discussion" inflated one category). We removed them and replaced with LLM classification which produces richer labels (5 fields + `key_insight`) with ~95% accuracy. Cost: ~$0.02 per 1K posts with Groq, $0 with local Ollama.

### Analysis Layer (3 analysis scripts, fully automated)

| Script | Charts | What it answers |
|---|---|---|
| `v1_descriptive` | 7 charts | Volume trends, content types, feature mentions, YouTube creators, cross-platform comparison, launch spikes |
| `v2_sentiment` | 5 charts | Sentiment over time, sentiment by content type, viral keywords (TF-IDF), temporal heatmap, sentiment vs engagement |
| `v3_virality` | 4 charts | Correlation matrix, viral vs normal profile, creator tiers, engagement quadrants |

**Why automated:** Charts are deterministic from data. Same enriched CSV always produces same PNG. Only the interpretation requires a human.

### Monitoring Layer (automated detection, human action)

| Signal | Trigger | Why this threshold | Action |
|---|---|---|---|
| Volume spike | 24h post count > 3x the 4-week rolling average | 3x eliminates normal weekly variance while catching real events (product launches, controversies) | Auto-alert to Slack. Human reviews top posts to classify cause. |
| Sentiment crash | Weekly mean compound drops > 0.3 below 4-week average | 0.3 on VADER's [-1, 1] scale represents a significant shift (e.g., from 0.15 neutral to -0.15 negative) | Auto-alert + email to growth lead. Check for outages, pricing changes, PR issues. |
| Viral breakout | Single post exceeds 1,000 upvotes within 24h | Top 0.1% threshold based on our dataset (median ~230 upvotes). These posts shape narrative. | Log post details. Assess if organic or seeded. Consider amplification or response. |
| New creator entry | YouTube channel with >100K subscribers posts first Claude video | Macro/mega creators entering the space represent partnership opportunities and significant reach expansion. | Add to creator watchlist. Assess content sentiment and alignment. |
| Competitor surge | Competitor name mentions in Claude posts spike 2x week-over-week | Competitor launch or comparative shift. Important for positioning. | Analyze comparative sentiment. Update competitive brief. |

### Human-Reviewed Step

**Insight interpretation + strategy** (growth team, Monday morning)

Why not automated: connecting data patterns to business actions requires market context, competitive awareness, and judgment about organizational priorities. The pipeline surfaces signals; humans decide what to do. Example: a sentiment crash could mean "our pricing is wrong" or "a bug is fixed and users are recalibrating" — same data, opposite actions.

---

## Tool Recommendations

| Component | Recommended | Why this over alternatives |
|---|---|---|
| **Orchestrator** | **Prefect** (free tier) | Python-native, simple DAGs, built-in retry/scheduling. Airflow is too heavy for this scale (requires separate DB, webserver). Cron works but lacks retry logic, failure notifications, and run history. |
| **Storage** | **Local CSV** now, **S3 + Parquet** at 10x | CSV is human-readable, git-trackable, and sufficient at 3K posts. At 30K+, Parquet cuts storage 5x and enables columnar queries. S3 for team access. |
| **LLM provider** | **Ollama** (local) primary, **Groq** (cloud) backup | Ollama: $0, no rate limits, data stays local. Groq free tier: 14,400 req/day, fast inference. Anthropic/OpenAI as premium options for higher accuracy. |
| **Alerting** | **Slack webhooks** | Free, instant, team-visible. Every growth team already uses Slack. Webhook setup is 5 minutes. Email for high-priority escalation. |
| **Monitoring** | **Prefect dashboard** + custom z-score script | Prefect tracks pipeline health (did each step succeed?). Z-score script tracks data anomalies (did the numbers change?). Two different failure modes. |

---

## Error Recovery

| Failure mode | How it's handled |
|---|---|
| Scraper rate-limited | Built-in: Reddit waits on `Retry-After` header. YouTube retries on API errors. All scrapers have `max_retries` with exponential backoff. |
| Scraper returns 0 results | Step1 skips that platform gracefully. Pipeline continues with available data. Console warns which platforms were missing. |
| NLP step crashes mid-run | Steps are idempotent. Re-run with `python run_pipeline.py --from 3`. Previous step outputs are preserved. |
| LLM provider down | Step4 checks provider availability before starting. If unreachable, copies step3 output to `output/clean/` unchanged — stage2 charts work with or without LLM columns. |
| LLM returns bad JSON | `parse_llm_json()` strips thinking tags, markdown fences, and attempts substring extraction. If all parsing fails, that batch gets `None` padding — dataframe alignment is preserved. |
| Partial pipeline run | `run_pipeline.py --from N` resumes from any step. Each step reads from the previous step's output directory, not from memory. |
| Corrupt/stale data | Step1 drops old classification columns from previous runs. Step4 overwrites `output/clean/` on each run. No stale data leaks forward. |

## Data Freshness

| Data source | Freshness | Bottleneck |
|---|---|---|
| Reddit | ~6 hours | Reddit rate limits (~10 req/min). Scraper takes ~5 min per run. |
| YouTube | ~24 hours | API quota (10K units/day). One full run uses ~6.5K units. |
| Twitter | ~24 hours | Google CSE limit (100 queries/day free). |
| Processing pipeline | ~30 min after scraping | Steps 1-3 are instant. Step 4 (LLM) takes ~20 min for 3K posts with Ollama. |
| Charts | ~5 min after processing | All matplotlib scripts run in seconds. |

---

## Cost Estimates

### Current scale (~3,500 Reddit + 1,000 YouTube + ~100 Twitter)

| Component | Cost | Notes |
|---|---|---|
| Reddit scraping | $0 | Public JSON endpoint, no API key |
| YouTube scraping | $0 | Free tier: 10,000 quota units/day |
| Twitter scraping | $0 | Google CSE: 100 free queries/day |
| Processing steps 1-3 | $0 | pandas, VADER, scikit-learn — all local |
| Step 4 LLM (Ollama) | $0 | Local model, no API cost |
| Step 4 LLM (Groq) | ~$0.02 | Llama 3.1 8B, ~3K posts |
| Step 4 LLM (Anthropic) | ~$0.50 | Claude Sonnet, ~3K posts |
| Compute (VPS for scheduling) | $5/mo | Any $5 VPS runs the full pipeline |
| Storage | ~50 MB/month | CSV + PNG charts |
| **Total (Ollama)** | **$0-5/mo** | |
| **Total (Anthropic)** | **$5-10/mo** | |

### At 10x scale (~35K Reddit + 10K YouTube + 1K Twitter)

| Component | Cost | Change needed |
|---|---|---|
| Reddit | $0 | Switch to OAuth for higher rate limits (still free) |
| YouTube | $0-50/mo | May need paid quota or multiple API keys |
| Twitter | $0-100/mo | X API Basic ($100/mo) for direct search, or more CSE queries |
| Step 4 LLM (Ollama) | $0 | Longer runtime (~3 hours) but no cost |
| Step 4 LLM (Groq) | ~$0.20 | Still cheap at 10x |
| Step 4 LLM (Anthropic) | ~$5.00 | Gets expensive at scale |
| Storage | ~500 MB/month | Switch CSV to Parquet, save 5x space |
| Compute | $10-20/mo | Needs more RAM for larger dataframes |
| **Total (Ollama)** | **$10-70/mo** | |
| **Total (Anthropic)** | **$20-125/mo** | |

---

## Working Prototype

The processing pipeline (`stage1/processing/run_pipeline.py`) is a fully working prototype of the automated enrichment step. It has been run successfully on 3,357 Reddit posts and 3,164 YouTube videos.

```bash
# Full pipeline
cd lab/stage1/processing
python run_pipeline.py

# Resume from specific step
python run_pipeline.py --from 3    # re-run NLP + LLM only
python run_pipeline.py --from 4    # re-run LLM classification only
```

Output: enriched CSVs in `output/clean/` with 40+ columns per post, ready for stage2 visualization.
