"""
Claude Growth Analysis v2 — Sentiment, keywords, and temporal patterns.

Part of Stage 2 (Decode the Playbook). Generates 5 charts that answer:
  - How does community sentiment change over time? (and does it correlate with launches?)
  - Which content categories have the most positive/negative sentiment?
  - What keywords predict viral vs low-engagement posts? (TF-IDF correlation)
  - When do high-engagement posts appear? (day-of-week x hour heatmap)
  - Does positive sentiment actually predict more upvotes?

Uses enriched data from the processing pipeline — sentiment_compound and
sentiment_label columns are already computed in step3. If missing (raw data
fallback), VADER is computed on the fly.

Reads from: stage1/output/clean/*_enriched.csv
Writes to:  stage2/v2_sentiment/charts/*.png

Usage: python sentiment_analysis.py
Prereq: Run stage1 processing pipeline first (run_pipeline.py)
"""
import os
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# VADER and TF-IDF are only used as fallback when enriched data is not available.
# The processing pipeline (step3_nlp.py) already computes these columns.
from nltk.sentiment.vader import SentimentIntensityAnalyzer
from sklearn.feature_extraction.text import TfidfVectorizer

# ── Path resolution ──────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LAB_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))  # lab/
STAGE1_DIR = os.path.join(LAB_DIR, "stage1")
RAW_DIR = os.path.join(STAGE1_DIR, "output", "raw")
CLEAN_DIR = os.path.join(STAGE1_DIR, "output", "clean")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "charts")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── Style ────────────────────────────────────────────────────────────────────
plt.style.use("dark_background")
plt.rcParams.update({
    "figure.facecolor": "#1a1a2e",
    "axes.facecolor": "#16213e",
    "axes.edgecolor": "#444444",
    "text.color": "#e0e0e0",
    "axes.labelcolor": "#e0e0e0",
    "xtick.color": "#cccccc",
    "ytick.color": "#cccccc",
})
ACCENT = "#C8FF00"
ACCENT2 = "#00D4FF"
ACCENT3 = "#FF6B6B"

LAUNCHES = [
    ("2023-07-11", "Claude 2"),
    ("2024-03-04", "Claude 3"),
    ("2024-06-20", "Sonnet 3.5 + Artifacts"),
    ("2024-10-22", "Computer Use"),
    ("2025-03-04", "Sonnet 3.7"),
    ("2025-04-15", "Claude 4"),
    ("2025-05-22", "Claude Code"),
    ("2026-03-15", "Pentagon standoff"),
]


# ── Data loading ─────────────────────────────────────────────────────────────
def load_data():
    reddit_df = None
    youtube_df = None

    reddit_csv = os.path.join(CLEAN_DIR, "reddit_enriched.csv")
    if not os.path.exists(reddit_csv):
        reddit_csv = os.path.join(RAW_DIR, "reddit", "reddit_data.csv")
    if os.path.exists(reddit_csv):
        reddit_df = pd.read_csv(reddit_csv, parse_dates=["date"])
        reddit_df = reddit_df[reddit_df["date"] >= "2023-01-01"].copy()
        print(f"Loaded {len(reddit_df)} Reddit posts")

    youtube_csv = os.path.join(CLEAN_DIR, "youtube_enriched.csv")
    if not os.path.exists(youtube_csv):
        youtube_csv = os.path.join(RAW_DIR, "youtube", "youtube_data.csv")
    if os.path.exists(youtube_csv):
        youtube_df = pd.read_csv(youtube_csv, parse_dates=["date"])
        youtube_df = youtube_df[youtube_df["date"] >= "2023-01-01"].copy()
        print(f"Loaded {len(youtube_df)} YouTube videos")

    return reddit_df, youtube_df


# ── VADER sentiment scoring ──────────────────────────────────────────────────
def add_sentiment(df, text_col="title"):
    """Add compound, pos, neu, neg sentiment scores and a label column."""
    sia = SentimentIntensityAnalyzer()
    scores = df[text_col].fillna("").apply(sia.polarity_scores)
    df["sentiment_compound"] = scores.apply(lambda s: s["compound"])
    df["sentiment_pos"] = scores.apply(lambda s: s["pos"])
    df["sentiment_neg"] = scores.apply(lambda s: s["neg"])
    df["sentiment_label"] = df["sentiment_compound"].apply(
        lambda c: "Positive" if c >= 0.05 else ("Negative" if c <= -0.05 else "Neutral")
    )
    return df


