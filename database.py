import aiosqlite
import os

base_dir = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(base_dir, "users.db")

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS linked_accounts (
                telegram_id INTEGER PRIMARY KEY,
                coc_tag TEXT NOT NULL
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS user_tags (
                telegram_id INTEGER,
                tag TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                PRIMARY KEY (telegram_id, tag)
            )
        ''')
        # Migrate old data silently
        await db.execute('''
            INSERT OR IGNORE INTO user_tags (telegram_id, tag, entity_type)
            SELECT telegram_id, coc_tag, 'player' FROM linked_accounts
        ''')
        await db.commit()

async def link_account(telegram_id: int, tag: str, entity_type: str = 'player'):
    async with aiosqlite.connect(DB_PATH) as db:
        # Also maintain legacy for old commands just in case
        if entity_type == 'player':
            await db.execute('''
                INSERT INTO linked_accounts (telegram_id, coc_tag)
                VALUES (?, ?)
                ON CONFLICT(telegram_id) DO UPDATE SET coc_tag=excluded.coc_tag
            ''', (telegram_id, tag))
        
        await db.execute('''
            INSERT OR REPLACE INTO user_tags (telegram_id, tag, entity_type)
            VALUES (?, ?, ?)
        ''', (telegram_id, tag, entity_type))
        await db.commit()

async def get_linked_account(telegram_id: int, entity_type: str = 'player') -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT tag FROM user_tags WHERE telegram_id = ? AND entity_type = ? LIMIT 1", (telegram_id, entity_type)) as cursor:
            row = await cursor.fetchone()
            if row: return row[0]
            
        if entity_type == 'player':
            async with db.execute('SELECT coc_tag FROM linked_accounts WHERE telegram_id = ?', (telegram_id,)) as cursor:
                row = await cursor.fetchone()
                if row: return row[0]
        return None

async def get_all_linked_tags(telegram_id: int, entity_type: str = None) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        query = "SELECT tag FROM user_tags WHERE telegram_id = ?"
        params = [telegram_id]
        if entity_type:
            query += " AND entity_type = ?"
            params.append(entity_type)
            
        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            if rows:
                return [row[0] for row in rows]
                
        # Fallback to legacy
        if not entity_type or entity_type == 'player':
            async with db.execute('SELECT coc_tag FROM linked_accounts WHERE telegram_id = ?', (telegram_id,)) as cursor:
                rows = await cursor.fetchall()
                result = [row[0] for row in rows]
                # auto-migrate
                for t in result:
                    await db.execute("INSERT OR IGNORE INTO user_tags (telegram_id, tag, entity_type) VALUES (?, ?, 'player')", (telegram_id, t))
                await db.commit()
                return result
        return []
