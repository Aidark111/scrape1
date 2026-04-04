"""
Reddit Scraper v2 — Enhanced time coverage.
Scrapes by quarterly time slices to get even distribution across Claude's history.
Usage: python3 reddit_scraper_v2.py
"""
import requests
import json
import csv
import time
import os
from datetime import datetime, timezone

USER_AGENT = "ClaudeGrowthResearch/1.0 (hackathon project)"
HEADERS = {"User-Agent": USER_AGENT}

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "raw")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# === SUBREDDITS TO SCRAPE ===
SUBREDDITS_DIRECT = ["ClaudeAI"]
SUBREDDITS_SEARCH = ["ChatGPT", "artificial", "LocalLLaMA", "singularity", "technology",
                      "MachineLearning", "ArtificialIntelligence", "OpenAI", "Bard"]

# === TIME SLICES for even coverage ===
# Each slice = (label, after_timestamp, before_timestamp)
# This ensures we get posts from EVERY period, not just viral peaks
TIME_SLICES = []
import calendar
# Generate quarterly slices from Q3 2023 (Claude 2 launch) to now
quarters = [
    ("2023-Q3", "2023-07-01", "2023-10-01"),
    ("2023-Q4", "2023-10-01", "2024-01-01"),
    ("2024-Q1", "2024-01-01", "2024-04-01"),
    ("2024-Q2", "2024-04-01", "2024-07-01"),
    ("2024-Q3", "2024-07-01", "2024-10-01"),
    ("2024-Q4", "2024-10-01", "2025-01-01"),
    ("2025-Q1", "2025-01-01", "2025-04-01"),
    ("2025-Q2", "2025-04-01", "2025-07-01"),
    ("2025-Q3", "2025-07-01", "2025-10-01"),
    ("2025-Q4", "2025-10-01", "2026-01-01"),
    ("2026-Q1", "2026-01-01", "2026-04-01"),
    ("2026-Q2", "2026-04-01", "2026-07-01"),
]

def to_ts(date_str):
    return int(datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())


def fetch_reddit_json(url, params=None, max_retries=3):
    for attempt in range(max_retries):
        try:
            time.sleep(2)
            resp = requests.get(url, headers=HEADERS, params=params, timeout=15)
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 60))
                print(f"    Rate limited. Waiting {wait}s...")
                time.sleep(wait)
                continue
            if resp.status_code == 200:
                return resp.json()
            else:
                print(f"    HTTP {resp.status_code} on attempt {attempt+1}")
                time.sleep(5)
        except Exception as e:
            print(f"    Error: {e}")
            time.sleep(5)
    return None


def extract_post(p, subreddit):
    created = datetime.fromtimestamp(p.get("created_utc", 0))
    return {
        "platform": "Reddit",
        "subreddit": f"r/{subreddit}",
        "title": p.get("title", ""),
        "author": p.get("author", "[deleted]"),
        "date": created.strftime("%Y-%m-%d"),
        "date_full": created.strftime("%Y-%m-%d %H:%M:%S"),
        "upvotes": p.get("ups", 0),
        "upvote_ratio": p.get("upvote_ratio", 0),
        "comments": p.get("num_comments", 0),
        "url": f"https://reddit.com{p.get('permalink', '')}",
        "selftext_length": len(p.get("selftext", "")),
        "is_self": p.get("is_self", False),
        "link_flair_text": p.get("link_flair_text", ""),
        "post_id": p.get("id", ""),
    }


