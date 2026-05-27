#!/usr/bin/env python3
"""
FitDrop / Dread Files — Pivot Tracker
Log video performance manually and get data-driven pivot recommendations.

Usage:
    python pivot_tracker.py                          # interactive menu
    python pivot_tracker.py log tiktok               # log a TikTok video
    python pivot_tracker.py log youtube              # log a YouTube video
    python pivot_tracker.py report tiktok            # generate TikTok report
    python pivot_tracker.py report youtube           # generate YouTube report
    python pivot_tracker.py report both              # generate both reports

Data is stored in output/analytics/tiktok_log.csv and output/analytics/youtube_log.csv
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean

# ── Config ────────────────────────────────────────────────────────────────────

CONFIG_PATH = Path(__file__).parent.parent / "config" / "channels.json"
ANALYTICS_DIR = Path(__file__).parent.parent / "output" / "analytics"

TIKTOK_LOG = ANALYTICS_DIR / "tiktok_log.csv"
YOUTUBE_LOG = ANALYTICS_DIR / "youtube_log.csv"

TIKTOK_FIELDS = ["date", "video_id", "title", "views", "likes", "saves", "shares", "shop_clicks", "sales"]
YOUTUBE_FIELDS = ["date", "video_id", "title", "views", "watch_time_minutes", "avg_view_duration_pct", "likes", "subs_gained", "ctr_pct"]

def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text())

def ensure_dirs() -> None:
    ANALYTICS_DIR.mkdir(parents=True, exist_ok=True)

# ── CSV helpers ───────────────────────────────────────────────────────────────

def init_csv(path: Path, fields: list[str]) -> None:
    if not path.exists():
        with open(path, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=fields).writeheader()

def append_row(path: Path, fields: list[str], row: dict) -> None:
    with open(path, "a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=fields).writerow(row)

def read_rows(path: Path, fields: list[str]) -> list[dict]:
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f, fieldnames=fields))

# ── Input helpers ─────────────────────────────────────────────────────────────

def prompt_int(label: str, default: int = 0) -> int:
    val = input(f"  {label} [{default}]: ").strip()
    return int(val) if val.isdigit() else default

def prompt_float(label: str, default: float = 0.0) -> float:
    val = input(f"  {label} [{default}]: ").strip()
    try:
        return float(val)
    except ValueError:
        return default

def prompt_str(label: str, default: str = "") -> str:
    val = input(f"  {label} [{default}]: ").strip()
    return val if val else default

# ── Logging ───────────────────────────────────────────────────────────────────

def log_tiktok() -> None:
    ensure_dirs()
    init_csv(TIKTOK_LOG, TIKTOK_FIELDS)
    print("\n── Log TikTok Video ──────────────────────")
    row = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "video_id": prompt_str("Video ID or URL snippet"),
        "title": prompt_str("Video title/description"),
        "views": prompt_int("Views"),
        "likes": prompt_int("Likes"),
        "saves": prompt_int("Saves (important — saves > likes in 2026 algo)"),
        "shares": prompt_int("Shares"),
        "shop_clicks": prompt_int("Shop link clicks (from TikTok analytics)"),
        "sales": prompt_int("Confirmed sales (from TikTok Shop dashboard)"),
    }
    append_row(TIKTOK_LOG, TIKTOK_FIELDS, row)
    print(f"✓ Logged: {row['title'][:40]}")


def log_youtube() -> None:
    ensure_dirs()
    init_csv(YOUTUBE_LOG, YOUTUBE_FIELDS)
    print("\n── Log YouTube Video ─────────────────────")
    row = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "video_id": prompt_str("Video ID (from YouTube URL)"),
        "title": prompt_str("Video title"),
        "views": prompt_int("Views (check after 48 hours)"),
        "watch_time_minutes": prompt_int("Total watch time (minutes, from YouTube Studio)"),
        "avg_view_duration_pct": prompt_float("Avg view duration % (e.g. 52.3)"),
        "likes": prompt_int("Likes"),
        "subs_gained": prompt_int("Subscribers gained from this video"),
        "ctr_pct": prompt_float("Click-through rate % (from YouTube Studio)"),
    }
    append_row(YOUTUBE_LOG, YOUTUBE_FIELDS, row)
    print(f"✓ Logged: {row['title'][:40]}")

# ── Reports ───────────────────────────────────────────────────────────────────

def report_tiktok(config: dict) -> str:
    rows = read_rows(TIKTOK_LOG, TIKTOK_FIELDS)[1:]  # skip header
    if not rows:
        return "No TikTok data logged yet. Run: python pivot_tracker.py log tiktok"

    threshold = config["tiktok"]["pivot_threshold"]
    min_views = threshold["min_avg_views_per_video"]
    min_ctr = threshold["min_shop_ctr_percent"]
    eval_after = threshold["evaluation_after_n_posts"]

    views = [int(r["views"]) for r in rows if r["views"].isdigit()]
    saves = [int(r["saves"]) for r in rows if r["saves"].isdigit()]
    shop_clicks = [int(r["shop_clicks"]) for r in rows if r["shop_clicks"].isdigit()]
    sales = [int(r["sales"]) for r in rows if r["sales"].isdigit()]

    avg_views = mean(views) if views else 0
    avg_saves = mean(saves) if saves else 0
    total_clicks = sum(shop_clicks)
    total_sales = sum(sales)
    shop_ctr = (total_clicks / sum(views) * 100) if sum(views) > 0 else 0

    # 7-day rolling trend
    recent = rows[-7:] if len(rows) >= 7 else rows
    recent_views = [int(r["views"]) for r in recent if r["views"].isdigit()]
    trend_avg = mean(recent_views) if recent_views else 0
    trend_dir = "↑ Improving" if trend_avg >= avg_views else "↓ Declining"

    status = "CONTINUE" if avg_views >= min_views and shop_ctr >= min_ctr else "REVIEW"
    if len(rows) >= eval_after and status == "REVIEW":
        status = "⚠ PIVOT RECOMMENDED"

    lines = [
        "═══════════════════════════════════════════",
        "  TIKTOK PIVOT REPORT — FitDrop",
        f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "═══════════════════════════════════════════",
        f"  Videos logged:       {len(rows)}",
        f"  Avg views/video:     {avg_views:.0f}  (threshold: ≥ {min_views})",
        f"  Avg saves/video:     {avg_saves:.0f}",
        f"  Shop link CTR:       {shop_ctr:.1f}%  (threshold: ≥ {min_ctr}%)",
        f"  Total shop clicks:   {total_clicks}",
        f"  Total sales:         {total_sales}",
        f"  7-day view trend:    {trend_avg:.0f} avg  ({trend_dir})",
        "───────────────────────────────────────────",
        f"  STATUS:              {status}",
        "───────────────────────────────────────────",
    ]

    if status == "CONTINUE":
        lines += [
            "  ✓ Metrics above threshold. Keep posting.",
            "  Focus: increase saves — add 'save this for later' in captions.",
        ]
    elif "PIVOT" in status:
        lines += [
            "  ✗ Below threshold after evaluation period.",
            "  Recommended pivot options:",
            "    1. New product category (e.g., accessories, activewear, shoes)",
            "    2. New hook angle (try transformation or size-inclusive content)",
            "    3. New posting time — try 12pm and 7pm if you've been posting mornings",
            "    4. If no improvement after 10 more posts → full niche pivot",
        ]
    else:
        remaining = max(0, eval_after - len(rows))
        lines += [
            f"  ⚡ {remaining} more videos before full pivot evaluation.",
            "  Focus on improving hooks — first 2 seconds are critical.",
        ]
    lines.append("═══════════════════════════════════════════")
    return "\n".join(lines)


def report_youtube(config: dict) -> str:
    rows = read_rows(YOUTUBE_LOG, YOUTUBE_FIELDS)[1:]
    if not rows:
        return "No YouTube data logged yet. Run: python pivot_tracker.py log youtube"

    threshold = config["youtube"]["pivot_threshold"]
    min_views = threshold["min_avg_views_per_video"]
    min_subs = threshold["min_subs_per_month"]
    eval_after = threshold["evaluation_after_n_videos"]
    ctr_target = config["youtube"]["ctr_benchmark_percent"]
    avd_target = config["youtube"]["avg_view_duration_target_percent"]

    views = [int(r["views"]) for r in rows if r["views"].isdigit()]
    ctrs = [float(r["ctr_pct"]) for r in rows if r["ctr_pct"].replace(".", "").isdigit()]
    avds = [float(r["avg_view_duration_pct"]) for r in rows if r["avg_view_duration_pct"].replace(".", "").isdigit()]
    subs = [int(r["subs_gained"]) for r in rows if r["subs_gained"].isdigit()]

    avg_views = mean(views) if views else 0
    avg_ctr = mean(ctrs) if ctrs else 0
    avg_avd = mean(avds) if avds else 0
    total_subs = sum(subs)
    subs_per_month = total_subs  # rough if all within 30 days

    recent = rows[-7:] if len(rows) >= 7 else rows
    recent_views = [int(r["views"]) for r in recent if r["views"].isdigit()]
    trend_avg = mean(recent_views) if recent_views else 0
    trend_dir = "↑ Improving" if trend_avg >= avg_views else "↓ Declining"

    status = "CONTINUE"
    if avg_views < min_views or subs_per_month < min_subs:
        status = "REVIEW"
    if len(rows) >= eval_after and status == "REVIEW":
        status = "⚠ PIVOT RECOMMENDED"

    lines = [
        "═══════════════════════════════════════════",
        "  YOUTUBE PIVOT REPORT — Dread Files",
        f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "═══════════════════════════════════════════",
        f"  Videos logged:       {len(rows)}",
        f"  Avg views/video:     {avg_views:.0f}  (threshold: ≥ {min_views})",
        f"  Avg CTR:             {avg_ctr:.1f}%  (target: ≥ {ctr_target}%)",
        f"  Avg view duration:   {avg_avd:.1f}%  (target: ≥ {avd_target}%)",
        f"  Total subs gained:   {total_subs}  (monthly target: ≥ {min_subs})",
        f"  7-day view trend:    {trend_avg:.0f} avg  ({trend_dir})",
        "───────────────────────────────────────────",
        f"  STATUS:              {status}",
        "───────────────────────────────────────────",
    ]

    if status == "CONTINUE":
        if avg_ctr < ctr_target:
            lines.append("  ⚡ CTR below target — A/B test thumbnails. Try adding a face or text overlay.")
        if avg_avd < avd_target:
            lines.append("  ⚡ AVD below target — tighten Act 2. Cut slow exposition beats.")
        lines.append("  ✓ Overall: keep posting. Consistency is the growth driver at this stage.")
    elif "PIVOT" in status:
        lines += [
            "  ✗ Below threshold after evaluation period.",
            "  Recommended next steps:",
            "    1. A/B test 5 new thumbnail styles before full pivot",
            "    2. Analyze top 3 performing videos — find the common hook pattern",
            "    3. Consider sub-niche: 'real paranormal events' vs 'fictional horror'",
            "    4. If no change after 2 more weeks → pivot to adjacent niche",
            "       (e.g., true crime, unsolved mysteries, ghost towns)",
        ]
    else:
        remaining = max(0, eval_after - len(rows))
        lines.append(f"  ⚡ {remaining} more videos before full pivot evaluation.")

    lines.append("═══════════════════════════════════════════")
    return "\n".join(lines)

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Pivot tracker for TikTok and YouTube channels")
    parser.add_argument("action", nargs="?", choices=["log", "report"], help="Action to take")
    parser.add_argument("platform", nargs="?", choices=["tiktok", "youtube", "both"], help="Platform")
    args = parser.parse_args()

    config = load_config()

    if not args.action:
        print("\nPivot Tracker — FitDrop / Dread Files")
        print("1. Log TikTok video")
        print("2. Log YouTube video")
        print("3. TikTok report")
        print("4. YouTube report")
        print("5. Both reports")
        choice = input("\nChoice [1-5]: ").strip()
        action_map = {"1": ("log", "tiktok"), "2": ("log", "youtube"),
                      "3": ("report", "tiktok"), "4": ("report", "youtube"), "5": ("report", "both")}
        if choice not in action_map:
            sys.exit("Invalid choice.")
        args.action, args.platform = action_map[choice]

    if args.action == "log":
        if args.platform == "tiktok":
            log_tiktok()
        elif args.platform == "youtube":
            log_youtube()

    elif args.action == "report":
        report_dir = ANALYTICS_DIR
        report_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")

        if args.platform in ("tiktok", "both"):
            report = report_tiktok(config)
            print("\n" + report)
            report_path = report_dir / f"tiktok_report_{timestamp}.txt"
            report_path.write_text(report, encoding="utf-8")
            print(f"\nReport saved: {report_path}")

        if args.platform in ("youtube", "both"):
            report = report_youtube(config)
            print("\n" + report)
            report_path = report_dir / f"youtube_report_{timestamp}.txt"
            report_path.write_text(report, encoding="utf-8")
            print(f"\nReport saved: {report_path}")


if __name__ == "__main__":
    main()
