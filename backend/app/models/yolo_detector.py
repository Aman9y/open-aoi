"""YOLOComponentDetector — Ultralytics YOLO behind the ComponentDetector interface.

Optional. Nothing on the deterministic path imports this. It is loaded lazily
(and only if ``AOI_YOLO_MODEL_PATH`` points at a real file) so the core install
never needs PyTorch / Ultralytics. See ``backend/requirements-ml.txt``.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from ..logging_config import get_logger
from .component_detector import MODEL_NOT_CONFIGURED, ComponentDetector, Detection

log = get_logger(__name__)


class YOLOComponentDetector(ComponentDetector):
    def __init__(
        self,
        model_path: Path | str | None,
        confidence: float = 0.35,
        class_aliases: dict[str, str] | None = None,
    ) -> None:
        self._confidence = confidence
        self._aliases = {k.lower(): v for k, v in (class_aliases or {}).items()}
        self._model = None
        self._status = MODEL_NOT_CONFIGURED

        if not model_path or not Path(model_path).is_file():
            log.info("no YOLO model file at %r — component detection disabled", str(model_path))
            return
        try:
            from ultralytics import YOLO  # heavy; imported only when a model exists

            self._model = YOLO(str(model_path))
            self._status = "READY"
            log.info("YOLO model loaded: %s (classes: %s)", model_path,
                     list(getattr(self._model, "names", {}).values()))
        except Exception as exc:  # noqa: BLE001
            log.warning("could not load YOLO model (%s); staying disabled", exc)

    @property
    def status(self) -> str:
        return self._status

    def _canonical(self, label: str) -> str:
        return self._aliases.get(label.lower().strip(), label.lower().strip())

    def detect(self, image_bgr: np.ndarray) -> list[Detection]:
        if self._model is None:
            return []
        results = self._model.predict(image_bgr, conf=self._confidence, verbose=False)
        out: list[Detection] = []
        for r in results:
            names = r.names
            for box in r.boxes:
                x1, y1, x2, y2 = (int(v) for v in box.xyxy[0].tolist())
                out.append(
                    Detection(
                        label=self._canonical(names[int(box.cls[0])]),
                        confidence=float(box.conf[0]),
                        bbox=(x1, y1, x2, y2),
                    )
                )
        return out
