"""
==============================================================
  TREND BOT v3 — AI SCORER + TOKEN CARD GENERATOR

  Generates the COMPLETE pump.fun token card:
  - Score (0-100) with detailed reasoning
  - Token name + ticker
  - Description (the text buyers see on pump.fun)
  - Visual description (for image search)
  - Optional social links suggestion

  Cost: ~$0.002 per story (Haiku)
==============================================================
"""

import json
import logging
import time
import requests

from config.settings import ANTHROPIC_API_KEY, AI_MODEL

# Rate limiting
_last_call = 0
_MIN_DELAY = 0.3

# Cache
_cache = {}
_cache_ttl = 600

# ---------------------------------------------------------------
# Main scoring + card generation (single API call)
# ---------------------------------------------------------------

FULL_CARD_PROMPT = """You are a pump.fun meme token expert. Analyze this news story and create a COMPLETE token card.

NEWS STORY:
Title: {title}
Summary: {summary}
Source: {source}

SCORING CRITERIA (score each 0-25):
1. VISUAL: Can this become a mascot/meme image? Animals, costumes, absurd visuals = high
2. EMOTION: Does it trigger humor, outrage, surprise, absurdity? Strong emotion = high
3. VIRALITY: Would crypto Twitter share this? Unusual + timely = high
4. TIMING: Is this breaking news or old? Fresh and trending = high

TOKEN CARD RULES:
- Name: 1-3 words, catchy, memeable, memorable (like "Dogwifhat", "Slurmit", "Bonk")
- Ticker: 3-6 chars, ALL CAPS, easy to type
- Description: 1-2 sentences MAX. Must be:
  * Funny/irreverent tone (crypto degen style)
  * Reference the viral moment from the news
  * Create FOMO ("the next 100x", "you saw it here first")
  * Include a call to action or meme phrase
  * Under 200 characters ideally
- Visual: Describe the ideal token profile picture (for image search)

EXAMPLES of great pump.fun descriptions:
- "The frog that crashed the White House. Slurmit season is here. 🐸"
- "He really showed up in a banana suit to Congress. $BNANA to the moon 🍌"
- "When the bear market ends but your portfolio doesn't know yet 📈🐻"

Respond with ONLY this JSON (no markdown, no backticks, no extra text):
{{
    "score": 75,
    "visual_score": 20,
    "emotion_score": 18,
    "virality_score": 22,
    "timing_score": 15,
    "reasoning": "Brief 1-line explanation of the score",
    "name": "Slurmit",
    "ticker": "SLRM",
    "description": "The frog that crashed the White House. Slurmit season. 🐸",
    "visual": "green cartoon frog mascot with protest sign",
    "keywords": ["frog", "protest", "white house"]
}}

If the story is boring/sad/generic: score below 30 and still fill all fields."""


def score_and_generate_card(title, summary="", source=""):
    """
    Single API call that scores the story AND generates the full token card.

    Returns dict with:
        score, reasoning, name, ticker, description, visual, keywords,
        visual_score, emotion_score, virality_score, timing_score
    Or None if AI unavailable.
    """
    global _last_call

    if not ANTHROPIC_API_KEY:
        return None

    # Check cache
    cache_key = title[:100].lower().strip()
    if cache_key in _cache:
        t, result = _cache[cache_key]
        if time.time() - t < _cache_ttl:
            return result

    # Rate limiting
    elapsed = time.time() - _last_call
    if elapsed < _MIN_DELAY:
        time.sleep(_MIN_DELAY - elapsed)

    try:
        prompt = FULL_CARD_PROMPT.format(
            title=title[:200],
            summary=summary[:400],
            source=source,
        )

        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": AI_MODEL,
                "max_tokens": 300,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=15,
        )

        _last_call = time.time()

        if resp.status_code == 429:
            logging.warning("AI rate limited, waiting 5s...")
            time.sleep(5)
            return None

        if resp.status_code != 200:
            logging.error(f"AI error {resp.status_code}: {resp.text[:200]}")
            return None

        data = resp.json()
        text = data["content"][0]["text"].strip()

        # Clean markdown fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        if text.startswith("{") is False:
            # Try to find JSON in the response
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                text = text[start:end]

        result = json.loads(text)

        # Validate and clean
        result["score"] = max(0, min(100, int(result.get("score", 0))))
        result["name"] = str(result.get("name", "Token"))[:40]
        result["ticker"] = str(result.get("ticker", "TOKEN"))[:8].upper().replace(" ", "")
        result["description"] = str(result.get("description", ""))[:280]
        result["visual"] = str(result.get("visual", ""))[:100]
        result["reasoning"] = str(result.get("reasoning", ""))[:150]
        result["keywords"] = result.get("keywords", [])[:5]

        # Ensure description exists and is good
        if len(result["description"]) < 10:
            result["description"] = f"{result['name']} — inspired by trending news. LFG! 🚀"

        # Cache
        _cache[cache_key] = (time.time(), result)

        logging.info(
            f"AI Card: {result['score']}/100 | {result['name']} (${result['ticker']}) | "
            f"Desc: {result['description'][:60]} | Story: {title[:50]}"
        )

        return result

    except json.JSONDecodeError as e:
        logging.error(f"AI invalid JSON: {e}")
        return None
    except Exception as e:
        logging.error(f"AI scorer error: {e}")
        return None


# ---------------------------------------------------------------
# Standalone name+description generator (fallback)
# ---------------------------------------------------------------

def generate_card_ai(title, summary=""):
    """
    Generate just the token card (name, ticker, description) without scoring.
    Used when scoring was done via keywords but we still want AI naming.
    """
    if not ANTHROPIC_API_KEY:
        return None

    try:
        prompt = f"""Create a pump.fun meme token for this news:

Title: {title[:200]}
Details: {summary[:200]}

Respond ONLY with JSON:
{{
    "name": "Creative Name",
    "ticker": "TICK",
    "description": "Short funny pump.fun description under 200 chars with emoji"
}}

Rules:
- Name: 1-3 words, catchy, memeable
- Ticker: 3-6 chars, ALL CAPS
- Description: funny, degen tone, creates FOMO, 1-2 sentences MAX
- Must be related to the news story"""

        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": AI_MODEL,
                "max_tokens": 150,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=10,
        )

        if resp.status_code == 200:
            data = resp.json()
            text = data["content"][0]["text"].strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

            result = json.loads(text)
            return {
                "name": str(result.get("name", "Token"))[:40],
                "ticker": str(result.get("ticker", "TOKEN"))[:8].upper(),
                "description": str(result.get("description", "LFG 🚀"))[:280],
            }

        return None

    except Exception as e:
        logging.error(f"AI card gen error: {e}")
        return None
