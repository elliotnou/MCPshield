"""Swagger/OpenAPI ingestion pipeline with Prance + Gemini API fallback.

Usage:
    # Parse OpenAPI spec from URL using Prance
    python swagger_ingest.py --url https://petstore.swagger.io/v2/swagger.json
    
    # Parse OpenAPI spec from local file
    python swagger_ingest.py --file openapi.yaml
    
    # Use Gemini API for messy/non-standard docs
    python swagger_ingest.py --file messy_docs.md --use-gemini
    
    # Specify custom output path
    python swagger_ingest.py --url https://example.com/api.json --output tools.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv

from .logger import get_logger

load_dotenv()


logger = get_logger()


def is_url(source: str) -> bool:
    """Check if source is a URL."""
    try:
        parsed = urlparse(source)
        return parsed.scheme in ("http", "https")
    except Exception:
        return False


def fetch_url(url: str) -> str:
    """Fetch content from a URL."""
    logger.info("Fetching content from: %s", url)
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        resp = client.get(url, headers={"Accept": "application/json, application/yaml, */*"})
        resp.raise_for_status()
    return resp.text


def parse_with_prance(source: str) -> dict[str, Any]:
    """Parse OpenAPI/Swagger spec using Prance ResolvingParser.
    
    Prance handles:
    - $ref resolution (local and remote)
    - Swagger 2.x and OpenAPI 3.x
    - YAML and JSON formats
    - URL and file sources
    """
    from prance import ResolvingParser
    
    logger.info("Parsing with Prance: %s", source)
    
    try:
        # Increase recursion limit for large specs like Stripe
        parser = ResolvingParser(source, strict=False, recursion_limit=100)
        spec = parser.specification
        
        # Extract API info
        info = spec.get("info", {})
        
        # Determine base URL
        base_url = ""
        servers = spec.get("servers", [])
        if servers:
            base_url = servers[0].get("url", "")
        elif "host" in spec:
            scheme = (spec.get("schemes") or ["https"])[0]
            base_url = f"{scheme}://{spec['host']}{spec.get('basePath', '')}"
        
        # Extract tools from paths
        tools = []
        for path, path_item in spec.get("paths", {}).items():
            if not isinstance(path_item, dict):
                continue
                
            for method in ("get", "post", "put", "patch", "delete", "head", "options"):
                operation = path_item.get(method)
                if not operation:
                    continue
                
                # Build tool definition
                operation_id = operation.get("operationId", "")
                if not operation_id:
                    # Generate operation ID from method + path
                    operation_id = f"{method}_{path.replace('/', '_').strip('_')}"
                
                # Collect parameters
                params = []
                
                # Path-level + operation-level params
                all_params = path_item.get("parameters", []) + operation.get("parameters", [])
                for p in all_params:
                    params.append({
                        "name": p.get("name", ""),
                        "type": p.get("schema", {}).get("type", p.get("type", "string")),
                        "required": p.get("required", False),
                        "location": p.get("in", "query"),
                        "description": p.get("description", ""),
                    })
                
                # Request body (OpenAPI 3.x)
                request_body = operation.get("requestBody")
                if request_body:
                    content = request_body.get("content", {})
                    json_schema = content.get("application/json", {}).get("schema", {})
                    if json_schema:
                        required_fields = set(json_schema.get("required", []))
                        for prop_name, prop_schema in json_schema.get("properties", {}).items():
                            params.append({
                                "name": prop_name,
                                "type": prop_schema.get("type", "string"),
                                "required": prop_name in required_fields,
                                "location": "body",
                                "description": prop_schema.get("description", ""),
                            })
                
                tools.append({
                    "name": operation_id,
                    "description": operation.get("summary", "") or operation.get("description", ""),
                    "method": method.upper(),
                    "path": path,
                    "params": params,
                    "tags": operation.get("tags", []),
                    "deprecated": operation.get("deprecated", False),
                })
        
        return {
            "source": source,
            "parser": "prance",
            "api_info": {
                "title": info.get("title", "Untitled API"),
                "version": info.get("version", ""),
                "description": info.get("description", ""),
                "base_url": base_url,
            },
            "tools": tools,
        }
        
    except Exception as e:
        logger.error("Prance parsing failed: %s", e)
        raise


def parse_with_gemini(source: str, content: str | None = None, max_retries: int = 3) -> dict[str, Any]:
    """Use Gemini API to extract tool definitions from messy/non-standard docs.
    
    Best for:
    - Non-standard documentation formats
    - Markdown API docs
    - Poorly formatted specs
    - Documentation without proper OpenAPI structure
    """
    import time
    from google import genai
    
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is required for Gemini parsing")
    
    logger.info("Parsing with Gemini API: %s", source)
    
    # Load content if not provided
    if content is None:
        if is_url(source):
            content = fetch_url(source)
        else:
            content = Path(source).read_text(encoding="utf-8")
    
    # Initialize Gemini client
    client = genai.Client(api_key=api_key)
    
    # Improved prompt for extracting API tool definitions
    prompt = f"""You are an expert API documentation parser. Your task is to extract ALL API endpoints from the documentation below and convert them into structured tool definitions.

## Instructions

1. **Read the entire documentation carefully** to identify every API endpoint
2. **Extract complete information** for each endpoint including all parameters
3. **Use snake_case** for all tool names (e.g., create_user, get_todos_by_id)
4. **Infer parameter types** from context (string, integer, boolean, object, array)
5. **Mark parameters as required** based on documentation clues like "required", "must", or lack of "optional"
6. **Identify parameter locations**: path (in URL like /users/{{id}}), query (?param=value), body (JSON payload), header (HTTP headers)

## Output Format

Return ONLY valid JSON matching this exact structure:

