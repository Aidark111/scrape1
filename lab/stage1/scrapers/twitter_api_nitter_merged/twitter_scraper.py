"""
Twitter/X Scraper — API (free tier) + Nitter (public, no auth) merged.

Strategy:
  1. Twitter API v2 free tier (Bearer token) — recent search, last 7 days,
     ~1500 tweets/month. If BEARER_TOKEN not provided, skips with warning.
  2. Nitter public instances — no auth required, fits "public data only"
     constraint from the brief. Scrapes search pages via requests + HTML parsing.
  3. Merge + deduplicate results.

Usage:
  python twitter_scraper.py                          # Nitter only (or .env TWITTER_BEARER_TOKEN)
  python twitter_scraper.py --bearer YOUR_TOKEN      # API + Nitter
  python twitter_scraper.py --api-only               # API only (reads .env)
"""
import os
import sys
import json
import csv
import time
import re
import argparse
from datetime import datetime, timezone
from urllib.parse import quote_plus

from dotenv import load_dotenv
import requests
from bs4 import BeautifulSoup

# ── Paths ────────────────────────────────────────────────────────────────────
STAGE1_DIR = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)
)))
OUTPUT_DIR = os.path.join(STAGE1_DIR, "output", "raw", "twitter")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── Search queries ───────────────────────────────────────────────────────────
QUERIES = [
    "Claude AI",
    "Anthropic Claude",
    "#ClaudeAI",
    "Claude Sonnet",
    "Claude Opus",
    "Claude vs ChatGPT",
    "Claude vs GPT",
    "Claude Code",
    "Claude Artifacts",
]

# ── Nitter instances (try in order, use first that works) ────────────────────
NITTER_INSTANCES = [
    "https://nitter.privacydev.net",
    "https://nitter.poast.org",
    "https://nitter.woodland.cafe",
    "https://nitter.1d4.us",
]

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


# ═════════════════════════════════════════════════════════════════════════════
# PART 1: Twitter API v2 (free tier)
# ═════════════════════════════════════════════════════════════════════════════

def api_search(bearer_token, query, max_results=100):
    """
    Search recent tweets via Twitter API v2 free tier.
    Free tier: GET /2/tweets/search/recent — last 7 days, 10 req/month for app.
    """
    url = "https://api.twitter.com/2/tweets/search/recent"
    headers = {"Authorization": f"Bearer {bearer_token}"}
    params = {
        "query": f"{query} -is:retweet lang:en",
        "max_results": min(max_results, 100),
        "tweet.fields": "created_at,public_metrics,author_id,lang",
        "expansions": "author_id",
        "user.fields": "name,username,public_metrics,verified",
    }

    all_tweets = []
    next_token = None

    while len(all_tweets) < max_results:
        if next_token:
            params["next_token"] = next_token

        try:
            resp = requests.get(url, headers=headers, params=params, timeout=15)

            if resp.status_code == 401:
                print("    ERROR: Invalid bearer token")
                return []
            if resp.status_code == 429:
                print("    Rate limited (free tier: 10 requests/month)")
                return all_tweets
            if resp.status_code != 200:
                print(f"    API error {resp.status_code}: {resp.text[:200]}")
                return all_tweets

            data = resp.json()
        except Exception as e:
            print(f"    Request error: {e}")
            return all_tweets

        tweets = data.get("data", [])
        if not tweets:
            break

        # Build author lookup
        users = {}
        for user in data.get("includes", {}).get("users", []):
            users[user["id"]] = user

        for tweet in tweets:
            author = users.get(tweet.get("author_id"), {})
            metrics = tweet.get("public_metrics", {})
            all_tweets.append({
                "platform": "Twitter",
                "source": "api_v2",
                "tweet_id": tweet["id"],
                "author": author.get("name", ""),
                "handle": f"@{author.get('username', '')}",
                "followers": author.get("public_metrics", {}).get("followers_count", 0),
                "verified": author.get("verified", False),
                "content": tweet.get("text", ""),
                "date": tweet.get("created_at", "")[:10],
                "date_full": tweet.get("created_at", ""),
                "likes": metrics.get("like_count", 0),
                "retweets": metrics.get("retweet_count", 0),
                "replies": metrics.get("reply_count", 0),
                "impressions": metrics.get("impression_count", 0),
                "url": f"https://x.com/i/status/{tweet['id']}",
                "search_query": query,
            })

        next_token = data.get("meta", {}).get("next_token")
        if not next_token:
            break
        time.sleep(1)

    return all_tweets


def scrape_api(bearer_token, queries, max_per_query=100):
    """Run all queries through Twitter API v2."""
    print("\n=== Twitter API v2 (free tier) ===")
    all_tweets = []
    seen_ids = set()

    for i, query in enumerate(queries):
        print(f"  [{i+1}/{len(queries)}] API search: '{query}'")
        tweets = api_search(bearer_token, query, max_per_query)
        new = 0
        for t in tweets:
            if t["tweet_id"] not in seen_ids:
                seen_ids.add(t["tweet_id"])
                all_tweets.append(t)
                new += 1
        print(f"    {new} new tweets (total: {len(all_tweets)})")
        time.sleep(1)  # Respect rate limits

    print(f"  API total: {len(all_tweets)} unique tweets")
    return all_tweets


