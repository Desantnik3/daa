from __future__ import annotations

import csv
import random
from pathlib import Path
from statistics import median

from PIL import Image

try:
    import matplotlib.pyplot as plt
except Exception as exc:  # pragma: no cover - optional runtime dependency
    raise SystemExit("matplotlib is required to run this script") from exc


IMAGE_PATH = Path(__file__).with_name("Screenshot_105.png")
OUTPUT_CSV = Path(__file__).with_name("spectrum.csv")
OUTPUT_PNG = Path(__file__).with_name("spectrum.png")

FREQ_START_MHZ = 850
FREQ_STOP_MHZ = 2730
FREQ_STEP_MHZ = 5

BASELINE_DBM = -50.0
PEAK_DBM = 10.0
PEAK_RANGE_MHZ = (2520, 2680)

SUBTRACT_OUTSIDE_DBM = 20.0
RANDOM_SEED = 20260121
RANDOM_VARIATION = 0.02


def is_trace_pixel(r: int, g: int, b: int) -> bool:
    return g > r + 30 and g > b + 30 and g > 80


def extract_trace_y(image: Image.Image) -> tuple[dict[int, int], int, int]:
    rgb = image.convert("RGB")
    width, height = rgb.size
    pixels = rgb.load()

    coords: list[tuple[int, int]] = []
    for y in range(height):
        for x in range(width):
            r, g, b = pixels[x, y]
            if is_trace_pixel(r, g, b):
                coords.append((x, y))

    if not coords:
        raise SystemExit("No trace pixels detected. Adjust color thresholds.")

    ys_sorted = sorted(y for _, y in coords)
    y_lo = ys_sorted[int(len(ys_sorted) * 0.02)]
    y_hi = ys_sorted[int(len(ys_sorted) * 0.98)]

    trace: dict[int, list[int]] = {}
    for x, y in coords:
        if y_lo - 2 <= y <= y_hi + 2:
            trace.setdefault(x, []).append(y)

    if not trace:
        raise SystemExit("Trace extraction failed after filtering.")

    x_min = min(trace)
    x_max = max(trace)

    # Use the topmost pixel for the trace position.
    trace_top = {x: min(ys) for x, ys in trace.items()}

    # Fill gaps via linear interpolation.
    x_sorted = sorted(trace_top)
    filled: dict[int, int] = {}
    for idx in range(len(x_sorted) - 1):
        x0 = x_sorted[idx]
        x1 = x_sorted[idx + 1]
        y0 = trace_top[x0]
        y1 = trace_top[x1]
        span = x1 - x0
        if span == 0:
            filled[x0] = y0
            continue
        for x in range(x0, x1 + 1):
            t = (x - x0) / span
            y = round(y0 * (1 - t) + y1 * t)
            filled[x] = y

    filled[x_sorted[0]] = trace_top[x_sorted[0]]
    filled[x_sorted[-1]] = trace_top[x_sorted[-1]]
    return filled, x_min, x_max


def x_to_freq(x: int, x_min: int, x_max: int) -> float:
    return FREQ_START_MHZ + (x - x_min) * (FREQ_STOP_MHZ - FREQ_START_MHZ) / (
        x_max - x_min
    )


def freq_to_x(freq: float, x_min: int, x_max: int) -> int:
    return round(
        x_min
        + (freq - FREQ_START_MHZ) * (x_max - x_min) / (FREQ_STOP_MHZ - FREQ_START_MHZ)
    )


def estimate_scale(y_by_x: dict[int, int], x_min: int, x_max: int) -> tuple[float, float]:
    baseline_samples: list[int] = []
    peak_samples: list[int] = []
    for x, y in y_by_x.items():
        freq = x_to_freq(x, x_min, x_max)
        if PEAK_RANGE_MHZ[0] <= freq <= PEAK_RANGE_MHZ[1]:
            peak_samples.append(y)
        elif (1750 <= freq <= 1900) or (2050 <= freq <= 2150):
            continue
        else:
            baseline_samples.append(y)

    if not baseline_samples or not peak_samples:
        raise SystemExit("Insufficient samples to estimate scaling.")

    baseline_y = median(baseline_samples)
    peak_y = median(peak_samples)

    if peak_y == baseline_y:
        raise SystemExit("Invalid scale: peak and baseline y are identical.")

    slope = (PEAK_DBM - BASELINE_DBM) / (peak_y - baseline_y)
    intercept = BASELINE_DBM - slope * baseline_y
    return slope, intercept


def main() -> None:
    if not IMAGE_PATH.exists():
        raise SystemExit(f"Missing input image: {IMAGE_PATH}")

    image = Image.open(IMAGE_PATH)
    y_by_x, x_min, x_max = extract_trace_y(image)
    slope, intercept = estimate_scale(y_by_x, x_min, x_max)

    frequencies = list(range(FREQ_START_MHZ, FREQ_STOP_MHZ + 1, FREQ_STEP_MHZ))
    amplitudes: list[float] = []

    random.seed(RANDOM_SEED)
    for freq in frequencies:
        x = freq_to_x(freq, x_min, x_max)
        y = y_by_x.get(x, y_by_x[min(y_by_x, key=lambda k: abs(k - x))])
        amplitude = slope * y + intercept
        if not (PEAK_RANGE_MHZ[0] <= freq <= PEAK_RANGE_MHZ[1]):
            amplitude -= SUBTRACT_OUTSIDE_DBM
        amplitude *= 1.0 + random.uniform(-RANDOM_VARIATION, RANDOM_VARIATION)
        amplitudes.append(amplitude)

    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Frequency_MHz", "Amplitude_dBm"])
        for freq, amp in zip(frequencies, amplitudes):
            writer.writerow([freq, f"{amp:.3f}"])

    plt.figure(figsize=(10, 4))
    plt.plot(frequencies, amplitudes)
    plt.xlabel("Frequency (MHz)")
    plt.ylabel("Amplitude (dBm)")
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(OUTPUT_PNG, dpi=150)

    print(f"Wrote {OUTPUT_CSV} and {OUTPUT_PNG}")


if __name__ == "__main__":
    main()
