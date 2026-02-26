"""
==============================================================
  TREND BOT v3 — TELEGRAM BOT
  Flow:
    1. Bot sends FULL CARD (image + name + ticker + score + link)
    2. You tap [🧪 Go Sim] or [❌ No Go]
    3. If sim OK → bot sends result + [💰 Go Real] or [❌ Cancel]
    4. If Go Real → bot launches for real
==============================================================
"""

import os
import json
import requests
import logging
from datetime import datetime

from config.settings import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    NOTIFY_TELEGRAM,
    DEV_BUY_AMOUNT_SOL,
)

_last_update_id = 0


# ---------------------------------------------------------------
# Telegram API helpers
# ---------------------------------------------------------------

def _api(method, data=None, files=None):
    """Telegram Bot API call."""
    if not TELEGRAM_BOT_TOKEN:
        return None
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    try:
        if files:
            resp = requests.post(url, data=data or {}, files=files, timeout=15)
        else:
            resp = requests.post(url, json=data or {}, timeout=10)
        return resp.json()
    except Exception as e:
        logging.error(f"Telegram API error: {e}")
        return None


def send_message(text, parse_mode="Markdown", reply_markup=None):
    """Send text message."""
    if not NOTIFY_TELEGRAM or not TELEGRAM_CHAT_ID:
        return False
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    result = _api("sendMessage", payload)
    return result and result.get("ok")


def send_photo(image_path, caption, reply_markup=None):
    """Send a photo with caption and optional inline buttons."""
    if not NOTIFY_TELEGRAM or not TELEGRAM_CHAT_ID:
        return False

    if not image_path or not os.path.exists(image_path):
        return send_message(caption, reply_markup=reply_markup)

    try:
        data = {
            "chat_id": TELEGRAM_CHAT_ID,
            "caption": caption,
            "parse_mode": "Markdown",
        }
        if reply_markup:
            data["reply_markup"] = json.dumps(reply_markup)

        with open(image_path, "rb") as photo:
            result = _api("sendPhoto", data=data, files={"photo": photo})

        return result and result.get("ok")
    except Exception as e:
        logging.error(f"Send photo error: {e}")
        return send_message(caption, reply_markup=reply_markup)


# ---------------------------------------------------------------
# STEP 1: Full token card with image
# ---------------------------------------------------------------

def send_alert(story, image_path=None):
    """
    Send FULL TOKEN CARD:
    - Image (found online or generated)
    - Name, ticker, score, AI reasoning
    - Article link, dev buy, strategy
    - Buttons: [🧪 Go Sim] [❌ No Go]
    """
    if not NOTIFY_TELEGRAM:
        return

    score = story["score"]
    stars = "🟢" if score >= 70 else "🟡" if score >= 50 else "🔴"

    token_name = story.get("ai_name", "Unknown")
    ticker = story.get("ai_ticker", "???")
    reason = story.get("ai_reason", "keyword match")
    description = story.get("ai_description", "")

    caption = (
        f"{stars} *TREND DETECTED* — Score: {score}/100\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🪙 *{token_name}* (${ticker})\n"
        f"🤖 _{reason}_\n\n"
    )

    if description:
        caption += f"📝 *Description pump.fun:*\n_{description}_\n\n"

    caption += (
        f"📰 {story['source']}\n"
        f"🕐 {story['published']}\n"
        f"💰 Dev buy: *{DEV_BUY_AMOUNT_SOL} SOL*\n"
        f"📈 Auto-sell: *+70%*\n\n"
        f"🔗 [Article]({story.get('link', '')})\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👇 *Test en simulation d'abord?*"
    )

    keyboard = {
        "inline_keyboard": [
            [
                {"text": "🧪 Go Sim", "callback_data": f"sim|{story['id'][:50]}"},
                {"text": "❌ No Go", "callback_data": f"skip|{story['id'][:50]}"},
            ],
        ]
    }

    if image_path and os.path.exists(image_path):
        send_photo(image_path, caption, reply_markup=keyboard)
    else:
        send_message(caption, reply_markup=keyboard)


# ---------------------------------------------------------------
# STEP 2: Simulation result → confirm real launch
# ---------------------------------------------------------------

def send_sim_result(story, result):
    """
    After sim succeeds → show result + [💰 Go Real] [❌ Cancel]
    """
    if not result:
        send_message("❌ *Simulation failed.* Check logs.")
        return

    competition = story.get("competition", {}).get("reason", "OK")

    text = (
        f"✅ *SIMULATION OK*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🪙 *{result['name']}* (${result['ticker']})\n"
        f"💰 Dev buy: {result['dev_buy_sol']} SOL\n"
        f"📊 Score: {story['score']}/100\n\n"
        f"✅ Token creation: OK\n"
        f"✅ Name: OK\n"
        f"✅ Competition: {competition}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👇 *Lancer pour de vrai?*\n"
        f"⚠️ *{DEV_BUY_AMOUNT_SOL} SOL* seront dépensés"
    )

    keyboard = {
        "inline_keyboard": [
            [
                {"text": "💰 Go Real", "callback_data": f"real|{story['id'][:50]}"},
                {"text": "❌ Cancel", "callback_data": f"cancel|{story['id'][:50]}"},
            ],
        ]
    }

    send_message(text, reply_markup=keyboard)


