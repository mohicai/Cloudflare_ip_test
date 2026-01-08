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
CONCURRENCY = 50  # 降低并发数以适应更少的IP测试
MAX_IPS = 10000  # 新增：最大测试IP数


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

    # 展开所有 IPv4 段为单个 IP，但只取前100个
    all_ips = []
    ip_count = 0
    
    for cidr in v4_cidrs:
        if ip_count >= MAX_IPS:
            break
            
        net = ipaddress.ip_network(cidr)
        for ip in net.hosts():
            if ip_count >= MAX_IPS:
                break
            all_ips.append(str(ip))
            ip_count += 1

    print(f"[INFO] 总共测试 {len(all_ips)} 个 IP（前 {MAX_IPS} 个）")

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

    # 实时显示成功IP（每分钟5个）
    print(f"\n[INFO] 可访问IP列表（共{len(unblocked)}个）：")
    if unblocked:
        print("[PASS]", ", ".join(unblocked))
        
        # 如果需要每分钟输出5个（但总共可能不到5个）
        if len(unblocked) > 5:
            print("\n[INFO] 开始每分钟输出5个可访问IP...")
            for i in range(0, len(unblocked), 5):
                batch = unblocked[i:i+5]
                print(f"[PASS] {', '.join(batch)}")
                if i + 5 < len(unblocked):  # 如果不是最后一批，则等待
                    await asyncio.sleep(60)
    else:
        print("[INFO] 没有找到可访问的IP")

    # 输出统计
    print(f"\n[SUMMARY] 测试完成，用时 {time.time() - start_time:.2f} 秒")
    print(f"[SUMMARY] 总共测试IP数: {len(all_ips)}")
    print(f"[SUMMARY] 可访问 IP 数量: {len(unblocked)}")
    print(f"[SUMMARY] 不可访问 IP 数量: {len(blocked)}")
    
    if unblocked:
        print(f"[SUMMARY] 成功率: {len(unblocked)/len(all_ips)*100:.2f}%")

    # 写入文件（文件名加前缀表示只测试了100个）
    with open(f"blocked.txt", "w") as f:
        f.write("\n".join(blocked))
    with open(f"unblocked.txt", "w") as f:
        f.write("\n".join(unblocked))

    print(f"[INFO] 已保存结果到 blocked_{MAX_IPS}.txt 和 unblocked_{MAX_IPS}.txt")


if __name__ == "__main__":
    asyncio.run(main())