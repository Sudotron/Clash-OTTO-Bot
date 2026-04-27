"""
Maintenance Monitor — Detects Clash of Clans API outages.

- Polls the CoC API every 2 minutes via a background job.
- Sets a global `maintenance_mode` flag in bot_data.
- Sends elegant notifications to the tracked clan's chat when maintenance starts/ends.
- Any command triggered during maintenance returns a freeze message.
"""

import logging
import httpx
import os
from telegram import Update
from telegram.ext import ContextTypes

CHAT_ID = os.getenv("CHAT_ID")

# The probe URL — a lightweight CoC API endpoint to check availability.
# We use /locations as it's a static, cacheable, public endpoint.
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
            # 503 = maintenance, 200 = up, anything else treat as up (temporary errors)
            if r.status_code == 503:
                return False
            return True
    except Exception:
        # Network error — treat as temporary, don't freeze the bot
        return True


async def maintenance_check_job(context: ContextTypes.DEFAULT_TYPE):
    """Background job: polls the API every 2 minutes and updates maintenance state."""
    was_in_maintenance = context.bot_data.get("maintenance_mode", False)
    is_up = await _is_api_up()
    now_in_maintenance = not is_up

    context.bot_data["maintenance_mode"] = now_in_maintenance

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
    """Returns True if the bot is currently in maintenance freeze mode."""
    return context.bot_data.get("maintenance_mode", False)


async def maintenance_guard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Call this at the top of any command handler.
    Returns True if we're in maintenance (caller should return immediately).
    """
    if not is_maintenance(context):
        return False

    if update.message:
        await update.message.reply_text(COMMAND_FROZEN_MSG, parse_mode="HTML")
    elif update.callback_query:
        await update.callback_query.answer(
            "🛑 Bot is frozen — Clash servers are under maintenance!", show_alert=True
        )
    return True
