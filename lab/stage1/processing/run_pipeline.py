"""
Processing pipeline orchestrator — runs all 4 steps in order.

Pipeline flow (each step reads the previous step's output):
  Step 1: Clean   — raw CSVs → deduped, normalized, date-filtered data
  Step 2: Features — cleaned data → engagement scores, virality flags, time features
  Step 3: NLP     — feature data → VADER sentiment, TF-IDF keywords, competitor mentions
  Step 4: LLM     — NLP data → Ollama classification (content type, sentiment, audience)

Data path:
  output/raw/ → output/step1_cleaned/ → output/step2_features/
             → output/step3_nlp/ → output/clean/ (final enriched CSVs)

Usage:
  python run_pipeline.py             # run all 4 steps from scratch
  python run_pipeline.py --from 3    # resume from step 3 (reuses step2 output)
  python run_pipeline.py --from 4    # re-run only LLM classification

Note: Each step is idempotent — re-running overwrites previous output safely.
Step 4 (LLM) requires Ollama running locally; if unavailable it skips gracefully.
"""
import argparse
import time

# Each step exposes a main() function that reads from its input dir and writes
# to its output dir. No arguments needed — paths are resolved relative to STAGE1_DIR.
from step1_clean import main as step1
from step2_features import main as step2
from step3_nlp import main as step3
from step4_llm_classify import main as step4


def main():
    parser = argparse.ArgumentParser(description="Run processing pipeline")
    # --from lets you skip expensive early steps when iterating on later ones.
    # E.g. after fixing step4, run `--from 4` to avoid re-cleaning and re-featurizing.
    parser.add_argument("--from", type=int, default=1, dest="start",
                        help="Start from step N (1-4, default: 1)")
    args = parser.parse_args()

    steps = [
        (1, "Clean", step1),       # Dedup, text normalization, date parsing
        (2, "Features", step2),    # Engagement scores, virality flags, time features
        (3, "NLP", step3),         # VADER sentiment, TF-IDF keywords, competitor detection
        (4, "LLM Classify", step4),  # Ollama-based content classification (6-field schema)
    ]

    total_start = time.time()

    for num, name, func in steps:
        if num < args.start:
            print(f"\n  Skipping step {num}: {name}")
            continue
        print(f"\n{'#' * 60}")
        print(f"  PIPELINE STEP {num}/4: {name}")
        print(f"{'#' * 60}")
        t = time.time()
        func()
        elapsed = time.time() - t
        print(f"  Step {num} took {elapsed:.1f}s")

    total = time.time() - total_start
    print(f"\n{'#' * 60}")
    print(f"  PIPELINE COMPLETE — {total:.1f}s total")
    print(f"  Final enriched data: stage1/output/clean/")
    print(f"{'#' * 60}")


if __name__ == "__main__":
    main()
