import logging
import httpx
import os
import coc
from telegram import Update
from telegram.ext import ContextTypes

CHAT_ID = os.getenv("CHAT_ID")
PROBE_URL = "https://api.clashk.ing/v1/locations?limit=1"

MAINTENANCE_MSG = (
    "🛑 <b>Clash of Clans is Under Maintenance!</b>\n\n"
    "🔧 Supercell's servers are currently down for maintenance.\n"
    "⚔️ All bot commands are <b>frozen</b> until the game is back online.\n\n"
    "⏳ <i>Sit tight, Chief! Your village will be waiting...</i>\n\n"
    "🔔 I'll notify you the moment the servers are back up!"
)

COMMAND_FROZEN_MSG = (
    "🛑 <b>Bot is Frozen — Game Under Maintenance</b>\n\n"
    "⚔️ Clash of Clans servers are currently down.\n"
    "❄️ All commands are suspended until maintenance ends.\n\n"
    "🔔 You'll get a notification here when the bot is back online!"
)

BACK_ONLINE_MSG = (
    "✅ <b>Clash of Clans is Back Online!</b>\n\n"
    "⚔️ The servers are back up and running!\n"
    "🚀 All bot commands are now <b>active</b> again.\n\n"
    "👑 Go crush your enemies, Chief! 💪"
)

async def _is_api_up() -> bool:
    """Returns True if the CoC API is reachable, False if it's in maintenance."""
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(PROBE_URL, headers={"Accept": "application/json"})
            if r.status_code == 503:
                return False
            return True
    except Exception:
        return True

async def maintenance_check_job(context: ContextTypes.DEFAULT_TYPE):
    """Background job: polls the API and updates maintenance state."""
    print(f"--- [Job] Checking Maintenance Status ---", flush=True)
    was_in_maintenance = context.bot_data.get("maintenance_mode", False)
    
    now_in_maintenance = False
    coc_client = context.bot_data.get("coc_client")
    
    if coc_client:
        try:
            # Try a direct call to the official API.
            await coc_client.get_location(32000000) # Europe
            now_in_maintenance = False
        except coc.Maintenance:
            now_in_maintenance = True
            print("--- [Job] coc.Maintenance exception caught ---", flush=True)
        except Exception as e:
            print(f"--- [Job] coc_client error: {e}, falling back to proxy ---", flush=True)
            is_up = await _is_api_up()
            now_in_maintenance = not is_up
    else:
        is_up = await _is_api_up()
        now_in_maintenance = not is_up

    context.bot_data["maintenance_mode"] = now_in_maintenance
    print(f"--- [Job] maintenance_mode is now {now_in_maintenance} ---", flush=True)

    # Transition: just went into maintenance
    if now_in_maintenance and not was_in_maintenance:
        logging.warning("⚠️ CoC API maintenance detected. Freezing bot commands.")
        chat_id = context.bot_data.get("tracking_chat_id") or CHAT_ID
        if chat_id:
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=MAINTENANCE_MSG,
                    parse_mode="HTML"
                )
            except Exception as e:
                logging.error(f"Failed to send maintenance notification: {e}")

    # Transition: just came back online
    elif not now_in_maintenance and was_in_maintenance:
        logging.info("✅ CoC API is back online. Resuming bot commands.")
        chat_id = context.bot_data.get("tracking_chat_id") or CHAT_ID
        if chat_id:
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=BACK_ONLINE_MSG,
                    parse_mode="HTML"
                )
            except Exception as e:
                logging.error(f"Failed to send back-online notification: {e}")

def is_maintenance(context: ContextTypes.DEFAULT_TYPE) -> bool:
    return context.bot_data.get("maintenance_mode", False)
