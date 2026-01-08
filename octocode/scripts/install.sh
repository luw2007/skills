#!/usr/bin/env bash
# Octocode Claude Code Skill 安装脚本

set -e

echo ""
echo "========================================"
echo "Octocode Claude Code Skill 安装器"
echo "========================================"
echo ""
echo "⚠️  实验性测试版本 (v0.1.0-alpha)"
echo "   仅供学习和测试使用"
echo ""

# 检查 Claude Code
if ! command -v claude &> /dev/null; then
  echo "错误: 未找到 Claude Code CLI"
  echo "请先安装: https://code.claude.com"
  exit 1
fi

echo "✓ Claude Code 已安装"
echo ""

# 选择安装位置
echo "安装位置："
echo "  1. 当前项目 (.claude/skills/octocode)"
echo "  2. 全局安装 (~/.claude/skills/octocode) [推荐]"
echo ""
read -p "选择 (1/2) [2]: " choice
choice=${choice:-2}

if [ "$choice" = "1" ]; then
  INSTALL_DIR=".claude/skills/octocode"
else
  INSTALL_DIR="$HOME/.claude/skills/octocode"
fi

# 获取脚本所在目录（skill 根目录）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# 检查是否已存在
if [ -d "$INSTALL_DIR" ]; then
  echo ""
  echo "⚠️  目标目录已存在: $INSTALL_DIR"
  read -p "是否覆盖? (y/n) [n]: " overwrite
  if [[ ! "$overwrite" =~ ^[Yy]$ ]]; then
    echo "安装已取消"
    exit 0
  fi
  rm -rf "$INSTALL_DIR"
fi

# 复制文件
mkdir -p "$(dirname "$INSTALL_DIR")"
cp -r "$SCRIPT_DIR" "$INSTALL_DIR"

echo ""
echo "✓ Skill 已安装到: $INSTALL_DIR"
echo ""
echo "========================================"
echo "下一步操作："
echo "========================================"
echo ""
echo "1. 安装并配置 Octocode (必需):"
echo "   详见: https://github.com/muvon/octocode"
echo ""
echo "2. 索引你的项目:"
echo "   $ cd /path/to/your/project"
echo "   $ cargo run --manifest-path /path/to/octocode/Cargo.toml -- index"
echo ""
echo "3. 启动 Claude Code:"
echo "   $ claude"
echo ""
echo "4. 测试 Skill:"
echo "   > 使用 octocode 搜索 \"authentication logic\""
echo ""
echo "详细文档: $INSTALL_DIR/README.md"
echo ""
