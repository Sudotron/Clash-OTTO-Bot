from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from coc_api import get_player, get_player_stats, get_player_warhits, get_clan, get_player_join_leave
from commands.utils import E, _resolve_tag, _build_player_page1, _build_player_page2
from database import get_all_linked_tags

async def player_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tag = await _resolve_tag(update, context)
    if not tag:
        await update.message.reply_text("Please provide a tag or link an account first via /link <tag>.")
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    msg = await update.message.reply_text("⏳ Diving into the game to fetch player data...")

    data = await get_player(tag)
    if "error" in data:
        await msg.edit_text(f"❌ {data['error']}")
        return

    stats = await get_player_stats(tag)
    warhits = await get_player_warhits(tag)

    norm_tag = tag.strip().upper()
    context.bot_data[f"pdata_{norm_tag}"] = (data, stats, warhits)

    page1_text = _build_player_page1(data, stats, warhits, norm_tag)

    keyboard = [
        [InlineKeyboardButton("🛡️ Clan History", callback_data=f"player_history:{norm_tag}")],
        [InlineKeyboardButton(f"{E['next']} Troops & Heroes", callback_data=f"player_p2:{norm_tag}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await msg.edit_text(page1_text, parse_mode='Markdown', reply_markup=reply_markup)


async def player_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":", 1)
    action = parts[0]
    tag = parts[1] if len(parts) > 1 else ""

    norm_tag = tag.strip().upper()
    cached = context.bot_data.get(f"pdata_{norm_tag}")

    if action == "player_p2":
        if cached:
            data, stats, warhits = cached
        else:
            data = await get_player(tag)
            stats = await get_player_stats(tag)
            warhits = await get_player_warhits(tag)
            if "error" in data:
                await query.edit_message_text(f"❌ {data['error']}")
                return
            context.bot_data[f"pdata_{norm_tag}"] = (data, stats, warhits)

        page2_text = _build_player_page2(data)
        keyboard = [[
            InlineKeyboardButton(f"{E['back']} Season Stats", callback_data=f"player_p1:{norm_tag}")
        ]]
        await query.edit_message_text(
            page2_text, parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif action == "player_p1":
        if cached:
            data, stats, warhits = cached
        else:
            data = await get_player(tag)
            stats = await get_player_stats(tag)
            warhits = await get_player_warhits(tag)
            if "error" in data:
                await query.edit_message_text(f"❌ {data['error']}")
                return
            context.bot_data[f"pdata_{norm_tag}"] = (data, stats, warhits)

        page1_text = _build_player_page1(data, stats, warhits, norm_tag)
        keyboard = [
            [InlineKeyboardButton("🛡️ Clan History", callback_data=f"player_history:{norm_tag}")],
            [InlineKeyboardButton(f"{E['next']} Troops & Heroes", callback_data=f"player_p2:{norm_tag}")]
        ]
        await query.edit_message_text(
            page1_text, parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif action == "player_history":
        history_data = await get_player_join_leave(tag, limit=15)
        if isinstance(history_data, dict) and "error" in history_data:
            await query.edit_message_text(f"❌ {history_data['error']}")
            return
            
        if isinstance(history_data, dict) and 'items' in history_data:
            history = history_data['items']
        elif isinstance(history_data, list):
            history = history_data
        else:
            history = []
            
        if not history:
            text = f"❌ No clan history found for {norm_tag}."
            keyboard = [[InlineKeyboardButton(f"{E['back']} Back to Profile", callback_data=f"player_p1:{norm_tag}")]]
            await query.edit_message_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
            return
            
        text = f"🛡️ **Clan History for {norm_tag}**\n\n"
        for item in history[:15]:
            c_tag = item.get('clan', '').replace('#', '')
            c_name = item.get('clan_name', 'Unknown')
            t_type = item.get('type', 'join').capitalize()
            # formatting date
            t_str = str(item.get('time', ''))[:16].replace('T', ' ')
            
            link = f"https://link.clashofclans.com/en?action=OpenClanProfile&tag=%23{c_tag}"
            emoji = "🟢" if t_type.lower() == "join" else "🔴"
            
            text += f"{emoji} **{t_type}** | [{c_name}]({link}) `#{c_tag}`\n"
            text += f"📅 {t_str}\n\n"
            
        keyboard = [[InlineKeyboardButton(f"{E['back']} Back to Profile", callback_data=f"player_p1:{norm_tag}")]]
        await query.edit_message_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))


async def troops_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tag = await _resolve_tag(update, context)
    if not tag:
        await update.message.reply_text("Please provide a tag or link an account first.")
        return

    data = await get_player(tag)
    if "error" in data:
        await update.message.reply_text(f"❌ {data['error']}")
        return

    troops = [t for t in data.get('troops', []) if t.get('village') == 'home' and 'Super' not in t.get('name','')]
    text = f"{E['troop']} **{data.get('name')} — Home Troops:**\n"
    for t in troops:
        lvl, ml = t.get('level'), t.get('maxLevel')
        maxed = " ✅" if lvl == ml else ""
        text += f"• {t.get('name')}: Lvl {lvl}/{ml}{maxed}\n"
    if len(text) > 4000:
        text = text[:4000] + "...\n(Trimmed)"
    await update.message.reply_text(text, parse_mode='Markdown')


async def heroes_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tag = await _resolve_tag(update, context)
    if not tag:
        await update.message.reply_text("Please provide a tag or link an account first.")
        return

    data = await get_player(tag)
    if "error" in data:
        await update.message.reply_text(f"❌ {data['error']}")
        return

    heroes = data.get('heroes', [])
    equipment = data.get('heroEquipment', [])

    text = f"{E['hero']} **{data.get('name')} — Heroes:**\n"
    for h in heroes:
        if h.get('village') == 'home':
            lvl, ml = h.get('level'), h.get('maxLevel')
            maxed = " ✅" if lvl == ml else ""
            text += f"• {h.get('name')}: Lvl {lvl}/{ml}{maxed}\n"

    if equipment:
        text += "\n🔮 **Hero Equipment:**\n"
        for e in equipment:
            lvl, ml = e.get('level'), e.get('maxLevel')
            maxed = " ✅" if lvl == ml else ""
            text += f"• {e.get('name')}: Lvl {lvl}/{ml}{maxed}\n"

    if text == f"{E['hero']} **{data.get('name')} — Heroes:**\n":
        text = "No heroes found."

    await update.message.reply_text(text, parse_mode='Markdown')


async def spells_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tag = await _resolve_tag(update, context)
    if not tag:
        await update.message.reply_text("Please provide a tag or link an account first.")
        return

    data = await get_player(tag)
    if "error" in data:
        await update.message.reply_text(f"❌ {data['error']}")
        return

    spells = [s for s in data.get('spells', []) if s.get('village') == 'home']
    if not spells:
        await update.message.reply_text("No spells found.")
        return

    text = f"{E['spell']} **{data.get('name')} — Spells:**\n"
    for s in spells:
        lvl, ml = s.get('level'), s.get('maxLevel')
        maxed = " ✅" if lvl == ml else ""
        text += f"• {s.get('name')}: Lvl {lvl}/{ml}{maxed}\n"
    await update.message.reply_text(text, parse_mode='Markdown')


def _build_todo_page(data: dict, category: str, tag: str) -> tuple:
    name = data.get('name', 'Unknown')
    th = data.get('townHallLevel', '?')

    to_upgrade_heroes = []
    to_upgrade_troops = []
    to_upgrade_spells = []

    for h in data.get('heroes', []):
        if h.get('village') == 'home' and h.get('level') < h.get('maxLevel'):
            to_upgrade_heroes.append(h)
            
    for t in data.get('troops', []):
        if t.get('village') == 'home' and 'Super' not in t.get('name', '') and not t.get('name', '').startswith('Super') and t.get('level') < t.get('maxLevel'):
            to_upgrade_troops.append(t)
            
    for s in data.get('spells', []):
        if s.get('village') == 'home' and s.get('level') < s.get('maxLevel'):
            to_upgrade_spells.append(s)

    text = f"📋 **To-Do List for {name} (TH{th}):**\n\n"
    
    if category == "heroes":
        emoji = E.get('hero', '👑')
        items = to_upgrade_heroes
        title = "Heroes"
    elif category == "troops":
        emoji = E.get('troop', '🪖')
        items = to_upgrade_troops
        title = "Troops"
    else:
        category = "spells"
        emoji = E.get('spell', '🧪')
        items = to_upgrade_spells
        title = "Spells"
        
    if not items:
        text += f"🎉 **All Home Village {title} are maxed out!**"
    else:
        text += f"{emoji} **{title} to Max ({len(items)}):**\n"
        for i in items:
            text += f" • {i.get('name')}: Lvl {i.get('level')} -> {i.get('maxLevel')}\n"

    keyboard = [
        [
            InlineKeyboardButton(f"{'✅ ' if category=='heroes' else ''}👑 Heroes", callback_data=f"todo_p:heroes:{tag}"),
            InlineKeyboardButton(f"{'✅ ' if category=='troops' else ''}🪖 Troops", callback_data=f"todo_p:troops:{tag}"),
            InlineKeyboardButton(f"{'✅ ' if category=='spells' else ''}🧪 Spells", callback_data=f"todo_p:spells:{tag}")
        ]
    ]

    return text, InlineKeyboardMarkup(keyboard)


async def todo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tag = await _resolve_tag(update, context)
    if not tag:
        await update.message.reply_text("Please provide a tag or link an account first.")
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    msg = await update.message.reply_text("⏳ Diving into the game to fetch to-do list...")
    
    data = await get_player(tag)
    if "error" in data:
        await msg.edit_text(f"❌ {data['error']}")
        return

    norm_tag = tag.strip().upper()
    context.bot_data[f"tododata_{norm_tag}"] = data
    
    text, markup = _build_todo_page(data, "heroes", norm_tag)
    await msg.edit_text(text, parse_mode='Markdown', reply_markup=markup)


async def todo_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":", 2)
    action = parts[0]
    category = parts[1]
    tag = parts[2] if len(parts) > 2 else ""
    norm_tag = tag.strip().upper()

    data = context.bot_data.get(f"tododata_{norm_tag}")
    if not data:
        data = await get_player(norm_tag)
        if "error" in data:
            await query.edit_message_text(f"❌ {data['error']}")
            return
        context.bot_data[f"tododata_{norm_tag}"] = data

    text, markup = _build_todo_page(data, category, norm_tag)
    await query.edit_message_text(text, parse_mode='Markdown', reply_markup=markup)


async def _generate_accounts_text(accounts: list) -> str:
    text = "👥 **Your Linked Accounts:**\n\n"
    for tag in accounts:
        data = await get_player(tag)
        if "error" in data:
            text += f"• `{tag}` — ❌ Unable to fetch data\n"
        else:
            name = data.get('name', 'Unknown')
            th = data.get('townHallLevel', '?')
            trophies = data.get('trophies', 0)
            text += f"• **{name}** (TH{th}) 🏆 {trophies} \n   `{tag}`\n"
    return text


async def myid_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    photos = await context.bot.get_user_profile_photos(user.id)
    photo_id = None
    if photos.photos:
        photo_id = photos.photos[0][-1].file_id
        
    text = (
        f"👤 **User Identity**\n"
        f"Name: {user.full_name}\n"
        f"ID: `{user.id}`\n"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("🔗 Back to Profile", callback_data="myid:home"),
            InlineKeyboardButton("🔗 Linked Accounts", callback_data="myid:accounts")
        ],
        [
            InlineKeyboardButton("🛡️ Linked Clan", callback_data="myid:clan")
        ]
    ]
    markup = InlineKeyboardMarkup(keyboard)
    
    if photo_id:
        await update.message.reply_photo(photo=photo_id, caption=text, parse_mode='Markdown', reply_markup=markup)
    else:
        await update.message.reply_text(text, parse_mode='Markdown', reply_markup=markup)


