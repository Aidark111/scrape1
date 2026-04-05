"""
Anomaly detection — monitors enriched data for growth-relevant signals.
Computes z-scores on rolling windows to detect spikes, crashes, and breakouts.

Reads from: stage1/output/clean/
Outputs: alerts list (returned as dicts, consumed by machine.py)
"""
import os
import pandas as pd
from datetime import datetime, timedelta

LAB_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STAGE1_DIR = os.path.join(LAB_DIR, "stage1")
CLEAN_DIR = os.path.join(STAGE1_DIR, "output", "clean")


def build_alert(signal, platform, priority, message, **kwargs):
    """Create a consistent alert payload for file, console, and Slack delivery."""
    alert = {
        "signal": signal,
        "platform": platform,
        "priority": priority,
        "message": message,
    }
    alert.update(kwargs)
    return alert


def load_enriched(platform):
    path = os.path.join(CLEAN_DIR, f"{platform}_enriched.csv")
    print(f"Loading enriched data for {platform} from {path}...")
    if not os.path.exists(path):
        print(f"  Missing data file for {platform}, skipping anomaly checks.")
        return None
    df = pd.read_csv(path, encoding="utf-8")
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df.dropna(subset=["date"])


def detect_volume_spike(df, platform, window_weeks=4, threshold=3.0):
    """Alert if recent 24h post volume exceeds 3x the rolling average."""
    daily = df.set_index("date").resample("D").size()
    if len(daily) < window_weeks * 7:
        return None

    rolling_mean = daily.rolling(window=window_weeks * 7).mean()
    rolling_std = daily.rolling(window=window_weeks * 7).std()

    latest = daily.iloc[-1]
    mean = rolling_mean.iloc[-2] if len(rolling_mean) > 1 else 0
    std = rolling_std.iloc[-2] if len(rolling_std) > 1 else 1

    if std == 0 or pd.isna(std):
        return None

    z = (latest - mean) / std
    if z >= threshold:
        latest_day = daily.index[-1]
        return build_alert(
            signal="volume_spike",
            platform=platform,
            priority="HIGH",
            message=(
                f"{platform} volume spike: {int(latest)} posts on {latest_day.date()} "
                f"vs {mean:.1f} baseline (z={z:.2f}, threshold={threshold:.1f})"
            ),
            value=int(latest),
            baseline=round(mean, 1),
            z_score=round(z, 2),
            threshold=threshold,
            window_weeks=window_weeks,
            window_days=window_weeks * 7,
            event_date=latest_day.isoformat(),
        )
    return None


def detect_sentiment_crash(df, platform, window_weeks=4, drop_threshold=0.3):
    """Alert if weekly sentiment drops > 0.3 from rolling average."""
    if "sentiment_compound" not in df.columns:
        return None

    weekly = df.set_index("date").resample("W")["sentiment_compound"].mean()
    if len(weekly) < window_weeks + 1:
        return None

    rolling_mean = weekly.rolling(window=window_weeks).mean()
    latest = weekly.iloc[-1]
    baseline = rolling_mean.iloc[-2] if len(rolling_mean) > 1 else 0

    if pd.isna(latest) or pd.isna(baseline):
        return None

    drop = baseline - latest
    if drop >= drop_threshold:
        latest_week = weekly.index[-1]
        return build_alert(
            signal="sentiment_crash",
            platform=platform,
            priority="HIGH",
            message=(
                f"{platform} sentiment crash: weekly sentiment {latest:.3f} vs {baseline:.3f} "
                f"baseline (drop={drop:.3f}, threshold={drop_threshold:.3f})"
            ),
            value=round(latest, 3),
            baseline=round(baseline, 3),
            drop=round(drop, 3),
            threshold=drop_threshold,
            window_weeks=window_weeks,
            week_ending=latest_week.isoformat(),
        )
    return None


