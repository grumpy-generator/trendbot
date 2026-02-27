"""
==============================================================
  TREND BOT v3 — SETTINGS
  All configuration in one place.
  Secrets loaded from .env file (never hardcoded).
==============================================================
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load secrets from .env file (project root)
_project_root = Path(__file__).resolve().parent.parent
load_dotenv(_project_root / ".env")

# ---------------------------------------------------------------
# SECRETS (loaded from .env — never edit here)
# ---------------------------------------------------------------
WALLET_PRIVATE_KEY = os.getenv("WALLET_PRIVATE_KEY", "YOUR_PRIVATE_KEY_HERE")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")
ANTHROPIC_API_KEY  = os.getenv("ANTHROPIC_API_KEY", "")
AI_MODEL = "claude-haiku-4-5-20251001"
SOLANA_RPC_URL     = os.getenv("SOLANA_RPC_URL", "https://api.devnet.solana.com")

# ---------------------------------------------------------------
# TRADING SETTINGS
# ---------------------------------------------------------------

# SOL to spend per token launch (dev buy)
DEV_BUY_AMOUNT_SOL = 0.1

# Sell strategy: sell 100% at +70% gain — simple and clean
SELL_STRATEGY = [
    {"target_multiplier": 1.7, "sell_percent": 100},
]

# Stop loss: sell everything if price drops 40% from BUY PRICE
STOP_LOSS_PERCENT = 0.40
STOP_LOSS_FROM_BUY_PRICE = True  # True = vs buy price, False = vs peak

# Creator fee: 100% to your wallet
CREATOR_FEE_PERCENT = 100

# ---------------------------------------------------------------
# SAFETY LIMITS (hard-coded in logic, not just instructions)
# ---------------------------------------------------------------
MAX_LAUNCHES_PER_HOUR = 3
MAX_DAILY_SOL_SPEND   = 2.0
MAX_ACTIVE_POSITIONS  = 5

# ---------------------------------------------------------------
# NEWS SOURCES
#
# Philosophy: we want EARLY signal, before crypto Twitter picks it up.
# CoinDesk / CoinTelegraph / crypto subreddits are DOWNSTREAM — they
# report on trends 24-48h after the meme already spread elsewhere.
# Instead: scan the places where weird/viral stuff ORIGINATES.
# ---------------------------------------------------------------
RSS_FEEDS = [
    # --- BREAKING / WEIRD NEWS (national + tabloid) ---
    # Kept small: we just need the one that breaks the story, not 10 outlets
    ("AP News Entertainment",   "https://feeds.apnews.com/rss/entertainment"),
    ("AP News Oddities",        "https://feeds.apnews.com/rss/oddities"),
    ("NY Post",                 "https://nypost.com/feed/"),
    ("NY Post Weird",           "https://nypost.com/weird/feed/"),
    ("Fox News Latest",         "https://moxie.foxnews.com/google-publisher/latest.xml"),
    ("Mediaite",                "https://www.mediaite.com/feed/"),
    ("TMZ",                     "https://www.tmz.com/rss.xml"),
    ("People Magazine",         "https://people.com/feed/"),
    ("Barstool Sports",         "https://www.barstoolsports.com/rss"),

    # --- VIRAL / MEME CULTURE (where trends actually start) ---
    ("Know Your Meme",          "https://knowyourmeme.com/newsfeed.rss"),
    ("Fark",                    "https://www.fark.com/fark.rss"),
    ("Oddity Central",          "https://www.odditycentral.com/feed"),
    ("Daily Dot",               "https://www.dailydot.com/feed/"),
    ("Bored Panda",             "https://www.boredpanda.com/feed/"),
    ("Cheezburger",             "https://cheezburger.com/feed"),
    ("LADbible",                "https://www.ladbible.com/rss"),
    ("Unilad",                  "https://www.unilad.com/feed/"),
    ("ViralHog",                "https://www.viralhog.com/feed"),
    ("Cracked",                 "https://www.cracked.com/feed"),
    ("The Onion",               "https://www.theonion.com/rss"),
    ("ClickHole",               "https://www.clickhole.com/rss"),
    ("IFLScience",              "https://www.iflscience.com/rss.xml"),
    ("Futurism",                "https://futurism.com/feed"),

    # --- IMGUR (visual virality — where memes circulate before Twitter) ---
    ("Imgur Hot",               "https://imgur.com/hot.rss"),
    ("Imgur Viral",             "https://imgur.com/viral.rss"),

    # --- REDDIT VIRAL (best early-signal, 30-60 min ahead of mainstream) ---
    ("Reddit Popular",          "https://www.reddit.com/r/popular/.rss"),
    ("Reddit All Rising",       "https://www.reddit.com/r/all/rising/.rss"),
    ("Reddit nottheonion",      "https://www.reddit.com/r/nottheonion/.rss"),
    ("Reddit Damnthatsinteresting", "https://www.reddit.com/r/Damnthatsinteresting/.rss"),
    ("Reddit mildlyinteresting","https://www.reddit.com/r/mildlyinteresting/.rss"),
    ("Reddit interestingasfuck","https://www.reddit.com/r/interestingasfuck/.rss"),
    ("Reddit BeAmazed",         "https://www.reddit.com/r/BeAmazed/.rss"),
    ("Reddit nextfuckinglevel", "https://www.reddit.com/r/nextfuckinglevel/.rss"),
    ("Reddit WTF",              "https://www.reddit.com/r/WTF/.rss"),
    ("Reddit PublicFreakout",   "https://www.reddit.com/r/PublicFreakout/.rss"),
    ("Reddit AnimalsBeingDerps","https://www.reddit.com/r/AnimalsBeingDerps/.rss"),
    ("Reddit Unexpected",       "https://www.reddit.com/r/Unexpected/.rss"),
    ("Reddit HumansBeingBros",  "https://www.reddit.com/r/HumansBeingBros/.rss"),
    ("Reddit FloridaMan",       "https://www.reddit.com/r/FloridaMan/.rss"),
    ("Reddit news",             "https://www.reddit.com/r/news/.rss"),
    ("Reddit worldnews",        "https://www.reddit.com/r/worldnews/.rss"),
    ("Reddit TikTokCringe",     "https://www.reddit.com/r/TikTokCringe/.rss"),
    ("Reddit LivestreamFail",   "https://www.reddit.com/r/LivestreamFail/.rss"),
    ("Reddit CrazyFuckingVideos","https://www.reddit.com/r/CrazyFuckingVideos/.rss"),
    ("Reddit shitposting",      "https://www.reddit.com/r/shitposting/.rss"),

    # --- SPORTS / POP CULTURE (athletes and celebrities go viral fast) ---
    ("ESPN Top Headlines",      "https://www.espn.com/espn/rss/news"),
    ("Deadspin",                "https://deadspin.com/rss"),
    ("E! Online",               "https://www.eonline.com/syndication/feeds/rssfeeds/topstories.xml"),

    # --- LOCAL WEIRD NEWS (breaks before nationals — FloridaMan effect) ---
    ("WSVN Miami",              "https://wsvn.com/feed/"),
    ("NY Daily News",           "https://www.nydailynews.com/arcio/rss/"),
]

# ---------------------------------------------------------------
# SCORING
# ---------------------------------------------------------------

# Minimum AI score to alert (AI scoring is much smarter than keywords)
MIN_SCORE_TO_ALERT = 60

# Max stories to send per wave (AI picks the best ones)
TOP_STORIES_PER_WAVE = 5

# Fallback keywords (used ONLY if AI scoring unavailable)
HIGH_VALUE_KEYWORDS = [
    "frog", "dog", "cat", "monkey", "ape", "bear", "bull", "whale",
    "penguin", "hamster", "goat",
    "trump", "biden", "musk", "elon", "congress", "president",
    "protest", "rally", "viral", "costume",
    "bitcoin", "crypto", "solana",
    "scandal", "arrested", "fired", "resigned",
    "crash", "surge", "ban", "tariff",
]

LOW_VALUE_KEYWORDS = [
    "obituary", "funeral", "weather forecast", "traffic",
    "quarterly earnings", "annual report", "press release",
    "tax filing", "zoning", "budget committee",
]

# Stories matching ANY of these will be rejected before AI scoring
# Covers: racism, discrimination, religion-baiting, mass tragedies
BLOCKED_TOPIC_KEYWORDS = [
    # Racial hatred / discrimination
    "white supremac", "white nationalist", "neo-nazi", "kkk ", "hate crime",
    "ethnic cleansing", "genocide", "antisemit", "islamophob",
    # Tragedies that shouldn't be meme'd
    "school shooting", "mass shooting", "mass casualty", "terrorist attack",
    "suicide bomber", "child abuse", "pedophil", "human trafficking",
    # Religion (mocking specific religions creates bad optics)
    "mosque attack", "church attack", "synagogue attack", "temple attack",
    "blasphemy", "religious persecution", "jihad",
]

# ---------------------------------------------------------------
# TIMING  — 3 waves/day at peak launch hours (UTC)
# ---------------------------------------------------------------
#   Wave 1 → 13:00 UTC = 08:00 EST  — market open, CT waking up
#   Wave 2 → 17:00 UTC = 12:00 EST  — midday peak engagement
#   Wave 3 → 21:00 UTC = 16:00 EST  — post-market, evening degens
WAVE_TIMES_UTC         = ["13:00", "17:00", "21:00"]
SCAN_INTERVAL_MINUTES  = 15   # kept for --scan-once / health-check compat
ACTIVE_HOURS_START_UTC = 13
ACTIVE_HOURS_END_UTC   = 22
MAX_STORY_AGE_MINUTES  = 720  # 12 hours — older articles are rejected

# ---------------------------------------------------------------
# NOTIFICATIONS
# ---------------------------------------------------------------
NOTIFY_TERMINAL = True
NOTIFY_TELEGRAM = bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)
USE_AI_SCORING = bool(ANTHROPIC_API_KEY)

# ---------------------------------------------------------------
# SOLANA
# ---------------------------------------------------------------
PUMP_FUN_PROGRAM_ID = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