def classify_content_type(title):
    t = title.lower()

    if any(w in t for w in [
        " vs ", "versus", "compared to", "comparison", "better than", "worse than",
        "switch from", "switched to", "switching to", "moved to", "moving to",
        "or claude", "claude or ", "over chatgpt", "over gpt", "instead of gpt",
        "chatgpt vs", "gpt vs", "gemini vs", "gpt-4 vs", "gpt4 vs",
        "which is better", "which one", "prefer claude", "prefer gpt",
        "beats", "beating", "destroys", "smokes", "wipes the floor",
    ]):
        return "Comparison"

    if any(w in t for w in [
        "issue", "bug", "broken", "error", "can't", "doesn't work", "won't",
        "frustrat", "disappoint", "downgrade", "worse", "terrible", "awful",
        "unusable", "garbage", "trash", "hate", "ruined", "nerf", "nerfed",
        "censored", "refuses to", "won't let me", "limit", "throttl",
        "outage", "down for", "not working", "stopped working", "regression",
        "paying for", "waste of money", "cancel", "unsubscri",
    ]):
        return "Complaint"

    if any(w in t for w in [
        "i used", "i built", "i made", "i created", "i wrote", "i generated",
        "i automated", "i asked claude", "i tried", "just tried",
        "here's what", "here is what", "check out what", "look what",
        "my experience", "my workflow", "my project", "my app",
        "use case", "using claude for", "using claude to",
        "built with", "made with", "powered by", "created with",
        "showcase", "sharing my", "wanted to share",
        "i got claude to", "claude helped me", "claude wrote",
        "claude generated", "claude made", "claude built",
        "works great for", "perfect for", "been using claude",
    ]):
        return "Use Case"

    if any(w in t for w in [
        "insane", "incredible", "amazing", "holy", "wow", "blown away",
        "game changer", "mind blown", "mind-blown", "mindblown",
        "impressed", "impressive", "unbelievable", "crazy good",
        "best ai", "best model", "love claude", "obsessed",
        "goat", "king", "god tier", "next level", "no way",
        "just discovered", "finally tried", "first time using",
        "changed my life", "changed everything", "revolutionary",
        "can't believe", "speechless", "stunned", "shocked",
        "so good", "too good", "absolutely", "genuinely",
        "underrated", "overrated", "slept on",
        "blew my mind", "!!",
    ]):
        return "Reaction"

    if any(w in t for w in [
        "announced", "announcement", "release", "released", "launch",
        "new model", "new version", "new feature", "just dropped",
        "introducing", "rolling out", "now available", "coming soon",
        "leaked", "rumor", "roadmap", "blog post", "press release",
        "pricing", "price change", "free tier", "pro plan",
        "partnership", "acquisition", "funding", "series",
        "benchmark", "leaderboard", "arena", "lmsys",
        "anthropic just", "anthropic is", "anthropic announced",
    ]):
        return "News"

    if any(w in t for w in [
        "tutorial", "how to", "guide", "step by step", "tips",
        "trick", "hack", "technique", "method", "approach",
        "prompt engineering", "prompting", "system prompt",
        "best way to", "best practice", "pro tip",
        "beginner", "getting started", "learn",
        "template", "cheat sheet",
    ]):
        return "Tutorial"

    if any(w in t for w in [
        "feature request", "wish", "please add", "should add",
        "would love", "would be nice", "hope they", "need",
        "suggestion", "idea for", "can we get", "when will",
        "waiting for", "desperately need", "missing feature",
    ]):
        return "Feature Request"

    if any(w in t for w in [
        "meme", "lol", "lmao", "funny", "shitpost", "joke",
        "humor", "humour", "haha", "hilarious",
        "be like", "nobody:", "starter pack",
    ]):
        return "Meme"

    if t.strip().endswith("?") or t.startswith("how ") or t.startswith("what ") or \
       t.startswith("why ") or t.startswith("is ") or t.startswith("does ") or \
       t.startswith("can ") or t.startswith("should ") or t.startswith("will ") or \
       t.startswith("has ") or t.startswith("are ") or t.startswith("do ") or \
       t.startswith("where ") or t.startswith("when ") or \
       any(w in t for w in ["anyone know", "any idea", "help me", "eli5", "explain"]):
        return "Question"

    if any(w in t for w in [
        "think", "opinion", "thoughts", "anyone else", "am i the only",
        "unpopular opinion", "hot take", "controversial", "debate",
        "discuss", "discussion", "perspective", "take on",
        "feel like", "seems like", "notice", "noticed",
        "theory", "prediction", "bet", "calling it",
        "rant", "vent", "psa", "reminder",
        "the problem with", "the issue with", "the thing about",
        "honestly", "seriously", "real talk",
    ]):
        return "Discussion"

    return "Discussion"


