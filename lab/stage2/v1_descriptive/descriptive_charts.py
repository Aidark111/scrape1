"""
Claude Growth Analysis v1 — Descriptive charts and summary stats.
Run AFTER scrapers have produced data.
Usage: python descriptive_charts.py
"""
import pandas as pd
import matplotlib.pyplot as plt
import json
import os
from datetime import datetime

plt.style.use('dark_background')
plt.rcParams['figure.facecolor'] = '#1a1a2e'
plt.rcParams['axes.facecolor'] = '#16213e'
plt.rcParams['axes.edgecolor'] = '#444444'
plt.rcParams['text.color'] = '#e0e0e0'
plt.rcParams['axes.labelcolor'] = '#e0e0e0'
plt.rcParams['xtick.color'] = '#cccccc'
plt.rcParams['ytick.color'] = '#cccccc'
ACCENT = '#C8FF00'
ACCENT2 = '#00D4FF'
ACCENT3 = '#FF6B6B'

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LAB_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))  # lab/
STAGE1_DIR = os.path.join(LAB_DIR, "stage1")
RAW_DIR = os.path.join(STAGE1_DIR, "output", "raw")
CLEAN_DIR = os.path.join(STAGE1_DIR, "output", "clean")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "charts")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Claude product launch dates for overlay
LAUNCHES = [
    ("2023-07-11", "Claude 2"),
    ("2024-03-04", "Claude 3"),
    ("2024-06-20", "Sonnet 3.5\n+ Artifacts"),
    ("2024-10-22", "Computer Use"),
    ("2025-03-04", "Sonnet 3.7"),
    ("2025-04-15", "Claude 4"),
    ("2025-05-22", "Claude Code"),
    ("2026-03-15", "Pentagon\nstandoff"),
]


def load_data():
    """Load cleaned data if available, otherwise raw."""
    reddit_df = None
    youtube_df = None

    # Try enriched (pipeline output) first, fall back to raw
    reddit_csv = os.path.join(CLEAN_DIR, "reddit_enriched.csv")
    if not os.path.exists(reddit_csv):
        reddit_csv = os.path.join(RAW_DIR, "reddit", "reddit_data.csv")
    if os.path.exists(reddit_csv):
        reddit_df = pd.read_csv(reddit_csv, parse_dates=["date"])
        reddit_df = reddit_df[reddit_df["date"] >= "2023-01-01"].copy()
        print(f"Loaded {len(reddit_df)} Reddit posts from {reddit_csv}")

    youtube_csv = os.path.join(CLEAN_DIR, "youtube_enriched.csv")
    if not os.path.exists(youtube_csv):
        youtube_csv = os.path.join(RAW_DIR, "youtube", "youtube_data.csv")
    if os.path.exists(youtube_csv):
        youtube_df = pd.read_csv(youtube_csv, parse_dates=["date"])
        youtube_df = youtube_df[youtube_df["date"] >= "2023-01-01"].copy()
        print(f"Loaded {len(youtube_df)} YouTube videos from {youtube_csv}")

    return reddit_df, youtube_df


def chart_1_timeline_with_launches(reddit_df, youtube_df):
    """Chart 1: Post volume over time overlaid with product launches."""
    fig, axes = plt.subplots(2, 1, figsize=(14, 8), sharex=True)
    fig.suptitle("Claude mention volume vs product launches", fontsize=16, color=ACCENT, fontweight='bold')

    for ax, df, label, color in [
        (axes[0], reddit_df, "Reddit posts per week", ACCENT),
        (axes[1], youtube_df, "YouTube videos per week", ACCENT2),
    ]:
        if df is not None and len(df) > 0:
            weekly = df.set_index("date").resample("W").size()
            ax.fill_between(weekly.index, weekly.values, alpha=0.3, color=color)
            ax.plot(weekly.index, weekly.values, color=color, linewidth=1.5)

        # Overlay launch dates
        for date_str, name in LAUNCHES:
            launch_date = pd.Timestamp(date_str)
            ax.axvline(x=launch_date, color=ACCENT3, linestyle='--', alpha=0.6, linewidth=0.8)
            ax.text(launch_date, ax.get_ylim()[1] * 0.85, name,
                    rotation=45, fontsize=7, color=ACCENT3, ha='left', va='top')

        ax.set_ylabel(label, fontsize=10)
        ax.grid(axis='y', alpha=0.15)

    axes[1].set_xlabel("Date")
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "01_timeline_launches.png"), dpi=150, bbox_inches='tight')
    plt.close()
    print("  Chart 1: Timeline with launches — SAVED")


