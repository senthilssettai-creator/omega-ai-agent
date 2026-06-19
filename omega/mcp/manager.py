"""OMEGA MCP (Model Context Protocol) Support

Auto-discovers and connects to MCP servers.
Supports filesystem, GitHub, Browser, Database, Notion, Slack, Google Drive and custom servers.
"""

import asyncio
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
import structlog
import httpx

from omega.config import config

logger = structlog.get_logger(__name__)


class MCPServer:
    """Represents a connected MCP server"""

    def __init__(self, name: str, url: Optional[str] = None,
                 command: Optional[List[str]] = None,
                 env: Optional[Dict[str, str]] = None):
        self.name = name
        self.url = url
        self.command = command
        self.env = env or {}
        self._process: Optional[subprocess.Popen] = None
        self._tools: List[Dict] = []
        self._connected = False

    async def connect(self) -> bool:
        """Connect to the MCP server"""
        if self.url:
            return await self._connect_http()
        elif self.command:
            return await self._connect_stdio()
        return False

    async def _connect_http(self) -> bool:
        """Connect to HTTP-based MCP server"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(f"{self.url}/tools")
                if r.status_code == 200:
                    data = r.json()
                    self._tools = data.get("tools", [])
                    self._connected = True
                    logger.info("mcp_connected", server=self.name, tools=len(self._tools))
                    return True
        except Exception as e:
            logger.warning("mcp_http_connect_failed", server=self.name, error=str(e))
        return False

    async def _connect_stdio(self) -> bool:
        """Connect to stdio-based MCP server"""
        try:
            import os
            env = {**os.environ, **self.env}
            self._process = subprocess.Popen(
                self.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )
            # Send initialize request
            init_request = json.dumps({
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "clientInfo": {"name": "OMEGA", "version": "1.0.0"},
                    "capabilities": {},
                }
            }) + "\n"

            self._process.stdin.write(init_request.encode())
            self._process.stdin.flush()

            # Read response (non-blocking with timeout)
            import select
            ready = select.select([self._process.stdout], [], [], 5.0)
            if ready[0]:
                response_line = self._process.stdout.readline()
                response = json.loads(response_line)
                if "result" in response:
                    # List tools
                    await self._list_tools_stdio()
                    self._connected = True
                    logger.info("mcp_stdio_connected", server=self.name)
                    return True
        except Exception as e:
            logger.warning("mcp_stdio_connect_failed", server=self.name, error=str(e))
        return False

    async def _list_tools_stdio(self):
        """List available tools via stdio"""
        try:
            request = json.dumps({
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
                "params": {},
            }) + "\n"
            self._process.stdin.write(request.encode())
            self._process.stdin.flush()

            import select
            ready = select.select([self._process.stdout], [], [], 5.0)
            if ready[0]:
                response_line = self._process.stdout.readline()
                response = json.loads(response_line)
                self._tools = response.get("result", {}).get("tools", [])
        except Exception as e:
            logger.warning("mcp_list_tools_failed", server=self.name, error=str(e))

    async def call_tool(self, tool_name: str, arguments: Dict) -> Any:
        """Call an MCP tool"""
        if self.url:
            return await self._call_http(tool_name, arguments)
        elif self._process:
            return await self._call_stdio(tool_name, arguments)
        return None

    async def _call_http(self, tool_name: str, arguments: Dict) -> Any:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                f"{self.url}/tools/{tool_name}",
                json={"arguments": arguments},
            )
            return r.json()

    async def _call_stdio(self, tool_name: str, arguments: Dict) -> Any:
        try:
            request = json.dumps({
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": arguments},
            }) + "\n"
            self._process.stdin.write(request.encode())
            self._process.stdin.flush()

            import select
            ready = select.select([self._process.stdout], [], [], 30.0)
            if ready[0]:
                response_line = self._process.stdout.readline()
                response = json.loads(response_line)
                return response.get("result")
        except Exception as e:
            logger.error("mcp_call_failed", tool=tool_name, error=str(e))
        return None

    @property
    def tools(self) -> List[Dict]:
        return self._tools

    @property
    def connected(self) -> bool:
        return self._connected

    def disconnect(self):
        if self._process:
            self._process.terminate()
            self._process = None
        self._connected = False


class MCPManager:
    """Manages multiple MCP server connections"""

    def __init__(self):
        self._servers: Dict[str, MCPServer] = {}
        self._config_path = config.omega_home / "mcp_servers.json"

    async def auto_discover(self):
        """Auto-discover MCP servers from config file"""
        if self._config_path.exists():
            with open(self._config_path) as f:
                server_configs = json.load(f)
            for sc in server_configs:
                server = MCPServer(
                    name=sc["name"],
                    url=sc.get("url"),
                    command=sc.get("command"),
                    env=sc.get("env", {}),
                )
                if await server.connect():
                    self._servers[server.name] = server

    async def add_server(self, name: str, url: Optional[str] = None,
                          command: Optional[List[str]] = None,
                          env: Optional[Dict] = None) -> bool:
        """Add and connect to a new MCP server"""
        server = MCPServer(name=name, url=url, command=command, env=env or {})
        if await server.connect():
            self._servers[name] = server
            await self._save_config()
            return True
        return False

    async def _save_config(self):
        """Save server configs to disk"""
        configs = []
        for name, server in self._servers.items():
            configs.append({
                "name": name,
                "url": server.url,
                "command": server.command,
                "env": server.env,
            })
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._config_path, "w") as f:
            json.dump(configs, f, indent=2)

    async def call_tool(self, server_name: str, tool_name: str, arguments: Dict) -> Any:
        """Call a tool on a specific MCP server"""
        server = self._servers.get(server_name)
        if not server:
            raise ValueError(f"MCP server not found: {server_name}")
        return await server.call_tool(tool_name, arguments)

    def list_all_tools(self) -> Dict[str, List[Dict]]:
        """List all tools across all connected servers"""
        return {name: server.tools for name, server in self._servers.items()}

    def get_server(self, name: str) -> Optional[MCPServer]:
        return self._servers.get(name)

    @property
    def servers(self) -> Dict[str, MCPServer]:
        return self._servers


# Global MCP manager
mcp_manager = MCPManager()