async def myid_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    action = query.data.split(":")[1]
    user = update.effective_user

    keyboard = [
        [
            InlineKeyboardButton("🔗 Back to Profile", callback_data="myid:home"),
            InlineKeyboardButton("🔗 Linked Accounts", callback_data="myid:accounts")
        ],
        [
            InlineKeyboardButton("🛡️ Linked Clan", callback_data="myid:clan")
        ]
    ]
    markup = InlineKeyboardMarkup(keyboard)

    async def _edit(text: str):
        if query.message.photo:
            await query.edit_message_caption(caption=text, parse_mode='Markdown', reply_markup=markup)
        else:
            await query.edit_message_text(text=text, parse_mode='Markdown', reply_markup=markup)

    if action == "home":
        text = (
            f"👤 **User Identity**\n"
            f"Name: {user.full_name}\n"
            f"ID: `{user.id}`\n"
        )
        await _edit(text)
        return

    if action == "accounts":
        accounts = await get_all_linked_tags(user.id, "player")
        if not accounts:
            await _edit("❌ You don't have any linked player accounts. Use /link <tag>.")
            return
        text = await _generate_accounts_text(accounts)
        await _edit(text)

    elif action == "clan":
        clans = await get_all_linked_tags(user.id, "clan")
        if not clans:
            await _edit("❌ You don't have any linked clans. Use /link <tag>.")
            return

        text = "🛡️ **Your Linked Clans:**\n\n"
        for tag in clans:
            data = await get_clan(tag)
            if "error" in data:
                text += f"• `{tag}` — ❌ Unable to fetch data\n"
            else:
                name = data.get('name', 'Unknown')
                lvl = data.get('clanLevel', '?')
                text += f"• **{name}** (Lvl {lvl})\n   `{tag}`\n"
        await _edit(text)

