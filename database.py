import aiosqlite
import os

DB_PATH = "users.db"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS linked_accounts (
                telegram_id INTEGER PRIMARY KEY,
                coc_tag TEXT NOT NULL
            )
        ''')
        await db.commit()

async def link_account(telegram_id: int, coc_tag: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            INSERT INTO linked_accounts (telegram_id, coc_tag)
            VALUES (?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET coc_tag=excluded.coc_tag
        ''', (telegram_id, coc_tag))
        await db.commit()

async def get_linked_account(telegram_id: int) -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT coc_tag FROM linked_accounts WHERE telegram_id = ?', (telegram_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return row[0]
            return None
