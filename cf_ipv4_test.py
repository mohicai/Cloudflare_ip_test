import aiohttp
import asyncio
import ipaddress
import time
from tqdm import tqdm

CF_IPS_V4 = "https://www.cloudflare.com/ips-v4"
PROXY_URL = "http://f2O9Sw2sqd:zbZEBEqbho@120.230.229.77:35931"

TIMEOUT = 3
CONCURRENCY = 50
MAX_IPS = 1000


async def fetch_ips(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            text = await resp.text()
            return text.strip().splitlines()


async def test_proxy():
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
    """curl 测试 + 捕获错误日志"""
    try:
        proc = await asyncio.create_subprocess_exec(
            "curl",
            "-s",
            "-o", "/dev/null",
            "-w", "%{http_code}",
            f"http://{ip}",
            "--max-time", str(TIMEOUT),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()

        code = stdout.decode().strip()
        err = stderr.decode().strip()

        if code:
            return ip, True, err
        else:
            return ip, False, err or "No response"

    except Exception as e:
        return ip, False, f"Exception: {e}"


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

    # 展开 IP
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

    sem = asyncio.Semaphore(CONCURRENCY)

    async def sem_test(ip):
        async with sem:
            return await test_ip(ip)

    tasks = [sem_test(ip) for ip in all_ips]

    # 实时写入文件
    blocked_file = open("blocked.txt", "a")
    unblocked_file = open("unblocked.txt", "a")
    error_log = open("curl_errors.log", "a")

    success = 0
    fail = 0

    pbar = tqdm(
        asyncio.as_completed(tasks),
        total=len(tasks),
        desc="测试进度",
        dynamic_ncols=True
    )

    for f in pbar:
        ip, ok, err = await f

        if ok:
            success += 1
            unblocked_file.write(ip + "\n")
            unblocked_file.flush()
        else:
            fail += 1
            blocked_file.write(ip + "\n")
            blocked_file.flush()

            if err:
                error_log.write(f"{ip} -> {err}\n")
                error_log.flush()

        # 更新进度条显示
        rate = success / (success + fail) * 100
        pbar.set_description(
            f"测试进度 | 成功: {success} | 失败: {fail} | 成功率: {rate:.2f}%"
        )

    blocked_file.close()
    unblocked_file.close()
    error_log.close()

    print(f"\n[SUMMARY] 测试完成，用时 {time.time() - start_time:.2f} 秒")
    print(f"[SUMMARY] 成功: {success} 失败: {fail} 成功率: {success/(success+fail)*100:.2f}%")
    print("[INFO] 结果已实时写入 blocked.txt / unblocked.txt / curl_errors.log")


if __name__ == "__main__":
    asyncio.run(main())