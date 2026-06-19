"""API Tool"""
import httpx
import json
from typing import Dict, Optional, Any
from omega.tools.registry import BaseTool, ToolResult


class ApiTool(BaseTool):
    name = "api"
    description = "Make REST and GraphQL API calls"

    async def execute(self, action: str, **kwargs) -> ToolResult:
        try:
            method = action.upper()
            url = kwargs["url"]
            headers = kwargs.get("headers", {})
            body = kwargs.get("body") or kwargs.get("json")
            params = kwargs.get("params")
            timeout = kwargs.get("timeout", 30)

            async with httpx.AsyncClient(timeout=timeout) as client:
                if method == "GET":
                    r = await client.get(url, headers=headers, params=params)
                elif method == "POST":
                    if isinstance(body, (dict, list)):
                        r = await client.post(url, headers=headers, json=body)
                    else:
                        r = await client.post(url, headers=headers, content=body)
                elif method == "PUT":
                    r = await client.put(url, headers=headers, json=body)
                elif method == "PATCH":
                    r = await client.patch(url, headers=headers, json=body)
                elif method == "DELETE":
                    r = await client.delete(url, headers=headers)
                elif method == "GRAPHQL":
                    query = kwargs.get("query", "")
                    variables = kwargs.get("variables", {})
                    r = await client.post(url, headers=headers, json={"query": query, "variables": variables})
                else:
                    return ToolResult(success=False, error=f"Unknown method: {method}")

                try:
                    data = r.json()
                except Exception:
                    data = r.text

                return ToolResult(
                    success=r.status_code < 400,
                    output={"status": r.status_code, "data": data, "headers": dict(r.headers)},
                )
        except Exception as e:
            return ToolResult(success=False, error=str(e))
