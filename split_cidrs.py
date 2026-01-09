import argparse
import ipaddress
import json
import requests

def cidr_size(cidr):
    net = ipaddress.ip_network(cidr)
    return net.num_addresses - 2

def fetch_cidrs():
    url = "https://www.cloudflare.com/ips-v4"
    resp = requests.get(url)
    resp.raise_for_status()
    return [line.strip() for line in resp.text.splitlines() if line.strip()]

def split_cidrs(jobs, cidrs):
    segments = [(c, cidr_size(c)) for c in cidrs]
    total = sum(s for _, s in segments)
    target = total / jobs

    assignments = [[] for _ in range(jobs)]
    loads = [0] * jobs

    # 贪心分配：大段优先，放到当前最轻的 job
    for cidr, size in sorted(segments, key=lambda x: -x[1]):
        idx = min(range(jobs), key=lambda i: loads[i])
        assignments[idx].append(cidr)
        loads[idx] += size

    return assignments

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", type=int, required=True)
    args = parser.parse_args()

    cidrs = fetch_cidrs()
    assignments = split_cidrs(args.jobs, cidrs)
    print(json.dumps(assignments))