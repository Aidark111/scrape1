"""
Step 4: LLM classification (local + cloud providers).
Goal: Categorize posts with a configurable LLM provider for stage2-ready enrichment.

High-level architecture:
    1. Provider select: Uses .env to choose ollama/openai/gemini/anthropic.
    2. Discovery: For Ollama, finds a pulled local model.
    3. Batching: Groups posts (10 at a time) for efficient prompt context.
    4. Processing: Calls selected provider with growth-focused system prompts.
    5. Validation: Strips thinking tags and markdown to extract clean JSON.
    6. Merge: Joins classification fields into the final dataset.

Reads from: output/step3_nlp/ (NLP-enriched data)
Writes to: output/clean/ (Final dataset ready for stage2 analysis)

Env selection examples:
    - LLM_PROVIDER=ollama
    - LLM_PROVIDER=openai
    - LLM_PROVIDER=gemini
    - LLM_PROVIDER=anthropic
"""
import os
import json
import re
import time
from datetime import datetime, timezone
import requests
import pandas as pd
from dotenv import load_dotenv

# Path resolution relative to stage1/processing directory
STAGE1_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IN_DIR = os.path.join(STAGE1_DIR, "output", "step3_nlp")
OUT_DIR = os.path.join(STAGE1_DIR, "output", "clean")
os.makedirs(OUT_DIR, exist_ok=True)

# ── Provider config ──────────────────────────────────────────────────────────
ENV_PATH = ".env"
SUPPORTED_PROVIDERS = {"ollama", "openai", "gemini", "anthropic"}

# Provider model defaults can be overridden in .env
DEFAULT_MODELS = {
    "ollama": "qwen3:8b",
    "openai": "gpt-4o-mini",
    "gemini": "gemini-1.5-flash",
    "anthropic": "claude-sonnet-4-20250514",
}

OLLAMA_BASE_URL = "http://localhost:11434"
# Preference list for local models (descending order)
OLLAMA_MODELS = ["qwen3:38b", "qwen3:8b", "llama3.1:8b", "mistral:7b", "gemma2:9b"]
BATCH_SIZE = 20  # Balanced for 8B-14B models on consumer hardware

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

def get_selected_provider():
    """Return validated provider from environment."""
    aliases = {"claude": "anthropic"}
    provider = os.getenv("LLM_PROVIDER", "openai").strip().lower()
    provider = aliases.get(provider, provider)
    if provider not in SUPPORTED_PROVIDERS:
        print(f"    Invalid LLM_PROVIDER='{provider}', falling back to 'anthropic'.")
        return "anthropic"
    return provider


def get_provider_model(provider):
    """Resolve model name for selected provider from environment defaults."""
    env_key = f"{provider.upper()}_MODEL"
    return os.getenv(env_key, DEFAULT_MODELS[provider]).strip()


def check_provider_ready(provider):
    """Return (is_ready, model, reason)."""
    model = get_provider_model(provider)

    if provider == "ollama":
        selected = check_ollama_available()
        if not selected:
            return False, None, "Ollama not reachable or no model pulled"
        return True, selected, "ok"

    key_map = {
        "openai": "OPENAI_API_KEY",
        "gemini": "GEMINI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
    }
    api_key = os.getenv(key_map[provider], "").strip()
    if not api_key:
        return False, None, f"Missing {key_map[provider]}"

    return True, model, "ok"

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


def _to_int_or_none(value):
    """Convert numeric-like values to int, else None."""
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def append_usage_row(usage_csv_path, row):
    """Append one batch usage row to CSV, creating file with header if needed."""
    usage_df = pd.DataFrame([row])
    exists = os.path.exists(usage_csv_path)
    usage_df.to_csv(
        usage_csv_path,
        mode="a",
        index=False,
        header=not exists,
        encoding="utf-8",
    )


