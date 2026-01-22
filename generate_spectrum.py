from __future__ import annotations

import argparse
import csv
import json
import math
import random
from copy import deepcopy
from pathlib import Path
from statistics import median

from PIL import Image

try:
    from matplotlib.figure import Figure
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
TRACE_GREEN_MIN = 80
TRACE_GREEN_DELTA = 30
RANGE_RULES: list[dict] = []

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

DEFAULT_CONFIG = {
    "freq_start_mhz": FREQ_START_MHZ,
    "freq_stop_mhz": FREQ_STOP_MHZ,
    "freq_step_mhz": FREQ_STEP_MHZ,
    "baseline_dbm": BASELINE_DBM,
    "mid_peak_dbm": MID_PEAK_DBM,
    "peak_dbm": PEAK_DBM,
    "mid_peak_ranges_mhz": [list(r) for r in MID_PEAK_RANGES_MHZ],
    "peak_sample_range_mhz": list(PEAK_SAMPLE_RANGE_MHZ),
    "ul_mid_ranges_mhz": [list(r) for r in UL_MID_RANGES_MHZ],
    "ul_main_range_mhz": list(UL_MAIN_RANGE_MHZ),
    "dl_ranges_mhz": [list(r) for r in DL_RANGES_MHZ],
    "suppress_ranges_mhz": [list(r) for r in SUPPRESS_RANGES_MHZ],
    "peak_max_above_floor_db": PEAK_MAX_ABOVE_FLOOR_DB,
    "ul_main_base_offset_db": UL_MAIN_BASE_OFFSET_DB,
    "ul_main_edge_extra_db": UL_MAIN_EDGE_EXTRA_DB,
    "ul_mid_edge_extra_db": UL_MID_EDGE_EXTRA_DB,
    "ul_mid_diff_range_db": list(UL_MID_DIFF_RANGE_DB),
    "noise_jitter_db": NOISE_JITTER_DB,
    "noise_ripple_db": NOISE_RIPPLE_DB,
    "trace_green_min": TRACE_GREEN_MIN,
    "trace_green_delta": TRACE_GREEN_DELTA,
    "range_rules": [
        {
            "label": "UL 1800",
            "start_mhz": 1710,
            "end_mhz": 1785,
            "mode": "raise",
            "target_db": 70.0,
            "edge_extra_db": 4.0,
            "jitter_db": 1.6,
            "cap_above_floor_db": 75.0
        },
        {
            "label": "DL 1800",
            "start_mhz": 1805,
            "end_mhz": 1880,
            "mode": "lower"
        },
        {
            "label": "UL 2100",
            "start_mhz": 1920,
            "end_mhz": 1980,
            "mode": "raise",
            "target_db": 70.0,
            "edge_extra_db": 4.0,
            "jitter_db": 1.6,
            "cap_above_floor_db": 75.0
        },
        {
            "label": "DL 2100",
            "start_mhz": 2110,
            "end_mhz": 2170,
            "mode": "lower"
        },
        {
            "label": "UL 2600",
            "start_mhz": 2500,
            "end_mhz": 2570,
            "mode": "raise",
            "target_db": 70.0,
            "edge_extra_db": 5.0,
            "jitter_db": 2.0,
            "cap_above_floor_db": 75.0
        },
        {
            "label": "DL 2600",
            "start_mhz": 2620,
            "end_mhz": 2690,
            "mode": "lower"
        }
    ],
    "subtract_outside_dbm": SUBTRACT_OUTSIDE_DBM,
    "random_seed": RANDOM_SEED,
    "random_variation": RANDOM_VARIATION,
    "markers": [
        {"id": marker_id, "freq_mhz": freq} for marker_id, freq in MARKERS
    ],
    "plot": {
        "figure_size": [10, 4.8],
        "dpi": 150,
        "marker_color": "black",
        "marker_size": 4,
        "marker_label_size": 7,
        "footer_column_width": 42,
        "footer_font_size": 8,
        "footer_columns": 3,
        "grid": True,
    },
}


def normalize_range(band: list[float] | tuple[float, float]) -> tuple[float, float]:
    return (float(band[0]), float(band[1]))


