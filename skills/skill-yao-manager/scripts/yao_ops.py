#!/usr/bin/env python3
"""yao_ops.py — 自包含的 YaoMetaSkill 便捷入口，无外部依赖。

用法:
    python yao_ops.py list
    python yao_ops.py check-all <skill_name>
    python yao_ops.py scan
    python yao_ops.py init <name> --desc "..."
    python yao_ops.py validate <name>
    python yao_ops.py lint <name>
    python yao_ops.py context-size <name>
    python yao_ops.py package <name> [--platform generic] [--zip]

环境变量:
    HARNESS_YAO_META_SKILL_DIR  yao-meta-skill 仓库路径（默认: <skill_dir>/third_party/yao-meta-skill）
    HARNESS_SKILLS_DIR          skill 存放根目录（默认: <project_root>/skills）
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _project_root() -> Path:
    """通过 git rev-parse 动态获取项目根目录，禁止硬编码。"""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True,
            cwd=str(Path(__file__).resolve().parent),
        )
        return Path(result.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        # 回退：脚本位于 skills/skill-yao-manager/scripts/，向上 3 级
        return Path(__file__).resolve().parents[3]


# ---------- 配置 ----------

_ROOT = _project_root()
_SKILL_DIR = Path(__file__).resolve().parents[1]  # skills/skill-yao-manager/
_YAO_DIR = Path(os.environ.get(
    "HARNESS_YAO_META_SKILL_DIR",
    str(_SKILL_DIR / "third_party" / "yao-meta-skill"),
))
_SKILLS_DIR = Path(os.environ.get(
    "HARNESS_SKILLS_DIR",
    str(_ROOT / "skills"),
))


# ---------- YaoResult ----------

@dataclass
class YaoResult:
    ok: bool
    command: str
    returncode: int
    stdout: str
    stderr: str
    payload: dict[str, Any] | None

    def summary(self) -> str:
        if self.payload:
            return json.dumps(self.payload, ensure_ascii=False, indent=2)
        return self.stdout or self.stderr


# ---------- YaoMetaSkill ----------

class YaoMetaSkill:
    """封装 yao-meta-skill 仓库中各脚本的调用。"""

    def __init__(self, yao_dir: Path, skills_dir: Path) -> None:
        self.yao_dir = Path(yao_dir).resolve()
        self.scripts_dir = self.yao_dir / "scripts"
        self.skills_dir = Path(skills_dir).resolve()

        if not self.scripts_dir.is_dir():
            raise FileNotFoundError(
                f"yao-meta-skill scripts 目录不存在: {self.scripts_dir}\n"
                f"请执行: git clone https://github.com/yaojingang/yao-meta-skill.git "
                f"{self.yao_dir}"
            )

    def _run(self, script: str, args: list[str], cwd: Path | None = None) -> YaoResult:
        cmd = [sys.executable, str(self.scripts_dir / script), *args]
        proc = subprocess.run(
            cmd,
            cwd=str(cwd or self.yao_dir),
            capture_output=True,
            text=True,
            timeout=120,
        )
        payload = None
        stdout = proc.stdout.strip()
        if stdout:
            with contextlib.suppress(json.JSONDecodeError):
                payload = json.loads(stdout)

        return YaoResult(
            ok=proc.returncode == 0,
            command=f"{script} {' '.join(args)}".strip(),
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            payload=payload,
        )

    def init(self, name: str, description: str, title: str | None = None) -> YaoResult:
        args = [name, "--description", description, "--output-dir", str(self.skills_dir)]
        if title:
            args.extend(["--title", title])
        return self._run("init_skill.py", args)

    def validate(self, skill_name: str) -> YaoResult:
        return self._run("yao.py", ["validate", str(self.skills_dir / skill_name)])

    def context_size(self, skill_name: str) -> YaoResult:
        return self._run("context_sizer.py", [str(self.skills_dir / skill_name)])

    def resource_boundary(self, skill_name: str) -> YaoResult:
        return self._run("resource_boundary_check.py", [str(self.skills_dir / skill_name)])

    def lint(self, skill_name: str) -> YaoResult:
        return self._run("lint_skill.py", [str(self.skills_dir / skill_name)])

    def package(
        self,
        skill_name: str,
        platforms: list[str] | None = None,
        output_dir: str = "dist",
        zip_output: bool = False,
    ) -> YaoResult:
        skill_dir = str(self.skills_dir / skill_name)
        args = [skill_dir, "--output-dir", output_dir]
        for p in platforms or ["generic"]:
            args.extend(["--platform", p])
        if zip_output:
            args.append("--zip")
        return self._run("cross_packager.py", args)

    def check_all(self, skill_name: str) -> list[YaoResult]:
        return [
            self.validate(skill_name),
            self.context_size(skill_name),
            self.resource_boundary(skill_name),
        ]

    def list_skills(self) -> list[dict[str, str]]:
        """扫描 skills_dir 下含 SKILL.md 的目录，解析 frontmatter 提取 name/description。"""
        skills: list[dict[str, str]] = []
        if not self.skills_dir.is_dir():
            return skills

        fm_re = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
        field_re = re.compile(r"^(\w+)\s*:\s*(.+?)$", re.MULTILINE)

        for child in sorted(self.skills_dir.iterdir()):
            if not child.is_dir():
                continue
            md_path = child / "SKILL.md"
            if not md_path.exists():
                continue
            text = md_path.read_text(encoding="utf-8")
            m = fm_re.match(text)
            if not m:
                continue
            fields = dict(field_re.findall(m.group(1)))
            # description 可能是多行 | 格式，截取首行
            desc = fields.get("description", "").strip().split("\n")[0].strip()
            skills.append({
                "name": fields.get("name", child.name),
                "description": desc,
                "path": str(child),
            })
        return skills


# ---------- 命令处理 ----------

def _yao() -> YaoMetaSkill:
    return YaoMetaSkill(_YAO_DIR, _SKILLS_DIR)


def cmd_list(_args: argparse.Namespace) -> None:
    yao = _yao()
    skills = yao.list_skills()
    if not skills:
        print("无已注册 skill")
        return
    for s in skills:
        print(f"  {s['name']:30s} {s['description'][:80]}")


def cmd_check_all(args: argparse.Namespace) -> None:
    yao = _yao()
    results = yao.check_all(args.name)
    report = []
    all_ok = True
    for r in results:
        status = "PASS" if r.ok else "FAIL"
        report.append({"check": r.command, "status": status})
        if not r.ok:
            all_ok = False
            report[-1]["detail"] = (r.stderr or r.stdout)[:500]
    print(json.dumps({"skill": args.name, "all_ok": all_ok, "checks": report}, ensure_ascii=False, indent=2))
    if not all_ok:
        sys.exit(1)


def cmd_scan(_args: argparse.Namespace) -> None:
    yao = _yao()
    skills = yao.list_skills()
    summary = []
    for s in skills:
        results = yao.check_all(s["name"])
        ok = all(r.ok for r in results)
        fails = [r.command for r in results if not r.ok]
        summary.append({"skill": s["name"], "ok": ok, "fails": fails})
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if any(not s["ok"] for s in summary):
        sys.exit(1)


def cmd_init(args: argparse.Namespace) -> None:
    yao = _yao()
    result = yao.init(args.name, args.desc, getattr(args, "title", None))
    print(result.summary())
    if not result.ok:
        sys.exit(1)


def cmd_validate(args: argparse.Namespace) -> None:
    yao = _yao()
    result = yao.validate(args.name)
    print(result.summary())
    if not result.ok:
        sys.exit(1)


def cmd_lint(args: argparse.Namespace) -> None:
    yao = _yao()
    result = yao.lint(args.name)
    print(result.summary())
    if not result.ok:
        sys.exit(1)


def cmd_context_size(args: argparse.Namespace) -> None:
    yao = _yao()
    result = yao.context_size(args.name)
    print(result.summary())
    if not result.ok:
        sys.exit(1)


def cmd_package(args: argparse.Namespace) -> None:
    yao = _yao()
    platforms = args.platform or ["generic"]
    result = yao.package(args.name, platforms, args.output_dir, args.zip)
    print(result.summary())
    if not result.ok:
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="YaoMetaSkill 便捷入口（自包含，无外部依赖）")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="列出所有 skill")

    p = sub.add_parser("check-all", help="全面检查指定 skill")
    p.add_argument("name")

    sub.add_parser("scan", help="批量巡检所有 skill")

    p = sub.add_parser("init", help="创建新 skill")
    p.add_argument("name")
    p.add_argument("--desc", required=True)
    p.add_argument("--title", default=None)

    p = sub.add_parser("validate", help="验证 skill 结构")
    p.add_argument("name")

    p = sub.add_parser("lint", help="lint 规范检查")
    p.add_argument("name")

    p = sub.add_parser("context-size", help="上下文大小检查")
    p.add_argument("name")

    p = sub.add_parser("package", help="打包 skill")
    p.add_argument("name")
    p.add_argument("--platform", action="append", default=[])
    p.add_argument("--output-dir", default="dist")
    p.add_argument("--zip", action="store_true")

    args = parser.parse_args()
    {
        "list": cmd_list,
        "check-all": cmd_check_all,
        "scan": cmd_scan,
        "init": cmd_init,
        "validate": cmd_validate,
        "lint": cmd_lint,
        "context-size": cmd_context_size,
        "package": cmd_package,
    }[args.command](args)


if __name__ == "__main__":
    main()
