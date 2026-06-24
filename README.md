# OMEGA

<p align="center">
  <img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License MIT">
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue.svg" alt="Python Version">
  <img src="https://img.shields.io/badge/Model%20Context%20Protocol-Supported-orange.svg" alt="MCP Supported">
  <img src="https://img.shields.io/badge/Agents-8%20Active-magenta.svg" alt="8 Active Agents">
  <img src="https://img.shields.io/badge/API%20Resilience-100%25-brightgreen.svg" alt="API Resilience">
</p>

**The Ultimate Open-Source Autonomous Terminal AI Agent & Digital Employee**

OMEGA is a digital employee that lives in your terminal. It autonomously plans, researches, codes, debugs, browses the web, manages DevOps, and remembers — coordinating a team of 8 specialized AI agents to get real work done, powered entirely by free OpenRouter models with resilient retry logic.

```
 ██████╗ ███╗   ███╗███████╗ ██████╗  █████╗ 
██╔═══██╗████╗ ████║██╔════╝██╔════╝ ██╔══██╗
██║   ██║██╔████╔██║█████╗  ██║  ███╗███████║
██║   ██║██║╚██╔╝██║██╔══╝  ██║   ██║██╔══██║
╚██████╔╝██║ ╚═╝ ██║███████╗╚██████╔╝██║  ██║
 ╚═════╝ ╚═╝     ╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝
```

---

## Features

- **8 Specialized Agents** — Planner, Researcher, Coder, Browser, DevOps, Executor, Critic, and the new specialized **MCP Agent**.
- **Error-Free API Resilience** — Built-in exponential backoff retry mechanism (5 attempts) to eliminate timeout errors, rate-limit limits (RPM), and network drops.
- **Live Streamed Thinking** — All agent thought processes are streamed directly to the terminal UI in real-time (`dim white`), giving you complete transparency into their logic.
- **Isolated App Workspaces** — Running the `code` command automatically creates and separates projects into dedicated folders inside `apps/` (e.g. `apps/bakery_website/`) rather than cluttering your root directory.
- **Free-Model Routing** — Automatically selects the best free OpenRouter model per task; no paid API key required.
- **Multi-tier Memory** — Short-term context, SQLite long-term storage, semantic recall via ChromaDB, episodic action history, and a knowledge graph.
- **Built-in Plugins** — Filesystem, terminal, git, search, browser, docker, database, and custom HTTP API clients.
- **Model Context Protocol (MCP)** — Auto-discovers, saves, and connects stdio/HTTP MCP servers with interactive controls.
- **Security Gates** — Risk-assessed permission system requiring user approval before executing dangerous operations (e.g. deletions, deployments).
- **FastAPI Backend & UI** — Built-in FastAPI server with WebSocket live events alongside a Rich-powered beautiful terminal UI.

---

## Installation & Setup

Follow these steps to install, configure, and run OMEGA on your machine:

### 1. Clone the Repository
Open your terminal (PowerShell on Windows, Bash on Linux/macOS) and run:
```powershell
git clone https://github.com/senthilssettai-creator/omega-ai-agent omega
cd omega
```

### 2. Run the Installation Script
On Windows PowerShell, run the PowerShell setup script to configure the virtual environment and install dependencies:
```powershell
powershell -ExecutionPolicy Bypass -File install.ps1
```
*(On Linux/macOS, use `bash scripts/install.sh`)*

### 3. Configure Environment Variables
Copy `.env.example` to `.env` and open it:
```powershell
cp .env.example .env
```
Edit the `.env` file and set your OpenRouter API key:
```env
OPENROUTER_API_KEY=your-free-openrouter-key-here
```
> Get a free API key at [openrouter.ai/keys](https://openrouter.ai/keys).

### 4. Activate the Virtual Environment
Activate the environment in your current PowerShell session:
```powershell
.\.venv\Scripts\Activate.ps1
```
*(On Linux/macOS, use `source .venv/bin/activate`)*

### 5. Launch OMEGA
Start the interactive terminal UI session:
```powershell
omega run
```

---

## Usage Guide

### General CLI Commands

```bash
omega run                                      # Start interactive loop
omega run "build a REST API for a todo app"   # Run a single one-shot goal
omega serve                                    # Start the FastAPI REST server (API docs at /docs)
omega init                                     # Initialize configuration directories
omega version                                  # View installed version
```

### Interactive Mode Commands

Inside the interactive OMEGA prompt (`omega ›`), you can issue instructions or utilize special commands:

```
omega › research the current state of clean energy
omega › code build a landing page for my bakery
omega › browse github.com/trending
omega › status
omega › help
```

---

## Model Context Protocol (MCP) Integration

OMEGA fully supports adding external tools via MCP servers. Use the following commands to manage and run MCP servers:

### 1. List Servers
Show all configured stdio or HTTP MCP servers and their connection statuses:
```
omega › mcp list
```

### 2. Add an MCP Server
You can add a server interactively by simply typing `mcp add` and following the wizard prompts:
```
omega › mcp add
```
Or add a server directly by pasting a JSON configuration:
```
omega › mcp add {"mcpServers":{"puppeteer":{"command":"npx","args":["-y","@modelcontextprotocol/server-puppeteer"]}}}
```
Or add an HTTP MCP server:
```
omega › mcp add my-http-server http://localhost:3000
```

### 3. Use an MCP Server
Select an active MCP server, specify a task, and force the agent to prioritize the MCP server's tools over native system tools:
```
omega › mcp use
```

### 4. Remove a Server
Deactivate and remove an MCP configuration from OMEGA:
```
omega › mcp remove <server-name>
```

---

## Development & Test Execution

To install development dependencies and run the test suite:

```powershell
pip install -r requirements-dev.txt
python -m playwright install chromium
.\.venv\Scripts\python.exe -m pytest tests/ -v
```

---

## License

This project is licensed under the [MIT License](LICENSE).
