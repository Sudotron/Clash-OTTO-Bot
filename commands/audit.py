"""
Player Rush Audit — /audit

Quickly assess player quality by comparing hero levels, troops,
and spells against their Town Hall's maximum levels.
Uses coc.py library for TH-specific max level data.
"""

import os
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from coc_api import get_player
from commands.utils import E, _resolve_tag, fmt_number, get_scraped_th_max


async def _get_th_max_audit(context, tag: str, th_level: int) -> dict:
    """Get TH-specific max levels using coc.py library."""
    th_max = {}
    coc_client = context.bot_data.get("coc_client")
    if not coc_client:
        return th_max
    try:
        clean_tag = tag.strip().upper()
        if not clean_tag.startswith('#'):
            clean_tag = '#' + clean_tag
        player = await coc_client.get_player(clean_tag)
        for h in player.heroes:
            if h.is_home_base:
                ml = get_scraped_th_max(h.name, th_level)
                if ml:
                    th_max[h.name] = ml
        for t in player.troops:
            if t.is_home_base and not t.is_super_troop:
                ml = t.get_max_level_for_townhall(th_level)
                if ml:
                    th_max[t.name] = ml
        for s in player.spells:
            if s.is_home_base:
                ml = s.get_max_level_for_townhall(th_level)
                if ml:
                    th_max[s.name] = ml
    except Exception:
        pass
    return th_max


async def audit_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command: /audit #playerTag — Perform a rush audit on a player."""
    tag = await _resolve_tag(update, context)
    if not tag:
        await update.message.reply_text(
            "Please provide a player tag.\n"
            "Usage: `/audit #PLAYERTAG`",
            parse_mode="Markdown",
        )
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    msg = await update.message.reply_text("🔍 Auditing player profile...")

    data = await get_player(tag)
    if "error" in data:
        await msg.edit_text(f"❌ {data['error']}")
        return

    name = data.get("name", "Unknown")
    th = data.get("townHallLevel", 1)
    norm_tag = data.get("tag", tag).strip().upper()
    clean_tag = norm_tag.replace("#", "")
    p_link = f"https://link.clashofclans.com/en?action=OpenPlayerProfile&tag=%23{clean_tag}"

    # Get TH-specific max levels
    th_max = await _get_th_max_audit(context, norm_tag, th)

    # ── Heroes Analysis ──────────────────────────────────────────────────
    heroes = [h for h in data.get("heroes", []) if h.get("village") == "home"]
    hero_lines = []
    rushed_heroes = []

    for h in heroes:
        hname = h.get("name", "Unknown")
        lvl = h.get("level", 0)
        max_lvl = get_scraped_th_max(hname, th) or th_max.get(hname) or h.get("maxLevel", 1)
        pct = round(lvl / max_lvl * 100) if max_lvl > 0 else 100

        if pct >= 90:
            status = "✅"
        elif pct >= 75:
            status = "⚠️"
        else:
            status = "❌"
            if hname not in rushed_heroes:
                rushed_heroes.append(hname)

        hero_lines.append(f"  • {hname}: {lvl}/{max_lvl} ({pct}%) {status}")

    # ── Troops Analysis ──────────────────────────────────────────────────
    home_troops = [
        t for t in data.get("troops", [])
        if t.get("village") == "home"
        and "Super" not in t.get("name", "")
        and not t.get("name", "").startswith("Super")
    ]
    total_troops = len(home_troops)
    troop_sum = 0
    maxed_troops = 0
    for t in home_troops:
        t_ml = get_scraped_th_max(t.get("name", ""), th) or th_max.get(t.get("name", "")) or t.get("maxLevel", 1)
        troop_sum += (t.get("level", 0) / t_ml * 100) if t_ml > 0 else 100
        if t.get("level", 0) >= t_ml:
            maxed_troops += 1
    
    troop_pct = round(troop_sum / total_troops) if total_troops > 0 else 100
    troop_status = "✅" if troop_pct >= 80 else "⚠️" if troop_pct >= 60 else "❌"

    # ── Spells Analysis ──────────────────────────────────────────────────
    home_spells = [s for s in data.get("spells", []) if s.get("village") == "home"]
    total_spells = len(home_spells)
    spell_sum = 0
    maxed_spells = 0
    for s in home_spells:
        s_ml = get_scraped_th_max(s.get("name", ""), th) or th_max.get(s.get("name", "")) or s.get("maxLevel", 1)
        spell_sum += (s.get("level", 0) / s_ml * 100) if s_ml > 0 else 100
        if s.get("level", 0) >= s_ml:
            maxed_spells += 1
            
    spell_pct = round(spell_sum / total_spells) if total_spells > 0 else 100
    spell_status = "✅" if spell_pct >= 80 else "⚠️" if spell_pct >= 60 else "❌"


    # ── Overall Verdict ──────────────────────────────────────────────────
    hero_avg_pct = 0
    if heroes:
        def _hero_ml(h):
            hname = h.get("name", "")
            return get_scraped_th_max(hname, th) or th_max.get(hname) or h.get("maxLevel", 1)
        hero_avg_pct = round(sum(
            h.get("level", 0) / _hero_ml(h) * 100
            for h in heroes if _hero_ml(h) > 0
        ) / len(heroes))

    overall_score = (hero_avg_pct * 0.5) + (troop_pct * 0.3) + (spell_pct * 0.2)

    if overall_score >= 85:
        verdict = "✅ **NOT RUSHED** — Solid account!"
        verdict_color = "🟢"
    elif overall_score >= 70:
        verdict = "⚠️ **SLIGHTLY RUSHED** — Some areas need work"
        verdict_color = "🟡"
    elif overall_score >= 50:
        verdict = "❌ **RUSHED** — Significant upgrades needed"
        verdict_color = "🔴"
    else:
        verdict = "💀 **HEAVILY RUSHED** — Major recovery needed"
        verdict_color = "🔴"

    # ── Build Output ─────────────────────────────────────────────────────
    text = (
        f"🔍 **Rush Audit — [{name}]({p_link})**\n"
        f"{E['th']} Town Hall: **{th}** | Score: **{round(overall_score)}%** {verdict_color}\n"
        f"`{norm_tag}`\n"
        f"{'─' * 30}\n"
    )

    if hero_lines:
        text += f"\n{E['hero']} **Heroes** (avg {hero_avg_pct}% of TH{th} max):\n"
        text += "\n".join(hero_lines) + "\n"
    else:
        text += f"\n{E['hero']} **Heroes:** None unlocked\n"

    text += (
        f"\n{E['troop']} Troops: {maxed_troops}/{total_troops} maxed ({troop_pct}%) {troop_status}"
        f"\n{E['spell']} Spells: {maxed_spells}/{total_spells} maxed ({spell_pct}%) {spell_status}"
    )

    text += (
        f"\n\n{'─' * 30}\n"
        f"📊 **Verdict:** {verdict}\n"
    )

    if rushed_heroes:
        text += f"⚠️ Heroes need attention: {', '.join(rushed_heroes)}\n"

    await msg.edit_text(text, parse_mode="Markdown", disable_web_page_preview=True)
