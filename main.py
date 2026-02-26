"""
==============================================================
  TREND BOT v3 — MAIN
  python main.py              → Interactive menu
  python main.py --daemon     → Background (VPS/systemd)
  python main.py --scan-once  → Single scan, exit
  python main.py --status     → Print status JSON, exit
  python main.py --health     → Check feed health, exit
==============================================================
"""

import sys
import os
import time
import json
import logging
import argparse
import schedule
from datetime import datetime
from colorama import Fore, init

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scanner.news_scanner import (
    run_scan, is_active_hours, print_story_summary,
    format_alert, check_feed_health,
)
from scanner.duplicate_checker import (
    search_existing_tokens, evaluate_competition, format_competition_report,
)
from scanner.image_finder import find_token_image
from launcher.pump_launcher import TokenLauncher, check_wallet_ready, generate_token_name
from monitor.price_monitor import PriceMonitor
from telegram.bot import (
    send_message, send_alert, send_sim_result, send_launch_result,
    send_startup_message, send_daily_summary, get_pending_commands,
)
from config.settings import (
    SCAN_INTERVAL_MINUTES,
    MIN_SCORE_TO_ALERT,
    NOTIFY_TELEGRAM,
    DEV_BUY_AMOUNT_SOL,
    USE_AI_SCORING,
    ANTHROPIC_API_KEY,
    WALLET_PRIVATE_KEY,
    SOLANA_RPC_URL,
    MAX_LAUNCHES_PER_HOUR,
    MAX_DAILY_SOL_SPEND,
)

init(autoreset=True)
os.makedirs("logs", exist_ok=True)
os.makedirs("images", exist_ok=True)

