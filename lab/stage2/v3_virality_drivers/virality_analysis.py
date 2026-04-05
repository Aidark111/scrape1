"""
Claude Growth Analysis v3 — Virality drivers & engagement mechanics.

Part of Stage 2 (Decode the Playbook). Generates 4 charts that answer:
  - What post features correlate with high engagement? (correlation heatmap)
  - How do viral posts (top 10%) differ from normal ones? (distribution comparison)
  - Which YouTube creator tiers drive the most reach? (Nano → Mega breakdown)
  - What are the engagement quadrants? (broad appeal vs controversial vs niche)

Uses enriched data from the processing pipeline — engagement_score, is_viral,
comment_ratio, and other features are already computed in step2. If missing
(raw data fallback), features are computed on the fly.

Reads from: stage1/output/clean/*_enriched.csv
Writes to:  stage2/v3_virality_drivers/charts/*.png

Usage: python virality_analysis.py
Prereq: Run stage1 processing pipeline first (run_pipeline.py)
"""
import os
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# ── Path resolution ──────────────────────────────────────────────────────────
# Scripts live in lab/stage2/v3_virality_drivers/ but read data from lab/stage1/output/
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


def get_llm_category_col(df):
    """Resolve standardized LLM category column with lightweight fallback."""
    for col in ["ai_llm_content_category", "content_category"]:
        if df is not None and col in df.columns:
            return col
    return None


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


# ── Feature engineering ──────────────────────────────────────────────────────
def engineer_features(df):
    """Add derived columns useful for virality analysis."""
    df = df.copy()
    df["title_length"] = df["title"].fillna("").str.len()
    df["title_word_count"] = df["title"].fillna("").str.split().str.len()
    df["has_question"] = df["title"].fillna("").str.contains(r"\?", regex=True)
    df["has_exclamation"] = df["title"].fillna("").str.contains(r"!", regex=True)
    df["title_caps_ratio"] = df["title"].fillna("").apply(
        lambda t: sum(1 for c in t if c.isupper()) / max(len(t), 1)
    )

    if "comments" in df.columns and "upvotes" in df.columns:
        df["comment_ratio"] = df["comments"] / df["upvotes"].clip(lower=1)
        df["is_viral"] = df["upvotes"] >= df["upvotes"].quantile(0.9)
        df["is_controversial"] = df["comment_ratio"] >= df["comment_ratio"].quantile(0.9)

    return df


# ── Chart 13: Virality correlation matrix ────────────────────────────────────
def chart_13_virality_correlation(reddit_df):
    """What features correlate with high engagement?"""
    if reddit_df is None or len(reddit_df) < 50:
        return

    fig, ax = plt.subplots(figsize=(12, 10))
    fig.suptitle("What predicts a viral post?",
                 fontsize=16, color=ACCENT, fontweight="bold")

    numeric_cols = [
        "upvotes", "comments", "upvote_ratio", "selftext_length",
        "title_length", "title_word_count", "has_question",
        "has_exclamation", "title_caps_ratio", "comment_ratio",
    ]
    available = [c for c in numeric_cols if c in reddit_df.columns]
    corr = reddit_df[available].corr()

    mask = np.triu(np.ones_like(corr, dtype=bool))
    sns.heatmap(corr, mask=mask, annot=True, fmt=".2f", cmap="RdYlGn",
                center=0, linewidths=0.5, ax=ax, vmin=-1, vmax=1,
                annot_kws={"fontsize": 9})
    ax.set_xticklabels(ax.get_xticklabels(), rotation=45, ha="right", fontsize=9)
    ax.set_yticklabels(ax.get_yticklabels(), fontsize=9)

    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "13_virality_correlation.png"),
                dpi=150, bbox_inches="tight")
    plt.close()
    print("  Chart 13: Virality correlation — SAVED")


