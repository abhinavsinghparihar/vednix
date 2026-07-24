"""
System info plugin — live CPU / RAM / disk / battery.

♻️ PRESERVED from dev_ai/plugins/system_info.py.
Fixes: async via asyncio.to_thread (audit BL4: 300ms cpu_percent would stall a
request handler); Hindi/Hinglish triggers; psutil-missing answered politely in
the user's register.
"""

from __future__ import annotations

import asyncio
import re

from agents.base import Plugin, PluginContext

try:
    import psutil
except ImportError:  # psutil optional, same graceful pattern as the original
    psutil = None

TRIGGERS = (
    "cpu", "ram", "memory usage", "battery", "disk space", "system status", "system info",
    "system ka haal", "system status batao", "kitni ram", "battery kitni",
    "सीपीयू", "रैम", "बैटरी", "सिस्टम", "डिस्क",
)


def _collect_stats() -> list[str]:
    cpu = psutil.cpu_percent(interval=0.3)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    lines = [
        f"**CPU:** {cpu:.0f}%",
        f"**RAM:** {mem.percent:.0f}% used ({mem.used / 1024**3:.1f} GB / {mem.total / 1024**3:.1f} GB)",
        f"**Disk:** {disk.percent:.0f}% used ({disk.used / 1024**3:.0f} GB / {disk.total / 1024**3:.0f} GB)",
    ]
    if hasattr(psutil, "sensors_battery") and (battery := psutil.sensors_battery()) is not None:
        lines.append(f"**Battery:** {battery.percent:.0f}%{' (charging)' if battery.power_plugged else ''}")
    return lines


class SystemInfoPlugin(Plugin):
    name = "system_info"
    description = "Reports live CPU, RAM, battery, and disk usage."
    priority = 10

    def can_handle(self, text: str) -> bool:
        lowered = text.lower()
        return any(trigger in lowered for trigger in TRIGGERS)

    async def execute(self, text: str, ctx: PluginContext) -> str:
        if psutil is None:
            if re.search(r"[ऀ-ॿ]", text):
                return "psutil इंस्टॉल नहीं है — सिस्टम जानकारी के लिए `pip install psutil` चलाएँ."
            return "psutil isn't installed — run `pip install psutil` to enable system stats."
        lines = await asyncio.to_thread(_collect_stats)  # audit BL4: never block the loop
        return "\n".join(lines)
