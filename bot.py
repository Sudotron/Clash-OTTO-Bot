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
    ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler
)

from database import init_db

# Import our new command modules
from commands.link import link_cmd
from commands.player import (
    player_cmd, player_page_callback, troops_cmd, heroes_cmd, spells_cmd,
    todo_cmd, todo_page_callback, myid_cmd, myid_callback
)
from commands.clan import (
    clan_cmd, clan_page_callback, clanwar_cmd, clansorted_cmd, clansorted_callback, clanwar_analytics_callback
)


logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "<b>Welcome to Clash OTTO Bot</b> ⚔️\n"
        "<b>A Clash Of Clans Telegram Bot aiming to cover all possible features & do the heavy lifting so others don’t have to.</b>\n\n"
        "<b>Commands:</b>\n"
        "/link <code>#TAG</code> — Link your CoC Account\n"
        "/myid — View Profile & linked components\n"
        "/player <code>[tag]</code> — Full player stats\n"
        "/todo <code>[tag]</code> — To-Do List of character upgrades\n"
        "/troops <code>[tag]</code> — Troops levels\n"
        "/heroes <code>[tag]</code> — Heroes and equipment\n"
        "/spells <code>[tag]</code> — Spells levels\n"
        "/clan <code>[tag]</code> — Clan details\n"
        "/clansorted <code>[tag]</code> — Sort clan members interactively\n"
        "/clanwar <code>[tag]</code> — Current clan war info\n\n"
        "👑 <b>Bot Owner:</b> <a href='https://t.me/Llowx'>@Llowx</a>"
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

    app = ApplicationBuilder().token(token).build()

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
    app.add_handler(CommandHandler("myid", myid_cmd))

    # Inline page navigation
    app.add_handler(CallbackQueryHandler(player_page_callback, pattern=r"^(player_p[12]|player_history):"))
    app.add_handler(CallbackQueryHandler(todo_page_callback,   pattern=r"^todo_p:.*"))
    app.add_handler(CallbackQueryHandler(clan_page_callback,   pattern=r"^(clan_p[12]|clan_members|clan_noop).*"))
    app.add_handler(CallbackQueryHandler(clansorted_callback,  pattern=r"^clansort:.*"))
    app.add_handler(CallbackQueryHandler(clanwar_analytics_callback, pattern=r"^cwar_a:.*"))
    app.add_handler(CallbackQueryHandler(myid_callback,        pattern=r"^myid:.*"))

    logging.info("Starting bot...")
    app.run_polling()


if __name__ == '__main__':
    main()