def call_provider_response(provider, model, prompt):
    """
    Unified interface to call any supported LLM provider.
    Returns (response_text, usage_dict) where usage_dict has prompt/completion/total tokens.
    Each provider has a different API format — this function normalizes them all.
    """
    # ── Ollama (local, free) ──
    if provider == "ollama":
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.3, "num_predict": 8192},
            },
            timeout=300,
        )
        resp.raise_for_status()
        data = resp.json()
        usage = {
            "prompt_tokens": _to_int_or_none(data.get("prompt_eval_count")),
            "completion_tokens": _to_int_or_none(data.get("eval_count")),
            "total_tokens": _to_int_or_none(
                (data.get("prompt_eval_count") or 0) + (data.get("eval_count") or 0)
            ),
        }
        return data.get("response", ""), usage
    
    # ── OpenAI (cloud, paid) ──
    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise ValueError("OPENAI_API_KEY is missing or empty")

        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        try:
            response = client.chat.completions.create(
                model=model,
                temperature=0.3,
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "system",
                        "content": (
                            SYSTEM_PROMPT
                            + "\nOutput format requirement: "
                              '{"classifications": [ ... ]} where classifications is an array.'
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
            )
        except Exception as exc:
            msg = str(exc)
            if "401" in msg or "Unauthorized" in msg:
                raise RuntimeError(
                    "OpenAI auth failed (401). Check OPENAI_API_KEY and project permissions."
                ) from exc
            raise

        usage_raw = response.usage
        usage = {
            "prompt_tokens": _to_int_or_none(getattr(usage_raw, "prompt_tokens", None)),
            "completion_tokens": _to_int_or_none(getattr(usage_raw, "completion_tokens", None)),
            "total_tokens": _to_int_or_none(getattr(usage_raw, "total_tokens", None)),
        }
        return response.choices[0].message.content or "", usage

    # ── Google Gemini (cloud, free tier available) ──
    if provider == "gemini":
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            f"?key={api_key}"
        )
        resp = requests.post(
            url,
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": f"{SYSTEM_PROMPT}\n\n{prompt}"}]}],
                "generationConfig": {"temperature": 0.3},
            },
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        usage_raw = data.get("usageMetadata", {})
        usage = {
            "prompt_tokens": _to_int_or_none(usage_raw.get("promptTokenCount")),
            "completion_tokens": _to_int_or_none(usage_raw.get("candidatesTokenCount")),
            "total_tokens": _to_int_or_none(usage_raw.get("totalTokenCount")),
        }
        return data["candidates"][0]["content"]["parts"][0]["text"], usage

    # ── Anthropic Claude (cloud, paid) ──
    if provider == "anthropic":
        api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": 4096,
                "temperature": 0.3,
                "system": SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        usage_raw = data.get("usage", {})
        input_tokens = _to_int_or_none(usage_raw.get("input_tokens"))
        output_tokens = _to_int_or_none(usage_raw.get("output_tokens"))
        usage = {
            "prompt_tokens": input_tokens,
            "completion_tokens": output_tokens,
            "total_tokens": _to_int_or_none((input_tokens or 0) + (output_tokens or 0)),
        }
        return data["content"][0]["text"], usage

    raise ValueError(f"Unsupported provider: {provider}")


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
            for key in ["classifications", "results", "items", "data", "predictions"]:
                value = result.get(key)
                if isinstance(value, list):
                    return value
            return [result]
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

def classify_batch(df, provider, model, platform, out_path, usage_csv_path, batch_size=BATCH_SIZE):
    """
    Core classification loop — processes dataframe in batches through LLM.

    Crash-safe design:
    - After EVERY batch, saves partial results to out_path (CSV) and usage log.
    - If the script crashes mid-run, the CSV contains all completed batches.
    - Re-running will overwrite from scratch (no append-corruption).

    Row alignment:
    - If a batch fails (bad JSON, timeout), we pad with None instead of skipping.
    - This ensures results[i] always corresponds to df.iloc[i].
    """
    posts = df.to_dict("records")
    all_results = []
    total = len(posts)
    failed_batches = 0

    for i in range(0, total, batch_size):
        batch = posts[i:i + batch_size]
        batch_num = i // batch_size + 1
        
        posts_text = format_posts_for_llm(batch, i)
        prompt = (
            f"Task: Classify these {len(batch)} posts. "
            f"Return JSON object with key 'classifications' containing exactly {len(batch)} items.\n\n"
            f"{posts_text}"
        )

        started_at = datetime.now(timezone.utc)
        batch_usage = {
            "batch_id": batch_num,
            "platform": platform,
            "provider": provider,
            "model": model,
            "post_count": len(batch),
            "start_row": i,
            "end_row": i + len(batch) - 1,
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
            "started_at_utc": started_at.isoformat(),
            "ended_at_utc": None,
            "status": "ok",
            "error": "",
        }
        batch_start = time.time()

        try:
            # DEBUG: Print input being sent to LLM
            print(f"\n\n{'='*20} LLM INPUT (Batch {batch_num}) {'='*20}")
            print(prompt)
            print(f"{'='*60}\n")

            result_text, api_usage = call_provider_response(provider, model, prompt)
            batch_usage["prompt_tokens"] = api_usage.get("prompt_tokens")
            batch_usage["completion_tokens"] = api_usage.get("completion_tokens")
            batch_usage["total_tokens"] = api_usage.get("total_tokens")

            # DEBUG: Print output received from LLM
            print(f"{'='*20} LLM OUTPUT (Batch {batch_num}) {'='*20}")
            print(result_text)
            print(f"{'='*60}\n")

            parsed = parse_llm_json(result_text)

            if parsed and len(parsed) >= len(batch):
                all_results.extend(parsed[:len(batch)])
            else:
                # PADDING: ensure dataframe rows remain aligned with LLM results
                all_results.extend([None] * len(batch))
                failed_batches += 1
                batch_usage["status"] = "parse_failed"
                batch_usage["error"] = "Invalid JSON or insufficient classifications"

        except Exception as e:
            all_results.extend([None] * len(batch))
            failed_batches += 1
            batch_usage["status"] = "request_failed"
            batch_usage["error"] = str(e)
            print(f"\n    ✗ Batch {batch_num} error: {e}")

        batch_usage["duration_sec"] = round(time.time() - batch_start, 3)
        batch_usage["ended_at_utc"] = datetime.now(timezone.utc).isoformat()

        # Save partial classified output after each batch for crash-safe progress.
        partial_df = merge_results(
            df.copy(),
            all_results,
            prefix="ai_llm",
            source_provider=provider,
        )
        partial_df.to_csv(out_path, index=False, encoding="utf-8")

        # Persist usage row immediately after each batch.
        append_usage_row(usage_csv_path, batch_usage)

        done = min(i + batch_size, total)
        print(f"\r    Classified {done}/{total} ({done/total*100:.0f}%)", end="", flush=True)

    print()
    return all_results


