import asyncio, coc, os
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))

async def test():
    c = coc.Client(load_game_data=coc.LoadGameData(always=True))
    await c.login(os.getenv('COC_EMAIL'), os.getenv('COC_PASSWORD'))
    p = await c.get_player('#YVPRUQ9VP')
    th = p.town_hall
    print(f'TH: {th}')
    for h in p.heroes:
        if h.is_home_base:
            th_max = h.get_max_level_for_townhall(th)
            print(f'{h.name}: level={h.level}, game_max={h.max_level}, th_max={th_max}')
    await c.close()

asyncio.run(test())
