import argparse
import json
import math
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
from selenium.common.exceptions import WebDriverException

BASE_DIR = Path(__file__).resolve().parent
STAGE1_DIR = BASE_DIR.parent.parent.parent  # lab/stage1/
SCRAPER_DIR = BASE_DIR / "scraper"
if str(SCRAPER_DIR) not in sys.path:
    sys.path.insert(0, str(SCRAPER_DIR))

from twitter_scraper import Twitter_Scraper

DEFAULT_CLAUDE_QUERIES = [
    "Claude AI",
    '"Anthropic Claude"',
    "@AnthropicAI Claude",
    "#ClaudeAI",
    '"Claude" "Anthropic"',
]

OUTPUT_COLUMNS = [
    "Name",
    "Handle",
    "Timestamp",
    "Verified",
    "Content",
    "Comments",
    "Retweets",
    "Likes",
    "Analytics",
    "Tags",
    "Mentions",
    "Emojis",
    "Profile Image",
    "Tweet Link",
    "Tweet ID",
    "Tweeter ID",
    "Following",
    "Followers",
    "Search Query",
]

CHECKPOINT_EVERY = 100
CHECKPOINT_SLEEP_SECONDS = 10


def load_cookies_into_driver(driver, cookie_path: Path):
    if not cookie_path.exists():
        raise FileNotFoundError(f"Cookie file not found: {cookie_path}")

    raw = json.loads(cookie_path.read_text(encoding="utf-8"))
    loaded = 0

    driver.get("https://x.com")

    for cookie in raw:
        normalized = dict(cookie)
        normalized.pop("sameSite", None)

        expiry = normalized.get("expiry")
        if isinstance(expiry, float):
            normalized["expiry"] = int(expiry)

        try:
            driver.add_cookie(normalized)
            loaded += 1
        except WebDriverException:
            continue

    driver.get("https://x.com/home")
    return loaded


def build_query(keyword: str, since: str | None, until: str | None, lang: str | None = "en") -> str:
    parts = [keyword, "-is:retweet"]
    if lang:
        parts.append(f"lang:{lang}")
    if since:
        parts.append(f"since:{since}")
    if until:
        parts.append(f"until:{until}")
    return " ".join(parts)


def tuple_to_row(tweet_tuple, search_query: str):
    values = list(tweet_tuple)
    if len(values) < 18:
        values.extend([None] * (18 - len(values)))

    row = {
        "Name": values[0],
        "Handle": values[1],
        "Timestamp": values[2],
        "Verified": values[3],
        "Content": values[4],
        "Comments": values[5],
        "Retweets": values[6],
        "Likes": values[7],
        "Analytics": values[8],
        "Tags": values[9],
        "Mentions": values[10],
        "Emojis": values[11],
        "Profile Image": values[12],
        "Tweet Link": values[13],
        "Tweet ID": f"tweet_id:{values[14]}" if values[14] else "",
        "Tweeter ID": f"user_id:{values[15]}" if values[15] else "",
        "Following": values[16],
        "Followers": values[17],
        "Search Query": search_query,
    }
    return row


def scrape_query(cookie_path: Path, query: str, max_tweets: int, headless: str, latest: bool, top: bool):
    scraper = Twitter_Scraper(
        mail="",
        username="cookie_auth",
        password="cookie_auth",
        headlessState=headless,
        max_tweets=max_tweets,
    )

    try:
        loaded_count = load_cookies_into_driver(scraper.driver, cookie_path)
        print(f"Loaded cookies: {loaded_count}")

        scraper.scrape_tweets(
            max_tweets=max_tweets,
            no_tweets_limit=False,
            scrape_query=query,
            scrape_latest=latest,
            scrape_top=top,
        )
        return scraper.get_tweets()
    finally:
        if scraper.driver:
            scraper.driver.quit()


def write_outputs(rows, output_dir: Path, base_name: str):
    output_dir.mkdir(parents=True, exist_ok=True)

    if not rows:
        raise RuntimeError("No tweets were collected, so no output files were written.")

    df = pd.DataFrame(rows)
    for column in OUTPUT_COLUMNS:
        if column not in df.columns:
            df[column] = None

    df = df[OUTPUT_COLUMNS]
    df = df.drop_duplicates(subset=["Tweet ID", "Tweet Link", "Content"], keep="first")

    csv_path = output_dir / "twitter_data.csv"
    json_path = output_dir / "twitter_data.json"
    report_path = output_dir / "twitter_data_report.txt"

    df.to_csv(csv_path, index=False, encoding="utf-8")
    df.to_json(json_path, orient="records", force_ascii=False, indent=2)

    with report_path.open("w", encoding="utf-8") as report_file:
        report_file.write("Claude Selenium Scrape Report\n")
        report_file.write(f"Generated: {datetime.now().isoformat()}\n")
        report_file.write(f"Rows saved: {len(df)}\n")
        report_file.write(f"CSV: {csv_path.name}\n")
        report_file.write(f"JSON: {json_path.name}\n")

    print(f"Saved CSV:  {csv_path}")
    print(f"Saved JSON: {json_path}")
    print(f"Saved TXT:  {report_path}")


