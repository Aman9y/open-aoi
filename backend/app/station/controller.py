"""Physical inspection-station state.

The backend does not talk to the ESP32 directly. The ESP32:

  * POSTs ``/api/station/trigger`` when its button / part-present sensor fires,
  * polls ``/api/station/state`` a few times a second and drives its outputs
    (green / red / amber LED, servo reject gate, buzzer) from ``verdict`` +
    ``counter`` (a monotonically increasing id — act only when it changes).

Every inspection (station-triggered, dashboard upload, live camera) updates this
state when the station is enabled, so the lamp stack always reflects the last
result regardless of how it was started.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from ..config import Settings, get_settings
from ..logging_config import get_logger
from ..schemas.inspection import InspectionResult, MultiViewResult

log = get_logger(__name__)


@dataclass
class StationState:
    enabled: bool
    counter: int = 0                 # bumps on every recorded inspection
    verdict: str = "IDLE"            # GOOD | DEFECTIVE | REVIEW | IDLE
    reason: str = ""
    defect_count: int = 0
    reject: bool = False             # ESP32 should actuate the reject gate
    inspection_id: str = ""
    timestamp: str = ""
    view_count: int = 1
    source: str = ""
    esp32_online: bool = False
    esp32_last_seen_s_ago: float | None = None


@dataclass
class StationController:
    _cfg: Settings
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _counter: int = 0
    _last: InspectionResult | MultiViewResult | None = None
    _esp32_last_poll: float = 0.0

    @property
    def enabled(self) -> bool:
        return self._cfg.station_enabled

    @property
    def source(self) -> str:
        return self._cfg.station_source

    @property
    def reference_id(self) -> str | None:
        return self._cfg.station_reference_id

    def record(self, result: InspectionResult | MultiViewResult) -> None:
        """Called after any inspection completes (when the station is enabled)."""
        with self._lock:
            self._counter += 1
            self._last = result
        log.info("station: verdict #%d -> %s", self._counter, result.status.value)

    def note_esp32_poll(self) -> None:
        self._esp32_last_poll = time.monotonic()

    def state(self) -> StationState:
        with self._lock:
            last = self._last
            counter = self._counter
        online_gap = time.monotonic() - self._esp32_last_poll if self._esp32_last_poll else None
        online = online_gap is not None and online_gap <= self._cfg.station_esp32_offline_after_s

        views = self._cfg.station_views
        source_label = f"{len(views)} cameras" if views else self.source
        st = StationState(
            enabled=self.enabled,
            counter=counter,
            source=source_label,
            esp32_online=online,
            esp32_last_seen_s_ago=round(online_gap, 1) if online_gap is not None else None,
        )
        if last is not None:
            st.verdict = last.status.value
            st.reason = last.reason.value
            st.defect_count = len(last.defects)
            st.reject = last.status.value in self._cfg.station_reject_statuses
            st.inspection_id = last.inspection_id
            st.timestamp = last.timestamp
            st.view_count = getattr(last, "view_count", 1)
        return st


_STATION: StationController | None = None


def get_station() -> StationController:
    global _STATION
    if _STATION is None:
        _STATION = StationController(_cfg=get_settings())
    return _STATION
