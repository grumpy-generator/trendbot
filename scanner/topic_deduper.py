"""
==============================================================
  TREND BOT v3 — TOPIC-LEVEL DEDUPLICATION
  Prevents re-alerting on trends that are already 2-3 days old.

  Article-level dedup (_seen_ids in news_scanner.py) only stops
  the exact same article from being sent twice. This layer stops
  the SAME TOPIC from being re-alerted within 5 days even when
  fresh new articles about that trend appear.
==============================================================
"""

import json
import os
import time
import logging

_DATA_DIR = "data"
_STORE_FILE = os.path.join(_DATA_DIR, "seen_topics.json")
_TOPIC_TTL = 5 * 24 * 3600  # 5 days


def _load_store():
    if os.path.exists(_STORE_FILE):
        try:
            with open(_STORE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_store(store):
    os.makedirs(_DATA_DIR, exist_ok=True)
    try:
        with open(_STORE_FILE, "w") as f:
            json.dump(store, f)
    except Exception as e:
        logging.warning(f"topic_deduper: could not save store: {e}")


def _make_topic_key(keywords):
    """Build a stable key from the top 3 keywords (sorted, lowercased)."""
    clean = sorted(set(k.lower().strip() for k in keywords if k and k.strip()))[:3]
    if not clean:
        return None
    return "_".join(clean)


def is_topic_seen(keywords):
    """
    Return True if this keyword combination was alerted in the last 5 days.
    Call this BEFORE sending an alert to avoid re-alerting stale trends.
    """
    key = _make_topic_key(keywords)
    if not key:
        return False

    store = _load_store()
    now = time.time()

    # Clean expired entries while we have it open
    expired = [k for k, ts in store.items() if now - ts >= _TOPIC_TTL]
    if expired:
        for k in expired:
            del store[k]
        _save_store(store)

    seen = key in store
    if seen:
        age_h = (now - store[key]) / 3600
        logging.info(f"topic_deduper: SKIP '{key}' — already alerted {age_h:.1f}h ago")
    return seen


def mark_topic_seen(keywords):
    """
    Record that this topic was just alerted. Call this AFTER sending.
    """
    key = _make_topic_key(keywords)
    if not key:
        return

    store = _load_store()
    now = time.time()

    # Clean expired
    store = {k: v for k, v in store.items() if now - v < _TOPIC_TTL}
    store[key] = now
    _save_store(store)
    logging.info(f"topic_deduper: marked '{key}' as seen (expires in 72h)")
