"""
==============================================================
  TREND BOT v3 — NEWS SCANNER
  Parallel RSS scanning with AI-powered scoring
==============================================================
"""

import logging
import hashlib
import threading
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from colorama import Fore, init

import feedparser

from config.settings import (
    RSS_FEEDS, HIGH_VALUE_KEYWORDS, LOW_VALUE_KEYWORDS,
    MIN_SCORE_TO_ALERT, MAX_STORY_AGE_MINUTES,
    ACTIVE_HOURS_START_UTC, ACTIVE_HOURS_END_UTC,
)
from scanner.ai_scorer import score_and_generate_card, ANTHROPIC_API_KEY

init(autoreset=True)
logging.basicConfig(
    filename="logs/scanner.log",
    level=logging.INFO,
    format="%(asctime)s - %(message)s",
)

# Track seen stories to avoid duplicates (thread-safe)
_seen_ids = set()
_seen_ids_lock = threading.Lock()

# Track feed health
_feed_health = {}  # feed_name -> {"ok": int, "fail": int, "last_error": str}
_feed_health_lock = threading.Lock()


def is_active_hours():
    """Check if we're in active trading hours."""
    hour = datetime.now(timezone.utc).hour
    return ACTIVE_HOURS_START_UTC <= hour < ACTIVE_HOURS_END_UTC


def _parse_pub_time(entry):
    """Extract publication datetime from RSS entry."""
    for field in ["published_parsed", "updated_parsed", "created_parsed"]:
        t = getattr(entry, field, None)
        if t:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    return None


def _is_fresh(entry):
    """Check if story is recent enough."""
    pub = _parse_pub_time(entry)
    if pub is None:
        return True  # Assume fresh if unknown
    return (datetime.now(timezone.utc) - pub) < timedelta(minutes=MAX_STORY_AGE_MINUTES)


def _story_id(entry):
    """Generate a unique ID for a story."""
    raw = getattr(entry, "id", None) or getattr(entry, "link", None) or getattr(entry, "title", "")
    return hashlib.md5(raw.encode()).hexdigest()


def score_story_fallback(title, summary=""):
    """
    Keyword-based scoring fallback (used when AI is unavailable).
    Returns (score, keywords).
    """
    text = (title + " " + summary).lower()
    score = 10
    matched = []

    for kw in HIGH_VALUE_KEYWORDS:
        if kw.lower() in text:
            score += 10
            matched.append(kw)

    for kw in LOW_VALUE_KEYWORDS:
        if kw.lower() in text:
            score -= 15

    if "!" in title or "?" in title:
        score += 5
    if len(title.split()) < 8:
        score += 5

    return max(0, min(100, score)), matched


def _scan_single_feed(feed_name, feed_url):
    """Scan one RSS feed. Returns list of raw story dicts."""
    stories = []
    try:
        feed = feedparser.parse(feed_url, request_headers={
            "User-Agent": "TrendBot/3.0 (RSS Reader)"
        })

        if feed.bozo and not feed.entries:
            with _feed_health_lock:
                _feed_health.setdefault(feed_name, {"ok": 0, "fail": 0, "last_error": ""})
                _feed_health[feed_name]["fail"] += 1
                _feed_health[feed_name]["last_error"] = str(feed.bozo_exception)[:100]
            return stories

        with _feed_health_lock:
            _feed_health.setdefault(feed_name, {"ok": 0, "fail": 0, "last_error": ""})
            _feed_health[feed_name]["ok"] += 1

        for entry in feed.entries:
            sid = _story_id(entry)
            with _seen_ids_lock:
                if sid in _seen_ids:
                    continue
                _seen_ids.add(sid)
            if not _is_fresh(entry):
                continue

            title = getattr(entry, "title", "").strip()
            if not title:
                continue

            summary = getattr(entry, "summary", "").strip()
            link = getattr(entry, "link", "")
            pub_time = _parse_pub_time(entry)

            stories.append({
                "id": sid,
                "source": feed_name,
                "title": title,
                "summary": summary[:300],
                "link": link,
                "pub_time": pub_time,
                "published": pub_time.strftime("%Y-%m-%d %H:%M UTC") if pub_time else "Unknown",
            })

    except Exception as e:
        logging.error(f"Error scanning {feed_name}: {e}")

    return stories