def classify_feature(title):
    t = title.lower()
    if "artifact" in t:
        return "Artifacts"
    elif "sonnet" in t and ("3.5" in t or "3.6" in t):
        return "Sonnet 3.5"
    elif "sonnet" in t and ("4" in t or "3.7" in t):
        return "Sonnet 4"
    elif "opus" in t:
        return "Opus"
    elif any(w in t for w in ["200k", "100k", "long context", "context window"]):
        return "Long Context"
    elif any(w in t for w in ["code", "coding", "programming", "developer"]):
        return "Coding"
    elif any(w in t for w in ["writing", "write", "essay", "creative"]):
        return "Writing"
    elif "project" in t:
        return "Projects"
    elif "api" in t:
        return "API"
    elif "computer use" in t:
        return "Computer Use"
    elif "claude code" in t:
        return "Claude Code"
    elif "mcp" in t:
        return "MCP"
    return "General"


def scrape_subreddit_top(subreddit, sort="top", time_filter="all", limit=100):
    url = f"https://www.reddit.com/r/{subreddit}/{sort}.json"
    params = {"limit": min(limit, 100)}
    if time_filter and sort == "top":
        params["t"] = time_filter
    data = fetch_reddit_json(url, params)
    if not data or "data" not in data:
        return []
    return [extract_post(c["data"], subreddit) for c in data["data"].get("children", [])]


def search_subreddit_timeslice(subreddit, query, after_ts, before_ts, sort="top", limit=100):
    """Search subreddit within a specific time window."""
    url = f"https://www.reddit.com/r/{subreddit}/search.json"
    # Reddit search supports timestamp filtering
    full_query = f"{query} timestamp:{after_ts}..{before_ts}" if query else f"timestamp:{after_ts}..{before_ts}"
    params = {
        "q": query or "claude",
        "restrict_sr": "on",
        "sort": sort,
        "limit": min(limit, 100),
        "t": "all",
    }
    data = fetch_reddit_json(url, params)
    if not data or "data" not in data:
        return []
    return [extract_post(c["data"], subreddit) for c in data["data"].get("children", [])]


def search_subreddit(subreddit, query, sort="top", time_filter="all", limit=100):
    url = f"https://www.reddit.com/r/{subreddit}/search.json"
    params = {
        "q": query,
        "restrict_sr": "on",
        "sort": sort,
        "limit": min(limit, 100),
    }
    if time_filter:
        params["t"] = time_filter
    data = fetch_reddit_json(url, params)
    if not data or "data" not in data:
        return []
    return [extract_post(c["data"], subreddit) for c in data["data"].get("children", [])]


