"""Anvil API — FastAPI backend that wraps the forge pipeline for the frontend.

Run:  uvicorn api_server:app --port 8080 --reload --reload-exclude output
"""

from __future__ import annotations

import fcntl
import json
import os
import pickle
import tempfile
import uuid
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from mcp_adapter.ingest import ingest
from mcp_adapter.mine import mine_tools
from mcp_adapter.models import (
    APISpec, AuthScheme, Endpoint, HttpMethod, ParamLocation,
    ParamSchema, SafetyLevel, ToolDefinition, ToolParam,
)
from mcp_adapter.safety import SafetyPolicy, apply_safety
from mcp_adapter.agentic_codegen import generate as agentic_generate
from mcp_adapter.deploy import deploy as deploy_to_github
from mcp_adapter.swagger_ingest import ingest as swagger_ingest
from mcp_adapter.sdk_ingest import ingest as sdk_ingest
from mcp_adapter.discover import classify_tools, apply_rules
from mcp_adapter.logger import setup_logging

setup_logging(verbose=False)

app = FastAPI(title="Anvil API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── File-backed session store (survives uvicorn reloads) ──────────────────

_SESSION_DIR = Path(__file__).parent / ".sessions"
_SESSION_DIR.mkdir(exist_ok=True)
OUTPUT_ROOT = Path(__file__).parent / "output"

# ── Credit store (JSON file per user) ─────────────────────────────────────

_CREDITS_DIR = Path(__file__).parent / ".credits"
_CREDITS_DIR.mkdir(exist_ok=True)
CREDIT_COST_PER_TOOL = 1  # credits charged per tool generated
CREDIT_PACK_SIZE = 100    # credits per purchase
CREDIT_PACK_PRICE = 1000  # $10.00 in cents


def _get_credits(user: str) -> dict:
    """Load credit balance for a user."""
    p = _CREDITS_DIR / f"{user}.json"
    if p.exists():
        return json.loads(p.read_text())
    return {"user": user, "balance": 0, "total_purchased": 0, "total_spent": 0, "transactions": []}


def _save_credits(user: str, data: dict) -> None:
    """Persist credit data for a user."""
    (_CREDITS_DIR / f"{user}.json").write_text(json.dumps(data, indent=2))


def _save_session(session_id: str, data: dict[str, Any]) -> None:
    """Persist session to disk with file locking."""
    p = _SESSION_DIR / f"{session_id}.pkl"
    with open(p, "wb") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.write(pickle.dumps(data))
        fcntl.flock(f, fcntl.LOCK_UN)


def _load_session(session_id: str) -> dict[str, Any] | None:
    """Load session from disk with file locking."""
    p = _SESSION_DIR / f"{session_id}.pkl"
    if not p.exists():
        return None
    with open(p, "rb") as f:
        fcntl.flock(f, fcntl.LOCK_SH)
        data = pickle.loads(f.read())
        fcntl.flock(f, fcntl.LOCK_UN)
    return data


# ── Request / response models ─────────────────────────────────────────────

class IngestRequest(BaseModel):
    source: str  # URL or file path
    source_type: str = "openapi"  # openapi, docs, sdk, postman

class PolicyUpdate(BaseModel):
    session_id: str
    policies: list[dict[str, Any]]  # [{name, safety, auto_execute, rate_limit_qpm}]

class GenerateRequest(BaseModel):
    session_id: str
    server_name: str | None = None

class DeployRequest(BaseModel):
    session_id: str
    github_org: str | None = None
    github_token: str | None = None

class DiscoverRequest(BaseModel):
    session_id: str
    policy: str = "moderate"  # conservative, moderate, permissive
    use_gemini: bool = False

class DiscoverConfirmRequest(BaseModel):
    session_id: str
    allowed_tools: list[str]  # tool names to carry forward

class CreditPurchaseRequest(BaseModel):
    user: str
    credits: int = 100  # default pack size
    payment_id: str | None = None  # Flowglad payment/checkout ID


# ── Raw tool → canonical model converters ─────────────────────────────────

def _raw_tools_to_canonical(raw_tools: list[dict], api_info: dict) -> tuple[APISpec, list[ToolDefinition]]:
    """Convert raw tool dicts (from swagger_ingest/sdk_ingest) into canonical APISpec + ToolDefinition."""
    endpoints: list[Endpoint] = []
    tools: list[ToolDefinition] = []

    for rt in raw_tools:
        method_str = rt.get("method", "GET").upper()
        if method_str == "FUNCTION":
            method_str = "POST"
        try:
            method = HttpMethod(method_str)
        except ValueError:
            method = HttpMethod.GET

        path = rt.get("path", "/")

        # Build params
        params: list[ParamSchema] = []
        tool_params: list[ToolParam] = []
        for p in rt.get("params", []):
            loc_str = p.get("location", "query")
            try:
                loc = ParamLocation(loc_str)
            except ValueError:
                loc = ParamLocation.QUERY if loc_str != "body" else ParamLocation.BODY
            params.append(ParamSchema(
                name=p.get("name", ""),
                location=loc,
                description=p.get("description", ""),
                required=p.get("required", False),
                schema_type=p.get("type", p.get("schema_type", "string")),
            ))
            tool_params.append(ToolParam(
                name=p.get("name", ""),
                description=p.get("description", ""),
                json_type=p.get("type", p.get("json_type", "string")),
                required=p.get("required", False),
            ))

        ep = Endpoint(
            method=method,
            path=path,
            operation_id=rt.get("name", ""),
            summary=rt.get("description", ""),
            description=rt.get("description", ""),
            tags=rt.get("tags", []),
            parameters=params,
            deprecated=rt.get("deprecated", False),
        )
        endpoints.append(ep)

        tools.append(ToolDefinition(
            name=rt.get("name", ""),
            description=rt.get("description", ""),
            endpoints=[ep],
            params=tool_params,
            tags=rt.get("tags", []),
        ))

    spec = APISpec(
        title=api_info.get("title", "Untitled API"),
        version=api_info.get("version", ""),
        description=api_info.get("description", ""),
        base_url=api_info.get("base_url", ""),
        endpoints=endpoints,
        tags=sorted({t for ep in endpoints for tag in ep.tags for t in ([tag] if tag else [])}),
    )
    return spec, tools


def _serialize_tools(tools: list[ToolDefinition]) -> list[dict]:
    """Serialize canonical ToolDefinitions for JSON response."""
    return [
        {
            "name": t.name,
            "description": t.description,
            "safety": t.safety.value,
            "params": [
                {"name": p.name, "description": p.description, "json_type": p.json_type, "required": p.required}
                for p in t.params
            ],
            "endpoints": [{"method": e.method.value, "path": e.path} for e in t.endpoints],
            "tags": t.tags,
        }
        for t in tools
    ]


def _serialize_endpoints(endpoints: list[Endpoint]) -> list[dict]:
    """Serialize canonical Endpoints for JSON response."""
    return [
        {
            "method": ep.method.value,
            "path": ep.path,
            "operation_id": ep.operation_id,
            "summary": ep.summary,
            "description": ep.description,
            "tags": ep.tags,
            "params": [
                {"name": p.name, "location": p.location.value, "description": p.description,
                 "required": p.required, "schema_type": p.schema_type}
                for p in ep.parameters
            ],
            "deprecated": ep.deprecated,
        }
        for ep in endpoints
    ]


# ── Endpoints ─────────────────────────────────────────────────────────────

@app.post("/api/ingest")
async def api_ingest(req: IngestRequest):
    """Stage 1: Ingest an API spec and return parsed endpoints.

    Supports source_type: openapi, swagger, sdk, docs
    """
    session_id = str(uuid.uuid4())[:8]
    raw_tools: list[dict] = []

    try:
        if req.source_type in ("openapi", "postman"):
            # ── Existing pipeline: ingest → mine → safety ──
            api_spec = ingest(req.source)
            tools = mine_tools(api_spec)
            tools = apply_safety(tools)
            # Build raw_tools for discover step
            raw_tools = [
                {
                    "name": t.name,
                    "description": t.description,
                    "method": t.endpoints[0].method.value if t.endpoints else "GET",
                    "path": t.endpoints[0].path if t.endpoints else "/",
                    "params": [{"name": p.name, "type": p.json_type, "required": p.required,
                                "location": "body", "description": p.description} for p in t.params],
                    "tags": t.tags,
                }
                for t in tools
            ]

        elif req.source_type == "swagger":
            # ── Prance-based parsing (better $ref resolution) ──
            result = swagger_ingest(source=req.source, use_gemini=False)
            raw_tools = result.get("tools", [])
            api_spec, tools = _raw_tools_to_canonical(raw_tools, result.get("api_info", {}))
            tools = apply_safety(tools)

        elif req.source_type == "sdk":
            # ── SDK ingestion (GitHub repo or local) ──
            if req.source.startswith("http") and "github.com" in req.source:
                result = sdk_ingest(source=req.source, source_type="github")
            else:
                result = sdk_ingest(source=req.source, source_type="file")
            raw_tools = result.get("tools", [])
            api_spec, tools = _raw_tools_to_canonical(raw_tools, result.get("api_info", {}))
            tools = apply_safety(tools)

        elif req.source_type == "docs":
            # ── Gemini-based parsing for non-standard docs ──
            result = swagger_ingest(source=req.source, use_gemini=True)
            raw_tools = result.get("tools", [])
            api_spec, tools = _raw_tools_to_canonical(raw_tools, result.get("api_info", {}))
            tools = apply_safety(tools)

        else:
            raise ValueError(f"Unknown source_type: {req.source_type}")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Ingestion failed for source '{req.source}' (type={req.source_type}): {e}"
        )

    # Run rule-based classification automatically
    classifications = classify_tools(raw_tools, policy="moderate", use_gemini=False)

    _save_session(session_id, {
        "spec": api_spec,
        "tools": tools,
        "raw_tools": raw_tools,
        "classifications": classifications,
        "generated": None,
        "output_dir": None,
    })

    return {
        "session_id": session_id,
        "source_type": req.source_type,
        "spec": {
            "title": api_spec.title,
            "version": api_spec.version,
            "description": api_spec.description,
            "base_url": api_spec.base_url,
            "tags": api_spec.tags,
            "auth_schemes": [s.model_dump() for s in api_spec.auth_schemes],
        },
        "endpoints": _serialize_endpoints(api_spec.endpoints),
        "tools": _serialize_tools(tools),
        "classifications": classifications,
    }


