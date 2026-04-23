"""
Blender MCP server.

Exposes:
  - blender.render_scene  — runs blender --background with a Python script
                            and renders a frame or animation
  - blender.run_python    — runs an arbitrary Python script inside Blender

Run with:  python -m mcp_servers.blender_server
Requires blender on PATH.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "echo-blender", "version": "1.0.0"}

TOOLS = [
    {
        "name": "blender.render_scene",
        "description": "Render a .blend file to an image or animation.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "blend_file": {"type": "string"},
                "output_path": {"type": "string"},
                "frame": {"type": "integer", "default": 1},
                "engine": {"type": "string", "enum": ["CYCLES", "BLENDER_EEVEE_NEXT"],
                           "default": "BLENDER_EEVEE_NEXT"},
            },
            "required": ["blend_file", "output_path"],
        },
    },
    {
        "name": "blender.run_python",
        "description": "Run arbitrary Python inside Blender (headless).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "script": {"type": "string"},
                "blend_file": {"type": "string",
                               "description": "Optional .blend to open first"},
            },
            "required": ["script"],
        },
    },
]


def _send(msg: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def _error(req_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id,
            "error": {"code": code, "message": message}}


def _blender() -> str | None:
    return shutil.which("blender")


def _run(args: list[str], timeout: int = 600) -> dict[str, Any]:
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return {"ok": r.returncode == 0, "stdout": r.stdout[-4000:],
                "stderr": r.stderr[-2000:], "returncode": r.returncode}
    except subprocess.TimeoutExpired:
        return {"ok": False, "stderr": "blender call timed out"}


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
        blender = _blender()
        if not blender:
            return _error(req_id, -32000, "blender not found on PATH")

        params = request.get("params", {})
        name = params.get("name")
        args = params.get("arguments", {})

        if name == "blender.render_scene":
            cmd = [
                blender, "--background", args["blend_file"],
                "--engine", args.get("engine", "BLENDER_EEVEE_NEXT"),
                "--render-output", args["output_path"],
                "--render-frame", str(args.get("frame", 1)),
            ]
            result = _run(cmd)
        elif name == "blender.run_python":
            # Write script to temp file
            with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False,
                                              encoding="utf-8") as f:
                f.write(args["script"])
                script_path = f.name
            try:
                cmd = [blender, "--background"]
                if args.get("blend_file"):
                    cmd.append(args["blend_file"])
                cmd += ["--python", script_path]
                result = _run(cmd)
            finally:
                Path(script_path).unlink(missing_ok=True)
        else:
            return _error(req_id, -32601, f"unknown tool {name}")

        return {"jsonrpc": "2.0", "id": req_id, "result": {
            "content": [{"type": "text", "text": json.dumps(result)}],
            "isError": not result["ok"],
        }}

    if method and method.startswith("notifications/"):
        return {}

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
