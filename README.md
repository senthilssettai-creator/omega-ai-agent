# OMEGA

**The Ultimate Open-Source Autonomous Terminal AI Agent**

OMEGA is a digital employee that lives in your terminal. It autonomously plans, researches, codes, debugs, browses the web, manages DevOps, and remembers — coordinating a team of specialized AI agents to get real work done, powered entirely by free OpenRouter models.

```
 ██████╗ ███╗   ███╗███████╗ ██████╗  █████╗
██╔═══██╗████╗ ████║██╔════╝██╔════╝ ██╔══██╗
██║   ██║██╔████╔██║█████╗  ██║  ███╗███████║
██║   ██║██║╚██╔╝██║██╔══╝  ██║   ██║██╔══██║
╚██████╔╝██║ ╚═╝ ██║███████╗╚██████╔╝██║  ██║
 ╚═════╝ ╚═╝     ╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝
```

## Features

- **7 specialized agents** — Planner, Researcher, Coder, Browser, DevOps, Executor, Critic
- **Free-model routing** — automatically selects the best free OpenRouter model per task; no paid API required
- **Multi-tier memory** — short-term context, long-term SQLite storage, semantic recall via ChromaDB, episodic action history, knowledge graph
- **8 built-in tools** — filesystem, terminal, git, web search, browser automation, Docker, REST/GraphQL API client, database
- **MCP support** — auto-discovers and connects to Model Context Protocol servers
- **Security gates** — risk-assessed permission system requiring approval for dangerous actions
- **Workflow engine** — save, schedule, and replay multi-step agent workflows
- **REST API** — full FastAPI server with WebSocket live events
- **Beautiful terminal UI** — Rich-powered banners, live progress, task trees

## Quick Start

```bash
git clone <https://github.com/senthilssettai-creator/omega-ai-agent> omega && cd omega
bash install.ps1
# Edit .env and add your free OpenRouter API key from https://openrouter.ai/keys
.\.venv\Scripts\Activate.ps1
omega run
```

Or with Docker:

```bash
cp .env.example .env   # add your OPENROUTER_API_KEY
docker compose up
```

## Usage

```bash
omega run                      # interactive mode
omega run "build a REST API for a todo app"   # one-shot goal
omega serve                    # start the REST API server (see /docs)
omega init                     # set up config and directories
```

Inside interactive mode:

```
omega › research the current state of small modular reactors
omega › code add input validation to app.py
omega › browse github.com/trending
omega › run workflow daily_report
omega › create workflow check competitor pricing every morning and email me a summary
omega › status
omega › help
```

## Architecture

```
omega/
├── agents/        Planner, Researcher, Coder, Browser, DevOps, Executor, Critic + Orchestrator
├── models/         OpenRouter model router (free-tier auto-selection)
├── memory/         Short-term, long-term (SQLite), semantic (ChromaDB), episodic, knowledge graph
├── tools/           Filesystem, terminal, git, search, browser, docker, API, database
├── security/       Risk assessment, permission gates, sandboxed execution
├── mcp/             Model Context Protocol server discovery and integration
├── workflows/       Workflow engine (create, save, schedule, run)
├── ui/              Rich terminal interface
├── api/             FastAPI REST + WebSocket server
└── cli.py           Typer-based CLI entry point
```

## Configuration

All configuration lives in `.env` (copy from `.env.example`). The only required value is `OPENROUTER_API_KEY` — get a free one at [openrouter.ai/keys](https://openrouter.ai/keys).

## Development

```bash
pip install -r requirements-dev.txt
python -m playwright install chromium
pytest tests/ -v
```

The test suite (66 tests) covers the model router's task classification, the security manager's risk assessment, the multi-tier memory system, the tool registry, and the orchestrator's dependency-graph task execution — including regression tests for subprocess-cleanup correctness on timeout.

## Security

Dangerous actions (deletions, force-pushes, deployments, etc.) are risk-assessed and require explicit approval before execution. Code execution is sandboxed via Docker when available, falling back to subprocess isolation otherwise.

## License

MIT
