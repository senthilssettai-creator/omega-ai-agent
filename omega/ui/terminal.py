# -*- coding: utf-8 -*-
"""OMEGA Terminal UI - Rich-powered beautiful terminal interface"""

import asyncio
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
from pathlib import Path

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.prompt import Prompt, Confirm
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from rich.tree import Tree
from rich.markdown import Markdown
from rich.columns import Columns
from rich import box
import structlog

logger = structlog.get_logger(__name__)

console = Console()

OMEGA_BANNER = r"""
 ██████╗ ███╗   ███╗███████╗ ██████╗  █████╗ 
██╔═══██╗████╗ ████║██╔════╝██╔════╝ ██╔══██╗
██║   ██║██╔████╔██║█████╗  ██║  ███╗███████║
██║   ██║██║╚██╔╝██║██╔══╝  ██║   ██║██╔══██║
╚██████╔╝██║ ╚═╝ ██║███████╗╚██████╔╝██║  ██║
 ╚═════╝ ╚═╝     ╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝
"""

THEME = {
    "primary": "bold cyan",
    "secondary": "bold blue",
    "success": "bold green",
    "warning": "bold yellow",
    "error": "bold red",
    "muted": "dim white",
    "agent": "bold magenta",
    "tool": "bold yellow",
    "code": "bold bright_white",
}