def merge_results(df, results, prefix="ai_llm", source_provider=None):
    """
        Maps LLM JSON responses back to dataframe rows.
        - Writes stable ai_llm_* columns regardless of selected provider.
        - Stores the selected provider in classification_source.
        - Handles None results (failed batches) by leaving those cells as NA.
    """
    fields = ["content_category", "sentiment", "virality_potential",
              "growth_type", "target_audience", "key_insight"]

    # Pre-populate empty columns with stable ai_llm_* prefix.
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

            source = source_provider or prefix
            df["classification_source"] = source if classified > 0 else "none"
    return df


# ── Execution ────────────────────────────────────────────────────────────────

def main():
    """ Standard entry point for the LLM enrichment stage. """
    load_dotenv()
    provider = get_selected_provider()

    print("=" * 60)
    print(f"STEP 4: LLM CLASSIFICATION ({provider})")
    print("=" * 60)

    ready, model, reason = check_provider_ready(provider)

    if not ready:
        print(f"\n  Provider '{provider}' not ready: {reason}. SKIPPING classification.")
        print("    Final enriched CSVs will be produced without LLM labels.\n")
        # GRACEFUL FALLBACK: Copy step3 NLP output directly to output/clean/
        # so stage2 analysis scripts can still run (they guard missing LLM columns).
        for name in ["youtube", "reddit", "twitter"]:
            in_path = os.path.join(IN_DIR, f"{name}_nlp.csv")
            if os.path.exists(in_path):
                pd.read_csv(in_path, encoding="utf-8").to_csv(
                    os.path.join(OUT_DIR, f"{name}_enriched.csv"), index=False)
        return

    print(f"  Provider ready: {provider} | Model: {model}")
    usage_out_path = os.path.join(OUT_DIR, "llm_consumption.csv")
    if os.path.exists(usage_out_path):
        os.remove(usage_out_path)

    # Process all platforms available in the NLP staging area
    for name in ["reddit", "youtube", "twitter"]:
        in_path = os.path.join(IN_DIR, f"{name}_nlp.csv")
        if not os.path.exists(in_path):
            continue

        print(f"\n  Processing {name} ({provider})...")
        df = pd.read_csv(in_path, encoding="utf-8")
        
        out_path = os.path.join(OUT_DIR, f"{name}_enriched.csv")
        results = classify_batch(df, provider, model, name, out_path, usage_out_path)
        df = merge_results(df, results, prefix="ai_llm", source_provider=provider)

        # Final write still happens for clarity (already checkpointed every batch).
        df.to_csv(out_path, index=False, encoding="utf-8")
        print(f"  Saved Final Data: {out_path}")

    if os.path.exists(usage_out_path):
        print(f"  Saved LLM usage log: {usage_out_path}")

    print(f"\n{'=' * 60}")
    print(f"STEP 4 DONE — final enriched data available in {OUT_DIR}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
