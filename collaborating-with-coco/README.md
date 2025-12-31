# collaborating-with-coco

A Claude Code **Agent Skill** that bridges Claude with Coco CLI (Codebase Copilot) for multi-model collaboration on coding tasks.

## Overview

This Skill enables Claude to delegate coding tasks to Coco CLI, combining the strengths of multiple AI models. Coco handles algorithm implementation, debugging, and code analysis while Claude orchestrates the workflow and refines the output.

## Features

- **Multi-turn sessions**: Maintain conversation context across multiple interactions via `SESSION_ID`
- **Fine-grained tool control**: Allow or disallow specific tools for enhanced security
- **YOLO mode**: Bypass permission checks for trusted environments
- **Timeout configuration**: Set timeouts for bash tools and queries
- **JSON output**: Structured responses for easy parsing and integration
- **Cross-platform**: Windows path escaping handled automatically

## Installation

### 1. Install Coco CLI

Coco CLI (Codebase Copilot) is required. See the [Coco User Manual](https://bytedance.larkoffice.com/wiki/JUgywUkeZiz6Pqk271zc0iQanHg) for installation instructions.

Verify installation:
```bash
coco --version
```

### 2. Install this Skill

Copy this Skill to your Claude Code skills directory:
- User-level: `~/.claude/skills/collaborating-with-coco/`
- Project-level: `.claude/skills/collaborating-with-coco/`

## Usage

### Basic

```bash
python scripts/coco_bridge.py --cd "/path/to/project" --PROMPT "Analyze the authentication flow"
```

### Multi-turn Session

```bash
# Start a session
python scripts/coco_bridge.py --cd "/project" --PROMPT "Review login.py for security issues"
# Response includes SESSION_ID

# Continue the session
python scripts/coco_bridge.py --cd "/project" --SESSION_ID "uuid-from-response" --PROMPT "Suggest fixes for the issues found"
```

### Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `--PROMPT` | Yes | Task instruction |
| `--cd` | Yes | Workspace root directory |
| `--SESSION_ID` | No | Resume a previous session |
| `--return-all-messages` | No | Include full reasoning trace in output |
| `--model` | No | Specify model (use only when explicitly requested) |
| `--yolo` | No | Enable YOLO mode - bypass tool permission checks |
| `--allowed-tool` | No | Auto approve on this tool (can specify multiple times) |
| `--disallowed-tool` | No | Auto reject this tool (can specify multiple times) |
| `--bash-tool-timeout` | No | Timeout for bash tool (e.g. '30s', '5m', '1h') |
| `--query-timeout` | No | Timeout for a single query (e.g. '30s', '5m', '1h') |

### Output Format

```json
{
  "success": true,
  "SESSION_ID": "uuid",
  "agent_messages": "Coco response text",
  "all_messages": []
}
```

### Available Models

Coco supports multiple built-in models:
- `kimi-k2` (default)
- `kimi-k2-thinking`
- `seed-code-preview`
- `seed-code-preview-beta`
- `gemini-2.5-pro`
- `doubao-1.6`
- `deepseek-v3.1`

### Built-in Tools

Coco provides 16 built-in tools:

**File Operations:**
- Read, Write, Edit, ApplyPatch, Glob, LS, Grep

**Command Execution:**
- Bash, BashOutput, KillShell

**Advanced Features:**
- Task, Skill, TodoWrite, UnderstandImage

## Acknowledgments

This project is inspired by [GuDaStudio/skills](https://github.com/GuDaStudio/skills).

## License

MIT License. See [LICENSE](LICENSE) for details.
