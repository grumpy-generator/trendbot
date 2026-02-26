"""
==============================================================
  TREND BOT v3 — TELEGRAM TEST SUITE
  Tests ALL Telegram alert types with sample data.

  Usage:
    python test_telegram.py              → Interactive menu
    python test_telegram.py --all        → Send all test messages
    python test_telegram.py --alert      → Test trend alert card
    python test_telegram.py --sim        → Test simulation result
    python test_telegram.py --launch     → Test launch notification
    python test_telegram.py --sell       → Test sell alert
    python test_telegram.py --stoploss   → Test stop-loss alert
    python test_telegram.py --summary    → Test daily summary
    python test_telegram.py --startup    → Test startup message
    python test_telegram.py --status     → Test status message
==============================================================
"""

import sys
import os
import argparse
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.settings import NOTIFY_TELEGRAM, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from datetime import datetime


def check_telegram_config():
    """Verify Telegram is configured."""
    if not TELEGRAM_BOT_TOKEN:
        print("  ERROR: TELEGRAM_BOT_TOKEN not set in .env")
        return False
    if not TELEGRAM_CHAT_ID:
        print("  ERROR: TELEGRAM_CHAT_ID not set in .env")
        return False
    if not NOTIFY_TELEGRAM:
        print("  ERROR: NOTIFY_TELEGRAM is False (check .env)")
        return False
    print(f"  Telegram configured: bot token ends ...{TELEGRAM_BOT_TOKEN[-6:]}")
    print(f"  Chat ID: {TELEGRAM_CHAT_ID}")
    return True


# ---------------------------------------------------------------
# Sample data for testing
# ---------------------------------------------------------------

SAMPLE_STORY = {
    "id": "test-story-001-abcdef1234567890abcdef1234567890abcdef1234567890",
    "title": "Giant Inflatable Frog Appears at White House Rally, Goes Viral",
    "summary": "A massive inflatable frog mascot surprised attendees at a political rally today, becoming an instant meme across social media platforms.",
    "source": "Reuters Top News",
    "score": 82,
    "keywords": ["frog", "protest", "white house", "viral"],
    "ai_name": "Rally Frog",
    "ai_ticker": "RFROG",
    "ai_reason": "Absurd visual + political context = peak meme energy. Instant virality.",
    "ai_description": "The frog that crashed the White House. Rally Frog season is here. LFG! 🐸",
    "ai_visual": "giant green inflatable frog mascot at political rally",
    "published": datetime.now().strftime("%Y-%m-%d %H:%M UTC"),
    "link": "https://example.com/frog-rally",
    "image_path": None,
    "competition": {
        "should_launch": True,
        "confidence": "HIGH",
        "reason": "No existing tokens — you'd be FIRST 🥇",
    },
}

SAMPLE_SIM_RESULT = {
    "mint_address": "SIM1234567890123456789012345678901234567890pump",
    "name": "Rally Frog",
    "ticker": "RFROG",
    "story_title": "Giant Inflatable Frog Appears at White House Rally",
    "story_score": 82,
    "launch_time": datetime.now().isoformat(),
    "dev_buy_sol": 0.1,
    "status": "simulated",
    "sell_strategy": [{"target_multiplier": 1.7, "sell_percent": 100}],
}

SAMPLE_LAUNCH_RESULT = {
    "mint_address": "FroG1234567890123456789012345678901234567890pump",
    "name": "Rally Frog",
    "ticker": "RFROG",
    "story_title": "Giant Inflatable Frog Appears at White House Rally",
    "story_score": 82,
    "launch_time": datetime.now().isoformat(),
    "dev_buy_sol": 0.1,
    "signature": "5abc123def456...",
    "status": "launched",
    "sell_strategy": [{"target_multiplier": 1.7, "sell_percent": 100}],
    "pump_url": "https://pump.fun/coin/FroG1234567890123456789012345678901234567890pump",
}

SAMPLE_DAILY_STATS = {
    "stories_scanned": 47,
    "alerts": 5,
    "launched": 2,
    "sol_spent": 0.2,
    "sol_received": 0.34,
    "date": datetime.now().strftime("%Y-%m-%d"),
}


# ---------------------------------------------------------------
# Test functions
# ---------------------------------------------------------------

def test_simple_message():
    """Test 1: Basic connectivity."""
    from telegram.bot import send_message
    print("\n  [1/8] Sending simple test message...")
    ok = send_message("🧪 *Trend Bot v3 — Telegram Test*\n\nIf you see this, Telegram is working! ✅")
    print(f"  {'SUCCESS' if ok else 'FAILED'}")
    return ok


def test_trend_alert():
    """Test 2: Full trend alert card (Step 1 of the flow)."""
    from telegram.bot import send_alert
    print("\n  [2/8] Sending trend alert card (with buttons)...")
    send_alert(SAMPLE_STORY, image_path=None)
    print("  SENT — Check Telegram for [Go Sim] and [No Go] buttons")
    return True


def test_sim_result():
    """Test 3: Simulation result (Step 2 of the flow)."""
    from telegram.bot import send_sim_result
    print("\n  [3/8] Sending simulation result (with Go Real button)...")
    send_sim_result(SAMPLE_STORY, SAMPLE_SIM_RESULT)
    print("  SENT — Check Telegram for [Go Real] and [Cancel] buttons")
    return True


