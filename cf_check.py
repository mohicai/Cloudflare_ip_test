import aiohttp
import asyncio
import ipaddress

# Cloudflare IPv4 段列表
CF_IPS_V4 = "https://www.cloudflare.com/ips-v4"

# Mihomo HTTP代理配置
PROXY_URL = "http://cloudnproxy.baidu.com:443"
PROXY_HEADERS = {
    "X-T5-Auth": "683556433",
    "Host": "153.3.236.22:443"
}

TIMEOUT = 3
CONCURRENCY = 100


async def fetch_ips(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            text = await resp.text()
            return text.strip().splitlines()


async def test_ip(ip, session):
    try:
        async with session.get(
            f"https://{ip}",
            proxy=PROXY_URL,
            headers=PROXY_HEADERS,
            timeout=TIMEOUT,
            ssl=False
        ) as resp:
            return ip, resp.status == 200
    except Exception:
        return ip, False


async def main():
    # 获取 CF IPv4 CIDR 列表
    v4_cidrs = await fetch_ips(CF_IPS_V4)

    # 展开所有 IPv4 段为单个 IP
    all_ips = []
    for cidr in v4_cidrs:
        net = ipaddress.ip_network(cidr)
        all_ips.extend([str(ip) for ip in net.hosts()])

    blocked, unblocked = [], []

    connector = aiohttp.TCPConnector(limit=CONCURRENCY)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [test_ip(ip, session) for ip in all_ips]
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