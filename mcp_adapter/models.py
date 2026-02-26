"""Core domain models for the Anvil pipeline.

All ingestion sources (OpenAPI specs, Postman collections, SDK code, etc.)
get normalized into these models. Downstream stages like mining, safety
classification, and code generation all operate on these shared types.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ── HTTP verbs and param locations ──────────────────────────────────────────

class HttpMethod(str, Enum):
    """Standard HTTP methods supported by the pipeline."""
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"


class ParamLocation(str, Enum):
    """Where a parameter lives in an HTTP request."""
    QUERY = "query"
    PATH = "path"
    HEADER = "header"
    COOKIE = "cookie"
    BODY = "body"
    FORM_DATA = "formData"


class SafetyLevel(str, Enum):
    """Risk tier assigned to each tool during safety classification."""
    READ = "read"
    WRITE = "write"
    DESTRUCTIVE = "destructive"


# ── Request / response schemas ──────────────────────────────────────────────

class ParamSchema(BaseModel):
    """Describes a single API parameter (query, path, header, or body field)."""
    name: str
    location: ParamLocation
    description: str = ""
    required: bool = False
    schema_type: str = "string"
    enum: list[str] | None = None
    default: Any | None = None
    example: Any | None = None


class ResponseSchema(BaseModel):
    """Lightweight representation of an API response."""
    status_code: int
    description: str = ""
    content_type: str = "application/json"
    schema_fields: dict[str, Any] = Field(default_factory=dict)


# ── Endpoint ────────────────────────────────────────────────────────────────

class Endpoint(BaseModel):
    """A single API endpoint parsed from a specification file."""
    method: HttpMethod
    path: str
    operation_id: str = ""
    summary: str = ""
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    parameters: list[ParamSchema] = Field(default_factory=list)
    request_body_schema: dict[str, Any] = Field(default_factory=dict)
    responses: list[ResponseSchema] = Field(default_factory=list)
    auth_schemes: list[str] = Field(default_factory=list)
    deprecated: bool = False


# ── MCP tool definitions ───────────────────────────────────────────────────

class ToolParam(BaseModel):
    """A parameter exposed by a generated MCP tool function."""
    name: str
    description: str = ""
    json_type: str = "string"
    required: bool = False
    enum: list[str] | None = None
    default: Any | None = None


class ToolDefinition(BaseModel):
    """An MCP tool — may wrap one or more upstream API endpoints."""
    name: str
    description: str
    safety: SafetyLevel = SafetyLevel.READ
    params: list[ToolParam] = Field(default_factory=list)
    endpoints: list[Endpoint] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


# ── Top-level API metadata ─────────────────────────────────────────────────

class AuthScheme(BaseModel):
    """Auth scheme declared by the upstream spec (apiKey, http, oauth2, …)."""
    name: str
    scheme_type: str          # apiKey | http | oauth2 | openIdConnect
    location: str = ""        # header | query | cookie (for apiKey)
    header_name: str = ""
    flows: dict[str, Any] = Field(default_factory=dict)


class APISpec(BaseModel):
    """Fully-parsed, source-agnostic API representation.

    Central data structure consumed by every downstream pipeline stage.
    """
    title: str
    version: str = ""
    description: str = ""
    base_url: str = ""
    auth_schemes: list[AuthScheme] = Field(default_factory=list)
    endpoints: list[Endpoint] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    raw_meta: dict[str, Any] = Field(default_factory=dict)
