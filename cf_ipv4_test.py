import aiohttp
import asyncio
import ipaddress
import time
import sys
import random

CF_IPS_V4 = "https://www.cloudflare.com/ips-v4"
PROXY_URL = "http://f2O9Sw2sqd:zbZEBEqbho@120.230.229.77:35831"

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

        # 000 表示失败
        if code and code != "000":
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
    last_print = time.time()

    unblocked_list = []
    blocked_list = []

    for idx, f in enumerate(asyncio.as_completed(tasks), 1):
        ip, ok, err = await f

        if ok:
            success += 1
            unblocked_file.write(ip + "\n")
            unblocked_file.flush()
            unblocked_list.append(ip)
        else:
            fail += 1
            blocked_file.write(ip + "\n")
            blocked_file.flush()
            blocked_list.append(ip)
            if err:
                error_log.write(f"{ip} -> {err}\n")
                error_log.flush()

        # 每隔 5 秒打印一次进度 + 随机样本
        now = time.time()
        if now - last_print >= 5:
            rate = success / (success + fail) * 100
            print(f"[INFO] 测试进度 | 成功: {success} | 失败: {fail} | 成功率: {rate:.2f}% ({idx}/{len(tasks)})")

            if unblocked_list:
                sample_success = random.sample(unblocked_list, min(2, len(unblocked_list)))
                print(f"[INFO] 随机成功样本: {', '.join(sample_success)}")

            if blocked_list:
                sample_fail = random.sample(blocked_list, min(2, len(blocked_list)))
                print(f"[INFO] 随机失败样本: {', '.join(sample_fail)}")

            last_print = now

    blocked_file.close()
    unblocked_file.close()
    error_log.close()

    print(f"\n[SUMMARY] 测试完成，用时 {time.time() - start_time:.2f} 秒")
    print(f"[SUMMARY] 成功: {success} 失败: {fail} 成功率: {success/(success+fail)*100:.2f}%")
    print("[INFO] 结果已实时写入 blocked.txt / unblocked.txt / curl_errors.log")

    # 随机打印 10 个成功和失败的 IP
    if unblocked_list:
        sample_success = random.sample(unblocked_list, min(10, len(unblocked_list)))
        print(f"\n[INFO] 随机成功 IP 示例（共 {len(unblocked_list)} 个）：")
        print(", ".join(sample_success))

    if blocked_list:
        sample_fail = random.sample(blocked_list, min(10, len(blocked_list)))
        print(f"\n[INFO] 随机失败 IP 示例（共 {len(blocked_list)} 个）：")
        print(", ".join(sample_fail))


if __name__ == "__main__":
    asyncio.run(main())