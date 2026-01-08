#!/usr/bin/env bash
# Check if octocode index exists for current project
#
# Exit codes:
#   0 - Index exists
#   1 - Index not found (but octocode is available)
#   2 - octocode command not available

# Check if octocode is installed
if ! command -v octocode &> /dev/null; then
    echo "❌ 错误: octocode 命令不存在" >&2
    echo "请先安装 octocode: https://github.com/liuwei1129/octocode" >&2
    exit 2
fi

# Check index status
output=$(octocode config --show 2>&1)

if echo "$output" | grep -q "Database status: ✅ Found"; then
    exit 0
elif echo "$output" | grep -q "Database status: ❌ Not found"; then
    exit 1
else
    # Unknown status
    echo "⚠️ 警告: 无法确定索引状态" >&2
    echo "输出: $output" >&2
    exit 1
fi
