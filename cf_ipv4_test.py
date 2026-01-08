import aiohttp
import asyncio
import ipaddress
import time
from tqdm import tqdm

# Cloudflare IPv4 段列表
CF_IPS_V4 = "https://www.cloudflare.com/ips-v4"

# Mihomo HTTP代理配置（带账号密码）
PROXY_URL = "http://f2O9Sw2sqd:zbZEBEqbho@120.230.229.77:35933"

TIMEOUT = 3
CONCURRENCY = 100


async def fetch_ips(url):
    """获取 Cloudflare IPv4 CIDR 列表"""
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            text = await resp.text()
            return text.strip().splitlines()


async def test_proxy():
    """测试代理是否可用"""
    print("[INFO] 正在测试代理连通性...")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://www.cloudflare.com",
                proxy=PROXY_URL,
                timeout=TIMEOUT,
                ssl=False
            ) as resp:
                if resp.status == 200:
                    print("[INFO] 代理可用，返回状态码 200")
                    return True
                else:
                    print(f"[WARN] 代理返回状态码 {resp.status}")
                    return False
    except Exception as e:
        print(f"[ERROR] 代理不可用: {e}")
        return False


async def test_ip(ip, session):
    """测试单个 IP 是否可访问"""
    try:
        async with session.get(
            f"https://{ip}",
            proxy=PROXY_URL,
            timeout=TIMEOUT,
            ssl=False
        ) as resp:
            if resp.status == 200:
                return ip, True
            else:
                return ip, False
    except Exception:
        return ip, False


async def main():
    start_time = time.time()

    # 测试代理
    proxy_ok = await test_proxy()
    if not proxy_ok:
        print("[FATAL] 代理不可用，退出程序")
        return

    # 获取 CF IPv4 CIDR 列表
    v4_cidrs = await fetch_ips(CF_IPS_V4)
    print(f"[INFO] 获取到 {len(v4_cidrs)} 个 IPv4 段")

    # 展开所有 IPv4 段为单个 IP
    all_ips = []
    for cidr in v4_cidrs:
        net = ipaddress.ip_network(cidr)
        all_ips.extend([str(ip) for ip in net.hosts()])

    print(f"[INFO] 总共需要测试 {len(all_ips)} 个 IP")

    blocked, unblocked = [], []

    connector = aiohttp.TCPConnector(limit=CONCURRENCY)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [test_ip(ip, session) for ip in all_ips]

        # 使用 tqdm 显示进度条
        results = []
        for f in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="测试进度"):
            ip, ok = await f
            results.append((ip, ok))

    # 分类结果
    for ip, ok in results:
        if ok:
            unblocked.append(ip)
        else:
            blocked.append(ip)

    # 每分钟显示 5 个成功 IP
    print("[INFO] 开始输出可访问 IP（每分钟 5 个）...")
    for i in range(0, len(unblocked), 5):
        batch = unblocked[i:i+5]
        print("[PASS]", ", ".join(batch))
        await asyncio.sleep(60)  # 每分钟输出一次

    # 输出统计
    print(f"[SUMMARY] 测试完成，用时 {time.time() - start_time:.2f} 秒")
    print(f"[SUMMARY] 可访问 IP 数量: {len(unblocked)}")
    print(f"[SUMMARY] 不可访问 IP 数量: {len(blocked)}")

    # 写入文件
    with open("blocked.txt", "w") as f:
        f.write("\n".join(blocked))
    with open("unblocked.txt", "w") as f:
        f.write("\n".join(unblocked))

    print("[INFO] 已保存结果到 blocked.txt 和 unblocked.txt")


if __name__ == "__main__":
    asyncio.run(main())