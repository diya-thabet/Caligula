"""Provider-neutral tool definitions from plain functions.

Agent tools are Python functions whose signature and docstring describe them
(see `application/investigation/toolkit.py`). This turns one into a JSON
schema any tool-calling API accepts, and runs a call from a model: arguments
are validated and coerced against the signature, and a refusal or a bad
argument goes back to the model as an error message instead of crashing
the loop.
"""

from __future__ import annotations

import inspect
import json
import re
import typing
from typing import Any

from pydantic import ValidationError, create_model

from caligula.application.ports.llm import Tool, ToolRefusal

_ARG = re.compile(r"^(\s*)(\w+):\s*(.*)$")


def _docstring(fn: Tool) -> tuple[str, dict[str, str]]:
    """(description, {arg: description}) from a Google-style docstring."""
    head, _, args = (inspect.getdoc(fn) or "").partition("\nArgs:\n")
    params: dict[str, str] = {}
    current, indent = None, None
    for line in args.splitlines():
        m = _ARG.match(line)
        if m and (indent is None or len(m.group(1)) == indent):
            indent, current = len(m.group(1)), m.group(2)
            params[current] = m.group(3).strip()
        elif current and line.strip():  # continuation of the previous argument
            params[current] += " " + line.strip()
    return " ".join(head.split()), params


def _model(fn: Tool):
    hints = typing.get_type_hints(fn)
    fields = {}
    for name, p in inspect.signature(fn).parameters.items():
        default = ... if p.default is inspect.Parameter.empty else p.default
        fields[name] = (hints.get(name, Any), default)
    return create_model(f"{fn.__name__}_args", **fields)


def _strip_titles(node: Any) -> Any:
    if isinstance(node, dict):
        return {k: _strip_titles(v) for k, v in node.items() if k != "title"}
    if isinstance(node, list):
        return [_strip_titles(v) for v in node]
    return node


def function_schema(fn: Tool) -> dict:
    """{name, description, parameters} for one tool."""
    description, arg_docs = _docstring(fn)
    schema = _strip_titles(_model(fn).model_json_schema())
    for name, text in arg_docs.items():
        if name in schema.get("properties", {}):
            schema["properties"][name]["description"] = text
    schema.setdefault("properties", {})
    return {"name": fn.__name__, "description": description, "parameters": schema}


def call_tool(fn: Tool, arguments: str | dict) -> tuple[str, bool]:
    """Run a tool call from a model. Returns (output, is_error)."""
    try:
        raw = json.loads(arguments or "{}") if isinstance(arguments, str) else arguments
        args = _model(fn).model_validate(raw)
    except (json.JSONDecodeError, ValidationError) as exc:
        return f"Invalid arguments: {exc}", True
    try:
        return fn(**dict(args)), False
    except ToolRefusal as exc:
        return str(exc), True
