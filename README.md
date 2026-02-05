# Anvil

**Forge safe MCP servers from any API.**

We're racing toward an agentic future where AI models don't just chat — they *act*. They book flights, process refunds, manage infrastructure. But connecting an LLM to a real-world API is terrifyingly unsafe. Most MCP tools today are "dumb pipes" that expose every endpoint to the AI without a second thought. Give an agent your Stripe key and the wrong prompt, and it will happily `DELETE /customers`.

Anvil exists to close that gap. It takes any API specification — OpenAPI, Swagger, Postman, or even a raw docs page — and forges a complete MCP server with **automatic safety classification**, **destructive action guards**, and **human-in-the-loop policies**. The output works immediately with Claude, Cursor, Gemini, or any MCP-compatible client.

---

## Quick Start

```bash
# 1. Clone and install
git clone <this-repo> && cd MCP_Adapter-main
pip install -r requirements.txt

# 2. Configure (only FEATHERLESS_API_KEY is required)
cp .env.example .env
# Edit .env — add your key from https://featherless.ai

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

## What Anvil Does

```
   API Spec (any format)              Production MCP Server
         |                                  ^
         v                                  |
   +-----------+   +--------+   +---------+   +----------+
   |  INGEST   |-->|  MINE  |-->| SAFETY  |-->|  FORGE   |
   |           |   |        |   |         |   |          |
   | Parse any |   | Group  |   | Classify|   | LLM gen  |
   | spec fmt  |   | into   |   | R/W/D   |   | full     |
   |           |   | tools  |   | + badge |   | server   |
   +-----------+   +--------+   +---------+   +----------+
```

**Ingest** — Handles OpenAPI 3.x, Swagger 2.x, Postman v2.1, raw HTML docs (via Gemini). Resolves `$ref`, auto-discovers Swagger UI endpoints, handles messy specs.

**Mine** — Groups raw endpoints into logical "tools" by tag and path. `GET /users` + `POST /users` + `GET /users/{id}` become `list_users`, `create_user`, `get_user`.

**Safety** — Classifies every tool: `READ` (safe), `WRITE` (modifies data), `DESTRUCTIVE` (deletes data). Badges like `[DESTRUCTIVE]` are injected into tool descriptions so AI agents know to pause and confirm.

**Forge** — DeepSeek-V3 writes a complete, runnable async Python server in a single LLM pass. Validated with `ast.parse()`, auto-repaired if syntax errors are found. No templates or scaffolding.

**Deploy** (optional) — Push to GitHub and deploy to the cloud with `--deploy`.

---

## CLI Usage

```bash
# Forge from local file
python -m mcp_adapter generate --spec path/to/openapi.yaml -o ./output/my-api

# Forge from URL
python -m mcp_adapter generate --url https://petstore.swagger.io/v2/swagger.json -o ./output/petstore

# Block all destructive tools
python -m mcp_adapter generate --spec api.yaml -o ./output/safe-api --block-destructive

# Only include specific tools
python -m mcp_adapter generate --spec api.yaml -o ./output/scoped --allowlist get_users,create_user

# Preview tools without generating (dry run)
python -m mcp_adapter inspect --spec api.yaml
python -m mcp_adapter inspect --spec api.yaml --json-output

# Enhance descriptions with K2 reasoning model
python -m mcp_adapter generate --spec api.yaml -o ./output --use-k2

# Auto-deploy to GitHub
python -m mcp_adapter generate --spec api.yaml -o ./output --deploy --github-org myorg
```

### All Flags

| Flag | What it does |
|------|-------------|
| `--spec PATH` | Local spec file (YAML/JSON) |
| `--url URL` | Remote spec URL |
| `-o, --output DIR` | Where to write generated files (required) |
| `--name NAME` | Override server name |
| `--block-destructive` | Drop all DELETE tools |
| `--max-tools N` | Cap the number of tools |
| `--allowlist A,B,C` | Only include these tools |
| `--denylist X,Y,Z` | Exclude these tools |
| `--use-k2` | AI-enhanced descriptions |
| `--deploy` | Push to GitHub after generation |
| `--github-org ORG` | GitHub org for deploy |
| `-v` | Debug logging |

---

## Web Dashboard

Anvil also ships with a web UI that walks you through a 7-step pipeline:

**Ingest** → **Discover** → **Schema** → **Policy** → **Generate** → **Test** → **Deploy**

```bash
# Terminal 1 — API backend
uvicorn api_server:app --port 8080 --reload

