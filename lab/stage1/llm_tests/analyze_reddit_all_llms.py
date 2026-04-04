"""
HackNU 2026 - Reddit Analysis with Claude, OpenAI, Gemini, and Ollama
=====================================================================

Analyzes first 20 rows from data/raw/reddit_data.csv using four LLM providers.
API keys loaded from .env file in the same directory.
Ollama runs locally (no API key needed).

Usage:
    python analyze_reddit_all_llms.py
"""

import os
import json
import pandas as pd
import time
from datetime import datetime
from typing import List, Dict, Optional
import sys
from pathlib import Path
from dotenv import load_dotenv

# ============================================================
# CONFIGURATION
# ============================================================

# Load .env from the same directory as this script
SCRIPT_DIR = Path(__file__).resolve().parent
load_dotenv(SCRIPT_DIR / ".env")

# Project root is 3 levels up from lab/stage1/llm_tests/
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent
CSV_PATH = str(PROJECT_ROOT / "data" / "raw" / "reddit_data.csv")
OUTPUT_DIR = str(SCRIPT_DIR / "analysis_results")

# Only analyze first 20 rows
MAX_ROWS = 20

CLASSIFICATION_SCHEMA = """
Classify each Reddit post into these categories:

1. content_category (pick ONE):
   - discussion: General conversation about Claude/AI
   - comparison: Claude vs competitors (ChatGPT, Gemini, etc.)
   - tutorial: How-to guides, prompting tips
   - showcase: User showing what they built with Claude
   - complaint: Bugs, frustrations, limitations
   - praise: Positive feedback, success stories
   - news: Official announcements, media coverage
   - question: Users asking for help
   - meme: Humor, jokes
   - feature_request: Requesting new features

2. sentiment (pick ONE):
   - positive: Favorable toward Claude
   - negative: Critical of Claude
   - neutral: Balanced/informational
   - mixed: Both positive and negative

3. virality_potential (pick ONE):
   - high: Likely to go viral (controversial, breakthrough, relatable)
   - medium: Moderate engagement expected
   - low: Minimal engagement expected

4. growth_type (pick ONE):
   - organic: Natural user enthusiasm
   - reactive: Response to news/events
   - competitive: Comparing to/switching from competitors
   - educational: Teaching others about Claude

5. target_audience (pick ONE):
   - developers: Technical users
   - general: Everyday users
   - enterprise: Business users
   - researchers: Academic/research
   - creators: Writers, artists
"""

SYSTEM_PROMPT = f"""You are a growth analyst classifying Reddit posts about Claude AI for a hackathon project.

{CLASSIFICATION_SCHEMA}

For each post, return a JSON object with these exact fields:
- content_category: string
- sentiment: string
- virality_potential: string
- growth_type: string
- target_audience: string
- key_insight: string (one sentence explaining growth significance)

Return ONLY valid JSON array, no markdown, no explanation."""


# ============================================================
# UTILITY FUNCTIONS
# ============================================================

def load_data(csv_path: str, max_rows: int = MAX_ROWS) -> pd.DataFrame:
    """Load and prepare the Reddit dataset (limited to max_rows)."""
    print(f"Loading data from {csv_path}...")
    df = pd.read_csv(csv_path, nrows=max_rows)
    print(f"✓ Loaded {len(df):,} posts (limited to first {max_rows})")
    return df


def format_posts_for_llm(posts: List[Dict], start_idx: int = 0) -> str:
    """Format posts for LLM input."""
    formatted = []
    for i, post in enumerate(posts):
        formatted.append(
            f"POST {start_idx + i + 1}:\n"
            f"Title: {post['title']}\n"
            f"Subreddit: {post['subreddit']}\n"
            f"Upvotes: {post['upvotes']}, Comments: {post['comments']}\n"
            f"Content Type: {post.get('content_type', 'unknown')}\n"
            f"Date: {post['date']}"
        )
    return "\n\n".join(formatted)


def parse_llm_json(response_text: str) -> list:
    """Parse JSON from LLM response, handling markdown fences."""
    text = response_text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    result = json.loads(text)
    if isinstance(result, dict):
        if "classifications" in result:
            return result["classifications"]
        return [result]
    return result


