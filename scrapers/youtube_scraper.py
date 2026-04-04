"""
YouTube Scraper for Claude Growth Analysis
Requires a free YouTube Data API key (5 min setup — see README).
Run: python youtube_scraper.py YOUR_API_KEY
"""
import sys
import json
import csv
import os
from datetime import datetime

try:
    from googleapiclient.discovery import build
except ImportError:
    print("Installing google-api-python-client...")
    os.system("pip install google-api-python-client")
    from googleapiclient.discovery import build

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "raw")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# === CONFIG: Search queries ===
SEARCH_QUERIES = [
    "Claude AI",
    "Claude vs ChatGPT",
    "Claude vs GPT-4",
    "Claude 3.5 Sonnet",
    "Claude Artifacts",
    "Anthropic Claude review",
    "Claude AI coding",
    "Claude computer use",
    "Claude 4",
    "Claude Code CLI",
]

MAX_RESULTS_PER_QUERY = 50


def get_video_details(youtube, video_ids):
    """Fetch detailed stats for a batch of video IDs."""
    details = {}
    # API allows 50 IDs per call
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i+50]
        resp = youtube.videos().list(
            part="statistics,contentDetails",
            id=",".join(batch)
        ).execute()

        for item in resp.get("items", []):
            vid = item["id"]
            stats = item.get("statistics", {})
            details[vid] = {
                "views": int(stats.get("viewCount", 0)),
                "likes": int(stats.get("likeCount", 0)),
                "comments": int(stats.get("commentCount", 0)),
                "duration": item.get("contentDetails", {}).get("duration", ""),
            }
    return details


def search_youtube(youtube, query, max_results=50):
    """Search YouTube and return video metadata."""
    print(f"  Searching: '{query}'...")
    all_items = []
    next_page = None

    while len(all_items) < max_results:
        request = youtube.search().list(
            part="snippet",
            q=query,
            type="video",
            order="viewCount",
            maxResults=min(50, max_results - len(all_items)),
            pageToken=next_page,
        )
        resp = request.execute()
        items = resp.get("items", [])
        if not items:
            break

        all_items.extend(items)
        next_page = resp.get("nextPageToken")
        if not next_page:
            break

    print(f"  Found {len(all_items)} videos")
    return all_items


def classify_content_type(title):
    """Auto-classify video content type."""
    title_lower = title.lower()
    if any(w in title_lower for w in ["vs", "versus", "compared", "comparison", "better"]):
        return "Comparison"
    elif any(w in title_lower for w in ["tutorial", "how to", "guide", "learn", "beginner"]):
        return "Tutorial"
    elif any(w in title_lower for w in ["review", "honest", "my thoughts", "opinion"]):
        return "Review"
    elif any(w in title_lower for w in ["i built", "i made", "i used", "workflow", "use case", "demo"]):
        return "Use Case"
    elif any(w in title_lower for w in ["news", "announced", "just dropped", "release", "update", "new"]):
        return "News"
    elif any(w in title_lower for w in ["insane", "mind-blowing", "incredible", "game changer", "wow", "crazy"]):
        return "Reaction"
    elif any(w in title_lower for w in ["100 seconds", "explained", "what is", "introduction"]):
        return "Explainer"
    return "Other"


def classify_feature(title):
    """Auto-classify which Claude feature is discussed."""
    title_lower = title.lower()
    if "artifact" in title_lower:
        return "Artifacts"
    elif "sonnet" in title_lower and ("3.5" in title_lower or "3.6" in title_lower):
        return "Sonnet 3.5"
    elif "sonnet" in title_lower and ("4" in title_lower or "3.7" in title_lower):
        return "Sonnet 4"
    elif "opus" in title_lower:
        return "Opus"
    elif "computer use" in title_lower:
        return "Computer Use"
    elif "claude code" in title_lower:
        return "Claude Code"
    elif any(w in title_lower for w in ["code", "coding", "programming", "developer"]):
        return "Coding"
    elif any(w in title_lower for w in ["writing", "write", "essay", "creative"]):
        return "Writing"
    elif "api" in title_lower:
        return "API"
    return "General"


def main():
    if len(sys.argv) < 2:
        print("=" * 60)
        print("USAGE: python youtube_scraper.py YOUR_API_KEY")
        print()
        print("Get a free API key in 5 minutes:")
        print("1. Go to https://console.cloud.google.com/")
        print("2. Create a new project (any name)")
        print("3. Go to APIs & Services > Enable APIs")
        print("4. Search 'YouTube Data API v3' and enable it")
        print("5. Go to APIs & Services > Credentials")
        print("6. Click 'Create Credentials' > 'API Key'")
        print("7. Copy the key and run this script with it")
        print("=" * 60)
        return

    api_key = sys.argv[1]

    print("=" * 60)
    print("CLAUDE GROWTH — YOUTUBE SCRAPER")
    print("=" * 60)

    youtube = build("youtube", "v3", developerKey=api_key)

    all_videos = []
    seen_ids = set()

    for query in SEARCH_QUERIES:
        print(f"\n--- {query} ---")
        items = search_youtube(youtube, query, MAX_RESULTS_PER_QUERY)

        video_ids = [item["id"]["videoId"] for item in items if "videoId" in item.get("id", {})]
        details = get_video_details(youtube, video_ids)

        for item in items:
            vid = item["id"].get("videoId", "")
            if not vid or vid in seen_ids:
                continue
            seen_ids.add(vid)

            snippet = item.get("snippet", {})
            stats = details.get(vid, {})
            pub_date = snippet.get("publishedAt", "")[:10]
            title = snippet.get("title", "")

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
                "content_type": classify_content_type(title),
                "claude_feature": classify_feature(title),
                "search_query": query,
            })

    # Sort by views
    all_videos.sort(key=lambda x: x["views"], reverse=True)

    # Save CSV
    output_file = os.path.join(OUTPUT_DIR, "youtube_data.csv")
    if all_videos:
        fieldnames = list(all_videos[0].keys())
        with open(output_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_videos)

    # Save JSON
    json_file = os.path.join(OUTPUT_DIR, "youtube_data.json")
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(all_videos, f, indent=2, ensure_ascii=False)

    print(f"\n{'=' * 60}")
    print(f"DONE! Scraped {len(all_videos)} unique videos")
    print(f"CSV: {output_file}")
    print(f"JSON: {json_file}")
    print(f"{'=' * 60}")

    # Quick stats
    print(f"\nTop 10 by views:")
    for v in all_videos[:10]:
        print(f"  {v['views']:>10,} views | {v['channel']}: {v['title'][:60]}")


if __name__ == "__main__":
    main()
