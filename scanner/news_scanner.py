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

import requests

from config.settings import (
    RSS_FEEDS, REDDIT_JSON_SUBREDDITS,
    HIGH_VALUE_KEYWORDS, LOW_VALUE_KEYWORDS,
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


def _extract_entry_image(entry):
    """
    Pull the actual image URL out of an RSS entry.
    Reddit/Imgur/etc. embed the post image in media_content or enclosures.
    Using this means we get the viral image itself, not a random search result.
    """
    # 1. media:content (Reddit, Imgur, many modern feeds)
    media = getattr(entry, "media_content", None)
    if media:
        for m in media:
            url = m.get("url", "")
            if url and any(url.lower().endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".gif", ".webp")):
                return url
        # accept non-extension URLs from media_content too (e.g. i.redd.it)
        for m in media:
            url = m.get("url", "")
            if url and ("i.redd.it" in url or "i.imgur.com" in url or "preview.redd.it" in url):
                return url

    # 2. enclosures (podcast/media feeds sometimes use this)
    enclosures = getattr(entry, "enclosures", None)
    if enclosures:
        for enc in enclosures:
            url = enc.get("href", enc.get("url", ""))
            if url and "image" in enc.get("type", "image"):
                return url

    # 3. <img> tag inside the summary/content HTML
    content = getattr(entry, "content", [])
    html = content[0].get("value", "") if content else getattr(entry, "summary", "")
    if html:
        import re as _re
        m = _re.search(r'<img[^>]+src=["\']([^"\']+)["\']', html)
        if m:
            url = m.group(1)
            # Skip tiny icons and tracking pixels
            if url and not any(x in url for x in ["1x1", "pixel", "icon", "emoji"]):
                return url

    return None


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
                "source_image_url": _extract_entry_image(entry),
            })

    except Exception as e:
        logging.error(f"Error scanning {feed_name}: {e}")

    return stories


_REDDIT_HEADERS = {"User-Agent": "TrendBot/3.0 (viral news scanner)"}


def _scan_reddit_json(subreddit, min_upvotes):
    """
    Scan a subreddit via Reddit's JSON API.

    Why JSON instead of RSS:
    - RSS gives no upvote count → we can't filter for virality
    - RSS thumbnails are tiny or auth-gated → images break
    - JSON gives score + full preview image from the post itself

    Only posts with score >= min_upvotes are returned.
    """
    stories = []
    try:
        url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit=25"
        resp = requests.get(url, headers=_REDDIT_HEADERS, timeout=10)
        if resp.status_code != 200:
            logging.warning(f"Reddit r/{subreddit}: HTTP {resp.status_code}")
            return stories

        posts = resp.json().get("data", {}).get("children", [])
        feed_name = f"Reddit r/{subreddit}"

        for pw in posts:
            post = pw.get("data", {})

            # Hard gates
            if post.get("stickied") or post.get("pinned"):
                continue
            if post.get("over_18"):
                continue

            score = post.get("score", 0)
            if score < min_upvotes:
                continue

            title = post.get("title", "").strip()
            if not title:
                continue

            sid = hashlib.md5(post.get("id", title).encode()).hexdigest()
            with _seen_ids_lock:
                if sid in _seen_ids:
                    continue
                _seen_ids.add(sid)

            # Age check
            created_utc = post.get("created_utc", 0)
            if created_utc:
                pub_time = datetime.fromtimestamp(created_utc, tz=timezone.utc)
                if (datetime.now(timezone.utc) - pub_time) > timedelta(minutes=MAX_STORY_AGE_MINUTES):
                    continue
            else:
                pub_time = None

            # Best image: full-res preview from the post (not thumbnail)
            source_image_url = None
            preview_images = post.get("preview", {}).get("images", [])
            if preview_images:
                src = preview_images[0].get("source", {})
                img_url = src.get("url", "")
                if img_url:
                    # Reddit HTML-encodes & in preview URLs
                    source_image_url = img_url.replace("&amp;", "&")
            # Fallback: thumbnail (only if it's a real URL, not "self"/"default")
            if not source_image_url:
                thumb = post.get("thumbnail", "")
                if thumb and thumb.startswith("http"):
                    source_image_url = thumb

            link = f"https://www.reddit.com{post.get('permalink', '')}"
            summary = post.get("selftext", "")[:300]

            stories.append({
                "id": sid,
                "source": feed_name,
                "title": title,
                "summary": summary,
                "link": link,
                "pub_time": pub_time,
                "published": pub_time.strftime("%Y-%m-%d %H:%M UTC") if pub_time else "Unknown",
                "source_image_url": source_image_url,
                "reddit_score": score,
            })

        if stories:
            logging.info(f"Reddit r/{subreddit}: {len(stories)} posts ≥{min_upvotes} upvotes")

    except Exception as e:
        logging.error(f"Reddit JSON scan error r/{subreddit}: {e}")

    return stories


