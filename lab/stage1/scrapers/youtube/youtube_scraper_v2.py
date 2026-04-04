"""
YouTube Scraper v2 — Maximum coverage.
60+ targeted search queries to capture Claude/Anthropic content comprehensively.
API budget: ~6,500 of 10,000 free daily quota units.
Usage: python3 youtube_scraper_v2.py                 # reads YOUTUBE_API_KEY from .env
       python3 youtube_scraper_v2.py YOUR_API_KEY    # or pass directly
"""
import sys
import json
import csv
import os
from datetime import datetime
from dotenv import load_dotenv
from googleapiclient.discovery import build

STAGE1_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
OUTPUT_DIR = os.path.join(STAGE1_DIR, "output", "raw", "youtube")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# === 60+ SEARCH QUERIES — organized by category ===
SEARCH_QUERIES = [
    # --- Core product ---
    "Claude AI",
    "Claude 3",
    "Claude 3.5",
    "Claude 4",
    "Claude 3 Opus",
    "Claude 3.5 Sonnet",
    "Claude 3.7 Sonnet",
    "Claude Sonnet",
    "Claude Opus",
    "Claude Haiku",
    "Claude Pro subscription",

    # --- Features ---
    "Claude Artifacts",
    "Claude Projects feature",
    "Claude computer use demo",
    "Claude Code CLI",
    "Claude MCP protocol",
    "Claude API tutorial",
    "Claude system prompt tips",
    "Claude extended thinking",
    "Claude Max plan",

    # --- Comparisons ---
    "Claude vs ChatGPT",
    "Claude vs GPT-4",
    "Claude vs GPT-4o",
    "Claude vs Gemini",
    "Claude vs DeepSeek",
    "Claude vs Copilot",
    "Claude vs Llama",
    "Claude vs Grok",
    "ChatGPT vs Claude 2024",
    "ChatGPT vs Claude 2025",
    "best AI model 2024",
    "best AI model 2025",
    "best AI chatbot comparison",
    "best AI for coding 2024",
    "best AI for coding 2025",
    "best AI for writing",

    # --- Brand / Company ---
    "Anthropic",
    "Anthropic Claude",
    "Anthropic AI",
    "Dario Amodei",
    "Dario Amodei interview",
    "Anthropic safety AI",
    "Anthropic funding",
    "Anthropic valuation",

    # --- Use cases ---
    "Claude AI coding",
    "Claude AI writing",
    "Claude for developers",
    "Claude AI workflow",
    "Claude AI productivity",
    "Claude for business",
    "Claude AI data analysis",
    "using Claude for work",
    "Claude AI automation",

    # --- Reviews / Opinions ---
    "Claude review",
    "Claude AI review 2024",
    "Claude AI review 2025",
    "is Claude worth it",
    "Claude Pro worth it",
    "why I switched to Claude",
    "Claude honest review",

    # --- Tutorials ---
    "Claude AI tutorial",
    "Claude AI beginner guide",
    "Claude AI tips and tricks",
    "how to use Claude AI",
    "Claude prompt engineering",
]

MAX_RESULTS_PER_QUERY = 50

# Words that signal NOT Claude AI
EXCLUDE_KEYWORDS = [
    "van damme", "jean-claude", "jean claude", "kickboxer", "bloodsport",
    "claude ams", "programming guru",
    "debussy", "monet", "claude rains", "claude kelly",
    "claude giroux",
    "claude the cat",
    "speed", "asmr",  # spam channels
]

REQUIRE_ANY = [
    "claude", "anthropic", "sonnet", "opus", "haiku",
    "artifacts", "ai model", "ai chatbot", "chatbot",
    "dario", "amodei", "llm",
]


def get_video_details(youtube, video_ids):
    details = {}
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i+50]
        resp = youtube.videos().list(
            part="statistics,contentDetails,snippet",
            id=",".join(batch)
        ).execute()
        for item in resp.get("items", []):
            vid = item["id"]
            stats = item.get("statistics", {})
            snippet = item.get("snippet", {})
            details[vid] = {
                "views": int(stats.get("viewCount", 0)),
                "likes": int(stats.get("likeCount", 0)),
                "comments": int(stats.get("commentCount", 0)),
                "duration": item.get("contentDetails", {}).get("duration", ""),
                "channel_subs": None,
                "tags": snippet.get("tags", []),
                "description_snippet": snippet.get("description", "")[:200],
            }
    return details


