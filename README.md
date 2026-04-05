# Claude's Viral Growth Machine

**HackNU 2026 | Growth Engineering Track**

Reverse-engineering how Claude became one of the most talked-about AI products on the internet. Built scrapers to collect public discourse, a 4-step processing pipeline to enrich the data, and an automated monitoring system a growth team could use every Monday morning.

## Quick Start

```bash
# 1. Clone and install
git clone <repo-url>
cd scrape1
python -m venv .venv
.venv/Scripts/activate      # Windows
# source .venv/bin/activate  # Mac/Linux
pip install -r lab/requirements.txt

# 2. Set up API keys
cp lab/stage1/processing/.env.example lab/stage1/processing/.env
# Edit .env: set LLM_PROVIDER=ollama (or anthropic/openai/gemini)
# Optional: set YOUTUBE_API_KEY, GROQ_API_KEY, SLACK_WEBHOOK_URL

# 3. If using Ollama (free, local LLM):
ollama pull qwen3:8b

# 4. Run the full machine
cd lab/stage2/part3_automation
python machine.py --ai ollama --reddit-max-items 4000 --youtube-max-items 1500
```

## What This Does

### Part 1: Scrape the Discourse (25% weight)

Three scrapers collecting public conversation about Claude AI:

| Platform | Method | Auth needed | Data collected |
|---|---|---|---|
| **Reddit** | Public JSON API (`reddit.com/r/.../...json`) | None | Posts from r/ClaudeAI + 9 cross-community subreddits |
| **YouTube** | YouTube Data API v3 (free tier) | API key | 60+ search queries with relevance filtering |
| **Twitter/X** | Google Custom Search API | CSE key | `site:twitter.com "Claude AI"` tweet discovery |

Platform prioritization rationale: Reddit has the deepest technical discussion (3K+ posts). YouTube has the widest reach (242M+ total views). Twitter/X was deprioritized because direct API requires paid access ($100/month) and Nitter instances are behind JS challenges. Instagram/LinkedIn/TikTok lack text-heavy AI discourse and require login (violates "public data only" constraint).

### Part 2: Decode the Playbook (30% weight)

A 4-step processing pipeline enriches raw scraper output into analysis-ready data:

```
raw CSV → Step 1: Clean → Step 2: Features → Step 3: NLP → Step 4: LLM → enriched CSV
          dedup, dates    engagement_score    VADER sentiment   content_category
          text normalize  virality flags      TF-IDF keywords   growth_type
          missing values  time features       competitor detect  target_audience
```

Then 16 charts across 3 analysis scripts decode Claude's growth patterns:

| Analysis | Charts | Key questions answered |
|---|---|---|
| **v1: Descriptive** | 7 charts | Volume vs launches, content types, feature mentions, top creators |
| **v2: Sentiment** | 5 charts | Sentiment trends, viral keywords, temporal patterns, engagement correlation |
| **v3: Virality** | 4 charts | What predicts virality, creator tiers, engagement quadrants |

### Part 3: Build the Machine (15% weight)

A fully working automated pipeline that runs the entire intelligence operation:

```bash
# Full cycle: scrape → process → analyze → monitor
python machine.py --ai ollama --reddit-max-items 4000 --youtube-max-items 1500

# Recurring schedule
python machine.py --ai ollama --reddit-max-items 4000 --youtube-max-items 1500 --schedule 6h

# Just check anomalies on existing data
python machine.py --ai ollama --reddit-max-items 0 --youtube-max-items 0 --only-monitor
```

Includes 5 anomaly detection signals (volume spike, sentiment crash, viral breakout, new creator entry, competitor surge) with Slack webhook alerting.

Full architecture diagram, cost estimates, error recovery, and tool recommendations: [docs/part3_build_the_machine.md](docs/part3_build_the_machine.md)

### Part 4: Counter-Playbook (20% weight)

Growth distribution plan for a competing AI product, grounded in data from Parts 1-2. See [docs/part4_counter_playbook.md](docs/part4_counter_playbook.md).

## Project Structure

