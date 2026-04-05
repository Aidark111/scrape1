"""
The Machine — automated competitive intelligence pipeline.

Orchestrates the full growth monitoring cycle across 4 phases:
  Phase 1: SCRAPING    — collect raw data from Reddit, YouTube (via subprocess)
  Phase 2: PROCESSING  — clean → features → NLP → LLM classify (4-step pipeline)
  Phase 3: ANALYSIS    — generate 16 charts across 3 analysis scripts
  Phase 4: MONITORING  — detect anomalies (z-score) and deliver alerts (console/Slack)

Each phase is independent — failures in one don't crash the whole cycle.
Step 4 (LLM) failure is non-critical: charts work without classification columns.
All scripts run as subprocesses so they get their own import scope and error handling.

Usage:
  python machine.py --ai ollama --reddit-max-items 4000 --youtube-max-items 1500
  python machine.py --ai anthropic --reddit-max-items 100 --youtube-max-items 50 --skip-scrape
  python machine.py --ai ollama --reddit-max-items 4000 --youtube-max-items 1500 --schedule 6h
  python machine.py --ai ollama --reddit-max-items 0 --youtube-max-items 0 --only-monitor
"""
import os
import sys
import time
import json
import argparse
import subprocess
from datetime import datetime
from pathlib import Path

# ── Path resolution ──────────────────────────────────────────────────────────
# machine.py lives at: lab/stage2/part3_automation/machine.py
# It needs to reach: lab/stage1/scrapers/, lab/stage1/processing/, lab/stage2/v*/
MACHINE_DIR = Path(__file__).resolve().parent
LAB_DIR = MACHINE_DIR.parent.parent          # lab/
STAGE1_DIR = LAB_DIR / "stage1"              # scrapers + processing + output
STAGE2_DIR = LAB_DIR / "stage2"              # analysis scripts (v1, v2, v3)
PROCESSING_DIR = STAGE1_DIR / "processing"   # step1-4 + run_pipeline.py
SCRAPERS_DIR = STAGE1_DIR / "scrapers"       # reddit/, youtube/, twitter_api_nitter_merged/
CLEAN_DIR = STAGE1_DIR / "output" / "clean"  # final enriched CSVs ({platform}_enriched.csv)
STATUS_FILE = MACHINE_DIR / "machine_status.json"  # last run status for monitoring

# Use the same Python that launched this script (respects .venv)
PYTHON = sys.executable


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"  [{ts}] {msg}")


def run_script(script_path, label, cwd=None, script_args=None):
    """
    Run a Python script as a subprocess with UTF-8 encoding forced.
    Returns (success: bool, duration_sec: float).

    Why subprocess instead of import?
    - Each script has its own imports, path resolution, and error handling.
    - A crash in one script doesn't bring down the whole machine.
    - Environment variables (like LLM_PROVIDER) are inherited by child processes.
    """
    if not script_path.exists():
        log(f"SKIP {label}: {script_path} not found")
        return False, 0

    log(f"START {label}")
    start = time.time()

    try:
        cmd = [PYTHON, str(script_path)] + [str(a) for a in (script_args or [])]
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        result = subprocess.run(
            cmd,
            cwd=str(cwd or script_path.parent),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
            env=env,
        )
        duration = time.time() - start

        if result.returncode == 0:
            log(f"DONE  {label} ({duration:.1f}s)")
            return True, duration
        else:
            log(f"FAIL  {label} (exit {result.returncode}, {duration:.1f}s)")
            if result.stderr:
                for line in result.stderr.strip().split("\n")[-5:]:
                    log(f"      {line}")
            return False, duration

    except subprocess.TimeoutExpired:
        log(f"TIMEOUT {label} (>600s)")
        return False, 600
    except Exception as e:
        log(f"ERROR {label}: {e}")
        return False, 0


def save_status(status):
    """Save machine run status to JSON for monitoring."""
    with open(STATUS_FILE, "w") as f:
        json.dump(status, f, indent=2)


def run_scrapers(reddit_max_items, youtube_max_items):
    """
    Phase 1: Collect raw data from social platforms.

    Each scraper runs independently — if YouTube fails (e.g. API quota exceeded),
    Reddit data is still collected and the pipeline continues with what's available.
    Scrapers write to stage1/output/raw/{platform}/ as CSV files.

    The --max-items flag caps how many posts each scraper collects per run,
    which controls both API usage and processing time downstream.
    """
    log("=" * 50)
    log("PHASE 1: SCRAPING")
    log("=" * 50)

    results = {}

    # Each tuple: (display name, script path, CLI arguments to pass)
    scrapers = [
        ("Reddit", SCRAPERS_DIR / "reddit" / "reddit_scraper.py", ["--max-items", reddit_max_items]),
        ("YouTube", SCRAPERS_DIR / "youtube" / "youtube_scraper_v2.py", ["--max-items", youtube_max_items]),
    ]

    for name, path, script_args in scrapers:
        success, duration = run_script(path, f"Scraper: {name}", script_args=script_args)
        results[name.lower()] = {"success": success, "duration_sec": round(duration, 1)}

    return results


