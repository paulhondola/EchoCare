"""Records gesture samples for the model (08-ecou.md §2.3, spike S15).

Each sample is 2 seconds of distances straight ahead at 20 a second, one row in
`gestures.csv` under ECOU_DATA (default: ./data): `label,d0,…,d39`, in metres, 4.0 for
no echo. Upload the file to Edge Impulse with its CSV Wizard, one row per sample.

The display shows which class is being recorded (1 wave, 2 palm, 3 pass, 4 none) and
the samples left; the matrix counts down before each one.
"""

from __future__ import annotations

import csv
import os
import time
from pathlib import Path

from body import Body
from sensing import or_far

LABELS = ("wave", "palm", "pass", "none")
PER_LABEL = int(os.environ.get("ECOU_SAMPLES", "20"))
SAMPLE_S = 2.0
HOW = {
    "wave": "wave a hand 10–40 cm in front of the eyes",
    "palm": "hold a palm still 10–40 cm in front of the eyes",
    "pass": "walk past in front of Ecou, once",
    "none": "nothing in front; move around further back",
}


def run(body: Body) -> None:
    out = Path(os.environ.get("ECOU_DATA", "data")) / "gestures.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    new = not out.exists()
    body.look(90, 90)
    with out.open("a", newline="") as f:
        rows = csv.writer(f)
        if new:
            rows.writerow(["label", *[f"d{i}" for i in range(int(SAMPLE_S * 20))]])
        for n, label in enumerate(LABELS, start=1):
            print(f"[record] {label}: {HOW[label]}, {PER_LABEL} times", flush=True)
            for left in range(PER_LABEL, 0, -1):
                body.show_number(n * 1000 + left)
                for count in (3, 2, 1):
                    body.face("yellow" if count > 1 else "green")
                    time.sleep(0.5)
                window = body.stream(SAMPLE_S)
                values = [round(or_far(d), 3) for d in window][: int(SAMPLE_S * 20)]
                values += [4.0] * (int(SAMPLE_S * 20) - len(values))
                rows.writerow([label, *values])
                f.flush()
                time.sleep(0.5)
    body.blank()
    print(f"[record] done: {out}", flush=True)
