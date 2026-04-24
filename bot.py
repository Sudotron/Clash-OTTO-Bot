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
    ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters
)

from database import init_db

# Import our new command modules
from commands.link import link_cmd, owner_link_cmd
from commands.player import (
    player_cmd, player_page_callback, troops_cmd, heroes_cmd, spells_cmd,
    todo_cmd, todo_page_callback, myid_cmd, myid_callback
)
from commands.clan import (
    clan_cmd, clan_page_callback, clanwar_cmd, clansorted_cmd, clansorted_callback, clanwar_analytics_callback,
    cwl_cmd, cwl_callback
)
from commands.tracking import (
    track_cmd, deltrack_cmd, crnttrack_cmd, getid_cmd, setup_coc_client, check_clan_changes
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
        "• /link <code>#TAG</code> — Link your CoC Account\n"
        "• /myid — Profile & Linked Accounts\n"
        "• /player <code>[tag]</code> — Full player stats\n"
        "• /todo <code>[tag]</code> — Upgrade Progress\n"
        "• /troops <code>[tag]</code> / /heroes / /spells\n"
        "• /clan <code>[tag]</code> — Clan Profile & Roster\n"
        "• /clansorted <code>[tag]</code> — Interactive Roster Sorting\n"
        "• /clanwar <code>[tag]</code> — War Info & Analytics\n"
        "• /cwl <code>[tag]</code> — CWL Group & War Details\n\n"
        "👑 <b>Owner Commands:</b>\n"
        "• /track <code>#CLANTAG</code> — Start Join/Leave/War logs\n"
        "• /deltrack — Stop tracking\n"
        "• /crnttrack — Tracked Clan Details\n"
        "• <code>>link #TAG</code> — Link CoC tag to user (Reply to msg)\n\n"
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

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("link", link_cmd))
    app.add_handler(CommandHandler("player", player_cmd))
    app.add_handler(CommandHandler("todo", todo_cmd))
    app.add_handler(CommandHandler("troops", troops_cmd))
    app.add_handler(CommandHandler("heroes", heroes_cmd))
    app.add_handler(CommandHandler("spells", spells_cmd))
    app.add_handler(CommandHandler("clan", clan_cmd))
    app.add_handler(CommandHandler("clansorted", clansorted_cmd))
    app.add_handler(CommandHandler("clanwar", clanwar_cmd))
    app.add_handler(CommandHandler("cwl", cwl_cmd))
    app.add_handler(CommandHandler("myid", myid_cmd))
    
    # Message handler for >link (owner only)
    app.add_handler(MessageHandler(filters.Regex(r'^>link\s+'), owner_link_cmd))

    # Tracking commands
    app.add_handler(CommandHandler("track", track_cmd))
    app.add_handler(CommandHandler("deltrack", deltrack_cmd))
    app.add_handler(CommandHandler("crnttrack", crnttrack_cmd))
    app.add_handler(CommandHandler("getid", getid_cmd))

    # Inline page navigation
    app.add_handler(CallbackQueryHandler(player_page_callback, pattern=r"^(player_p[123]|player_history):"))
    app.add_handler(CallbackQueryHandler(todo_page_callback,   pattern=r"^todo_p:.*"))
    app.add_handler(CallbackQueryHandler(clan_page_callback,   pattern=r"^(clan_p[12]|clan_members|clan_noop).*"))
    app.add_handler(CallbackQueryHandler(clansorted_callback,  pattern=r"^clansort:.*"))
    app.add_handler(CallbackQueryHandler(clanwar_analytics_callback, pattern=r"^cwar_a:.*"))
    app.add_handler(CallbackQueryHandler(cwl_callback,         pattern=r"^cwl_r:.*"))
    app.add_handler(CallbackQueryHandler(myid_callback,        pattern=r"^myid:.*"))

    # Background job: check clan changes every 30 seconds
    app.job_queue.run_repeating(check_clan_changes, interval=30, first=10)

    logging.info("Starting bot...")
    app.run_polling()


if __name__ == '__main__':
    main()