# ═════════════════════════════════════════════════════════════════════════════
# PART 2: Nitter (public, no auth)
# ═════════════════════════════════════════════════════════════════════════════

def find_working_nitter():
    """Find first working Nitter instance."""
    for instance in NITTER_INSTANCES:
        try:
            resp = requests.get(instance, headers={"User-Agent": USER_AGENT}, timeout=10)
            if resp.status_code == 200:
                print(f"  Using Nitter instance: {instance}")
                return instance
        except Exception:
            continue
    return None


def parse_nitter_tweet(tweet_el, nitter_base):
    """Parse a single tweet element from Nitter HTML."""
    try:
        # Author info
        fullname_el = tweet_el.select_one(".fullname")
        username_el = tweet_el.select_one(".username")
        author = fullname_el.get_text(strip=True) if fullname_el else ""
        handle = username_el.get_text(strip=True) if username_el else ""

        # Content
        content_el = tweet_el.select_one(".tweet-content")
        content = content_el.get_text(strip=True) if content_el else ""

        # Date
        date_el = tweet_el.select_one(".tweet-date a")
        date_str = ""
        if date_el and date_el.get("title"):
            date_str = date_el["title"]

        # Tweet link → extract tweet ID
        link_el = tweet_el.select_one(".tweet-link")
        tweet_link = ""
        tweet_id = ""
        if link_el and link_el.get("href"):
            tweet_link = link_el["href"]
            parts = tweet_link.rstrip("/").split("/")
            tweet_id = parts[-1] if parts else ""

        # Stats
        stats = tweet_el.select(".tweet-stat .tweet-stat-value") or []
        replies = stats[0].get_text(strip=True) if len(stats) > 0 else "0"
        retweets = stats[1].get_text(strip=True) if len(stats) > 1 else "0"
        likes = stats[2].get_text(strip=True) if len(stats) > 2 else "0"

        def parse_count(s):
            s = s.replace(",", "").strip()
            if not s:
                return 0
            if s.endswith("K"):
                return int(float(s[:-1]) * 1000)
            if s.endswith("M"):
                return int(float(s[:-1]) * 1000000)
            try:
                return int(s)
            except ValueError:
                return 0

        # Parse date
        date_clean = ""
        if date_str:
            for fmt in ["%b %d, %Y · %I:%M %p %Z", "%b %d, %Y · %H:%M %Z",
                        "%d/%m/%Y, %H:%M:%S", "%Y-%m-%dT%H:%M:%S"]:
                try:
                    dt = datetime.strptime(date_str.strip(), fmt)
                    date_clean = dt.strftime("%Y-%m-%d")
                    break
                except ValueError:
                    continue
            if not date_clean:
                # Try to extract just the date part
                match = re.search(r"(\w+ \d+, \d{4})", date_str)
                if match:
                    try:
                        dt = datetime.strptime(match.group(1), "%b %d, %Y")
                        date_clean = dt.strftime("%Y-%m-%d")
                    except ValueError:
                        pass

        return {
            "platform": "Twitter",
            "source": "nitter",
            "tweet_id": tweet_id,
            "author": author,
            "handle": handle,
            "followers": 0,  # Not available from Nitter search
            "verified": False,
            "content": content,
            "date": date_clean,
            "date_full": date_str,
            "likes": parse_count(likes),
            "retweets": parse_count(retweets),
            "replies": parse_count(replies),
            "impressions": 0,
            "url": f"https://x.com{tweet_link}" if tweet_link else "",
            "search_query": "",
        }
    except Exception as e:
        return None


def nitter_search(nitter_base, query, max_pages=3):
    """Search Nitter for tweets matching query."""
    tweets = []
    encoded_query = quote_plus(query)
    cursor = ""

    for page in range(max_pages):
        url = f"{nitter_base}/search?f=tweets&q={encoded_query}"
        if cursor:
            url += f"&cursor={cursor}"

        try:
            resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
            if resp.status_code != 200:
                print(f"    Nitter returned {resp.status_code}")
                break
        except Exception as e:
            print(f"    Nitter error: {e}")
            break

        soup = BeautifulSoup(resp.text, "html.parser")
        timeline = soup.select(".timeline-item")

        if not timeline:
            break

        for item in timeline:
            tweet = parse_nitter_tweet(item, nitter_base)
            if tweet and tweet["tweet_id"]:
                tweet["search_query"] = query
                tweets.append(tweet)

        # Find next page cursor
        show_more = soup.select_one(".show-more a")
        if show_more and show_more.get("href"):
            href = show_more["href"]
            cursor_match = re.search(r"cursor=([^&]+)", href)
            if cursor_match:
                cursor = cursor_match.group(1)
            else:
                break
        else:
            break

        time.sleep(2)  # Be polite to Nitter instances

    return tweets


