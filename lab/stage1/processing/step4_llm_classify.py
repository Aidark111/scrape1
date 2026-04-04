"""
Step 4: LLM classification via Ollama (local, free).
Goal: Leverage high-reasoning local LLMs to categorize posts with human-level accuracy.

High-level architecture (mirrors llm_tests/analyze_reddit_all_llms.py):
  1. Discovery: Finds available Ollama models (e.g., qwen3, llama3.1)
  2. Batching: Groups posts (10 at a time) for efficient context window use
  3. Processing: Calls local LLM API with growth-focused system prompts
  4. Validation: Strips thinking tags and markdown to extract clean JSON
  5. Merge: Joins classification fields into the final dataset

Reads from: output/step3_nlp/ (NLP-enriched data)
Writes to: output/clean/ (The final project dataset ready for stage2 analysis)

Requirements:
  - Local Ollama server: https://ollama.com
  - Pulled model: 'ollama pull qwen3:8b' or similar
"""
import os
import json
import time
import requests
import pandas as pd
from dotenv import load_dotenv

# Path resolution relative to stage1/processing directory
STAGE1_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IN_DIR = os.path.join(STAGE1_DIR, "output", "step3_nlp")
OUT_DIR = os.path.join(STAGE1_DIR, "output", "clean")
os.makedirs(OUT_DIR, exist_ok=True)

# ── Ollama config ────────────────────────────────────────────────────────────
OLLAMA_BASE_URL = "http://localhost:11434"
# Preference list for local models (descending order)
OLLAMA_MODELS = ["qwen3:38b", "qwen3:8b", "llama3.1:8b", "mistral:7b", "gemma2:9b"]
BATCH_SIZE = 10  # Balanced for 8B-14B models on consumer hardware

# ── Classification schema ───────────────────────────────────────────────────
# Defines the exact categorical values required for downstream stage2 charts.
CLASSIFICATION_SCHEMA = """
Classify each social media post into these categories:

1. content_category (pick ONE):
   - discussion     : General conversation
   - comparison     : Claude vs competitors (ChatGPT, etc.)
   - tutorial       : How-to, tips
   - showcase       : Projects built with Claude
   - complaint      : Bugs, frustrations
   - praise         : Success stories
   - news           : Announcements
   - question       : Help requests
   - meme           : Humor
   - feature_request: Desired new features

2. sentiment (pick ONE):
   - positive, negative, neutral, mixed

3. virality_potential (pick ONE):
   - high (breakthrough), medium, low

4. growth_type (pick ONE):
   - organic (enthusiasm), reactive (to events), competitive (switching), educational

5. target_audience (pick ONE):
   - developers, general, enterprise, researchers, creators
"""

SYSTEM_PROMPT = f"""You are a growth analyst specializing in AI market trends.
Classification Goal: {CLASSIFICATION_SCHEMA}
Constraint: Return ONLY a valid raw JSON array of objects.
"""


# ── Internal utilities ───────────────────────────────────────────────────────

def check_ollama_available():
    """
    Scans the local Ollama API to find an active server and pulled models.
    - Matches preferred models from OLLAMA_MODELS list.
    - Avoids failure by picking any available model as a last resort.
    """
    try:
        resp = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        resp.raise_for_status()
        available = [m["name"] for m in resp.json().get("models", [])]
        
        if not available:
            print("    Ollama is running but no models are found. Use 'ollama pull'.")
            return None

        # Preference matching logic
        for preferred in OLLAMA_MODELS:
            for avail in available:
                if avail.startswith(preferred.split(":")[0]):
                    print(f"    Selected primary model: {avail}")
                    return avail

        # Fallback
        model = available[0]
        print(f"    Selected fallback model: {model}")
        return model

    except requests.ConnectionError:
        print("    Ollama NOT found. Expected running on http://localhost:11434")
        return None
    except Exception as e:
        print(f"    Connection check error: {e}")
        return None


def format_posts_for_llm(posts, start_idx=0):
    """
    Concatenates batch metadata into a structured list for the LLM.
    - Limits title length to 200 chars to conserve context window.
    - Provides upvote/comment context to help LLM gauge growth significance.
    """
    formatted = []
    for i, post in enumerate(posts):
        title = str(post.get("title_clean", post.get("title", "")))[:200]
        platform = str(post.get("platform", "reddit"))
        upvotes = post.get("upvotes", post.get("likes", 0))
        comments = post.get("comments", post.get("num_comments", 0))
        date = post.get("date", post.get("created_utc", ""))

        formatted.append(
            f"POST {start_idx + i + 1}:\n"
            f"Title: {title}\n"
            f"Platform: {platform} | Upvotes: {upvotes}, Comments: {comments}\n"
            f"Date: {date}"
        )
    return "\n\n".join(formatted)