def get_channel_info(youtube, channel_ids):
    """Get subscriber counts for channels."""
    info = {}
    unique_ids = list(set(channel_ids))
    for i in range(0, len(unique_ids), 50):
        batch = unique_ids[i:i+50]
        resp = youtube.channels().list(
            part="statistics",
            id=",".join(batch)
        ).execute()
        for item in resp.get("items", []):
            stats = item.get("statistics", {})
            info[item["id"]] = int(stats.get("subscriberCount", 0))
    return info


def search_youtube(youtube, query, max_results=50):
    print(f"  Searching: '{query}'...")
    all_items = []
    next_page = None
    while len(all_items) < max_results:
        try:
            request = youtube.search().list(
                part="snippet",
                q=query,
                type="video",
                order="viewCount",
                publishedAfter="2023-01-01T00:00:00Z",
                maxResults=min(50, max_results - len(all_items)),
                pageToken=next_page,
            )
            resp = request.execute()
        except Exception as e:
            print(f"    Error: {e}")
            break
        items = resp.get("items", [])
        if not items:
            break
        all_items.extend(items)
        next_page = resp.get("nextPageToken")
        if not next_page:
            break
    print(f"    Found {len(all_items)} videos")
    return all_items


def is_relevant(title):
    """Check if video is actually about Claude AI."""
    t = title.lower()
    if any(kw in t for kw in EXCLUDE_KEYWORDS):
        return False
    if any(kw in t for kw in REQUIRE_ANY):
        return True
    return False


# NOTE: Classification moved to stage1/analysis pipeline (LLM-based).
# Kept here for reference only.
# def classify_content_type(title):
def _classify_content_type_DISABLED(title):
    t = title.lower()
    if any(w in t for w in [" vs ", "versus", "compared", "comparison", "better",
                             "which is", "which one", "battle", "showdown", "face off"]):
        return "Comparison"
    elif any(w in t for w in ["tutorial", "how to", "guide", "learn", "beginner",
                               "step by step", "tips", "tricks", "course", "master"]):
        return "Tutorial"
    elif any(w in t for w in ["review", "honest", "my thoughts", "opinion", "worth it",
                               "tested", "testing", "hands on", "hands-on"]):
        return "Review"
    elif any(w in t for w in ["i built", "i made", "i used", "workflow", "use case",
                               "demo", "project", "showcase", "watch me", "using",
                               "built with", "made with", "automate", "automation"]):
        return "Use Case"
    elif any(w in t for w in ["news", "announced", "just dropped", "release", "update",
                               "new model", "launch", "breaking", "leaked",
                               "just released", "pricing", "free tier"]):
        return "News"
    elif any(w in t for w in ["insane", "mind-blowing", "mind blowing", "incredible",
                               "game changer", "game-changer", "wow", "crazy", "amazing",
                               "holy", "blown away", "changed everything", "can't believe",
                               "shocking", "unbelievable", "next level"]):
        return "Reaction"
    elif any(w in t for w in ["100 seconds", "explained", "what is", "introduction",
                               "understand", "in simple terms", "overview"]):
        return "Explainer"
    elif any(w in t for w in ["interview", "podcast", "conversation", "talk",
                               "fireside", "keynote", "summit"]):
        return "Interview"
    return "General"


# def classify_feature(title):
def _classify_feature_DISABLED(title):
    t = title.lower()
    if "artifact" in t:
        return "Artifacts"
    elif "sonnet" in t and ("3.5" in t or "3.6" in t):
        return "Sonnet 3.5"
    elif "sonnet" in t and ("4" in t or "3.7" in t):
        return "Sonnet 4"
    elif "opus" in t:
        return "Opus"
    elif "haiku" in t:
        return "Haiku"
    elif "computer use" in t:
        return "Computer Use"
    elif "claude code" in t or "cli" in t:
        return "Claude Code"
    elif "mcp" in t or "model context" in t:
        return "MCP"
    elif any(w in t for w in ["code", "coding", "programming", "developer"]):
        return "Coding"
    elif any(w in t for w in ["writing", "write", "essay", "creative"]):
        return "Writing"
    elif "api" in t:
        return "API"
    elif any(w in t for w in ["dario", "amodei", "anthropic"]):
        return "Company/Leadership"
    elif "safety" in t or "alignment" in t:
        return "AI Safety"
    return "General"