```
scrape1/
├── README.md                              # This file
├── docs/
│   └── part3_build_the_machine.md         # Architecture, costs, alerts, setup
│
├── lab/
│   ├── requirements.txt                   # Python dependencies
│   │
│   ├── stage1/                            # Data collection + processing
│   │   ├── scrapers/
│   │   │   ├── reddit/
│   │   │   │   └── reddit_scraper.py      # Reddit public JSON scraper
│   │   │   ├── youtube/
│   │   │   │   └── youtube_scraper_v2.py  # YouTube Data API v3 scraper
│   │   │   └── twitter_api_nitter_merged/
│   │   │       └── twitter_scraper.py     # Google CSE tweet discovery
│   │   │
│   │   ├── processing/                    # 4-step enrichment pipeline
│   │   │   ├── run_pipeline.py            # Orchestrator (runs step1 → step4)
│   │   │   ├── step1_clean.py             # Dedup, normalize, date filter
│   │   │   ├── step2_features.py          # Engagement, virality, time features
│   │   │   ├── step3_nlp.py              # VADER sentiment, TF-IDF, competitors
│   │   │   └── step4_llm_classify.py      # LLM classification (multi-provider)
│   │   │
│   │   ├── llm_tests/                     # LLM provider benchmarks
│   │   │   └── analyze_reddit_all_llms.py # Claude/OpenAI/Gemini/Ollama comparison
│   │   │
│   │   └── output/                        # Pipeline data at each stage
│   │       ├── raw/                       # Scraper output
│   │       │   ├── reddit/reddit_data.csv
│   │       │   └── youtube/youtube_data.csv
│   │       ├── step1_cleaned/             # After cleaning
│   │       ├── step2_features/            # After feature engineering
│   │       ├── step3_nlp/                 # After NLP processing
│   │       └── clean/                     # Final enriched CSVs
│   │           ├── reddit_enriched.csv    # 47 columns per post
│   │           └── youtube_enriched.csv   # 44 columns per video
│   │
│   └── stage2/                            # Analysis + automation
│       ├── v1_descriptive/
│       │   ├── descriptive_charts.py      # 7 charts
│       │   └── charts/*.png
│       ├── v2_sentiment/
│       │   ├── sentiment_analysis.py      # 5 charts
│       │   └── charts/*.png
│       ├── v3_virality_drivers/
│       │   ├── virality_analysis.py       # 4 charts
│       │   └── charts/*.png
│       └── part3_automation/
│           ├── machine.py                 # Full cycle orchestrator
│           ├── anomaly_detector.py        # 5 z-score signal detectors
│           ├── alerter.py                 # Console + Slack delivery
│           └── architecture.mmd           # Mermaid architecture diagram
│
└── input/                                 # HackNU brief PDFs
    ├── GROWTH ENGINEERING TRACK.pdf
    └── HackNU 2026 Submission Instructions.pdf
```

## Deliverables Checklist

| Deliverable | Format | Location |
|---|---|---|
| Working scrapers + code | Python | `lab/stage1/scrapers/` |
| Structured dataset | CSV + JSON | `lab/stage1/output/clean/` |
| Playbook analysis with data | 16 PNG charts + stats JSON | `lab/stage2/v1_descriptive/`, `v2_sentiment/`, `v3_virality_drivers/` |
| Automation architecture diagram | Mermaid | `lab/stage2/part3_automation/architecture.mmd` |
| Counter-playbook / distribution plan | Markdown | `docs/part4_counter_playbook.md` |
| README (setup, assumptions, tradeoffs) | Markdown | This file |

## Assumptions & Tradeoffs

**Platform selection:** Prioritized Reddit (text-heavy discourse), YouTube (widest reach), Twitter/X (real-time sentiment). Skipped Instagram/TikTok (visual-first, minimal AI technical discussion) and LinkedIn (requires login).

**Twitter/X constraint:** The brief requires "public data only, no login-wall scraping." Twitter search requires authentication. We use Google Custom Search API (`site:twitter.com`) as a compliant workaround. Nitter instances were tested but are behind JS challenges that block automated access.

**LLM classification:** Keyword-based classifiers were initially built into scrapers but misclassified ~30% of posts. We moved classification to step4 using LLM providers (Ollama local = $0, Anthropic cloud = ~$0.50/run) for ~95% accuracy. The brief explicitly allows AI assistants.

**Data freshness:** Scraped data is a point-in-time snapshot. Reddit's public JSON API returns at most ~1000 posts per sort/search combination. YouTube's free tier allows 10,000 API units/day. These are sufficient for trend analysis but not exhaustive.

## AI Tools Used

- **Claude Code** (Anthropic) — code generation, architecture design, analysis planning
- **Ollama (Qwen 3 8B)** — local LLM for post classification in step4
- **Anthropic Claude API** — cloud LLM classification (used for initial full-dataset run)
- **VADER (nltk)** — rule-based sentiment analysis
- **scikit-learn TF-IDF** — keyword extraction and engagement correlation

All AI-generated code was reviewed, tested, and validated by running the full pipeline end-to-end.
