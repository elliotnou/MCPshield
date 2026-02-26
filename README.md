# Anvil

**Forge safe MCP servers from any API.**

AI agents are moving from chat to action — booking flights, managing infrastructure, processing payments. But connecting an LLM to a live API is dangerous. Most MCP tools today are dumb pipes that expose every endpoint without guardrails. Hand an agent your Stripe key and the wrong prompt, and it'll happily `DELETE /customers`.

Anvil fixes that. Feed it any API specification — OpenAPI, Swagger, Postman, or even a raw docs page — and it produces a complete MCP server with **automatic safety classification**, **destructive action guards**, and **human-in-the-loop policies**. The output works out of the box with Claude, Cursor, Gemini, or any MCP-compatible client.

---

## Quick Start

```bash
# 1. Clone and install
git clone https://github.com/elliotnou/MCPshield.git && cd MCPshield
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Add your Anthropic and Gemini keys (see .env.example)

# 3. Forge a server from any API spec
python -m mcp_adapter generate \
  --spec examples/petstore.yaml \
  -o ./output/petstore-mcp

# 4. Run it
cd output/petstore-mcp
pip install -r requirements.txt
cp .env.example .env   # add your upstream API key
python server.py       # MCP server on http://127.0.0.1:8000/mcp
```

---

## How It Works

```
   API Spec (any format)              Production MCP Server
         │                                  ▲
         ▼                                  │
   ┌───────────┐   ┌────────┐   ┌─────────┐   ┌──────────┐
   │  INGEST   │──▸│  MINE  │──▸│ SAFETY  │──▸│  FORGE   │
   │           │   │        │   │         │   │          │
   │ Parse any │   │ Group  │   │ Classify│   │ Claude   │
   │ spec fmt  │   │ into   │   │ R/W/D   │   │ writes   │
   │           │   │ tools  │   │ + badge │   │ server   │
   └───────────┘   └────────┘   └─────────┘   └──────────┘
```

**Ingest** — Parses OpenAPI 3.x, Swagger 2.x, Postman v2.1, and raw HTML docs (via Gemini). Resolves `$ref` chains, auto-discovers Swagger UI endpoints, and handles messy real-world specs.

**Mine** — Groups raw endpoints into logical tools by tag and path prefix. `GET /users` + `POST /users` + `GET /users/{id}` become `list_users`, `create_user`, `get_user`. Read-heavy groups are merged into a single search tool when the heuristic fires.

**Safety** — Classifies every tool as `READ` (safe), `WRITE` (modifies data), or `DESTRUCTIVE` (deletes data). Badges like `[⚠️ DESTRUCTIVE]` are injected into tool descriptions so AI agents know to pause and confirm. Sensitive parameter names (passwords, tokens, SSNs) are automatically redacted.

**Forge** — Claude Haiku writes a complete, runnable async Python server in a single LLM pass. The output is validated with `ast.parse()` and auto-repaired if syntax errors are found. Falls back to template-based generation with `--no-llm`.

**Deploy** (optional) — Push to GitHub with `--deploy`. The web dashboard also supports one-click deploy with your own GitHub PAT.

---

## CLI

```bash
# Generate from a local file
python -m mcp_adapter generate --spec path/to/openapi.yaml -o ./output/my-api

# Generate from a URL
python -m mcp_adapter generate --url https://petstore.swagger.io/v2/swagger.json -o ./output/petstore

# Block all destructive tools
python -m mcp_adapter generate --spec api.yaml -o ./output/safe-api --block-destructive

# Only include specific tools
python -m mcp_adapter generate --spec api.yaml -o ./output/scoped --allowlist get_users,create_user

# Template-based generation (no LLM key needed)
python -m mcp_adapter generate --spec api.yaml -o ./output/my-api --no-llm

# Preview tools without generating (dry run)
python -m mcp_adapter inspect --spec api.yaml
python -m mcp_adapter inspect --spec api.yaml --json-output

# Auto-deploy to GitHub
python -m mcp_adapter generate --spec api.yaml -o ./output --deploy --github-org myorg
```

### Flags

