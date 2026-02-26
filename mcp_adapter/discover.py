"""Automated tool discovery with intelligent classification.

Combines Gemini-based analysis with rule-based heuristics to decide which
API endpoints should be exposed as MCP tools. Supports an interactive
confirmation step where the user can accept/reject suggestions.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv

from .logger import get_logger

load_dotenv()

logger = get_logger()


# ── Classification Rules ──────────────────────────────────────────────────────

PolicyType = Literal["conservative", "moderate", "permissive"]

CLASSIFICATION_RULES = {
    # Methods that are always safe (read-only)
    "safe_methods": ["GET", "HEAD", "OPTIONS"],
    
    # Methods that are always unsafe (destructive)
    "unsafe_methods": ["DELETE"],
    
    # Keywords that indicate safe operations
    "safe_keywords": [
        "list", "get", "read", "fetch", "describe", "show", "view",
        "search", "find", "query", "lookup", "check", "validate"
    ],
    
    # Keywords that indicate unsafe operations
    "unsafe_keywords": [
        "delete", "destroy", "remove", "terminate", "purge", "drop",
        "revoke", "cancel", "disable", "deactivate", "kill"
    ],
    
    # Keywords that indicate billing/payment (block)
    "billing_keywords": [
        "billing", "payment", "invoice", "charge", "subscription",
        "credit", "cost", "price", "purchase", "order"
    ],
    
    # Keywords that indicate auth operations (block)
    "auth_keywords": [
        "token", "secret", "password", "credential", "key", "auth",
        "login", "logout", "session"
    ],
}


def apply_rules(tool: dict, policy: PolicyType) -> dict:
    """Apply rule-based classification to a tool."""
    name = tool.get("name", "").lower()
    method = tool.get("method", "").upper()
    description = tool.get("description", "").lower()
    path = tool.get("path", "").lower()
    
    combined_text = f"{name} {description} {path}"
    
    # Check for unsafe keywords first
    for kw in CLASSIFICATION_RULES["unsafe_keywords"]:
        if kw in combined_text:
            return {
                "classification": "unsafe",
                "expose": False,
                "reason": f"Contains destructive keyword: '{kw}'",
                "confidence": 0.9
            }
    
    # Check for billing/payment
    for kw in CLASSIFICATION_RULES["billing_keywords"]:
        if kw in combined_text:
            return {
                "classification": "unsafe",
                "expose": False,
                "reason": f"Billing/payment operation: '{kw}'",
                "confidence": 0.85
            }
    
    # Check for auth operations
    for kw in CLASSIFICATION_RULES["auth_keywords"]:
        if kw in name or kw in path:  # Stricter check for auth
            return {
                "classification": "unsafe",
                "expose": False,
                "reason": f"Authentication/security operation: '{kw}'",
                "confidence": 0.8
            }
    
    # Check HTTP method
    if method in CLASSIFICATION_RULES["safe_methods"]:
        # Safe methods with safe keywords = definitely safe
        for kw in CLASSIFICATION_RULES["safe_keywords"]:
            if kw in combined_text:
                return {
                    "classification": "safe",
                    "expose": True,
                    "reason": f"Read-only {method} operation with safe keyword: '{kw}'",
                    "confidence": 0.95
                }
        # Safe method without clear indicators
        return {
            "classification": "safe",
            "expose": True,
            "reason": f"Read-only {method} operation",
            "confidence": 0.8
        }
    
    if method in CLASSIFICATION_RULES["unsafe_methods"]:
        return {
            "classification": "unsafe",
            "expose": False,
            "reason": f"Destructive {method} operation",
            "confidence": 0.95
        }
    
    # POST/PUT/PATCH - depends on policy
    if method in ["POST", "PUT", "PATCH"]:
        if policy == "conservative":
            return {
                "classification": "conditional",
                "expose": False,
                "reason": f"Write operation ({method}) blocked by conservative policy",
                "confidence": 0.7
            }
        elif policy == "moderate":
            # Check for safe keywords
            for kw in CLASSIFICATION_RULES["safe_keywords"]:
                if kw in combined_text:
                    return {
                        "classification": "conditional",
                        "expose": True,
                        "reason": f"Write operation with safe context: '{kw}'",
                        "confidence": 0.6
                    }
            # Create/Update operations are generally OK
            if "create" in combined_text or "update" in combined_text:
                return {
                    "classification": "conditional",
                    "expose": True,
                    "reason": "Standard create/update operation",
                    "confidence": 0.65
                }
            return {
                "classification": "conditional",
                "expose": "review",
                "reason": f"Write operation ({method}) needs manual review",
                "confidence": 0.5
            }
        else:  # permissive
            return {
                "classification": "conditional",
                "expose": True,
                "reason": f"Write operation ({method}) allowed by permissive policy",
                "confidence": 0.6
            }
    
    # Unknown - needs review
    return {
        "classification": "unknown",
        "expose": "review",
        "reason": "Unable to classify automatically",
        "confidence": 0.3
    }


# ── Gemini Classification ─────────────────────────────────────────────────────


def classify_batch_with_gemini(
    tools: list[dict],
    policy: PolicyType,
    batch_size: int = 20
) -> list[dict]:
    """Classify tools in batches using Gemini 2.5 Flash."""
    from google import genai
    
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY required for Gemini classification")
    
    client = genai.Client(api_key=api_key)
    results = []
    
    for i in range(0, len(tools), batch_size):
        batch = tools[i:i + batch_size]
        logger.info("Classifying batch %d/%d", i//batch_size + 1, (len(tools)-1)//batch_size + 1)
        
        # Create prompt for batch classification
        tools_json = json.dumps(batch, indent=2)
        prompt = f"""You are an API security classifier. Analyze these API tools and classify each one.