class OmegaUI:
    """Main terminal UI manager"""

    def __init__(self):
        self.console = console
        self._live: Optional[Live] = None
        self._progress: Optional[Progress] = None
        self._task_id = None
        self._agent_statuses: Dict[str, str] = {}
        self._log_lines: List[str] = []
        self._max_log_lines = 20

    def print_banner(self):
        """Print the OMEGA startup banner"""
        self.console.print()
        self.console.print(OMEGA_BANNER, style="bold cyan", highlight=False)
        self.console.print(
            Panel(
                "[bold cyan]The Ultimate Autonomous Terminal AI Agent[/bold cyan]\n"
                "[dim]Powered by OpenRouter · Free Models · Zero Lock-in[/dim]",
                border_style="cyan",
                padding=(0, 2),
            )
        )
        self.console.print()

    def print_status(self, memory_stats: Dict, config_info: Dict):
        """Print system status table"""
        table = Table(box=box.ROUNDED, border_style="cyan", padding=(0, 1), expand=True)
        table.add_column("Component", style="bold cyan", width=16, no_wrap=True)
        table.add_column("Status", width=14, no_wrap=True)
        table.add_column("Info", style="dim", ratio=1)

        table.add_row("Memory", "[green]● Active[/green]",
                       f"{memory_stats.get('memories', 0)} memories · {memory_stats.get('episodes', 0)} episodes")
        table.add_row("Model Router", "[green]● Ready[/green]",
                       "Auto-selects best free OpenRouter model")
        table.add_row("Agents", "[green]● 8 Active[/green]",
                       "Planner · Researcher · Coder · Browser · DevOps · Executor · Critic · MCP")
        table.add_row("Plugins", "[green]● Loaded[/green]",
                       "Filesystem · Terminal · Git · Search · Browser · Docker · API · DB")
        table.add_row("Security", "[green]● Active[/green]",
                       "Permission gates · Approval workflow")
        table.add_row("Sandbox", "[green]● Ready[/green]",
                       "Docker + subprocess isolation")
        table.add_row("MCP", "[green]● Ready[/green]",
                       "Auto-discovers MCP servers")
        table.add_row("Workflows", "[green]● Ready[/green]",
                       f"{config_info.get('workflow_count', 0)} workflows loaded")

        self.console.print(Panel(table, title="[bold cyan]OMEGA Status[/bold cyan]", border_style="cyan"))

    def print_help(self):
        """Print help information"""
        help_text = """
[bold cyan]OMEGA Commands[/bold cyan]

[bold]Goal Execution[/bold]
  [cyan]>[/cyan] [white]Any natural language goal[/white]         Execute autonomously
  [cyan]>[/cyan] [white]run workflow <name>[/white]               Run a saved workflow
  [cyan]>[/cyan] [white]create workflow <description>[/white]     Create workflow from description

[bold]Memory[/bold]
  [cyan]>[/cyan] [white]remember <fact>[/white]                   Store a fact
  [cyan]>[/cyan] [white]recall <query>[/white]                    Search memory
  [cyan]>[/cyan] [white]memory stats[/white]                      Show memory statistics

[bold]Agents[/bold]
  [cyan]>[/cyan] [white]research <topic>[/white]                  Research a topic
  [cyan]>[/cyan] [white]code <task>[/white]                       Write/debug code
  [cyan]>[/cyan] [white]browse <url>[/white]                      Open URL in browser agent
  [cyan]>[/cyan] [white]deploy <path>[/white]                     Deploy a project

[bold]System[/bold]
  [cyan]>[/cyan] [white]status[/white]                            Show system status
  [cyan]>[/cyan] [white]models[/white]                            List available free models
  [cyan]>[/cyan] [white]plugins[/white]                           List loaded plugins
  [cyan]>[/cyan] [white]mcp list[/white]                          List all saved MCP servers
  [cyan]>[/cyan] [white]mcp add[/white]                           Interactive wizard to add a server
  [cyan]>[/cyan] [white]mcp add <json-config>[/white]             Add server(s) from JSON inline
  [cyan]>[/cyan] [white]mcp use[/white]                           Pick a server and run a prompt with it
  [cyan]>[/cyan] [white]mcp remove <name>[/white]               Remove a saved server
  [cyan]>[/cyan] [white]clear[/white]                             Clear screen
  [cyan]>[/cyan] [white]exit[/white]                              Exit OMEGA

[bold]JSON config format (Claude / Cursor style)[/bold]
  [dim]{"mcpServers":{"my-server":{"command":"npx","args":["-y","pkg@latest"]}}}[/dim]
"""
        self.console.print(Panel(help_text.strip(), title="[bold cyan]Help[/bold cyan]",
                                  border_style="cyan"))

    def agent_message(self, agent: str, message: str, style: str = "cyan"):
        """Print a message from an agent"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.console.print(
            f"[dim]{timestamp}[/dim] [bold {style}][{agent.upper()}][/bold {style}] {message}"
        )

    def print_plan(self, plan: Dict):
        """Render an execution plan as a tree"""
        tree = Tree(
            f"[bold cyan]📋 Plan: {plan.get('goal', 'Unknown')}[/bold cyan]",
        )

        summary_node = tree.add(f"[dim]{plan.get('summary', '')}[/dim]")

        tasks_node = tree.add("[bold]Tasks[/bold]")
        for task in plan.get("tasks", []):
            agent = task.get("agent", "executor")
            icon = self._agent_icon(agent)
            task_node = tasks_node.add(
                f"{icon} [bold]{task['name']}[/bold] [dim]({agent})[/dim]"
            )
            task_node.add(f"[dim]{task.get('description', '')[:80]}[/dim]")
            if task.get("depends_on"):
                task_node.add(f"[dim yellow]Depends: {', '.join(task['depends_on'])}[/dim yellow]")

        risks = plan.get("risks", [])
        if risks:
            risk_node = tree.add("[bold yellow]⚠ Risks[/bold yellow]")
            for risk in risks:
                risk_node.add(f"[yellow]{risk}[/yellow]")

        est = plan.get("estimated_total_minutes", 0)
        tree.add(f"[dim]Estimated: ~{est} minutes[/dim]")

        self.console.print(Panel(tree, border_style="cyan"))

    def _agent_icon(self, agent: str) -> str:
        icons = {
            "planner": "🧠",
            "researcher": "🔍",
            "coder": "💻",
            "browser": "🌐",
            "devops": "⚙️",
            "executor": "⚡",
            "critic": "🔬",
            "mcp": "🔌",
            "memory": "💾",
        }
        return icons.get(agent, "🤖")

    def print_result(self, result: Dict):
        """Print the final execution result"""
        success = result.get("success", False)
        border = "green" if success else "red"
        icon = "✅" if success else "❌"
        status = "SUCCESS" if success else "FAILED"

        # Summary panel
        completed = result.get("completed_tasks", 0)
        total = result.get("total_tasks", 0)
        duration = result.get("duration", 0)

        summary = (
            f"{icon} [bold {'green' if success else 'red'}]{status}[/bold {'green' if success else 'red'}]\n\n"
            f"[white]Tasks:[/white] [bold]{completed}/{total}[/bold] completed\n"
            f"[white]Duration:[/white] [bold]{duration:.1f}s[/bold]\n"
        )

        if result.get("error"):
            summary += f"\n[red]Error:[/red] {result['error']}"

        self.console.print(Panel(summary, title="[bold]Execution Result[/bold]",
                                  border_style=border))

        # Task breakdown table
        tasks = result.get("tasks", [])
        if tasks:
            table = Table(box=box.SIMPLE, padding=(0, 1))
            table.add_column("Task", style="white")
            table.add_column("Agent", style="cyan", width=12)
            table.add_column("Status", width=8)
            table.add_column("Output", style="dim", max_width=50)

            for task in tasks:
                status_str = (
                    "[green]✓[/green]" if task["status"] == "done"
                    else "[red]✗[/red]" if task["status"] == "failed"
                    else "[yellow]?[/yellow]"
                )
                output = (task.get("output") or "")[:60]
                duration_s = f" ({task['duration']:.1f}s)" if task.get("duration") else ""
                table.add_row(
                    f"{task['name']}{duration_s}",
                    task.get("agent", ""),
                    status_str,
                    output,
                )

            self.console.print(table)

    def print_research(self, result: Dict):
        """Render a research report"""
        report = result.get("report", "No report generated")
        self.console.print(Panel(
            Markdown(report),
            title="[bold cyan]Research Report[/bold cyan]",
            border_style="cyan",
            padding=(1, 2),
        ))

    def print_code(self, code: str, language: str = "python"):
        """Syntax-highlighted code display"""
        syntax = Syntax(code, language, theme="monokai", line_numbers=True,
                         word_wrap=True)
        self.console.print(Panel(syntax, title=f"[bold cyan]{language.title()} Code[/bold cyan]",
                                  border_style="cyan"))

    def print_memory_stats(self, stats: Dict):
        """Print memory statistics"""
        table = Table(box=box.SIMPLE)
        table.add_column("Memory Type", style="cyan")
        table.add_column("Count", style="bold white", justify="right")

        table.add_row("Short-term messages", str(stats.get("short_term_messages", 0)))
        table.add_row("Long-term memories", str(stats.get("memories", 0)))
        table.add_row("Episodes (actions)", str(stats.get("episodes", 0)))
        table.add_row("Workflows", str(stats.get("workflows", 0)))
        table.add_row("Knowledge edges", str(stats.get("knowledge_edges", 0)))

        self.console.print(Panel(table, title="[bold cyan]Memory Stats[/bold cyan]",
                                  border_style="cyan"))

    def print_recall_results(self, results: List[Dict], query: str):
        """Display semantic recall results"""
        if not results:
            self.console.print(f"[yellow]No memories found for: {query}[/yellow]")
            return

        self.console.print(f"\n[bold cyan]Recall results for:[/bold cyan] {query}\n")
        for i, result in enumerate(results, 1):
            distance = result.get("distance", 0)
            relevance = max(0, 1 - distance) if distance else 1
            bar = "█" * int(relevance * 10) + "░" * (10 - int(relevance * 10))
            self.console.print(
                f"[bold cyan]{i}.[/bold cyan] [dim]{bar}[/dim] {result.get('text', '')[:200]}"
            )
        self.console.print()

    def print_models(self, models: List[Dict]):
        """Display available free models"""
        table = Table(box=box.ROUNDED, border_style="cyan")
        table.add_column("Model", style="cyan")
        table.add_column("Context", justify="right")
        table.add_column("Best For", style="dim")

        for model in models[:20]:
            ctx = model.get("context_length", 0)
            ctx_str = f"{ctx//1000}K" if ctx else "?"
            table.add_row(model.get("id", ""), ctx_str, "Free tier")

        self.console.print(Panel(table, title="[bold cyan]Available Free Models[/bold cyan]",
                                  border_style="cyan"))

    def print_workflows(self, workflows: List[Dict]):
        """Display workflow list"""
        if not workflows:
            self.console.print("[dim]No workflows saved yet.[/dim]")
            return

        table = Table(box=box.SIMPLE)
        table.add_column("Name", style="cyan bold")
        table.add_column("Description", style="dim")
        table.add_column("Steps", justify="right")
        table.add_column("Runs", justify="right")
        table.add_column("Schedule", style="yellow")

        for wf in workflows:
            table.add_row(
                wf["name"],
                wf.get("description", "")[:50],
                str(len(wf.get("steps", []))),
                str(wf.get("run_count", 0)),
                wf.get("schedule", "-"),
            )

        self.console.print(Panel(table, title="[bold cyan]Workflows[/bold cyan]",
                                  border_style="cyan"))

    async def approval_prompt(self, action: str, description: str,
                               risk: str, context: Dict) -> bool:
        """Interactive approval prompt for dangerous actions"""
        risk_color = {"low": "green", "medium": "yellow", "high": "red", "critical": "bold red"}.get(risk, "yellow")

        self.console.print()
        self.console.print(Panel(
            f"[bold yellow]⚠ APPROVAL REQUIRED[/bold yellow]\n\n"
            f"[white]Action:[/white] [bold]{action}[/bold]\n"
            f"[white]Description:[/white] {description}\n"
            f"[white]Risk Level:[/white] [{risk_color}]{risk.upper()}[/{risk_color}]",
            border_style="yellow",
            title="Security Gate",
        ))

        try:
            approved = Confirm.ask("[bold yellow]Allow this action?[/bold yellow]", default=False)
            return approved
        except (KeyboardInterrupt, EOFError):
            return False

    def spinner(self, message: str):
        """Return a context manager for spinner display"""
        return self.console.status(f"[bold cyan]{message}[/bold cyan]",
                                    spinner="dots", spinner_style="cyan")

    def success(self, msg: str):
        self.console.print(f"[bold green]✓[/bold green] {msg}")

    def error(self, msg: str):
        self.console.print(f"[bold red]✗[/bold red] {msg}")

    def warning(self, msg: str):
        self.console.print(f"[bold yellow]⚠[/bold yellow] {msg}")

    def info(self, msg: str):
        self.console.print(f"[bold cyan]ℹ[/bold cyan] {msg}")

    def thinking(self, agent: str):
        """Show agent is thinking"""
        icon = {
            "planner": "🧠", "researcher": "🔍", "coder": "💻",
            "browser": "🌐", "devops": "⚙️", "executor": "⚡", "critic": "🔬"
        }.get(agent, "🤖")
        return self.console.status(
            f"[bold cyan]{icon} {agent.upper()} thinking...[/bold cyan]",
            spinner="dots",
        )


# Global UI instance
ui = OmegaUI()
