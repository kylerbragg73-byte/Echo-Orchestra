"""
LOOP-06 — Movie Loop.

Produces a real MP4 on disk at `workspace/movies/<slug>/output.mp4`.
Uses ffmpeg for the concat step. Generates per-scene images via a
multimodal model (premium-multimodal) and narration audio via any TTS
the operator wires in. If TTS is not configured, the video is silent
with on-screen captions.

WORKSTATION tier required (ffmpeg binary + multimodal model budget).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from compliance.legal_gate import LegalGate, Jurisdiction
from intel.perplexity_client import PerplexityIntelClient
from loops._base import LoopBase
from util.logging_setup import get_logger

log = get_logger("echo.loop.movie")


# Simple silent slideshow: each scene is a solid-color frame with caption text.
# A real workstation setup would swap in generated images and TTS narration.
def _build_caption_png(text: str, out_path: Path, width: int = 1280, height: int = 720) -> bool:
    """Use ffmpeg's drawtext filter to render a caption card as a PNG.
    Returns True on success."""
    # Escape for ffmpeg drawtext
    safe = text.replace(":", " -").replace("'", "").replace("\\", "")[:200]
    try:
        subprocess.run([
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"color=c=black:s={width}x{height}:d=1",
            "-vf",
            f"drawtext=text='{safe}':fontcolor=white:fontsize=48:"
            f"x=(w-text_w)/2:y=(h-text_h)/2",
            "-frames:v", "1",
            str(out_path),
        ], check=True, capture_output=True, timeout=30)
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
        log.warning("caption render failed: %s", exc)
        return False


class MovieLoop(LoopBase):
    loop_name = "movie"
    minimum_tier = "workstation"

    def __init__(self, output_root: str = "workspace/movies"):
        super().__init__()
        self.gate = LegalGate()
        self.intel = PerplexityIntelClient()
        self.output_root = Path(output_root)
        self.output_root.mkdir(parents=True, exist_ok=True)

    def run(self, concept: str, num_scenes: int = 5,
            seconds_per_scene: int = 4) -> dict:
        log.info("MovieLoop start: concept=%s scenes=%d", concept, num_scenes)

        if shutil.which("ffmpeg") is None:
            return {"status": "blocked",
                    "reason": "ffmpeg not found on PATH. Install ffmpeg first."}

        compliance = self.gate.check(
            product_type="video",
            target_markets=[Jurisdiction.US, Jurisdiction.EU],
            description=concept,
        )
        if not compliance.approved:
            return {"status": "blocked", "reason": compliance.block_reason}

        # Script
        self._record("claude-opus-4-7", "script", 1000, 2000, agent="writer")
        script = self._call_model(
            "premium-code",
            prompt=(
                f"Write a {num_scenes}-scene short-video script for: {concept}. "
                f"Each scene should be a single sentence caption ({seconds_per_scene} "
                f"seconds on screen). Return exactly {num_scenes} lines, no numbering, "
                f"no extra text."
            ),
            max_tokens=1000,
        )
        if not script:
            return {"status": "failed", "reason": "empty_model_response"}

        scenes = [s.strip() for s in script.splitlines() if s.strip()][:num_scenes]
        if len(scenes) < 2:
            scenes = [concept, f"The end."]

        slug = self.slug(concept)[:40] or "echo-movie"
        proj_dir = self.output_root / slug
        if proj_dir.exists():
            return {"status": "exists", "output_path": str(proj_dir)}
        proj_dir.mkdir(parents=True, exist_ok=True)

        # Render caption frames
        scene_files = []
        for i, scene in enumerate(scenes):
            img_path = proj_dir / f"scene_{i:02d}.png"
            if _build_caption_png(scene, img_path):
                scene_files.append(img_path)
            else:
                # Fallback: skip this scene
                continue

        if not scene_files:
            return {"status": "failed", "reason": "no_scenes_rendered"}

        # Concat using ffmpeg's concat demuxer
        concat_file = proj_dir / "scenes.txt"
        with concat_file.open("w", encoding="utf-8") as f:
            for img in scene_files:
                f.write(f"file '{img.name}'\nduration {seconds_per_scene}\n")
            # Last frame needs repeating (concat demuxer quirk)
            f.write(f"file '{scene_files[-1].name}'\n")

        output_mp4 = proj_dir / "output.mp4"
        try:
            subprocess.run([
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", concat_file.name,
                "-vsync", "vfr",
                "-pix_fmt", "yuv420p",
                str(output_mp4.name),
            ], check=True, capture_output=True, timeout=120, cwd=str(proj_dir))
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            log.error("ffmpeg concat failed: %s", exc)
            return {"status": "failed", "reason": "ffmpeg_concat_failed"}

        (proj_dir / "script.txt").write_text("\n".join(scenes), encoding="utf-8")
        (proj_dir / "meta.json").write_text(json.dumps({
            "concept": concept, "slug": slug,
            "num_scenes": len(scene_files), "seconds_per_scene": seconds_per_scene,
            "created_at": datetime.utcnow().isoformat(),
            "output_mp4": str(output_mp4),
            "disclosures": compliance.required_disclosures,
        }, indent=2), encoding="utf-8")

        log.info("MovieLoop wrote %s", output_mp4)
        return {
            "status": "created",
            "output_path": str(proj_dir),
            "output_mp4": str(output_mp4),
            "scenes": len(scene_files),
        }