# ── Chart 14: Viral vs non-viral profile ─────────────────────────────────────
def chart_14_viral_profile(reddit_df):
    """Compare feature distributions for viral vs normal posts."""
    if reddit_df is None or len(reddit_df) < 50:
        return

    fig, axes = plt.subplots(2, 3, figsize=(16, 10))
    fig.suptitle("Viral vs normal posts — what's different?",
                 fontsize=16, color=ACCENT, fontweight="bold")

    features = [
        ("title_length", "Title length (chars)"),
        ("title_word_count", "Title word count"),
        ("comment_ratio", "Comment/upvote ratio"),
        ("upvote_ratio", "Upvote ratio"),
        ("selftext_length", "Self text length"),
        ("title_caps_ratio", "CAPS ratio in title"),
    ]

    viral = reddit_df[reddit_df["is_viral"]]
    normal = reddit_df[~reddit_df["is_viral"]]

    for idx, (col, label) in enumerate(features):
        if col not in reddit_df.columns:
            continue
        ax = axes[idx // 3][idx % 3]

        # Clip outliers for readability
        p99 = reddit_df[col].quantile(0.99)
        bins = np.linspace(0, p99, 30)

        ax.hist(normal[col].clip(upper=p99), bins=bins, alpha=0.5,
                color="#888", label="Normal", density=True)
        ax.hist(viral[col].clip(upper=p99), bins=bins, alpha=0.6,
                color=ACCENT, label="Viral (top 10%)", density=True)

        ax.set_xlabel(label, fontsize=9)
        ax.set_ylabel("Density", fontsize=9)
        ax.legend(fontsize=8)
        ax.grid(alpha=0.1)

    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "14_viral_profile.png"),
                dpi=150, bbox_inches="tight")
    plt.close()
    print("  Chart 14: Viral profile — SAVED")


# ── Chart 15: YouTube creator tier analysis ──────────────────────────────────
def chart_15_creator_tiers(youtube_df):
    """Segment creators by subscriber count, show how reach scales."""
    if youtube_df is None or len(youtube_df) == 0:
        return
    if "channel_subscribers" not in youtube_df.columns:
        print("  Chart 15: Skipped (no subscribers column)")
        return

    fig, axes = plt.subplots(1, 2, figsize=(14, 7))
    fig.suptitle("Creator tier analysis — who actually drives reach?",
                 fontsize=16, color=ACCENT, fontweight="bold")

    df = youtube_df.copy()
    df["channel_subscribers"] = pd.to_numeric(df["channel_subscribers"], errors="coerce")
    df = df.dropna(subset=["channel_subscribers"])

    # Define tiers
    bins = [0, 1_000, 10_000, 100_000, 1_000_000, float("inf")]
    labels = ["Nano\n(<1K)", "Micro\n(1K-10K)", "Mid\n(10K-100K)",
              "Macro\n(100K-1M)", "Mega\n(1M+)"]
    df["tier"] = pd.cut(df["channel_subscribers"], bins=bins, labels=labels)

    # Left: video count per tier
    tier_counts = df["tier"].value_counts().reindex(labels)
    axes[0].bar(range(len(labels)), tier_counts.values, color=ACCENT2, alpha=0.7)
    axes[0].set_xticks(range(len(labels)))
    axes[0].set_xticklabels(labels, fontsize=9)
    axes[0].set_ylabel("Number of videos")
    axes[0].set_title("Volume by creator tier", fontsize=12)
    for i, v in enumerate(tier_counts.values):
        axes[0].text(i, v + 0.5, str(int(v)), ha="center", fontsize=9, color="white")

    # Right: total views per tier
    tier_views = df.groupby("tier", observed=False)["views"].sum().reindex(labels)
    axes[1].bar(range(len(labels)), tier_views.values, color=ACCENT, alpha=0.7)
    axes[1].set_xticks(range(len(labels)))
    axes[1].set_xticklabels(labels, fontsize=9)
    axes[1].set_ylabel("Total views")
    axes[1].set_title("Reach by creator tier", fontsize=12)
    for i, v in enumerate(tier_views.values):
        axes[1].text(i, v + tier_views.max() * 0.01, f"{v:,.0f}",
                     ha="center", fontsize=8, color="white")

    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "15_creator_tiers.png"),
                dpi=150, bbox_inches="tight")
    plt.close()
    print("  Chart 15: Creator tiers — SAVED")


