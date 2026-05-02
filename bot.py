import os
import sys
import logging
import asyncio
from dotenv import load_dotenv
from telegram import Update

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

base_dir = os.path.dirname(os.path.abspath(__file__))
dotenv_path = os.path.join(base_dir, '.env')
load_dotenv(dotenv_path)
from telegram.ext import (
    ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ApplicationHandlerStop
)

from database import init_db

# Import our new command modules
from commands.link import link_cmd, owner_link_cmd
from commands.player import (
    player_cmd, player_page_callback,
    todo_cmd, todo_page_callback, myid_cmd, myid_callback
)
from commands.clan import (
    clan_cmd, clan_page_callback, clanwar_cmd, clansorted_cmd, clansorted_callback, clanwar_analytics_callback,
    cwl_cmd, cwl_callback
)
from commands.tracking import (
    track_cmd, deltrack_cmd, crnttrack_cmd, getid_cmd, setup_coc_client, check_clan_changes,
    track_config_callback
)
from commands.capital import cap_stats_cmd, cap_stats_callback
from commands.audit import audit_cmd
from commands.scraper import scrap_cmd, auto_scrap_job
from commands.maintenance import maintenance_check_job, COMMAND_FROZEN_MSG
from commands.forecaster import (
    loot_notification_job, loot_cmd, loot_toggle_callback,
    loot_worldwide_callback, loot_region_callback, loot_back_callback
)


logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "<b>Welcome to Clash OTTO Bot</b> ⚔️\n\n"
        "<b>A high-performance bot for Clash Of Clans tracking and analytics.</b>\n\n"
        "📊 <b>Commands:</b>\n"
        "• /link <code>[tag]</code> — Link your CoC Account\n"
        "• /myid — Profile & Linked Accounts\n"
        "• /player <code>[tag]</code> — Full player stats\n"
        "• /todo <code>[tag]</code> — Upgrade Progress (TH-specific)\n"
        "• /clan <code>[tag]</code> — Clan Profile & Roster\n"
        "• /clansorted <code>[tag]</code> — Interactive Roster Sorting\n"
        "• /clanwar <code>[tag]</code> — War Info & Analytics\n"
        "• /cwl <code>[tag]</code> — CWL Group & War Details\n"
        "• /audit <code>[tag]</code> — Player Rush Audit\n"
        "• /cap_stats <code>[tag]</code> — Capital Gold Rankings\n"
        "• /loot — Loot Forecaster Statistics\n\n"
        "👑 <b>Admin Commands:</b>\n"
        "• /clantrack <code>[tag]</code> — Start Join/Leave/War logs\n"
        "• /deltrack — Stop tracking\n"
        "• /crnttrack — Tracked Clan Details\n"
        "• /scrap — Scrape latest TH max levels\n"
        "• <code>>link [tag]</code> — Link CoC tag to user (Reply to msg)\n\n"
        "🔔 <b>Automated:</b>\n"
        "• War Feed — Real-time attack notifications\n\n"
        "🆔 <b>Utilities:</b>\n"
        "• /getid — Get your Telegram ID\n\n"
        "👑 <b>Owner:</b> <a href='https://t.me/Llowx'>@Llowx</a>"
    )
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    gif_path = os.path.join(base_dir, "gif", "animation.gif.mp4")
    
    if os.path.exists(gif_path):
        with open(gif_path, 'rb') as f:
            await update.message.reply_animation(
                animation=f,
                caption=welcome_text,
                parse_mode='HTML'
            )
    else:
        await update.message.reply_text(welcome_text, parse_mode='HTML')


