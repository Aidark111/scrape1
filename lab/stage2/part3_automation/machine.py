"""
The Machine — automated competitive intelligence pipeline.

Runs the full cycle: scrape → process → analyze → detect anomalies → alert.
Can run once (CLI) or on a recurring schedule.

Usage:
  python machine.py                    # run full cycle once
  python machine.py --schedule 6h      # run every 6 hours
  python machine.py --skip-scrape      # skip scraping, just process + analyze
  python machine.py --only-monitor     # only run anomaly detection + alerts
"""
import os
import sys
import time
import json
import argparse
import subprocess
from datetime import datetime
from pathlib import Path

# Resolve project paths
MACHINE_DIR = Path(__file__).resolve().parent
LAB_DIR = MACHINE_DIR.parent.parent
STAGE1_DIR = LAB_DIR / "stage1"
STAGE2_DIR = LAB_DIR / "stage2"
PROCESSING_DIR = STAGE1_DIR / "processing"
SCRAPERS_DIR = STAGE1_DIR / "scrapers"
CLEAN_DIR = STAGE1_DIR / "output" / "clean"
STATUS_FILE = MACHINE_DIR / "machine_status.json"

# Python executable from venv
PYTHON = sys.executable


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"  [{ts}] {msg}")


def run_script(script_path, label, cwd=None):
    """Run a Python script as subprocess. Returns (success, duration_sec)."""
    if not script_path.exists():
        log(f"SKIP {label}: {script_path} not found")
        return False, 0

    log(f"START {label}")
    start = time.time()

    try:
        result = subprocess.run(
            [PYTHON, str(script_path)],
            cwd=str(cwd or script_path.parent),
            capture_output=True,
            text=True,
            timeout=600,
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


def run_scrapers():
    """Run all scrapers. Each is independent — failures don't block others."""
    log("=" * 50)
    log("PHASE 1: SCRAPING")
    log("=" * 50)

    results = {}

    scrapers = [
        ("Reddit", SCRAPERS_DIR / "reddit" / "reddit_scraper.py"),
        ("YouTube", SCRAPERS_DIR / "youtube" / "youtube_scraper_v2.py"),
        ("Twitter", SCRAPERS_DIR / "twitter_api_nitter_merged" / "twitter_scraper.py"),
    ]

    for name, path in scrapers:
        success, duration = run_script(path, f"Scraper: {name}")
        results[name.lower()] = {"success": success, "duration_sec": round(duration, 1)}

    return results


def run_processing():
    """Run the 4-step processing pipeline."""
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
            # Steps 1-3 are critical — stop if they fail
            log(f"Pipeline stopped: {name} failed")
            break
        # Step 4 failure is non-critical (data still usable without LLM labels)

    return results


def run_analysis():
    """Run stage2 analysis scripts to generate charts."""
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
    """Run anomaly detection and deliver alerts."""
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


def run_full_cycle(skip_scrape=False, only_monitor=False):
    """Run the complete machine cycle."""
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
            status["phases"]["scraping"] = run_scrapers()
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

    if args.schedule:
        interval = parse_schedule(args.schedule)
        print(f"\n  Machine scheduled: every {args.schedule} ({interval}s)")
        print("  Press Ctrl+C to stop.\n")

        while True:
            try:
                run_full_cycle(
                    skip_scrape=args.skip_scrape,
                    only_monitor=args.only_monitor,
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
        )


if __name__ == "__main__":
    main()
