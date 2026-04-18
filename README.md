# Clash OTTO Bot

A comprehensive Telegram Bot for Clash of Clans, powered by `python-telegram-bot`, `aiohttp`, and the custom `api.clashk.ing` proxy API.

## Features

- **Personal Account Linking**: Map your unique Telegram User ID to your CoC Player Tag.
- **Detailed Player Stats**: Dedicated commands to query general info, home village troops, heroes/equipment, and spells.
- **Detailed Clan Stats**: Dedicated commands to fetch clan details, the clan member roster, and current war status.
- **Fully Asynchronous**: Built with `asyncio`, `aiohttp`, and `aiosqlite` for non-blocking, rapid requests.

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
- `/link <#TAG>` - Link your Telegram account with your Clash of Clans Player/Clan Tag
- `/myid` - View your Telegram User Profile along with all linked player accounts and clans
- `/player [tag]` - Detailed overview of player stats, plus Clan History navigation
- `/todo [tag]` - Interactive To-Do List for tracking hero, troop, and spell upgrades
- `/troops [tag]` - Specific home village troop levels
- `/heroes [tag]` - Specific hero and hero equipment levels
- `/spells [tag]` - Specific spell levels
- `/clan [tag]` - Details about the clan alongside a paginated offline member roster
- `/clansorted [tag]` - Sort clan members interactively by Trophies, Town Hall, Donations, Role, or XP Level
- `/clanwar [tag]` - View current clan war info and detailed war analytics