# ---------------------------------------------------------------
# Launch result notification
# ---------------------------------------------------------------

def send_launch_result(token_info, result):
    """Notify on real launch."""
    if not result:
        send_message("❌ *Launch failed.* Check logs.")
        return

    if result.get("status") == "launched":
        text = (
            f"🚀 *LAUNCHED!*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🪙 *{result['name']}* (${result['ticker']})\n"
            f"💰 Spent: `{result['dev_buy_sol']} SOL`\n\n"
            f"📊 [pump.fun]({result.get('pump_url', '')})\n"
            f"🔍 [Solscan](https://solscan.io/token/{result.get('mint_address', '')})\n\n"
            f"⏳ _Price monitor actif_\n"
            f"📈 _Vente auto à +70% | Stop-loss à -40%_"
        )
    else:
        text = f"🧪 *Simulation* — {result['name']} (${result['ticker']})"

    send_message(text)


# ---------------------------------------------------------------
# Sell / stop-loss / daily notifications
# ---------------------------------------------------------------

def send_sell_alert(token_name, ticker, target_multiplier, sell_percent, sol_received):
    profit_pct = (target_multiplier - 1) * 100
    text = (
        f"💸 *VENDU — +{profit_pct:.0f}%*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🪙 *{token_name}* (${ticker})\n"
        f"Vendu: *{sell_percent}%*\n"
        f"Reçu: *{sol_received:.4f} SOL* 💰"
    )
    send_message(text)


def send_stop_loss_alert(token_name, ticker, loss_percent):
    text = (
        f"🛑 *STOP LOSS*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🪙 *{token_name}* (${ticker})\n"
        f"Baisse: *-{loss_percent:.0f}%*\n"
        f"Tout vendu."
    )
    send_message(text)


def send_daily_summary(stats):
    net = stats.get("sol_received", 0) - stats.get("sol_spent", 0)
    emoji = "📈" if net >= 0 else "📉"
    text = (
        f"📊 *RÉSUMÉ DU JOUR*\n"
        f"_{datetime.now().strftime('%Y-%m-%d')}_\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Stories: *{stats.get('stories_scanned', 0)}*\n"
        f"Alerts: *{stats.get('alerts', 0)}*\n"
        f"Lancés: *{stats.get('launched', 0)}*\n\n"
        f"Dépensé: *{stats.get('sol_spent', 0):.3f} SOL*\n"
        f"Reçu: *{stats.get('sol_received', 0):.3f} SOL*\n"
        f"{emoji} Net: *{net:+.3f} SOL*"
    )
    send_message(text)


def send_startup_message():
    from config.settings import RSS_FEEDS, SCAN_INTERVAL_MINUTES
    text = (
        f"🤖 *Trend Bot v3 Online*\n"
        f"_{datetime.now().strftime('%Y-%m-%d %H:%M UTC')}_\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📡 *{len(RSS_FEEDS)}* feeds\n"
        f"⏱ Scan: *{SCAN_INTERVAL_MINUTES} min*\n"
        f"🧠 AI: ✅\n"
        f"💰 Buy: *{DEV_BUY_AMOUNT_SOL} SOL*\n"
        f"📈 Sell: *+70%* | 🛑 Stop: *-40%*\n\n"
        f"`/status` `/tokens` `/pause` `/resume` `/summary`"
    )
    send_message(text)


# ---------------------------------------------------------------
# Poll for commands & button taps
# ---------------------------------------------------------------

def get_pending_commands():
    """Poll Telegram for updates. Returns list of command dicts."""
    global _last_update_id

    if not NOTIFY_TELEGRAM or not TELEGRAM_BOT_TOKEN:
        return []

    result = _api("getUpdates", {
        "offset": _last_update_id + 1,
        "timeout": 1,
        "limit": 10,
    })

    if not result or not result.get("ok"):
        return []

    commands = []
    for update in result.get("result", []):
        _last_update_id = update["update_id"]

        if "callback_query" in update:
            cb = update["callback_query"]
            data = cb.get("data", "")
            action, *rest = data.split("|")
            story_id = rest[0] if rest else ""
            _api("answerCallbackQuery", {"callback_query_id": cb["id"]})
            commands.append({
                "type": "callback",
                "action": action,   # sim, real, skip, cancel
                "story_id": story_id,
            })

        elif "message" in update:
            text = update["message"].get("text", "").strip()
            if text.startswith("/"):
                commands.append({
                    "type": "command",
                    "action": text.split()[0].lower(),
                })

    return commands
