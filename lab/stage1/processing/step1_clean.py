"""
Step 1: Data cleaning — dedup, text normalization, date parsing, missing values.
Goal: Transform messy scraper output into a consistent format for downstream features.

Reads from: output/raw/ (Reddit, YouTube, Twitter)
Writes to: output/step1_cleaned/ (Intermediate format)

Note: This step is destructive regarding garbage data but preserves all original 
content in 'title_clean' while removing URLs and normalizing whitespace.
"""
import os
import re
import pandas as pd
import unicodedata

# Resolve paths relative to the lab/stage1 directory
STAGE1_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(STAGE1_DIR, "output", "raw")
OUT_DIR = os.path.join(STAGE1_DIR, "output", "step1_cleaned")
os.makedirs(OUT_DIR, exist_ok=True)


def clean_text(text):
    """
    Standardizes text content across all platforms.
    - Normalizes unicode (e.g., converts 'é' to standard form)
    - Replaces URLs with empty strings to avoid confusing NLP/LLM steps
    - Collapses multiple spaces/newlines into a single space
    """
    if not isinstance(text, str):
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"https?://\S+", "", text)       # remove URLs (noise for NLP)
    text = re.sub(r"\s+", " ", text).strip()        # collapse whitespace
    return text


def clean_reddit(path):
    """
    Processes Reddit CSV data.
    - Dedups by post_id (scrapers often hit common posts twice)
    - Filters for posts from 2023 onwards (Claude's main era)
    - Standardizes numeric columns (upvotes, comments)
    - Removes old classification tags to prevent stale data leaking into step4
    """
    df = pd.read_csv(path, encoding="utf-8")
    n_before = len(df)

    # Dedup by post_id (Reddit unique identifier)
    df = df.drop_duplicates(subset=["post_id"], keep="first")

    # Date filter: focus on recent Claude-era activity
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df[df["date"] >= "2023-01-01"].copy()
    df = df.dropna(subset=["date"])

    # Parse full datetime for future temporal analysis (e.g., time-of-day heatmaps)
    df["datetime"] = pd.to_datetime(df["date_full"], errors="coerce")

    # Text cleaning (stored in title_clean to keep original 'title' safe)
    df["title_clean"] = df["title"].apply(clean_text)

    # Fill missing values and ensure correct types (crucial for feature engineering in step2)
    df["author"] = df["author"].fillna("[deleted]")
    df["upvotes"] = pd.to_numeric(df["upvotes"], errors="coerce").fillna(0).astype(int)
    df["comments"] = pd.to_numeric(df["comments"], errors="coerce").fillna(0).astype(int)
    df["upvote_ratio"] = pd.to_numeric(df["upvote_ratio"], errors="coerce").fillna(0.5)
    df["selftext_length"] = pd.to_numeric(df["selftext_length"], errors="coerce").fillna(0).astype(int)

    # DROP OLD TAGS: We deliberately remove existing classification columns 
    # to ensure step4_llm_classify generates fresh, high-quality labels.
    for col in ["content_type", "claude_feature"]:
        if col in df.columns:
            df = df.drop(columns=[col])

    n_after = len(df)
    print(f"  Reddit: {n_before} -> {n_after} ({n_before - n_after} removed)")
    return df


def clean_youtube(path):
    """
    Processes YouTube CSV data.
    - Dedups by video_id
    - Standardizes views, likes, and comments
    - Normalizes subscriber counts for reach analysis
    """
    df = pd.read_csv(path, encoding="utf-8")
    n_before = len(df)

    # Dedup by video_id
    df = df.drop_duplicates(subset=["video_id"], keep="first")

    # Date filter
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df[df["date"] >= "2023-01-01"].copy()
    df = df.dropna(subset=["date"])

    # Text cleaning
    df["title_clean"] = df["title"].apply(clean_text)

    # Ensure numeric types (mapped to consistent names where possible)
    df["views"] = pd.to_numeric(df["views"], errors="coerce").fillna(0).astype(int)
    df["likes"] = pd.to_numeric(df["likes"], errors="coerce").fillna(0).astype(int)
    df["comments"] = pd.to_numeric(df["comments"], errors="coerce").fillna(0).astype(int)
    df["channel_subscribers"] = pd.to_numeric(
        df.get("channel_subscribers", pd.Series(dtype=int)), errors="coerce"
    ).fillna(0).astype(int)

    # Drop old tags to avoid stale classification data
    for col in ["content_type", "claude_feature"]:
        if col in df.columns:
            df = df.drop(columns=[col])

    n_after = len(df)
    print(f"  YouTube: {n_before} -> {n_after} ({n_before - n_after} removed)")
    return df


