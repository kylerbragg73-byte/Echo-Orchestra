"""
Godot MCP server.

Minimal Model Context Protocol server over stdio. Exposes two tools:
  - godot.export_project  — runs `godot --export-release` on a project dir
  - godot.check_errors    — runs Godot in script mode and returns stderr

Run with:  python -m mcp_servers.godot_server
(Configured as an MCP server in whichever client you use — Claude Desktop,
Cursor, etc.)

Requires Godot 4.2+ on PATH.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from typing import Any


PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "echo-godot", "version": "1.0.0"}

TOOLS = [
    {
        "name": "godot.export_project",
        "description": "Export a Godot 4 project to a release binary.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_path": {"type": "string", "description": "Absolute path to project directory"},
                "export_preset": {"type": "string", "description": "Name of the export preset"},
                "output_path": {"type": "string", "description": "Absolute output path for the binary"},
            },
            "required": ["project_path", "export_preset", "output_path"],
        },
    },
    {
        "name": "godot.check_errors",
        "description": "Run the Godot project headless and capture errors.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_path": {"type": "string"},
            },
            "required": ["project_path"],
        },
    },
]


def _send(msg: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def _error(req_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id,
            "error": {"code": code, "message": message}}


def _call_godot(args: list[str]) -> dict[str, Any]:
    godot = shutil.which("godot") or shutil.which("godot4")
    if not godot:
        return {"ok": False, "stderr": "godot binary not found on PATH"}
    try:
        r = subprocess.run([godot, *args], capture_output=True, text=True, timeout=600)
        return {"ok": r.returncode == 0, "stdout": r.stdout[-2000:],
                "stderr": r.stderr[-2000:], "returncode": r.returncode}
    except subprocess.TimeoutExpired:
        return {"ok": False, "stderr": "godot call timed out"}


def handle(request: dict[str, Any]) -> dict[str, Any]:
    req_id = request.get("id")
    method = request.get("method")

    if method == "initialize":
        return {"jsonrpc": "2.0", "id": req_id, "result": {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO,
        }}

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}

    if method == "tools/call":
        params = request.get("params", {})
        name = params.get("name")
        args = params.get("arguments", {})
        if name == "godot.export_project":
            result = _call_godot([
                "--headless", "--path", args["project_path"],
                "--export-release", args["export_preset"], args["output_path"],
            ])
        elif name == "godot.check_errors":
            result = _call_godot(["--headless", "--path", args["project_path"],
                                  "--check-only"])
        else:
            return _error(req_id, -32601, f"unknown tool {name}")
        return {"jsonrpc": "2.0", "id": req_id, "result": {
            "content": [{"type": "text", "text": json.dumps(result)}],
            "isError": not result["ok"],
        }}

    if method and method.startswith("notifications/"):
        return {}  # notifications don't get responses

    return _error(req_id, -32601, f"unknown method {method}")


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = handle(request)
        if resp:
            _send(resp)


if __name__ == "__main__":
    main()