def parse_llm_json(response_text):
    """
    Robust JSON extraction logic to handle various LLM formatting errors.
    - Thinking removal: Strips <think>...</think> tags if model is in 'chain of thought' mode.
    - Clean extraction: Attempts to find the first '[' and last ']' to isolate the JSON array.
    """
    text = response_text.strip()

    # REMOVE LOGIC TRACES: Many models (e.g., DeepSeek, Qwen) output 'thought' text in these tags.
    import re
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    # STRIP MARKDOWN FENCES: Removes ```json ... ``` wrappers.
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    # ATTEMPT CLEAN PARSE
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result.get("classifications", [result])
        return result
    except json.JSONDecodeError:
        pass

    # BRUTE-FORCE SUBSTRING EXTRACTION (Useful for long, messy model outputs)
    start_arr = text.find("[")
    end_arr = text.rfind("]") + 1
    if start_arr >= 0 and end_arr > start_arr:
        try:
            return json.loads(text[start_arr:end_arr])
        except json.JSONDecodeError:
            pass

    return None


# ── Classification Logic ────────────────────────────────────────────────────

def classify_batch_ollama(df, model, batch_size=BATCH_SIZE):
    """
    Loop through dataframe chunks and send to Ollama API.
    - Mirrors the batching structure used in production LLM benchmarks.
    - Automatically retries with None-padding if JSON parsing fails for a specific batch.
    """
    posts = df.to_dict("records")
    all_results = []
    total = len(posts)
    failed_batches = 0

    for i in range(0, total, batch_size):
        batch = posts[i:i + batch_size]
        batch_num = i // batch_size + 1
        
        posts_text = format_posts_for_llm(batch, i)
        prompt = (f"{SYSTEM_PROMPT}\n\nTask: Classify these {len(batch)} posts. "
                  f"Return JSON array ONLY.\n\n{posts_text}")

        try:
            # INTERACTING WITH LOCAL API
            resp = requests.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.3, "num_predict": 8192},
                },
                timeout=300, # Long timeout for intensive local inference
            )
            resp.raise_for_status()

            # EXTRACTION
            result_text = resp.json()["response"]
            parsed = parse_llm_json(result_text)

            if parsed and len(parsed) >= len(batch):
                all_results.extend(parsed[:len(batch)])
            else:
                # PADDING: ensure dataframe rows remain aligned with LLM results
                all_results.extend([None] * len(batch))
                failed_batches += 1

        except Exception as e:
            all_results.extend([None] * len(batch))
            failed_batches += 1
            print(f"\n    ✗ Batch {batch_num} error: {e}")

        done = min(i + batch_size, total)
        print(f"\r    Classified {done}/{total} ({done/total*100:.0f}%)", end="", flush=True)

    print()
    return all_results


def merge_results(df, results, prefix="llm"):
    """ Joins LLM classification JSON fields back into the main CSV dataframe. """
    fields = ["content_category", "sentiment", "virality_potential",
              "growth_type", "target_audience", "key_insight"]

    # Pre-populate empty columns
    for field in fields:
        df[f"{prefix}_{field}"] = pd.NA

    # Map results by row index
    classified = 0
    for i, result in enumerate(results):
        if i < len(df) and isinstance(result, dict):
            for field in fields:
                if field in result:
                    df.loc[df.index[i], f"{prefix}_{field}"] = result[field]
            classified += 1

    df["classification_source"] = "ollama" if classified > 0 else "none"
    return df


# ── Execution ────────────────────────────────────────────────────────────────

def main():
    """ Standard entry point for the LLM enrichment stage. """
    load_dotenv()
    print("=" * 60)
    print("STEP 4: LLM CLASSIFICATION (Ollama)")
    print("=" * 60)

    # Check for active local server
    model = check_ollama_available()

    if not model:
        print("\n  ⚠ LLM server not found or no models pulled. SKIPPING classification.")
        print("    Final enriched CSVs will be produced without LLM labels.\n")
        # Ensure clean directory is still populated for downstream stage2 success
        for name in ["reddit", "youtube", "twitter"]:
            in_path = os.path.join(IN_DIR, f"{name}_nlp.csv")
            if os.path.exists(in_path):
                pd.read_csv(in_path, encoding="utf-8").to_csv(
                    os.path.join(OUT_DIR, f"{name}_enriched.csv"), index=False)
        return

    # Process all platforms available in the NLP staging area
    for name in ["reddit", "youtube", "twitter"]:
        in_path = os.path.join(IN_DIR, f"{name}_nlp.csv")
        if not os.path.exists(in_path):
            continue

        print(f"\n  Processing {name} (LLM)...")
        df = pd.read_csv(in_path, encoding="utf-8")
        
        # ACTIVATE LOCAL LLM BATCH PROCESSING
        results = classify_batch_ollama(df, model)
        df = merge_results(df, results)

        # Write to FINAL destination: stage1/output/clean/
        out_path = os.path.join(OUT_DIR, f"{name}_enriched.csv")
        df.to_csv(out_path, index=False, encoding="utf-8")
        print(f"  Saved Final Data: {out_path}")

    print(f"\n{'=' * 60}")
    print(f"STEP 4 DONE — final enriched data available in {OUT_DIR}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