def main():
    load_dotenv()
    api_key = sys.argv[1] if len(sys.argv) > 1 else os.getenv("YOUTUBE_API_KEY")

    if not api_key:
        print("ERROR: No YouTube API key provided.")
        print("  Option 1: Set YOUTUBE_API_KEY in .env file")
        print("  Option 2: python youtube_scraper_v2.py YOUR_API_KEY")
        print("  Get a free key: https://console.cloud.google.com/")
        return

    print("=" * 60)
    print("CLAUDE GROWTH — YOUTUBE SCRAPER v2")
    print(f"Running {len(SEARCH_QUERIES)} search queries")
    print(f"Estimated API cost: ~{len(SEARCH_QUERIES) * 100 + 500} / 10,000 quota units")
    print("=" * 60)

    youtube = build("youtube", "v3", developerKey=api_key)

    all_videos = []
    seen_ids = set()
    skipped_irrelevant = 0

    for i, query in enumerate(SEARCH_QUERIES):
        print(f"\n[{i+1}/{len(SEARCH_QUERIES)}] {query}")
        items = search_youtube(youtube, query, MAX_RESULTS_PER_QUERY)

        video_ids = [item["id"]["videoId"] for item in items if "videoId" in item.get("id", {})]
        if not video_ids:
            continue

        details = get_video_details(youtube, video_ids)

        for item in items:
            vid = item["id"].get("videoId", "")
            if not vid or vid in seen_ids:
                continue

            snippet = item.get("snippet", {})
            title = snippet.get("title", "")

            # Filter irrelevant
            if not is_relevant(title):
                skipped_irrelevant += 1
                continue

            seen_ids.add(vid)
            stats = details.get(vid, {})
            pub_date = snippet.get("publishedAt", "")[:10]

            all_videos.append({
                "platform": "YouTube",
                "video_id": vid,
                "channel": snippet.get("channelTitle", ""),
                "channel_id": snippet.get("channelId", ""),
                "title": title,
                "date": pub_date,
                "views": stats.get("views", 0),
                "likes": stats.get("likes", 0),
                "comments": stats.get("comments", 0),
                "duration": stats.get("duration", ""),
                "url": f"https://youtube.com/watch?v={vid}",
                # Classification moved to stage1/analysis pipeline
                # "content_type": classify_content_type(title),
                # "claude_feature": classify_feature(title),
                "search_query": query,
                "tags": "|".join(stats.get("tags", [])[:5]),
                "description_snippet": stats.get("description_snippet", ""),
            })

    # Get channel subscriber counts
    print("\n\nFetching channel subscriber data...")
    channel_ids = list(set(v["channel_id"] for v in all_videos if v["channel_id"]))
    channel_subs = get_channel_info(youtube, channel_ids)
    for v in all_videos:
        v["channel_subscribers"] = channel_subs.get(v["channel_id"], 0)

    # Filter out pre-2023 noise (non-AI "Claude" videos)
    all_videos = [v for v in all_videos if v["date"] >= "2023-01-01"]

    # Sort by views
    all_videos.sort(key=lambda x: x["views"], reverse=True)

    # Save
    output_csv = os.path.join(OUTPUT_DIR, "youtube_data.csv")
    output_json = os.path.join(OUTPUT_DIR, "youtube_data.json")

    if all_videos:
        fieldnames = list(all_videos[0].keys())
        with open(output_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_videos)

    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(all_videos, f, indent=2, ensure_ascii=False)

    print(f"\n{'=' * 60}")
    print(f"DONE! {len(all_videos)} unique relevant videos")
    print(f"Skipped {skipped_irrelevant} irrelevant results")
    print(f"CSV: {output_csv}")
    print(f"{'=' * 60}")

    # Stats
    # from collections import Counter
    print(f"\nTop 15 by views:")
    for v in all_videos[:15]:
        print(f"  {v['views']:>12,} views | {v['channel']}: {v['title'][:55]}")

    # Classification stats (disabled — moved to analysis pipeline)
    # print(f"\nContent types:")
    # for t, c in Counter(v["content_type"] for v in all_videos).most_common():
    #     print(f"  {t:15s} {c:4d}")

    print(f"\nTop channels by total Claude views:")
    ch_views = {}
    ch_count = {}
    for v in all_videos:
        ch_views[v["channel"]] = ch_views.get(v["channel"], 0) + v["views"]
        ch_count[v["channel"]] = ch_count.get(v["channel"], 0) + 1
    for ch in sorted(ch_views, key=ch_views.get, reverse=True)[:15]:
        print(f"  {ch_views[ch]:>12,} views ({ch_count[ch]} vids) | {ch}")

    print(f"\nTimeline coverage:")
    months = sorted(set(v["date"][:7] for v in all_videos))
    print(f"  {months[0]} to {months[-1]} ({len(months)} months)")

    # print(f"\nFeatures mentioned:")
    # for t, c in Counter(v["claude_feature"] for v in all_videos).most_common():
    #     print(f"  {t:20s} {c:4d}")


if __name__ == "__main__":
    main()
