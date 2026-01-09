import argparse
import ipaddress
import json
import requests

def cidr_size(cidr: str) -> int:
    """计算 CIDR 段的可用 IP 数量"""
    net = ipaddress.ip_network(cidr)
    return net.num_addresses - 2  # 去掉网络地址和广播地址

def split_large(cidr: str, target: int):
    """拆分大段，使其容量不超过目标值"""
    net = ipaddress.ip_network(cidr)
    size = cidr_size(cidr)
    if size <= target:
        return [cidr]

    new_prefix = net.prefixlen
    # 动态选择合适的前缀，直到子段容量 <= target
    while True:
        subnets = list(net.subnets(new_prefix=new_prefix))
        if cidr_size(str(subnets[0])) <= target or new_prefix >= 32:
            return [str(s) for s in subnets]
        new_prefix += 1

def fetch_cidrs():
    """从 Cloudflare 官方获取 IPv4 CIDR 段"""
    url = "https://www.cloudflare.com/ips-v4"
    resp = requests.get(url)
    resp.raise_for_status()
    return [line.strip() for line in resp.text.splitlines() if line.strip()]

def split_cidrs(jobs: int, cidrs: list):
    """均分 CIDR 段到指定数量的 job"""
    total = sum(cidr_size(c) for c in cidrs)
    target = total / jobs

    # 拆分大段
    expanded = []
    for c in cidrs:
        expanded.extend(split_large(c, target))

    segments = [(c, cidr_size(c)) for c in expanded]
    assignments = [[] for _ in range(jobs)]
    loads = [0] * jobs

    # 贪心分配：每次把最大段放到当前最轻的 job
    for cidr, size in sorted(segments, key=lambda x: -x[1]):
        idx = min(range(jobs), key=lambda i: loads[i])
        assignments[idx].append(cidr)
        loads[idx] += size

    return assignments, loads, total

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", type=int, required=True)
    args = parser.parse_args()

    cidrs = fetch_cidrs()
    assignments, loads, total = split_cidrs(args.jobs, cidrs)

    # 输出 JSON 给 workflow matrix
    print(json.dumps(assignments))

    # 写 job_summary.txt
    with open("job_summary.txt", "w") as f:
        f.write(f"总 IP 数: {total}\n")
        f.write(f"目标均分: {total/args.jobs:.0f} 每个 job\n\n")
        for i, (job, count) in enumerate(zip(assignments, loads), 1):
            f.write(f"Job {i}:\n")
            f.write(f"- CIDRs: {', '.join(job)}\n")
            f.write(f"- Total IPs: {count}\n\n")