"""
Reddit Scraper for Claude Growth Analysis
Uses Reddit's public JSON endpoints — NO API KEY NEEDED.
Just run: python reddit_scraper.py
"""
import requests
import json
import csv
import time
import os
from datetime import datetime

USER_AGENT = "ClaudeGrowthResearch/1.0 (hackathon project)"
HEADERS = {"User-Agent": USER_AGENT}

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "raw")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# === CONFIG: What to scrape ===
TARGETS = [
    # (subreddit, search_query, sort, time_filter, label)
    ("ClaudeAI", None, "top", "all", "claudeai_top_alltime"),
    ("ClaudeAI", None, "top", "year", "claudeai_top_year"),
    ("ClaudeAI", None, "top", "month", "claudeai_top_month"),
    ("ClaudeAI", None, "hot", None, "claudeai_hot"),
    ("ChatGPT", "Claude", "top", "all", "chatgpt_claude_top"),
    ("ChatGPT", "Claude", "top", "year", "chatgpt_claude_year"),
    ("artificial", "Claude", "top", "all", "artificial_claude_top"),
    ("LocalLLaMA", "Claude", "top", "all", "locallama_claude_top"),
    ("singularity", "Claude", "top", "year", "singularity_claude_top"),
]

MAX_POSTS_PER_TARGET = 100  # Reddit returns max 100 per page


def fetch_reddit_json(url, params=None, max_retries=3):
    """Fetch JSON from Reddit with rate limiting and retries."""
    for attempt in range(max_retries):
        try:
            time.sleep(2)  # Be polite — Reddit rate limits at ~30 req/min
            resp = requests.get(url, headers=HEADERS, params=params, timeout=15)

            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 60))
                print(f"  Rate limited. Waiting {wait}s...")
                time.sleep(wait)
                continue

            if resp.status_code == 200:
                return resp.json()
            else:
                print(f"  HTTP {resp.status_code} on attempt {attempt+1}")
                time.sleep(5)

        except Exception as e:
            print(f"  Error on attempt {attempt+1}: {e}")
            time.sleep(5)

    return None


def scrape_subreddit(subreddit, sort="top", time_filter="all", limit=100):
    """Scrape posts from a subreddit listing."""
    url = f"https://www.reddit.com/r/{subreddit}/{sort}.json"
    params = {"limit": min(limit, 100)}
    if time_filter and sort == "top":
        params["t"] = time_filter

    print(f"  Fetching r/{subreddit}/{sort} (t={time_filter})...")
    data = fetch_reddit_json(url, params)

    if not data or "data" not in data:
        print(f"  Failed to fetch r/{subreddit}")
        return []

    posts = []
    for child in data["data"].get("children", []):
        p = child["data"]
        posts.append(extract_post(p, subreddit))

    # Pagination — get more if available
    after = data["data"].get("after")
    if after and len(posts) < limit:
        params["after"] = after
        time.sleep(2)
        data2 = fetch_reddit_json(url, params)
        if data2 and "data" in data2:
            for child in data2["data"].get("children", []):
                p = child["data"]
                posts.append(extract_post(p, subreddit))

    print(f"  Got {len(posts)} posts")
    return posts


def search_subreddit(subreddit, query, sort="top", time_filter="all", limit=100):
    """Search within a subreddit."""
    url = f"https://www.reddit.com/r/{subreddit}/search.json"
    params = {
        "q": query,
        "restrict_sr": "on",
        "sort": sort,
        "limit": min(limit, 100),
    }
    if time_filter:
        params["t"] = time_filter

    print(f"  Searching r/{subreddit} for '{query}' (sort={sort}, t={time_filter})...")
    data = fetch_reddit_json(url, params)

    if not data or "data" not in data:
        print(f"  Failed to search r/{subreddit}")
        return []

    posts = []
    for child in data["data"].get("children", []):
        p = child["data"]
        posts.append(extract_post(p, subreddit))

    print(f"  Got {len(posts)} posts")
    return posts


def extract_post(p, subreddit):
    """Extract relevant fields from a Reddit post."""
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
        "over_18": p.get("over_18", False),
        "post_id": p.get("id", ""),
    }