# ── Chart 8: Sentiment over time ─────────────────────────────────────────────
def chart_8_sentiment_over_time(reddit_df):
    """Rolling weekly sentiment overlaid with product launches."""
    if reddit_df is None or len(reddit_df) == 0:
        return

    fig, axes = plt.subplots(2, 1, figsize=(14, 8), sharex=True,
                              gridspec_kw={"height_ratios": [2, 1]})
    fig.suptitle("Community sentiment over time", fontsize=16,
                 color=ACCENT, fontweight="bold")

    # Top: rolling sentiment with confidence band
    weekly = reddit_df.set_index("date").resample("W").agg(
        mean_sentiment=("sentiment_compound", "mean"),
        std_sentiment=("sentiment_compound", "std"),
        count=("sentiment_compound", "size"),
    ).dropna()

    ax = axes[0]
    ax.plot(weekly.index, weekly["mean_sentiment"], color=ACCENT, linewidth=1.5)
    ax.fill_between(
        weekly.index,
        weekly["mean_sentiment"] - weekly["std_sentiment"],
        weekly["mean_sentiment"] + weekly["std_sentiment"],
        alpha=0.15, color=ACCENT,
    )
    ax.axhline(y=0, color="#666", linestyle="-", linewidth=0.5)

    for date_str, name in LAUNCHES:
        launch = pd.Timestamp(date_str)
        ax.axvline(x=launch, color=ACCENT3, linestyle="--", alpha=0.5, linewidth=0.8)
        ax.text(launch, ax.get_ylim()[1] * 0.9, name, rotation=45,
                fontsize=7, color=ACCENT3, ha="left", va="top")

    ax.set_ylabel("Mean sentiment (compound)")
    ax.grid(axis="y", alpha=0.15)

    # Bottom: stacked proportions of pos/neu/neg
    ax2 = axes[1]
    weekly_labels = reddit_df.set_index("date").resample("W")["sentiment_label"].value_counts().unstack(fill_value=0)
    weekly_pcts = weekly_labels.div(weekly_labels.sum(axis=1), axis=0) * 100

    colors = {"Positive": ACCENT, "Neutral": "#888888", "Negative": ACCENT3}
    for label in ["Positive", "Neutral", "Negative"]:
        if label in weekly_pcts.columns:
            ax2.fill_between(weekly_pcts.index, 0, weekly_pcts[label],
                             alpha=0.3, color=colors[label], label=label)
            ax2.plot(weekly_pcts.index, weekly_pcts[label],
                     color=colors[label], linewidth=1)

    ax2.set_ylabel("% of posts")
    ax2.set_xlabel("Date")
    ax2.legend(fontsize=9, loc="upper left")
    ax2.grid(axis="y", alpha=0.15)

    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "08_sentiment_over_time.png"),
                dpi=150, bbox_inches="tight")
    plt.close()
    print("  Chart 8: Sentiment over time — SAVED")


# ── Chart 9: Sentiment by content type ────────────────────────────────────────
def chart_9_sentiment_by_content_type(reddit_df):
    """Box plot: sentiment distribution per content type."""
    if reddit_df is None or len(reddit_df) == 0:
        return

    fig, ax = plt.subplots(figsize=(14, 7))
    fig.suptitle("Sentiment by content type — where is the love (and hate)?",
                 fontsize=16, color=ACCENT, fontweight="bold")

    # Order by median sentiment
    order = (reddit_df.groupby("anthropic_content_category")["sentiment_compound"]
             .median().sort_values().index.tolist())

    palette = {ct: ACCENT if reddit_df[reddit_df["anthropic_content_category"] == ct]["sentiment_compound"].median() >= 0
               else ACCENT3 for ct in order}

    sns.boxplot(
        data=reddit_df, y="anthropic_content_category", x="sentiment_compound",
        order=order, palette=palette, fliersize=2, linewidth=0.8,
        ax=ax, orient="h",
    )
    ax.axvline(x=0, color="#666", linestyle="-", linewidth=0.8)
    ax.set_xlabel("Sentiment (compound score)")
    ax.set_ylabel("")
    ax.grid(axis="x", alpha=0.15)

    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "09_sentiment_by_content_type.png"),
                dpi=150, bbox_inches="tight")
    plt.close()
    print("  Chart 9: Sentiment by content type — SAVED")


