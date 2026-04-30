import asyncio, coc, os
from dotenv import load_dotenv

async def main():
    load_dotenv('.env')
    client = coc.Client(load_game_data=coc.LoadGameData.always)
    await client.login(os.getenv('COC_EMAIL'), os.getenv('COC_PASSWORD'))
    try:
        # Search for a clan
        clans = await client.search_clans(name="Indian", limit=1)
        if clans:
            clan = await client.get_clan(clans[0].tag)
            m = clan.members[0]
            print(dir(m))
            print("TH:", getattr(m, 'town_hall', 'N/A'))
            print("XP:", getattr(m, 'exp_level', 'N/A'))
    except Exception as e:
        print("Error:", e)
    await client.close()

if __name__ == '__main__':
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