def merge_results(df: pd.DataFrame, all_results: list, prefix: str) -> pd.DataFrame:
    """Merge LLM classification results into dataframe."""
    for i, result in enumerate(all_results):
        if i < len(df) and isinstance(result, dict):
            for key, value in result.items():
                df.loc[i, f"{prefix}_{key}"] = str(value) if isinstance(value, (list, dict)) else value
    return df


def save_results(df: pd.DataFrame, provider: str):
    """Save analysis results."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = f"{OUTPUT_DIR}/reddit_analysis_{provider}_{timestamp}.csv"
    json_path = f"{OUTPUT_DIR}/reddit_analysis_{provider}_{timestamp}.json"

    df.to_csv(csv_path, index=False)
    df.to_json(json_path, orient='records', indent=2)

    print(f"✓ Saved: {csv_path}")
    print(f"✓ Saved: {json_path}")
    return csv_path


# ============================================================
# 1. ANTHROPIC CLAUDE — claude-sonnet-4-20250514: $3/$15 per 1M tokens
# ============================================================

def analyze_with_claude(df: pd.DataFrame, batch_size: int = 25) -> pd.DataFrame:
    """Analyze Reddit posts using Claude Sonnet 4."""
    try:
        import anthropic
    except ImportError:
        os.system("pip install anthropic -q")
        import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set")
        return df

    model = "claude-sonnet-4-20250514"
    client = anthropic.Anthropic(api_key=api_key)
    posts = df.to_dict('records')

    print(f"\n{'='*60}")
    print(f"CLAUDE ANALYSIS ({model})")
    print(f"{'='*60}")
    print(f"Posts: {len(posts):,} | Batch size: {batch_size}")

    all_results = []
    total_input_tokens = 0
    total_output_tokens = 0

    for i in range(0, len(posts), batch_size):
        batch = posts[i:i+batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(posts) + batch_size - 1) // batch_size
        print(f"\rProcessing batch {batch_num}/{total_batches}...", end='', flush=True)

        posts_text = format_posts_for_llm(batch, i)

        try:
            message = client.messages.create(
                model=model,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=[{
                    "role": "user",
                    "content": f"Classify these {len(batch)} Reddit posts. Return a JSON array with exactly {len(batch)} objects.\n\n{posts_text}"
                }]
            )

            total_input_tokens += message.usage.input_tokens
            total_output_tokens += message.usage.output_tokens
            all_results.extend(parse_llm_json(message.content[0].text))

        except json.JSONDecodeError:
            print(f"\n  Warning: JSON parse error in batch {batch_num}")
            all_results.extend([{"error": "parse_failed"} for _ in batch])
        except Exception as e:
            print(f"\n  Error in batch {batch_num}: {e}")
            all_results.extend([{"error": str(e)} for _ in batch])

        time.sleep(0.5)

    cost = (total_input_tokens * 3.00 + total_output_tokens * 15.00) / 1_000_000
    print(f"\n\n✓ Complete! Tokens: {total_input_tokens:,} in / {total_output_tokens:,} out | Cost: ${cost:.2f}")

    return merge_results(df, all_results, "claude")


# ============================================================
# 2. OPENAI — gpt-4o-mini: $0.15/$0.60 per 1M tokens
# ============================================================

def analyze_with_openai(df: pd.DataFrame, batch_size: int = 30) -> pd.DataFrame:
    """Analyze Reddit posts using GPT-4o mini."""
    try:
        from openai import OpenAI
    except ImportError:
        os.system("pip install openai -q")
        from openai import OpenAI

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("ERROR: OPENAI_API_KEY not set")
        return df

    model = "gpt-4o-mini"
    client = OpenAI(api_key=api_key)
    posts = df.to_dict('records')

    print(f"\n{'='*60}")
    print(f"OPENAI ANALYSIS ({model})")
    print(f"{'='*60}")
    print(f"Posts: {len(posts):,} | Batch size: {batch_size}")

    all_results = []
    total_input_tokens = 0
    total_output_tokens = 0

    for i in range(0, len(posts), batch_size):
        batch = posts[i:i+batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(posts) + batch_size - 1) // batch_size
        print(f"\rProcessing batch {batch_num}/{total_batches}...", end='', flush=True)

        posts_text = format_posts_for_llm(batch, i)

        try:
            response = client.chat.completions.create(
                model=model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT + '\n\nReturn as: {"classifications": [...]}'},
                    {"role": "user", "content": f"Classify these {len(batch)} Reddit posts:\n\n{posts_text}"}
                ],
                max_tokens=4096,
                temperature=0.3
            )

            total_input_tokens += response.usage.prompt_tokens
            total_output_tokens += response.usage.completion_tokens
            all_results.extend(parse_llm_json(response.choices[0].message.content))

        except Exception as e:
            print(f"\n  Error in batch {batch_num}: {e}")
            all_results.extend([{"error": str(e)} for _ in batch])

        time.sleep(0.3)

    cost = (total_input_tokens * 0.15 + total_output_tokens * 0.60) / 1_000_000
    print(f"\n\n✓ Complete! Tokens: {total_input_tokens:,} in / {total_output_tokens:,} out | Cost: ${cost:.4f}")

    return merge_results(df, all_results, "openai")


# ============================================================
# 3. GOOGLE GEMINI — gemini-2.0-flash: $0.10/$0.40 per 1M tokens
# ============================================================

def analyze_with_gemini(df: pd.DataFrame, batch_size: int = 50) -> pd.DataFrame:
    """Analyze Reddit posts using Gemini 2.0 Flash."""
    try:
        import google.generativeai as genai
    except ImportError:
        os.system("pip install google-generativeai -q")
        import google.generativeai as genai

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY not set")
        return df

    model = "gemini-2.0-flash"
    genai.configure(api_key=api_key)
    model_instance = genai.GenerativeModel(model)
    posts = df.to_dict('records')

    print(f"\n{'='*60}")
    print(f"GEMINI ANALYSIS ({model})")
    print(f"{'='*60}")
    print(f"Posts: {len(posts):,} | Batch size: {batch_size}")

    all_results = []
    total_chars = 0

    for i in range(0, len(posts), batch_size):
        batch = posts[i:i+batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(posts) + batch_size - 1) // batch_size
        print(f"\rProcessing batch {batch_num}/{total_batches}...", end='', flush=True)

        posts_text = format_posts_for_llm(batch, i)
        total_chars += len(posts_text)

        prompt = f"""{SYSTEM_PROMPT}

