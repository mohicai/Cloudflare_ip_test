# Cloudflare_ip_test
---

Cloudflare IP Test

本项目用于自动化测试 Cloudflare IPv4 段的可访问性，并将最终结果（blocked.txt、unblocked.txt、curl_errors.log）直接推送到仓库的 master 分支。

测试过程完全由 GitHub Actions 执行，支持并行任务、动态 CIDR 均分、进度条刷新、预计完成时间（ETA）等功能。

---

✨ 功能特性

🔹 自动获取 Cloudflare 官方 IPv4 段
脚本会从 https://www.cloudflare.com/ips-v4 拉取最新 CIDR 列表，确保测试数据始终最新。

🔹 智能均分 CIDR
大段（如 /13、/14、/15）会自动拆分成更小的子段，确保每个 job 的 IP 数量尽可能平均。

🔹 并行测试
你可以指定 job 数量（默认 20），GitHub Actions 会并行执行测试，加快整体速度。

🔹 实时进度条 + ETA
每隔 N 秒（默认 5 秒）刷新一次进度条，显示：

- 当前成功数  
- 当前失败数  
- 预计完成时间（ETA）  

🔹 自动合并结果
所有 job 的结果会自动合并到：

- merged/blocked.txt
- merged/unblocked.txt
- merged/curl_errors.log

🔹 自动推送到 master
测试完成后，结果会自动 commit 并推送到 master 分支。

---

📁 文件结构

`
.
├── split_cidrs.py        # 负责均分 Cloudflare CIDR 段
├── testcfips.py        # 负责测试每个 IP 的可访问性
├── .github/workflows/
│   └── cfiptest.yml    # GitHub Actions 工作流
└── merged/
    ├── blocked.txt       # 测试失败的 IP
    ├── unblocked.txt     # 测试成功的 IP
    └── curl_errors.log   # curl 错误日志
`

---

🚀 如何运行

进入 GitHub 仓库 → Actions → 选择 Cloudflare IP Test → 点击 Run workflow。

你可以自定义两个参数：

| 参数 | 说明 | 默认值 |
|------|------|--------|
| jobs | 并行 job 数量（1–256） | 20 |
| interval | 进度条刷新间隔（秒） | 5 |

---

📊 结果说明

unblocked.txt
表示通过代理访问 Cloudflare IP 返回了有效 HTTP 状态码（非 000）。

blocked.txt
表示访问失败或无响应。

curl_errors.log
记录 curl 的 stderr 输出，例如：

- 超时  
- 连接失败  
- 代理错误  
- DNS 解析失败  

---

🧠 工作流逻辑概述

1. generate-matrix  
   - 拉取 Cloudflare CIDR  
   - 自动拆分并均分  
   - 输出 matrix 给后续 job  

2. test（并行执行）  
   - 每个 job 测试自己的 IP 列表  
   - 每隔 N 秒刷新进度条和 ETA  
   - 将结果追加到 merged/  

3. merge-results  
   - 汇总所有结果  
   - 输出测试统计到 GitHub Summary  
   - 推送结果文件到 master  

---

⚠️ 注意事项

- GitHub Actions 默认不允许直接推送到受保护的分支，请确保 master 未开启保护规则，或允许 Actions 推送。
- 如果代理不可用，脚本会提前退出。
- 大规模 IP 测试可能需要较长时间，建议合理设置 job 数量。

---

🛠️ 后续可扩展方向

- 支持 IPv6 测试  
- 支持多代理轮询  
- 支持自动生成 HTML 报告  
- 支持 Telegram / Discord 推送结果  

---