## Policy: {policy.upper()}
- conservative: Only expose read-only (GET) operations
- moderate: Expose reads + safe writes (create/update), block deletes and sensitive ops
- permissive: Expose everything except destructive and security-sensitive operations

## Classification Rules
- "safe": Read-only, no side effects, can always expose
- "unsafe": Destructive, billing, auth - never expose
- "conditional": Write operations - depends on policy

## Tools to Classify
{tools_json}

## Output Format
Return ONLY a JSON array with one object per tool:
```json
[
  {{
    "name": "tool_name",
    "classification": "safe|unsafe|conditional",
    "expose": true|false|"review",
    "reason": "Brief explanation",
    "confidence": 0.0-1.0
  }}
]
```

Classify each tool based on its name, method, path, and description."""

        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
            )
            
            response_text = response.text.strip()
            
            # Clean up response
            if response_text.startswith("```"):
                lines = response_text.split("\n")
                end_idx = len(lines) - 1
                for j in range(len(lines) - 1, 0, -1):
                    if lines[j].strip() == "```":
                        end_idx = j
                        break
                response_text = "\n".join(lines[1:end_idx])
            
            if not response_text.startswith("["):
                start = response_text.find("[")
                end = response_text.rfind("]") + 1
                if start != -1 and end > start:
                    response_text = response_text[start:end]
            
            batch_results = json.loads(response_text)
            results.extend(batch_results)
            
            # Rate limiting
            time.sleep(1)
            
        except Exception as e:
            logger.warning("Gemini batch failed: %s", e)
            # Fall back to rule-based for this batch
            for tool in batch:
                result = apply_rules(tool, policy)
                result["name"] = tool["name"]
                results.append(result)
    
    return results


# ── Featherless Reasoning ─────────────────────────────────────────────────────


def _reasoning_edge_cases(
    tools: list[dict],
    classifications: list[dict],
    model: str = "deepseek-ai/DeepSeek-R1"
) -> list[dict]:
    """Use Featherless (DeepSeek-R1) to reason about edge cases."""
    from openai import OpenAI
    
    api_key = os.getenv("DEDALUS_API_KEY")
    if not api_key:
        logger.warning("DEDALUS_API_KEY not set, skipping reasoning enhancement")
        return classifications
    
    client = OpenAI(
        base_url="https://api.featherless.ai/v1",
        api_key=api_key,
    )
    
    # Find edge cases (low confidence or needs review)
    edge_cases = []
    for i, (tool, classification) in enumerate(zip(tools, classifications)):
        if classification.get("expose") == "review" or classification.get("confidence", 1.0) < 0.6:
            edge_cases.append((i, tool, classification))
    
    if not edge_cases:
        logger.info("No edge cases to analyze")
        return classifications
    
    logger.info("Analyzing %d edge cases with %s", len(edge_cases), model)
    
    for idx, tool, current in edge_cases:
        prompt = f"""Analyze this API endpoint and determine if it should be exposed via MCP.

Tool: {json.dumps(tool, indent=2)}

Current classification:
- Classification: {current.get('classification')}
- Expose: {current.get('expose')}
- Reason: {current.get('reason')}
- Confidence: {current.get('confidence')}

Consider:
1. What are the potential risks of exposing this endpoint?
2. Could it be misused in harmful ways?
3. Does it affect billing, security, or system stability?
4. Is it a standard CRUD operation or something more sensitive?

