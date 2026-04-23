"""
FFmpeg MCP server.

Exposes:
  - ffmpeg.concat_clips   — concatenates a list of media files into one MP4
  - ffmpeg.overlay_audio  — muxes a narration audio track onto a video
  - ffmpeg.probe          — returns ffprobe JSON for a media file

Run with:  python -m mcp_servers.ffmpeg_server
Requires ffmpeg + ffprobe on PATH.
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
SERVER_INFO = {"name": "echo-ffmpeg", "version": "1.0.0"}

TOOLS = [
    {
        "name": "ffmpeg.concat_clips",
        "description": "Concatenate a list of media files into a single MP4.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "files": {"type": "array", "items": {"type": "string"}},
                "output_path": {"type": "string"},
            },
            "required": ["files", "output_path"],
        },
    },
    {
        "name": "ffmpeg.overlay_audio",
        "description": "Mux an audio track onto a video (replaces existing audio).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "video_path": {"type": "string"},
                "audio_path": {"type": "string"},
                "output_path": {"type": "string"},
            },
            "required": ["video_path", "audio_path", "output_path"],
        },
    },
    {
        "name": "ffmpeg.probe",
        "description": "Return ffprobe JSON metadata for a media file.",
        "inputSchema": {
            "type": "object",
            "properties": {"file_path": {"type": "string"}},
            "required": ["file_path"],
        },
    },
]


def _send(msg: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def _error(req_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id,
            "error": {"code": code, "message": message}}


def _run(args: list[str], timeout: int = 300) -> dict[str, Any]:
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return {"ok": r.returncode == 0, "stdout": r.stdout[-4000:],
                "stderr": r.stderr[-2000:], "returncode": r.returncode}
    except subprocess.TimeoutExpired:
        return {"ok": False, "stderr": "ffmpeg call timed out"}


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
        ffmpeg = shutil.which("ffmpeg")
        ffprobe = shutil.which("ffprobe")
        if not ffmpeg or not ffprobe:
            return _error(req_id, -32000, "ffmpeg/ffprobe not found on PATH")

        params = request.get("params", {})
        name = params.get("name")
        args = params.get("arguments", {})

        if name == "ffmpeg.concat_clips":
            with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False,
                                              encoding="utf-8") as f:
                for fp in args["files"]:
                    f.write(f"file '{fp}'\n")
                concat_list = f.name
            try:
                result = _run([
                    ffmpeg, "-y", "-f", "concat", "-safe", "0",
                    "-i", concat_list, "-c", "copy", args["output_path"],
                ])
            finally:
                Path(concat_list).unlink(missing_ok=True)

        elif name == "ffmpeg.overlay_audio":
            result = _run([
                ffmpeg, "-y",
                "-i", args["video_path"],
                "-i", args["audio_path"],
                "-c:v", "copy", "-c:a", "aac",
                "-map", "0:v:0", "-map", "1:a:0",
                "-shortest", args["output_path"],
            ])

        elif name == "ffmpeg.probe":
            result = _run([
                ffprobe, "-v", "quiet", "-print_format", "json",
                "-show_format", "-show_streams", args["file_path"],
            ])

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