Classify these {len(batch)} Reddit posts. Return a JSON array with exactly {len(batch)} objects.

{posts_text}"""

        try:
            response = model_instance.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(
                    response_mime_type="application/json",
                    max_output_tokens=8192,
                    temperature=0.3
                )
            )
            all_results.extend(parse_llm_json(response.text))

        except json.JSONDecodeError:
            print(f"\n  Warning: JSON parse error in batch {batch_num}")
            all_results.extend([{"error": "parse_failed"} for _ in batch])
        except Exception as e:
            print(f"\n  Error in batch {batch_num}: {e}")
            all_results.extend([{"error": str(e)} for _ in batch])

        time.sleep(0.2)

    est_input_tokens = total_chars // 4
    est_output_tokens = len(all_results) * 30
    cost = (est_input_tokens * 0.10 + est_output_tokens * 0.40) / 1_000_000
    print(f"\n\n✓ Complete! ~{est_input_tokens:,} in / ~{est_output_tokens:,} out | Cost: ~${cost:.4f}")

    return merge_results(df, all_results, "gemini")


# ============================================================
# 4. OLLAMA — qwen3:38b (local, free)
# ============================================================

def analyze_with_ollama(df: pd.DataFrame, batch_size: int = 10) -> pd.DataFrame:
    """Analyze Reddit posts using Ollama with Qwen3 38B locally."""
    import requests

    model = "qwen3:38b"
    base_url = "http://localhost:11434"
    posts = df.to_dict('records')

    print(f"\n{'='*60}")
    print(f"OLLAMA ANALYSIS ({model})")
    print(f"{'='*60}")
    print(f"Posts: {len(posts):,} | Batch size: {batch_size}")

    all_results = []

    for i in range(0, len(posts), batch_size):
        batch = posts[i:i+batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(posts) + batch_size - 1) // batch_size
        print(f"\rProcessing batch {batch_num}/{total_batches}...", end='', flush=True)

        posts_text = format_posts_for_llm(batch, i)

        prompt = f"""{SYSTEM_PROMPT}

Classify these {len(batch)} Reddit posts. Return a JSON array with exactly {len(batch)} objects.