def detect_viral_breakout(df, platform, upvote_threshold=1000):
    """Alert if any post in the last 24h exceeds the upvote threshold."""
    engagement_col = "upvotes" if "upvotes" in df.columns else "likes"
    if engagement_col not in df.columns:
        return None

    cutoff = datetime.now() - timedelta(days=1)
    recent = df[df["date"] >= cutoff]
    if len(recent) == 0:
        return None

    top = recent.nlargest(1, engagement_col).iloc[0]
    if top[engagement_col] >= upvote_threshold:
        title = str(top.get("title", top.get("title_clean", "")))[:100]
        url = str(top.get("url", ""))
        post_id = str(top.get("post_id", top.get("video_id", "")))
        return build_alert(
            signal="viral_breakout",
            platform=platform,
            priority="MEDIUM",
            message=(
                f"{platform} viral breakout: {int(top[engagement_col])} {engagement_col} "
                f"(threshold={upvote_threshold}) — \"{title}\""
            ),
            value=int(top[engagement_col]),
            threshold=upvote_threshold,
            title=title,
            metric=engagement_col,
            post_id=post_id,
            url=url,
            post_date=pd.to_datetime(top.get("date")).isoformat() if pd.notna(top.get("date")) else None,
            lookback_hours=24,
        )
    return None


def detect_new_creator(df, platform, min_subscribers=100_000):
    """Alert if a YouTube channel with >100K subs posted its first Claude video."""
    if platform != "youtube" or "channel_subscribers" not in df.columns:
        return None

    df_sorted = df.sort_values("date")
    channel_first = df_sorted.groupby("channel").agg(
        first_date=("date", "min"),
        subs=("channel_subscribers", "max"),
    )

    cutoff = datetime.now() - timedelta(days=7)
    new_big = channel_first[
        (channel_first["first_date"] >= cutoff) &
        (channel_first["subs"] >= min_subscribers)
    ]

    if len(new_big) > 0:
        ch = new_big.index[0]
        subs = int(new_big.iloc[0]["subs"])
        first_date = pd.to_datetime(new_big.iloc[0]["first_date"])
        return build_alert(
            signal="new_creator",
            platform=platform,
            priority="MEDIUM",
            message=(
                f"New creator entry: {ch} ({subs:,} subscribers) posted first Claude video "
                f"on {first_date.date()}"
            ),
            channel=ch,
            subscribers=subs,
            threshold=min_subscribers,
            first_date=first_date.isoformat(),
            lookback_days=7,
        )
    return None


def detect_competitor_surge(df, platform, window_weeks=4, multiplier=2.0):
    """Alert if competitor mentions spike 2x week-over-week."""
    if "mentions_competitor" not in df.columns:
        return None

    weekly_comp = df.set_index("date").resample("W")["mentions_competitor"].sum()
    if len(weekly_comp) < 2:
        return None

    current = weekly_comp.iloc[-1]
    previous = weekly_comp.iloc[-2]

    if previous > 0 and current / previous >= multiplier:
        week_ending = weekly_comp.index[-1]
        ratio = current / previous
        return build_alert(
            signal="competitor_surge",
            platform=platform,
            priority="LOW",
            message=(
                f"{platform} competitor surge: {int(current)} mentions this week vs "
                f"{int(previous)} last week ({ratio:.1f}x, threshold={multiplier:.1f}x)"
            ),
            current_week=int(current),
            previous_week=int(previous),
            ratio=round(ratio, 1),
            threshold=multiplier,
            week_ending=week_ending.isoformat(),
        )
    return None


def run_all_checks():
    """Run all anomaly checks across all platforms. Returns list of alert dicts."""
    alerts = []
    detected_at = datetime.now().isoformat()

    for platform in ["reddit", "youtube"]:
        df = load_enriched(platform)
        if df is None:
            continue
        print(f"Loaded {len(df)} enriched posts for {platform}.")
        checks = [
            detect_volume_spike(df, platform),
            detect_sentiment_crash(df, platform),
            detect_viral_breakout(df, platform),
            detect_new_creator(df, platform),
            detect_competitor_surge(df, platform),
        ]

        for alert in checks:
            if alert is not None:
                alert["detected_at"] = detected_at
                alert["dataset_rows"] = int(len(df))
                alerts.append(alert)

    return alerts


if __name__ == "__main__":
    print("=" * 60)
    print("ANOMALY DETECTION")
    print("=" * 60)

    alerts = run_all_checks()

    if not alerts:
        print("\n  No anomalies detected. All signals normal.")
    else:
        print(f"\n  {len(alerts)} alert(s) detected:\n")
        for a in alerts:
            icon = {"HIGH": "!!!", "MEDIUM": " ! ", "LOW": " . "}
            print(f"  [{icon.get(a['priority'], '   ')}] {a['message']}")