def chart_2_content_type_engagement(reddit_df):
    """Chart 2: Which content types get the most engagement?"""
    if reddit_df is None or len(reddit_df) == 0:
        return

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    fig.suptitle("Content type analysis — what drives engagement?", fontsize=16, color=ACCENT, fontweight='bold')

    # Volume by type
    type_counts = reddit_df['anthropic_content_category'].value_counts()
    bars1 = axes[0].barh(type_counts.index, type_counts.values, color=ACCENT, alpha=0.7)
    axes[0].set_title("Volume (post count)", fontsize=12)
    axes[0].set_xlabel("Number of posts")
    for bar, val in zip(bars1, type_counts.values):
        axes[0].text(val + 1, bar.get_y() + bar.get_height()/2, str(val),
                     va='center', fontsize=9, color='white')

    # Avg engagement by type
    avg_engagement = reddit_df.groupby('anthropic_content_category')['upvotes'].mean().sort_values(ascending=True)
    colors = [ACCENT3 if v == avg_engagement.max() else ACCENT2 for v in avg_engagement.values]
    bars2 = axes[1].barh(avg_engagement.index, avg_engagement.values, color=colors, alpha=0.7)
    axes[1].set_title("Avg upvotes per post", fontsize=12)
    axes[1].set_xlabel("Average upvotes")
    for bar, val in zip(bars2, avg_engagement.values):
        axes[1].text(val + 1, bar.get_y() + bar.get_height()/2, f"{val:.0f}",
                     va='center', fontsize=9, color='white')

    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "02_content_type_engagement.png"), dpi=150, bbox_inches='tight')
    plt.close()
    print("  Chart 2: Content type engagement — SAVED")


def chart_3_feature_heatmap(reddit_df):
    """Chart 3: Which Claude features drive the most discussion?"""
    if reddit_df is None or len(reddit_df) == 0:
        return

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    fig.suptitle("Claude feature analysis — what are people talking about?", fontsize=16, color=ACCENT, fontweight='bold')

    feat_counts = reddit_df['features_mentioned'].value_counts()
    bars1 = axes[0].barh(feat_counts.index, feat_counts.values, color=ACCENT, alpha=0.7)
    axes[0].set_title("Mention volume", fontsize=12)
    for bar, val in zip(bars1, feat_counts.values):
        axes[0].text(val + 0.5, bar.get_y() + bar.get_height()/2, str(val),
                     va='center', fontsize=9, color='white')

    feat_eng = reddit_df.groupby('features_mentioned')['upvotes'].mean().sort_values(ascending=True)
    colors = [ACCENT3 if v == feat_eng.max() else '#00D4FF' for v in feat_eng.values]
    bars2 = axes[1].barh(feat_eng.index, feat_eng.values, color=colors, alpha=0.7)
    axes[1].set_title("Avg upvotes when mentioned", fontsize=12)
    for bar, val in zip(bars2, feat_eng.values):
        axes[1].text(val + 0.5, bar.get_y() + bar.get_height()/2, f"{val:.0f}",
                     va='center', fontsize=9, color='white')

    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "03_feature_analysis.png"), dpi=150, bbox_inches='tight')
    plt.close()
    print("  Chart 3: Feature analysis — SAVED")


def chart_4_youtube_creator_landscape(youtube_df):
    """Chart 4: YouTube creator analysis — who drives Claude's reach?"""
    if youtube_df is None or len(youtube_df) == 0:
        return

    fig, ax = plt.subplots(figsize=(14, 7))
    fig.suptitle("YouTube creator landscape — who amplifies Claude?", fontsize=16, color=ACCENT, fontweight='bold')

    # Top channels by total views
    channel_views = youtube_df.groupby('channel')['views'].sum().sort_values(ascending=False).head(15)
    channel_count = youtube_df.groupby('channel').size()

    bars = ax.barh(range(len(channel_views)), channel_views.values, color=ACCENT2, alpha=0.7)
    ax.set_yticks(range(len(channel_views)))
    ax.set_yticklabels(channel_views.index, fontsize=9)
    ax.set_xlabel("Total views across Claude videos")
    ax.invert_yaxis()

    for i, (bar, channel) in enumerate(zip(bars, channel_views.index)):
        count = channel_count.get(channel, 0)
        ax.text(bar.get_width() + channel_views.max() * 0.01, bar.get_y() + bar.get_height()/2,
                f"{bar.get_width():,.0f} views ({count} videos)",
                va='center', fontsize=8, color='white')

    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "04_youtube_creators.png"), dpi=150, bbox_inches='tight')
    plt.close()
    print("  Chart 4: YouTube creator landscape — SAVED")


