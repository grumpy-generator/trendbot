"""
==============================================================
  TREND BOT v3 — DUPLICATE CHECKER
  Checks if token already exists on pump.fun
  Cache TTL increased to 10min to reduce API calls
==============================================================
"""

import requests
import logging
import time

_cache = {}
_cache_ttl = 600  # 10 minutes (was 2min — too aggressive)


def search_existing_tokens(keywords, story_title):
    """Search pump.fun for existing tokens matching this trend."""
    results = []
    search_terms = keywords[:3] if keywords else [story_title.split()[0]]

    for term in search_terms:
        term_lower = term.lower().strip()
        if not term_lower or len(term_lower) < 2:
            continue

        # Check cache
        if term_lower in _cache:
            cached_time, cached_result = _cache[term_lower]
            if time.time() - cached_time < _cache_ttl:
                results.extend(cached_result)
                continue

        found = _search_pumpfun(term_lower)
        _cache[term_lower] = (time.time(), found)
        results.extend(found)

    # Deduplicate by mint
    seen = set()
    unique = []
    for t in results:
        mint = t.get("mint", "")
        if mint and mint not in seen:
            seen.add(mint)
            unique.append(t)

    return unique


def _search_pumpfun(query):
    """Query pump.fun API for matching tokens."""
    try:
        resp = requests.get(
            "https://frontend-api.pump.fun/coins",
            params={
                "searchTerm": query,
                "limit": 10,
                "sort": "created_timestamp",
                "order": "DESC",
                "includeNsfw": "false",
            },
            timeout=5,
        )
        if resp.status_code == 200:
            coins = resp.json()
            return [
                {
                    "mint": c.get("mint", ""),
                    "name": c.get("name", ""),
                    "ticker": c.get("symbol", ""),
                    "market_cap": c.get("usd_market_cap", 0),
                    "created": c.get("created_timestamp", 0),
                    "url": f"https://pump.fun/coin/{c.get('mint', '')}",
                }
                for c in coins
            ]
    except Exception as e:
        logging.debug(f"pump.fun search error for '{query}': {e}")
    return []


def evaluate_competition(existing_tokens):
    """Decide if it's still worth launching given existing tokens."""
    if not existing_tokens:
        return {
            "should_launch": True,
            "confidence": "HIGH",
            "reason": "No existing tokens — you'd be FIRST 🥇",
        }

    count = len(existing_tokens)
    top_mcap = max((t.get("market_cap", 0) for t in existing_tokens), default=0)

    if count == 1 and top_mcap < 5_000:
        return {
            "should_launch": True,
            "confidence": "MEDIUM",
            "reason": f"1 token exists, low mcap (${top_mcap:,.0f}) — still early",
            "existing": existing_tokens,
        }
    elif count <= 2 and top_mcap < 10_000:
        return {
            "should_launch": True,
            "confidence": "LOW",
            "reason": f"{count} tokens, top mcap ${top_mcap:,.0f} — competitive but possible",
            "existing": existing_tokens,
        }
    elif top_mcap >= 20_000:
        return {
            "should_launch": False,
            "confidence": "SKIP",
            "reason": f"Top token at ${top_mcap:,.0f} mcap — too late 🔴",
            "existing": existing_tokens,
        }
    else:
        return {
            "should_launch": False,
            "confidence": "SKIP",
            "reason": f"{count} tokens already exist — saturated 🔴",
            "existing": existing_tokens,
        }


def format_competition_report(story, evaluation):
    """Format a readable competition report."""
    lines = [f"\n  🔍 Competition: '{story['title'][:50]}...'"]
    lines.append(f"  → {evaluation['reason']}")
    if evaluation.get("existing"):
        for t in evaluation["existing"][:3]:
            lines.append(f"    • {t['name']} (${t['ticker']}) — mcap: ${t.get('market_cap', 0):,.0f}")
    return "\n".join(lines)