# ── Chart 16: Engagement ratio map ───────────────────────────────────────────
def chart_16_engagement_ratio(reddit_df):
    """Classify posts into quadrants: broad appeal, controversial, niche, dead."""
    if reddit_df is None or len(reddit_df) < 50:
        return

    fig, ax = plt.subplots(figsize=(12, 8))
    fig.suptitle("Engagement quadrants — broad appeal vs controversy",
                 fontsize=16, color=ACCENT, fontweight="bold")

    df = reddit_df[reddit_df["upvotes"] > 0].copy()
    med_upvotes = df["upvotes"].median()
    med_ratio = df["comment_ratio"].median()

    # Quadrant colors
    quadrant_colors = []
    for _, row in df.iterrows():
        if row["upvotes"] >= med_upvotes and row["comment_ratio"] < med_ratio:
            quadrant_colors.append(ACCENT)       # Broad appeal: high votes, low controversy
        elif row["upvotes"] >= med_upvotes and row["comment_ratio"] >= med_ratio:
            quadrant_colors.append(ACCENT3)      # Controversial: high votes, high discussion
        elif row["upvotes"] < med_upvotes and row["comment_ratio"] >= med_ratio:
            quadrant_colors.append(ACCENT2)      # Niche: low votes, high discussion
        else:
            quadrant_colors.append("#555555")    # Low engagement

    ax.scatter(df["upvotes"], df["comment_ratio"], c=quadrant_colors,
               alpha=0.4, s=15, edgecolors="none")

    ax.axvline(x=med_upvotes, color="#666", linestyle="--", linewidth=0.8)
    ax.axhline(y=med_ratio, color="#666", linestyle="--", linewidth=0.8)

    # Quadrant labels
    xlim = ax.get_xlim()
    ylim = ax.get_ylim()
    ax.text(xlim[1] * 0.7, ylim[0] + (med_ratio - ylim[0]) * 0.3,
            "BROAD APPEAL\nhigh upvotes, low discussion",
            fontsize=9, color=ACCENT, ha="center", style="italic")
    ax.text(xlim[1] * 0.7, med_ratio + (ylim[1] - med_ratio) * 0.7,
            "CONTROVERSIAL\nhigh upvotes, high discussion",
            fontsize=9, color=ACCENT3, ha="center", style="italic")
    ax.text(med_upvotes * 0.3, med_ratio + (ylim[1] - med_ratio) * 0.7,
            "NICHE\nlow upvotes, high discussion",
            fontsize=9, color=ACCENT2, ha="center", style="italic")
    ax.text(med_upvotes * 0.3, ylim[0] + (med_ratio - ylim[0]) * 0.3,
            "LOW ENGAGEMENT",
            fontsize=9, color="#888", ha="center", style="italic")

    ax.set_xlabel("Upvotes", fontsize=11)
    ax.set_ylabel("Comment/upvote ratio", fontsize=11)
    ax.set_xscale("symlog", linthresh=10)
    ax.grid(alpha=0.1)

    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "16_engagement_ratio.png"),
                dpi=150, bbox_inches="tight")
    plt.close()
    print("  Chart 16: Engagement ratio map — SAVED")