logging.basicConfig(
    filename="logs/bot.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

# ---------------------------------------------------------------
# Global state
# ---------------------------------------------------------------
launcher = TokenLauncher()
price_monitor = PriceMonitor()
is_paused = False
daily_stats = {
    "stories_scanned": 0,
    "alerts": 0,
    "launched": 0,
    "sol_spent": 0.0,
    "sol_received": 0.0,
    "date": datetime.now().strftime("%Y-%m-%d"),
}

# Pending stories keyed by story_id (waiting for user decision)
pending_stories = {}

# Simulated results waiting for Step 2 confirmation
pending_sim_results = {}  # story_id → (story, result)


def print_banner():
    print(Fore.CYAN + """
╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║   🐸  TREND TOKEN BOT  v3                                ║
║                                                           ║
║   AI Scoring → Image Search → Telegram Card              ║
║   → You Say Go → Sim First → Confirm → Launch            ║
║   → Auto Sell at +70%                                    ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
    """)


def print_config_status():
    print(Fore.WHITE + "  ── Configuration ──")
    if WALLET_PRIVATE_KEY:
        print(Fore.GREEN + "  ✅ Wallet configured")
    else:
        print(Fore.YELLOW + "  ⚠️  No wallet (set in .env)")

    if ANTHROPIC_API_KEY:
        print(Fore.GREEN + "  ✅ AI scoring ON")
    else:
        print(Fore.YELLOW + "  ⚠️  No AI key → keyword fallback")

    if NOTIFY_TELEGRAM:
        print(Fore.GREEN + "  ✅ Telegram ON")
    else:
        print(Fore.YELLOW + "  ⚠️  Telegram OFF")

    if "devnet" in SOLANA_RPC_URL:
        print(Fore.YELLOW + "  🧪 Network: DEVNET")
    else:
        print(Fore.GREEN + "  💰 Network: MAINNET")

    print(Fore.WHITE + f"  💰 Dev buy: {DEV_BUY_AMOUNT_SOL} SOL")
    print(Fore.WHITE + f"  📈 Auto-sell: +70% | Stop-loss: -40%")
    print(Fore.WHITE + f"  🔒 Max: {MAX_LAUNCHES_PER_HOUR}/h, {MAX_DAILY_SOL_SPEND} SOL/day")
    print()


def print_menu():
    print(Fore.WHITE + """
┌─────────────────────────────────────────────────────────┐
│  MENU                                                   │
│                                                         │
│  [1] Start bot (continuous scan + Telegram)             │
│  [2] Single scan now                                    │
│  [3] Dry run (zero risk test)                           │
│  [4] Check wallet                                       │
│  [5] Active positions                                   │
│  [6] Launch history                                     │
│  [7] Test Telegram                                      │
│  [8] Feed health check                                  │
│  [q] Quit                                               │
│                                                         │
└─────────────────────────────────────────────────────────┘
    """)


# ---------------------------------------------------------------
# Core scan cycle
# ---------------------------------------------------------------

def run_scan_cycle():
    """Full cycle: scan → AI score → find image → dedup → send card to Telegram."""
    global is_paused, daily_stats

    if is_paused:
        print(Fore.YELLOW + "\n  ⏸  Paused.")
        return

    if os.path.exists(".pause"):
        print(Fore.YELLOW + "\n  ⏸  Paused (.pause file).")
        return

    if not is_active_hours():
        print(Fore.YELLOW + "\n  😴 Outside active hours")
        return

    # Reset daily stats on new day
    today = datetime.now().strftime("%Y-%m-%d")
    if daily_stats["date"] != today:
        daily_stats = {
            "stories_scanned": 0, "alerts": 0, "launched": 0,
            "sol_spent": 0.0, "sol_received": 0.0, "date": today,
        }

    # 1. Scan all feeds (async parallel + AI scoring)
    alerts = run_scan()
    daily_stats["stories_scanned"] += len(alerts)  # alerts count (filtered above threshold)

    if not alerts:
        print(Fore.YELLOW + f"  No stories above threshold (≥{MIN_SCORE_TO_ALERT})")
        return

    print_story_summary(alerts)

    # 2. Process each alert
    for story in alerts:
        # Competition check
        keywords = story.get("keywords", [])
        if story.get("ai_ticker"):
            keywords = [story["ai_ticker"]] + keywords

        existing = search_existing_tokens(keywords, story["title"])
        evaluation = evaluate_competition(existing)
        print(format_competition_report(story, evaluation))

        story["competition"] = evaluation

        # Skip if too much competition
        if not evaluation["should_launch"]:
            print(Fore.RED + f"  ⚠️  Skipping: {evaluation['reason']}")
            continue

        # 3. Find/generate token image
        print(Fore.CYAN + f"  🖼  Searching image for '{story.get('ai_name', story['title'][:30])}'...")
        image_path = find_token_image(
            story_title=story["title"],
            ticker=story.get("ai_ticker", "TOKEN"),
            name=story.get("ai_name", ""),
            visual_hint=story.get("ai_visual", ""),
            keywords=story.get("keywords", []),
        )
        if image_path:
            print(Fore.GREEN + f"  ✅ Image: {image_path}")
            story["image_path"] = image_path
        else:
            print(Fore.YELLOW + f"  ⚠️  No image found")
            story["image_path"] = None

        # Store as pending
        pending_stories[story["id"]] = story
        daily_stats["alerts"] += 1

        # 4. Send card to Telegram (or handle in terminal)
        if NOTIFY_TELEGRAM:
            send_alert(story, image_path=story.get("image_path"))
        else:
            handle_alert_terminal(story, evaluation)


def handle_alert_terminal(story, evaluation):
    """Terminal mode: print alert and ask for action."""
    print(format_alert(story))
    print(Fore.GREEN + f"  ✅ {evaluation['reason']}")
    print("\n  [l] Sim   [L] REAL   [s] Skip")
    choice = input("  → ").strip()

    if choice == "l":
        result = do_launch(story, dry_run=True)
        if result:
            print(Fore.YELLOW + "\n  Launch REAL? [y/n]")
            if input("  → ").strip().lower() == "y":
                do_launch(story, dry_run=False)
    elif choice == "L":
        confirm = input(Fore.RED + f"  ⚠️  Spend {DEV_BUY_AMOUNT_SOL} SOL? (yes): ")
        if confirm.lower() == "yes":
            do_launch(story, dry_run=False)


def do_launch(story, dry_run=True):
    """Execute launch (sim or real)."""
    global daily_stats

    # Build complete token info from AI-generated card
    if story.get("ai_ticker") and story.get("ai_name"):
        token_info = {
            "name": story["ai_name"],
            "ticker": story["ai_ticker"],
            "description": story.get("ai_description", "")
                          or story.get("ai_reason", story["title"][:100]),
            "image_path": story.get("image_path"),
        }
    else:
        token_info = generate_token_name(story)
        token_info["image_path"] = story.get("image_path")

    result = launcher.launch_token(story, token_info, dry_run=dry_run)

    if result:
        price_monitor.add_token(result)
        if not dry_run:
            daily_stats["launched"] += 1
            daily_stats["sol_spent"] += DEV_BUY_AMOUNT_SOL
            if NOTIFY_TELEGRAM:
                send_launch_result(token_info, result)

    return result


# ---------------------------------------------------------------
# Telegram command processing (with double confirmation)
# ---------------------------------------------------------------

def process_telegram_commands():
    """Process Telegram button taps and commands."""
    global is_paused

    commands = get_pending_commands()
    for cmd in commands:
        action = cmd.get("action", "")

        if cmd["type"] == "callback":
            story_id = cmd.get("story_id", "")

            # Find matching story
            story = None
            for sid, s in pending_stories.items():
                if sid[:50] == story_id:
                    story = s
                    break

            # ── STEP 1: User taps [Go Sim] ──
            if action == "sim" and story:
                send_message(f"🧪 Simulation en cours: *{story.get('ai_name', story['title'][:40])}*...")
                result = do_launch(story, dry_run=True)
                if result:
                    # Store sim result and ask for Step 2 confirmation
                    pending_sim_results[story_id] = (story, result)
                    send_sim_result(story, result)
                else:
                    send_message("❌ Simulation échouée. Check les logs.")

            # ── STEP 2: User confirms [Go Real] ──
            elif action == "real":
                sim_data = pending_sim_results.get(story_id)
                if sim_data:
                    story, _ = sim_data
                    send_message(f"💰 Lancement RÉEL: *{story.get('ai_name', '')}*\n"
                                 f"Dépense: *{DEV_BUY_AMOUNT_SOL} SOL*...")
                    result = do_launch(story, dry_run=False)
                    if result:
                        send_launch_result(None, result)
                    else:
                        send_message("❌ Lancement échoué. Check les logs.")
                    # Clean up
                    pending_sim_results.pop(story_id, None)
                elif story:
                    # Direct real launch (shouldn't happen in normal flow)
                    send_message(f"💰 Lancement: *{story.get('ai_name', '')}*...")
                    result = do_launch(story, dry_run=False)
                    if result:
                        send_launch_result(None, result)

            # ── No Go / Cancel ──
            elif action in ("skip", "cancel"):
                pending_sim_results.pop(story_id, None)
                send_message("⏭ Annulé.")

        elif cmd["type"] == "command":
            if action == "/status":
                _send_status()
            elif action == "/tokens":
                _send_positions()
            elif action == "/pause":
                is_paused = True
                send_message("⏸ Bot en pause.")
            elif action == "/resume":
                is_paused = False
                send_message("▶️ Bot relancé.")
            elif action == "/stop":
                send_message("🛑 Arrêt...")
                price_monitor.stop()
                sys.exit(0)
            elif action == "/summary":
                send_daily_summary(daily_stats)


def _send_status():
    wallet_ok, wallet_info = check_wallet_ready()
    w = f"✅ {wallet_info:.4f} SOL" if wallet_ok else f"❌ {wallet_info}"
    positions = price_monitor.get_active_positions()
    net = daily_stats["sol_received"] - daily_stats["sol_spent"]
    text = (
        f"🤖 *Status*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{'✅ Running' if not is_paused else '⏸ Paused'}\n"
        f"Wallet: {w}\n"
        f"Positions: {len(positions)}\n"
        f"Lancés: {daily_stats['launched']}\n"
        f"Net: {net:+.3f} SOL"
    )
    send_message(text)


def _send_positions():
    positions = price_monitor.get_active_positions()
    if not positions:
        send_message("📊 Aucune position active.")
        return
    text = f"📊 *Positions ({len(positions)})*\n\n"
    for p in positions:
        sim = " [SIM]" if p["simulated"] else ""
        text += f"• *{p['name']}* (${p['ticker']}){sim}\n"
        text += f"  Reste: {p['remaining_percent']}% | Ventes: {len(p['sells_executed'])}\n\n"
    send_message(text)


# ---------------------------------------------------------------
# Bot modes
# ---------------------------------------------------------------

def start_bot_continuous():
    """Continuous scanning loop."""
    print(Fore.GREEN + f"\n  🤖 Bot started! Scan every {SCAN_INTERVAL_MINUTES} min.")
    print(Fore.WHITE + "  Ctrl+C to stop.\n")

    price_monitor.start()

    if NOTIFY_TELEGRAM:
        send_startup_message()

    wallet_ok, wallet_info = check_wallet_ready()
    if wallet_ok:
        print(Fore.GREEN + f"  ✅ Wallet: {wallet_info:.4f} SOL")
    else:
        print(Fore.YELLOW + f"  ⚠️  {wallet_info}")

    run_scan_cycle()
    schedule.every(SCAN_INTERVAL_MINUTES).minutes.do(run_scan_cycle)
    schedule.every().day.at("23:55").do(lambda: send_daily_summary(daily_stats))

    try:
        while True:
            schedule.run_pending()
            if NOTIFY_TELEGRAM:
                process_telegram_commands()
            time.sleep(5)
    except KeyboardInterrupt:
        print(Fore.YELLOW + "\n\n  Bot stopped.")
        price_monitor.stop()
        if NOTIFY_TELEGRAM:
            send_message("🛑 Bot arrêté.")


def start_daemon():
    logging.info("Daemon mode")
    start_bot_continuous()


def run_once():
    alerts = run_scan()
    for story in alerts:
        keywords = story.get("keywords", [])
        existing = search_existing_tokens(keywords, story["title"])
        evaluation = evaluate_competition(existing)
        print(f"ALERT|{story['score']}|{story['title']}|{evaluation['reason']}")
    sys.exit(0)


def print_status():
    wallet_ok, wallet_info = check_wallet_ready()
    positions = price_monitor.get_active_positions()
    print(json.dumps({
        "wallet_ok": wallet_ok,
        "wallet_info": str(wallet_info),
        "active_positions": len(positions),
        "daily_stats": daily_stats,
        "paused": is_paused,
    }, indent=2))
    sys.exit(0)


def view_launch_history():
    log_file = "logs/launches.json"
    if not os.path.exists(log_file):
        print(Fore.YELLOW + "\n  No launches yet.")
        return
    with open(log_file) as f:
        launches = json.load(f)
    if not launches:
        print(Fore.YELLOW + "\n  No launches yet.")
        return
    print(Fore.CYAN + f"\n  📋 History ({len(launches)} total):\n")
    for launch in launches[-10:]:
        color = Fore.GREEN if launch["status"] == "launched" else Fore.YELLOW
        print(color + f"  • {launch['name']} (${launch['ticker']}) — {launch['status']}")
        print(Fore.WHITE + f"    {launch['story_title'][:60]}")
        if "pump_url" in launch:
            print(f"    {launch['pump_url']}")
        print()


# ---------------------------------------------------------------
# Interactive menu
# ---------------------------------------------------------------

def interactive_menu():
    print_banner()
    print_config_status()

    while True:
        print_menu()
        choice = input("  → ").strip().lower()

        if choice == "1":
            start_bot_continuous()
        elif choice == "2":
            run_scan_cycle()
            input(Fore.WHITE + "\n  Enter...")
        elif choice == "3":
            print(Fore.CYAN + "\n  Dry run test...")
            alerts = run_scan()
            if alerts:
                story = alerts[0]
                # Find image for demo
                image_path = find_token_image(
                    story["title"],
                    story.get("ai_ticker", "TEST"),
                    story.get("ai_name", ""),
                    story.get("ai_visual", ""),
                    story.get("keywords", []),
                )
                if image_path:
                    print(Fore.GREEN + f"  🖼  Image: {image_path}")
                do_launch(story, dry_run=True)
            else:
                fake = {
                    "id": "demo-001",
                    "title": "Giant Inflatable Frog at White House Rally",
                    "summary": "A massive frog costume appeared",
                    "source": "Demo",
                    "score": 82,
                    "keywords": ["frog", "protest"],
                    "ai_ticker": "FROGGY",
                    "ai_name": "Rally Frog",
                    "ai_reason": "Absurd visual + political = meme energy",
                    "ai_visual": "inflatable green frog mascot",
                    "published": datetime.now().strftime("%Y-%m-%d %H:%M UTC"),
                    "link": "https://example.com",
                    "competition": {"should_launch": True, "reason": "No tokens found"},
                }
                print(Fore.YELLOW + "\n  No live alerts — demo:")
                image_path = find_token_image(
                    fake["title"], "FROGGY", "Rally Frog", "green frog mascot", ["frog"]
                )
                if image_path:
                    print(Fore.GREEN + f"  🖼  Image: {image_path}")
                do_launch(fake, dry_run=True)
            input(Fore.WHITE + "\n  Enter...")
        elif choice == "4":
            ok, info = check_wallet_ready()
            print((Fore.GREEN + f"\n  ✅ {info:.4f} SOL") if ok else (Fore.RED + f"\n  {info}"))
            input(Fore.WHITE + "\n  Enter...")
        elif choice == "5":
            price_monitor.print_positions()
            input(Fore.WHITE + "\n  Enter...")
        elif choice == "6":
            view_launch_history()
            input(Fore.WHITE + "\n  Enter...")
        elif choice == "7":
            if NOTIFY_TELEGRAM:
                ok = send_message("🧪 Test Trend Bot v3 ✅")
                print(Fore.GREEN + "  ✅ Sent!" if ok else Fore.RED + "  ❌ Failed.")
            else:
                print(Fore.YELLOW + "  Telegram OFF (set in .env)")
            input(Fore.WHITE + "\n  Enter...")
        elif choice == "8":
            run_scan()
            check_feed_health()
            input(Fore.WHITE + "\n  Enter...")
        elif choice == "q":
            print(Fore.YELLOW + "\n  Bye! 🐸\n")
            sys.exit(0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Trend Token Bot v3")
    parser.add_argument("--daemon", action="store_true")
    parser.add_argument("--scan-once", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--health", action="store_true")
    args = parser.parse_args()

    if args.daemon:
        start_daemon()
    elif args.scan_once:
        run_once()
    elif args.status:
        print_status()
    elif args.health:
        run_scan()
        check_feed_health()
    else:
        interactive_menu()