```json
{{
  "api_info": {{
    "title": "API name from docs or 'Unknown API'",
    "version": "Version if mentioned or empty string",
    "description": "Brief description of the API purpose",
    "base_url": "Base URL if mentioned or empty string"
  }},
  "tools": [
    {{
      "name": "snake_case_function_name",
      "description": "Clear description of what this endpoint does",
      "method": "GET|POST|PUT|PATCH|DELETE",
      "path": "/path/with/{{param_placeholders}}",
      "params": [
        {{
          "name": "param_name",
          "type": "string|integer|boolean|object|array",
          "required": true,
          "location": "path|query|body|header",
          "description": "What this parameter is for"
        }}
      ]
    }}
  ]
}}
```

## API Documentation to Parse

{content[:50000]}

## Important

- Return ONLY the JSON object, no markdown code blocks or explanation
- Include ALL endpoints found in the documentation
- If authentication is mentioned, include auth parameters (like API keys as header params)
- Path parameters should use {{param}} syntax in the path field"""

    # Retry with exponential backoff
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
            )
            
            # Parse response
            response_text = response.text.strip()
            
            # Remove markdown code blocks if present (handles ```json and ``` variants)
            if response_text.startswith("```"):
                lines = response_text.split("\n")
                # Find the ending ``` 
                end_idx = len(lines) - 1
                for i in range(len(lines) - 1, 0, -1):
                    if lines[i].strip() == "```":
                        end_idx = i
                        break
                response_text = "\n".join(lines[1:end_idx])
            
            # Try to extract JSON if there's extra text
            if not response_text.startswith("{"):
                # Find first { and last }
                start = response_text.find("{")
                end = response_text.rfind("}") + 1
                if start != -1 and end > start:
                    response_text = response_text[start:end]
            
            result = json.loads(response_text)
            
            # Validate structure
            if "tools" not in result:
                result["tools"] = []
            if "api_info" not in result:
                result["api_info"] = {}
            
            return {
                "source": source,
                "parser": "gemini",
                "api_info": result.get("api_info", {}),
                "tools": result.get("tools", []),
            }
            
        except json.JSONDecodeError as e:
            logger.error("Failed to parse Gemini response as JSON (attempt %d): %s", attempt + 1, e)
            if attempt < max_retries - 1:
                logger.info("Retrying...")
                time.sleep(2 ** attempt)
            else:
                logger.debug("Response was: %s...", response_text[:500])
                raise ValueError(f"Gemini returned invalid JSON after {max_retries} attempts: {e}")
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                if attempt < max_retries - 1:
                    wait_time = 2 ** (attempt + 2)
                    logger.warning("Rate limited, waiting %ds before retry...", wait_time)
                    time.sleep(wait_time)
                else:
                    raise
            else:
                raise
    
    raise ValueError("Failed to parse with Gemini after all retries")


def detect_source_type(source: str) -> str:
    """Detect if source is OpenAPI/Swagger or needs Gemini parsing.
    
    Returns: 'openapi' or 'unknown'
    """
    try:
        if is_url(source):
            content = fetch_url(source)
        else:
            content = Path(source).read_text(encoding="utf-8")
        
        # Check for OpenAPI/Swagger markers
        content_lower = content.lower()
        if '"openapi"' in content_lower or "'openapi'" in content_lower:
            return "openapi"
        if '"swagger"' in content_lower or "'swagger'" in content_lower:
            return "openapi"
        if "openapi:" in content_lower:
            return "openapi"
        if "swagger:" in content_lower:
            return "openapi"
        
        return "unknown"
    except Exception:
        return "unknown"


def ingest(
    source: str,
    use_gemini: bool = False,
    output_path: str | None = None,
) -> dict[str, Any]:
    """Main ingestion function.
    
    Args:
        source: URL or file path to API docs
        use_gemini: Force using Gemini API even for OpenAPI specs
        output_path: Path to write output JSON (default: test_application/raw_tool_definitions.json)
    
    Returns:
        Dict with source, parser, api_info, and tools
    """
    result: dict[str, Any]
    
    if use_gemini:
        # Force Gemini parsing
        result = parse_with_gemini(source)
    else:
        # Auto-detect and try Prance first for OpenAPI specs
        source_type = detect_source_type(source)
        
        if source_type == "openapi":
            try:
                result = parse_with_prance(source)
            except Exception as e:
                logger.warning("Prance failed, falling back to Gemini: %s", e)
                result = parse_with_gemini(source)
        else:
            # Non-standard docs, use Gemini
            logger.info("Source doesn't appear to be OpenAPI, using Gemini")
            result = parse_with_gemini(source)
    
    # Write output if path given
    if output_path:
        logger.info("Writing output to: %s", output_path)
        Path(output_path).write_text(
            json.dumps(result, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
    
    logger.info("Ingestion complete — API: %s, Tools: %d, Parser: %s",
                result['api_info'].get('title', 'Unknown'), len(result['tools']), result['parser'])
    
    return result


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Ingest Swagger/OpenAPI specs or API docs into tool definitions"
    )
    
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument(
        "--url",
        help="URL to fetch API spec from",
    )
    source_group.add_argument(
        "--file",
        help="Local file path to API spec",
    )
    
    parser.add_argument(
        "--use-gemini",
        action="store_true",
        help="Force using Gemini API for parsing (best for non-standard docs)",
    )
    parser.add_argument(
        "--output", "-o",
        help="Output file path (default: test_application/raw_tool_definitions.json)",
    )
    
    args = parser.parse_args()
    
    source = args.url or args.file
    
    try:
        ingest(
            source=source,
            use_gemini=args.use_gemini,
            output_path=args.output,
        )
    except Exception as e:
        print(f"[ERROR] Ingestion failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
