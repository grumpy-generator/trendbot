"""
==============================================================
  TREND BOT v3 — PUMP.FUN LAUNCHER
  Token creation with AI naming + safety limits
==============================================================
"""

import os
import time
import json
import random
import logging
from datetime import datetime, timedelta
from collections import deque
from colorama import Fore

from config.settings import (
    WALLET_PRIVATE_KEY, DEV_BUY_AMOUNT_SOL, SELL_STRATEGY,
    SOLANA_RPC_URL, PUMP_FUN_PROGRAM_ID,
    MAX_LAUNCHES_PER_HOUR, MAX_DAILY_SOL_SPEND,
    CREATOR_FEE_PERCENT,
)
from scanner.ai_scorer import generate_token_name_ai, ai_available


# ---------------------------------------------------------------
# Token name generator (fallback if AI unavailable)
# ---------------------------------------------------------------

_SKIP_WORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to",
    "for", "of", "with", "by", "from", "is", "are", "was", "were",
    "will", "be", "been", "have", "has", "had", "do", "does", "did",
    "not", "that", "this", "it", "he", "she", "they", "we", "you",
    "i", "my", "your", "his", "her", "its", "our", "their", "says",
    "said", "new", "after", "over", "about", "into", "could",
}


def generate_token_name_fallback(story_title):
    """Basic name generation from title words."""
    words = story_title.split()
    interesting = [
        w.strip(".,!?\"'()[]{}").upper()
        for w in words
        if w.lower().strip(".,!?\"'()[]{}") not in _SKIP_WORDS and len(w) > 2
    ]
    if not interesting:
        interesting = [w.upper() for w in words[:3]]

    ticker = interesting[0][:6] if interesting else "TREND"
    name = " ".join(w.capitalize() for w in interesting[:3])

    return {
        "name": name,
        "ticker": ticker,
        "description": f"Based on trending news: {story_title[:100]}",
    }


def generate_token_name(story):
    """
    Generate token name — AI first, fallback if unavailable.
    Uses AI-generated name from scoring if already available.
    """
    # If AI already scored this story, use those names
    if story.get("ai_name") and story.get("ai_ticker"):
        return {
            "name": story["ai_name"],
            "ticker": story["ai_ticker"],
            "description": f"Based on trending news: {story['title'][:100]}",
        }

    # Try AI generation
    if ai_available():
        ai_name = generate_token_name_ai(story["title"], story.get("summary", ""))
        if ai_name:
            return ai_name

    # Fallback
    return generate_token_name_fallback(story["title"])


# ---------------------------------------------------------------
# Wallet utilities
# ---------------------------------------------------------------

def get_wallet_balance():
    """Check SOL balance. Returns float or None."""
    try:
        from solana.rpc.api import Client
        from solders.keypair import Keypair
        import base58

        client = Client(SOLANA_RPC_URL)
        kp = Keypair.from_bytes(base58.b58decode(WALLET_PRIVATE_KEY))
        resp = client.get_balance(kp.pubkey())
        return resp.value / 1_000_000_000
    except Exception as e:
        logging.error(f"Balance check error: {e}")
        return None


def check_wallet_ready():
    """Verify wallet is configured and funded. Returns (ok, info)."""
    if WALLET_PRIVATE_KEY == "YOUR_PRIVATE_KEY_HERE":
        return False, "Wallet not configured — set WALLET_PRIVATE_KEY in .env"

    balance = get_wallet_balance()
    if balance is None:
        return False, "Could not connect to Solana network"

    minimum = DEV_BUY_AMOUNT_SOL + 0.1
    if balance < minimum:
        return False, f"Low balance: {balance:.3f} SOL (need {minimum:.3f})"

    return True, balance


# ---------------------------------------------------------------
# Token Launcher with safety limits
# ---------------------------------------------------------------