{posts_text}"""

        try:
            response = requests.post(
                f"{base_url}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.3,
                        "num_predict": 8192
                    }
                },
                timeout=300
            )
            response.raise_for_status()

            result_text = response.json()["response"]
            all_results.extend(parse_llm_json(result_text))

        except json.JSONDecodeError:
            print(f"\n  Warning: JSON parse error in batch {batch_num}")
            all_results.extend([{"error": "parse_failed"} for _ in batch])
        except Exception as e:
            print(f"\n  Error in batch {batch_num}: {e}")
            all_results.extend([{"error": str(e)} for _ in batch])

    print(f"\n\n✓ Complete! (local model, no cost)")

    return merge_results(df, all_results, "ollama")


# ============================================================
# GROWTH INSIGHTS ANALYSIS
# ============================================================

def generate_growth_insights(df: pd.DataFrame, provider: str = "claude") -> str:
    """Generate growth strategy insights from classified data."""

    prefix = f"{provider}_"

    cat_col = f"{prefix}content_category"
    if cat_col not in df.columns:
        return "No classification data found. Run classification first."

    insights = []
    insights.append("=" * 60)
    insights.append(f"GROWTH INSIGHTS — {provider.upper()}")
    insights.append("=" * 60)

    insights.append("\n📊 CONTENT CATEGORY DISTRIBUTION:")
    cat_counts = df[cat_col].value_counts()
    for cat, count in cat_counts.items():
        pct = count / len(df) * 100
        insights.append(f"  {cat}: {count} ({pct:.1f}%)")

    sent_col = f"{prefix}sentiment"
    if sent_col in df.columns:
        insights.append("\n💬 SENTIMENT DISTRIBUTION:")
        sent_counts = df[sent_col].value_counts()
        for sent, count in sent_counts.items():
            pct = count / len(df) * 100
            insights.append(f"  {sent}: {count} ({pct:.1f}%)")

    viral_col = f"{prefix}virality_potential"
    if viral_col in df.columns:
        insights.append("\n🚀 VIRALITY POTENTIAL:")
        viral_counts = df[viral_col].value_counts()
        for v, count in viral_counts.items():
            pct = count / len(df) * 100
            insights.append(f"  {v}: {count} ({pct:.1f}%)")

    insights.append("\n🏆 TOP CONTENT CATEGORIES BY ENGAGEMENT:")
    if cat_col in df.columns:
        cat_engagement = df.groupby(cat_col)['upvotes'].agg(['mean', 'sum', 'count'])
        cat_engagement = cat_engagement.sort_values('mean', ascending=False)
        for cat, row in cat_engagement.head(5).iterrows():
            insights.append(f"  {cat}: avg {row['mean']:.0f} upvotes ({row['count']} posts)")

    insight_col = f"{prefix}key_insight"
    if insight_col in df.columns:
        insights.append("\n💡 SAMPLE KEY INSIGHTS:")
        top_posts = df.nlargest(10, 'upvotes')
        for _, post in top_posts.head(5).iterrows():
            if pd.notna(post.get(insight_col)):
                insights.append(f"  • {post[insight_col]}")

    return "\n".join(insights)


# ============================================================
# MAIN EXECUTION
# ============================================================

def main():
    """Main execution function."""

    print("\n" + "=" * 60)
    print("HACKNU 2026 - REDDIT GROWTH ANALYSIS")
    print("=" * 60)

    # Check for API keys
    has_claude = bool(os.environ.get("ANTHROPIC_API_KEY"))
    has_openai = bool(os.environ.get("OPENAI_API_KEY"))
    has_gemini = bool(os.environ.get("GEMINI_API_KEY"))
    has_ollama = True  # local, always available

    print(f"\nProviders:")
    print(f"  Claude (Anthropic): {'✓' if has_claude else '✗'}")
    print(f"  OpenAI:             {'✓' if has_openai else '✗'}")
    print(f"  Gemini (Google):    {'✓' if has_gemini else '✗'}")
    print(f"  Ollama (local):     ✓")

    # Load data (first 20 rows)
    df = load_data(CSV_PATH)

    # Run all available providers
    if has_gemini:
        df = analyze_with_gemini(df)
    if has_openai:
        df = analyze_with_openai(df)
    if has_claude:
        df = analyze_with_claude(df)
    df = analyze_with_ollama(df)

    # Generate insights for each
    for provider in ["gemini", "openai", "claude", "ollama"]:
        if f"{provider}_content_category" in df.columns:
            print(generate_growth_insights(df, provider))

    save_results(df, "all_providers")


if __name__ == "__main__":
    main()