# ── Chart 10: Keywords that predict high engagement ──────────────────────────
def chart_10_keyword_engagement(reddit_df):
    """TF-IDF keywords correlated with above-median engagement."""
    if reddit_df is None or len(reddit_df) < 50:
        return

    fig, axes = plt.subplots(1, 2, figsize=(14, 7))
    fig.suptitle("Keywords that predict engagement",
                 fontsize=16, color=ACCENT, fontweight="bold")

    titles = reddit_df["title"].fillna("").tolist()
    upvotes = reddit_df["upvotes"].values

    tfidf = TfidfVectorizer(max_features=500, stop_words="english",
                            min_df=5, ngram_range=(1, 2))
    X = tfidf.fit_transform(titles)
    feature_names = tfidf.get_feature_names_out()

    # Correlation of each term with upvotes
    correlations = np.array([
        np.corrcoef(X[:, i].toarray().ravel(), upvotes)[0, 1]
        for i in range(X.shape[1])
    ])

    # Top positive (viral keywords)
    top_pos_idx = np.argsort(correlations)[-20:][::-1]
    top_pos_words = [feature_names[i] for i in top_pos_idx]
    top_pos_corr = [correlations[i] for i in top_pos_idx]

    ax = axes[0]
    ax.barh(range(len(top_pos_words)), top_pos_corr, color=ACCENT, alpha=0.7)
    ax.set_yticks(range(len(top_pos_words)))
    ax.set_yticklabels(top_pos_words, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlabel("Correlation with upvotes")
    ax.set_title("Viral keywords", fontsize=12, color=ACCENT)
    ax.grid(axis="x", alpha=0.15)

    # Top negative (low engagement keywords)
    top_neg_idx = np.argsort(correlations)[:20]
    top_neg_words = [feature_names[i] for i in top_neg_idx]
    top_neg_corr = [correlations[i] for i in top_neg_idx]

    ax2 = axes[1]
    ax2.barh(range(len(top_neg_words)), top_neg_corr, color=ACCENT3, alpha=0.7)
    ax2.set_yticks(range(len(top_neg_words)))
    ax2.set_yticklabels(top_neg_words, fontsize=9)
    ax2.invert_yaxis()
    ax2.set_xlabel("Correlation with upvotes")
    ax2.set_title("Low-engagement keywords", fontsize=12, color=ACCENT3)
    ax2.grid(axis="x", alpha=0.15)

    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "10_keyword_engagement.png"),
                dpi=150, bbox_inches="tight")
    plt.close()
    print("  Chart 10: Keyword engagement — SAVED")


# ── Chart 11: Temporal heatmap ────────────────────────────────────────────────
def chart_11_temporal_heatmap(reddit_df):
    """When do high-engagement posts appear? Day-of-week × hour heatmap."""
    if reddit_df is None or len(reddit_df) == 0:
        return
    if "date_full" not in reddit_df.columns:
        print("  Chart 11: Skipped (no date_full column)")
        return

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    fig.suptitle("When do Claude posts get the most engagement?",
                 fontsize=16, color=ACCENT, fontweight="bold")

    df = reddit_df.copy()
    df["datetime"] = pd.to_datetime(df["date_full"], errors="coerce")
    df = df.dropna(subset=["datetime"])
    df["dow"] = df["datetime"].dt.day_name()
    df["hour"] = df["datetime"].dt.hour

    day_order = ["Monday", "Tuesday", "Wednesday", "Thursday",
                 "Friday", "Saturday", "Sunday"]

    # Left: volume heatmap
    pivot_count = df.pivot_table(index="dow", columns="hour", values="upvotes",
                                  aggfunc="count", fill_value=0)
    pivot_count = pivot_count.reindex(day_order)

    sns.heatmap(pivot_count, ax=axes[0], cmap="YlGn", linewidths=0.3,
                cbar_kws={"label": "Post count"})
    axes[0].set_title("Post volume", fontsize=12)
    axes[0].set_ylabel("")
    axes[0].set_xlabel("Hour (UTC)")

    # Right: avg engagement heatmap
    pivot_eng = df.pivot_table(index="dow", columns="hour", values="upvotes",
                                aggfunc="mean", fill_value=0)
    pivot_eng = pivot_eng.reindex(day_order)

    sns.heatmap(pivot_eng, ax=axes[1], cmap="YlOrRd", linewidths=0.3,
                cbar_kws={"label": "Avg upvotes"})
    axes[1].set_title("Avg engagement", fontsize=12)
    axes[1].set_ylabel("")
    axes[1].set_xlabel("Hour (UTC)")

    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "11_temporal_heatmap.png"),
                dpi=150, bbox_inches="tight")
    plt.close()
    print("  Chart 11: Temporal heatmap — SAVED")


