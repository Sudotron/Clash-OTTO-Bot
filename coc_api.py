import httpx
import os
import urllib.parse
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://api.clashk.ing/v1"   # Official CoC proxy endpoints
STATS_URL = "https://api.clashk.ing"      # ClashK.ing custom stats endpoints


async def _fetch(base: str, endpoint: str) -> dict:
    headers = {"Accept": "application/json"}
    url = f"{base}{endpoint}"
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            response = await client.get(url, headers=headers)
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                return {"error": "Not Found. Tag might be incorrect."}
            elif response.status_code == 403:
                return {"error": "Forbidden. API Key might be invalid."}
            else:
                return {"error": f"API Error: Status {response.status_code}"}
        except httpx.TimeoutException:
            return {"error": "Request timed out. Try again later."}
        except Exception as e:
            return {"error": str(e)}


async def fetch_coc_data(endpoint: str) -> dict:
    return await _fetch(BASE_URL, endpoint)


async def fetch_stats_data(endpoint: str) -> dict:
    return await _fetch(STATS_URL, endpoint)


def format_tag(tag: str) -> str:
    tag = tag.strip().upper()
    if tag.startswith('#'):
        return urllib.parse.quote_plus(tag)
    return "%23" + tag


async def get_player(tag: str):
    return await fetch_coc_data(f"/players/{format_tag(tag)}")

async def get_player_stats(tag: str):
    return await fetch_stats_data(f"/player/{format_tag(tag)}/stats")

async def get_player_warhits(tag: str):
    return await fetch_stats_data(f"/player/{format_tag(tag)}/warhits")

async def get_clan(tag: str):
    return await fetch_coc_data(f"/clans/{format_tag(tag)}")

async def get_player_join_leave(tag: str, limit: int = 15):
    return await fetch_stats_data(f"/player/{format_tag(tag)}/join-leave?timestamp_start=0&time_stamp_end=9999999999&limit={limit}")

async def get_clan_members(tag: str):
    return await fetch_coc_data(f"/clans/{format_tag(tag)}/members")

async def get_clan_war(tag: str):
    return await fetch_coc_data(f"/clans/{format_tag(tag)}/currentwar")

async def get_previous_wars(tag: str, limit: int = 2):
    return await fetch_stats_data(f"/war/{format_tag(tag)}/previous?limit={limit}")