def scrape_nitter(queries, max_pages_per_query=3):
    """Run all queries through Nitter."""
    print("\n=== Nitter (public, no auth) ===")

    nitter_base = find_working_nitter()
    if not nitter_base:
        print("  WARNING: No working Nitter instance found.")
        print("  Known instances may be down. Try again later or use --bearer for API.")
        print("  Tried:", ", ".join(NITTER_INSTANCES))
        return []

    all_tweets = []
    seen_ids = set()

    for i, query in enumerate(queries):
        print(f"  [{i+1}/{len(queries)}] Nitter search: '{query}'")
        tweets = nitter_search(nitter_base, query, max_pages_per_query)
        new = 0
        for t in tweets:
            if t["tweet_id"] not in seen_ids:
                seen_ids.add(t["tweet_id"])
                all_tweets.append(t)
                new += 1
        print(f"    {new} new tweets (total: {len(all_tweets)})")
        time.sleep(1)

    print(f"  Nitter total: {len(all_tweets)} unique tweets")
    return all_tweets


# ═════════════════════════════════════════════════════════════════════════════
# PART 3: Merge + save
# ═════════════════════════════════════════════════════════════════════════════

def merge_and_save(api_tweets, nitter_tweets):
    """Merge, deduplicate, filter, and save."""
    seen_ids = set()
    merged = []

    # API tweets take priority (more metadata)
    for t in api_tweets:
        if t["tweet_id"] and t["tweet_id"] not in seen_ids:
            seen_ids.add(t["tweet_id"])
            merged.append(t)

    for t in nitter_tweets:
        if t["tweet_id"] and t["tweet_id"] not in seen_ids:
            seen_ids.add(t["tweet_id"])
            merged.append(t)

    # Filter pre-2023
    merged = [t for t in merged if t["date"] >= "2023-01-01"]

    # Sort by likes
    merged.sort(key=lambda x: x["likes"], reverse=True)

    # Save
    output_csv = os.path.join(OUTPUT_DIR, "twitter_data.csv")
    output_json = os.path.join(OUTPUT_DIR, "twitter_data.json")

    if merged:
        fieldnames = list(merged[0].keys())
        with open(output_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(merged)

    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)

    return merged, output_csv


# ── CLI ──────────────────────────────────────────────────────────────────────
def parse_args():
    parser = argparse.ArgumentParser(
        description="Twitter/X scraper — API (free tier) + Nitter (public) merged."
    )
    parser.add_argument(
        "--bearer", type=str, default=None,
        help="Twitter API v2 Bearer token. If not provided, API is skipped.",
    )
    parser.add_argument(
        "--api-only", action="store_true",
        help="Skip Nitter, use API only.",
    )
    parser.add_argument(
        "--nitter-only", action="store_true",
        help="Skip API, use Nitter only.",
    )
    parser.add_argument(
        "--max-per-query", type=int, default=100,
        help="Max tweets per query for API (default: 100).",
    )
    parser.add_argument(
        "--nitter-pages", type=int, default=3,
        help="Max pages per query for Nitter (default: 3).",
    )
    return parser.parse_args()


def main():
    load_dotenv()
    args = parse_args()

    # Resolve bearer: CLI flag > .env
    bearer = args.bearer or os.getenv("TWITTER_BEARER_TOKEN")

    print("=" * 60)
    print("CLAUDE GROWTH — TWITTER/X SCRAPER")
    print("API (free tier) + Nitter (public, no auth)")
    print("=" * 60)

    api_tweets = []
    nitter_tweets = []

    # ── API ──
    if not args.nitter_only:
        if bearer:
            api_tweets = scrape_api(bearer, QUERIES, args.max_per_query)
        else:
            print("\n  WARNING: No bearer token found. Skipping Twitter API.")
            print("  Option 1: Set TWITTER_BEARER_TOKEN in .env")
            print("  Option 2: python twitter_scraper.py --bearer YOUR_TOKEN")
            print("  Get one free: https://developer.x.com/en/portal/dashboard")
            if args.api_only:
                print("\n  ERROR: --api-only but no bearer token available.")
                return

    # ── Nitter ──
    if not args.api_only:
        nitter_tweets = scrape_nitter(QUERIES, args.nitter_pages)

    # ── Merge + save ──
    if not api_tweets and not nitter_tweets:
        print("\n  No tweets collected from either source.")
        print("  Provide --bearer for API or check Nitter instance availability.")
        return

    merged, output_csv = merge_and_save(api_tweets, nitter_tweets)

    print(f"\n{'=' * 60}")
    print(f"DONE! {len(merged)} unique tweets")
    print(f"  From API:    {len(api_tweets)}")
    print(f"  From Nitter: {len(nitter_tweets)}")
    print(f"CSV: {output_csv}")
    print(f"{'=' * 60}")

    # Quick stats
    if merged:
        dates = sorted(set(t["date"] for t in merged if t["date"]))
        if dates:
            print(f"\nDate range: {dates[0]} to {dates[-1]}")
        print(f"\nTop 10 by likes:")
        for t in merged[:10]:
            print(f"  {t['likes']:>6} likes | @{t['handle']:15s} | {t['content'][:60]}")


if __name__ == "__main__":
    main()
