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
    MIN_SCORE_TO_ALERT, TOP_STORIES_PER_WAVE, MAX_STORY_AGE_MINUTES,
    ACTIVE_HOURS_START_UTC, ACTIVE_HOURS_END_UTC,
    BLOCKED_TOPIC_KEYWORDS,
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
    """Check if story is within the 12-hour window. Rejects articles with no timestamp."""
    pub = _parse_pub_time(entry)
    if pub is None:
        return False  # No timestamp = could be very old, skip it
    return (datetime.now(timezone.utc) - pub) < timedelta(minutes=MAX_STORY_AGE_MINUTES)


def _is_blocked_topic(title, summary=""):
    """Return True if the story matches a blocked/sensitive topic."""
    text = (title + " " + summary).lower()
    for kw in BLOCKED_TOPIC_KEYWORDS:
        if kw.lower() in text:
            return True, kw
    return False, None


def _story_id(entry):
    """Generate a unique ID for a story."""
    raw = getattr(entry, "id", None) or getattr(entry, "link", None) or getattr(entry, "title", "")
    return hashlib.md5(raw.encode()).hexdigest()


_SKIP_WORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to",
    "for", "of", "with", "by", "from", "is", "are", "was", "were",
    "will", "be", "been", "have", "has", "had", "do", "does", "did",
    "not", "that", "this", "it", "he", "she", "they", "we", "you",
    "says", "said", "new", "after", "over", "about", "into", "could",
}


def _generate_fallback_name(title):
    """Generate a basic token name + ticker from headline words."""
    words = title.split()
    interesting = [
        w.strip(".,!?\"'()[]{}:")
        for w in words
        if w.lower().strip(".,!?\"'()[]{}:") not in _SKIP_WORDS and len(w) > 2
    ]
    if not interesting:
        interesting = [w for w in words[:3]]

    ticker = interesting[0][:6].upper() if interesting else "TREND"
    name = " ".join(w.capitalize() for w in interesting[:3])
    return name, ticker


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

    # --- Phase 2: Pre-filter with keywords, then AI-score only promising stories ---
    use_ai = bool(ANTHROPIC_API_KEY)
    if use_ai:
        print(Fore.CYAN + "   🤖 AI scoring (keyword pre-filter to save costs)")
    else:
        print(Fore.YELLOW + "   ⚠️  No AI key — keyword fallback scoring")

    # Pre-filter: only send stories to AI if they have keyword matches
    # Raised from 15 → 25 to reduce AI calls on borderline stories
    AI_PREFILTER_MIN = 25  # must score at least 25 on keywords before calling AI

    scored = []
    ai_count = 0
    skipped_ai = 0
    blocked_count = 0
    ai_rejected = 0
    for story in all_stories:
        # Safety filter: reject blocked/sensitive topics before any AI call
        is_blocked, matched_kw = _is_blocked_topic(story["title"], story["summary"])
        if is_blocked:
            logging.info(f"BLOCKED topic [{matched_kw}]: {story['title'][:60]}")
            blocked_count += 1
            continue

        if use_ai:
            # Quick keyword check first to avoid wasting API calls
            pre_score, pre_kws = score_story_fallback(story["title"], story["summary"])
            if pre_score < AI_PREFILTER_MIN:
                # Too boring for AI — skip entirely (don't even show low-score fallbacks)
                skipped_ai += 1
                continue

            card = score_and_generate_card(story["title"], story["summary"], story["source"])
            if card:
                # AI may explicitly reject a story (safety / no trend potential)
                if card.get("reject"):
                    logging.info(f"AI rejected: {card.get('reject_reason', '?')} | {story['title'][:60]}")
                    ai_rejected += 1
                    continue
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
                # AI call failed → use keyword fallback
                score, kws = score_story_fallback(story["title"], story["summary"])
                story["score"] = score
                story["keywords"] = kws
                story["scoring_method"] = "fallback"
                name, ticker = _generate_fallback_name(story["title"])
                story["ai_name"] = name
                story["ai_ticker"] = ticker
                story["ai_reason"] = f"Keyword match: {', '.join(kws[:3])}" if kws else "Trending"
                story["ai_description"] = f"{name} — based on breaking news. LFG! 🚀"
        else:
            score, kws = score_story_fallback(story["title"], story["summary"])
            story["score"] = score
            story["keywords"] = kws
            story["scoring_method"] = "fallback"
            name, ticker = _generate_fallback_name(story["title"])
            story["ai_name"] = name
            story["ai_ticker"] = ticker
            story["ai_reason"] = f"Keyword match: {', '.join(kws[:3])}" if kws else "Trending"
            story["ai_description"] = f"{name} — based on breaking news. LFG! 🚀"

        scored.append(story)

    summary_parts = []
    if ai_count:
        summary_parts.append(f"🤖 AI scored {ai_count}")
    if skipped_ai:
        summary_parts.append(f"skipped {skipped_ai} boring (saved ~${skipped_ai * 0.001:.3f})")
    if ai_rejected:
        summary_parts.append(f"AI rejected {ai_rejected}")
    if blocked_count:
        summary_parts.append(f"blocked {blocked_count} sensitive")
    if summary_parts:
        print(Fore.CYAN + "   " + " | ".join(summary_parts))

    # Sort by score descending
    scored.sort(key=lambda x: x["score"], reverse=True)

    # Filter above threshold
    alerts = [s for s in scored if s["score"] >= MIN_SCORE_TO_ALERT]

    print(Fore.CYAN + f"   {len(alerts)} stories above threshold (≥{MIN_SCORE_TO_ALERT})")

    # AI already ranked by score — keep only the top N for this wave
    if len(alerts) > TOP_STORIES_PER_WAVE:
        print(Fore.CYAN + f"   Trimming to top {TOP_STORIES_PER_WAVE} stories for this wave")
        alerts = alerts[:TOP_STORIES_PER_WAVE]

    logging.info(f"Scan: {len(all_stories)} stories, {len(alerts)} alerts (top {TOP_STORIES_PER_WAVE} max)")

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
