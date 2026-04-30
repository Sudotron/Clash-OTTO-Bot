import json
import os
import time
from datetime import datetime, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_FILE = os.path.join(base_dir, "forecaster_data.json")

# Base epoch corresponding to index 0 in the data array (1680162300)
BASE_EPOCH = 1680162300
WEEK_SECONDS = 7 * 24 * 60 * 60

CONFIG_FILE = os.path.join(base_dir, "loot_config.json")

def _get_forecaster_data() -> dict:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def get_loot_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {"enabled": True}

def set_loot_config(enabled: bool):
    with open(CONFIG_FILE, 'w') as f:
        json.dump({"enabled": enabled}, f)

def get_current_loot_info():
    """Calculates the current loot index based on the static repeating weekly model."""
    data = _get_forecaster_data()
    if not data or "totals" not in data:
        return None
        
    loot_minutes = data["totals"]["lootMinutes"]
    max_loot_minute = float(data.get("maxLootMinute", 45494096))
    
    current_epoch = time.time()
    offset = current_epoch - BASE_EPOCH
    index = int(offset // 60) % len(loot_minutes)
    
    # Current
    current_loot = loot_minutes[index]
    current_index = round((current_loot / max_loot_minute) * 10, 1)
    
    players_online = data["totals"]["playersOnline"][index]
    shielded_players = data["totals"]["shieldedPlayers"][index]
    
    # Next hour
    next_hour_index = (index + 60) % len(loot_minutes)
    next_hour_loot = loot_minutes[next_hour_index]
    next_hour_idx = round((next_hour_loot / max_loot_minute) * 10, 1)
    
    # Next 2 hours
    next_2hour_index = (index + 120) % len(loot_minutes)
    next_2hour_loot = loot_minutes[next_2hour_index]
    next_2hour_idx = round((next_2hour_loot / max_loot_minute) * 10, 1)
    
    def get_status(idx):
        if idx >= 9.0: return "Excellent 🟢"
        if idx >= 8.0: return "Great 🟢"
        if idx >= 6.0: return "Good 🟡"
        if idx >= 4.0: return "Okay 🟡"
        if idx >= 2.0: return "Poor 🔴"
        return "Terrible 🔴"

    return {
        "index": current_index,
        "status": get_status(current_index),
        "players_online": players_online,
        "shielded_players": shielded_players,
        "next_hour_index": next_hour_idx,
        "next_hour_status": get_status(next_hour_idx),
        "trend": "📈 Increasing" if next_hour_idx > current_index else "📉 Decreasing" if next_hour_idx < current_index else "➡️ Stable",
        "next_2hour_index": next_2hour_idx,
        "next_2hour_status": get_status(next_2hour_idx),
        "trend_2h": "📈 Increasing" if next_2hour_idx > current_index else "📉 Decreasing" if next_2hour_idx < current_index else "➡️ Stable"
    }

async def loot_notification_job(context: ContextTypes.DEFAULT_TYPE):
    """Background job to send the loot index notification."""
    config = get_loot_config()
    if not config.get("enabled", True):
        return
    # We will fetch the chat_id from tracking data to know where to send it.
    tracking_db = os.path.join(base_dir, "clan_data.json")
    chat_id = None
    if os.path.exists(tracking_db):
        try:
            with open(tracking_db, 'r') as f:
                tracking_data = json.load(f)
                chat_id = tracking_data.get("chat_id")
        except:
            pass
            
    # Fallback to env variable
    if not chat_id:
        chat_id = os.getenv("CHAT_ID")
        
    if not chat_id:
        return
        
    info = get_current_loot_info()
    if not info:
        return
        
    # Only notify if it's "Good" or better, OR we just do it every 6 hours?
    # Let's send a standard notification
    text = (
        f"📊 **Loot Forecaster Update**\n\n"
        f"Current Loot Index: **{info['index']}/10.0** ({info['status']})\n"
        f"Forecast (1h): **{info['next_hour_index']}/10.0** ({info['trend']})\n"
        f"Forecast (2h): **{info['next_2hour_index']}/10.0** ({info['trend_2h']})\n\n"
        f"_The best time to raid is when the index is above 8.0!_\n\n"
        f"⚠️ _Disclaimer: This data is not affiliated with Clash of Clans servers. It is calculated by a predictive algorithm and is not 100% reliable._"
    )
    
    try:
        await context.bot.send_message(chat_id=chat_id, text=text, parse_mode='Markdown')
        print(f"Sent Loot Forecaster notification to {chat_id}")
    except Exception as e:
        print(f"Failed to send loot notification: {e}")

def _get_loot_keyboard():
    return [
        [
            InlineKeyboardButton("🌍 Worldwide Stats", callback_data="loot_worldwide"),
            InlineKeyboardButton("🗺️ Most Active Region", callback_data="loot_region")
        ],
        [InlineKeyboardButton("Toggle Notifications", callback_data="loot_toggle")]
    ]

async def loot_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    info = get_current_loot_info()
    if not info:
        await update.message.reply_text("Loot data not available.")
        return
        
    config = get_loot_config()
    status_emoji = "✅ ON" if config.get("enabled", True) else "❌ OFF"
    
    text = (
        f"📊 **Loot Forecaster**\n\n"
        f"Current Loot Index: **{info['index']}/10.0** ({info['status']})\n"
        f"Forecast (1h): **{info['next_hour_index']}/10.0** ({info['trend']})\n"
        f"Forecast (2h): **{info['next_2hour_index']}/10.0** ({info['trend_2h']})\n\n"
        f"Group Notifications: {status_emoji}\n\n"
        f"⚠️ _Disclaimer: This data is not affiliated with Clash of Clans servers. It is calculated by a predictive algorithm and is not 100% reliable._"
    )
    
    reply_markup = InlineKeyboardMarkup(_get_loot_keyboard())
    if update.message:
        await update.message.reply_text(text, parse_mode='Markdown', reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)

async def loot_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    config = get_loot_config()
    new_status = not config.get("enabled", True)
    set_loot_config(new_status)
    
    # Just render the main menu again
    await loot_cmd(update, context)

async def loot_back_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await loot_cmd(update, context)

async def loot_worldwide_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    info = get_current_loot_info()
    
    text = (
        f"🌍 **Worldwide Clash Stats**\n\n"
        f"👤 Players Online: **{info['players_online']:,}**\n"
        f"🛡️ Shielded Players: **{info['shielded_players']:,}**\n\n"
        f"_Data based on cyclical forecaster model_"
    )
    keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data="loot_back")]]
    await query.edit_message_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))

def get_most_active_region():
    utc_hour = datetime.now(timezone.utc).hour
    if 1 <= utc_hour < 7:
        return "North America 🇺🇸🇨🇦"
    elif 7 <= utc_hour < 11:
        return "Asia / Oceania 🇦🇺🇯🇵"
    elif 11 <= utc_hour < 16:
        return "Asia (China/India) 🇨🇳🇮🇳"
    elif 16 <= utc_hour < 20:
        return "Europe & Africa 🇪🇺🌍"
    else:
        return "Americas & Europe 🌎🌍"

async def loot_region_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    region = get_most_active_region()
    text = (
        f"🗺️ **Most Active Region**\n\n"
        f"Based on current global timezones, the most active player base right now is likely in:\n\n"
        f"🌟 **{region}**"
    )
    keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data="loot_back")]]
    await query.edit_message_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
