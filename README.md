# MCP Servers

These are Model Context Protocol servers over stdio, written in plain Python.
They let MCP-aware clients (Claude Desktop, Cursor, etc.) call tools that
wrap Godot, Blender, and ffmpeg.

**WORKSTATION tier only.** Each server requires its binary on PATH:
- `godot` or `godot4` (4.2+)
- `blender` (4.0+)
- `ffmpeg` and `ffprobe` (6.0+)

## Running a server manually

```bash
cd echo-orchestra
python -m mcp_servers.godot_server
python -m mcp_servers.blender_server
python -m mcp_servers.ffmpeg_server
```

Each server reads JSON-RPC requests from stdin and writes responses to stdout.

## Claude Desktop config

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`
(macOS) or the Windows / Linux equivalent:

```json
{
  "mcpServers": {
    "echo-godot": {
      "command": "python",
      "args": ["-m", "mcp_servers.godot_server"],
      "cwd": "/absolute/path/to/echo-orchestra"
    },
    "echo-blender": {
      "command": "python",
      "args": ["-m", "mcp_servers.blender_server"],
      "cwd": "/absolute/path/to/echo-orchestra"
    },
    "echo-ffmpeg": {
      "command": "python",
      "args": ["-m", "mcp_servers.ffmpeg_server"],
      "cwd": "/absolute/path/to/echo-orchestra"
    }
  }
}
```

## Tools exposed

**godot-server**
- `godot.export_project` — export a Godot 4 project to a release binary
- `godot.check_errors` — headless syntax/asset check

**blender-server**
- `blender.render_scene` — render a .blend to image or animation
- `blender.run_python` — run arbitrary Python inside headless Blender

**ffmpeg-server**
- `ffmpeg.concat_clips` — concatenate media files into MP4
- `ffmpeg.overlay_audio` — mux narration onto a video
- `ffmpeg.probe` — ffprobe JSON metadata

## Not implemented (yet)

- Authentication (servers run under your local user; do not expose to network)
- Rate limiting (clients handle this)
- Multi-client concurrency — each server handles one stdin/stdout pair at a time