def chart_5_cross_platform_comparison(reddit_df, youtube_df):
    """Chart 5: How content types differ across platforms — grouped bar chart."""
    if reddit_df is None or youtube_df is None:
        return

    # Unify categories across both platforms
    shared_types = ["Comparison", "Use Case", "Reaction", "News", "Tutorial", "Discussion", "Review", "Explainer"]

    reddit_pcts = {}
    yt_pcts = {}
    for ct in shared_types:
        reddit_pcts[ct] = (reddit_df['anthropic_content_category'] == ct).sum() / len(reddit_df) * 100
        yt_pcts[ct] = (youtube_df['anthropic_content_category'] == ct).sum() / len(youtube_df) * 100

    # Sort by Reddit percentage
    sorted_types = sorted(shared_types, key=lambda x: reddit_pcts[x])

    fig, ax = plt.subplots(figsize=(14, 7))
    fig.suptitle("Cross-platform content mix — Reddit vs YouTube", fontsize=16, color=ACCENT, fontweight='bold')

    y = range(len(sorted_types))
    height = 0.35
    reddit_vals = [reddit_pcts[t] for t in sorted_types]
    yt_vals = [yt_pcts[t] for t in sorted_types]

    bars1 = ax.barh([i + height/2 for i in y], reddit_vals, height, label='Reddit', color=ACCENT, alpha=0.7)
    bars2 = ax.barh([i - height/2 for i in y], yt_vals, height, label='YouTube', color=ACCENT2, alpha=0.7)

    ax.set_yticks(list(y))
    ax.set_yticklabels(sorted_types, fontsize=10)
    ax.set_xlabel("% of posts", fontsize=11)
    ax.legend(fontsize=11)
    ax.grid(axis='x', alpha=0.15)

    for bar, val in zip(bars1, reddit_vals):
        if val > 1:
            ax.text(val + 0.3, bar.get_y() + bar.get_height()/2, f"{val:.0f}%",
                    va='center', fontsize=8, color=ACCENT)
    for bar, val in zip(bars2, yt_vals):
        if val > 1:
            ax.text(val + 0.3, bar.get_y() + bar.get_height()/2, f"{val:.0f}%",
                    va='center', fontsize=8, color=ACCENT2)

    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "05_cross_platform.png"), dpi=150, bbox_inches='tight')
    plt.close()
    print("  Chart 5: Cross-platform comparison — SAVED")


def chart_6_engagement_vs_comments(reddit_df):
    """Chart 6: Scatter — upvotes vs comments, colored by content type."""
    if reddit_df is None or len(reddit_df) == 0:
        return

    fig, ax = plt.subplots(figsize=(12, 7))
    fig.suptitle("Engagement depth — upvotes vs discussion", fontsize=16, color=ACCENT, fontweight='bold')

    type_colors = {
        'Comparison': '#FF6B6B', 'Reaction': '#C8FF00', 'Use Case': '#00D4FF',
        'Tutorial': '#FFD93D', 'News': '#FF9F43', 'Discussion': '#A29BFE',
        'Complaint': '#FD79A8', 'Meme': '#FDCB6E', 'Question': '#74B9FF',
        'Feature Request': '#E17055', 'Other': '#636e72'
    }

    for ctype in reddit_df['anthropic_content_category'].unique():
        subset = reddit_df[reddit_df['anthropic_content_category'] == ctype]
        color = type_colors.get(ctype, '#636e72')
        ax.scatter(subset['upvotes'], subset['comments'], alpha=0.5, s=30,
                   color=color, label=ctype, edgecolors='none')

    ax.set_xlabel("Upvotes", fontsize=11)
    ax.set_ylabel("Comments", fontsize=11)
    ax.legend(loc='upper left', fontsize=8, framealpha=0.3)
    ax.grid(alpha=0.1)

    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "06_engagement_scatter.png"), dpi=150, bbox_inches='tight')
    plt.close()
    print("  Chart 6: Engagement scatter — SAVED")


def chart_7_launch_spike_analysis(reddit_df):
    """Chart 7: Quantify the spike after each product launch."""
    if reddit_df is None or len(reddit_df) == 0:
        return

    fig, ax = plt.subplots(figsize=(14, 6))
    fig.suptitle("Post-launch engagement spike analysis", fontsize=16, color=ACCENT, fontweight='bold')

    launch_spikes = []
    for date_str, name in LAUNCHES:
        launch = pd.Timestamp(date_str)
        before = reddit_df[(reddit_df['date'] >= launch - pd.Timedelta(days=7)) &
                           (reddit_df['date'] < launch)]
        after = reddit_df[(reddit_df['date'] >= launch) &
                          (reddit_df['date'] < launch + pd.Timedelta(days=7))]

        avg_before = before['upvotes'].mean() if len(before) > 0 else 0
        avg_after = after['upvotes'].mean() if len(after) > 0 else 0
        count_before = len(before)
        count_after = len(after)

        launch_spikes.append({
            'launch': name.replace('\n', ' '),
            'posts_before': count_before,
            'posts_after': count_after,
            'avg_upvotes_before': avg_before,
            'avg_upvotes_after': avg_after,
            'volume_multiplier': count_after / max(count_before, 1),
        })

    spike_df = pd.DataFrame(launch_spikes)
    if len(spike_df) == 0:
        return

    x = range(len(spike_df))
    width = 0.35
    ax.bar([i - width/2 for i in x], spike_df['posts_before'], width, label='Week before', color='#444', alpha=0.7)
    ax.bar([i + width/2 for i in x], spike_df['posts_after'], width, label='Week after', color=ACCENT, alpha=0.7)
    ax.set_xticks(list(x))
    ax.set_xticklabels(spike_df['launch'], rotation=30, ha='right', fontsize=9)
    ax.set_ylabel("Post count (7-day window)")
    ax.legend()

    for i, mult in enumerate(spike_df['volume_multiplier']):
        if mult > 0:
            ax.text(i, spike_df['posts_after'].iloc[i] + 0.5, f"{mult:.1f}x",
                    ha='center', fontsize=9, color=ACCENT, fontweight='bold')

    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "07_launch_spikes.png"), dpi=150, bbox_inches='tight')
    plt.close()
    print("  Chart 7: Launch spike analysis — SAVED")


