import argparse
import asyncio
import ipaddress
import os
import time
from tqdm import tqdm

import requests
from urllib.parse import urlparse

def resolve_proxy(domain_url, username, password):
    """
    访问域名，跟随重定向，解析最终 IP 和端口，返回代理 URL
    """
    try:
        resp = requests.get(domain_url, allow_redirects=True, timeout=5)
        final_url = resp.url
        parsed = urlparse(final_url)
        ip = parsed.hostname
        port = parsed.port
        if not ip or not port:
            raise ValueError(f"无法解析最终地址: {final_url}")
        if username and password:
            proxy_url = f"http://{username}:{password}@{ip}:{port}"
        else:
            proxy_url = f"http://{ip}:{port}"
        return proxy_url
    except Exception as e:
        print(f"[ERROR] 解析代理失败: {e}")
        return None

# 从 GitHub Secrets 注入的环境变量读取
domain_url = os.environ.get("PROXY_DOMAIN_URL")
username   = os.environ.get("PROXY_USERNAME")
password   = os.environ.get("PROXY_PASSWORD")

PROXY_URL = resolve_proxy(domain_url, username, password)

print("PROXY_URL:")
print(domain_url)

TIMEOUT = 3
CONCURRENCY = 50

async def test_proxy():
    """测试代理是否能正常访问百度"""
    try:
        cmd = [
            "curl","-s","-o","/dev/null","-w","%{http_code}",
            "https://www.baidu.com","--max-time","15",
            "-x", PROXY_URL
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        code = stdout.decode().strip()
        if code == "200":
            print("[INFO] 代理可用，成功访问百度")
            return True
        else:
            print(f"[ERROR] 代理不可用，返回码 {code}")
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
    if use_proxy:
        ok = await test_proxy()
        if not ok:
            print("[FATAL] 代理不可用，退出测试")
            return

    with open(cidr_file) as f:
        cidrs = [line.strip() for line in f if line.strip()]

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

        now = time.time()
        if now - last_refresh >= refresh_interval or idx == total_tasks:
            elapsed = now - start_time
            ips_per_sec = done_count / elapsed if elapsed > 0 else 0
            remaining = total_tasks - idx
            eta = remaining / ips_per_sec if ips_per_sec > 0 else 0

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