def main():
    token = os.getenv("TG_BOT_TOKEN")
    if not token or token == "your_telegram_bot_token_here":
        logging.error("No valid TG_BOT_TOKEN found in .env!")
        return

    import asyncio
    asyncio.run(init_db())

    app = ApplicationBuilder().token(token).post_init(setup_coc_client).build()

    # Global maintenance guard — catches ALL commands before they reach their handlers
    async def global_maintenance_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if context.bot_data.get("maintenance_mode", False):
            if update.message:
                await update.message.reply_text(COMMAND_FROZEN_MSG, parse_mode="HTML")
            elif update.callback_query:
                await update.callback_query.answer(
                    "🛑 Bot is frozen — Clash servers are under maintenance!", show_alert=True
                )
            # CRITICAL: Stop the update from reaching any other handler group
            raise ApplicationHandlerStop

    # group=-1 runs BEFORE all command handlers in group 0
    app.add_handler(MessageHandler(filters.COMMAND, global_maintenance_handler), group=-1)
    app.add_handler(CallbackQueryHandler(global_maintenance_handler), group=-1)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("link", link_cmd))
    app.add_handler(CommandHandler("player", player_cmd))
    app.add_handler(CommandHandler("todo", todo_cmd))
    app.add_handler(CommandHandler("clan", clan_cmd))
    app.add_handler(CommandHandler("clansorted", clansorted_cmd))
    app.add_handler(CommandHandler("clanwar", clanwar_cmd))
    app.add_handler(CommandHandler("cwl", cwl_cmd))
    app.add_handler(CommandHandler("myid", myid_cmd))
    app.add_handler(CommandHandler("cap_stats", cap_stats_cmd))
    app.add_handler(CommandHandler("audit", audit_cmd))
    app.add_handler(CommandHandler("loot", loot_cmd))
    
    # Message handler for >link (owner only)
    app.add_handler(MessageHandler(filters.Regex(r'^>link\s+'), owner_link_cmd))

    # Tracking commands
    app.add_handler(CommandHandler("clantrack", track_cmd))
    app.add_handler(CommandHandler("deltrack", deltrack_cmd))
    app.add_handler(CommandHandler("crnttrack", crnttrack_cmd))
    app.add_handler(CommandHandler("getid", getid_cmd))
    app.add_handler(CommandHandler("scrap", scrap_cmd))

    # Inline page navigation
    app.add_handler(CallbackQueryHandler(player_page_callback, pattern=r"^(player_p[123]|player_history):"))
    app.add_handler(CallbackQueryHandler(todo_page_callback,   pattern=r"^todo_p:.*"))
    app.add_handler(CallbackQueryHandler(clan_page_callback,   pattern=r"^(clan_p[12]|clan_members|clan_noop).*"))
    app.add_handler(CallbackQueryHandler(clansorted_callback,  pattern=r"^clansort:.*"))
    app.add_handler(CallbackQueryHandler(clanwar_analytics_callback, pattern=r"^cwar_a:.*"))
    app.add_handler(CallbackQueryHandler(cwl_callback,         pattern=r"^cwl_r:.*"))
    app.add_handler(CallbackQueryHandler(myid_callback,        pattern=r"^myid:.*"))
    app.add_handler(CallbackQueryHandler(track_config_callback, pattern=r"^tkcfg:.*"))
    app.add_handler(CallbackQueryHandler(cap_stats_callback, pattern=r"^capst:.*"))
    app.add_handler(CallbackQueryHandler(loot_toggle_callback, pattern=r"^loot_toggle$"))
    app.add_handler(CallbackQueryHandler(loot_worldwide_callback, pattern=r"^loot_worldwide$"))
    app.add_handler(CallbackQueryHandler(loot_region_callback, pattern=r"^loot_region$"))
    app.add_handler(CallbackQueryHandler(loot_back_callback, pattern=r"^loot_back$"))

    # Background job: check clan changes every 30 seconds
    app.job_queue.run_repeating(check_clan_changes, interval=30, first=10)

    # Background job: check for CoC API maintenance every 2 minutes
    app.job_queue.run_repeating(maintenance_check_job, interval=120, first=5)
    
    # Background job: auto-scrape max levels once a week (604800 seconds)
    app.job_queue.run_repeating(auto_scrap_job, interval=604800, first=60)

    # Background job: Loot Forecaster notification every 4 hours (14400 seconds)
    app.job_queue.run_repeating(loot_notification_job, interval=14400, first=120)

    logging.info("Starting bot...")
    app.run_polling()


if __name__ == '__main__':
    main()
