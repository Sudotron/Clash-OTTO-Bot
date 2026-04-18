from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ChatAction
from database import link_account
from coc_api import get_player, get_clan

async def link_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Please provide a tag! Example: /link #YY8PQY28")
        return
    tag = context.args[0]
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    
    pdata = await get_player(tag)
    if not "error" in pdata:
        name = pdata.get('name', 'Unknown')
        th = pdata.get('townHallLevel', '?')
        exp = pdata.get('expLevel', '?')
        await link_account(update.effective_user.id, tag, 'player')
        await update.message.reply_text(f"✅ Player **{name}** (TH{th} | Lvl {exp}) linked to your account!", parse_mode='Markdown')
        return
        
    cdata = await get_clan(tag)
    if not "error" in cdata:
        name = cdata.get('name', 'Unknown')
        lvl = cdata.get('clanLevel', '?')
        leader = "Unknown"
        for m in cdata.get('memberList', []):
            if m.get('role') == 'leader':
                leader = m.get('name')
                break
        await link_account(update.effective_user.id, tag, 'clan')
        await update.message.reply_text(f"✅ Clan **{name}** (Lvl {lvl} | Leader: {leader}) linked to your account!", parse_mode='Markdown')
        return
        
    await update.message.reply_text(f"❌ Invalid Tag! Could not find any player or clan with `{tag}`.", parse_mode='Markdown')
