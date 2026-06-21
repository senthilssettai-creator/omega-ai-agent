# -*- coding: utf-8 -*-
"""OMEGA CLI - Main entry point for the terminal application"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

import typer
from rich.prompt import Prompt

from omega.config import config
from omega.ui.terminal import ui

app = typer.Typer(
    name="omega",
    help="OMEGA - The Ultimate Autonomous Terminal AI Agent",
    add_completion=False,
)


def _check_api_key() -> bool:
    """Verify OpenRouter API key is configured"""
    if not config.openrouter_api_key:
        ui.error("OPENROUTER_API_KEY not set!")
        ui.console.print(
            "\n[dim]Get a free API key at:[/dim] [cyan]https://openrouter.ai/keys[/cyan]\n"
            "[dim]Then set it:[/dim] [white]export OPENROUTER_API_KEY=your-key[/white]\n"
            "[dim]Or add it to a .env file in your working directory.[/dim]\n"
        )
        return False
    return True


@app.command()
def run(
    goal: Optional[str] = typer.Argument(None, help="Goal to execute autonomously"),
):
    """Start OMEGA in interactive mode, or execute a single goal"""
    config.ensure_dirs()

    if not _check_api_key():
        raise typer.Exit(1)

    if goal:
        asyncio.run(_run_single_goal(goal))
    else:
        asyncio.run(_interactive_loop())


async def _run_single_goal(goal: str):
    """Execute a single goal and exit"""
    ui.print_banner()
    await _execute_goal_flow(goal)


async def _interactive_loop():
    """Main interactive REPL loop"""
    ui.print_banner()

    from omega.memory.store import memory
    from omega.tools.registry import registry
    from omega.mcp.manager import mcp_manager
    from omega.workflows.engine import workflow_engine

    with ui.spinner("Initializing OMEGA systems..."):
        await registry.load_builtin_tools()
        await registry.load_plugins()
        await mcp_manager.auto_discover()

    stats = memory.stats()
    ui.print_status(stats, {"workflow_count": len(workflow_engine.list_workflows())})

    ui.console.print(
        "\n[dim]Type your goal, or 'help' for commands. Type 'exit' to quit.[/dim]\n"
    )

    while True:
        try:
            user_input = await asyncio.to_thread(
                Prompt.ask, "[bold cyan]omega[/bold cyan] [dim]›[/dim]"
            )
        except (KeyboardInterrupt, EOFError):
            ui.console.print("\n[dim]Goodbye![/dim]")
            break

        if not user_input.strip():
            continue

        user_input = user_input.strip()
        cmd_lower = user_input.lower()

        if cmd_lower in ("exit", "quit", "q"):
            ui.console.print("[dim]Shutting down OMEGA...[/dim]")
            break

        elif cmd_lower == "help":
            ui.print_help()

        elif cmd_lower == "clear":
            ui.console.clear()
            ui.print_banner()

        elif cmd_lower == "status":
            stats = memory.stats()
            ui.print_status(stats, {"workflow_count": len(workflow_engine.list_workflows())})

        elif cmd_lower == "memory stats":
            ui.print_memory_stats(memory.stats())

        elif cmd_lower.startswith("remember "):
            content = user_input[9:]
            memory.remember(content, type_="user_fact", importance=0.8)
            ui.success(f"Remembered: {content}")

        elif cmd_lower.startswith("recall "):
            query = user_input[7:]
            results = memory.recall(query)
            ui.print_recall_results(results, query)

        elif cmd_lower == "models":
            with ui.spinner("Fetching available models..."):
                from omega.models.router import router
                try:
                    models = await router.list_free_models()
                    ui.print_models(models)
                except Exception as e:
                    ui.error(f"Could not fetch models: {e}")

        elif cmd_lower == "plugins":
            tools = registry.list_tools()
            for tool in tools:
                ui.console.print(f"[cyan]●[/cyan] [bold]{tool['name']}[/bold] - {tool['description']}")

        elif cmd_lower == "mcp list":
            servers = mcp_manager.servers
            if not servers:
                ui.console.print("[dim]No MCP servers connected.[/dim]")
            for name, server in servers.items():
                status = "[green]connected[/green]" if server.connected else "[dim]saved[/dim]"
                ui.console.print(f"[cyan]●[/cyan] [bold]{name}[/bold] — {status} · {len(server.tools)} tools")

        elif cmd_lower == "mcp add":
            # Interactive wizard — no inline args
            await _handle_mcp_add_interactive()

        elif cmd_lower.startswith("mcp add "):
            raw = user_input[8:].strip()
            await _handle_mcp_add(raw)

        elif cmd_lower == "mcp use":
            await _handle_mcp_use()

        elif cmd_lower.startswith("mcp remove "):
            name = user_input[11:].strip()
            if not name:
                ui.error("Usage: mcp remove <name>")
            else:
                removed = await mcp_manager.remove_server(name)
                if removed:
                    ui.success(f"Removed MCP server: {name}")
                else:
                    ui.error(f"Server not found: {name}")

        elif cmd_lower.startswith("research "):
            topic = user_input[9:]
            await _run_research(topic)

        elif cmd_lower.startswith("code "):
            task = user_input[5:]
            await _run_code(task)

        elif cmd_lower.startswith("browse "):
            url = user_input[7:]
            await _run_browse(url)

        elif cmd_lower.startswith("deploy "):
            path = user_input[7:]
            await _run_deploy(path)

        elif cmd_lower.startswith("run workflow "):
            name = user_input[13:]
            await _run_workflow(name)

        elif cmd_lower.startswith("create workflow "):
            description = user_input[16:]
            await _create_workflow_nl(description)

        elif cmd_lower == "workflows":
            ui.print_workflows(workflow_engine.list_workflows())

        else:
            # Treat as a goal
            await _execute_goal_flow(user_input)

        ui.console.print()


async def _handle_mcp_add_interactive():
    """Step-by-step interactive wizard for adding an MCP server."""
    from omega.mcp.manager import mcp_manager

    ui.console.print(
        "\n[bold cyan]MCP Server Setup Wizard[/bold cyan]\n"
        "[dim]Follow the prompts below. Press Ctrl+C to cancel.[/dim]\n"
    )

    # ── Step 1: Name ──────────────────────────────────────────────────────────
    try:
        name = await asyncio.to_thread(
            Prompt.ask, "[bold cyan]  Step 1[/bold cyan] Enter a name for this server"
        )
        name = name.strip()
    except (KeyboardInterrupt, EOFError):
        ui.console.print("\n[dim]Cancelled.[/dim]")
        return

    if not name:
        ui.error("Name cannot be empty.")
        return

    # ── Step 2: JSON config ───────────────────────────────────────────────────
    ui.console.print(
        f"\n[bold cyan]  Step 2[/bold cyan] Paste the JSON config for [bold]{name}[/bold]\n"
        "[dim]  Example:[/dim]\n"
        '[dim]  {"mcpServers":{"'
        + name
        + '":{"command":"npx","args":["-y","your-mcp-pkg@latest"]}}}'
        "[/dim]\n"
    )
    try:
        raw_cfg = await asyncio.to_thread(
            Prompt.ask, "[bold cyan]  Config[/bold cyan]"
        )
        raw_cfg = raw_cfg.strip()
    except (KeyboardInterrupt, EOFError):
        ui.console.print("\n[dim]Cancelled.[/dim]")
        return

    if not raw_cfg:
        ui.error("Config cannot be empty.")
        return

    # ── Parse the pasted config ───────────────────────────────────────────────
    json_start = raw_cfg.find("{")
    if json_start == -1:
        ui.error("No JSON object found in the pasted config.")
        return

    try:
        data = json.loads(raw_cfg[json_start:])
    except json.JSONDecodeError as exc:
        ui.error(f"Invalid JSON: {exc}")
        return

    # Normalise: extract command/url for the named server
    server_cfg: dict = {}

    if "mcpServers" in data:
        # {"mcpServers": {"name": {...}}}  — use the server matching 'name', or first entry
        servers_map = data["mcpServers"]
        if name in servers_map:
            server_cfg = servers_map[name]
        elif servers_map:
            # User gave a different name — just take the first entry and use their chosen name
            server_cfg = next(iter(servers_map.values()))
    elif name in data:
        server_cfg = data[name]
    elif "command" in data or "url" in data:
        server_cfg = data
    elif isinstance(data, dict) and all(isinstance(v, dict) for v in data.values()):
        server_cfg = next(iter(data.values()))
    else:
        server_cfg = data

    url = server_cfg.get("url")
    command_str = server_cfg.get("command")
    args = server_cfg.get("args", [])
    env = server_cfg.get("env", {})
    command = [command_str] + list(args) if command_str else None

    if not url and not command:
        ui.error("Config must contain either a 'url' or a 'command' field.")
        return

    # ── Connect & save ────────────────────────────────────────────────────────
    ui.console.print()
    with ui.spinner(f"Saving and connecting to [bold]{name}[/bold]..."):
        connected = await mcp_manager.add_server(name=name, url=url, command=command, env=env)

    if connected:
        tools_count = len(mcp_manager.servers[name].tools)
        ui.success(f"Connected to [bold]{name}[/bold] — {tools_count} tools available.")
    else:
        ui.warning(
            f"[bold]{name}[/bold] saved but could not connect right now.\n"
            "  It will be auto-retried on next startup.\n"
            "  Tip: use [bold]mcp list[/bold] to check status."
        )


async def _handle_mcp_use():
    """Interactive MCP server selector: list saved servers → pick one → run a prompt with it."""
    from omega.mcp.manager import mcp_manager

    # ── Load all saved servers (connected or not) ─────────────────────────────
    saved = await mcp_manager.list_saved_servers()
    if not saved:
        ui.console.print(
            "[dim]No MCP servers saved yet.[/dim]\n"
            "[dim]Use [bold]mcp add[/bold] to add one.[/dim]"
        )
        return

    # ── Display server list ───────────────────────────────────────────────────
    ui.console.print("\n[bold cyan]Saved MCP Servers[/bold cyan]\n")
    for i, srv in enumerate(saved, 1):
        srv_name = srv["name"]
        is_live = srv_name in mcp_manager.servers and mcp_manager.servers[srv_name].connected
        status_tag = "[green]● live[/green]" if is_live else "[dim]○ saved[/dim]"
        cmd = srv.get("command", [])
        detail = " ".join(cmd[:3]) + ("..." if len(cmd) > 3 else "") if cmd else srv.get("url", "")
        ui.console.print(
            f"  [bold cyan]{i}.[/bold cyan] {status_tag} [bold]{srv_name}[/bold]"
            + (f"  [dim]{detail}[/dim]" if detail else "")
        )
    ui.console.print()

    # ── Pick a server ─────────────────────────────────────────────────────────
    try:
        choice_raw = await asyncio.to_thread(
            Prompt.ask, "[bold cyan]Select server[/bold cyan] [dim](number)[/dim]"
        )
        choice = int(choice_raw.strip()) - 1
        if not (0 <= choice < len(saved)):
            ui.error("Invalid selection.")
            return
    except (ValueError, KeyboardInterrupt, EOFError):
        ui.console.print("[dim]Cancelled.[/dim]")
        return

    selected = saved[choice]
    server_name = selected["name"]

    # ── Ensure the server is connected ────────────────────────────────────────
    is_live = server_name in mcp_manager.servers and mcp_manager.servers[server_name].connected
    if not is_live:
        with ui.spinner(f"Connecting to [bold]{server_name}[/bold]..."):
            await mcp_manager.add_server(
                name=server_name,
                url=selected.get("url"),
                command=selected.get("command"),
                env=selected.get("env", {}),
            )

    server = mcp_manager.servers.get(server_name)
    connected = server and server.connected

    if connected:
        tools = server.tools
        tool_names = ", ".join(t.get("name", "?") for t in tools[:6])
        suffix = "..." if len(tools) > 6 else ""
        ui.console.print(
            f"\n[green]✓[/green] Connected to [bold]{server_name}[/bold] "
            f"— {len(tools)} tool(s)"
            + (f": [dim]{tool_names}{suffix}[/dim]" if tool_names else "")
        )
    else:
        ui.warning(
            f"Could not connect to [bold]{server_name}[/bold] right now, "
            "but will try to use it anyway."
        )

    # ── Get the user's prompt ─────────────────────────────────────────────────
    ui.console.print()
    try:
        goal = await asyncio.to_thread(
            Prompt.ask,
            f"[bold cyan]omega[/bold cyan] [dim][{server_name}][/dim] [dim]›[/dim]",
        )
        goal = goal.strip()
    except (KeyboardInterrupt, EOFError):
        ui.console.print("[dim]Cancelled.[/dim]")
        return

    if not goal:
        return

    # Augment the prompt to force the AI to use the MCP server tools
    augmented_goal = (
        f"{goal}\n\n"
        f"(SYSTEM INSTRUCTION: You MUST use the tools provided by the connected "
        f"MCP server '{server_name}' to complete this task. Prioritize these MCP tools "
        f"over default OS commands. If browsing the web, you must use the {server_name} browser tools.)"
    )

    # ── Execute the goal (MCP server is now active in the registry) ───────────
    await _execute_goal_flow(augmented_goal)


async def _handle_mcp_add(raw: str):

    """Handle 'mcp add' — supports JSON config blocks and plain 'name url' syntax.

    Accepted JSON formats:
      {"mcpServers": {"server-name": {"command": "npx", "args": [...], "env": {...}}}}
      {"server-name": {"command": "npx", "args": [...]}}
      {"name": "server-name", "command": "npx", "args": [...]}
      {"name": "server-name", "url": "http://..."}
    Plain text:
      <name> <url>
    """
    from omega.mcp.manager import mcp_manager

    # ── Try to parse as JSON ──────────────────────────────────────────────────
    json_start = raw.find("{")
    if json_start != -1:
        json_str = raw[json_start:]
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as exc:
            ui.error(f"Invalid JSON: {exc}")
            return

        # Normalise to a list of server dicts: [{name, url?, command?, args?, env?}]
        server_entries = []

        if "mcpServers" in data:
            # Standard Claude/Cursor format
            for srv_name, srv_cfg in data["mcpServers"].items():
                entry = {"name": srv_name, **srv_cfg}
                server_entries.append(entry)
        elif isinstance(data, dict) and all(isinstance(v, dict) for v in data.values()):
            # Bare dict of servers without the "mcpServers" wrapper
            for srv_name, srv_cfg in data.items():
                entry = {"name": srv_name, **srv_cfg}
                server_entries.append(entry)
        else:
            # Single server object: {"name": ..., "url": ...} or {"name": ..., "command": ...}
            server_entries.append(data)

        if not server_entries:
            ui.error("No server entries found in JSON config.")
            return

        added, failed = [], []
        for entry in server_entries:
            srv_name = entry.get("name")
            if not srv_name:
                ui.error("Server entry is missing a 'name' field — skipping.")
                continue

            url = entry.get("url")
            args = entry.get("args", [])
            command_str = entry.get("command")
            env = entry.get("env", {})

            # Build the command list: ["npx", "-y", "chrome-devtools-mcp@latest"]
            command = None
            if command_str:
                command = [command_str] + list(args)

            connected = await mcp_manager.add_server(
                name=srv_name, url=url, command=command, env=env
            )
            if connected:
                added.append(srv_name)
            else:
                failed.append(srv_name)

        for n in added:
            ui.success(f"Connected to MCP server: {n}")
        for n in failed:
            ui.error(f"Could not connect to MCP server: {n} (saved for later auto-connect)")
        return

    # ── Plain text: <name> <url> ──────────────────────────────────────────────
    parts = raw.split()
    if len(parts) >= 2:
        name, url = parts[0], parts[1]
        connected = await mcp_manager.add_server(name=name, url=url)
        if connected:
            ui.success(f"Connected to MCP server: {name}")
        else:
            ui.error(f"Could not connect to MCP server: {name} (saved for later auto-connect)")
    else:
        ui.error(
            "Usage:  mcp add <name> <url>\n"
            "        mcp add '{\"mcpServers\":{\"name\":{\"command\":\"npx\",\"args\":[\"-y\",\"pkg@latest\"]}}}'"
        )


async def _execute_goal_flow(goal: str):
    """Execute a goal through the full orchestrator pipeline"""
    from omega.agents.orchestrator import Orchestrator
    from omega.security.manager import security

    security._approval_callback = ui.approval_prompt

    events_log = []

    async def on_progress(event_type, message):
        events_log.append((event_type, message))
        if event_type == "planning":
            ui.thinking("planner").__enter__()
        elif event_type == "planned":
            ui.success(message)
        elif event_type == "executing":
            ui.agent_message("orchestrator", message, style="cyan")
        elif event_type in ("task_done", "task_timeout"):
            ui.console.print(f"  {message}")

    with ui.spinner(f"Planning: {goal[:60]}..."):
        orchestrator = Orchestrator()

        from omega.agents.planner import PlannerAgent
        planner = PlannerAgent()
        plan_result = await planner.run(goal)

    if not plan_result.success:
        ui.error(f"Planning failed: {plan_result.error}")
        return

    ui.print_plan(plan_result.output)

    # Convert plan to task objects and execute
    for task_spec in plan_result.output.get("tasks", []):
        task = type("T", (), {})()

    ui.console.print()
    result = await orchestrator.execute_goal(goal, on_progress=_make_progress_printer())

    ui.print_result(result)


def _make_progress_printer():
    async def printer(event_type, message):
        if event_type == "executing":
            ui.console.print(f"  [cyan]▶[/cyan] {message}")
        elif event_type == "task_done":
            ui.console.print(f"  {message}")
        elif event_type == "task_timeout":
            ui.console.print(f"  [yellow]{message}[/yellow]")
    return printer


async def _run_research(topic: str):
    from omega.agents.researcher import ResearchAgent
    agent = ResearchAgent()
    with ui.thinking("researcher"):
        result = await agent.run(topic)
    if result.success:
        ui.print_research(result.output)
    else:
        ui.error(result.error or "Research failed")


async def _run_code(task: str):
    from omega.agents.coder import CoderAgent
    agent = CoderAgent()
    with ui.thinking("coder"):
        result = await agent.run(task, {"project_path": os.getcwd()})
    if result.success:
        ui.success(result.output.get("explanation", "Code task completed"))
        for f in result.output.get("files_written", []):
            ui.console.print(f"  [green]✓[/green] {f}")
    else:
        ui.error(result.error or "Code task failed")


async def _run_browse(url: str):
    from omega.agents.browser import BrowserAgent
    agent = BrowserAgent()
    if not url.startswith("http"):
        url = f"https://{url}"
    with ui.thinking("browser"):
        result = await agent.run(f"Navigate to {url} and summarize the page content")
    if result.success:
        ui.console.print(result.output)
    else:
        ui.error(result.error or "Browse failed")
    await agent.close()


async def _run_deploy(path: str):
    from omega.agents.devops import DevOpsAgent
    agent = DevOpsAgent()
    with ui.thinking("devops"):
        result = await agent.run(f"Deploy the project at {path}", {"project_path": path})
    if result.success:
        ui.success("Deployment task completed")
        ui.console.print(result.output)
    else:
        ui.error(result.error or "Deploy failed")


async def _run_workflow(name: str):
    from omega.workflows.engine import workflow_engine

    async def on_progress(event_type, message):
        ui.console.print(f"  [cyan]▶[/cyan] {message}")

    with ui.spinner(f"Running workflow: {name}"):
        result = await workflow_engine.run(name, on_progress=on_progress)
    if result.get("success"):
        ui.success(f"Workflow '{name}' completed")
    else:
        ui.error(result.get("error", f"Workflow '{name}' failed"))


async def _create_workflow_nl(description: str):
    from omega.workflows.engine import workflow_engine

    async def on_progress(event_type, message):
        ui.console.print(f"  [cyan]▶[/cyan] {message}")

    with ui.spinner("Creating and running workflow..."):
        result = await workflow_engine.run_from_nl(description, on_progress=on_progress)
    if result.get("success"):
        ui.success("Workflow created and executed successfully")
    else:
        ui.error(result.get("error", "Workflow creation failed"))


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="API server host"),
    port: int = typer.Option(8888, help="API server port"),
):
    """Start the OMEGA REST API server"""
    config.ensure_dirs()
    if not _check_api_key():
        raise typer.Exit(1)

    ui.print_banner()
    ui.info(f"Starting API server at http://{host}:{port}")
    ui.info(f"API docs available at http://{host}:{port}/docs")

    config.api_host = host
    config.api_port = port

    from omega.api.server import start_api
    start_api()


@app.command()
def init():
    """Initialize OMEGA configuration and directories"""
    config.ensure_dirs()
    ui.print_banner()
    ui.success(f"OMEGA home directory created: {config.omega_home}")

    env_file = Path(".env")
    if not env_file.exists():
        api_key = typer.prompt("Enter your OpenRouter API key (get one free at openrouter.ai/keys)",
                                default="", show_default=False)
        if api_key:
            env_file.write_text(f"OPENROUTER_API_KEY={api_key}\n")
            ui.success(".env file created")
    else:
        ui.info(".env file already exists")

    ui.console.print("\n[bold cyan]Setup complete![/bold cyan] Run [white]omega run[/white] to start.\n")


@app.command()
def version():
    """Show OMEGA version"""
    from omega import __version__
    ui.console.print(f"OMEGA v{__version__}")


if __name__ == "__main__":
    app()