def normalize_ranges(ranges: list[list[float]]) -> tuple[tuple[float, float], ...]:
    return tuple(normalize_range(band) for band in ranges)


def normalize_markers(markers: list[object]) -> list[tuple[int, float]]:
    normalized: list[tuple[int, float]] = []
    for item in markers:
        if isinstance(item, dict):
            marker_id = int(item.get("id", 0))
            freq = float(item.get("freq_mhz", 0.0))
        else:
            marker_id, freq = item
            marker_id = int(marker_id)
            freq = float(freq)
        normalized.append((marker_id, freq))
    return normalized


def normalize_range_rules(rules: list[dict]) -> list[dict]:
    normalized: list[dict] = []
    for idx, rule in enumerate(rules):
        label = str(rule.get("label", f"Rule {idx + 1}"))
        start = float(rule.get("start_mhz", rule.get("start", 0.0)))
        end = float(rule.get("end_mhz", rule.get("end", 0.0)))
        mode = str(rule.get("mode", "")).strip().lower()
        if mode not in ("raise", "lower"):
            raise ValueError(f"Неверный режим правила: {mode}")
        normalized_rule = {
            "label": label,
            "start_mhz": start,
            "end_mhz": end,
            "mode": mode,
        }
        if mode == "raise":
            if "target_db" not in rule:
                raise ValueError(f"Для правила '{label}' нужен target_db")
            normalized_rule["target_db"] = float(rule.get("target_db", 0.0))
            normalized_rule["edge_extra_db"] = float(rule.get("edge_extra_db", 0.0))
            normalized_rule["jitter_db"] = float(rule.get("jitter_db", 1.6))
            if "cap_above_floor_db" in rule:
                normalized_rule["cap_above_floor_db"] = float(
                    rule.get("cap_above_floor_db")
                )
        normalized.append(normalized_rule)
    return normalized


def load_config(path: str | None) -> dict:
    config = deepcopy(DEFAULT_CONFIG)
    if not path:
        return config

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    plot_data = data.pop("plot", None)
    config.update(data)
    if plot_data:
        config["plot"].update(plot_data)
    return config


def apply_config(config: dict) -> None:
    global FREQ_START_MHZ
    global FREQ_STOP_MHZ
    global FREQ_STEP_MHZ
    global BASELINE_DBM
    global MID_PEAK_DBM
    global PEAK_DBM
    global MID_PEAK_RANGES_MHZ
    global PEAK_SAMPLE_RANGE_MHZ
    global UL_MID_RANGES_MHZ
    global UL_MAIN_RANGE_MHZ
    global DL_RANGES_MHZ
    global SUPPRESS_RANGES_MHZ
    global PEAK_MAX_ABOVE_FLOOR_DB
    global UL_MAIN_BASE_OFFSET_DB
    global UL_MAIN_EDGE_EXTRA_DB
    global UL_MID_EDGE_EXTRA_DB
    global UL_MID_DIFF_RANGE_DB
    global NOISE_JITTER_DB
    global NOISE_RIPPLE_DB
    global TRACE_GREEN_MIN
    global TRACE_GREEN_DELTA
    global RANGE_RULES
    global SUBTRACT_OUTSIDE_DBM
    global RANDOM_SEED
    global RANDOM_VARIATION
    global MARKERS

    FREQ_START_MHZ = int(config["freq_start_mhz"])
    FREQ_STOP_MHZ = int(config["freq_stop_mhz"])
    FREQ_STEP_MHZ = int(config["freq_step_mhz"])
    BASELINE_DBM = float(config["baseline_dbm"])
    MID_PEAK_DBM = float(config["mid_peak_dbm"])
    PEAK_DBM = float(config["peak_dbm"])
    MID_PEAK_RANGES_MHZ = normalize_ranges(config["mid_peak_ranges_mhz"])
    PEAK_SAMPLE_RANGE_MHZ = normalize_range(config["peak_sample_range_mhz"])
    UL_MID_RANGES_MHZ = normalize_ranges(config["ul_mid_ranges_mhz"])
    UL_MAIN_RANGE_MHZ = normalize_range(config["ul_main_range_mhz"])
    DL_RANGES_MHZ = normalize_ranges(config["dl_ranges_mhz"])
    SUPPRESS_RANGES_MHZ = normalize_ranges(config["suppress_ranges_mhz"])
    PEAK_MAX_ABOVE_FLOOR_DB = float(config["peak_max_above_floor_db"])
    UL_MAIN_BASE_OFFSET_DB = float(config["ul_main_base_offset_db"])
    UL_MAIN_EDGE_EXTRA_DB = float(config["ul_main_edge_extra_db"])
    UL_MID_EDGE_EXTRA_DB = float(config["ul_mid_edge_extra_db"])
    UL_MID_DIFF_RANGE_DB = tuple(float(v) for v in config["ul_mid_diff_range_db"])
    NOISE_JITTER_DB = float(config["noise_jitter_db"])
    NOISE_RIPPLE_DB = float(config["noise_ripple_db"])
    TRACE_GREEN_MIN = int(config["trace_green_min"])
    TRACE_GREEN_DELTA = int(config["trace_green_delta"])
    SUBTRACT_OUTSIDE_DBM = float(config["subtract_outside_dbm"])
    RANDOM_SEED = int(config["random_seed"])
    RANDOM_VARIATION = float(config["random_variation"])
    MARKERS = normalize_markers(config["markers"])
    range_rules = config.get("range_rules", [])
    RANGE_RULES = normalize_range_rules(range_rules) if range_rules else []


