from __future__ import annotations

import csv
import math
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
MID_PEAK_DBM = -34.0
PEAK_DBM = 10.0
MID_PEAK_RANGES_MHZ = ((1800, 1860), (2080, 2140))
PEAK_SAMPLE_RANGE_MHZ = (2620, 2690)
UL_MID_RANGES_MHZ = ((1710, 1785), (1920, 1980))
UL_MAIN_RANGE_MHZ = (2500, 2570)
DL_RANGES_MHZ = ((1805, 1880), (2110, 2170), (2620, 2690))
SUPPRESS_RANGES_MHZ = ((2090, 2230), (2600, 2730))
PEAK_MAX_ABOVE_FLOOR_DB = 75.0
UL_MAIN_BASE_OFFSET_DB = 70.0
UL_MAIN_EDGE_EXTRA_DB = 5.0
UL_MID_EDGE_EXTRA_DB = 4.0
UL_MID_DIFF_RANGE_DB = (3.0, 5.0)
NOISE_JITTER_DB = 2.8
NOISE_RIPPLE_DB = 0.8

SUBTRACT_OUTSIDE_DBM = 20.0
RANDOM_SEED = 20260121
RANDOM_VARIATION = 0.02

MARKERS = [
    (1, 890.0),
    (2, 935.0),
    (3, 1735.0),
    (4, 1835.0),
    (5, 1960.0),
    (6, 2110.0),
    (7, 2540.0),
    (8, 2660.0),
    (9, 2712.6),
]


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
    mid_samples: list[int] = []
    peak_samples: list[int] = []
    for x, y in y_by_x.items():
        freq = x_to_freq(x, x_min, x_max)
        if PEAK_SAMPLE_RANGE_MHZ[0] <= freq <= PEAK_SAMPLE_RANGE_MHZ[1]:
            peak_samples.append(y)
        elif any(start <= freq <= end for start, end in MID_PEAK_RANGES_MHZ):
            mid_samples.append(y)
        else:
            baseline_samples.append(y)

    if not baseline_samples:
        raise SystemExit("Insufficient samples to estimate scaling.")

    baseline_y = median(baseline_samples)
    if mid_samples:
        mid_y = median(mid_samples)
        if mid_y == baseline_y:
            raise SystemExit("Invalid scale: mid-peak and baseline y are identical.")
        slope = (MID_PEAK_DBM - BASELINE_DBM) / (mid_y - baseline_y)
        intercept = BASELINE_DBM - slope * baseline_y
        return slope, intercept

    if not peak_samples:
        raise SystemExit("Insufficient samples to estimate scaling.")

    peak_y = median(peak_samples)
    if peak_y == baseline_y:
        raise SystemExit("Invalid scale: peak and baseline y are identical.")

    slope = (PEAK_DBM - BASELINE_DBM) / (peak_y - baseline_y)
    intercept = BASELINE_DBM - slope * baseline_y
    return slope, intercept


def in_ranges(freq: float, ranges: tuple[tuple[float, float], ...]) -> bool:
    return any(start <= freq <= end for start, end in ranges)


def in_range(freq: float, band: tuple[float, float]) -> bool:
    return band[0] <= freq <= band[1]


def stable_jitter(freq: float, scale: float, seed_offset: int) -> float:
    rng = random.Random(RANDOM_SEED + seed_offset + int(freq * 10))
    return rng.uniform(-scale, scale)


def ul_main_offset(freq: float) -> float:
    left, right = UL_MAIN_RANGE_MHZ
    width = right - left
    t = (freq - left) / width
    edge = 0.5 - 0.5 * math.cos(math.pi * t)
    offset = UL_MAIN_BASE_OFFSET_DB + UL_MAIN_EDGE_EXTRA_DB * edge
    offset += 1.4 * math.sin(freq * 0.15) + 0.9 * math.sin(freq * 0.47)
    offset += stable_jitter(freq, 2.0, 9001) * (0.3 + 0.7 * edge)
    return offset


def ul_mid_delta(band: tuple[float, float]) -> float:
    seed = RANDOM_SEED + int(band[0] * 10)
    rng = random.Random(seed)
    return rng.uniform(*UL_MID_DIFF_RANGE_DB)


def ul_mid_offset(freq: float, band: tuple[float, float]) -> float:
    left, right = band
    width = right - left
    t = (freq - left) / width
    edge = 0.5 - 0.5 * math.cos(math.pi * t)
    delta = ul_mid_delta(band)
    offset = (UL_MAIN_BASE_OFFSET_DB - delta) + UL_MID_EDGE_EXTRA_DB * edge
    offset += 1.1 * math.sin(freq * 0.2) + 0.7 * math.sin(freq * 0.53)
    offset += stable_jitter(freq, 1.6, 7001) * (0.35 + 0.65 * edge)
    return offset


def dl_floor_value(freq: float, floor: float) -> float:
    return floor + stable_jitter(freq, 1.2, 5001)


def noise_floor_variation(freq: float) -> float:
    jitter = stable_jitter(freq, NOISE_JITTER_DB, 3001)
    ripple = NOISE_RIPPLE_DB * math.sin(freq * 0.12) + 0.5 * math.sin(freq * 0.37 + 1.3)
    return jitter + ripple


