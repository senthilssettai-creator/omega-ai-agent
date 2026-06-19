"""OMEGA FastAPI REST API - Programmatic access to all OMEGA capabilities"""

import asyncio
import json
import time
import uuid
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import structlog

from omega.config import config

logger = structlog.get_logger(__name__)

app = FastAPI(
    title="OMEGA API",
    description="Autonomous Terminal AI Agent - REST API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Active sessions
_sessions: Dict[str, Dict] = {}
_websocket_connections: List[WebSocket] = []


# ── Request/Response Models ──────────────────────────────────────────────────

class GoalRequest(BaseModel):
    goal: str
    context: Optional[Dict] = None
    stream: bool = False


class AgentRequest(BaseModel):
    task: str
    context: Optional[Dict] = None


class MemoryRequest(BaseModel):
    content: str
    type_: str = "fact"
    key: Optional[str] = None
    importance: float = 0.5


class RecallRequest(BaseModel):
    query: str
    n: int = 5


class WorkflowRequest(BaseModel):
    name: str
    description: str = ""
    steps: List[Dict]
    schedule: Optional[str] = None


class RunWorkflowRequest(BaseModel):
    context: Optional[Dict] = None


class MCPServerRequest(BaseModel):
    name: str
    url: Optional[str] = None
    command: Optional[List[str]] = None
    env: Optional[Dict[str, str]] = None


class ApprovalRequest(BaseModel):
    session_id: str
    approved: bool


# ── Core Endpoints ───────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {
        "name": "OMEGA",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    from omega.memory.store import memory
    return {
        "status": "healthy",
        "memory": memory.stats(),
        "timestamp": time.time(),
    }


@app.post("/goals")
async def execute_goal(request: GoalRequest, background_tasks: BackgroundTasks):
    """Execute a high-level goal autonomously"""
    session_id = str(uuid.uuid4())
    _sessions[session_id] = {
        "goal": request.goal,
        "status": "running",
        "started_at": time.time(),
        "events": [],
    }

    async def run():
        from omega.agents.orchestrator import Orchestrator
        from omega.security.manager import security

        # Set up approval callback
        async def approval_cb(action, description, risk, context):
            _sessions[session_id]["pending_approval"] = {
                "action": action,
                "description": description,
                "risk": risk,
                "context": context,
            }
            # Wait for approval via /goals/{session_id}/approve
            for _ in range(60):  # Wait up to 60s
                await asyncio.sleep(1)
                if "approval_result" in _sessions[session_id]:
                    result = _sessions[session_id].pop("approval_result")
                    _sessions[session_id].pop("pending_approval", None)
                    return result
            return False  # Timeout = deny

        security._approval_callback = approval_cb

        async def on_progress(event_type, message):
            event = {"type": event_type, "message": message, "timestamp": time.time()}
            _sessions[session_id]["events"].append(event)
            # Broadcast to websockets
            for ws in _websocket_connections[:]:
                try:
                    await ws.send_json({"session_id": session_id, **event})
                except Exception:
                    pass

        orchestrator = Orchestrator(progress_callback=on_progress)
        result = await orchestrator.execute_goal(
            request.goal,
            context=request.context,
            on_progress=on_progress,
        )
        _sessions[session_id].update({
            "status": "done",
            "result": result,
            "finished_at": time.time(),
        })

    background_tasks.add_task(run)
    return {"session_id": session_id, "status": "started"}


@app.get("/goals/{session_id}")
async def get_goal_status(session_id: str):
    """Get the status of a running goal"""
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    return session


@app.post("/goals/{session_id}/approve")
async def approve_action(session_id: str, request: ApprovalRequest):
    """Approve or deny a pending dangerous action"""
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    session["approval_result"] = request.approved
    return {"approved": request.approved}


# ── Agent Endpoints ──────────────────────────────────────────────────────────

@app.post("/agents/plan")
async def plan(request: AgentRequest):
    from omega.agents.planner import PlannerAgent
    agent = PlannerAgent()
    result = await agent.run(request.task, request.context or {})
    return {"success": result.success, "plan": result.output, "error": result.error}


@app.post("/agents/research")
async def research(request: AgentRequest):
    from omega.agents.researcher import ResearchAgent
    agent = ResearchAgent()
    result = await agent.run(request.task, request.context or {})
    return {"success": result.success, "output": result.output, "error": result.error}


@app.post("/agents/code")
async def code(request: AgentRequest):
    from omega.agents.coder import CoderAgent
    agent = CoderAgent()
    result = await agent.run(request.task, request.context or {})
    return {"success": result.success, "output": result.output, "error": result.error}


@app.post("/agents/execute")
async def execute(request: AgentRequest):
    from omega.agents.executor import ExecutorAgent
    agent = ExecutorAgent()
    result = await agent.run(request.task, request.context or {})
    return {"success": result.success, "output": result.output, "error": result.error}


@app.post("/agents/browse")
async def browse(request: AgentRequest):
    from omega.agents.browser import BrowserAgent
    agent = BrowserAgent()
    result = await agent.run(request.task, request.context or {})
    return {"success": result.success, "output": result.output, "error": result.error}


@app.post("/agents/devops")
async def devops(request: AgentRequest):
    from omega.agents.devops import DevOpsAgent
    agent = DevOpsAgent()
    result = await agent.run(request.task, request.context or {})
    return {"success": result.success, "output": result.output, "error": result.error}


# ── Memory Endpoints ─────────────────────────────────────────────────────────

@app.post("/memory/store")
async def store_memory(request: MemoryRequest):
    from omega.memory.store import memory
    id_ = memory.remember(
        content=request.content,
        type_=request.type_,
        key=request.key,
        importance=request.importance,
    )
    return {"id": id_, "stored": True}


@app.post("/memory/recall")
async def recall_memory(request: RecallRequest):
    from omega.memory.store import memory
    results = memory.recall(request.query, n=request.n)
    return {"results": results, "query": request.query}


@app.get("/memory/stats")
async def memory_stats():
    from omega.memory.store import memory
    return memory.stats()


@app.get("/memory/episodes")
async def get_episodes(agent: Optional[str] = None, limit: int = 20):
    from omega.memory.store import memory
    episodes = memory.long_term.get_episodes(agent=agent, limit=limit)
    return {"episodes": episodes}


# ── Workflow Endpoints ────────────────────────────────────────────────────────

@app.get("/workflows")
async def list_workflows():
    from omega.workflows.engine import workflow_engine
    return {"workflows": workflow_engine.list_workflows()}


@app.post("/workflows")
async def create_workflow(request: WorkflowRequest):
    from omega.workflows.engine import workflow_engine
    wf = workflow_engine.create_workflow(
        name=request.name,
        steps=request.steps,
        description=request.description,
        schedule=request.schedule,
    )
    return {"workflow": wf.to_dict()}


@app.post("/workflows/{name}/run")
async def run_workflow(name: str, request: RunWorkflowRequest, background_tasks: BackgroundTasks):
    from omega.workflows.engine import workflow_engine
    session_id = str(uuid.uuid4())
    _sessions[session_id] = {"workflow": name, "status": "running", "events": []}

    async def run():
        async def on_progress(event_type, message):
            _sessions[session_id]["events"].append({"type": event_type, "message": message})

        result = await workflow_engine.run(name, context=request.context, on_progress=on_progress)
        _sessions[session_id].update({"status": "done", "result": result})

    background_tasks.add_task(run)
    return {"session_id": session_id, "status": "started"}


@app.delete("/workflows/{name}")
async def delete_workflow(name: str):
    from omega.workflows.engine import workflow_engine
    deleted = workflow_engine.delete_workflow(name)
    return {"deleted": deleted}


# ── MCP Endpoints ─────────────────────────────────────────────────────────────

@app.get("/mcp/servers")
async def list_mcp_servers():
    from omega.mcp.manager import mcp_manager
    servers = {
        name: {"name": name, "connected": s.connected, "tools": len(s.tools)}
        for name, s in mcp_manager.servers.items()
    }
    return {"servers": servers}


@app.post("/mcp/servers")
async def add_mcp_server(request: MCPServerRequest):
    from omega.mcp.manager import mcp_manager
    connected = await mcp_manager.add_server(
        name=request.name,
        url=request.url,
        command=request.command,
        env=request.env,
    )
    return {"connected": connected, "name": request.name}


@app.get("/mcp/tools")
async def list_mcp_tools():
    from omega.mcp.manager import mcp_manager
    return {"tools": mcp_manager.list_all_tools()}


# ── Model Endpoints ──────────────────────────────────────────────────────────

@app.get("/models")
async def list_models():
    from omega.models.router import router
    try:
        models = await router.list_free_models()
        return {"models": models}
    except Exception as e:
        return {"models": [], "error": str(e)}


@app.get("/models/config")
async def model_config():
    return {"model_routing": config.models, "fallback": config.fallback_model}


# ── WebSocket for real-time events ────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    _websocket_connections.append(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Echo back or handle commands
            await websocket.send_json({"echo": data})
    except WebSocketDisconnect:
        _websocket_connections.remove(websocket)


def start_api():
    """Start the API server"""
    import uvicorn
    uvicorn.run(app, host=config.api_host, port=config.api_port, log_level="warning")