def classify_content_type(title):
    """Auto-classify post content type based on title keywords.
    Priority order: most specific first, Discussion as default.
    """
    t = title.lower()

    # 1. COMPARISON — Claude vs something else
    if any(w in t for w in [
        " vs ", "versus", "compared to", "comparison", "better than", "worse than",
        "switch from", "switched to", "switching to", "moved to", "moving to",
        "or claude", "claude or ", "over chatgpt", "over gpt", "instead of gpt",
        "chatgpt vs", "gpt vs", "gemini vs", "gpt-4 vs", "gpt4 vs",
        "which is better", "which one", "prefer claude", "prefer gpt",
        "beats", "beating", "destroys", "smokes", "wipes the floor",
    ]):
        return "Comparison"

    # 2. COMPLAINT / FRUSTRATION
    if any(w in t for w in [
        "issue", "bug", "broken", "error", "can't", "doesn't work", "won't",
        "frustrat", "disappoint", "downgrade", "worse", "terrible", "awful",
        "unusable", "garbage", "trash", "hate", "ruined", "nerf", "nerfed",
        "censored", "refuses to", "won't let me", "limit", "throttl",
        "outage", "down for", "not working", "stopped working", "regression",
        "paying for", "waste of money", "cancel", "unsubscri",
    ]):
        return "Complaint"

    # 3. USE CASE / SHOWCASE — sharing what they built or did
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

    # 4. REACTION / HYPE — emotional first impressions
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
        "blew my mind", "🔥", "🤯", "!!",
    ]):
        return "Reaction"

    # 5. NEWS / ANNOUNCEMENT
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

    # 6. TUTORIAL / GUIDE
    if any(w in t for w in [
        "tutorial", "how to", "guide", "step by step", "tips",
        "trick", "hack", "technique", "method", "approach",
        "prompt engineering", "prompting", "system prompt",
        "best way to", "best practice", "pro tip",
        "beginner", "getting started", "learn",
        "template", "cheat sheet",
    ]):
        return "Tutorial"

    # 7. FEATURE REQUEST
    if any(w in t for w in [
        "feature request", "wish", "please add", "should add",
        "would love", "would be nice", "hope they", "need",
        "suggestion", "idea for", "can we get", "when will",
        "waiting for", "desperately need", "missing feature",
    ]):
        return "Feature Request"

    # 8. MEME / HUMOR
    if any(w in t for w in [
        "meme", "lol", "lmao", "funny", "shitpost", "joke",
        "humor", "humour", "😂", "haha", "hilarious",
        "be like", "nobody:", "starter pack",
    ]):
        return "Meme"

    # 9. QUESTION — titles that are questions
    if t.strip().endswith("?") or t.startswith("how ") or t.startswith("what ") or \
       t.startswith("why ") or t.startswith("is ") or t.startswith("does ") or \
       t.startswith("can ") or t.startswith("should ") or t.startswith("will ") or \
       t.startswith("has ") or t.startswith("are ") or t.startswith("do ") or \
       t.startswith("where ") or t.startswith("when ") or \
       any(w in t for w in ["anyone know", "any idea", "help me", "eli5", "explain"]):
        return "Question"

    # 10. DISCUSSION — opinion, debate, meta
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

    # DEFAULT — if nothing matched, it's general discussion
    return "Discussion"


def classify_feature(title):
    """Auto-classify which Claude feature is mentioned."""
    title_lower = title.lower()
    if "artifact" in title_lower:
        return "Artifacts"
    elif "sonnet" in title_lower and ("3.5" in title_lower or "3.6" in title_lower):
        return "Sonnet 3.5"
    elif "sonnet" in title_lower and ("4" in title_lower or "3.7" in title_lower):
        return "Sonnet 4"
    elif "opus" in title_lower:
        return "Opus"
    elif any(w in title_lower for w in ["200k", "100k", "long context", "context window"]):
        return "Long Context"
    elif any(w in title_lower for w in ["code", "coding", "programming", "developer"]):
        return "Coding"
    elif any(w in title_lower for w in ["writing", "write", "essay", "creative"]):
        return "Writing"
    elif "project" in title_lower:
        return "Projects"
    elif "api" in title_lower:
        return "API"
    elif "computer use" in title_lower:
        return "Computer Use"
    elif "claude code" in title_lower:
        return "Claude Code"
    return "General"


def main():
    print("=" * 60)
    print("CLAUDE GROWTH — REDDIT SCRAPER")
    print("=" * 60)
    print()

    all_posts = []
    seen_ids = set()

    for subreddit, query, sort, time_filter, label in TARGETS:
        print(f"\n--- {label} ---")

        if query:
            posts = search_subreddit(subreddit, query, sort, time_filter)
        else:
            posts = scrape_subreddit(subreddit, sort, time_filter)

        # Deduplicate
        new = 0
        for p in posts:
            if p["post_id"] not in seen_ids:
                seen_ids.add(p["post_id"])
                p["content_type"] = classify_content_type(p["title"])
                p["claude_feature"] = classify_feature(p["title"])
                p["source_label"] = label
                all_posts.append(p)
                new += 1
        print(f"  {new} new unique posts (total: {len(all_posts)})")

    # Sort by upvotes descending
    all_posts.sort(key=lambda x: x["upvotes"], reverse=True)

    # Save to CSV
    output_file = os.path.join(OUTPUT_DIR, "reddit_data.csv")
    if all_posts:
        fieldnames = list(all_posts[0].keys())
        with open(output_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_posts)

    # Save to JSON too
    json_file = os.path.join(OUTPUT_DIR, "reddit_data.json")
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(all_posts, f, indent=2, ensure_ascii=False)

    print(f"\n{'=' * 60}")
    print(f"DONE! Scraped {len(all_posts)} unique posts")
    print(f"CSV saved: {output_file}")
    print(f"JSON saved: {json_file}")
    print(f"{'=' * 60}")

    # Quick stats
    print(f"\nQuick stats:")
    from collections import Counter
    type_counts = Counter(p["content_type"] for p in all_posts)
    for t, c in type_counts.most_common():
        print(f"  {t}: {c}")


if __name__ == "__main__":
    main()