# Terminal 2 — Frontend
cd frontend && npm install && npm run dev
# Open http://localhost:3000
```

Create `frontend/.env.local`:
```
NEXT_PUBLIC_API_URL=http://localhost:8080
```

---

## What Gets Generated

Each run produces a self-contained directory you can deploy anywhere:

```
output/my-api-mcp/
├── server.py          # Complete async MCP server with @tool decorators
├── test_server.py     # Contract tests for every tool
├── main.py            # Deployment entry point
├── requirements.txt   # dedalus-mcp, httpx
├── pyproject.toml     # Package metadata
├── .env.example       # Upstream API credentials template
└── dedalus.json       # Deployment manifest
```

Example of a generated tool:

```python
@tool(description="Delete a customer [DESTRUCTIVE]")
async def delete_customer(customer_id: str) -> str:
    """Permanently remove a customer record."""
    return await _request("DELETE", f"/customers/{customer_id}")
```

The `[DESTRUCTIVE]` badge in the description tells Claude, Cursor, and other MCP clients that this action is dangerous — they'll prompt the user for confirmation before executing.

---

## Environment Variables

You need **one** LLM API key — pick whichever provider you prefer:

| Variable | Purpose |
|----------|---------|
| `LLM_API_KEY` | API key for any OpenAI-compatible provider |
| `LLM_BASE_URL` | Provider base URL (default: Featherless) |
| `LLM_MODEL` | Model ID (default: `deepseek-ai/DeepSeek-V3-0324`) |

**Free options:**
- **DeepSeek** — free credits on signup at https://platform.deepseek.com
- **Ollama** — run locally for free: `brew install ollama && ollama pull deepseek-coder-v2`

Legacy `FEATHERLESS_API_KEY` also works as a fallback.

| Variable | Required | Purpose |
|----------|----------|---------|
| `GEMINI_API_KEY` | No | Parse non-standard docs |
| `GITHUB_TOKEN` | No | `--deploy` flag |
| `K2_API_KEY` | No | `--use-k2` flag |
| `DEDALUS_API_KEY` | No | Cloud hosting |

Full details in `.env.example`.

---

## Project Layout

```
├── mcp_adapter/              # Core forge pipeline (Python)
│   ├── cli.py                # Click CLI
│   ├── ingest.py             # Spec parser (OpenAPI/Swagger/Postman)
│   ├── swagger_ingest.py     # Prance + Gemini fallback
│   ├── sdk_ingest.py         # GitHub repo introspection
│   ├── mine.py               # Endpoint → tool grouping
│   ├── discover.py           # Tool classification
│   ├── safety.py             # READ/WRITE/DESTRUCTIVE engine
│   ├── reasoning.py          # K2 AI enhancement
│   ├── agentic_codegen.py    # LLM code generation
│   ├── deploy.py             # GitHub push + cloud deploy
│   ├── models.py             # Pydantic data models
│   └── logger.py             # Coloured pipeline logging
├── api_server.py             # FastAPI backend for web dashboard
├── frontend/                 # Next.js 7-step pipeline UI
├── examples/                 # Sample specs (petstore.yaml)
├── test_application/         # Math API for testing
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

- **Python** — FastAPI, Click, Pydantic, httpx
- **DeepSeek-V3** via Featherless — LLM code generation
- **Google Gemini** — fallback doc parser (2M token context)
- **K2 (MBZUAI)** — optional reasoning enhancement
- **Dedalus MCP** — runtime framework for generated servers
- **Next.js 16** + React 19 + Tailwind CSS — web dashboard

---

## License

MIT
