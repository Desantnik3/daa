from __future__ import annotations

import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from tkinter import filedialog, messagebox
import tkinter as tk
from tkinter import ttk

import generate_spectrum as gen


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = SCRIPT_DIR / "config_example.json"
GENERATOR_PATH = SCRIPT_DIR / "generate_spectrum.py"


def parse_range_lines(text: str) -> list[list[float]]:
    ranges: list[list[float]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        clean = line.replace(" ", "")
        if "-" in clean:
            parts = clean.split("-")
        elif "," in clean:
            parts = clean.split(",")
        else:
            raise ValueError(f"Invalid range line: {line}")
        if len(parts) != 2:
            raise ValueError(f"Invalid range line: {line}")
        start = float(parts[0])
        end = float(parts[1])
        ranges.append([start, end])
    return ranges


def format_range_lines(ranges: list[list[float]]) -> str:
    return "\n".join(f"{start}-{end}" for start, end in ranges)


def parse_marker_lines(text: str) -> list[dict]:
    markers: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        clean = line.replace(" ", "")
        parts = clean.split(",")
        if len(parts) == 1:
            marker_id = len(markers) + 1
            freq = float(parts[0])
        else:
            marker_id = int(parts[0])
            freq = float(parts[1])
        markers.append({"id": marker_id, "freq_mhz": freq})
    return markers


def format_marker_lines(markers: list[dict]) -> str:
    lines = []
    for item in markers:
        if isinstance(item, dict):
            marker_id = int(item.get("id", 0))
            freq = float(item.get("freq_mhz", 0.0))
        else:
            marker_id = int(item[0])
            freq = float(item[1])
        lines.append(f"{marker_id}, {freq}")
    return "\n".join(lines)


class SpectrumApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Spectrum Generator")

        self.config = self.load_initial_config()

        self.image_path_var = tk.StringVar()
        self.output_csv_var = tk.StringVar()
        self.output_png_var = tk.StringVar()

        self.freq_start_var = tk.StringVar()
        self.freq_stop_var = tk.StringVar()
        self.freq_step_var = tk.StringVar()
        self.peak_sample_start_var = tk.StringVar()
        self.peak_sample_end_var = tk.StringVar()

        self.ul_main_start_var = tk.StringVar()
        self.ul_main_end_var = tk.StringVar()

        self.baseline_var = tk.StringVar()
        self.mid_peak_var = tk.StringVar()
        self.peak_var = tk.StringVar()
        self.subtract_outside_var = tk.StringVar()
        self.peak_max_above_floor_var = tk.StringVar()
        self.ul_main_base_var = tk.StringVar()
        self.ul_main_edge_var = tk.StringVar()
        self.ul_mid_edge_var = tk.StringVar()
        self.ul_mid_diff_min_var = tk.StringVar()
        self.ul_mid_diff_max_var = tk.StringVar()
        self.noise_jitter_var = tk.StringVar()
        self.noise_ripple_var = tk.StringVar()
        self.random_seed_var = tk.StringVar()
        self.random_variation_var = tk.StringVar()

        self.markers_text: tk.Text | None = None
        self.ul_mid_ranges_text: tk.Text | None = None
        self.dl_ranges_text: tk.Text | None = None
        self.suppress_ranges_text: tk.Text | None = None

        self.log_text: tk.Text | None = None

        self._build_ui()
        self.populate_from_config(self.config)

    def load_initial_config(self) -> dict:
        if DEFAULT_CONFIG_PATH.exists():
            return gen.load_config(str(DEFAULT_CONFIG_PATH))
        return deepcopy(gen.DEFAULT_CONFIG)

    def _build_ui(self) -> None:
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)

        files_tab = ttk.Frame(notebook)
        ranges_tab = ttk.Frame(notebook)
        levels_tab = ttk.Frame(notebook)
        markers_tab = ttk.Frame(notebook)

        notebook.add(files_tab, text="Files")
        notebook.add(ranges_tab, text="Ranges")
        notebook.add(levels_tab, text="Levels")
        notebook.add(markers_tab, text="Markers")

        self._build_files_tab(files_tab)
        self._build_ranges_tab(ranges_tab)
        self._build_levels_tab(levels_tab)
        self._build_markers_tab(markers_tab)

        actions = ttk.Frame(self.root)
        actions.pack(fill="x", padx=10, pady=(0, 8))
        ttk.Button(actions, text="Load Config", command=self.on_load_config).pack(
            side="left"
        )
        ttk.Button(actions, text="Save Config", command=self.on_save_config).pack(
            side="left", padx=(8, 0)
        )
        ttk.Button(actions, text="Generate", command=self.on_generate).pack(
            side="right"
        )

        log_frame = ttk.LabelFrame(self.root, text="Log")
        log_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.log_text = tk.Text(log_frame, height=6, wrap="word")
        self.log_text.pack(fill="both", expand=True)

    def _build_files_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(1, weight=1)

        ttk.Label(parent, text="Input image").grid(row=0, column=0, sticky="w")
        ttk.Entry(parent, textvariable=self.image_path_var).grid(
            row=0, column=1, sticky="ew", padx=6
        )
        ttk.Button(parent, text="Browse", command=self.browse_image).grid(
            row=0, column=2
        )

        ttk.Label(parent, text="Output CSV").grid(row=1, column=0, sticky="w")
        ttk.Entry(parent, textvariable=self.output_csv_var).grid(
            row=1, column=1, sticky="ew", padx=6
        )
        ttk.Button(parent, text="Browse", command=self.browse_output_csv).grid(
            row=1, column=2
        )

        ttk.Label(parent, text="Output PNG").grid(row=2, column=0, sticky="w")
        ttk.Entry(parent, textvariable=self.output_png_var).grid(
            row=2, column=1, sticky="ew", padx=6
        )
        ttk.Button(parent, text="Browse", command=self.browse_output_png).grid(
            row=2, column=2
        )

    def _build_ranges_tab(self, parent: ttk.Frame) -> None:
        for col in range(4):
            parent.columnconfigure(col, weight=1)

        ttk.Label(parent, text="Freq start (MHz)").grid(row=0, column=0, sticky="w")
        ttk.Entry(parent, textvariable=self.freq_start_var, width=12).grid(
            row=0, column=1, sticky="w"
        )
        ttk.Label(parent, text="Freq stop (MHz)").grid(row=0, column=2, sticky="w")
        ttk.Entry(parent, textvariable=self.freq_stop_var, width=12).grid(
            row=0, column=3, sticky="w"
        )
        ttk.Label(parent, text="Freq step (MHz)").grid(row=1, column=0, sticky="w")
        ttk.Entry(parent, textvariable=self.freq_step_var, width=12).grid(
            row=1, column=1, sticky="w"
        )

        ttk.Label(parent, text="Peak sample range (MHz)").grid(
            row=2, column=0, sticky="w"
        )
        ttk.Entry(parent, textvariable=self.peak_sample_start_var, width=12).grid(
            row=2, column=1, sticky="w"
        )
        ttk.Entry(parent, textvariable=self.peak_sample_end_var, width=12).grid(
            row=2, column=2, sticky="w"
        )

        ttk.Label(parent, text="UL main range (MHz)").grid(
            row=3, column=0, sticky="w"
        )
        ttk.Entry(parent, textvariable=self.ul_main_start_var, width=12).grid(
            row=3, column=1, sticky="w"
        )
        ttk.Entry(parent, textvariable=self.ul_main_end_var, width=12).grid(
            row=3, column=2, sticky="w"
        )

        ttk.Label(parent, text="UL mid ranges (one per line)").grid(
            row=4, column=0, sticky="w", pady=(8, 0)
        )
        self.ul_mid_ranges_text = tk.Text(parent, height=4, width=24)
        self.ul_mid_ranges_text.grid(row=5, column=0, columnspan=2, sticky="ew")

        ttk.Label(parent, text="DL ranges (one per line)").grid(
            row=4, column=2, sticky="w", pady=(8, 0)
        )
        self.dl_ranges_text = tk.Text(parent, height=4, width=24)
        self.dl_ranges_text.grid(row=5, column=2, columnspan=2, sticky="ew")

        ttk.Label(parent, text="Suppress ranges (one per line)").grid(
            row=6, column=0, sticky="w", pady=(8, 0)
        )
        self.suppress_ranges_text = tk.Text(parent, height=4, width=24)
        self.suppress_ranges_text.grid(row=7, column=0, columnspan=2, sticky="ew")

    def _build_levels_tab(self, parent: ttk.Frame) -> None:
        for col in range(4):
            parent.columnconfigure(col, weight=1)

        self._add_level_entry(parent, "Baseline (dBm)", self.baseline_var, 0, 0)
        self._add_level_entry(parent, "Mid peak (dBm)", self.mid_peak_var, 0, 2)
        self._add_level_entry(parent, "Peak (dBm)", self.peak_var, 1, 0)
        self._add_level_entry(
            parent, "Subtract outside (dBm)", self.subtract_outside_var, 1, 2
        )

        self._add_level_entry(
            parent,
            "Peak max above floor (dB)",
            self.peak_max_above_floor_var,
            2,
            0,
        )

        self._add_level_entry(
            parent, "UL main base (dB)", self.ul_main_base_var, 3, 0
        )
        self._add_level_entry(
            parent, "UL main edge extra", self.ul_main_edge_var, 3, 2
        )
        self._add_level_entry(
            parent, "UL mid edge extra", self.ul_mid_edge_var, 4, 0
        )
        self._add_level_entry(
            parent, "UL mid diff min", self.ul_mid_diff_min_var, 4, 2
        )
        self._add_level_entry(
            parent, "UL mid diff max", self.ul_mid_diff_max_var, 5, 0
        )

        self._add_level_entry(
            parent, "Noise jitter (dB)", self.noise_jitter_var, 6, 0
        )
        self._add_level_entry(
            parent, "Noise ripple (dB)", self.noise_ripple_var, 6, 2
        )

        self._add_level_entry(parent, "Random seed", self.random_seed_var, 7, 0)
        self._add_level_entry(
            parent, "Random variation", self.random_variation_var, 7, 2
        )

    def _add_level_entry(
        self,
        parent: ttk.Frame,
        label: str,
        variable: tk.StringVar,
        row: int,
        col: int,
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=col, sticky="w")
        ttk.Entry(parent, textvariable=variable, width=12).grid(
            row=row, column=col + 1, sticky="w"
        )

    def _build_markers_tab(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Markers (id, freq MHz per line)").pack(anchor="w")
        self.markers_text = tk.Text(parent, height=12, width=40)
        self.markers_text.pack(fill="both", expand=True)

    def log(self, message: str) -> None:
        if not self.log_text:
            return
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")

    def browse_image(self) -> None:
        path = filedialog.askopenfilename(
            title="Select input image",
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.webp *.gif"), ("All", "*")],
        )
        if path:
            self.image_path_var.set(path)

    def browse_output_csv(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Select output CSV",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("All", "*")],
        )
        if path:
            self.output_csv_var.set(path)

    def browse_output_png(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Select output PNG",
            defaultextension=".png",
            filetypes=[("PNG", "*.png"), ("All", "*")],
        )
        if path:
            self.output_png_var.set(path)

    def on_load_config(self) -> None:
        path = filedialog.askopenfilename(
            title="Load config",
            filetypes=[("JSON", "*.json"), ("All", "*")],
        )
        if not path:
            return
        try:
            config = gen.load_config(path)
            self.populate_from_config(config)
            self.log(f"Loaded config: {path}")
        except Exception as exc:
            messagebox.showerror("Load error", str(exc))

    def on_save_config(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save config",
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("All", "*")],
        )
        if not path:
            return
        try:
            config = self.build_config()
            Path(path).write_text(json.dumps(config, indent=2), encoding="utf-8")
            self.log(f"Saved config: {path}")
        except Exception as exc:
            messagebox.showerror("Save error", str(exc))

    def on_generate(self) -> None:
        try:
            config = self.build_config()
        except Exception as exc:
            messagebox.showerror("Config error", str(exc))
            return

        config_path = SCRIPT_DIR / "gui_config.json"
        config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")

        image_path = self.image_path_var.get().strip()
        output_csv = self.output_csv_var.get().strip()
        output_png = self.output_png_var.get().strip()
        if not image_path or not output_csv or not output_png:
            messagebox.showerror("Generate error", "Please fill input/output paths.")
            return

        cmd = [
            sys.executable,
            str(GENERATOR_PATH),
            "--config",
            str(config_path),
            "--image",
            image_path,
            "--output-csv",
            output_csv,
            "--output-png",
            output_png,
        ]
        self.log("Running: " + " ".join(cmd))
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.stdout:
            self.log(result.stdout.strip())
        if result.stderr:
            self.log(result.stderr.strip())
        if result.returncode != 0:
            messagebox.showerror("Generate error", "Failed to generate output.")
        else:
            messagebox.showinfo("Done", "Spectrum generated successfully.")

    def populate_from_config(self, config: dict) -> None:
        self.config = deepcopy(config)
        self.image_path_var.set(str(gen.IMAGE_PATH))
        self.output_csv_var.set(str(gen.OUTPUT_CSV))
        self.output_png_var.set(str(gen.OUTPUT_PNG))

        self.freq_start_var.set(str(config["freq_start_mhz"]))
        self.freq_stop_var.set(str(config["freq_stop_mhz"]))
        self.freq_step_var.set(str(config["freq_step_mhz"]))

        peak_sample = config["peak_sample_range_mhz"]
        self.peak_sample_start_var.set(str(peak_sample[0]))
        self.peak_sample_end_var.set(str(peak_sample[1]))

        ul_main = config["ul_main_range_mhz"]
        self.ul_main_start_var.set(str(ul_main[0]))
        self.ul_main_end_var.set(str(ul_main[1]))

        self.baseline_var.set(str(config["baseline_dbm"]))
        self.mid_peak_var.set(str(config["mid_peak_dbm"]))
        self.peak_var.set(str(config["peak_dbm"]))
        self.subtract_outside_var.set(str(config["subtract_outside_dbm"]))
        self.peak_max_above_floor_var.set(str(config["peak_max_above_floor_db"]))
        self.ul_main_base_var.set(str(config["ul_main_base_offset_db"]))
        self.ul_main_edge_var.set(str(config["ul_main_edge_extra_db"]))
        self.ul_mid_edge_var.set(str(config["ul_mid_edge_extra_db"]))
        self.ul_mid_diff_min_var.set(str(config["ul_mid_diff_range_db"][0]))
        self.ul_mid_diff_max_var.set(str(config["ul_mid_diff_range_db"][1]))
        self.noise_jitter_var.set(str(config["noise_jitter_db"]))
        self.noise_ripple_var.set(str(config["noise_ripple_db"]))
        self.random_seed_var.set(str(config["random_seed"]))
        self.random_variation_var.set(str(config["random_variation"]))

        if self.ul_mid_ranges_text:
            self.ul_mid_ranges_text.delete("1.0", "end")
            self.ul_mid_ranges_text.insert(
                "1.0", format_range_lines(config["ul_mid_ranges_mhz"])
            )
        if self.dl_ranges_text:
            self.dl_ranges_text.delete("1.0", "end")
            self.dl_ranges_text.insert(
                "1.0", format_range_lines(config["dl_ranges_mhz"])
            )
        if self.suppress_ranges_text:
            self.suppress_ranges_text.delete("1.0", "end")
            self.suppress_ranges_text.insert(
                "1.0", format_range_lines(config["suppress_ranges_mhz"])
            )
        if self.markers_text:
            self.markers_text.delete("1.0", "end")
            self.markers_text.insert(
                "1.0", format_marker_lines(config["markers"])
            )

    def build_config(self) -> dict:
        config = deepcopy(self.config)
        config["freq_start_mhz"] = int(self.freq_start_var.get())
        config["freq_stop_mhz"] = int(self.freq_stop_var.get())
        config["freq_step_mhz"] = int(self.freq_step_var.get())
        config["peak_sample_range_mhz"] = [
            float(self.peak_sample_start_var.get()),
            float(self.peak_sample_end_var.get()),
        ]
        config["ul_main_range_mhz"] = [
            float(self.ul_main_start_var.get()),
            float(self.ul_main_end_var.get()),
        ]

        config["baseline_dbm"] = float(self.baseline_var.get())
        config["mid_peak_dbm"] = float(self.mid_peak_var.get())
        config["peak_dbm"] = float(self.peak_var.get())
        config["subtract_outside_dbm"] = float(self.subtract_outside_var.get())
        config["peak_max_above_floor_db"] = float(self.peak_max_above_floor_var.get())
        config["ul_main_base_offset_db"] = float(self.ul_main_base_var.get())
        config["ul_main_edge_extra_db"] = float(self.ul_main_edge_var.get())
        config["ul_mid_edge_extra_db"] = float(self.ul_mid_edge_var.get())
        config["ul_mid_diff_range_db"] = [
            float(self.ul_mid_diff_min_var.get()),
            float(self.ul_mid_diff_max_var.get()),
        ]
        config["noise_jitter_db"] = float(self.noise_jitter_var.get())
        config["noise_ripple_db"] = float(self.noise_ripple_var.get())
        config["random_seed"] = int(self.random_seed_var.get())
        config["random_variation"] = float(self.random_variation_var.get())

        if not self.ul_mid_ranges_text:
            raise ValueError("UL mid ranges missing")
        config["ul_mid_ranges_mhz"] = parse_range_lines(
            self.ul_mid_ranges_text.get("1.0", "end")
        )

        if not self.dl_ranges_text:
            raise ValueError("DL ranges missing")
        config["dl_ranges_mhz"] = parse_range_lines(
            self.dl_ranges_text.get("1.0", "end")
        )

        if not self.suppress_ranges_text:
            raise ValueError("Suppress ranges missing")
        config["suppress_ranges_mhz"] = parse_range_lines(
            self.suppress_ranges_text.get("1.0", "end")
        )

        if not self.markers_text:
            raise ValueError("Markers missing")
        config["markers"] = parse_marker_lines(
            self.markers_text.get("1.0", "end")
        )

        return config


def main() -> None:
    root = tk.Tk()
    SpectrumApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