def run_processing():
    """
    Phase 2: Transform raw CSVs into enriched datasets.

    Runs 4 processing steps sequentially (each reads previous step's output):
      Step 1 (Clean)    → dedup, normalize text, parse dates, handle missing values
      Step 2 (Features) → compute engagement_score, virality flags, time features
      Step 3 (NLP)      → VADER sentiment, TF-IDF keywords, competitor detection
      Step 4 (LLM)      → classify via Ollama/Anthropic/etc (provider set by --ai flag)

    Critical vs non-critical:
      Steps 1-3 are essential — if any fails, the pipeline halts (no point continuing
      with bad data). Step 4 is optional — if LLM is down, enriched CSVs are still
      produced without classification columns, and stage2 charts handle that gracefully.

    All steps run with cwd=PROCESSING_DIR so their relative imports work correctly.
    The LLM_PROVIDER env var (set in main()) is inherited by the step4 subprocess.
    """
    log("=" * 50)
    log("PHASE 2: PROCESSING PIPELINE")
    log("=" * 50)

    steps = [
        ("Step 1: Clean", PROCESSING_DIR / "step1_clean.py"),
        ("Step 2: Features", PROCESSING_DIR / "step2_features.py"),
        ("Step 3: NLP", PROCESSING_DIR / "step3_nlp.py"),
        ("Step 4: LLM Classify", PROCESSING_DIR / "step4_llm_classify.py"),
    ]

    results = {}
    for name, path in steps:
        success, duration = run_script(path, name, cwd=PROCESSING_DIR)
        results[name] = {"success": success, "duration_sec": round(duration, 1)}
        if not success and "Step 4" not in name:
            log(f"Pipeline stopped: {name} failed (critical step)")
            break

    return results


def run_analysis():
    """
    Phase 3: Generate 16 charts from enriched data.

    Three analysis scripts, each producing a set of PNG charts:
      v1 (Descriptive)  → 7 charts: timeline, content types, features, creators, cross-platform
      v2 (Sentiment)    → 5 charts: sentiment trends, keywords, temporal heatmap, engagement
      v3 (Virality)     → 4 charts: correlation matrix, viral profile, creator tiers, quadrants

    All scripts read from stage1/output/clean/{platform}_enriched.csv
    and write PNGs to their own charts/ subdirectory.
    Failures are logged but don't stop other analyses from running.
    """
    log("=" * 50)
    log("PHASE 3: ANALYSIS + CHARTS")
    log("=" * 50)

    results = {}

    analyses = [
        ("v1: Descriptive", STAGE2_DIR / "v1_descriptive" / "descriptive_charts.py"),
        ("v2: Sentiment", STAGE2_DIR / "v2_sentiment" / "sentiment_analysis.py"),
        ("v3: Virality", STAGE2_DIR / "v3_virality_drivers" / "virality_analysis.py"),
    ]

    for name, path in analyses:
        success, duration = run_script(path, name)
        results[name] = {"success": success, "duration_sec": round(duration, 1)}

    return results


def run_monitoring():
    """
    Phase 4: Check enriched data for anomalies and deliver alerts.

    Unlike phases 1-3, this runs in-process (not subprocess) because it needs
    to return alert data to the cycle summary. Two components:
      - anomaly_detector.py: 5 z-score checks (volume spike, sentiment crash,
        viral breakout, new creator, competitor surge)
      - alerter.py: delivers alerts to console, alert_log.jsonl, and Slack
        (if SLACK_WEBHOOK_URL is set in .env)

    This phase reads from stage1/output/clean/{platform}_enriched.csv — the same
    files that stage2 charts use. No separate data path.
    """
    log("=" * 50)
    log("PHASE 4: ANOMALY DETECTION + ALERTS")
    log("=" * 50)

    from anomaly_detector import run_all_checks
    from alerter import deliver_alerts

    alerts = run_all_checks()
    deliver_alerts(alerts)

    return {
        "alerts_count": len(alerts),
        "alerts": alerts,
    }


