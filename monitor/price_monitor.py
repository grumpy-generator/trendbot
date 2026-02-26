"""
==============================================================
  TREND BOT v3 — PRICE MONITOR
  Auto-sell at +70% (100% of position)
  Stop loss from BUY PRICE (not peak) — configurable
==============================================================
"""

import time
import math
import random
import logging
import threading
import requests
from datetime import datetime
from colorama import Fore

from config.settings import (
    SELL_STRATEGY, STOP_LOSS_PERCENT, STOP_LOSS_FROM_BUY_PRICE,
    DEV_BUY_AMOUNT_SOL, SOLANA_RPC_URL, WALLET_PRIVATE_KEY,
    NOTIFY_TELEGRAM,
)

PRICE_CHECK_INTERVAL = 10  # seconds


class PriceMonitor:
    def __init__(self):
        self.watched_tokens = {}
        self.lock = threading.Lock()
        self.running = False
        self.thread = None
        self.stats = {
            "launched": 0,
            "sol_spent": 0.0,
            "sol_received": 0.0,
        }

    def start(self):
        """Start background price monitoring."""
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        print(Fore.CYAN + "  💹 Price monitor started")

    def stop(self):
        self.running = False

    def add_token(self, launch_result):
        """Add a token to the watch list."""
        if not launch_result:
            return
        mint = launch_result.get("mint_address")
        if not mint:
            return

        with self.lock:
            self.watched_tokens[mint] = {
                "mint": mint,
                "name": launch_result.get("name", ""),
                "ticker": launch_result.get("ticker", ""),
                "launch_time": datetime.now(),
                "buy_price_sol": None,
                "peak_price_sol": None,
                "buy_amount_sol": DEV_BUY_AMOUNT_SOL,
                "remaining_percent": 100,
                "sells_executed": [],
                "status": "watching",
                "simulated": launch_result.get("status") == "simulated",
            }

        self.stats["launched"] += 1
        self.stats["sol_spent"] += DEV_BUY_AMOUNT_SOL
        print(Fore.GREEN + f"  👁  Watching: {launch_result.get('name')} (${launch_result.get('ticker')})")

    def get_active_positions(self):
        with self.lock:
            return list(self.watched_tokens.values())

    def _loop(self):
        """Main monitoring loop."""
        while self.running:
            try:
                with self.lock:
                    tokens = list(self.watched_tokens.items())

                for mint, pos in tokens:
                    if pos["status"] != "watching":
                        continue

                    price = self._get_price(mint, pos["simulated"])
                    if price is None:
                        continue

                    # Set initial buy price
                    if pos["buy_price_sol"] is None:
                        pos["buy_price_sol"] = price
                        pos["peak_price_sol"] = price
                        continue

                    # Track peak
                    if price > pos["peak_price_sol"]:
                        pos["peak_price_sol"] = price

                    buy = pos["buy_price_sol"]
                    mult = price / buy if buy > 0 else 1.0

                    # --- CHECK SELL TARGETS ---
                    for target in SELL_STRATEGY:
                        tgt_mult = target["target_multiplier"]
                        sell_pct = target["sell_percent"]

                        if tgt_mult in [s["target"] for s in pos["sells_executed"]]:
                            continue

                        if mult >= tgt_mult and pos["remaining_percent"] > 0:
                            sol = self._execute_sell(mint, pos, sell_pct, price)
                            pos["sells_executed"].append({
                                "target": tgt_mult,
                                "sell_percent": sell_pct,
                                "price": price,
                                "sol_received": sol,
                                "time": datetime.now().isoformat(),
                            })
                            pos["remaining_percent"] -= sell_pct
                            self.stats["sol_received"] += sol

                            print(Fore.GREEN + f"  💸 SELL: {pos['name']} at {tgt_mult}x → {sol:.4f} SOL")

                            if NOTIFY_TELEGRAM:
                                try:
                                    from telegram.bot import send_sell_alert
                                    send_sell_alert(pos['name'], pos['ticker'], tgt_mult, sell_pct, sol)
                                except Exception as e:
                                    logging.error(f"Telegram sell alert error: {e}")

                            if pos["remaining_percent"] <= 0:
                                pos["status"] = "completed"
                                break

                    # --- CHECK STOP LOSS ---
                    if pos["status"] == "watching" and pos["remaining_percent"] > 0:
                        if STOP_LOSS_FROM_BUY_PRICE:
                            # Stop loss vs buy price
                            drop = (buy - price) / buy if buy > 0 else 0
                        else:
                            # Stop loss vs peak
                            peak = pos["peak_price_sol"]
                            drop = (peak - price) / peak if peak and peak > 0 else 0

                        if drop >= STOP_LOSS_PERCENT:
                            sol = self._execute_sell(mint, pos, pos["remaining_percent"], price)
                            pos["status"] = "stopped"
                            self.stats["sol_received"] += sol
                            print(Fore.RED + f"  🛑 STOP LOSS: {pos['name']} — {drop:.0%} drop")

                            if NOTIFY_TELEGRAM:
                                try:
                                    from telegram.bot import send_stop_loss_alert
                                    send_stop_loss_alert(pos['name'], pos['ticker'], drop * 100)
                                except Exception as e:
                                    logging.error(f"Telegram stop loss alert error: {e}")

            except Exception as e:
                logging.error(f"Price monitor error: {e}")

            time.sleep(PRICE_CHECK_INTERVAL)

    def _get_price(self, mint, simulated=False):
        """Get current token price in SOL."""
        if simulated:
            return self._sim_price(mint)

        try:
            resp = requests.get(
                f"https://frontend-api.pump.fun/coins/{mint}",
                timeout=5,
            )
            if resp.status_code == 200:
                data = resp.json()
                sol_res = data.get("virtual_sol_reserves", 0)
                tok_res = data.get("virtual_token_reserves", 1)
                return sol_res / tok_res if tok_res > 0 else None
        except Exception as e:
            logging.debug(f"Price fetch error: {e}")
        return None

    def _sim_price(self, mint):
        """Simulate realistic price curve for testing."""
        seed = sum(ord(c) for c in mint[:10])
        random.seed(seed + int(time.time() / 10))

        t = (time.time() % 300) / 300
        peak_t = 0.5 + (seed % 10) / 20
        max_mult = 2 + (seed % 30) / 10

        if t < peak_t:
            price = 0.001 * (1 + (max_mult - 1) * (t / peak_t))
        else:
            price = 0.001 * max_mult * (1 - 0.8 * ((t - peak_t) / (1 - peak_t)))

        return max(0.0001, price + random.uniform(-0.00005, 0.00005))

    def _execute_sell(self, mint, pos, sell_pct, price):
        """Execute sell. Returns SOL received."""
        if pos["simulated"]:
            tokens = (pos["buy_amount_sol"] / pos["buy_price_sol"]) if pos["buy_price_sol"] else 0
            to_sell = tokens * (sell_pct / 100)
            sol = to_sell * price * 0.99
            logging.info(f"SIM SELL: {pos['name']} {sell_pct}% = {sol:.4f} SOL")
            return sol

        try:
            import base58, base64
            from solana.rpc.api import Client
            from solders.keypair import Keypair
            from solders.transaction import VersionedTransaction

            client = Client(SOLANA_RPC_URL)
            wallet = Keypair.from_bytes(base58.b58decode(WALLET_PRIVATE_KEY))

            resp = requests.post(
                "https://pumpportal.fun/api/trade-local",
                headers={"Content-Type": "application/json"},
                json={
                    "publicKey": str(wallet.pubkey()),
                    "action": "sell",
                    "mint": mint,
                    "denominatedInSol": "false",
                    "amount": f"{sell_pct}%",
                    "slippage": 15,
                    "priorityFee": 0.0005,
                    "pool": "pump",
                },
                timeout=15,
            )

            if resp.status_code == 200:
                tx = VersionedTransaction.from_bytes(base64.b64decode(resp.content))
                tx.sign([wallet])
                sig = client.send_raw_transaction(bytes(tx)).value
                logging.info(f"SELL TX: {pos['name']} {sell_pct}% — {sig}")

                tokens = (pos["buy_amount_sol"] / pos["buy_price_sol"]) if pos["buy_price_sol"] else 0
                return (tokens * (sell_pct / 100)) * price * 0.97
            else:
                logging.error(f"Sell failed: {resp.status_code}")
                return 0.0

        except Exception as e:
            logging.error(f"Sell error: {e}")
            return 0.0

    def print_positions(self):
        """Print positions to terminal."""
        positions = self.get_active_positions()
        if not positions:
            print(Fore.YELLOW + "  No active positions.")
            return

        print(Fore.CYAN + f"\n  📊 Active Positions ({len(positions)}):")
        for p in positions:
            icon = "👁" if p["status"] == "watching" else "✅" if p["status"] == "completed" else "🛑"
            sim = " [SIM]" if p["simulated"] else ""
            print(f"  {icon} {p['name']} (${p['ticker']}){sim}")
            print(f"     Remaining: {p['remaining_percent']}% | Sells: {len(p['sells_executed'])}")
