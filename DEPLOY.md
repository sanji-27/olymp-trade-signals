# Deployment Guide — GitHub + Railway

## Step 1: Install tools (one-time)

1. **Git** — https://git-scm.com/downloads
2. **GitHub Desktop** — https://desktop.github.com
3. **VS Code** (optional, for editing) — https://code.visualstudio.com

## Step 2: Get the code on your computer

You already have this folder. Confirm the structure looks like:
```
olymp_signal_bot/
├── README.md
├── requirements.txt
├── run.py
├── Procfile
├── railway.json
├── runtime.txt
├── Dockerfile
├── .env.example
├── .gitignore
├── config/
├── src/
├── tests/
├── data/
└── logs/
```

## Step 3: Create a GitHub repo

### Using GitHub Desktop (easiest)
1. Open GitHub Desktop -> sign in with your GitHub account
2. **File -> Add Local Repository** -> select the `olymp_signal_bot` folder
3. It says "this is not a git repo" -> click **"create a repository"**
4. Fill in:
   - Name: `olymp-signal-bot`
   - **Git ignore: Python**
5. Click **Create Repository**
6. Click **Publish repository** (top right)
7. **CHECK** "Keep this code private"
8. Click **Publish Repository**

### Safety check before publishing
Open the file list on left side of GitHub Desktop.
- `.env` should NOT appear (gitignore protects it)
- `.env.example` SHOULD appear

If `.env` appears, delete it from your folder before publishing.

## Step 4: Get your secrets ready

Before deploying, gather these 4 values:

### OLYMP_SSID
1. Open https://olymptrade.com in Chrome -> log in
2. Press F12 -> Network tab -> filter "WS"
3. Refresh page. Click any `wss://ws...olymptrade.com/...` connection
4. In Messages, find the first sent message containing `"token":"..."`
5. Copy the token value

### TELEGRAM_BOT_TOKEN
1. Open Telegram -> message [@BotFather](https://t.me/BotFather)
2. Send `/newbot`
3. Pick a name and username
4. Copy the token (looks like `1234567890:ABC-DEF...`)

### TELEGRAM_CHAT_ID
1. Open Telegram -> message [@userinfobot](https://t.me/userinfobot)
2. It replies with your numeric ID

### ALPHA_VANTAGE_KEY (optional fallback)
1. Get free key at https://www.alphavantage.co/support/#api-key
2. Copy the key

## Step 5: Deploy to Railway

1. Go to **railway.app** -> **Login with GitHub**
2. Authorize Railway
3. Click **New Project** -> **Deploy from GitHub repo**
4. Select `olymp-signal-bot`
5. Click **Deploy Now**
6. Wait ~2 minutes for build (will fail without secrets - that's expected)

## Step 6: Add secrets in Railway

1. Click your service (the box with your repo name)
2. Click **Variables** tab
3. Click **+ New Variable** for each:

| Name | Value |
|---|---|
| `OLYMP_SSID` | from Step 4 |
| `TELEGRAM_BOT_TOKEN` | from Step 4 |
| `TELEGRAM_CHAT_ID` | from Step 4 |
| `ALPHA_VANTAGE_KEY` | from Step 4 |
| `LOG_LEVEL` | `INFO` |

Railway auto-redeploys after each variable.

## Step 7: Add persistent storage

1. In your service -> **Settings** tab
2. Scroll to **Volumes** -> **+ New Volume**
3. Mount path: `/app/data`
4. Click **Add**

Without this, your signals.db gets wiped on every redeploy.

## Step 8: Verify it works

1. Click **Deployments** tab -> latest deployment -> **View Logs**
2. Look for these messages within 30 seconds:
   ```
   logging initialized
   db ready: data/signals.db
   telegram started
   [router] using Olymp WS (primary)
   engine started
   ```
3. Open Telegram -> message your bot -> send `/status`
4. It should reply with status

## Step 9: Daily routine

- **Morning:** check Telegram `/status`. If "Connection: DOWN", refresh `OLYMP_SSID` in Railway Variables
- **During day:** reply `WIN` or `LOSS` to every signal so the bot learns
- **Sunday 8 PM UTC:** bot sends weekly performance report automatically

## Step 10: Updating code

When you change any file:
1. Open GitHub Desktop -> see your changes listed
2. Type a summary like "fix risk agent" at bottom
3. Click **Commit to main**
4. Click **Push origin** (top)
5. Railway redeploys automatically in ~2 minutes

## Common errors

| Error | Fix |
|---|---|
| `OLYMP_SSID empty` | Add the variable in Railway -> Variables |
| `Auth rejected` | SSID expired -> get fresh one from browser |
| `telegram disabled` | Bot token or chat ID missing |
| `[router] using FALLBACK provider` | Olymp WS unreachable -> refresh SSID |
| Build fails on `pandas-ta` | Check `runtime.txt` says `python-3.12` |
| `address already in use` | Wait 60 seconds, Railway is restarting |