def generate_summary_stats(reddit_df, youtube_df):
    """Generate summary statistics JSON for the README."""
    stats = {}

    if reddit_df is not None and len(reddit_df) > 0:
        stats["reddit"] = {
            "total_posts": len(reddit_df),
            "subreddits": reddit_df['subreddit'].nunique(),
            "date_range": f"{reddit_df['date'].min().strftime('%Y-%m-%d')} to {reddit_df['date'].max().strftime('%Y-%m-%d')}",
            "total_upvotes": int(reddit_df['upvotes'].sum()),
            "avg_upvotes": round(reddit_df['upvotes'].mean(), 1),
            "median_upvotes": round(reddit_df['upvotes'].median(), 1),
            "total_comments": int(reddit_df['comments'].sum()),
            "top_content_type": reddit_df['anthropic_content_category'].value_counts().index[0],
            "highest_engagement_type": reddit_df.groupby('anthropic_content_category')['upvotes'].mean().idxmax(),
            "top_feature": reddit_df['features_mentioned'].value_counts().index[0],
        }

    if youtube_df is not None and len(youtube_df) > 0:
        stats["youtube"] = {
            "total_videos": len(youtube_df),
            "unique_channels": youtube_df['channel'].nunique(),
            "date_range": f"{youtube_df['date'].min().strftime('%Y-%m-%d')} to {youtube_df['date'].max().strftime('%Y-%m-%d')}",
            "total_views": int(youtube_df['views'].sum()),
            "avg_views": round(youtube_df['views'].mean(), 1),
            "top_channel": youtube_df.groupby('channel')['views'].sum().idxmax(),
            "top_content_type": youtube_df['anthropic_content_category'].value_counts().index[0],
        }

    output_file = os.path.join(SCRIPT_DIR, "summary_stats.json")
    with open(output_file, "w") as f:
        json.dump(stats, f, indent=2)
    print(f"\n  Summary stats saved to {output_file}")
    return stats


def main():
    print("=" * 60)
    print("CLAUDE GROWTH — ANALYSIS ENGINE")
    print("=" * 60)

    reddit_df, youtube_df = load_data()

    if reddit_df is None and youtube_df is None:
        print("\nNo data found! Run scrapers first:")
        print("  python scrapers/reddit_scraper.py")
        print("  python scrapers/youtube_scraper.py YOUR_API_KEY")
        return

    print(f"\nGenerating charts...")
    chart_1_timeline_with_launches(reddit_df, youtube_df)
    chart_2_content_type_engagement(reddit_df)
    chart_3_feature_heatmap(reddit_df)
    chart_4_youtube_creator_landscape(youtube_df)
    chart_5_cross_platform_comparison(reddit_df, youtube_df)
    chart_6_engagement_vs_comments(reddit_df)
    chart_7_launch_spike_analysis(reddit_df)

    stats = generate_summary_stats(reddit_df, youtube_df)

    print(f"\n{'=' * 60}")
    print(f"ALL CHARTS SAVED to {OUTPUT_DIR}")
    print(f"{'=' * 60}")

    if "reddit" in stats:
        r = stats["reddit"]
        print(f"\nKEY FINDINGS (use these in your playbook):")
        print(f"  Reddit: {r['total_posts']} posts, avg {r['avg_upvotes']} upvotes")
        print(f"  Most common content: {r['top_content_type']}")
        print(f"  Highest engagement content: {r['highest_engagement_type']}")
        print(f"  Most discussed feature: {r['top_feature']}")

    if "youtube" in stats:
        y = stats["youtube"]
        print(f"  YouTube: {y['total_videos']} videos, {y['total_views']:,} total views")
        print(f"  Top channel: {y['top_channel']}")


if __name__ == "__main__":
    main()
