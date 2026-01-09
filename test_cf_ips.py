import argparse
import asyncio
import ipaddress
import time
import random
from tqdm import tqdm

PROXY_URL = "http://f2O9Sw2sqd:zbZEBEqbho@120.230.229.77:35831"

TIMEOUT = 3
CONCURRENCY = 50

async def test_proxy():
    """测试代理是否可用（使用百度 URL）"""
    try:
        proc = await asyncio.create_subprocess_exec(
            "curl","-s","-o","/dev/null","-w","%{http_code}",
            "http://www.baidu.com","--max-time",str(TIMEOUT),
            "-x", PROXY_URL,
            stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        code = stdout.decode().strip()
        if code == "200":
            print(f"[INFO] 代理可用 (返回码 {code})")
            return True
        else:
            print(f"[WARN] 代理不可用 (返回码 {code}, 错误: {stderr.decode().strip()})")
            return False
    except Exception as e:
        print(f"[ERROR] 代理测试异常: {e}")
        return False

async def test_ip(ip, use_proxy=True):
    try:
        cmd = [
            "curl","-s","-o","/dev/null","-w","%{http_code}",
            f"http://{ip}","--max-time",str(TIMEOUT)
        ]
        if use_proxy:
            cmd.extend(["-x", PROXY_URL])

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        code = stdout.decode().strip()
        err = stderr.decode().strip()
        if code and code != "000":
            return ip, True, err
        else:
            return ip, False, err or "No response"
    except Exception as e:
        return ip, False, f"Exception: {e}"

async def main(cidr_file, refresh_interval, limit, use_proxy):
    # ✅ 启动时测试代理
    if use_proxy:
        await test_proxy()

    # 从 workflow 提供的文件读取 CIDR 段
    with open(cidr_file) as f:
        cidrs = [line.strip() for line in f if line.strip()]

    all_ips = []
    for cidr in cidrs:
        net = ipaddress.ip_network(cidr)
        for ip in net.hosts():
            all_ips.append(str(ip))

    if limit != "all":
        max_ips = int(limit)
        all_ips = all_ips[:max_ips]

    total_tasks = len(all_ips)
    print(f"[INFO] 本次测试 {total_tasks} 个 IP (CIDR 段数 {len(cidrs)}, limit={limit}, proxy={'ON' if use_proxy else 'OFF'})")

    sem = asyncio.Semaphore(CONCURRENCY)
    async def sem_test(ip):
        async with sem:
            return await test_ip(ip, use_proxy)

    tasks = [sem_test(ip) for ip in all_ips]

    success, fail = 0, 0
    unblocked_list, blocked_list, error_list = [], [], []
    last_refresh = time.time()
    start_time = time.time()
    pbar = tqdm(total=total_tasks, desc="测试进度", dynamic_ncols=True)

    for idx, f in enumerate(asyncio.as_completed(tasks), 1):
        ip, ok, err = await f
        if ok:
            success += 1
            unblocked_list.append(ip)
        else:
            fail += 1
            blocked_list.append(ip)
            error_list.append(f"{ip}: {err}")

        now = time.time()
        if now - last_refresh >= refresh_interval:
            elapsed = now - start_time
            avg_time = elapsed / idx
            remaining = total_tasks - idx
            eta_seconds = int(avg_time * remaining)
            eta_str = time.strftime("%H:%M:%S", time.gmtime(eta_seconds))

            rate = success/(success+fail)*100 if (success+fail)>0 else 0
            pbar.update(idx - pbar.n)
            pbar.set_description(f"成功:{success} 失败:{fail} 成功率:{rate:.2f}% ETA:{eta_str}")
            last_refresh = now

    pbar.update(total_tasks - pbar.n)
    pbar.close()

    print(f"\n[SUMMARY] 成功:{success} 失败:{fail} 成功率:{success/(success+fail)*100:.2f}%")
    if unblocked_list:
        print("\n随机成功样本:", ", ".join(random.sample(unblocked_list, min(10,len(unblocked_list)))))
    if blocked_list:
        print("\n随机失败样本:", ", ".join(random.sample(blocked_list, min(10,len(blocked_list)))))

    # ✅ 输出结果文件，供 workflow 汇总
    with open("blocked.txt", "w") as f:
        f.write("\n".join(blocked_list))
    with open("unblocked.txt", "w") as f:
        f.write("\n".join(unblocked_list))
    with open("curl_errors.log", "w") as f:
        f.write("\n".join(error_list))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cidr-file", required=True, help="CIDR 段文件 (workflow 提供)")
    parser.add_argument("--interval", type=int, default=5)
    parser.add_argument("--limit", default="1000", help="测试数量 (数字 或 all)")
    parser.add_argument("--no-proxy", action="store_true", help="禁用代理测试")
    args = parser.parse_args()
    asyncio.run(main(args.cidr_file, args.interval, args.limit, not args.no_proxy))