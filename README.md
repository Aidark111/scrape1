# Claude's Viral Growth Machine

**HackNU 2026 | Growth Engineering Track**

Reverse-engineering how Claude became one of the most talked-about AI products on the internet. Built scrapers to collect public discourse, a 4-step processing pipeline to enrich the data, and an automated monitoring system a growth team could use every Monday morning.

## Key Findings

Our analysis of 4,346 data points (3,353 Reddit posts + 993 YouTube videos) revealed 8 growth patterns:

1. **Pentagon > product launches** — 72 posts, 246K upvotes, 0.23 keyword correlation. Claude hit #1 on App Store from a political stance, not a feature release.
2. **Reactive beats educational 2.7x** — reactive content (1,681 avg engagement) vs educational (612). The content companies invest most in drives the least growth.
3. **r/technology delivers 3.9x more than r/ClaudeAI** — viral growth happens outside the AI community, not inside it.
4. **3 YouTube creators match Anthropic's entire channel** — Fireship + CarterPCs + AI Code Arena = 34M views from 23 videos vs Anthropic's 10.1M from 43 videos.
5. **Complaints outperform praise** — negative content (1,462 avg) beats positive (1,342). Frustration drives more sharing than satisfaction.
6. **Comments predict virality, formatting doesn't** — 0.67 correlation for comments vs ~0 for title length, caps, or exclamation marks.
7. **Sunday morning is the sweet spot** — 80% higher engagement than Thursday, yet most content is posted mid-week.
8. **Viral posts flip audience** — daily community targets developers (organic), viral moments reach general public (reactive).

Full analysis with charts: [docs/playbook_analysis.md](docs/playbook_analysis.md)

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

Platform prioritization rationale: Reddit has the deepest technical discussion (3K+ posts). YouTube has the widest reach (272M+ total views). Twitter/X was deprioritized because direct API requires paid access ($100/month) and Nitter instances are behind JS challenges. Instagram/LinkedIn/TikTok lack text-heavy AI discourse and require login (violates "public data only" constraint).

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

6 concrete growth strategies for a competing AI product, each grounded in our data findings:

1. **Engineer a values moment** — because Pentagon (246K upvotes) beat every product launch
2. **Seed mainstream communities** — because r/technology (3,192 avg) delivers 3.9x more than r/ClaudeAI
3. **Creator partnerships at Mega + Micro tiers** — because 3 creators matched Anthropic's 43-video channel
4. **Optimize for reactive/competitive content** — because reactive (1,681) beats educational (612) by 2.7x
5. **Time launches for weekends** — because Sunday (1,842) beats Thursday (1,023) by 80%
6. **Build dual engines** — technical retention (daily) + narrative acquisition (periodic)

Includes measurement framework, budget allocation, and 6-week execution calendar.

Full plan: [docs/part4_counter_playbook.md](docs/part4_counter_playbook.md)

## Project Structure

```
scrape1/
├── README.md                              # This file
├── docs/
│   ├── playbook_analysis.md               # Part 2: 8 findings with data
│   ├── part3_build_the_machine.md         # Part 3: Architecture, costs, alerts
│   └── part4_counter_playbook.md          # Part 4: 6 growth strategies
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
│   │           ├── youtube_enriched.csv   # 44 columns per video
│   │           └── llm_consumption.csv    # API token tracking
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
| Playbook analysis (8 findings) | Markdown | `docs/playbook_analysis.md` |
| Analysis charts (16) | PNG + stats JSON | `lab/stage2/v1_descriptive/`, `v2_sentiment/`, `v3_virality_drivers/` |
| Automation architecture diagram | Mermaid | `lab/stage2/part3_automation/architecture.mmd` |
| Automation design doc | Markdown | `docs/part3_build_the_machine.md` |
| Counter-playbook (6 strategies) | Markdown | `docs/part4_counter_playbook.md` |
| README | Markdown | This file |

## Assumptions & Tradeoffs

**Platform selection:** Prioritized Reddit (text-heavy discourse), YouTube (widest reach), Twitter/X (real-time sentiment). Skipped Instagram/TikTok (visual-first, minimal AI technical discussion) and LinkedIn (requires login).

**Twitter/X constraint:** The brief requires "public data only, no login-wall scraping." Twitter search requires authentication. We use Google Custom Search API (`site:twitter.com`) as a compliant workaround. Nitter instances were tested but are behind JS challenges that block automated access.

**LLM classification over keyword matching:** Keyword-based classifiers misclassified ~30-40% of posts (51% defaulted to "Discussion"). We moved classification to step4 using LLM providers (Ollama local = $0, Anthropic cloud = ~$0.50/run) for ~95% accuracy. Token consumption tracked in `llm_consumption.csv`. The brief explicitly allows AI assistants.

**Top-post sampling bias:** Reddit's API returns top posts per sort/search combination. For growth analysis this is ideal — we're studying what drives virality, not measuring average post quality. Noted in methodology.

**Recent data oversampling:** Paginating r/ClaudeAI/new gives more 2026 Q1-Q2 posts. Doesn't affect pattern-level findings. Documented in playbook analysis methodology section.

## AI Tools Used

- **Claude Code** (Anthropic) — code generation, architecture design, analysis planning
- **Claude (claude.ai)** — strategy planning, document drafting, data interpretation
- **Anthropic Claude Sonnet 4 API** — batch LLM classification of all 4,346 posts (218 batches, ~530K tokens)
- **Ollama (Qwen 3 8B)** — local LLM for post classification (free alternative to cloud)
- **VADER (nltk)** — rule-based sentiment analysis in step3
- **scikit-learn TF-IDF** — keyword extraction and engagement correlation in step3

All AI-generated code was reviewed, tested, and validated by running the full pipeline end-to-end. Scraper outputs were spot-checked against live Reddit/YouTube data.

## What We'd Do With More Time

- Add X/Twitter data via a paid scraping API (~$10 for 5K tweets)
- Run Gemini Flash (free tier) as a second classifier and compare accuracy
- Build a Streamlit dashboard for the Monday morning brief
- Add email alerting for HIGH priority signals
- Execute the 6-week counter-playbook calendar with tracking
- A/B test posting times based on the temporal heatmap findings
