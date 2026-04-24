import sys

NEW_CODE = '''

# ═══════════════════════════════════════════════════════════════════════════════
# /cwl — Clan War League
# ═══════════════════════════════════════════════════════════════════════════════

def _cwl_round_markup(tag: str, round_idx: int, total_rounds: int, view: str = "round") -> InlineKeyboardMarkup:
    # Navigation keyboard for CWL rounds
    nav = []
    if round_idx > 0:
        nav.append(InlineKeyboardButton("◀️ Prev Round", callback_data=f"cwl_r:{view}:{tag}:{round_idx - 1}"))
    if round_idx < total_rounds - 1:
        nav.append(InlineKeyboardButton("Next Round ▶️", callback_data=f"cwl_r:{view}:{tag}:{round_idx + 1}"))
    keyboard = []
    if nav:
        keyboard.append(nav)
    keyboard.append([
        InlineKeyboardButton("📋 Group Overview", callback_data=f"cwl_r:overview:{tag}:0"),
        InlineKeyboardButton("🗡️ Attacks", callback_data=f"cwl_r:attacks:{tag}:{round_idx}"),
    ])
    return InlineKeyboardMarkup(keyboard)


def _cwl_overview_text(group: dict, clan_tag: str) -> str:
    # Build CWL group overview: season, participating clans, round info
    season = group.get("season", "Unknown Season")
    clans  = group.get("clans", [])
    rounds = group.get("rounds", [])
    total_rounds = len(rounds)
    completed = sum(1 for r in rounds if any(wt != "#0" for wt in r.get("warTags", [])))
    dash30 = "\u2500" * 30
    text = (
        f"🌟 **Clan War League — {season}**\\n"
        f"{dash30}\\n"
        f"📅 Rounds: {completed}/{total_rounds} completed\\n"
        f"👥 Participating Clans ({len(clans)}):\\n"
    )
    for i, c in enumerate(clans):
        ctag  = c.get("tag", "?")
        cname = c.get("name", "Unknown")
        clvl  = c.get("clanLevel", "?")
        icon  = "🏆" if ctag.upper() == clan_tag.upper() else "🛡️"
        text += f"  {icon} `{i+1}.` **{cname}** (Lvl {clvl}) `{ctag}`\\n"
    return text


async def cwl_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tag = await _resolve_tag(update, context, entity_type="clan")
    if not tag:
        await update.message.reply_text(
            "Please provide a clan tag or link a clan/player account first.\\n"
            "Usage: `/cwl #CLANTAG`", parse_mode="Markdown"
        )
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    msg = await update.message.reply_text("🌟 Fetching CWL group data...")
    # Resolve player tag → clan tag
    pdata = await get_player(tag)
    if "error" not in pdata and pdata.get("clan"):
        tag = pdata["clan"]["tag"]
    norm_tag = tag.strip().upper()
    group = await get_cwl_group(norm_tag)
    if "error" in group:
        await msg.edit_text(
            "❌ CWL data not available.\\n\\n"
            "_CWL only runs for the first ~10 days of each month. "
            "Outside that window, or if the clan is not participating, no data is returned._",
            parse_mode="Markdown"
        )
        return
    context.bot_data[f"cwl_{norm_tag}"] = group
    overview_text = _cwl_overview_text(group, norm_tag)
    rounds = group.get("rounds", [])
    total_rounds = len(rounds)
    latest = 0
    for i, r in enumerate(rounds):
        if any(wt != "#0" for wt in r.get("warTags", [])):
            latest = i
    keyboard = []
    if total_rounds > 0:
        keyboard.append([InlineKeyboardButton(
            f"⚔️ View Round {latest + 1}",
            callback_data=f"cwl_r:round:{norm_tag}:{latest}"
        )])
    await msg.edit_text(
        overview_text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None
    )


async def cwl_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts     = query.data.split(":", 3)
    view      = parts[1] if len(parts) > 1 else "overview"
    tag       = parts[2] if len(parts) > 2 else ""
    norm_tag  = tag.strip().upper()
    round_idx = int(parts[3]) if len(parts) > 3 else 0
    group = context.bot_data.get(f"cwl_{norm_tag}")
    if not group:
        group = await get_cwl_group(norm_tag)
        if "error" in group:
            await query.edit_message_text("❌ CWL data expired. Run `/cwl` again.", parse_mode="Markdown")
            return
        context.bot_data[f"cwl_{norm_tag}"] = group
    rounds       = group.get("rounds", [])
    total_rounds = len(rounds)
    if view == "overview":
        text = _cwl_overview_text(group, norm_tag)
        latest = 0
        for i, r in enumerate(rounds):
            if any(wt != "#0" for wt in r.get("warTags", [])):
                latest = i
        kb = [[InlineKeyboardButton(f"⚔️ View Round {latest + 1}", callback_data=f"cwl_r:round:{norm_tag}:{latest}")]] if total_rounds > 0 else []
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb) if kb else None)
        return
    if round_idx >= total_rounds:
        await query.edit_message_text("❌ Round not found.")
        return
    round_data = rounds[round_idx]
    war_tags   = [wt for wt in round_data.get("warTags", []) if wt != "#0"]
    if not war_tags:
        await query.edit_message_text(
            f"⏳ Round {round_idx + 1} hasn't started yet.",
            reply_markup=_cwl_round_markup(norm_tag, round_idx, total_rounds, view)
        )
        return
    our_war = None
    for wt in war_tags:
        wdata = await get_cwl_war(wt)
        if "error" not in wdata:
            c_tag = wdata.get("clan", {}).get("tag", "").upper()
            o_tag = wdata.get("opponent", {}).get("tag", "").upper()
            if norm_tag in (c_tag, o_tag):
                if o_tag == norm_tag:
                    wdata["clan"], wdata["opponent"] = wdata["opponent"], wdata["clan"]
                our_war = wdata
                break
    if not our_war:
        our_war = await get_cwl_war(war_tags[0])
    if not our_war or "error" in our_war:
        await query.edit_message_text(
            f"❌ Could not load Round {round_idx + 1} war data.",
            reply_markup=_cwl_round_markup(norm_tag, round_idx, total_rounds, view)
        )
        return
    c_name  = our_war.get("clan", {}).get("name", "Clan")
    c_stars = our_war.get("clan", {}).get("stars", 0)
    c_dest  = our_war.get("clan", {}).get("destructionPercentage", 0)
    o_name  = our_war.get("opponent", {}).get("name", "Opponent")
    o_stars = our_war.get("opponent", {}).get("stars", 0)
    o_dest  = our_war.get("opponent", {}).get("destructionPercentage", 0)
    w_state = our_war.get("state", "unknown")
    w_size  = our_war.get("teamSize", "?")
    if w_state == "preparation":
        s_dt = _parse_coc_time(our_war.get("startTime", ""))
        time_str    = _fmt_remaining(s_dt, "War Starts")
        state_label = "⚙️ Preparation"
    elif w_state == "inWar":
        e_dt = _parse_coc_time(our_war.get("endTime", ""))
        time_str    = _fmt_remaining(e_dt, "War Ends")
        state_label = "🔥 In War"
    else:
        time_str    = ""
        state_label = w_state.capitalize()
    if w_state == "warEnded":
        if c_stars > o_stars:
            result_line = "\\n🏆 Victory"
        elif o_stars > c_stars:
            result_line = "\\n💀 Defeat"
        else:
            result_line = "\\n🤝 Draw"
    else:
        result_line = ""
    dash28 = "\u2500" * 28
    dash30 = "\u2500" * 30
    if view == "attacks":
        lines = [f"🗡️ **CWL Round {round_idx + 1} — Our Attacks**\\n{dash28}\\n"]
        all_members = our_war.get("clan", {}).get("members", []) + our_war.get("opponent", {}).get("members", [])
        member_map  = {m.get("tag", ""): m for m in all_members}
        for m in our_war.get("clan", {}).get("members", []):
            for atk in m.get("attacks", []):
                defender  = member_map.get(atk.get("defenderTag", ""), {})
                ptag_raw  = m.get("tag", "").strip("#")
                plink     = f"https://link.clashofclans.com/en?action=OpenPlayerProfile&tag={ptag_raw}"
                st        = atk.get("stars", 0)
                dest      = atk.get("destructionPercentage", 0)
                dname     = defender.get("name", "?")
                dth       = defender.get("townhallLevel", "?")
                stars_str = "⭐" * st + "☆" * (3 - st)
                mname     = m.get("name", "?")
                mth       = m.get("townhallLevel", "?")
                lines.append(f"[{mname} TH{mth}]({plink}) → {dname} TH{dth}: {stars_str} {dest}%")
        if len(lines) == 1:
            lines.append("❌ No attacks recorded for this round yet.")
        text = "\\n".join(lines)
    else:
        text = (
            f"🌟 **CWL — Round {round_idx + 1}/{total_rounds}** ({state_label})\\n"
            f"👥 {w_size}v{w_size}{time_str}{result_line}\\n"
            f"{dash30}\\n"
            f"🛡️ **{c_name}**\\n"
            f"  ⭐ Stars: {c_stars}   💥 Dest: {c_dest:.1f}%\\n\\n"
            f"🏴 **{o_name}**\\n"
            f"  ⭐ Stars: {o_stars}   💥 Dest: {o_dest:.1f}%\\n"
        )
    if len(text) > 4096:
        text = text[:4090] + "\\n…"
    await query.edit_message_text(
        text, parse_mode="Markdown",
        reply_markup=_cwl_round_markup(norm_tag, round_idx, total_rounds, view)
    )


# ═══════════════════════════════════════════════════════════════════════════════
# /raidclans — Find Capital Hall 10 Clans for Raid Weekend
# ═══════════════════════════════════════════════════════════════════════════════

RAIDS_PER_PAGE = 5


def _raidclans_markup(page: int, total_pages: int) -> InlineKeyboardMarkup:
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ Prev", callback_data=f"raidclans:page:{page - 1}"))
    nav.append(InlineKeyboardButton(f"📄 {page + 1}/{total_pages}", callback_data="raidclans:noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("Next ▶️", callback_data=f"raidclans:page:{page + 1}"))
    return InlineKeyboardMarkup([nav])


def _build_raidclans_page(clans: list, page: int) -> tuple:
    total_pages = max(1, (len(clans) + RAIDS_PER_PAGE - 1) // RAIDS_PER_PAGE)
    page  = max(0, min(page, total_pages - 1))
    start = page * RAIDS_PER_PAGE
    end   = min(start + RAIDS_PER_PAGE, len(clans))
    dash30 = "\u2500" * 30
    text = (
        f"🗡️ **Raid Weekend Targets — Capital Hall 10**\\n"
        f"Found {len(clans)} clans • Page {page + 1}/{total_pages}\\n"
        f"{dash30}\\n"
    )
    for i, c in enumerate(clans[start:end], start=start + 1):
        cname      = c.get("name", "Unknown")
        ctag       = c.get("tag", "?")
        clvl       = c.get("clanLevel", "?")
        members    = c.get("members", "?")
        pts        = c.get("clanPoints", 0)
        cap_info   = c.get("clanCapital", {}) or {}
        cap_hall   = cap_info.get("capitalHallLevel", "?")
        cap_league = (c.get("capitalLeague", {}) or {}).get("name", "Unranked")
        location   = (c.get("location", {}) or {}).get("name", "International")
        clean_tag  = ctag.replace("#", "")
        clink      = f"https://link.clashofclans.com/en?action=OpenClanProfile&tag=%23{clean_tag}"
        text += (
            f"\\n`{i}.` **[{cname}]({clink})**\\n"
            f"   🏰 Capital Hall: **{cap_hall}** • 🌍 {location}\\n"
            f"   🏆 {pts:,} pts • 👥 {members}/50 • Lvl {clvl}\\n"
            f"   🎖️ {cap_league}\\n"
            f"   `{ctag}`\\n"
        )
    return text, _raidclans_markup(page, total_pages)


async def raidclans_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    msg = await update.message.reply_text(
        "🗡️ Scouting raid targets... searching for Capital Hall 10 clans...\\n"
        "_(This may take a moment as we scan multiple clans)_",
        parse_mode="Markdown"
    )
    result = await search_clans(min_clan_level=10, min_clan_points=40000, limit=50)
    if "error" in result:
        await msg.edit_text(f"❌ Search failed: {result['error']}")
        return
    items = result.get("items", [])
    cap10_clans = []
    for c in items:
        cap_hall = (c.get("clanCapital", {}) or {}).get("capitalHallLevel", 0)
        if cap_hall >= 10:
            cap10_clans.append(c)
        if len(cap10_clans) >= 10:
            break
    if len(cap10_clans) < 10:
        result2 = await search_clans(min_clan_level=15, min_clan_points=50000, limit=50)
        if "error" not in result2:
            existing_tags = {x.get("tag") for x in cap10_clans}
            for c in result2.get("items", []):
                if c.get("tag") in existing_tags:
                    continue
                cap_hall = (c.get("clanCapital", {}) or {}).get("capitalHallLevel", 0)
                if cap_hall >= 10:
                    cap10_clans.append(c)
                if len(cap10_clans) >= 10:
                    break
    if not cap10_clans:
        await msg.edit_text(
            "⚠️ Could not find Capital Hall 10 clans in the current search results.\\n"
            "_The CoC API clan search does not filter by Capital Hall level directly. "
            "Try again shortly or use /clan to check a specific clan._",
            parse_mode="Markdown"
        )
        return
    context.bot_data["raidclans_results"] = cap10_clans
    text, markup = _build_raidclans_page(cap10_clans, 0)
    await msg.edit_text(text, parse_mode="Markdown", reply_markup=markup, disable_web_page_preview=True)


async def raidclans_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts  = query.data.split(":")
    action = parts[1] if len(parts) > 1 else "noop"
    if action == "noop":
        return
    page  = int(parts[2]) if len(parts) > 2 else 0
    clans = context.bot_data.get("raidclans_results", [])
    if not clans:
        await query.edit_message_text("⚠️ Results expired. Please run /raidclans again.")
        return
    text, markup = _build_raidclans_page(clans, page)
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=markup, disable_web_page_preview=True)
'''

with open(r"d:\BOTS\Clash-OTTO-Bot\commands\clan.py", "a", encoding="utf-8") as f:
    # Need to unescape the explicit \\n back to \n
    f.write(NEW_CODE.replace('\\\\n', '\\n'))

print(f"Done - appended bytes")
