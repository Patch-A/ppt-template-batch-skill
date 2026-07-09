from __future__ import annotations

import os
import platform
import subprocess


def get_env_var(name: str) -> str:
    value = os.environ.get(name)
    if value:
        return value
    if platform.system().lower() != "windows":
        return ""
    for scope in ("User", "Machine"):
        try:
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    f"[Environment]::GetEnvironmentVariable('{name}', '{scope}')",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except Exception:
            continue
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    return ""
