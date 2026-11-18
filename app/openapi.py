"""OpenAPI 3.1 description of the /api/v1 contract, built from the `api_route` registry.

Exported to docs/openapi.json by scripts/export_openapi.py; CI fails when the file drifts.
The SPA generates its TypeScript types from that file.
"""

from __future__ import annotations

import json
import re
from typing import Any

from flask import Flask
from pydantic import TypeAdapter
from pydantic.json_schema import GenerateJsonSchema

from app.api import Endpoint, api_endpoints

_PREFIX = "#/components/schemas/"
_REF = _PREFIX + "{model}"
# Request models are first emitted as "<Model>Input" and merged with the response model when identical.
_INPUT_SUFFIX = "Input"
_PATH_PARAM = re.compile(r"<(?:(?P<converter>[a-z]+):)?(?P<name>[a-zA-Z_][a-zA-Z0-9_]*)>")

ERROR_SCHEMA = {
    "type": "object",
    "required": ["status", "error_code", "message", "correlation_id"],
    "properties": {
        "status": {"const": "error"},
        "error_code": {"type": "integer", "description": "See docs/error-codes.md"},
        "message": {"type": "string", "description": "Safe to show to users"},
        "correlation_id": {"type": "string"},
        "details": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["field", "message"],
                "properties": {"field": {"type": "string"}, "message": {"type": "string"}},
            },
        },
    },
}


class _ResponseSchema(GenerateJsonSchema):
    """Responses are dumped with every field (no exclude_unset/none), so every field is required."""

    def field_is_required(self, field: Any, total: bool) -> bool:
        return True


def _schema(annotation: Any, components: dict[str, Any], mode: str) -> dict[str, Any]:
    adapter = TypeAdapter(annotation)
    if mode == "serialization":
        schema = adapter.json_schema(ref_template=_REF, mode="serialization", schema_generator=_ResponseSchema)
        components.update(schema.pop("$defs", {}))
    else:
        schema = adapter.json_schema(ref_template=_REF + _INPUT_SUFFIX, mode="validation")
        components.update({name + _INPUT_SUFFIX: value for name, value in schema.pop("$defs", {}).items()})
    return schema


def _rewrite_refs(node: Any, rename: dict[str, str]) -> Any:
    if isinstance(node, dict):
        return {
            key: (_PREFIX + rename.get(value[len(_PREFIX) :], value[len(_PREFIX) :]))
            if key == "$ref" and isinstance(value, str) and value.startswith(_PREFIX)
            else _rewrite_refs(value, rename)
            for key, value in node.items()
        }
    if isinstance(node, list):
        return [_rewrite_refs(item, rename) for item in node]
    return node


def _merge_input_models(components: dict[str, Any], paths: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Name a request model like its response model unless the two schemas differ (e.g. optional vs required)."""
    inputs = {name[: -len(_INPUT_SUFFIX)] for name in components if name.endswith(_INPUT_SUFFIX)}
    inputs = {name for name in inputs if name + _INPUT_SUFFIX in components}
    plain = {name + _INPUT_SUFFIX: name for name in inputs}
    distinct = {
        name
        for name in inputs
        if name in components and _rewrite_refs(components[name + _INPUT_SUFFIX], plain) != components[name]
    }
    changed = True
    while changed:  # a model that references a distinct input model is distinct too
        changed = False
        for name in inputs - distinct:
            referenced = json.dumps(components[name + _INPUT_SUFFIX])
            if any(f'"{_PREFIX}{other}{_INPUT_SUFFIX}"' in referenced for other in distinct):
                distinct.add(name)
                changed = True
    rename = {name + _INPUT_SUFFIX: name for name in inputs - distinct}
    merged: dict[str, Any] = {}
    for name, schema in components.items():
        target = rename.get(name, name)
        if name in rename and target in components:
            continue  # identical to the response model
        merged[target] = _rewrite_refs(schema, rename)
    return merged, _rewrite_refs(paths, rename)


def _openapi_path(rule: str) -> tuple[str, list[dict[str, Any]]]:
    parameters = []
    for match in _PATH_PARAM.finditer(rule):
        kind = "integer" if match.group("converter") == "int" else "string"
        parameters.append({"name": match.group("name"), "in": "path", "required": True, "schema": {"type": kind}})
    return _PATH_PARAM.sub(lambda m: "{" + m.group("name") + "}", rule), parameters


def _operation(endpoint: Endpoint, components: dict[str, Any]) -> dict[str, Any]:
    path, parameters = _openapi_path(endpoint.rule)
    if endpoint.query is not None:
        query_schema = _schema(endpoint.query, components, "validation")
        required = set(query_schema.get("required", []))
        for name, prop in query_schema.get("properties", {}).items():
            parameters.append({"name": name, "in": "query", "required": name in required, "schema": prop})

    operation: dict[str, Any] = {
        "operationId": endpoint.name,
        "summary": endpoint.summary,
        "tags": [endpoint.tag],
    }
    if parameters:
        operation["parameters"] = parameters
    if endpoint.body is not None:
        operation["requestBody"] = {
            "required": True,
            "content": {"application/json": {"schema": _schema(endpoint.body, components, "validation")}},
        }

    if endpoint.raw_response is not None:
        success: dict[str, Any] = {
            "description": "File download",
            "content": {
                media_type: {"schema": {"type": "string", "format": "binary"}} for media_type in endpoint.raw_response
            },
        }
    else:
        data_schema = _schema(endpoint.response, components, "serialization") if endpoint.response else {"type": "null"}
        success = {
            "description": "Success",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "required": ["status", "correlation_id", "data"],
                        "properties": {
                            "status": {"const": "ok"},
                            "correlation_id": {"type": "string"},
                            "data": data_schema,
                        },
                    }
                }
            },
        }
    error = {
        "description": "Error envelope",
        "content": {"application/json": {"schema": {"$ref": _REF.format(model="ApiError")}}},
    }
    operation["responses"] = {str(endpoint.status): success, "default": error}
    if not endpoint.auth:
        operation["security"] = []
    return {"path": path, "method": endpoint.method.lower(), "operation": operation}


def build_openapi(app: Flask) -> dict[str, Any]:
    components: dict[str, Any] = {"ApiError": ERROR_SCHEMA}
    paths: dict[str, dict[str, Any]] = {}
    for endpoint in api_endpoints(app):
        built = _operation(endpoint, components)
        paths.setdefault(built["path"], {})[built["method"]] = built["operation"]
    components, paths = _merge_input_models(components, paths)
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "GivemeaChance API",
            "version": "1",
            "description": "Personal job-search workspace. Conventions, auth and errors: docs/api.md.",
        },
        "servers": [{"url": "/"}],
        "security": [{"session": []}],
        "paths": {path: paths[path] for path in sorted(paths)},
        "components": {
            "schemas": {name: components[name] for name in sorted(components)},
            "securitySchemes": {"session": {"type": "apiKey", "in": "cookie", "name": "session"}},
        },
    }