def write_default_config(path: str) -> None:
    Path(path).write_text(json.dumps(DEFAULT_CONFIG, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate spectrum data and plot from a screenshot."
    )
    parser.add_argument("--config", help="Path to JSON config file.")
    parser.add_argument(
        "--write-config",
        help="Write default config JSON to path and exit.",
    )
    parser.add_argument(
        "--image",
        default=str(IMAGE_PATH),
        help="Path to input screenshot image.",
    )
    parser.add_argument(
        "--output-csv",
        default=str(OUTPUT_CSV),
        help="Path to output CSV file.",
    )
    parser.add_argument(
        "--output-png",
        default=str(OUTPUT_PNG),
        help="Path to output PNG plot.",
    )
    return parser.parse_args()


def is_trace_pixel(r: int, g: int, b: int) -> bool:
    return (
        g > r + TRACE_GREEN_DELTA
        and g > b + TRACE_GREEN_DELTA
        and g > TRACE_GREEN_MIN
    )


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
        raise ValueError("Линия трассы не найдена. Проверьте пороги цвета.")

    ys_sorted = sorted(y for _, y in coords)
    y_lo = ys_sorted[int(len(ys_sorted) * 0.02)]
    y_hi = ys_sorted[int(len(ys_sorted) * 0.98)]

    trace: dict[int, list[int]] = {}
    for x, y in coords:
        if y_lo - 2 <= y <= y_hi + 2:
            trace.setdefault(x, []).append(y)

    if not trace:
        raise ValueError("Не удалось выделить трассу после фильтрации.")

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
        raise ValueError("Недостаточно данных для оценки масштаба.")

    baseline_y = median(baseline_samples)
    if mid_samples:
        mid_y = median(mid_samples)
        if mid_y == baseline_y:
            raise ValueError("Ошибка масштаба: mid-peak совпадает с базой.")
        slope = (MID_PEAK_DBM - BASELINE_DBM) / (mid_y - baseline_y)
        intercept = BASELINE_DBM - slope * baseline_y
        return slope, intercept

    if not peak_samples:
        raise ValueError("Недостаточно данных для оценки масштаба.")

    peak_y = median(peak_samples)
    if peak_y == baseline_y:
        raise ValueError("Ошибка масштаба: peak совпадает с базой.")

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


def build_frequencies(start: int, stop: int, step: int) -> list[int]:
    if step <= 0:
        raise ValueError("Шаг частоты должен быть больше нуля.")
    if start > stop:
        raise ValueError("Начальная частота должна быть меньше конечной.")
    freqs = list(range(start, stop + 1, step))
    if not freqs:
        freqs = [start]
    if freqs[-1] != stop:
        freqs.append(stop)
    return freqs


def rule_seed(rule: dict) -> int:
    return int(rule["start_mhz"] * 10 + rule["end_mhz"] * 10) % 10000


def band_raise_offset(freq: float, rule: dict) -> float:
    left = rule["start_mhz"]
    right = rule["end_mhz"]
    width = right - left
    t = (freq - left) / width if width else 0.0
    edge = 0.5 - 0.5 * math.cos(math.pi * t)
    offset = float(rule["target_db"]) + float(rule.get("edge_extra_db", 0.0)) * edge
    offset += 1.1 * math.sin(freq * 0.2) + 0.7 * math.sin(freq * 0.53)
    jitter_db = float(rule.get("jitter_db", 1.6))
    offset += stable_jitter(freq, jitter_db, 11000 + rule_seed(rule)) * (
        0.35 + 0.65 * edge
    )
    return offset


def find_rule(freq: float) -> dict | None:
    for rule in RANGE_RULES:
        if rule["start_mhz"] <= freq <= rule["end_mhz"]:
            return rule
    return None


def generate_series(
    image_path: Path, config: dict
) -> tuple[list[int], list[float], list[tuple[int, float, float]], dict]:
    apply_config(config)
    plot_config = config["plot"]

    if not image_path.exists():
        raise FileNotFoundError(f"Не найден файл изображения: {image_path}")

    image = Image.open(image_path)
    y_by_x, x_min, x_max = extract_trace_y(image)
    slope, intercept = estimate_scale(y_by_x, x_min, x_max)

    frequencies = build_frequencies(FREQ_START_MHZ, FREQ_STOP_MHZ, FREQ_STEP_MHZ)
    base_amplitudes: list[float] = []
    for freq in frequencies:
        x = freq_to_x(freq, x_min, x_max)
        y = y_by_x.get(x, y_by_x[min(y_by_x, key=lambda k: abs(k - x))])
        amplitude = slope * y + intercept
        amplitude -= SUBTRACT_OUTSIDE_DBM
        base_amplitudes.append(amplitude)

    if RANGE_RULES:
        active_ranges = tuple(
            (rule["start_mhz"], rule["end_mhz"]) for rule in RANGE_RULES
        )
        floor_samples = [
            amp
            for freq, amp in zip(frequencies, base_amplitudes)
            if not in_ranges(freq, active_ranges)
        ]
    else:
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
        if RANGE_RULES:
            rule = find_rule(freq)
            if rule:
                if rule["mode"] == "raise":
                    amplitude = floor_level + band_raise_offset(freq, rule)
                else:
                    amplitude = floor_level + noise_floor_variation(freq)
            else:
                amplitude = base_amp + noise_floor_variation(freq)
        else:
            if in_ranges(freq, SUPPRESS_RANGES_MHZ):
                amplitude = dl_floor_value(freq, floor_level)
            elif in_range(freq, UL_MAIN_RANGE_MHZ):
                amplitude = floor_level + ul_main_offset(freq)
            elif in_ranges(freq, UL_MID_RANGES_MHZ):
                band = next(b for b in UL_MID_RANGES_MHZ if in_range(freq, b))
                amplitude = floor_level + ul_mid_offset(freq, band)
            elif in_ranges(freq, DL_RANGES_MHZ):
                amplitude = dl_floor_value(freq, floor_level)
            else:
                amplitude = base_amp + noise_floor_variation(freq)
        amplitude *= 1.0 + random.uniform(-RANDOM_VARIATION, RANDOM_VARIATION)
        amplitudes.append(amplitude)

    if RANGE_RULES:
        for rule in RANGE_RULES:
            if rule["mode"] != "raise":
                continue
            indices = [
                idx
                for idx, freq in enumerate(frequencies)
                if rule["start_mhz"] <= freq <= rule["end_mhz"]
            ]
            if not indices:
                continue
            band_max = max(amplitudes[idx] for idx in indices)
            cap = float(rule.get("cap_above_floor_db", PEAK_MAX_ABOVE_FLOOR_DB))
            desired_max = floor_level + cap
            if band_max > desired_max:
                delta = band_max - desired_max
                for idx in indices:
                    amplitudes[idx] -= delta
    else:
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

    marker_values = []
    for marker_id, marker_freq in MARKERS:
        marker_amp = amplitude_at(marker_freq, frequencies, amplitudes)
        marker_values.append((marker_id, marker_freq, marker_amp))

    return frequencies, amplitudes, marker_values, plot_config


def create_plot(
    frequencies: list[int],
    amplitudes: list[float],
    marker_values: list[tuple[int, float, float]],
    plot_config: dict,
) -> Figure:
    fig = Figure(
        figsize=tuple(plot_config.get("figure_size", [10, 4.8])),
        dpi=int(plot_config.get("dpi", 150)),
    )
    ax, ax_text = fig.subplots(2, 1, gridspec_kw={"height_ratios": [4, 1]})
    ax.plot(frequencies, amplitudes)
    marker_color = plot_config.get("marker_color", "black")
    marker_size = plot_config.get("marker_size", 4)
    marker_label_size = plot_config.get("marker_label_size", 7)
    if marker_values:
        ax.plot(
            [freq for _, freq, _ in marker_values],
            [amp for _, _, amp in marker_values],
            linestyle="None",
            marker="o",
            color=marker_color,
            markersize=marker_size,
        )
        for marker_id, marker_freq, marker_amp in marker_values:
            ax.annotate(
                str(marker_id),
                (marker_freq, marker_amp),
                textcoords="offset points",
                xytext=(0, 4),
                ha="center",
                va="bottom",
                fontsize=marker_label_size,
                color=marker_color,
            )
    ax.set_xlabel("Frequency (MHz)")
    ax.set_ylabel("Amplitude (dBm)")
    ax.grid(bool(plot_config.get("grid", True)))
    if frequencies:
        ax.set_xlim(frequencies[0], frequencies[-1])
        ax.margins(x=0)

    ax_text.axis("off")
    if marker_values:
        formatted = {
            marker_id: f"Marker {marker_id}: {freq:.4f} MHz, {amp:.1f} dBm"
            for marker_id, freq, amp in marker_values
        }
        columns_count = max(1, int(plot_config.get("footer_columns", 3)))
        rows = math.ceil(len(marker_values) / columns_count)
        columns: list[list[int]] = [[] for _ in range(columns_count)]
        for row in range(rows):
            for col in range(columns_count):
                idx = row * columns_count + col
                if idx < len(marker_values):
                    columns[col].append(marker_values[idx][0])

        column_width = int(plot_config.get("footer_column_width", 42))
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
            fontsize=plot_config.get("footer_font_size", 8),
        )

    fig.tight_layout()
    return fig


