"""
Step 2: Feature engineering — engagement score, virality ratio, discussion ratio, time features.
Goal: Quantify post success and extract metadata for future charts and growth analysis.

Reads from: output/step1_cleaned/ (Standardized data)
Writes to: output/step2_features/ (Featurized data)

Engagement Metrics:
- Reddit: Weighted sum of upvotes and comments
- YouTube: Weighted sum of views, likes, and comments
- Twitter: Weighted sum of likes, retweets, and replies
All platforms use 90th percentile thresholds for 'is_viral' to isolate outliers.
"""
import os
import pandas as pd
import numpy as np

# Resolve paths relative to the lab/stage1 directory
STAGE1_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IN_DIR = os.path.join(STAGE1_DIR, "output", "step1_cleaned")
OUT_DIR = os.path.join(STAGE1_DIR, "output", "step2_features")
os.makedirs(OUT_DIR, exist_ok=True)


def add_reddit_features(df):
    """
    Analyzes Reddit-specific metrics.
    - Engagement Score: Weights comments heavily (5x) as they represent deeper community interaction.
    - Consistency: Clips upvotes to 1 in denominator to prevent divide-by-zero during ratio calculation.
    - Virality: Identifies top 10% highest performers in the current dataset.
    - Temporal features: Breaks down dates into hours and days to find peak activity windows.
    """
    # Engagement calculation: upvotes are passive; comments represent active engagement.
    df["engagement_score"] = df["upvotes"] + (df["comments"] * 5)

    # Discussion ratio: measures how much conversation a post generates vs its passive popularity.
    df["comment_ratio"] = df["comments"] / df["upvotes"].clip(lower=1)
    # 90th percentile threshold for identifying highly discussed/controversial posts.
    df["is_controversial"] = df["comment_ratio"] >= df["comment_ratio"].quantile(0.9)

    # Virality flag: isolates the top 10% of posts by overall engagement.
    df["is_viral"] = df["engagement_score"] >= df["engagement_score"].quantile(0.9)

    # Title-based linguistic features: do long titles or questions drive more engagement?
    df["title_length"] = df["title_clean"].str.len()
    df["title_word_count"] = df["title_clean"].str.split().str.len()
    df["has_question"] = df["title_clean"].str.contains(r"\?", regex=True, na=False)
    df["has_exclamation"] = df["title_clean"].str.contains(r"!", regex=True, na=False)
    # Measures 'shouting' or use of acronyms (common in tech discussions)
    df["title_caps_ratio"] = df["title_clean"].apply(
        lambda t: sum(1 for c in str(t) if c.isupper()) / max(len(str(t)), 1)
    )

    # Date breakdown: enables heatmaps and weekend vs weekday analysis.
    dt = pd.to_datetime(df["datetime"], errors="coerce")
    df["hour"] = dt.dt.hour
    df["day_of_week"] = dt.dt.day_name()
    df["is_weekend"] = dt.dt.dayofweek >= 5
    df["month"] = dt.dt.month
    df["quarter"] = dt.dt.quarter
    # Grouping by year_quarter (e.g., 2024Q1) is essential for multi-year growth trends.
    df["year_quarter"] = dt.dt.to_period("Q").astype(str)

    print(f"  Reddit: {len(df)} rows, {len(df.columns)} columns")
    print(f"    Viral posts (top 10%): {df['is_viral'].sum()}")
    print(f"    Controversial posts (top 10% comment ratio): {df['is_controversial'].sum()}")
    return df