| Flag | Description |
|------|-------------|
| `--spec PATH` | Local spec file (YAML/JSON) |
| `--url URL` | Remote spec URL |
| `-o, --output DIR` | Output directory (required) |
| `--name NAME` | Override server name |
| `--block-destructive` | Drop all destructive (DELETE) tools |
| `--max-tools N` | Cap the number of tools (0 = unlimited) |
| `--allowlist A,B,C` | Only include these tools |
| `--denylist X,Y,Z` | Exclude these tools |
| `--no-llm` | Template-based codegen (no API key needed) |
| `--deploy` | Push to GitHub after generation |
| `--github-org ORG` | GitHub org for deploy |
| `-v, --verbose` | Debug logging |

---

## Web Dashboard

Anvil ships with a full web UI that walks you through a 7-step pipeline:

**Ingest → Discover → Schema → Policy → Generate → Test → Deploy**

```bash
# Terminal 1 — API backend
uvicorn api_server:app --port 8080 --reload

# Terminal 2 — Next.js frontend
cd frontend && npm install && npm run dev
# Open http://localhost:3000
```

Create `frontend/.env.local`:
```
NEXT_PUBLIC_API_URL=http://localhost:8080
```

The dashboard supports all ingestion modes (OpenAPI upload, Swagger URL, SDK repo, raw docs paste), interactive tool selection in the Discover step, per-tool policy configuration, and one-click GitHub deploy with your own PAT.

---

## Generated Output

Each run produces a self-contained directory:

```
output/my-api-mcp/
├── server.py          # Async MCP server with @tool decorators
├── test_server.py     # Contract tests for every tool
├── main.py            # Deployment entry point
├── requirements.txt   # dedalus-mcp, httpx
├── pyproject.toml     # Package metadata
├── .env.example       # Upstream API credentials template
└── dedalus.json       # Deployment manifest
```

Example generated tool:

```python
@tool(description="Delete a customer [⚠️ DESTRUCTIVE — may permanently delete data]")
async def delete_customer(customer_id: str) -> str:
    """Permanently remove a customer record."""
    return await _request("DELETE", f"/customers/{customer_id}")
```

The `[DESTRUCTIVE]` badge tells Claude, Cursor, and other MCP clients to prompt the user for confirmation before executing.

---

## Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `ANTHROPIC_API_KEY` | **Yes** | Claude Haiku — code generation and agentic reasoning |
| `GEMINI_API_KEY` | **Yes** | Google Gemini — parsing non-standard docs and SDK sources |

GitHub deploy uses a personal access token entered at deploy time (not stored in `.env`).

See `.env.example` for setup instructions.

---

## Project Layout

```
├── mcp_adapter/              # Core forge pipeline
│   ├── cli.py                # Click CLI (generate, inspect)
│   ├── ingest.py             # Spec parser (OpenAPI / Swagger / Postman)
│   ├── swagger_ingest.py     # Prance-based parser + Gemini fallback
│   ├── sdk_ingest.py         # GitHub repo / SDK introspection via Gemini
│   ├── mine.py               # Endpoint → tool grouping
│   ├── discover.py           # Gemini + rule-based tool classification
│   ├── safety.py             # READ / WRITE / DESTRUCTIVE engine
│   ├── reasoning.py          # Optional AI-enhanced descriptions
│   ├── agentic_codegen.py    # Claude-powered code generation
│   ├── codegen.py            # Template-based code generation (no LLM)
│   ├── deploy.py             # GitHub repo creation + push
│   ├── models.py             # Pydantic domain models
│   └── logger.py             # Coloured, stage-aware logging
├── api_server.py             # FastAPI backend for the web dashboard
├── frontend/                 # Next.js 16 + React 19 + Tailwind CSS
├── examples/                 # Sample specs (petstore.yaml)
├── test_application/         # Math API for integration testing
├── test_all.py               # Integration test suite
├── requirements.txt
├── Dockerfile
└── .env.example
```

---

## Docker

```bash
docker build -t anvil .
docker run -p 8080:8080 --env-file .env anvil
```

---

## Tech Stack

- **Claude Haiku** (Anthropic) — LLM code generation
- **Google Gemini 2.5 Flash** — doc parsing, SDK introspection, tool classification
- **Python 3.11+** — FastAPI, Click, Pydantic, httpx
- **Dedalus MCP** — runtime framework for generated servers
- **Next.js 16** + React 19 + Tailwind CSS v4 — web dashboard

---

## License

MIT
