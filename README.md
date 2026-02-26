# 🐸 Trend Token Bot v3

Scans 55 news sources in parallel → AI-scores meme potential → checks duplicates on pump.fun → alerts you on Telegram → auto-sells at +70%.

## What's new in v3

- **AI scoring** (Claude Haiku) — evaluates real meme potential, not just keywords (~$0.05/day)
- **AI token naming** — generates creative names + tickers automatically
- **Parallel RSS scanning** — 55 feeds in ~10 seconds (was 5+ minutes)
- **Secrets in .env** — private key never in source code
- **Safety limits** — max 3 launches/hour, 2 SOL/day, 5 active positions
- **Stop loss from buy price** — won't sell a 2.5x winner because it dropped from 5x
- **Sell strategy: +70% → sell 100%** — simple, clean, consistent
- **Feed health monitoring** — know which RSS feeds are dead
- **Proper Python package structure** — clean imports, no path hacks

---

## 📁 Structure

```
trend-bot-v3/
├── main.py                     ← Start here
├── requirements.txt
├── .env.example                ← Copy to .env, fill secrets
├── .gitignore                  ← Protects .env from git
├── trend-bot.service           ← Systemd (auto-start on VPS)
│
├── config/
│   └── settings.py             ← All settings (reads .env)
│
├── scanner/
│   ├── ai_scorer.py            ← Claude AI scoring + naming
│   ├── news_scanner.py         ← Parallel RSS + scoring pipeline
│   ├── duplicate_checker.py    ← pump.fun competition check
│   └── google_trends.py        ← Optional Google Trends boost
│
├── launcher/
│   └── pump_launcher.py        ← Token creation + safety limits
│
├── monitor/
│   └── price_monitor.py        ← Auto-sell at +70%, stop loss
│
├── telegram/
│   └── bot.py                  ← Alerts + inline buttons
│
└── logs/                       ← Auto-created
    ├── bot.log
    ├── scanner.log
    └── launches.json
```

---

## 🚀 Setup Steps

### Step 1 — Install

```bash
# Python 3.10+ required
pip install -r requirements.txt
```

### Step 2 — Configure secrets

```bash
cp .env.example .env
nano .env
```

Fill in:
- `WALLET_PRIVATE_KEY` — your Solana wallet (base58)
- `TELEGRAM_BOT_TOKEN` — from @BotFather
- `TELEGRAM_CHAT_ID` — your chat ID
- `ANTHROPIC_API_KEY` — from console.anthropic.com
- `SOLANA_RPC_URL` — keep devnet for testing

### Step 3 — Test (zero risk)

```bash
python main.py
# Choose [3] for dry run
```

### Step 4 — Run for real

```bash
python main.py
# Choose [1] for continuous scanning
```

---

## VPS Deployment (24/7)

### 1. Get a VPS
- Hetzner CX11: €3.29/month (recommended)
- DigitalOcean: $4/month

### 2. Upload & install

```bash
scp -r trend-bot-v3/ ubuntu@YOUR_IP:/home/ubuntu/
ssh ubuntu@YOUR_IP
cd trend-bot-v3
pip install -r requirements.txt
cp .env.example .env && nano .env
```

### 3. Test

```bash
python main.py --scan-once
```

### 4. Run as service

```bash
sudo cp trend-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable trend-bot
sudo systemctl start trend-bot

# Check logs:
sudo journalctl -u trend-bot -f
```

---

## 💰 Cost Breakdown

| Item | Cost |
|---|---|
| VPS (Hetzner) | €3.29/month |
| Anthropic API (AI scoring) | ~$0.05/day = ~$1.50/month |
| Solana RPC (public) | Free |
| Total infra | ~€5/month |
| Per token launch | 0.1 SOL + ~0.001 SOL fees |

---

## ⚠️ Risk Management

Built into the code (not just settings):
1. **Max 3 launches/hour** — prevents spam in breaking news
2. **Max 2 SOL/day** — daily loss ceiling
3. **Max 5 active positions** — diversification limit
4. **Stop loss at -40%** from buy price — capital protection
5. **Duplicate check** — skips if tokens already exist with high mcap
6. **Active hours only** — 9am-7pm Eastern (peak crypto)
7. **All secrets in .env** — never in source code

**This bot does NOT guarantee profits. Only use money you can afford to lose.**

---

## 📱 Telegram Commands

| Command | Action |
|---|---|
| `/status` | Bot health + wallet |
| `/tokens` | Active positions |
| `/pause` | Pause scanning |
| `/resume` | Resume scanning |
| `/stop` | Stop bot |
| `/summary` | Daily P&L |

---

## 🤖 OpenClaw Integration (Optional)

OpenClaw turns your Telegram into a full AI agent:
- "Launch the frog token" → understands + executes
- "What's our P&L?" → queries + responds
- Natural language control of the bot

Setup: see OpenClaw docs at https://docs.openclaw.ai

Point OpenClaw at these commands:
```yaml
commands:
  scan:
    exec: python3 /home/ubuntu/trend-bot-v3/main.py --scan-once
  status:
    exec: python3 /home/ubuntu/trend-bot-v3/main.py --status
  pause:
    exec: touch /home/ubuntu/trend-bot-v3/.pause
  resume:
    exec: rm -f /home/ubuntu/trend-bot-v3/.pause
```