Respond with JSON only:
{{"expose": true/false, "reason": "explanation", "confidence": 0.0-1.0}}"""

        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
            )
            
            result_text = response.choices[0].message.content.strip()
            
            # Parse JSON from response
            if not result_text.startswith("{"):
                start = result_text.find("{")
                end = result_text.rfind("}") + 1
                if start != -1 and end > start:
                    result_text = result_text[start:end]
            
            result = json.loads(result_text)
            
            # Update classification
            classifications[idx]["expose"] = result.get("expose", "review")
            classifications[idx]["reason"] = result.get("reason", current.get("reason"))
            classifications[idx]["confidence"] = result.get("confidence", 0.7)
            classifications[idx]["enhanced"] = True
            
            time.sleep(0.5)  # Rate limiting
            
        except Exception as e:
            logger.warning("Reasoning failed for %s: %s", tool.get('name'), e)
    
    return classifications


# ── In-memory Classification (for API server use) ────────────────────────────


def classify_tools(
    tools: list[dict],
    policy: PolicyType = "moderate",
    use_gemini: bool = False,
    use_reasoning: bool = False,
) -> dict:
    """Classify a list of raw tool dicts in memory.

    Returns dict with summary and classifications list.
    """
    if not tools:
        return {"summary": {"total": 0, "exposable": 0, "blocked": 0, "needs_review": 0}, "classifications": []}

    logger.info("Classifying %d tools with '%s' policy", len(tools), policy)

    if use_gemini:
        classifications = classify_batch_with_gemini(tools, policy)
    else:
        classifications = []
        for tool in tools:
            result = apply_rules(tool, policy)
            result["name"] = tool.get("name", "")
            classifications.append(result)

    if use_reasoning:
        classifications = _reasoning_edge_cases(tools, classifications)

    exposable = sum(1 for c in classifications if c.get("expose") is True)
    blocked = sum(1 for c in classifications if c.get("expose") is False)
    review = sum(1 for c in classifications if c.get("expose") == "review")

    logger.info("Classification complete — Total: %d, Exposable: %d, Blocked: %d, Review: %d",
                len(tools), exposable, blocked, review)

    return {
        "policy": policy,
        "summary": {
            "total": len(tools),
            "exposable": exposable,
            "blocked": blocked,
            "needs_review": review,
        },
        "classifications": classifications,
    }


# ── File-based Classification (CLI use) ──────────────────────────────────────


def classify(
    input_path: str,
    output_path: str | None = None,
    policy: PolicyType = "moderate",
    use_gemini: bool = True,
    use_reasoning: bool = False,
) -> dict:
    """Main classification function."""
    
    # Load input
    input_data = json.loads(Path(input_path).read_text(encoding="utf-8"))
    tools = input_data.get("tools", [])
    
    if not tools:
        raise ValueError("No tools found in input file")
    
    logger.info("Classifying %d tools with '%s' policy", len(tools), policy)
    
    # Classify
    if use_gemini:
        classifications = classify_batch_with_gemini(tools, policy)
    else:
        classifications = []
        for tool in tools:
            result = apply_rules(tool, policy)
            result["name"] = tool["name"]
            classifications.append(result)
    
    # Enhance edge cases with reasoning
    if use_reasoning:
        classifications = _reasoning_edge_cases(tools, classifications)
    
    # Build output
    exposable = sum(1 for c in classifications if c.get("expose") == True)
    blocked = sum(1 for c in classifications if c.get("expose") == False)
    review = sum(1 for c in classifications if c.get("expose") == "review")
    
    result = {
        "source": input_data.get("source", input_path),
        "policy": policy,
        "summary": {
            "total": len(tools),
            "exposable": exposable,
            "blocked": blocked,
            "needs_review": review,
        },
        "classifications": classifications,
    }
    
    # Write output if path given
    if output_path:
        Path(output_path).write_text(
            json.dumps(result, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
    
    logger.info("Classification complete — Total: %d, Exposable: %d, Blocked: %d, Review: %d",
                len(tools), exposable, blocked, review)
    
    return result


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Classify API tools for MCP exposure"
    )
    
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="Input JSON file (from swagger_ingest.py or sdk_ingest.py)",
    )
    parser.add_argument(
        "--output", "-o",
        help="Output file path (default: input_classified.json)",
    )
    parser.add_argument(
        "--policy", "-p",
        choices=["conservative", "moderate", "permissive"],
        default="moderate",
        help="Exposure policy (default: moderate)",
    )
    parser.add_argument(
        "--no-gemini",
        action="store_true",
        help="Use rule-based classification only (no Gemini)",
    )
    parser.add_argument(
        "--use-reasoning",
        action="store_true",
        help="Use Featherless (DeepSeek-R1) for edge case reasoning",
    )
    
    args = parser.parse_args()
    
    try:
        classify(
            input_path=args.input,
            output_path=args.output,
            policy=args.policy,
            use_gemini=not args.no_gemini,
            use_reasoning=args.use_reasoning,
        )
    except Exception as e:
        print(f"[ERROR] Classification failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
