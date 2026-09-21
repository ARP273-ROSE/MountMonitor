"""Hardware detection for performance optimization."""

import os
import platform
import multiprocessing
from dataclasses import dataclass
from typing import Optional


@dataclass
class HardwareInfo:
    """Detected hardware capabilities."""
    os_name: str
    os_version: str
    cpu_name: str
    cpu_cores_physical: int
    cpu_cores_logical: int
    ram_total_mb: int
    gpu_name: str
    gpu_vram_mb: int
    is_ssd: bool

    @property
    def recommended_workers(self) -> int:
        """Recommended number of worker threads."""
        return max(2, min(self.cpu_cores_physical, 8))

    @property
    def recommended_buffer_size(self) -> int:
        """Recommended graph buffer size based on RAM."""
        if self.ram_total_mb > 16000:
            return 100000
        elif self.ram_total_mb > 8000:
            return 50000
        elif self.ram_total_mb > 4000:
            return 25000
        return 10000


# Sous pythonw, chaque sous-processus ouvre brievement une console noire :
# quatre fenetres qui clignotent au demarrage, sans explication. CREATE_NO_WINDOW
# n'existe que sous Windows.
_SANS_CONSOLE = getattr(__import__('subprocess'), 'CREATE_NO_WINDOW', 0)


def detect_hardware() -> HardwareInfo:
    """Detect hardware capabilities."""
    os_name = platform.system()
    os_version = platform.version()

    cpu_name = platform.processor() or "Unknown"
    cpu_cores_physical = multiprocessing.cpu_count() or 2
    cpu_cores_logical = os.cpu_count() or cpu_cores_physical

    # Try to get physical cores on Windows
    if os_name == "Windows":
        try:
            import subprocess
            result = subprocess.run(
                ["wmic", "cpu", "get", "NumberOfCores", "/value"],
                capture_output=True, text=True, timeout=5,
                creationflags=_SANS_CONSOLE
            )
            for line in result.stdout.strip().split('\n'):
                if 'NumberOfCores' in line:
                    cpu_cores_physical = int(line.split('=')[1].strip())
        except Exception:
            cpu_cores_physical = cpu_cores_logical // 2

        try:
            import subprocess
            result = subprocess.run(
                ["wmic", "cpu", "get", "Name", "/value"],
                capture_output=True, text=True, timeout=5,
                creationflags=_SANS_CONSOLE
            )
            for line in result.stdout.strip().split('\n'):
                if 'Name' in line:
                    cpu_name = line.split('=')[1].strip()
        except Exception:
            pass

    # RAM detection
    ram_total_mb = 8192  # Default
    try:
        if os_name == "Windows":
            import subprocess
            result = subprocess.run(
                ["wmic", "OS", "get", "TotalVisibleMemorySize", "/value"],
                capture_output=True, text=True, timeout=5,
                creationflags=_SANS_CONSOLE
            )
            for line in result.stdout.strip().split('\n'):
                if 'TotalVisibleMemorySize' in line:
                    ram_total_mb = int(line.split('=')[1].strip()) // 1024
        elif os_name == "Linux":
            with open('/proc/meminfo', 'r') as f:
                for line in f:
                    if line.startswith('MemTotal'):
                        ram_total_mb = int(line.split()[1]) // 1024
                        break
        elif os_name == "Darwin":
            import subprocess
            result = subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                capture_output=True, text=True, timeout=5,
                creationflags=_SANS_CONSOLE
            )
            ram_total_mb = int(result.stdout.strip()) // (1024 * 1024)
    except Exception:
        pass

    # GPU detection (basic)
    gpu_name = "Unknown"
    gpu_vram_mb = 0
    try:
        if os_name == "Windows":
            import subprocess
            result = subprocess.run(
                ["wmic", "path", "win32_VideoController", "get", "Name", "/value"],
                capture_output=True, text=True, timeout=5,
                creationflags=_SANS_CONSOLE
            )
            for line in result.stdout.strip().split('\n'):
                if 'Name' in line:
                    gpu_name = line.split('=')[1].strip()
                    break
    except Exception:
        pass

    # SSD detection (basic heuristic)
    is_ssd = True  # Default assumption for modern systems

    return HardwareInfo(
        os_name=os_name,
        os_version=os_version,
        cpu_name=cpu_name,
        cpu_cores_physical=cpu_cores_physical,
        cpu_cores_logical=cpu_cores_logical,
        ram_total_mb=ram_total_mb,
        gpu_name=gpu_name,
        gpu_vram_mb=gpu_vram_mb,
        is_ssd=is_ssd,
    )