def run_scan():
    """
    Scan all RSS feeds IN PARALLEL, then score with AI.
    Returns list of high-scoring story dicts, sorted by score.
    """
    print(Fore.CYAN + f"\n🔍 Scanning {len(RSS_FEEDS)} feeds... ({datetime.now().strftime('%H:%M:%S')})")

    # --- Phase 1: Parallel RSS + Reddit JSON fetch ---
    all_stories = []
    with ThreadPoolExecutor(max_workers=30) as pool:
        futures = {}
        # RSS feeds
        for name, url in RSS_FEEDS:
            futures[pool.submit(_scan_single_feed, name, url)] = name
        # Reddit JSON (upvote-gated, full images)
        for subreddit, min_upvotes in REDDIT_JSON_SUBREDDITS:
            futures[pool.submit(_scan_reddit_json, subreddit, min_upvotes)] = f"r/{subreddit}"

        for future in as_completed(futures):
            try:
                all_stories.extend(future.result())
            except Exception as e:
                logging.error(f"Feed thread error: {e}")

    rss_count = len(RSS_FEEDS)
    reddit_count = len(REDDIT_JSON_SUBREDDITS)
    print(Fore.CYAN + f"   Fetched {len(all_stories)} new stories ({rss_count} RSS feeds + {reddit_count} Reddit subs)")

    if not all_stories:
        return []

    # --- Phase 2: Funnel — keyword score ALL → top 15 → AI → top 5 ---
    use_ai = bool(ANTHROPIC_API_KEY)

    # Step A: keyword-score + block filter everything (instant, no API)
    candidates = []
    blocked_count = 0
    for story in all_stories:
        is_blocked, matched_kw = _is_blocked_topic(story["title"], story["summary"])
        if is_blocked:
            logging.info(f"BLOCKED [{matched_kw}]: {story['title'][:60]}")
            blocked_count += 1
            continue
        pre_score, pre_kws = score_story_fallback(story["title"], story["summary"])
        story["_pre_score"] = pre_score
        story["_pre_kws"] = pre_kws
        candidates.append(story)

    # Step B: sort by keyword score, keep only top 30 for AI
    # (49 feeds now — viral Reddit content rarely has meme keywords so needs
    #  a larger pool to ensure good stories aren't cut before AI sees them)
    candidates.sort(key=lambda x: x["_pre_score"], reverse=True)
    AI_CAP = 30
    ai_pool = candidates[:AI_CAP]
    skipped_ai = len(candidates) - len(ai_pool)

    print(Fore.CYAN + f"   Funnel: {len(all_stories)} → {len(candidates)} (blocked {blocked_count}) → top {len(ai_pool)} for AI")

    # Step C: AI-score the shortlist
    scored = []
    ai_count = 0
    ai_rejected = 0
    for story in ai_pool:
        pre_kws = story.pop("_pre_kws", [])
        story.pop("_pre_score", None)

        if use_ai:
            card = score_and_generate_card(story["title"], story["summary"], story["source"])
            if card:
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
                # AI call failed → keyword fallback
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
            story["score"] = story.pop("_pre_score", 0)
            story["keywords"] = pre_kws
            story["scoring_method"] = "fallback"
            name, ticker = _generate_fallback_name(story["title"])
            story["ai_name"] = name
            story["ai_ticker"] = ticker
            story["ai_reason"] = f"Keyword match: {', '.join(pre_kws[:3])}" if pre_kws else "Trending"
            story["ai_description"] = f"{name} — based on breaking news. LFG! 🚀"

        scored.append(story)

    summary_parts = [f"🤖 AI scored {ai_count}/{len(ai_pool)}"]
    if ai_rejected:
        summary_parts.append(f"AI rejected {ai_rejected}")
    if skipped_ai:
        summary_parts.append(f"skipped {skipped_ai} (saved ~${skipped_ai * 0.001:.2f})")
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
