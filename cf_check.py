import aiohttp
import asyncio

CF_IPS_V4 = "https://www.cloudflare.com/ips-v4"
CF_IPS_V6 = "https://www.cloudflare.com/ips-v6"

TIMEOUT = 3
CONCURRENCY = 50

async def fetch_ips(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            text = await resp.text()
            return text.strip().splitlines()

async def test_ip(ip, session):
    try:
        async with session.get(f"https://{ip}", timeout=TIMEOUT, ssl=False) as resp:
            return ip, resp.status == 200
    except Exception:
        return ip, False

async def main():
    v4_ips = await fetch_ips(CF_IPS_V4)
    v6_ips = await fetch_ips(CF_IPS_V6)
    all_ips = v4_ips + v6_ips

    blocked, unblocked = [], []
    connector = aiohttp.TCPConnector(limit=CONCURRENCY)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [test_ip(ip.split("/")[0], session) for ip in all_ips]
        results = await asyncio.gather(*tasks)

    for ip, ok in results:
        if ok:
            unblocked.append(ip)
        else:
            blocked.append(ip)

    with open("blocked.txt", "w") as f:
        f.write("\n".join(blocked))
    with open("unblocked.txt", "w") as f:
        f.write("\n".join(unblocked))

if __name__ == "__main__":
    asyncio.run(main())