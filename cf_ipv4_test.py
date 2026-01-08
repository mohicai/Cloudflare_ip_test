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
CONCURRENCY = 50
MAX_IPS = 100000


async def fetch_ips(url):
    """获取 Cloudflare IPv4 CIDR 列表"""
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            text = await resp.text()
            return text.strip().splitlines()


async def test_proxy():
    """测试代理是否可用（保持原逻辑）"""
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


async def test_ip(ip):
    """使用 curl 测试单个 IP 是否可联通，只要有返回值就算成功"""
    try:
        proc = await asyncio.create_subprocess_exec(
            "curl",
            "-s",
            "-o", "/dev/null",       # 丢弃 body
            "-w", "%{http_code}",    # 输出状态码
            f"http://{ip}",
            "--max-time", str(TIMEOUT),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        code = stdout.decode().strip()
        if code:  # 有返回值就算联通
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

    # 展开所有 IPv4 段为单个 IP，但只取前 MAX_IPS 个
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

    sem = asyncio.Semaphore(CONCURRENCY)

    async def sem_test(ip):
        async with sem:
            return await test_ip(ip)

    tasks = [sem_test(ip) for ip in all_ips]

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
        if len(unblocked) > 5:
            print("\n[INFO] 开始每分钟输出5个可访问IP...")
            for i in range(0, len(unblocked), 5):
                batch = unblocked[i:i+5]
                print(f"[PASS] {', '.join(batch)}")
                if i + 5 < len(unblocked):
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

    # 写入文件
    with open("blocked.txt", "w") as f:
        f.write("\n".join(blocked))
    with open("unblocked.txt", "w") as f:
        f.write("\n".join(unblocked))

    print(f"[INFO] 已保存结果到 blocked_{MAX_IPS}.txt 和 unblocked_{MAX_IPS}.txt")


if __name__ == "__main__":
    asyncio.run(main())