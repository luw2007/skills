"""
Coco Bridge Script for Claude Agent Skills.
Wraps the Coco CLI to provide a JSON-based interface for Claude.
"""

import json
import os
import sys
import subprocess
import shutil
import argparse
from pathlib import Path
from typing import List, Optional


def _get_windows_npm_paths() -> List[Path]:
    """Return candidate directories for npm global installs on Windows."""
    if os.name != "nt":
        return []
    paths: List[Path] = []
    env = os.environ
    if prefix := env.get("NPM_CONFIG_PREFIX") or env.get("npm_config_prefix"):
        paths.append(Path(prefix))
    if appdata := env.get("APPDATA"):
        paths.append(Path(appdata) / "npm")
    if localappdata := env.get("LOCALAPPDATA"):
        paths.append(Path(localappdata) / "npm")
    if programfiles := env.get("ProgramFiles"):
        paths.append(Path(programfiles) / "nodejs")
    return paths


def _augment_path_env(env: dict) -> None:
    """Prepend npm global directories to PATH if missing."""
    if os.name != "nt":
        return
    path_key = next((k for k in env if k.upper() == "PATH"), "PATH")
    path_entries = [p for p in env.get(path_key, "").split(os.pathsep) if p]
    lower_set = {p.lower() for p in path_entries}
    for candidate in _get_windows_npm_paths():
        if candidate.is_dir() and str(candidate).lower() not in lower_set:
            path_entries.insert(0, str(candidate))
            lower_set.add(str(candidate).lower())
    env[path_key] = os.pathsep.join(path_entries)


def _resolve_executable(name: str, env: dict) -> str:
    """Resolve executable path, checking npm directories for .cmd/.bat on Windows."""
    if os.path.isabs(name) or os.sep in name or (os.altsep and os.altsep in name):
        return name
    path_key = next((k for k in env if k.upper() == "PATH"), "PATH")
    path_val = env.get(path_key)
    win_exts = {".exe", ".cmd", ".bat", ".com"}
    if resolved := shutil.which(name, path=path_val):
        if os.name == "nt":
            suffix = Path(resolved).suffix.lower()
            if not suffix:
                resolved_dir = str(Path(resolved).parent)
                for ext in (".cmd", ".bat", ".exe", ".com"):
                    candidate = Path(resolved_dir) / f"{name}{ext}"
                    if candidate.is_file():
                        return str(candidate)
            elif suffix not in win_exts:
                return resolved
        return resolved
    if os.name == "nt":
        for base in _get_windows_npm_paths():
            for ext in (".cmd", ".bat", ".exe", ".com"):
                candidate = base / f"{name}{ext}"
                if candidate.is_file():
                    return str(candidate)
    return name


def run_shell_command(cmd: List[str], cwd: Optional[str] = None) -> subprocess.CompletedProcess:
    """Execute a command and return the result."""
    env = os.environ.copy()
    _augment_path_env(env)

    popen_cmd = cmd.copy()
    exe_path = _resolve_executable(cmd[0], env)
    popen_cmd[0] = exe_path

    if os.name == "nt" and Path(exe_path).suffix.lower() in {".cmd", ".bat"}:
        def _cmd_quote(arg: str) -> str:
            if not arg:
                return '""'
            arg = arg.replace('%', '%%')
            arg = arg.replace('^', '^^')
            if any(c in arg for c in '&|<>()^" \t'):
                escaped = arg.replace('"', '"^""')
                return f'"{escaped}"'
            return arg
        cmdline = " ".join(_cmd_quote(a) for a in popen_cmd)
        comspec = env.get("COMSPEC", "cmd.exe")
        popen_cmd = f'"{comspec}" /d /s /c "{cmdline}"'

    return subprocess.run(
        popen_cmd,
        shell=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding='utf-8',
        errors='replace',
        cwd=cwd,
        env=env,
    )


def windows_escape(prompt):
    """Windows style string escaping for newlines and special chars in prompt text."""
    result = prompt.replace('\n', '\\n')
    result = result.replace('\r', '\\r')
    result = result.replace('\t', '\\t')
    return result


def configure_windows_stdio() -> None:
    """Configure stdout/stderr to use UTF-8 encoding on Windows."""
    if os.name != "nt":
        return
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass


