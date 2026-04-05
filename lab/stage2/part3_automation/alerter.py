"""
Alert delivery — sends anomaly alerts to console, file log, and optionally Slack.

Usage:
  Called by machine.py after anomaly detection.
  Slack webhook is optional — set SLACK_WEBHOOK_URL in .env to enable.
"""
import os
import json
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

LAB_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALERT_LOG = os.path.join(LAB_DIR, "stage2", "part3_automation", "alert_log.jsonl")


def log_to_file(alerts):
    """Append alerts to JSONL log file (one JSON object per line)."""
    with open(ALERT_LOG, "a", encoding="utf-8") as f:
        for alert in alerts:
            f.write(json.dumps(alert, ensure_ascii=False) + "\n")
    print(f"  Logged {len(alerts)} alerts to {ALERT_LOG}")


def print_to_console(alerts):
    """Print formatted alerts to console."""
    icons = {"HIGH": "!!!", "MEDIUM": " ! ", "LOW": " . "}
    colors = {"HIGH": "\033[91m", "MEDIUM": "\033[93m", "LOW": "\033[90m"}
    reset = "\033[0m"

    print(f"\n  {'=' * 50}")
    print(f"  ALERTS — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  {'=' * 50}")

    for a in sorted(alerts, key=lambda x: {"HIGH": 0, "MEDIUM": 1, "LOW": 2}.get(x.get("priority"), 3)):
        p = a.get("priority", "LOW")
        print(f"  {colors.get(p, '')}{icons.get(p, '   ')} [{p}] {a['message']}{reset}")

    print()


def send_to_slack(alerts):
    """Send alerts to Slack via webhook. Requires SLACK_WEBHOOK_URL in .env."""
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    if not webhook_url:
        return False

    # Group by priority
    high = [a for a in alerts if a.get("priority") == "HIGH"]
    medium = [a for a in alerts if a.get("priority") == "MEDIUM"]
    low = [a for a in alerts if a.get("priority") == "LOW"]

    lines = [f"*Growth Intelligence Alert* — {datetime.now().strftime('%Y-%m-%d %H:%M')}"]

    if high:
        lines.append("\n:red_circle: *HIGH PRIORITY*")
        for a in high:
            lines.append(f"• {a['message']}")
    if medium:
        lines.append("\n:large_yellow_circle: *MEDIUM*")
        for a in medium:
            lines.append(f"• {a['message']}")
    if low:
        lines.append("\n:white_circle: *LOW*")
        for a in low:
            lines.append(f"• {a['message']}")

    payload = {"text": "\n".join(lines)}

    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        if resp.status_code == 200:
            print(f"  Slack alert sent ({len(alerts)} alerts)")
            return True
        else:
            print(f"  Slack webhook returned {resp.status_code}")
            return False
    except Exception as e:
        print(f"  Slack webhook failed: {e}")
        return False


def deliver_alerts(alerts):
    """Deliver alerts through all configured channels."""
    if not alerts:
        print("  No alerts to deliver.")
        return

    print_to_console(alerts)
    log_to_file(alerts)

    if os.getenv("SLACK_WEBHOOK_URL"):
        send_to_slack(alerts)
    else:
        print("  Slack not configured (set SLACK_WEBHOOK_URL in .env to enable)")