def generate_outputs(
    image_path: Path,
    output_csv: Path | None,
    output_png: Path,
    config: dict,
) -> None:
    frequencies, amplitudes, marker_values, plot_config = generate_series(
        image_path, config
    )

    if output_csv is not None:
        output_csv.parent.mkdir(parents=True, exist_ok=True)
    output_png.parent.mkdir(parents=True, exist_ok=True)

    if output_csv is not None:
        with output_csv.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["Frequency_MHz", "Amplitude_dBm"])
            for freq, amp in zip(frequencies, amplitudes):
                writer.writerow([freq, f"{amp:.3f}"])

    fig = create_plot(frequencies, amplitudes, marker_values, plot_config)
    fig.savefig(output_png, dpi=int(plot_config.get("dpi", 150)))

    if output_csv is not None:
        print(f"Wrote {output_csv} and {output_png}")
    else:
        print(f"Wrote {output_png}")


def main() -> None:
    args = parse_args()
    if args.write_config:
        write_default_config(args.write_config)
        print(f"Wrote default config to {args.write_config}")
        return

    config = load_config(args.config)
    image_path = Path(args.image)
    output_csv = Path(args.output_csv)
    output_png = Path(args.output_png)
    try:
        generate_outputs(image_path, output_csv, output_png, config)
    except Exception as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