def write_checkpoint(rows, output_dir: Path, base_name: str, checkpoint_index: int):
    checkpoint_dir = output_dir / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(rows)
    for column in OUTPUT_COLUMNS:
        if column not in df.columns:
            df[column] = None

    df = df[OUTPUT_COLUMNS]
    df = df.drop_duplicates(subset=["Tweet ID", "Tweet Link", "Content"], keep="first")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = checkpoint_dir / f"{base_name}_checkpoint_{checkpoint_index:03d}_{timestamp}.csv"
    json_path = checkpoint_dir / f"{base_name}_checkpoint_{checkpoint_index:03d}_{timestamp}.json"

    df.to_csv(csv_path, index=False, encoding="utf-8")
    df.to_json(json_path, orient="records", force_ascii=False, indent=2)

    print(f"Checkpoint {checkpoint_index} saved ({len(df)} unique rows)")
    print(f"  CSV:  {csv_path}")
    print(f"  JSON: {json_path}")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Claude-focused Selenium Twitter scraper using saved cookies.",
    )
    parser.add_argument(
        "--cookies",
        default="auth/session_cookies.json",
        help="Cookie file path (default: auth/session_cookies.json)",
    )
    parser.add_argument(
        "--output-dir",
        default=str(STAGE1_DIR / "output" / "raw" / "twitter"),
        help="Directory where CSV/JSON/TXT outputs will be written",
    )
    parser.add_argument(
        "--base-name",
        default="claude_growth",
        help="Base filename for generated outputs",
    )
    parser.add_argument(
        "-t",
        "--tweets",
        type=int,
        default=1000,
        help="Total tweets to collect across all queries",
    )
    parser.add_argument(
        "--since",
        default=None,
        help="Optional X advanced search since date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--until",
        default=None,
        help="Optional X advanced search until date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--queries",
        nargs="*",
        default=None,
        help="Optional custom query keywords. If omitted, Claude-focused defaults are used.",
    )
    parser.add_argument(
        "--latest",
        action="store_true",
        help="Scrape latest tweets (default)",
    )
    parser.add_argument(
        "--top",
        action="store_true",
        help="Scrape top tweets instead of latest",
    )
    parser.add_argument(
        "--headless",
        choices=["yes", "no"],
        default="no",
        help="Headless browser mode",
    )
    parser.add_argument(
        "--lang",
        type=str,
        default="en",
        help="Language filter (e.g. 'en' for English, 'fr' for French, or None to skip language filter)",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    cookie_file = Path(args.cookies)
    output_dir = Path(args.output_dir)

    if args.latest and args.top:
        print("Please choose either --latest or --top, not both.")
        raise SystemExit(1)

    latest_mode = not args.top if not args.latest and not args.top else args.latest
    top_mode = args.top

    base_queries = args.queries if args.queries else DEFAULT_CLAUDE_QUERIES
    lang_filter = None if args.lang == "none" else args.lang
    expanded_queries = [build_query(query, args.since, args.until, lang_filter) for query in base_queries]
    per_query_limit = max(1, math.ceil(args.tweets / len(expanded_queries)))
    checkpoint_index = 0
    next_checkpoint_size = CHECKPOINT_EVERY

    print("Claude task queries:")
    for query in expanded_queries:
        print(f"  - {query}")
    print(f"Per-query limit: {per_query_limit}")
    print(f"Language filter: {lang_filter if lang_filter else 'None (all languages)'}")
    print(f"Total tweets target: {args.tweets}")

    collected_rows = []
    for query in expanded_queries:
        print()
        print(f"Scraping query: {query}")
        tweet_rows = scrape_query(
            cookie_path=cookie_file,
            query=query,
            max_tweets=per_query_limit,
            headless=args.headless,
            latest=latest_mode,
            top=top_mode,
        )

        for tweet_row in tweet_rows:
            collected_rows.append(tuple_to_row(tweet_row, query))

            if len(collected_rows) >= next_checkpoint_size:
                checkpoint_index += 1
                write_checkpoint(collected_rows, output_dir, args.base_name, checkpoint_index)
                print(
                    f"Collected {len(collected_rows)} rows. Sleeping {CHECKPOINT_SLEEP_SECONDS} seconds before continuing..."
                )
                time.sleep(CHECKPOINT_SLEEP_SECONDS)
                next_checkpoint_size += CHECKPOINT_EVERY

    write_outputs(collected_rows, output_dir, args.base_name)


if __name__ == "__main__":
    main()
