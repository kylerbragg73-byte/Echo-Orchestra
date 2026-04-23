"""
Device tier detection.

At startup, Echo reads the host: OS, RAM, CPU, disk, Docker presence, GPU
presence. It then classifies into one of five tiers and reports which
capabilities are enabled. Capabilities that require a higher tier are
automatically disabled, so Echo never claims to do something its host
cannot actually deliver.
"""

from __future__ import annotations

import os
import platform as _platform
import shutil
import subprocess
from dataclasses import dataclass
from enum import Enum
from typing import List

import psutil

from util.logging_setup import get_logger

log = get_logger("echo.device")


class DeviceTier(Enum):
    PHONE = "phone"
    LITE = "lite"
    STANDARD = "standard"
    WORKSTATION = "workstation"
    SERVER = "server"


TIER_ORDER = [DeviceTier.PHONE, DeviceTier.LITE, DeviceTier.STANDARD,
              DeviceTier.WORKSTATION, DeviceTier.SERVER]


@dataclass
class Capability:
    name: str
    required_tier: DeviceTier
    enabled: bool = False
    reason: str = ""


# All capabilities Echo knows about, and the minimum tier each requires.
# Loop names match classes in loops/*.py
ALL_CAPABILITIES = [
    # Phone tier — pure API work
    ("api_routing",        DeviceTier.PHONE),
    ("ledger",             DeviceTier.PHONE),
    ("compliance_gate",    DeviceTier.PHONE),
    ("tax_module",         DeviceTier.PHONE),
    ("human_loop",         DeviceTier.PHONE),
    ("echo_intel",         DeviceTier.PHONE),
    ("strategy_engine",    DeviceTier.PHONE),
    ("self_upgrade_pip",   DeviceTier.PHONE),

    # Lite tier — build loops that produce files
    ("digital_product_loop", DeviceTier.LITE),
    ("content_loop",         DeviceTier.LITE),
    ("human_centered_loop",  DeviceTier.LITE),

    # Standard tier — docker + proxies
    ("docker_stack",        DeviceTier.STANDARD),
    ("litellm_proxy",       DeviceTier.STANDARD),
    ("saas_loop",           DeviceTier.STANDARD),
    ("stripe_webhook",      DeviceTier.STANDARD),
    ("scheduler_daemon",    DeviceTier.STANDARD),
    ("self_upgrade_docker", DeviceTier.STANDARD),

    # Workstation tier — GPU or heavy local compute
    ("local_llama",   DeviceTier.WORKSTATION),
    ("mcp_godot",     DeviceTier.WORKSTATION),
    ("mcp_blender",   DeviceTier.WORKSTATION),
    ("ffmpeg_render", DeviceTier.WORKSTATION),
    ("game_loop",     DeviceTier.WORKSTATION),
    ("movie_loop",    DeviceTier.WORKSTATION),

    # Server tier — unattended
    ("openclaw_247",       DeviceTier.SERVER),
    ("headless_operation", DeviceTier.SERVER),
]


class DeviceProfile:
    def __init__(self) -> None:
        self.os = _platform.system()
        self.os_release = _platform.release()
        self.arch = _platform.machine()
        self.ram_gb = psutil.virtual_memory().total / (1024 ** 3)
        self.cpu_count = psutil.cpu_count(logical=False) or psutil.cpu_count() or 1
        self.has_docker = self._detect_docker()
        self.has_gpu = self._detect_gpu()
        self.disk_free_gb = shutil.disk_usage(os.path.expanduser("~")).free / (1024 ** 3)
        self.is_headless = self._detect_headless()
        self.tier = self._classify()
        log.info(
            "Device: tier=%s os=%s arch=%s ram=%.1fGB cpu=%d docker=%s gpu=%s headless=%s",
            self.tier.value, self.os, self.arch, self.ram_gb, self.cpu_count,
            self.has_docker, self.has_gpu, self.is_headless,
        )

    @staticmethod
    def _detect_docker() -> bool:
        if shutil.which("docker") is None:
            return False
        try:
            r = subprocess.run(
                ["docker", "info"], capture_output=True, timeout=5, text=True
            )
            return r.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _detect_gpu(self) -> bool:
        # NVIDIA
        try:
            r = subprocess.run(
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                capture_output=True, timeout=5, text=True,
            )
            if r.returncode == 0 and r.stdout.strip():
                return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        # Apple Silicon — integrated GPU adequate for small models via MLX / llama.cpp
        if self.arch in ("arm64", "aarch64") and self.os == "Darwin":
            return True
        # AMD ROCm
        if shutil.which("rocm-smi"):
            return True
        return False

    @staticmethod
    def _detect_headless() -> bool:
        if os.name == "nt":
            return False  # Windows: treat as desktop
        return not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY")

    def _classify(self) -> DeviceTier:
        # Phone signals
        if os.environ.get("PREFIX", "").startswith("/data/data/com.termux"):
            return DeviceTier.PHONE
        if "iPhone" in _platform.platform() or "iPad" in _platform.platform():
            return DeviceTier.PHONE
        if self.ram_gb < 4:
            return DeviceTier.PHONE

        # Server: Linux, headless, docker, 16+ GB
        if (self.os == "Linux" and self.is_headless
                and self.has_docker and self.ram_gb >= 16):
            return DeviceTier.SERVER

        # Workstation: 16+ GB, docker, GPU
        if self.has_docker and self.ram_gb >= 16 and self.has_gpu:
            return DeviceTier.WORKSTATION

        # Standard: docker, 8+ GB
        if self.has_docker and self.ram_gb >= 8:
            return DeviceTier.STANDARD

        # Lite: everything else with enough RAM for Python
        if self.ram_gb >= 4:
            return DeviceTier.LITE

        return DeviceTier.PHONE

    def capabilities(self) -> List[Capability]:
        my_rank = TIER_ORDER.index(self.tier)
        caps = []
        for name, required in ALL_CAPABILITIES:
            needed_rank = TIER_ORDER.index(required)
            enabled = my_rank >= needed_rank
            caps.append(Capability(
                name=name,
                required_tier=required,
                enabled=enabled,
                reason=(f"tier {self.tier.value} >= {required.value}"
                        if enabled else
                        f"requires {required.value}, host is {self.tier.value}"),
            ))
        return caps

    def summary(self) -> dict:
        return {
            "tier": self.tier.value,
            "os": self.os,
            "os_release": self.os_release,
            "arch": self.arch,
            "ram_gb": round(self.ram_gb, 1),
            "cpu_count": self.cpu_count,
            "disk_free_gb": round(self.disk_free_gb, 1),
            "has_docker": self.has_docker,
            "has_gpu": self.has_gpu,
            "is_headless": self.is_headless,
            "capabilities": [
                {"name": c.name, "enabled": c.enabled,
                 "required_tier": c.required_tier.value, "reason": c.reason}
                for c in self.capabilities()
            ],
        }
