import argparse
import asyncio
import ipaddress
import time
from tqdm import tqdm

PROXY_URL = "http://f2O9Sw2sqd:zbZEBEqbho@120.230.229.77:35831"  # ⚠️替换成你的代理
TIMEOUT = 3
CONCURRENCY = 50

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
    # 从文件读取 CIDR 段
    with open(cidr_file) as f:
        cidrs = [line.strip() for line in f if line.strip()]

    # 展开 CIDR 段为 IP 列表
    all_ips = []
    for cidr in cidrs:
        net = ipaddress.ip_network(cidr)
        all_ips.extend([str(ip) for ip in net.hosts()])

    if limit != "all":
        all_ips = all_ips[:int(limit)]

    total_tasks = len(all_ips)
    print(f"[INFO] 本次测试 {total_tasks} 个 IP (段数 {len(cidrs)}, proxy={'ON' if use_proxy else 'OFF'})")

    sem = asyncio.Semaphore(CONCURRENCY)
    async def sem_test(ip):
        async with sem:
            return await test_ip(ip, use_proxy)

    tasks = [sem_test(ip) for ip in all_ips]
    success, fail = 0, 0
    unblocked, blocked, errors = [], [], []
    start_time = time.time()
    last_refresh = start_time
    pbar = tqdm(total=total_tasks, desc="测试进度", dynamic_ncols=True)

    done_count = 0
    for idx, f in enumerate(asyncio.as_completed(tasks), 1):
        ip, ok, err = await f
        if ok:
            success += 1
            unblocked.append(ip)
        else:
            fail += 1
            blocked.append(ip)
            errors.append(f"{ip}: {err}")
        done_count += 1

        # 每隔 refresh_interval 秒刷新一次进度条和 ETA
        now = time.time()
        if now - last_refresh >= refresh_interval or idx == total_tasks:
            elapsed = now - start_time
            ips_per_sec = done_count / elapsed if elapsed > 0 else 0
            remaining = total_tasks - idx
            eta = remaining / ips_per_sec if ips_per_sec > 0 else 0

            # 更新进度条位置和附加信息
            pbar.n = idx
            pbar.refresh()
            pbar.set_postfix({
                "成功": success,
                "失败": fail,
                "ETA": f"{eta:.0f}s"
            })
            last_refresh = now

    pbar.close()
    elapsed = time.time() - start_time
    print(f"[SUMMARY] 成功:{success} 失败:{fail} 成功率:{success/(success+fail)*100:.2f}% 耗时:{elapsed:.1f}s")

    # 输出结果文件
    with open("blocked.txt","w") as f: f.write("\n".join(blocked))
    with open("unblocked.txt","w") as f: f.write("\n".join(unblocked))
    with open("curl_errors.log","w") as f: f.write("\n".join(errors))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cidr-file", required=True, help="CIDR 段文件 (workflow 提供)")
    parser.add_argument("--interval", type=int, default=5, help="进度条刷新间隔 (秒)")
    parser.add_argument("--limit", default="1000", help="测试数量 (数字 或 all)")
    parser.add_argument("--no-proxy", action="store_true", help="禁用代理测试")
    args = parser.parse_args()
    asyncio.run(main(args.cidr_file, args.interval, args.limit, not args.no_proxy))