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
# NEWS SOURCES (trimmed to ~55 high-quality feeds)
# ---------------------------------------------------------------
RSS_FEEDS = [
    # --- MAJOR NATIONAL ---
    ("Reuters Top News",        "https://feeds.reuters.com/reuters/topNews"),
    ("AP News Top Stories",     "https://feeds.apnews.com/rss/topnews"),
    ("AP News Entertainment",   "https://feeds.apnews.com/rss/entertainment"),
    ("BBC News",                "http://feeds.bbci.co.uk/news/rss.xml"),
    ("BBC US & Canada",         "http://feeds.bbci.co.uk/news/world/us_and_canada/rss.xml"),
    ("NPR News",                "https://feeds.npr.org/1001/rss.xml"),
    ("CNN Top Stories",         "http://rss.cnn.com/rss/cnn_topstories.rss"),
    ("Fox News Latest",         "https://moxie.foxnews.com/google-publisher/latest.xml"),
    ("NBC News",                "https://feeds.nbcnews.com/nbcnews/public/news"),
    ("CBS News",                "https://www.cbsnews.com/latest/rss/main"),
    ("ABC News",                "https://abcnews.go.com/abcnews/topstories"),
    ("NYT Home Page",           "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml"),
    ("Washington Post",         "https://feeds.washingtonpost.com/rss/national"),
    ("The Guardian US",         "https://www.theguardian.com/us-news/rss"),

    # --- POLITICS ---
    ("Politico",                "https://www.politico.com/rss/politicopicks.xml"),
    ("The Hill",                "https://thehill.com/rss/syndicator/19110"),
    ("Axios",                   "https://api.axios.com/feed/"),
    ("Mediaite",                "https://www.mediaite.com/feed/"),

    # --- LOCAL US (secret edge) ---
    ("KOIN Portland",           "https://www.koin.com/feed/"),
    ("Oregon Live",             "https://www.oregonlive.com/arc/outboundfeeds/rss/"),
    ("Seattle Times",           "https://www.seattletimes.com/feed/"),
    ("LA Times",                "https://www.latimes.com/rss2.0.xml"),
    ("SF Gate",                 "https://www.sfgate.com/rss/feed/SFGate-Top-News-476.php"),
    ("CBS DFW Dallas",          "https://www.cbsnews.com/texas/local/feed/"),
    ("WSVN Miami",              "https://wsvn.com/feed/"),
    ("Tampa Bay Times",         "https://www.tampabay.com/feeds/rss/news/"),
    ("NY Post",                 "https://nypost.com/feed/"),
    ("Chicago Tribune",         "https://www.chicagotribune.com/arcio/rss/"),
    ("Denver Post",             "https://www.denverpost.com/feed/"),
    ("Atlanta Journal",         "https://www.ajc.com/arc/outboundfeeds/rss/"),

    # --- VIRAL / POP CULTURE ---
    ("TMZ",                     "https://www.tmz.com/rss.xml"),
    ("People Magazine",         "https://people.com/feed/"),
    ("Know Your Meme",          "https://knowyourmeme.com/newsfeed.rss"),
    ("Buzzfeed",                "https://www.buzzfeed.com/news.xml"),

    # --- CRYPTO & FINANCE ---
    ("CoinDesk",                "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("Decrypt",                 "https://decrypt.co/feed"),
    ("CoinTelegraph",           "https://cointelegraph.com/rss"),
    ("The Block",               "https://www.theblock.co/rss.xml"),

    # --- REDDIT (catches viral 30-60 min early) ---
    ("Reddit World News",       "https://www.reddit.com/r/worldnews/.rss"),
    ("Reddit Politics",         "https://www.reddit.com/r/politics/.rss"),
    ("Reddit Crypto",           "https://www.reddit.com/r/CryptoCurrency/.rss"),
    ("Reddit Solana",           "https://www.reddit.com/r/solana/.rss"),
    ("Reddit Meme Economy",     "https://www.reddit.com/r/MemeEconomy/.rss"),
    ("Reddit Popular",          "https://www.reddit.com/r/popular/.rss"),
    ("Reddit All Rising",       "https://www.reddit.com/r/all/rising/.rss"),
    ("Reddit News",             "https://www.reddit.com/r/news/.rss"),
    ("Reddit WTF",              "https://www.reddit.com/r/WTF/.rss"),

    # --- TECH & SCIENCE ---
    ("TechCrunch",              "https://techcrunch.com/feed/"),
    ("The Verge",               "https://www.theverge.com/rss/index.xml"),
    ("Ars Technica",            "https://feeds.arstechnica.com/arstechnica/index"),
    ("Wired",                   "https://www.wired.com/feed/rss"),

    # --- SPORTS ---
    ("ESPN Top Headlines",      "https://www.espn.com/espn/rss/news"),
]

# ---------------------------------------------------------------
# SCORING
# ---------------------------------------------------------------

# Minimum AI score to alert (AI scoring is much smarter than keywords)
MIN_SCORE_TO_ALERT = 60

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

# ---------------------------------------------------------------
# TIMING
# ---------------------------------------------------------------
SCAN_INTERVAL_MINUTES  = 5
ACTIVE_HOURS_START_UTC = 13
ACTIVE_HOURS_END_UTC   = 23
MAX_STORY_AGE_MINUTES  = 45

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