def run_full_cycle(skip_scrape=False, only_monitor=False, reddit_max_items=4000, youtube_max_items=1500):
    """
    Execute one complete intelligence cycle: scrape → process → analyze → monitor.

    The cycle is fault-tolerant:
      - --skip-scrape: reprocesses existing raw data (useful when iterating on pipeline)
      - --only-monitor: just checks anomalies on existing enriched data (fast, <2s)
      - If a scraper fails, processing still runs on whatever data exists
      - If step4 fails, charts still generate (without LLM columns)

    At the end, saves machine_status.json with timing and success/failure for each phase.
    This file can be checked by external monitoring to verify the machine ran correctly.
    """
    cycle_start = time.time()
    status = {
        "started_at": datetime.now().isoformat(),
        "phases": {},
    }

    print()
    print("=" * 60)
    print("  THE MACHINE — Competitive Intelligence Pipeline")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    if only_monitor:
        status["phases"]["monitoring"] = run_monitoring()
    else:
        if not skip_scrape:
            status["phases"]["scraping"] = run_scrapers(
                reddit_max_items=reddit_max_items,
                youtube_max_items=youtube_max_items,
            )
        else:
            log("Skipping scraping (--skip-scrape)")

        status["phases"]["processing"] = run_processing()
        status["phases"]["analysis"] = run_analysis()
        status["phases"]["monitoring"] = run_monitoring()

    total = time.time() - cycle_start
    status["completed_at"] = datetime.now().isoformat()
    status["total_duration_sec"] = round(total, 1)

    # Summary
    print()
    print("=" * 60)
    print(f"  CYCLE COMPLETE — {total:.0f}s total")
    print("=" * 60)

    for phase, result in status["phases"].items():
        if isinstance(result, dict) and "alerts_count" in result:
            print(f"  {phase}: {result['alerts_count']} alerts")
        elif isinstance(result, dict):
            ok = sum(1 for v in result.values() if isinstance(v, dict) and v.get("success"))
            total_steps = sum(1 for v in result.values() if isinstance(v, dict))
            print(f"  {phase}: {ok}/{total_steps} steps succeeded")

    # Check what enriched data exists
    enriched = [f for f in CLEAN_DIR.glob("*_enriched.csv")] if CLEAN_DIR.exists() else []
    print(f"\n  Enriched datasets: {len(enriched)}")
    for f in enriched:
        import pandas as pd
        rows = len(pd.read_csv(f, encoding="utf-8"))
        print(f"    {f.name}: {rows:,} rows")

    save_status(status)
    log(f"Status saved to {STATUS_FILE}")

    return status


def parse_schedule(s):
    """Parse schedule string like '6h', '30m', '1d' to seconds."""
    s = s.strip().lower()
    if s.endswith("h"):
        return int(s[:-1]) * 3600
    elif s.endswith("m"):
        return int(s[:-1]) * 60
    elif s.endswith("d"):
        return int(s[:-1]) * 86400
    else:
        return int(s)


def main():
    parser = argparse.ArgumentParser(
        description="The Machine — automated competitive intelligence pipeline"
    )
    parser.add_argument(
        "--ai", type=str, required=True,
        choices=["ollama", "openai", "gemini", "anthropic"],
        help="LLM provider for step4 classification (required). "
             "ollama=free local, openai/gemini/anthropic=cloud API key needed.",
    )
    parser.add_argument(
        "--reddit-max-items", type=int, required=True,
        help="Required cap for Reddit scraper unique posts.",
    )
    parser.add_argument(
        "--youtube-max-items", type=int, required=True,
        help="Required cap for YouTube scraper unique videos.",
    )
    parser.add_argument(
        "--schedule", type=str, default=None,
        help="Run on schedule (e.g. '6h', '30m', '1d'). Without this, runs once.",
    )
    parser.add_argument(
        "--skip-scrape", action="store_true",
        help="Skip scraping, only process + analyze existing data.",
    )
    parser.add_argument(
        "--only-monitor", action="store_true",
        help="Only run anomaly detection + alerts on existing data.",
    )
    args = parser.parse_args()

    # Pass LLM provider choice to step4 via environment variable.
    # step4_llm_classify.py reads os.getenv("LLM_PROVIDER") to decide
    # which API to call (ollama/openai/gemini/anthropic).
    # Since step4 runs as a subprocess, it inherits this env var automatically.
    os.environ["LLM_PROVIDER"] = args.ai
    log(f"LLM provider: {args.ai}")
    log(
        "Scraper limits: "
        f"reddit={args.reddit_max_items}, "
        f"youtube={args.youtube_max_items}"
    )

    if args.schedule:
        interval = parse_schedule(args.schedule)
        print(f"\n  Machine scheduled: every {args.schedule} ({interval}s)")
        print("  Press Ctrl+C to stop.\n")

        while True:
            try:
                run_full_cycle(
                    skip_scrape=args.skip_scrape,
                    only_monitor=args.only_monitor,
                    reddit_max_items=args.reddit_max_items,
                    youtube_max_items=args.youtube_max_items,
                )
                log(f"Next run in {args.schedule}...")
                time.sleep(interval)
            except KeyboardInterrupt:
                print("\n  Machine stopped by user.")
                break
    else:
        run_full_cycle(
            skip_scrape=args.skip_scrape,
            only_monitor=args.only_monitor,
            reddit_max_items=args.reddit_max_items,
            youtube_max_items=args.youtube_max_items,
        )


if __name__ == "__main__":
    main()
