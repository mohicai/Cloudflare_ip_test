import requests
import ipaddress
import time
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm   # 进度条库

# Cloudflare IPv4 段列表
CF_IPS_V4 = "https://www.cloudflare.com/ips-v4"

# 使用 Mihomo 本地代理端口
proxies = {
    "http": "http://127.0.0.1:7890",
    "https": "http://127.0.0.1:7890"
}


def fetch_ips(timeout):
    resp = requests.get(CF_IPS_V4, timeout=timeout)
    resp.raise_for_status()
    return resp.text.strip().splitlines()


def test_proxy(timeout):
    print("[INFO] 正在测试代理连通性...")
    try:
        resp = requests.get("https://www.cloudflare.com",
                            proxies=proxies,
                            timeout=timeout,
                            verify=False)
        if resp.status_code == 200:
            print("[INFO] 代理可用，返回状态码 200")
            return True
        else:
            print(f"[WARN] 代理返回状态码 {resp.status_code}")
            return False
    except Exception as e:
        print(f"[ERROR] 代理不可用: {e}")
        return False


def test_ip(ip, timeout):
    print(f"[DEBUG] 开始测试 IP: {ip}")
    try:
        resp = requests.get(f"https://{ip}",
                            proxies=proxies,
                            timeout=timeout,
                            verify=False)
        if resp.status_code == 200:
            print(f"[PASS] IP {ip} 可访问")
            return ip, True
        else:
            print(f"[FAIL] IP {ip} 返回状态码 {resp.status_code}")
            return ip, False
    except Exception as e:
        print(f"[FAIL] IP {ip} 测试失败: {e}")
        return ip, False


def main(limit, concurrency, timeout):
    start_time = time.time()

    # 测试代理
    if not test_proxy(timeout):
        print("[FATAL] 代理不可用，退出程序")
        return

    # 获取 CF IPv4 CIDR 列表
    v4_cidrs = fetch_ips(timeout)
    print(f"[INFO] 获取到 {len(v4_cidrs)} 个 IPv4 段")

    # 展开所有 IPv4 段为单个 IP
    all_ips = []
    for cidr in v4_cidrs:
        net = ipaddress.ip_network(cidr)
        all_ips.extend([str(ip) for ip in net.hosts()])

    # 限制测试数量
    if limit and len(all_ips) > limit:
        all_ips = all_ips[:limit]
        print(f"[INFO] 限制测试数量为 {limit} 个 IP")

    print(f"[INFO] 总共需要测试 {len(all_ips)} 个 IP")

    blocked, unblocked = [], []

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {executor.submit(test_ip, ip, timeout): ip for ip in all_ips}
        for future in tqdm(as_completed(futures), total=len(futures), desc="测试进度"):
            ip, ok = future.result()
            if ok:
                unblocked.append(ip)
            else:
                blocked.append(ip)

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
    parser = argparse.ArgumentParser(description="Cloudflare IP 测试工具")
    parser.add_argument("--limit", type=int, default=1000,
                        help="限制测试的 IP 数量，默认 1000")
    parser.add_argument("--concurrency", type=int, default=50,
                        help="并发线程数，默认 50")
    parser.add_argument("--timeout", type=int, default=3,
                        help="请求超时时间（秒），默认 3")
    args = parser.parse_args()
    main(args.limit, args.concurrency, args.timeout)