# ── Summary stats ─────────────────────────────────────────────────────────────
def generate_virality_stats(reddit_df, youtube_df):
    stats = {}

    if reddit_df is not None and len(reddit_df) > 0:
        llm_category_col = get_llm_category_col(reddit_df)
        viral = reddit_df[reddit_df["is_viral"]]
        normal = reddit_df[~reddit_df["is_viral"]]
        most_viral_type = (
            viral[llm_category_col].value_counts().index[0]
            if llm_category_col and len(viral) > 0 else "unknown"
        )
        most_controversial_type = (
            reddit_df.groupby(llm_category_col)["comment_ratio"].mean().idxmax()
            if llm_category_col else "unknown"
        )
        stats["reddit_virality"] = {
            "viral_threshold_upvotes": int(reddit_df["upvotes"].quantile(0.9)),
            "viral_count": int(len(viral)),
            "viral_avg_title_length": round(viral["title_length"].mean(), 1),
            "normal_avg_title_length": round(normal["title_length"].mean(), 1),
            "viral_question_pct": round(viral["has_question"].mean() * 100, 1),
            "normal_question_pct": round(normal["has_question"].mean() * 100, 1),
            "viral_avg_upvote_ratio": round(viral["upvote_ratio"].mean(), 3),
            "normal_avg_upvote_ratio": round(normal["upvote_ratio"].mean(), 3),
            "most_viral_content_type": most_viral_type,
            "most_controversial_type": most_controversial_type,
        }

    if youtube_df is not None and "channel_subscribers" in youtube_df.columns:
        df = youtube_df.copy()
        df["channel_subscribers"] = pd.to_numeric(df["channel_subscribers"], errors="coerce")
        mega = df[df["channel_subscribers"] >= 1_000_000]
        micro = df[(df["channel_subscribers"] >= 1_000) & (df["channel_subscribers"] < 10_000)]
        stats["youtube_creator_tiers"] = {
            "mega_videos": int(len(mega)),
            "mega_total_views": int(mega["views"].sum()) if len(mega) > 0 else 0,
            "micro_videos": int(len(micro)),
            "micro_total_views": int(micro["views"].sum()) if len(micro) > 0 else 0,
        }

    output_file = os.path.join(SCRIPT_DIR, "virality_stats.json")
    with open(output_file, "w") as f:
        json.dump(stats, f, indent=2)
    print(f"\n  Virality stats saved to {output_file}")
    return stats


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("CLAUDE GROWTH — VIRALITY DRIVERS (v3)")
    print("=" * 60)

    reddit_df, youtube_df = load_data()

    if reddit_df is None and youtube_df is None:
        print("\nNo data found! Run scrapers first.")
        return

    # Use existing features from pipeline if available, otherwise compute
    if reddit_df is not None:
        if "is_viral" in reddit_df.columns and "comment_ratio" in reddit_df.columns:
            print("\n  Reddit: using existing features from pipeline")
        else:
            print("\n  Reddit: computing features...")
            reddit_df = engineer_features(reddit_df)
        viral_count = reddit_df["is_viral"].sum()
        print(f"  Reddit: {viral_count} viral posts")

    # Generate charts
    print("\nGenerating charts...")
    chart_13_virality_correlation(reddit_df)
    chart_14_viral_profile(reddit_df)
    chart_15_creator_tiers(youtube_df)
    chart_16_engagement_ratio(reddit_df)

    stats = generate_virality_stats(reddit_df, youtube_df)

    print(f"\n{'=' * 60}")
    print(f"ALL CHARTS SAVED to {OUTPUT_DIR}")
    print(f"{'=' * 60}")

    if "reddit_virality" in stats:
        v = stats["reddit_virality"]
        print(f"\nKEY VIRALITY FINDINGS:")
        print(f"  Viral threshold: >= {v['viral_threshold_upvotes']} upvotes")
        print(f"  Viral posts use questions: {v['viral_question_pct']}% "
              f"vs normal {v['normal_question_pct']}%")
        print(f"  Most viral content type: {v['most_viral_content_type']}")
        print(f"  Most controversial type: {v['most_controversial_type']}")


if __name__ == "__main__":
    main()