def test_launch_result():
    """Test 4: Real launch notification."""
    from telegram.bot import send_launch_result
    print("\n  [4/8] Sending launch result notification...")
    send_launch_result(None, SAMPLE_LAUNCH_RESULT)
    print("  SENT — Check Telegram for pump.fun and Solscan links")
    return True


def test_sell_alert():
    """Test 5: Sell alert (+70%)."""
    from telegram.bot import send_sell_alert
    print("\n  [5/8] Sending sell alert (+70%)...")
    send_sell_alert("Rally Frog", "RFROG", 1.7, 100, 0.17)
    print("  SENT")
    return True


def test_stop_loss_alert():
    """Test 6: Stop-loss alert."""
    from telegram.bot import send_stop_loss_alert
    print("\n  [6/8] Sending stop-loss alert (-40%)...")
    send_stop_loss_alert("Rally Frog", "RFROG", 40)
    print("  SENT")
    return True


def test_daily_summary():
    """Test 7: Daily summary."""
    from telegram.bot import send_daily_summary
    print("\n  [7/8] Sending daily summary...")
    send_daily_summary(SAMPLE_DAILY_STATS)
    print("  SENT")
    return True


def test_startup_message():
    """Test 8: Startup message."""
    from telegram.bot import send_startup_message
    print("\n  [8/8] Sending startup message...")
    send_startup_message()
    print("  SENT")
    return True


ALL_TESTS = [
    ("Simple message",    test_simple_message),
    ("Trend alert card",  test_trend_alert),
    ("Simulation result", test_sim_result),
    ("Launch result",     test_launch_result),
    ("Sell alert (+70%)", test_sell_alert),
    ("Stop-loss (-40%)",  test_stop_loss_alert),
    ("Daily summary",     test_daily_summary),
    ("Startup message",   test_startup_message),
]


def run_all_tests():
    """Run all tests with a delay between each."""
    print("\n  Running ALL Telegram tests...\n")
    passed = 0
    for name, func in ALL_TESTS:
        try:
            result = func()
            if result:
                passed += 1
            time.sleep(1)  # Avoid Telegram rate limiting
        except Exception as e:
            print(f"  ERROR in '{name}': {e}")

    print(f"\n  ━━━━━━━━━━━━━━━━━━━━━━")
    print(f"  Results: {passed}/{len(ALL_TESTS)} passed")
    print(f"  Check your Telegram for all messages!")


def interactive_menu():
    """Interactive test menu."""
    print("""
╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║   🧪  TELEGRAM TEST SUITE — Trend Bot v3                 ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
    """)

    if not check_telegram_config():
        print("\n  Fix your .env file and try again.")
        sys.exit(1)

    while True:
        print("""
┌─────────────────────────────────────────────────────────┐
│  TEST MENU                                              │
│                                                         │
│  [1] Simple message (connectivity test)                 │
│  [2] Trend alert card (with Go Sim / No Go buttons)    │
│  [3] Simulation result (with Go Real / Cancel buttons)  │
│  [4] Launch result (pump.fun + Solscan links)           │
│  [5] Sell alert (+70% profit)                           │
│  [6] Stop-loss alert (-40% loss)                        │
│  [7] Daily summary (P&L report)                         │
│  [8] Startup message                                    │
│  [a] Run ALL tests                                      │
│  [q] Quit                                               │
│                                                         │
└─────────────────────────────────────────────────────────┘
        """)
        choice = input("  → ").strip().lower()

        if choice == "q":
            print("\n  Done! 🐸\n")
            break
        elif choice == "a":
            run_all_tests()
        elif choice in ("1", "2", "3", "4", "5", "6", "7", "8"):
            idx = int(choice) - 1
            name, func = ALL_TESTS[idx]
            try:
                func()
            except Exception as e:
                print(f"  ERROR: {e}")
        else:
            print("  Invalid choice.")

        input("\n  Press Enter to continue...")


if __name__ == "__main__":
    os.makedirs("logs", exist_ok=True)

    parser = argparse.ArgumentParser(description="Telegram Test Suite for Trend Bot v3")
    parser.add_argument("--all", action="store_true", help="Run all tests")
    parser.add_argument("--alert", action="store_true", help="Test trend alert card")
    parser.add_argument("--sim", action="store_true", help="Test simulation result")
    parser.add_argument("--launch", action="store_true", help="Test launch notification")
    parser.add_argument("--sell", action="store_true", help="Test sell alert")
    parser.add_argument("--stoploss", action="store_true", help="Test stop-loss alert")
    parser.add_argument("--summary", action="store_true", help="Test daily summary")
    parser.add_argument("--startup", action="store_true", help="Test startup message")
    parser.add_argument("--status", action="store_true", help="Test simple message")
    args = parser.parse_args()

    any_flag = any([args.all, args.alert, args.sim, args.launch,
                    args.sell, args.stoploss, args.summary, args.startup, args.status])

    if not any_flag:
        interactive_menu()
    else:
        print("\n  🧪 Telegram Test Suite — Trend Bot v3\n")
        if not check_telegram_config():
            sys.exit(1)

        if args.all:
            run_all_tests()
        else:
            if args.status:
                test_simple_message()
            if args.alert:
                test_trend_alert()
            if args.sim:
                test_sim_result()
            if args.launch:
                test_launch_result()
            if args.sell:
                test_sell_alert()
            if args.stoploss:
                test_stop_loss_alert()
            if args.summary:
                test_daily_summary()
            if args.startup:
                test_startup_message()
