# skills

A collection of Claude Code Agent Skills.

## Available Skills

| Skill | Description |
|-------|-------------|
| [collaborating-with-coco](https://github.com/luw2007/collaborating-with-coco) | Bridges Claude with Coco CLI for multi-model collaboration |
| [octocode](https://github.com/luw2007/claude-skill-octocode) | AI-powered code indexer with semantic search, knowledge graphs (GraphRAG), and persistent memory system |

## Installation

### Install Individual Skill

```bash
openskills install luw2007/collaborating-with-coco
openskills install luw2007/octocode
```

### Install All Skills (Manual)

```bash
git clone --recursive https://github.com/luw2007/skills.git
cp -r skills/collaborating-with-coco ~/.claude/skills/
cp -r skills/octocode ~/.claude/skills/
```

## Acknowledgments

This project structure is inspired by [GuDaStudio/skills](https://github.com/GuDaStudio/skills).

## License

MIT License
