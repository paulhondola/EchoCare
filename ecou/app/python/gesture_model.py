"""The gesture model from Edge Impulse, when there is one (08-ecou.md §2.3, spike S15).

Trained on record.py's samples (2 s, 40 distances) and exported for Linux as an `.eim`
file at ECOU_MODEL (default: models/gestures.eim). Without the file, or without the
`edge_impulse_linux` package, or when the model is unsure, the rules in sensing.classify
decide, so Ecou works before the model does.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from sensing import classify, or_far

log = logging.getLogger("ecou.gestures")

SAMPLES = 40  # 2 seconds at 20 a second, as recorded
SURE = 0.7  # below this the rules decide


class GestureModel:
    def __init__(self, path: str | None = None) -> None:
        self.runner = None
        model = Path(path or os.environ.get("ECOU_MODEL", "models/gestures.eim"))
        if not model.exists():
            log.info("no gesture model at %s: using the rules", model)
            return
        try:
            from edge_impulse_linux.runner import ImpulseRunner

            model.chmod(0o755)
            runner = ImpulseRunner(str(model.resolve()))
            info = runner.init()
            self.runner = runner
            log.info("gesture model %s loaded", info.get("project", {}).get("name", model))
        except Exception:
            log.exception("gesture model not loaded: using the rules")

    def classify(self, window: list[float | None]) -> str:
        rules = classify(window)
        if self.runner is None or len(window) < SAMPLES // 2:
            return rules
        features = [or_far(d) for d in window[-SAMPLES:]]
        features += [features[-1]] * (SAMPLES - len(features))
        try:
            scores = self.runner.classify(features)["result"]["classification"]
        except Exception:
            log.exception("gesture model failed: using the rules")
            return rules
        label, score = max(scores.items(), key=lambda kv: kv[1])
        return label if score >= SURE else rules