def main():
    configure_windows_stdio()
    parser = argparse.ArgumentParser(description="Coco Bridge")
    parser.add_argument("--PROMPT", required=True, help="Instruction for the task to send to coco.")
    parser.add_argument("--cd", required=True, type=Path, help="Set the workspace root for coco before executing the task.")
    parser.add_argument("--SESSION_ID", default="", help="Resume the specified session of the coco. Defaults to empty string, start a new session.")
    parser.add_argument("--return-all-messages", action="store_true", help="Return all messages (e.g. reasoning, tool calls, etc.) from the coco session. Set to `False` by default, only the agent's final reply message is returned.")
    parser.add_argument("--model", default="", help="The model to use for the coco session. This parameter is strictly prohibited unless explicitly specified by the user.")
    parser.add_argument("--yolo", action="store_true", help="Enable YOLO mode - bypass tool permission checks.")
    parser.add_argument("--allowed-tool", action="append", default=[], help="Auto approve on this tool (e.g. 'Bash', 'Edit', 'Write'), can specify multiple times.")
    parser.add_argument("--disallowed-tool", action="append", default=[], help="Auto reject this tool, can specify multiple times.")
    parser.add_argument("--bash-tool-timeout", default="", help="Timeout for bash tool, e.g. '30s' (30 seconds), '5m' (5 minutes), '1h' (1 hour).")
    parser.add_argument("--query-timeout", default="", help="Timeout for a single query, e.g. '30s' (30 seconds), '5m' (5 minutes), '1h' (1 hour).")

    args = parser.parse_args()

    cd: Path = args.cd
    if not cd.exists():
        result = {
            "success": False,
            "error": f"The workspace root directory `{cd.absolute()}` does not exist. Please check the path and try again."
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    PROMPT = args.PROMPT
    if os.name == "nt":
        PROMPT = windows_escape(PROMPT)

    cmd = ["coco", "--print", "--json", PROMPT]

    if args.yolo:
        cmd.insert(1, "--yolo")

    if args.model:
        cmd.insert(1, args.model)
        cmd.insert(1, "-c")
        cmd[2] = f"model.name={args.model}"

    if args.SESSION_ID:
        cmd.insert(1, args.SESSION_ID)
        cmd.insert(1, "--resume")

    for tool in args.allowed_tool:
        cmd.insert(1, tool)
        cmd.insert(1, "--allowed-tool")

    for tool in args.disallowed_tool:
        cmd.insert(1, tool)
        cmd.insert(1, "--disallowed-tool")

    if args.bash_tool_timeout:
        cmd.insert(1, args.bash_tool_timeout)
        cmd.insert(1, "--bash-tool-timeout")

    if args.query_timeout:
        cmd.insert(1, args.query_timeout)
        cmd.insert(1, "--query-timeout")

    result_data = run_shell_command(cmd, cwd=str(cd.absolute()))

    success = True
    err_message = ""
    agent_messages = ""
    session_id = None
    all_messages = []

    stdout_text = result_data.stdout.strip()
    stderr_text = result_data.stderr.strip()

    if result_data.returncode != 0:
        success = False
        err_message = f"Coco exited with code {result_data.returncode}."
        if stderr_text:
            err_message += f"\n\nStderr:\n{stderr_text}"
        if stdout_text:
            err_message += f"\n\nStdout:\n{stdout_text}"
    else:
        try:
            output_data = json.loads(stdout_text)
            all_messages = output_data if isinstance(output_data, list) else [output_data]

            for msg in all_messages:
                if isinstance(msg, dict):
                    if msg.get("session_id"):
                        session_id = msg.get("session_id")
                    if msg.get("type") == "assistant" and msg.get("content"):
                        content = msg.get("content", [])
                        if isinstance(content, list):
                            for item in content:
                                if isinstance(item, dict) and item.get("type") == "text":
                                    agent_messages += item.get("text", "")
                        elif isinstance(content, str):
                            agent_messages += content

        except json.JSONDecodeError as e:
            for line in stdout_text.split('\n'):
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                    all_messages.append(msg)
                    if isinstance(msg, dict):
                        if msg.get("session_id"):
                            session_id = msg.get("session_id")
                        if msg.get("type") == "assistant" and msg.get("content"):
                            content = msg.get("content", [])
                            if isinstance(content, list):
                                for item in content:
                                    if isinstance(item, dict) and item.get("type") == "text":
                                        agent_messages += item.get("text", "")
                            elif isinstance(content, str):
                                agent_messages += content
                except json.JSONDecodeError:
                    continue

            if not all_messages:
                success = False
                err_message = f"Failed to parse JSON output: {e}\n\nRaw output:\n{stdout_text}"

    result = {}

    if session_id:
        result["SESSION_ID"] = session_id
    else:
        if success:
            success = False
            err_message = "Failed to get `SESSION_ID` from the coco session."

    if success and not agent_messages:
        success = False
        err_message = (
            "Failed to retrieve `agent_messages` data from the Coco session. "
            "This might be due to Coco performing a tool call. "
            "You can continue using the `SESSION_ID` to proceed with the conversation.\n\n"
            + err_message
        )

    if success:
        result["agent_messages"] = agent_messages
    else:
        result["error"] = err_message

    result["success"] = success

    if args.return_all_messages:
        result["all_messages"] = all_messages

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