def amplitude_at(freq: float, frequencies: list[int], amplitudes: list[float]) -> float:
    lookup = dict(zip(frequencies, amplitudes))
    if freq in lookup:
        return lookup[freq]

    if freq < frequencies[0] or freq > frequencies[-1]:
        raise ValueError("Frequency out of range.")

    lower = int((freq - FREQ_START_MHZ) // FREQ_STEP_MHZ) * FREQ_STEP_MHZ + FREQ_START_MHZ
    upper = min(lower + FREQ_STEP_MHZ, FREQ_STOP_MHZ)
    if lower == upper:
        return lookup[lower]

    a0 = lookup[lower]
    a1 = lookup[upper]
    t = (freq - lower) / (upper - lower)
    return a0 + (a1 - a0) * t


def main() -> None:
    if not IMAGE_PATH.exists():
        raise SystemExit(f"Missing input image: {IMAGE_PATH}")

    image = Image.open(IMAGE_PATH)
    y_by_x, x_min, x_max = extract_trace_y(image)
    slope, intercept = estimate_scale(y_by_x, x_min, x_max)

    frequencies = list(range(FREQ_START_MHZ, FREQ_STOP_MHZ + 1, FREQ_STEP_MHZ))
    base_amplitudes: list[float] = []
    for freq in frequencies:
        x = freq_to_x(freq, x_min, x_max)
        y = y_by_x.get(x, y_by_x[min(y_by_x, key=lambda k: abs(k - x))])
        amplitude = slope * y + intercept
        amplitude -= SUBTRACT_OUTSIDE_DBM
        base_amplitudes.append(amplitude)

    floor_samples = [
        amp
        for freq, amp in zip(frequencies, base_amplitudes)
        if not in_range(freq, UL_MAIN_RANGE_MHZ)
        and not in_ranges(freq, UL_MID_RANGES_MHZ)
        and not in_ranges(freq, DL_RANGES_MHZ)
        and not in_ranges(freq, SUPPRESS_RANGES_MHZ)
    ]
    floor_level = median(floor_samples) if floor_samples else median(base_amplitudes)

    amplitudes: list[float] = []
    random.seed(RANDOM_SEED)
    for freq, base_amp in zip(frequencies, base_amplitudes):
        if in_range(freq, UL_MAIN_RANGE_MHZ):
            amplitude = floor_level + ul_main_offset(freq)
        elif in_ranges(freq, UL_MID_RANGES_MHZ):
            band = next(b for b in UL_MID_RANGES_MHZ if in_range(freq, b))
            amplitude = floor_level + ul_mid_offset(freq, band)
        elif in_ranges(freq, SUPPRESS_RANGES_MHZ):
            amplitude = dl_floor_value(freq, floor_level)
        elif in_ranges(freq, DL_RANGES_MHZ):
            amplitude = dl_floor_value(freq, floor_level)
        else:
            amplitude = base_amp + noise_floor_variation(freq)
        amplitude *= 1.0 + random.uniform(-RANDOM_VARIATION, RANDOM_VARIATION)
        amplitudes.append(amplitude)

    band_indices = [
        idx
        for idx, freq in enumerate(frequencies)
        if in_range(freq, UL_MAIN_RANGE_MHZ)
    ]
    if band_indices:
        band_max = max(amplitudes[idx] for idx in band_indices)
        desired_max = floor_level + PEAK_MAX_ABOVE_FLOOR_DB
        if band_max > desired_max:
            delta = band_max - desired_max
            for idx in band_indices:
                amplitudes[idx] -= delta

    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Frequency_MHz", "Amplitude_dBm"])
        for freq, amp in zip(frequencies, amplitudes):
            writer.writerow([freq, f"{amp:.3f}"])

    marker_values = []
    for marker_id, marker_freq in MARKERS:
        marker_amp = amplitude_at(marker_freq, frequencies, amplitudes)
        marker_values.append((marker_id, marker_freq, marker_amp))

    fig, (ax, ax_text) = plt.subplots(
        2, 1, figsize=(10, 4.8), gridspec_kw={"height_ratios": [4, 1]}
    )
    ax.plot(frequencies, amplitudes)
    ax.plot(
        [freq for _, freq, _ in marker_values],
        [amp for _, _, amp in marker_values],
        linestyle="None",
        marker="o",
        color="black",
        markersize=4,
    )
    for marker_id, marker_freq, marker_amp in marker_values:
        ax.annotate(
            str(marker_id),
            (marker_freq, marker_amp),
            textcoords="offset points",
            xytext=(0, 4),
            ha="center",
            va="bottom",
            fontsize=7,
            color="black",
        )
    ax.set_xlabel("Frequency (MHz)")
    ax.set_ylabel("Amplitude (dBm)")
    ax.grid(True)

    ax_text.axis("off")
    formatted = {
        marker_id: f"Marker {marker_id}: {freq:.4f} MHz, {amp:.1f} dBm"
        for marker_id, freq, amp in marker_values
    }
    columns = ([1, 4, 7], [2, 5, 8], [3, 6, 9])
    column_width = 42
    lines = []
    for row_idx in range(max(len(col) for col in columns)):
        parts = []
        for col in columns:
            if row_idx < len(col):
                parts.append(formatted[col[row_idx]].ljust(column_width))
            else:
                parts.append("".ljust(column_width))
        lines.append("".join(parts).rstrip())

    ax_text.text(
        0.01,
        0.9,
        "\n".join(lines),
        va="top",
        ha="left",
        family="monospace",
        fontsize=8,
    )

    fig.tight_layout()
    fig.savefig(OUTPUT_PNG, dpi=150)

    print(f"Wrote {OUTPUT_CSV} and {OUTPUT_PNG}")


if __name__ == "__main__":
    main()
