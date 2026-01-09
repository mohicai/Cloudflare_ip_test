import argparse
import ipaddress
import json
import requests

def cidr_size(cidr: str) -> int:
    net = ipaddress.ip_network(cidr)
    return net.num_addresses - 2

def split_to_22(cidr: str):
    """递归拆分到 /22"""
    net = ipaddress.ip_network(cidr)
    if net.prefixlen >= 22:
        return [str(net)]
    subnets = list(net.subnets(prefixlen_diff=1))
    result = []
    for s in subnets:
        result.extend(split_to_22(str(s)))
    return result

def fetch_cidrs():
    url = "https://www.cloudflare.com/ips-v4"
    resp = requests.get(url)
    resp.raise_for_status()
    return [line.strip() for line in resp.text.splitlines() if line.strip()]

def split_cidrs(jobs: int, cidrs: list):
    total = sum(cidr_size(c) for c in cidrs)

    # 拆分到 /22
    expanded = []
    for c in cidrs:
        expanded.extend(split_to_22(c))

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

    print(json.dumps(assignments))

    with open("job_summary.txt", "w") as f:
        f.write(f"总 IP 数: {total}\n")
        f.write(f"目标均分: {total/args.jobs:.0f} 每个 job\n\n")
        for i, (job, count) in enumerate(zip(assignments, loads), 1):
            f.write(f"Job {i}:\n")
            f.write(f"- CIDRs: {', '.join(job)}\n")
            f.write(f"- Total IPs: {count}\n\n")