def clean_twitter(path):
    """
    Processes Twitter CSV data (supports both standard and Selenium scrapers).
    - Maps Title Case columns (from Selenium) to lowercase standard
    - Cleans 'tweet_id:' prefixes
    - Standardizes metrics (retweets, likes, impressions)
    """
    df = pd.read_csv(path, encoding="utf-8")
    n_before = len(df)

    # Normalize column names: Selenium scraper often uses Title Case or different labels.
    # This map ensures consistency across different Twitter scraper versions.
    col_map = {
        "Name": "author", "Handle": "handle", "Timestamp": "date_full",
        "Content": "content", "Comments": "replies", "Retweets": "retweets",
        "Likes": "likes", "Tweet Link": "url", "Tweet ID": "tweet_id",
        "Followers": "followers", "Verified": "verified", "Search Query": "search_query",
        "Analytics": "impressions",
    }
    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

    # Clean tweet_id prefix if Selenium format was used
    if "tweet_id" in df.columns:
        df["tweet_id"] = df["tweet_id"].astype(str).str.replace("tweet_id:", "", regex=False)

    # Dedup by tweet ID
    id_col = "tweet_id" if "tweet_id" in df.columns else None
    if id_col:
        df = df.drop_duplicates(subset=[id_col], keep="first")

    # Date parsing
    df["date_full"] = df.get("date_full", pd.Series(dtype=str))
    df["date"] = pd.to_datetime(df["date_full"], errors="coerce")
    df = df[df["date"] >= "2023-01-01"].copy()
    df = df.dropna(subset=["date"])
    df["datetime"] = df["date"]

    # Text cleaning (stores in title_clean, maps 'content' or 'title' to it)
    text_col = "content" if "content" in df.columns else "title"
    df["title_clean"] = df[text_col].apply(clean_text)
    if "title" not in df.columns:
        df["title"] = df["title_clean"]

    # Numeric standardization for engagement calculations in step2
    for col in ["likes", "retweets", "replies", "impressions", "followers"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    df["platform"] = "Twitter"

    n_after = len(df)
    print(f"  Twitter: {n_before} -> {n_after} ({n_before - n_after} removed)")
    return df


def main():
    """ Orchestrates the cleaning of all platforms using available raw CSVs. """
    print("=" * 60)
    print("STEP 1: DATA CLEANING")
    print("=" * 60)

    # Search for raw files in both stage1 output and the global data folder.
    project_root = os.path.dirname(STAGE1_DIR)
    fallback_raw = os.path.join(project_root, "data", "raw")

    reddit_paths = [
        os.path.join(RAW_DIR, "reddit", "reddit_data.csv"),
        os.path.join(fallback_raw, "reddit_data.csv"),
    ]
    youtube_paths = [
        os.path.join(RAW_DIR, "youtube", "youtube_data.csv"),
        os.path.join(fallback_raw, "youtube_data.csv"),
    ]
    twitter_paths = [
        os.path.join(RAW_DIR, "twitter", "twitter_data.csv"),
    ]
    # Specialized check for Selenium-specific Twitter output directory
    selenium_dir = os.path.join(STAGE1_DIR, "scrapers", "twitter_selenium_scrapper_deprecated", "output")
    if os.path.isdir(selenium_dir):
        import glob
        csvs = sorted(glob.glob(os.path.join(selenium_dir, "claude_growth_*.csv")))
        if csvs:
            twitter_paths.append(csvs[-1])  # latest run
    
    # Process each platform
    results = {}
    for name, paths, cleaner in [
        ("reddit", reddit_paths, clean_reddit),
        ("youtube", youtube_paths, clean_youtube),
        ("twitter", twitter_paths, clean_twitter),
    ]:
        found = None
        for p in paths:
            if os.path.exists(p):
                found = p
                break
        if found:
            print(f"\n  Loading {name}: {found}")
            df = cleaner(found)
            out_path = os.path.join(OUT_DIR, f"{name}_cleaned.csv")
            df.to_csv(out_path, index=False, encoding="utf-8")
            print(f"  Saved: {out_path}")
            results[name] = out_path
        else:
            print(f"\n  {name}: no raw data found, skipping")

    print(f"\n{'=' * 60}")
    print(f"STEP 1 DONE — outputs in {OUT_DIR}")
    print(f"{'=' * 60}")
    return results


if __name__ == "__main__":
    main()