def run_scan():
    """
    Scan all RSS feeds IN PARALLEL, then score with AI.
    Returns list of high-scoring story dicts, sorted by score.
    """
    print(Fore.CYAN + f"\n🔍 Scanning {len(RSS_FEEDS)} feeds... ({datetime.now().strftime('%H:%M:%S')})")

    # --- Phase 1: Parallel RSS fetch ---
    all_stories = []
    with ThreadPoolExecutor(max_workers=20) as pool:
        futures = {
            pool.submit(_scan_single_feed, name, url): name
            for name, url in RSS_FEEDS
        }
        for future in as_completed(futures):
            try:
                all_stories.extend(future.result())
            except Exception as e:
                logging.error(f"Feed thread error: {e}")

    print(Fore.CYAN + f"   Fetched {len(all_stories)} new stories from feeds")

    if not all_stories:
        return []

    # --- Phase 2: Score stories + generate full token card ---
    use_ai = bool(ANTHROPIC_API_KEY)
    if use_ai:
        print(Fore.CYAN + "   🤖 AI scoring + card generation (Claude Haiku)")
    else:
        print(Fore.YELLOW + "   ⚠️  No AI key — keyword fallback scoring")

    scored = []
    ai_count = 0
    for story in all_stories:
        if use_ai:
            card = score_and_generate_card(story["title"], story["summary"], story["source"])
            if card:
                story["score"] = card["score"]
                story["keywords"] = card.get("keywords", [])
                story["ai_reason"] = card.get("reasoning", "")
                story["ai_name"] = card.get("name", "")
                story["ai_ticker"] = card.get("ticker", "")
                story["ai_description"] = card.get("description", "")
                story["ai_visual"] = card.get("visual", "")
                story["scoring_method"] = "ai"
                ai_count += 1
            else:
                score, kws = score_story_fallback(story["title"], story["summary"])
                story["score"] = score
                story["keywords"] = kws
                story["scoring_method"] = "fallback"
        else:
            score, kws = score_story_fallback(story["title"], story["summary"])
            story["score"] = score
            story["keywords"] = kws
            story["scoring_method"] = "fallback"

        scored.append(story)

    if ai_count:
        print(Fore.CYAN + f"   🤖 AI generated {ai_count} token cards")

    # Sort by score descending
    scored.sort(key=lambda x: x["score"], reverse=True)

    # Filter above threshold
    alerts = [s for s in scored if s["score"] >= MIN_SCORE_TO_ALERT]

    print(Fore.CYAN + f"   {len(alerts)} stories above threshold (score ≥ {MIN_SCORE_TO_ALERT})")
    logging.info(f"Scan: {len(all_stories)} stories, {len(alerts)} alerts")

    return alerts


def print_story_summary(stories, limit=5):
    """Print top stories to terminal."""
    n = min(limit, len(stories))
    print(Fore.WHITE + f"\n📊 Top {n} stories:")
    for i, s in enumerate(stories[:n]):
        color = Fore.GREEN if s["score"] >= 70 else Fore.YELLOW if s["score"] >= 45 else Fore.RED
        method = "🤖" if s.get("scoring_method") == "ai" else "📝"
        print(color + f"  {i+1}. [{s['score']:3d}] {method} {s['title'][:70]}")
        if s.get("ai_name"):
            print(Fore.WHITE + f"       → Token: {s['ai_name']} (${s.get('ai_ticker', '?')})")
        print(Fore.WHITE + f"       Source: {s['source']}")


def format_alert(story):
    """Format a story as terminal alert."""
    score = story["score"]
    color = Fore.GREEN if score >= 70 else Fore.YELLOW if score >= 45 else Fore.RED
    lines = [
        "",
        color + "=" * 60,
        color + f"  🔥 TREND ALERT — Score: {score}/100",
        color + "=" * 60,
        f"  📰 Source:    {story['source']}",
        f"  📌 Title:     {story['title']}",
        f"  🏷️  Keywords:  {', '.join(story.get('keywords', []))}",
    ]
    if story.get("ai_reason"):
        lines.append(f"  🤖 AI says:   {story['ai_reason']}")
    if story.get("ai_name"):
        lines.append(f"  🎯 Token:     {story['ai_name']} (${story.get('ai_ticker', '?')})")
    lines += [
        f"  🕐 Published: {story['published']}",
        f"  🔗 Link:      {story['link']}",
        color + "=" * 60,
    ]
    return "\n".join(lines)


def get_feed_health_report():
    """Return feed health stats for diagnostics."""
    report = []
    for name, stats in sorted(_feed_health.items()):
        total = stats["ok"] + stats["fail"]
        rate = (stats["ok"] / total * 100) if total > 0 else 0
        if rate < 50:
            report.append(f"  ⚠️  {name}: {rate:.0f}% success ({stats['last_error'][:50]})")
    return report


def check_feed_health():
    """Print feed health report to terminal."""
    report = get_feed_health_report()
    if report:
        print(Fore.YELLOW + "\n  📡 Feed Health Issues:")
        for line in report:
            print(Fore.YELLOW + line)
    else:
        print(Fore.GREEN + "\n  📡 All feeds healthy ✅")
    return report
