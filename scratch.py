import asyncio
import httpx

async def main():
    async with httpx.AsyncClient() as s:
        print("\nFetching previous wars...")
        r = await s.get('https://api.clashk.ing/war/%232RPR8G20C/previous?limit=2')
        data = r.json()
        
        items = data.get('items', [])
        print("Past wars count:", len(items))
        if items:
            war = items[0]
            print("Keys in previous war:", war.keys())
            clan = war.get('clan', {})
            print("Members in clan?", 'members' in clan)
            if 'members' in clan:
                print("Members array size:", len(clan['members']))
                if clan['members']:
                    print("First member keys:", clan['members'][0].keys())

asyncio.run(main())