def add_youtube_features(df):
    """
    Analyzes YouTube video success.
    - Engagement Score: Strongly weights likes (10x) and comments (20x) relative to views.
    - Creator Tiers: Segments channels into Nano/Micro/Mid/Macro based on subscriber count.
    """
    # High weighting for comments as they are the hardest form of engagement to earn.
    df["engagement_score"] = df["views"] + (df["likes"] * 10) + (df["comments"] * 20)

    # Ratios per view: measures interaction density.
    df["like_ratio"] = df["likes"] / df["views"].clip(lower=1)
    df["comment_ratio"] = df["comments"] / df["views"].clip(lower=1)

    # 90th percentile threshold for viral videos in the dataset.
    df["is_viral"] = df["engagement_score"] >= df["engagement_score"].quantile(0.9)

    # Same linguistic features as Reddit for cross-platform comparison.
    df["title_length"] = df["title_clean"].str.len()
    df["title_word_count"] = df["title_clean"].str.split().str.len()
    df["has_question"] = df["title_clean"].str.contains(r"\?", regex=True, na=False)
    df["has_exclamation"] = df["title_clean"].str.contains(r"!", regex=True, na=False)
    df["title_caps_ratio"] = df["title_clean"].apply(
        lambda t: sum(1 for c in str(t) if c.isupper()) / max(len(str(t)), 1)
    )

    # Categorize channel size to distinguish between indie tutorials and major tech news.
    subs = df["channel_subscribers"]
    df["creator_tier"] = pd.cut(
        subs, bins=[0, 1_000, 10_000, 100_000, 1_000_000, float("inf")],
        labels=["Nano", "Micro", "Mid", "Macro", "Mega"],
    )

    # Time features for quarterly growth reports.
    dt = pd.to_datetime(df["date"], errors="coerce")
    df["month"] = dt.dt.month
    df["quarter"] = dt.dt.quarter
    df["year_quarter"] = dt.dt.to_period("Q").astype(str)

    print(f"  YouTube: {len(df)} rows, {len(df.columns)} columns")
    print(f"    Viral videos (top 10%): {df['is_viral'].sum()}")
    return df


def add_twitter_features(df):
    """
    Analyzes Twitter metrics.
    - Weights retweets (3x) and replies (5x) heavily for engagement calculation.
    - Provides basic temporal feature set similar to Reddit.
    """
    # Twitter rewards sharing (retweets) and discussion (replies).
    likes = df.get("likes", pd.Series(0, index=df.index))
    retweets = df.get("retweets", pd.Series(0, index=df.index))
    replies = df.get("replies", pd.Series(0, index=df.index))
    df["engagement_score"] = likes + (retweets * 3) + (replies * 5)

    # 90th percentile threshold for virality.
    if len(df) > 10:
        df["is_viral"] = df["engagement_score"] >= df["engagement_score"].quantile(0.9)
    else:
        df["is_viral"] = False

    # Extract length and word count from tweet content.
    df["title_length"] = df["title_clean"].str.len()
    df["title_word_count"] = df["title_clean"].str.split().str.len()
    df["has_question"] = df["title_clean"].str.contains(r"\?", regex=True, na=False)
    df["has_exclamation"] = df["title_clean"].str.contains(r"!", regex=True, na=False)

    # Basic time features.
    dt = pd.to_datetime(df["datetime"], errors="coerce")
    df["hour"] = dt.dt.hour
    df["day_of_week"] = dt.dt.day_name()
    df["is_weekend"] = dt.dt.dayofweek >= 5
    df["month"] = dt.dt.month
    df["quarter"] = dt.dt.quarter

    print(f"  Twitter: {len(df)} rows, {len(df.columns)} columns")
    return df


def main():
    """ Orstrates feature generation for all platforms sequentially. """
    print("=" * 60)
    print("STEP 2: FEATURE ENGINEERING")
    print("=" * 60)

    # Platform-specific processors
    processors = {
        "reddit": add_reddit_features,
        "youtube": add_youtube_features,
        "twitter": add_twitter_features,
    }

    # Process all available cleaned CSVs.
    for name, processor in processors.items():
        in_path = os.path.join(IN_DIR, f"{name}_cleaned.csv")
        if not os.path.exists(in_path):
            print(f"\n  {name}: no cleaned data, skipping")
            continue

        print(f"\n  Processing {name}...")
        df = pd.read_csv(in_path, encoding="utf-8")
        df = processor(df)

        # Write to intermediate storage for the NLP step (step3) to consume.
        out_path = os.path.join(OUT_DIR, f"{name}_features.csv")
        df.to_csv(out_path, index=False, encoding="utf-8")
        print(f"  Saved: {out_path}")

    print(f"\n{'=' * 60}")
    print(f"STEP 2 DONE — outputs in {OUT_DIR}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
