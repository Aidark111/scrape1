"""
Clean scraped data — remove irrelevant results.
Run after scrapers, before analysis.
Usage: python3 clean_data.py
"""
import pandas as pd
import os

DATA_DIR = os.path.join(os.path.dirname(__file__), "raw")
CLEAN_DIR = os.path.join(os.path.dirname(__file__), "clean")
os.makedirs(CLEAN_DIR, exist_ok=True)

# Words that signal a video is NOT about Claude AI
EXCLUDE_KEYWORDS = [
    "van damme", "jean-claude", "jean claude", "kickboxer", "bloodsport",
    "claude ams", "programming guru",
    "roblox from scratch",  # ChatGPT vs Gemini, not Claude
    "debussy",  # Claude Debussy the composer
    "claude kelly",  # songwriter
    "claude giroux",  # hockey player
    "claude the cat",
    "claude monet",
    "claude rains",
    "claude shannon",  # unless in AI context, but usually historical
]

# Words that MUST appear somewhere in title to confirm it's about Claude AI
REQUIRE_ANY = [
    "claude", "anthropic", "sonnet", "opus", "haiku",
    "claude.ai", "artifacts",
]


def clean_youtube():
    csv_path = os.path.join(DATA_DIR, "youtube_data.csv")
    if not os.path.exists(csv_path):
        print("No YouTube data found")
        return

    df = pd.read_csv(csv_path)
    original_count = len(df)

    # Step 1: Remove rows where title doesn't mention Claude/Anthropic at all
    df['title_lower'] = df['title'].str.lower()

    has_claude_keyword = df['title_lower'].apply(
        lambda t: any(kw in t for kw in REQUIRE_ANY)
    )

    # Step 2: Remove rows with known irrelevant keywords
    has_exclude = df['title_lower'].apply(
        lambda t: any(kw in t for kw in EXCLUDE_KEYWORDS)
    )

    df_clean = df[has_claude_keyword & ~has_exclude].copy()
    df_clean = df_clean.drop(columns=['title_lower'])

    removed = original_count - len(df_clean)
    print(f"YouTube: {original_count} → {len(df_clean)} videos ({removed} irrelevant removed)")

    # Show what was removed
    removed_df = df[~has_claude_keyword | has_exclude]
    if len(removed_df) > 0:
        print(f"\n  Removed examples:")
        for _, row in removed_df.head(15).iterrows():
            print(f"    ✗ {row['views']:>10,} views | {row['title'][:70]}")

    # Show top 10 after cleaning
    df_clean = df_clean.sort_values('views', ascending=False)
    print(f"\n  Top 10 after cleaning:")
    for _, row in df_clean.head(10).iterrows():
        print(f"    ✓ {row['views']:>10,} views | {row['title'][:70]}")

    df_clean.to_csv(os.path.join(CLEAN_DIR, "youtube_clean.csv"), index=False)
    print(f"\n  Saved to data/clean/youtube_clean.csv")


def clean_reddit():
    csv_path = os.path.join(DATA_DIR, "reddit_data.csv")
    if not os.path.exists(csv_path):
        print("No Reddit data found")
        return

    df = pd.read_csv(csv_path)
    original_count = len(df)

    # Reddit data is already well-targeted since we searched in specific subreddits
    # Just remove deleted/removed posts and duplicates
    df_clean = df[df['author'] != '[deleted]'].copy()
    df_clean = df_clean[df_clean['title'].str.len() > 5]
    df_clean = df_clean.drop_duplicates(subset=['title'], keep='first')

    removed = original_count - len(df_clean)
    print(f"\nReddit: {original_count} → {len(df_clean)} posts ({removed} deleted/duplicate removed)")

    df_clean.to_csv(os.path.join(CLEAN_DIR, "reddit_clean.csv"), index=False)
    print(f"  Saved to data/clean/reddit_clean.csv")


def print_summary():
    print("\n" + "=" * 60)
    print("DATA SUMMARY")
    print("=" * 60)

    reddit_path = os.path.join(CLEAN_DIR, "reddit_clean.csv")
    yt_path = os.path.join(CLEAN_DIR, "youtube_clean.csv")

    if os.path.exists(reddit_path):
        r = pd.read_csv(reddit_path)
        print(f"\nReddit: {len(r)} clean posts")
        print(f"  Subreddits: {r['subreddit'].nunique()}")
        print(f"  Date range: {r['date'].min()} to {r['date'].max()}")
        print(f"  Avg upvotes: {r['upvotes'].mean():.0f}")
        print(f"\n  Content types:")
        for ct, count in r['content_type'].value_counts().items():
            pct = count / len(r) * 100
            print(f"    {ct:20s} {count:4d} ({pct:.1f}%)")

    if os.path.exists(yt_path):
        y = pd.read_csv(yt_path)
        print(f"\nYouTube: {len(y)} clean videos")
        print(f"  Channels: {y['channel'].nunique()}")
        print(f"  Total views: {y['views'].sum():,.0f}")
        print(f"  Avg views: {y['views'].mean():,.0f}")


if __name__ == "__main__":
    print("=" * 60)
    print("CLEANING SCRAPED DATA")
    print("=" * 60)
    clean_youtube()
    clean_reddit()
    print_summary()
