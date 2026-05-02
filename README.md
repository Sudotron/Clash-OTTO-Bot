# Clash OTTO Bot

A comprehensive Telegram Bot for Clash of Clans, powered by `python-telegram-bot` and the official `coc.py` wrapper for the Clash of Clans API.

## Features

- **Personal Account Linking**: Map your unique Telegram User ID to your CoC Player Tag.
- **Detailed Player Stats**: Dedicated commands to query general info, home village troops, heroes/equipment, and spells.
- **Detailed Clan Stats & CWL**: Dedicated commands to fetch clan details, interactive CWL season leaderboards, and real-time war analytics.
- **Loot Forecaster**: Global and regional Clash of Clans loot availability forecasts.
- **Clan Activity Tracking**: Real-time logs for members joining, leaving, or getting promoted/demoted within a tracked clan.
- **Fully Asynchronous**: Built with `asyncio`, `coc.py`, and `aiosqlite` for non-blocking, rapid requests.

## Setup Instructions

### 1. Requirements

- Python 3.10+
- A Telegram Bot Token from [@BotFather](https://t.me/BotFather)

### 2. Installation

1. Copy `.env.example` to a new file named `.env`:
   ```bash
   cp .env.example .env
   ```

2. Open `.env` and fill in your Bot Token:
   ```env
   TG_BOT_TOKEN=your_telegram_bot_token_here
   ```

3. Install the dependencies via `pip`:
   ```bash
   pip install -r requirements.txt
   ```

### 3. Running the Bot

Run the bot script directly:
```bash
python bot.py
```

The bot will automatically create a local `users.db` SQLite database to store user links.

## Usage Commands

Once the bot is running, interact with it on Telegram:

- `/start` - Start the bot and get a welcome message
- `/link <#TAG>` - Link your Telegram account with your Clash of Clans Player Tag
- `/myid` - View your Telegram User Profile along with all linked player accounts
- `/player [tag]` - Detailed overview of player stats, plus Clan History navigation
- `/todo [tag]` - Interactive To-Do List for tracking hero, troop, and spell upgrades
- `/clan [tag]` - Details about the clan alongside a paginated member roster
- `/clansorted [tag]` - Sort clan members interactively by Trophies, Town Hall, Donations, Role, or XP Level
- `/clanwar [tag]` - View current clan war info and detailed war analytics
- `/cwl [tag]` - Interactive Clan War League dashboard (Roster mapping, Analytics, Season Leaderboard)
- `/cap_stats [tag]` - View clan Clan Capital stats and contribution leaderboards
- `/audit [tag]` - Analyze a player's base for rush status across troops, heroes, and spells
- `/loot` - View the live Loot Forecaster for the best times to farm

### 🛡️ Admin & Tracking Commands
- `/clantrack <#CLANTAG>` - Start tracking a clan for join/leave/promotion/war events
- `/deltrack` - Stop tracking the current clan
- `/crnttrack` - Show details and configuration of the currently tracked clan
- `/scrap` - Automatically scrape the latest Town Hall max levels
- `>link [tag]` - Link a CoC tag to a specific user (Reply to their message)
- `/getid` - Get your Telegram User ID

---
**Clash OTTO Bot** | Built for the Clash of Clans Telegram community.
