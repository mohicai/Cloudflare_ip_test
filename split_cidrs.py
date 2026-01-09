import argparse
import ipaddress
import json
import requests

def cidr_size(cidr: str) -> int:
    """计算 CIDR 段的可用 IP 数量"""
    net = ipaddress.ip_network(cidr)
    return net.num_addresses - 2  # 去掉网络地址和广播地址

def split_large(cidr: str, target: int):
    """递归拆分大段，直到每个子段 ≤ target/2 或前缀达到 /22"""
    net = ipaddress.ip_network(cidr)
    size = cidr_size(cidr)
    if size <= target / 2 or net.prefixlen >= 22:
        return [cidr]

    # 拆分成两个更小的子网
    subnets = list(net.subnets(prefixlen_diff=1))
    result = []
    for s in subnets:
        result.extend(split_large(str(s), target))
    return result

def fetch_cidrs():
    """从 Cloudflare 官方获取 IPv4 CIDR 段"""
    url = "https://www.cloudflare.com/ips-v4"
    resp = requests.get(url)
    resp.raise_for_status()
    return [line.strip() for line in resp.text.splitlines() if line.strip()]

def balance_assignments(assignments, loads, target):
    """二次均衡：把超载 job 的子段挪到轻载 job"""
    for _ in range(20):  # 最多迭代 20 次
        max_idx = max(range(len(loads)), key=lambda i: loads[i])
        min_idx = min(range(len(loads)), key=lambda i: loads[i])
        if loads[max_idx] - loads[min_idx] < target * 0.05:  # 差距小于 5% 就停止
            break
        # 从超载 job 挪一个最小的子段到轻载 job
        if len(assignments[max_idx]) > 1:
            smallest = min(assignments[max_idx], key=lambda c: cidr_size(c))
            assignments[max_idx].remove(smallest)
            assignments[min_idx].append(smallest)
            loads[max_idx] -= cidr_size(smallest)
            loads[min_idx] += cidr_size(smallest)
    return assignments, loads

def split_cidrs(jobs: int, cidrs: list):
    """均分 CIDR 段到指定数量的 job"""
    total = sum(cidr_size(c) for c in cidrs)
    target = total / jobs

    # 拆分大段
    expanded = []
    for c in cidrs:
        expanded.extend(split_large(c, target))

    segments = sorted([(c, cidr_size(c)) for c in expanded], key=lambda x: -x[1])
    assignments = [[] for _ in range(jobs)]
    loads = [0] * jobs

    # 贪心分配：每次把最大段放到当前最轻的 job
    for cidr, size in segments:
        idx = min(range(jobs), key=lambda i: loads[i])
        assignments[idx].append(cidr)
        loads[idx] += size

    # 二次均衡
    assignments, loads = balance_assignments(assignments, loads, target)

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