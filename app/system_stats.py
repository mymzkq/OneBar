from __future__ import annotations

import time
from dataclasses import dataclass

try:
    import psutil
except Exception:  # pragma: no cover - defensive fallback for missing optional dependency.
    psutil = None


DOWN_ARROW = "\u2193"
UP_ARROW = "\u2191"


@dataclass
class StatsSnapshot:
    cpu_text: str | None = None
    memory_text: str | None = None
    network_text: str | None = None


class SystemStatsSampler:
    def __init__(self) -> None:
        self._last_net = None
        self._last_net_time = None
        if psutil is not None:
            try:
                psutil.cpu_percent(interval=None)
            except Exception:
                pass

    def sample(self, show_cpu: bool, show_memory: bool, show_network: bool) -> StatsSnapshot:
        snapshot = StatsSnapshot()
        if psutil is None:
            if show_cpu:
                snapshot.cpu_text = "CPU --"
            if show_memory:
                snapshot.memory_text = "RAM --"
            if show_network:
                snapshot.network_text = f"{DOWN_ARROW} -- {UP_ARROW} --"
            return snapshot

        if show_cpu:
            snapshot.cpu_text = self._sample_cpu()
        if show_memory:
            snapshot.memory_text = self._sample_memory()
        if show_network:
            snapshot.network_text = self._sample_network()
        else:
            self._last_net = None
            self._last_net_time = None
        return snapshot

    @staticmethod
    def _sample_cpu() -> str:
        try:
            return f"CPU {round(psutil.cpu_percent(interval=None))}%"
        except Exception:
            return "CPU --"

    @staticmethod
    def _sample_memory() -> str:
        try:
            return f"RAM {round(psutil.virtual_memory().percent)}%"
        except Exception:
            return "RAM --"

    def _sample_network(self) -> str:
        try:
            counters = psutil.net_io_counters()
            now = time.monotonic()
            if self._last_net is None or self._last_net_time is None:
                self._last_net = counters
                self._last_net_time = now
                return f"{DOWN_ARROW} 0B/s {UP_ARROW} 0B/s"

            elapsed = max(0.001, now - self._last_net_time)
            down = max(0, counters.bytes_recv - self._last_net.bytes_recv) / elapsed
            up = max(0, counters.bytes_sent - self._last_net.bytes_sent) / elapsed
            self._last_net = counters
            self._last_net_time = now
            return f"{DOWN_ARROW} {format_speed(down)} {UP_ARROW} {format_speed(up)}"
        except Exception:
            return f"{DOWN_ARROW} -- {UP_ARROW} --"


def format_speed(bytes_per_second: float) -> str:
    if bytes_per_second >= 1024 * 1024:
        return f"{bytes_per_second / (1024 * 1024):.1f}MB/s"
    if bytes_per_second >= 1024:
        return f"{bytes_per_second / 1024:.0f}KB/s"
    return f"{round(bytes_per_second)}B/s"
