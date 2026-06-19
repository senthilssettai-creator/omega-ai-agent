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
                ui.console.print(f"[cyan]●[/cyan] {name} - {len(server.tools)} tools")

        elif cmd_lower.startswith("mcp add "):
            parts = user_input[8:].split()
            if len(parts) >= 2:
                name, url = parts[0], parts[1]
                connected = await mcp_manager.add_server(name=name, url=url)
                if connected:
                    ui.success(f"Connected to MCP server: {name}")
                else:
                    ui.error(f"Could not connect to: {name}")
            else:
                ui.error("Usage: mcp add <name> <url>")

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