def main():
    print("=" * 60)
    print("CLAUDE GROWTH — REDDIT SCRAPER v2")
    print("Enhanced time coverage for unbiased timeline analysis")
    print("=" * 60)

    all_posts = []
    seen_ids = set()

    def add_posts(posts, label):
        new = 0
        for p in posts:
            if p["post_id"] not in seen_ids:
                seen_ids.add(p["post_id"])
                p["content_type"] = classify_content_type(p["title"])
                p["claude_feature"] = classify_feature(p["title"])
                p["source_label"] = label
                all_posts.append(p)
                new += 1
        return new

    # ========================================
    # PHASE 1: r/ClaudeAI — deep coverage
    # ========================================
    print("\n=== PHASE 1: r/ClaudeAI deep scrape ===")

    for sort, tf, label in [
        ("top", "all", "claudeai_top_all"),
        ("top", "year", "claudeai_top_year"),
        ("top", "month", "claudeai_top_month"),
        ("hot", None, "claudeai_hot"),
        ("new", None, "claudeai_new"),
    ]:
        print(f"\n  r/ClaudeAI/{sort} (t={tf})")
        posts = scrape_subreddit_top("ClaudeAI", sort, tf)
        n = add_posts(posts, label)
        print(f"    {n} new (total: {len(all_posts)})")

    # Also search for specific high-value terms in ClaudeAI
    for query in ["artifacts", "sonnet", "opus", "computer use", "claude code", "MCP",
                   "haiku", "API", "pro plan", "system prompt", "context window",
                   "extended thinking", "claude max", "projects"]:
        print(f"\n  r/ClaudeAI search: '{query}'")
        posts = search_subreddit("ClaudeAI", query, "top", "all")
        n = add_posts(posts, f"claudeai_search_{query}")
        print(f"    {n} new (total: {len(all_posts)})")

    # ========================================
    # PHASE 2: Cross-community perception
    # ========================================
    print("\n=== PHASE 2: Cross-community scrape ===")

    for sub in SUBREDDITS_SEARCH:
        for tf in ["all", "year"]:
            print(f"\n  r/{sub} search 'Claude' (t={tf})")
            posts = search_subreddit(sub, "Claude", "top", tf)
            n = add_posts(posts, f"{sub.lower()}_claude_{tf}")
            print(f"    {n} new (total: {len(all_posts)})")

        # Also search for Anthropic
        print(f"\n  r/{sub} search 'Anthropic' (t=all)")
        posts = search_subreddit(sub, "Anthropic", "top", "all")
        n = add_posts(posts, f"{sub.lower()}_anthropic")
        print(f"    {n} new (total: {len(all_posts)})")

    # ========================================
    # PHASE 3: r/ClaudeAI sorted by NEW for timeline coverage
    # ========================================
    print("\n=== PHASE 3: Recent posts for timeline density ===")

    # Get newest posts with pagination for better time coverage
    url = "https://www.reddit.com/r/ClaudeAI/new.json"
    after_token = None
    for page in range(8):  # 8 pages x 100 = 800 recent posts
        params = {"limit": 100}
        if after_token:
            params["after"] = after_token
        print(f"\n  r/ClaudeAI/new page {page+1}")
        data = fetch_reddit_json(url, params)
        if not data or "data" not in data:
            break
        children = data["data"].get("children", [])
        if not children:
            break
        posts = [extract_post(c["data"], "ClaudeAI") for c in children]
        n = add_posts(posts, f"claudeai_new_page{page+1}")
        print(f"    {n} new (total: {len(all_posts)})")
        after_token = data["data"].get("after")
        if not after_token:
            break

    # ========================================
    # DONE — save
    # ========================================
    all_posts.sort(key=lambda x: x["upvotes"], reverse=True)

    output_csv = os.path.join(OUTPUT_DIR, "reddit_data.csv")
    output_json = os.path.join(OUTPUT_DIR, "reddit_data.json")

    if all_posts:
        fieldnames = list(all_posts[0].keys())
        with open(output_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_posts)

    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(all_posts, f, indent=2, ensure_ascii=False)

    print(f"\n{'=' * 60}")
    print(f"DONE! {len(all_posts)} unique posts")
    print(f"CSV: {output_csv}")
    print(f"{'=' * 60}")

    # Stats
    from collections import Counter
    print(f"\nContent types:")
    for t, c in Counter(p["content_type"] for p in all_posts).most_common():
        print(f"  {t:20s} {c:4d}")

    print(f"\nFeatures mentioned:")
    for t, c in Counter(p["claude_feature"] for p in all_posts).most_common():
        print(f"  {t:20s} {c:4d}")

    # Timeline coverage
    dates = sorted(set(p["date"][:7] for p in all_posts))
    print(f"\nTimeline coverage: {dates[0]} to {dates[-1]}")
    print(f"  Months covered: {len(dates)}")

    # Posts per quarter
    print(f"\nPosts per quarter:")
    q_counts = Counter()
    for p in all_posts:
        year = p["date"][:4]
        month = int(p["date"][5:7])
        q = (month - 1) // 3 + 1
        q_counts[f"{year}-Q{q}"] += 1
    for q in sorted(q_counts.keys()):
        bar = "█" * (q_counts[q] // 5)
        print(f"  {q}: {q_counts[q]:4d} {bar}")


if __name__ == "__main__":
    main()