@app.get("/api/session/{session_id}")
async def api_session(session_id: str):
    """Get current session state."""
    sess = _load_session(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    api_spec = sess["spec"]
    tools = sess["tools"]

    return {
        "session_id": session_id,
        "spec": {
            "title": api_spec.title,
            "version": api_spec.version,
            "description": api_spec.description,
            "base_url": api_spec.base_url,
            "tags": api_spec.tags,
        },
        "endpoints": _serialize_endpoints(api_spec.endpoints),
        "tools": _serialize_tools(tools),
        "classifications": sess.get("classifications", {}),
        "has_generated": sess["generated"] is not None,
    }


@app.post("/api/discover")
async def api_discover(req: DiscoverRequest):
    """Stage 2: Classify tools for MCP exposure."""
    sess = _load_session(req.session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    raw_tools = sess.get("raw_tools", [])
    if not raw_tools:
        raise HTTPException(status_code=400, detail="No raw tools to classify. Run ingest first.")

    try:
        classifications = classify_tools(
            raw_tools,
            policy=req.policy,
            use_gemini=req.use_gemini,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Classification failed: {e}")

    sess["classifications"] = classifications
    _save_session(req.session_id, sess)

    return classifications


@app.post("/api/ingest/upload")
async def api_ingest_upload(
    file: UploadFile = File(...),
    source_type: str = Form("openapi"),
):
    """Ingest from an uploaded YAML/JSON file."""
    content = await file.read()
    text = content.decode("utf-8")

    suffix = ".yaml" if (file.filename or "").endswith((".yaml", ".yml")) else ".json"
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False, encoding="utf-8")
    try:
        tmp.write(text)
        tmp.close()

        session_id = str(uuid.uuid4())[:8]
        raw_tools: list[dict] = []

        if source_type in ("openapi", "postman"):
            api_spec = ingest(tmp.name)
            tools = mine_tools(api_spec)
            tools = apply_safety(tools)
            raw_tools = [
                {
                    "name": t.name, "description": t.description,
                    "method": t.endpoints[0].method.value if t.endpoints else "GET",
                    "path": t.endpoints[0].path if t.endpoints else "/",
                    "params": [{"name": p.name, "type": p.json_type, "required": p.required,
                                "location": "body", "description": p.description} for p in t.params],
                    "tags": t.tags,
                }
                for t in tools
            ]
        elif source_type == "swagger":
            result = swagger_ingest(source=tmp.name, use_gemini=False)
            raw_tools = result.get("tools", [])
            api_spec, tools = _raw_tools_to_canonical(raw_tools, result.get("api_info", {}))
            tools = apply_safety(tools)
        elif source_type == "docs":
            result = swagger_ingest(source=tmp.name, use_gemini=True)
            raw_tools = result.get("tools", [])
            api_spec, tools = _raw_tools_to_canonical(raw_tools, result.get("api_info", {}))
            tools = apply_safety(tools)
        else:
            raise ValueError(f"Unknown source_type: {source_type}")

        classifications = classify_tools(raw_tools, policy="moderate", use_gemini=False)

        _save_session(session_id, {
            "spec": api_spec, "tools": tools, "raw_tools": raw_tools,
            "classifications": classifications, "generated": None, "output_dir": None,
        })

        return {
            "session_id": session_id,
            "source_type": source_type,
            "spec": {
                "title": api_spec.title, "version": api_spec.version,
                "description": api_spec.description, "base_url": api_spec.base_url,
                "tags": api_spec.tags,
                "auth_schemes": [s.model_dump() for s in api_spec.auth_schemes],
            },
            "endpoints": _serialize_endpoints(api_spec.endpoints),
            "tools": _serialize_tools(tools),
            "classifications": classifications,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Ingestion failed: {e}")
    finally:
        os.unlink(tmp.name)


@app.post("/api/discover/confirm")
async def api_discover_confirm(req: DiscoverConfirmRequest):
    """Confirm discovery: filter session tools to only the allowed ones."""
    sess = _load_session(req.session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    allowed_set = set(req.allowed_tools)
    sess["tools"] = [t for t in sess["tools"] if t.name in allowed_set]
    sess["raw_tools"] = [rt for rt in sess.get("raw_tools", []) if rt.get("name") in allowed_set]

    # Also filter spec endpoints
    spec = sess["spec"]
    spec.endpoints = [ep for ep in spec.endpoints if ep.operation_id in allowed_set]
    sess["spec"] = spec

    _save_session(req.session_id, sess)
    return {"status": "ok", "allowed_count": len(sess["tools"])}


@app.post("/api/policy")
async def api_policy(req: PolicyUpdate):
    """Stage 4: Update tool policies (safety level, auto_execute, rate_limit)."""
    sess = _load_session(req.session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    tools = sess["tools"]
    policy_map = {p["name"]: p for p in req.policies}

    for tool in tools:
        if tool.name in policy_map:
            p = policy_map[tool.name]
            if "safety" in p:
                tool.safety = SafetyLevel(p["safety"])

    sess["tools"] = tools
    _save_session(req.session_id, sess)
    return {"status": "ok", "tool_count": len(tools)}


@app.post("/api/generate")
async def api_generate(req: GenerateRequest):
    """Stage 5: Generate the MCP server code (costs credits)."""
    sess = _load_session(req.session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    api_spec = sess["spec"]
    tools = sess["tools"]
    name = req.server_name or None

    # Credit check: 1 credit per tool
    user = sess.get("user", os.getenv("DEFAULT_USER", "default"))
    cost = len(tools) * CREDIT_COST_PER_TOOL
    cred = _get_credits(user)
    if cred["balance"] < cost:
        raise HTTPException(
            status_code=402,
            detail=f"Insufficient credits. Need {cost} credits ({len(tools)} tools × {CREDIT_COST_PER_TOOL}), have {cred['balance']}. Purchase more credits."
        )

    output_dir = OUTPUT_ROOT / (name or api_spec.title.lower().replace(" ", "-") + "-mcp")

    try:
        result = agentic_generate(api_spec, tools, server_name=name, output_dir=str(output_dir))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Code generation failed: {e}")

    # Deduct credits after successful generation
    cred = _get_credits(user)  # re-read in case of concurrent changes
    cred["balance"] -= cost
    cred["total_spent"] += cost
    cred["transactions"].append({
        "type": "deduct",
        "amount": cost,
        "reason": f"Generated {len(tools)} tools for {api_spec.title}",
        "session_id": req.session_id,
    })
    _save_credits(user, cred)

    sess["generated"] = result
    sess["output_dir"] = str(output_dir)
    _save_session(req.session_id, sess)

    # Read all generated files
    files: dict[str, dict] = {}
    if output_dir.exists():
        for f in sorted(output_dir.iterdir()):
            if f.is_file():
                try:
                    content = f.read_text(encoding="utf-8")
                    files[f.name] = {
                        "content": content,
                        "lines": len(content.splitlines()),
                        "lang": _detect_lang(f.name),
                    }
                except Exception:
                    files[f.name] = {"content": "(binary file)", "lines": 0, "lang": ""}

    return {
        "server_name": result.server_name,
        "tool_count": result.tool_count,
        "output_dir": str(output_dir),
        "files": files,
    }


@app.post("/api/test")
async def api_test(req: GenerateRequest):
    """Stage 6: Run the generated test suite."""
    sess = _load_session(req.session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    output_dir = sess.get("output_dir")
    if not output_dir:
        raise HTTPException(status_code=400, detail="No generated code to test")

    test_file = Path(output_dir) / "test_server.py"
    if not test_file.exists():
        raise HTTPException(status_code=400, detail="No test file found")

    # Return the test file content — actual test execution would need
    # the upstream API running. For now we return the test structure.
    test_code = test_file.read_text(encoding="utf-8")
    test_names = [
        line.strip().replace("async def ", "").replace("def ", "").split("(")[0]
        for line in test_code.splitlines()
        if line.strip().startswith(("async def test_", "def test_"))
    ]

    return {
        "test_file": test_code,
        "test_names": test_names,
        "test_count": len(test_names),
    }


@app.post("/api/deploy")
async def api_deploy(req: DeployRequest):
    """Stage 7: Deploy to GitHub."""
    sess = _load_session(req.session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    output_dir = sess.get("output_dir")
    generated = sess.get("generated")
    if not output_dir or not generated:
        raise HTTPException(status_code=400, detail="No generated code to deploy")

    api_spec = sess["spec"]

    try:
        deploy_info = deploy_to_github(
            output_dir=output_dir,
            repo_name=generated.server_name,
            description=f"Auto-generated MCP server for {api_spec.title}",
            org=req.github_org,
            open_dashboard=False,
            github_token=req.github_token,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Deploy failed: {e}")

    return deploy_info


# ── Credit endpoints ──────────────────────────────────────────────────────

@app.get("/api/credits/pricing")
async def api_credits_pricing():
    """Return pricing info for the credit system."""
    return {
        "pack_size": CREDIT_PACK_SIZE,
        "pack_price_cents": CREDIT_PACK_PRICE,
        "pack_price_display": f"${CREDIT_PACK_PRICE / 100:.2f}",
        "cost_per_tool": CREDIT_COST_PER_TOOL,
    }


@app.get("/api/credits/{user}")
async def api_get_credits(user: str):
    """Get credit balance for a user."""
    cred = _get_credits(user)
    return {
        "user": cred["user"],
        "balance": cred["balance"],
        "total_purchased": cred["total_purchased"],
        "total_spent": cred["total_spent"],
        "cost_per_tool": CREDIT_COST_PER_TOOL,
    }


@app.post("/api/credits/purchase")
async def api_purchase_credits(req: CreditPurchaseRequest):
    """Add credits after a successful payment (Flowglad checkout or test purchase)."""
    cred = _get_credits(req.user)
    cred["balance"] += req.credits
    cred["total_purchased"] += req.credits
    cred["transactions"].append({
        "type": "purchase",
        "amount": req.credits,
        "payment_id": req.payment_id,
        "reason": f"Purchased {req.credits} credits",
    })
    _save_credits(req.user, cred)
    return {
        "user": req.user,
        "credits_added": req.credits,
        "balance": cred["balance"],
    }


def _detect_lang(filename: str) -> str:
    ext_map = {
        ".py": "python",
        ".json": "json",
        ".toml": "toml",
        ".txt": "text",
        ".env": "env",
        ".md": "markdown",
        ".yaml": "yaml",
        ".yml": "yaml",
    }
    for ext, lang in ext_map.items():
        if filename.endswith(ext):
            return lang
    if filename.startswith(".env"):
        return "env"
    return ""
