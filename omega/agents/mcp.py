"""MCP Agent - Specialized agent for calling Model Context Protocol tools"""

import json
from typing import Any, Dict, List, Optional
import structlog

from omega.agents.base import BaseAgent, AgentResult
from omega.mcp.manager import mcp_manager
from omega.models.router import TaskType

logger = structlog.get_logger(__name__)


class MCPAgent(BaseAgent):
    name = "mcp"
    description = "Specialized agent for calling Model Context Protocol (MCP) tools added by the user"
    task_type = TaskType.GENERAL

    @property
    def system_prompt(self) -> str:
        # List all available MCP tools in the prompt
        tools_by_server = mcp_manager.list_all_tools()
        tools_info = []
        for server_name, tools in tools_by_server.items():
            for t in tools:
                tools_info.append({
                    "server": server_name,
                    "name": t.get("name"),
                    "description": t.get("description"),
                    "input_schema": t.get("inputSchema", {})
                })
        
        tools_json = json.dumps(tools_info, indent=2)
        
        return f"""You are the MCP Tool Calling Agent for OMEGA.
Your primary role is to select and call the best available MCP tools added by the user to execute the given task.

Available MCP Tools:
{tools_json}

Instructions:
1. Analyze the user's task carefully.
2. Select the most appropriate MCP tool(s) from the list above.
3. Call the selected tool by outputting JSON in the following format:
{{
  "call_tool": {{
    "server": "server_name",
    "tool": "tool_name",
    "arguments": {{
      "param1": "value1"
    }}
  }},
  "thought": "Your reasoning process for why you chose this tool"
}}

4. If you have called a tool and received the result, you can either call another tool or output the final result in the following format:
{{
  "final_result": "The final response or explanation based on the tool execution output",
  "success": true
}}

Ensure that you prioritize MCP tools over any local terminal commands or fallback mechanisms. If no tools match, explain why and output final_result with success: false.
"""

    async def _execute(self, task: str, context: Dict) -> AgentResult:
        messages = [{"role": "user", "content": f"Task: {task}"}]
        
        max_steps = 10
        for step in range(max_steps):
            response = await self.think(messages)
            try:
                res_str = response.strip()
                if "```json" in res_str:
                    res_str = res_str.split("```json")[1].split("```")[0].strip()
                elif "```" in res_str:
                    res_str = res_str.split("```")[1].split("```")[0].strip()
                
                data = json.loads(res_str)
            except Exception as e:
                return AgentResult(success=False, error=f"Failed to parse agent JSON response: {response}")
            
            if "call_tool" in data:
                call_spec = data["call_tool"]
                server_name = call_spec.get("server")
                tool_name = call_spec.get("tool")
                arguments = call_spec.get("arguments", {})
                
                from omega.ui.terminal import ui
                ui.console.print(f"  [yellow]⚙[/yellow] MCPAgent calling tool [bold]{tool_name}[/bold] on server [bold]{server_name}[/bold]...")
                
                try:
                    tool_result = await mcp_manager.call_tool(server_name, tool_name, arguments)
                    ui.console.print(f"  [green]✓[/green] Tool result received.")
                except Exception as e:
                    tool_result = f"Error calling tool: {e}"
                    ui.console.print(f"  [red]✗[/red] Tool call failed: {e}")
                
                messages.append({"role": "assistant", "content": response})
                messages.append({"role": "user", "content": f"Tool result from {server_name}/{tool_name}:\n{json.dumps(tool_result, indent=2)}"})
            elif "final_result" in data:
                return AgentResult(
                    success=data.get("success", True),
                    output=data.get("final_result")
                )
            else:
                return AgentResult(success=True, output=response)
        
        return AgentResult(success=False, error="Exceeded maximum steps for MCP tool execution.")
