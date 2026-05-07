# Olymp Trade Multi-Agent Signal Bot

Quality-first signal generator. Targets 10–15 high-confluence signals per day.
**Not financial advice. Binary options have a high probability of loss.**

---

## 1. Prerequisites

- Python 3.11 or 3.12 (avoid 3.13)
- A Telegram account
- An Olymp Trade account (for live data via the unofficial WS lib)

## 2. Local install

```bash
python -m venv venv
# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt
```

## 3. Configure secrets

```bash
cp .env.example .env
```

Fill in:

| Variable | Where to get it |
|---|---|
| `OLYMP_SSID` | See section 4 |
| `TELEGRAM_BOT_TOKEN` | [@BotFather](https://t.me/BotFather) → `/newbot` |
| `TELEGRAM_CHAT_ID` | [@userinfobot](https://t.me/userinfobot) |
| `ALPHA_VANTAGE_KEY` | https://www.alphavantage.co/support/#api-key |

## 4. Getting your Olymp Trade SSID

1. Open https://olymptrade.com in Chrome/Firefox and log in.
2. Press `F12` → **Network** tab → filter `WS`.
3. Refresh the page. Click any `wss://ws...olymptrade.com/...` connection.
4. In **Messages** look at the first sent message:
   ```json
   {"t":2,"e":11,"d":{"token":"abc123...","v":18,...}}
   ```
5. Copy the `token` value into `OLYMP_SSID`.

⚠️ Token rotates every 24–72 hours. Refresh when you see `Auth failed` in logs.
⚠️ Treat this token like a password.

## 5. Edit your trading config

Open `config/config.yaml` and set:
- Which assets to monitor
- Account size in USD
- Risk per trade (default 0.5%)
- Daily max risk (default 2.5%)

## 6. Run it

Dry-run first:
```bash
python run.py --dry-run
```

Live:
```bash
python run.py
```

## 7. Telegram commands

- `/status` — connection state, signals today
- `/stats` — win rate, expectancy this week
- `/pause` — stop sending new signals
- `/resume` — resume signals
- `/risk` — show today's risk usage
- Reply `WIN` or `LOSS` to any signal message after expiry

## 8. Deploy to Railway

1. Push this folder to a private GitHub repo.
2. railway.app → Login with GitHub → New Project → Deploy from GitHub repo.
3. In Variables tab, add `OLYMP_SSID`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `ALPHA_VANTAGE_KEY`, `LOG_LEVEL=INFO`.
4. Settings tab → Volumes → mount path `/app/data`, size 1 GB.
5. Deployment auto-runs `python run.py`.
6. Refresh `OLYMP_SSID` daily by editing the variable.

## 9. Troubleshooting

| Problem | Fix |
|---|---|
| `Auth failed` repeatedly | Refresh SSID |
| `No data for OTC pairs` | OTC only via WS; refresh SSID |
| `Module not found: pandas_ta` | `pip install pandas-ta==0.4.71b0` |
| Telegram silent | Send any message to your bot first; check chat ID |
| Bot crashes on Windows | Use Python 3.11, not 3.13 |

## 10. What this bot will NOT do

- Place trades automatically (by design)
- Recover lost money (no system promises this)
- Work without supervision

Read every signal critically. Confidence % is an estimate, not a guarantee.