# ── Chart 12: Sentiment vs engagement scatter ─────────────────────────────────
def chart_12_sentiment_engagement(reddit_df):
    """Does positive sentiment = more upvotes? Scatter with density."""
    if reddit_df is None or len(reddit_df) == 0:
        return

    fig, ax = plt.subplots(figsize=(12, 7))
    fig.suptitle("Does sentiment predict engagement?",
                 fontsize=16, color=ACCENT, fontweight="bold")

    colors = {"Positive": ACCENT, "Neutral": "#888888", "Negative": ACCENT3}
    for label, color in colors.items():
        subset = reddit_df[reddit_df["sentiment_label"] == label]
        ax.scatter(subset["sentiment_compound"], subset["upvotes"],
                   alpha=0.4, s=20, color=color, label=label, edgecolors="none")

    # Add median lines per group
    for label, color in colors.items():
        subset = reddit_df[reddit_df["sentiment_label"] == label]
        if len(subset) > 0:
            med = subset["upvotes"].median()
            ax.axhline(y=med, color=color, linestyle="--", alpha=0.5, linewidth=1)
            ax.text(0.95, med, f"{label} median: {med:.0f}",
                    transform=ax.get_yaxis_transform(), fontsize=8,
                    color=color, ha="right", va="bottom")

    ax.set_xlabel("Sentiment (compound)")
    ax.set_ylabel("Upvotes")
    ax.set_yscale("symlog", linthresh=10)
    ax.legend(fontsize=10)
    ax.grid(alpha=0.1)

    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "12_sentiment_engagement.png"),
                dpi=150, bbox_inches="tight")
    plt.close()
    print("  Chart 12: Sentiment vs engagement — SAVED")


# ── Summary stats ─────────────────────────────────────────────────────────────
def generate_sentiment_stats(reddit_df, youtube_df):
    stats = {}

    if reddit_df is not None and len(reddit_df) > 0:
        label_dist = reddit_df["sentiment_label"].value_counts().to_dict()
        stats["reddit_sentiment"] = {
            "mean_compound": round(reddit_df["sentiment_compound"].mean(), 3),
            "median_compound": round(reddit_df["sentiment_compound"].median(), 3),
            "positive_pct": round(label_dist.get("Positive", 0) / len(reddit_df) * 100, 1),
            "neutral_pct": round(label_dist.get("Neutral", 0) / len(reddit_df) * 100, 1),
            "negative_pct": round(label_dist.get("Negative", 0) / len(reddit_df) * 100, 1),
            "most_positive_type": (reddit_df.groupby("anthropic_content_category")["sentiment_compound"]
                                   .mean().idxmax()),
            "most_negative_type": (reddit_df.groupby("anthropic_content_category")["sentiment_compound"]
                                   .mean().idxmin()),
        }

    if youtube_df is not None and len(youtube_df) > 0:
        label_dist = youtube_df["sentiment_label"].value_counts().to_dict()
        stats["youtube_sentiment"] = {
            "mean_compound": round(youtube_df["sentiment_compound"].mean(), 3),
            "positive_pct": round(label_dist.get("Positive", 0) / len(youtube_df) * 100, 1),
            "neutral_pct": round(label_dist.get("Neutral", 0) / len(youtube_df) * 100, 1),
            "negative_pct": round(label_dist.get("Negative", 0) / len(youtube_df) * 100, 1),
        }

    output_file = os.path.join(SCRIPT_DIR, "sentiment_stats.json")
    with open(output_file, "w") as f:
        json.dump(stats, f, indent=2)
    print(f"\n  Sentiment stats saved to {output_file}")
    return stats


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("CLAUDE GROWTH — SENTIMENT & TEXT ANALYSIS (v2)")
    print("=" * 60)

    reddit_df, youtube_df = load_data()

    if reddit_df is None and youtube_df is None:
        print("\nNo data found! Run scrapers first.")
        return

    # Use existing sentiment from pipeline if available, otherwise compute
    for label, df in [("Reddit", reddit_df), ("YouTube", youtube_df)]:
        if df is None:
            continue
        if "sentiment_compound" in df.columns:
            print(f"\n  {label}: using existing VADER scores (mean={df['sentiment_compound'].mean():.3f})")
        else:
            print(f"\n  {label}: computing VADER sentiment...")
            if label == "Reddit":
                reddit_df = add_sentiment(reddit_df, "title")
            else:
                youtube_df = add_sentiment(youtube_df, "title")

    # Generate charts
    print("\nGenerating charts...")
    chart_8_sentiment_over_time(reddit_df)
    chart_9_sentiment_by_content_type(reddit_df)
    chart_10_keyword_engagement(reddit_df)
    chart_11_temporal_heatmap(reddit_df)
    chart_12_sentiment_engagement(reddit_df)

    stats = generate_sentiment_stats(reddit_df, youtube_df)

    print(f"\n{'=' * 60}")
    print(f"ALL CHARTS SAVED to {OUTPUT_DIR}")
    print(f"{'=' * 60}")

    if "reddit_sentiment" in stats:
        s = stats["reddit_sentiment"]
        print(f"\nKEY SENTIMENT FINDINGS:")
        print(f"  Overall: {s['positive_pct']}% positive, "
              f"{s['neutral_pct']}% neutral, {s['negative_pct']}% negative")
        print(f"  Most positive content: {s['most_positive_type']}")
        print(f"  Most negative content: {s['most_negative_type']}")


if __name__ == "__main__":
    main()