class TokenLauncher:
    def __init__(self):
        self.active_tokens = {}
        self.launch_log = []
        self._recent_launches = deque()  # timestamps for rate limiting
        self._daily_sol_spent = 0.0
        self._daily_reset_date = datetime.now().date()

    def _check_safety_limits(self):
        """Check rate limits and daily spend. Returns (ok, reason)."""
        now = datetime.now()

        # Reset daily counter if new day
        if now.date() != self._daily_reset_date:
            self._daily_sol_spent = 0.0
            self._daily_reset_date = now.date()

        # Check daily SOL limit
        if self._daily_sol_spent + DEV_BUY_AMOUNT_SOL > MAX_DAILY_SOL_SPEND:
            return False, f"Daily limit reached ({self._daily_sol_spent:.2f}/{MAX_DAILY_SOL_SPEND} SOL)"

        # Check hourly launch limit
        one_hour_ago = now - timedelta(hours=1)
        while self._recent_launches and self._recent_launches[0] < one_hour_ago:
            self._recent_launches.popleft()

        if len(self._recent_launches) >= MAX_LAUNCHES_PER_HOUR:
            return False, f"Hourly limit reached ({MAX_LAUNCHES_PER_HOUR}/hour)"

        return True, "OK"

    def launch_token(self, story, token_info=None, dry_run=True):
        """Launch a new token. Returns result dict or None."""
        # Safety check
        safe, reason = self._check_safety_limits()
        if not safe and not dry_run:
            print(Fore.RED + f"\n  🛡️ Safety limit: {reason}")
            logging.warning(f"Launch blocked by safety: {reason}")
            return None

        if token_info is None:
            token_info = generate_token_name(story)

        print(Fore.CYAN + "\n" + "=" * 60)
        print(Fore.CYAN + "  🚀 LAUNCHING TOKEN")
        print(Fore.CYAN + "=" * 60)
        print(f"  Name:        {token_info['name']}")
        print(f"  Ticker:      ${token_info['ticker']}")
        print(f"  Description: {token_info.get('description', '')[:60]}")
        print(f"  Dev Buy:     {DEV_BUY_AMOUNT_SOL} SOL")
        print(f"  Creator Fee: {CREATOR_FEE_PERCENT}%")
        print(f"  Sell at:     +70% (100% sold)")
        print(f"  Mode:        {'🧪 DRY RUN' if dry_run else '💰 LIVE'}")
        print(Fore.CYAN + "=" * 60)

        if dry_run:
            result = self._simulate_launch(story, token_info)
        else:
            ready, info = check_wallet_ready()
            if not ready:
                print(Fore.RED + f"\n  ❌ {info}")
                return None
            result = self._execute_launch(story, token_info)

        if result:
            self.active_tokens[result["mint_address"]] = result
            self.launch_log.append(result)
            self._save_launch_log()
            self._recent_launches.append(datetime.now())
            if not dry_run:
                self._daily_sol_spent += DEV_BUY_AMOUNT_SOL

        return result

    def _simulate_launch(self, story, token_info):
        """Simulate launch — no SOL spent."""
        fake_mint = "SIM" + "".join([str(random.randint(0, 9)) for _ in range(40)]) + "pump"

        result = {
            "mint_address": fake_mint,
            "name": token_info["name"],
            "ticker": token_info["ticker"],
            "story_title": story["title"],
            "story_score": story.get("score", 0),
            "launch_time": datetime.now().isoformat(),
            "dev_buy_sol": DEV_BUY_AMOUNT_SOL,
            "status": "simulated",
            "sell_strategy": SELL_STRATEGY,
        }

        print(Fore.YELLOW + f"\n  ✅ Simulated launch!")
        print(f"  Mint: {fake_mint[:25]}...")
        print(Fore.YELLOW + "  (No real SOL spent)")
        logging.info(f"SIM LAUNCH: {token_info['name']} (${token_info['ticker']})")

        return result

    def _execute_launch(self, story, token_info):
        """Execute real launch on pump.fun."""
        try:
            import requests as req
            from solana.rpc.api import Client
            from solders.keypair import Keypair
            from solders.transaction import VersionedTransaction
            import base58
            import base64

            client = Client(SOLANA_RPC_URL)
            wallet = Keypair.from_bytes(base58.b58decode(WALLET_PRIVATE_KEY))
            mint_kp = Keypair()
            mint_address = str(mint_kp.pubkey())

            print(f"\n  📝 Preparing transaction...")

            # Step 1: Upload metadata + image to IPFS
            print(f"  📤 Uploading metadata + image...")

            # Prepare the multipart form data
            meta_data = {
                "name": token_info["name"],
                "symbol": token_info["ticker"],
                "description": token_info.get("description", f"{token_info['name']} — LFG 🚀"),
                "showName": "true",
            }

            # Include token image if available
            meta_files = {}
            image_path = token_info.get("image_path") or story.get("image_path")
            if image_path and os.path.exists(image_path):
                meta_files["file"] = open(image_path, "rb")
                print(f"  🖼  Image included: {os.path.basename(image_path)}")

            try:
                meta_resp = req.post(
                    "https://pump.fun/api/ipfs",
                    data=meta_data,
                    files=meta_files if meta_files else None,
                    timeout=15,
                )
            finally:
                # Close file handle if opened
                if "file" in meta_files:
                    meta_files["file"].close()

            if meta_resp.status_code != 200:
                raise Exception(f"Metadata upload failed: {meta_resp.status_code}")

            metadata_uri = meta_resp.json().get("metadataUri", "")
            print(f"  ✅ Metadata: {metadata_uri[:40]}...")

            # Step 2: Build transaction
            print(f"  📦 Building transaction...")
            tx_resp = req.post(
                "https://pumpportal.fun/api/trade-local",
                headers={"Content-Type": "application/json"},
                json={
                    "publicKey": str(wallet.pubkey()),
                    "action": "create",
                    "tokenMetadata": {
                        "name": token_info["name"],
                        "symbol": token_info["ticker"],
                        "uri": metadata_uri,
                    },
                    "mint": str(mint_kp.pubkey()),
                    "denominatedInSol": "true",
                    "amount": DEV_BUY_AMOUNT_SOL,
                    "slippage": 10,
                    "priorityFee": 0.0005,
                    "pool": "pump",
                },
                timeout=15,
            )
            if tx_resp.status_code != 200:
                raise Exception(f"TX build failed: {tx_resp.status_code} - {tx_resp.text[:100]}")

            # Step 3: Sign and send
            print(f"  ✍️  Signing...")
            tx = VersionedTransaction.from_bytes(base64.b64decode(tx_resp.content))
            tx.sign([wallet, mint_kp])

            print(f"  📡 Sending to blockchain...")
            sig = client.send_raw_transaction(bytes(tx)).value

            print(Fore.GREEN + f"\n  ✅ TOKEN LAUNCHED!")
            print(f"  Pump: https://pump.fun/coin/{mint_address}")
            print(f"  Tx:   https://solscan.io/tx/{sig}")

            result = {
                "mint_address": mint_address,
                "name": token_info["name"],
                "ticker": token_info["ticker"],
                "story_title": story["title"],
                "story_score": story.get("score", 0),
                "launch_time": datetime.now().isoformat(),
                "dev_buy_sol": DEV_BUY_AMOUNT_SOL,
                "signature": str(sig),
                "status": "launched",
                "sell_strategy": SELL_STRATEGY,
                "pump_url": f"https://pump.fun/coin/{mint_address}",
            }

            logging.info(f"LAUNCHED: {token_info['name']} mint={mint_address}")
            return result

        except Exception as e:
            print(Fore.RED + f"\n  ❌ Launch failed: {e}")
            logging.error(f"Launch failed: {e}")
            return None

    def _save_launch_log(self):
        """Save launch history to JSON."""
        try:
            os.makedirs("logs", exist_ok=True)
            with open("logs/launches.json", "w") as f:
                json.dump(self.launch_log, f, indent=2, default=str)
        except Exception as e:
            logging.error(f"Could not save launch log: {e}")

    def get_daily_stats(self):
        """Return daily launch stats."""
        return {
            "launches_today": len([
                l for l in self.launch_log
                if l.get("launch_time", "").startswith(datetime.now().strftime("%Y-%m-%d"))
            ]),
            "sol_spent_today": self._daily_sol_spent,
            "max_daily": MAX_DAILY_SOL_SPEND,
        }
