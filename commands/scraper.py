import json
import os
import urllib.request
import logging
import bs4
from telegram import Update
from telegram.ext import ContextTypes

OWNER_ID = int(os.getenv('OWNER_ID', '0'))
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_FILE = os.path.join(BASE_DIR, "th_max_levels.json")

def scrape_max_levels() -> dict:
    req = urllib.request.Request(
        'https://www.clash.ninja/guides/max-levels-for-each-th', 
        headers={'User-Agent': 'Mozilla/5.0'}
    )
    html = urllib.request.urlopen(req).read()
    soup = bs4.BeautifulSoup(html, 'html.parser')
    
    tables = soup.find_all('table', class_='all-th-overview')
    data = {}
    
    # We only want tables for:
    # - Troops (Home & Dark)
    # - Spells
    # - Siege Machines
    # - Heroes
    # - Pets
    # Usually these are tables index 5 to 10 on Clash Ninja
    for idx, table in enumerate(tables):
        if idx < 5: # Skip Defenses, Traps, Army Buildings, Resources, Walls
            continue
            
        headers = table.find('tr').find_all('th')
        if len(headers) <= 2:
            continue
            
        th_levels = []
        for h in headers[2:]:
            try:
                th_levels.append(int(h.text.strip()))
            except ValueError:
                pass
                
        for row in table.find_all('tr')[1:]:
            tds = row.find_all('td')
            if not tds:
                continue
            unit_name = tds[0].text.strip()
            
            # Avoid some extra items like "Walls" if they appear in later tables
            if unit_name in ["Walls", "TH", "None"]:
                continue
                
            unit_data = {}
            for i, td in enumerate(tds[1:]):
                if i < len(th_levels):
                    val = td.text.strip()
                    if val != '-':
                        try:
                            unit_data[str(th_levels[i])] = int(val)
                        except ValueError:
                            pass
            if unit_data:
                data[unit_name] = unit_data
                
    return data

def compute_diff(old_data: dict, new_data: dict) -> list:
    changes = []
    for unit, new_levels in new_data.items():
        if unit not in old_data:
            changes.append(f"• 🆕 **{unit}** added.")
            continue
        
        old_levels = old_data[unit]
        for th, new_lvl in new_levels.items():
            old_lvl = old_levels.get(th)
            if old_lvl is None:
                changes.append(f"• **{unit}**: TH{th} added (max {new_lvl}).")
            elif old_lvl != new_lvl:
                changes.append(f"• **{unit}**: TH{th} changed from {old_lvl} to {new_lvl}.")
                
    for unit in old_data:
        if unit not in new_data:
            changes.append(f"• ❌ **{unit}** removed.")
            
    return changes

async def scrap_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Scrape the latest TH max levels data: /scrap (Owner only)"""
    user_id = update.effective_user.id
    if OWNER_ID != 0 and user_id != OWNER_ID:
        await update.message.reply_text("❌ This command is available for the owner only.")
        return

    msg = await update.message.reply_text("🔄 Scraping latest max levels from Clash Ninja...")
    
    try:
        old_data = {}
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r") as f:
                try:
                    old_data = json.load(f)
                except Exception:
                    pass
                    
        data = scrape_max_levels()
        if not data:
            raise Exception("No data could be extracted.")
            
        changes = compute_diff(old_data, data)
        
        with open(DATA_FILE, "w") as f:
            json.dump(data, f, indent=4)
            
        if not changes:
            await msg.edit_text(f"✅ Successfully scraped {len(data)} units. No level changes detected.")
        else:
            diff_text = "\n".join(changes)
            # Telegram message limit is 4096, truncate if too long
            if len(diff_text) > 3000:
                diff_text = diff_text[:3000] + "\n... (truncated)"
            await msg.edit_text(f"✅ Successfully scraped! Changes detected:\n\n{diff_text}", parse_mode='Markdown')
            
        logging.info(f"Scraped max levels updated by {update.effective_user.first_name}")
    except Exception as e:
        await msg.edit_text(f"❌ Failed to scrape data: {e}")
        logging.error(f"Scrape error: {e}")

async def auto_scrap_job(context: ContextTypes.DEFAULT_TYPE):
    """Background job that scrapes and only notifies owner if changes are found."""
    if OWNER_ID == 0:
        return
        
    try:
        old_data = {}
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r") as f:
                try:
                    old_data = json.load(f)
                except Exception:
                    pass
                    
        data = scrape_max_levels()
        if not data:
            return
            
        changes = compute_diff(old_data, data)
        
        # We only save and notify if there's actually a difference
        # (or if it's the very first run and we don't have old data, though initial run usually happens manually)
        if changes:
            with open(DATA_FILE, "w") as f:
                json.dump(data, f, indent=4)
                
            diff_text = "\n".join(changes)
            if len(diff_text) > 3000:
                diff_text = diff_text[:3000] + "\n... (truncated)"
                
            text = f"🔄 **Automated Scraper Update!**\nChanges detected in max levels:\n\n{diff_text}"
            await context.bot.send_message(chat_id=OWNER_ID, text=text, parse_mode='Markdown')
            logging.info("Auto-scraper found changes and notified owner.")
    except Exception as e:
        logging.error(f"Auto-scraper error: {e}")
