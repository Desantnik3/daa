from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from tkinter import filedialog, messagebox
import tkinter as tk
from tkinter import ttk

import generate_spectrum as gen


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = SCRIPT_DIR / "config_example.json"


class ToolTip:
    def __init__(self, widget: tk.Widget, text: str, delay_ms: int = 400) -> None:
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms
        self._after_id: str | None = None
        self._window: tk.Toplevel | None = None

        self.widget.bind("<Enter>", self._schedule)
        self.widget.bind("<Leave>", self._hide)
        self.widget.bind("<ButtonPress>", self._hide)

    def _schedule(self, _event: tk.Event | None = None) -> None:
        self._cancel()
        self._after_id = self.widget.after(self.delay_ms, self._show)

    def _cancel(self) -> None:
        if self._after_id is not None:
            self.widget.after_cancel(self._after_id)
            self._after_id = None

    def _show(self) -> None:
        if self._window or not self.text:
            return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self._window = tk.Toplevel(self.widget)
        self._window.wm_overrideredirect(True)
        self._window.wm_geometry(f"+{x}+{y}")
        label = tk.Label(
            self._window,
            text=self.text,
            justify="left",
            background="#ffffe0",
            relief="solid",
            borderwidth=1,
            padx=6,
            pady=3,
        )
        label.pack()

    def _hide(self, _event: tk.Event | None = None) -> None:
        self._cancel()
        if self._window:
            self._window.destroy()
            self._window = None


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
            raise ValueError(f"Неверная строка диапазона: {line}")
        if len(parts) != 2:
            raise ValueError(f"Неверная строка диапазона: {line}")
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
        try:
            if len(parts) == 1:
                marker_id = len(markers) + 1
                freq = float(parts[0])
            else:
                marker_id = int(parts[0])
                freq = float(parts[1])
        except ValueError as exc:
            raise ValueError(f"Неверная строка маркера: {line}") from exc
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
        self.root.title("Генератор спектра")

        self.config = self.load_initial_config()
        self.tooltips: list[ToolTip] = []

        self.image_path_var = tk.StringVar()
        self.output_csv_var = tk.StringVar()
        self.output_png_var = tk.StringVar()
        self.save_csv_var = tk.BooleanVar(value=True)

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
        self.trace_green_min_var = tk.StringVar()
        self.trace_green_delta_var = tk.StringVar()
        self.random_seed_var = tk.StringVar()
        self.random_variation_var = tk.StringVar()

        self.markers_text: tk.Text | None = None
        self.ul_mid_ranges_text: tk.Text | None = None
        self.dl_ranges_text: tk.Text | None = None
        self.suppress_ranges_text: tk.Text | None = None

        self.log_text: tk.Text | None = None
        self.log_menu: tk.Menu | None = None
        self.csv_entry: ttk.Entry | None = None
        self.csv_browse_button: ttk.Button | None = None

        self._build_ui()
        self.populate_from_config(self.config)

    def load_initial_config(self) -> dict:
        if DEFAULT_CONFIG_PATH.exists():
            return gen.load_config(str(DEFAULT_CONFIG_PATH))
        return deepcopy(gen.DEFAULT_CONFIG)

    def default_output_dir(self) -> Path:
        return Path.home() / "SpectrumGenerator"

    def _initial_dir_and_file(self, value: str) -> tuple[str, str]:
        fallback = self.default_output_dir()
        if not fallback.exists():
            fallback = Path.home()
        if not value:
            return str(fallback), ""
        path = Path(value).expanduser()
        if path.is_dir():
            return str(path), ""
        parent = path.parent if path.parent.exists() else fallback
        return str(parent), path.name

    def _ensure_unique_single(self, path: Path) -> Path:
        if not path.exists():
            return path
        for idx in range(1, 1000):
            candidate = path.with_name(f"{path.stem}_{idx}{path.suffix}")
            if not candidate.exists():
                return candidate
        raise RuntimeError(f"Не удалось подобрать имя для {path}")

    def _ensure_unique_outputs(
        self, csv_path: Path | None, png_path: Path
    ) -> tuple[Path | None, Path]:
        if csv_path is None:
            return None, self._ensure_unique_single(png_path)
        if csv_path.parent == png_path.parent and csv_path.stem == png_path.stem:
            if not csv_path.exists() and not png_path.exists():
                return csv_path, png_path
            for idx in range(1, 1000):
                csv_candidate = csv_path.with_name(
                    f"{csv_path.stem}_{idx}{csv_path.suffix}"
                )
                png_candidate = png_path.with_name(
                    f"{png_path.stem}_{idx}{png_path.suffix}"
                )
                if not csv_candidate.exists() and not png_candidate.exists():
                    return csv_candidate, png_candidate
        return self._ensure_unique_single(csv_path), self._ensure_unique_single(png_path)

    def _build_ui(self) -> None:
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)

        files_tab = ttk.Frame(notebook)
        ranges_tab = ttk.Frame(notebook)
        levels_tab = ttk.Frame(notebook)
        markers_tab = ttk.Frame(notebook)

        notebook.add(files_tab, text="Файлы")
        notebook.add(ranges_tab, text="Диапазоны")
        notebook.add(levels_tab, text="Уровни")
        notebook.add(markers_tab, text="Маркеры")

        self._build_files_tab(files_tab)
        self._build_ranges_tab(ranges_tab)
        self._build_levels_tab(levels_tab)
        self._build_markers_tab(markers_tab)

        actions = ttk.Frame(self.root)
        actions.pack(fill="x", padx=10, pady=(0, 8))
        load_button = ttk.Button(
            actions, text="Загрузить конфиг", command=self.on_load_config
        )
        load_button.pack(side="left")
        self._add_tooltip(load_button, "Загрузить параметры из JSON файла.")

        save_button = ttk.Button(
            actions, text="Сохранить конфиг", command=self.on_save_config
        )
        save_button.pack(side="left", padx=(8, 0))
        self._add_tooltip(save_button, "Сохранить текущие параметры в JSON.")

        generate_button = ttk.Button(
            actions, text="Сгенерировать", command=self.on_generate
        )
        generate_button.pack(side="right")
        self._add_tooltip(
            generate_button, "Построить спектр и сохранить CSV/PNG."
        )

        log_frame = ttk.LabelFrame(self.root, text="Журнал")
        log_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.log_text = tk.Text(log_frame, height=6, wrap="word")
        self.log_text.pack(fill="both", expand=True)
        self._setup_log_copy()

    def _build_files_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(1, weight=1)

        label = ttk.Label(parent, text="Входное изображение")
        label.grid(row=0, column=0, sticky="w")
        entry = ttk.Entry(parent, textvariable=self.image_path_var)
        entry.grid(row=0, column=1, sticky="ew", padx=6)
        button = ttk.Button(parent, text="Обзор", command=self.browse_image)
        button.grid(row=0, column=2)
        tooltip = "Скриншот спектра (PNG/JPG/WebP/GIF)."
        self._add_tooltip(label, tooltip)
        self._add_tooltip(entry, tooltip)
        self._add_tooltip(button, "Выбрать файл изображения.")

        label = ttk.Label(parent, text="Выходной CSV")
        label.grid(row=1, column=0, sticky="w")
        entry = ttk.Entry(parent, textvariable=self.output_csv_var)
        entry.grid(row=1, column=1, sticky="ew", padx=6)
        button = ttk.Button(parent, text="Обзор", command=self.browse_output_csv)
        button.grid(row=1, column=2)
        self.csv_entry = entry
        self.csv_browse_button = button
        tooltip = "Путь для сохранения таблицы Frequency/Amplitude."
        self._add_tooltip(label, tooltip)
        self._add_tooltip(entry, tooltip)
        self._add_tooltip(button, "Выбрать файл CSV для сохранения.")

        checkbox = ttk.Checkbutton(
            parent,
            text="Сохранять CSV",
            variable=self.save_csv_var,
            command=self.on_toggle_csv,
        )
        checkbox.grid(row=1, column=3, sticky="w")
        self._add_tooltip(checkbox, "Если выключить, CSV не сохраняется.")

        label = ttk.Label(parent, text="Выходной PNG")
        label.grid(row=2, column=0, sticky="w")
        entry = ttk.Entry(parent, textvariable=self.output_png_var)
        entry.grid(row=2, column=1, sticky="ew", padx=6)
        button = ttk.Button(parent, text="Обзор", command=self.browse_output_png)
        button.grid(row=2, column=2)
        tooltip = "Путь для сохранения графика."
        self._add_tooltip(label, tooltip)
        self._add_tooltip(entry, tooltip)
        self._add_tooltip(button, "Выбрать файл PNG для сохранения.")

    def _build_ranges_tab(self, parent: ttk.Frame) -> None:
        for col in range(4):
            parent.columnconfigure(col, weight=1)

        label = ttk.Label(parent, text="Начало частоты (MHz)")
        label.grid(row=0, column=0, sticky="w")
        entry = ttk.Entry(parent, textvariable=self.freq_start_var, width=12)
        entry.grid(row=0, column=1, sticky="w")
        tooltip = "Левая граница графика по частоте."
        self._add_tooltip(label, tooltip)
        self._add_tooltip(entry, tooltip)

        label = ttk.Label(parent, text="Конец частоты (MHz)")
        label.grid(row=0, column=2, sticky="w")
        entry = ttk.Entry(parent, textvariable=self.freq_stop_var, width=12)
        entry.grid(row=0, column=3, sticky="w")
        tooltip = "Правая граница графика по частоте."
        self._add_tooltip(label, tooltip)
        self._add_tooltip(entry, tooltip)

        label = ttk.Label(parent, text="Шаг (MHz)")
        label.grid(row=1, column=0, sticky="w")
        entry = ttk.Entry(parent, textvariable=self.freq_step_var, width=12)
        entry.grid(row=1, column=1, sticky="w")
        tooltip = "Шаг дискретизации по частоте."
        self._add_tooltip(label, tooltip)
        self._add_tooltip(entry, tooltip)

        label = ttk.Label(parent, text="Диапазон выборки пика (MHz)")
        label.grid(row=2, column=0, sticky="w")
        entry = ttk.Entry(parent, textvariable=self.peak_sample_start_var, width=12)
        entry.grid(row=2, column=1, sticky="w")
        entry_end = ttk.Entry(parent, textvariable=self.peak_sample_end_var, width=12)
        entry_end.grid(row=2, column=2, sticky="w")
        tooltip = "Участок для оценки шкалы пика на скриншоте."
        self._add_tooltip(label, tooltip)
        self._add_tooltip(entry, tooltip)
        self._add_tooltip(entry_end, tooltip)

        label = ttk.Label(parent, text="Основной UL (MHz)")
        label.grid(row=3, column=0, sticky="w")
        entry = ttk.Entry(parent, textvariable=self.ul_main_start_var, width=12)
        entry.grid(row=3, column=1, sticky="w")
        entry_end = ttk.Entry(parent, textvariable=self.ul_main_end_var, width=12)
        entry_end.grid(row=3, column=2, sticky="w")
        tooltip = "Диапазон аплинка 2600 (основная полоса)."
        self._add_tooltip(label, tooltip)
        self._add_tooltip(entry, tooltip)
        self._add_tooltip(entry_end, tooltip)

        label = ttk.Label(parent, text="UL средние диапазоны (по строке)")
        label.grid(row=4, column=0, sticky="w", pady=(8, 0))
        self._add_tooltip(label, "Аплинк 1800/2100. Формат: 1710-1785.")
        self.ul_mid_ranges_text = tk.Text(parent, height=4, width=24)
        self.ul_mid_ranges_text.grid(row=5, column=0, columnspan=2, sticky="ew")
        self._add_tooltip(
            self.ul_mid_ranges_text, "Каждая строка: начало-конец диапазона."
        )

        label = ttk.Label(parent, text="DL диапазоны (по строке)")
        label.grid(row=4, column=2, sticky="w", pady=(8, 0))
        self._add_tooltip(label, "Даунлинк диапазоны. Формат: 1805-1880.")
        self.dl_ranges_text = tk.Text(parent, height=4, width=24)
        self.dl_ranges_text.grid(row=5, column=2, columnspan=2, sticky="ew")
        self._add_tooltip(
            self.dl_ranges_text, "Каждая строка: начало-конец диапазона."
        )

        label = ttk.Label(parent, text="Подавляемые диапазоны (по строке)")
        label.grid(row=6, column=0, sticky="w", pady=(8, 0))
        self._add_tooltip(
            label,
            "Диапазоны, которые нужно опустить до уровня шума.",
        )
        self.suppress_ranges_text = tk.Text(parent, height=4, width=24)
        self.suppress_ranges_text.grid(row=7, column=0, columnspan=2, sticky="ew")
        self._add_tooltip(
            self.suppress_ranges_text, "Каждая строка: начало-конец диапазона."
        )

    def _build_levels_tab(self, parent: ttk.Frame) -> None:
        for col in range(4):
            parent.columnconfigure(col, weight=1)

        self._add_level_entry(
            parent,
            "Базовый уровень (dBm)",
            self.baseline_var,
            0,
            0,
            "Опорный уровень шума перед коррекцией.",
        )
        self._add_level_entry(
            parent,
            "Средний пик (dBm)",
            self.mid_peak_var,
            0,
            2,
            "Опорный уровень средних пиков (1800/2100).",
        )
        self._add_level_entry(
            parent,
            "Пик (dBm)",
            self.peak_var,
            1,
            0,
            "Опорный уровень сильного пика.",
        )
        self._add_level_entry(
            parent,
            "Сдвиг вне диапазона (dBm)",
            self.subtract_outside_var,
            1,
            2,
            "Насколько опустить уровни вне полос.",
        )

        self._add_level_entry(
            parent,
            "Макс. пик над шумом (dB)",
            self.peak_max_above_floor_var,
            2,
            0,
            "Ограничение высоты пика относительно шума.",
        )

        self._add_level_entry(
            parent,
            "UL база (dB)",
            self.ul_main_base_var,
            3,
            0,
            "Средний уровень аплинка 2600.",
        )
        self._add_level_entry(
            parent,
            "UL край (dB)",
            self.ul_main_edge_var,
            3,
            2,
            "Добавка к уровню на краях UL 2600.",
        )
        self._add_level_entry(
            parent,
            "UL средн. край (dB)",
            self.ul_mid_edge_var,
            4,
            0,
            "Добавка на краях UL 1800/2100.",
        )
        self._add_level_entry(
            parent,
            "UL разн. мин (dB)",
            self.ul_mid_diff_min_var,
            4,
            2,
            "Минимальная разница UL 1800/2100 от 2600.",
        )
        self._add_level_entry(
            parent,
            "UL разн. макс (dB)",
            self.ul_mid_diff_max_var,
            5,
            0,
            "Максимальная разница UL 1800/2100 от 2600.",
        )

        self._add_level_entry(
            parent,
            "Шум: джиттер (dB)",
            self.noise_jitter_var,
            6,
            0,
            "Случайные колебания уровня шума.",
        )
        self._add_level_entry(
            parent,
            "Шум: рябь (dB)",
            self.noise_ripple_var,
            6,
            2,
            "Волнообразная компонента шума.",
        )

        self._add_level_entry(
            parent,
            "Мин. зелёный (0-255)",
            self.trace_green_min_var,
            7,
            0,
            "Порог яркости зелёного для поиска трассы.",
        )
        self._add_level_entry(
            parent,
            "Преобладание зелёного",
            self.trace_green_delta_var,
            7,
            2,
            "Насколько зелёный должен быть выше красного/синего.",
        )

        self._add_level_entry(
            parent,
            "Сид случайности",
            self.random_seed_var,
            8,
            0,
            "Фиксирует повторяемость результата.",
        )
        self._add_level_entry(
            parent,
            "Случайная вариация",
            self.random_variation_var,
            8,
            2,
            "Относительная вариация значений (например 0.02 = 2%).",
        )

    def _add_level_entry(
        self,
        parent: ttk.Frame,
        label: str,
        variable: tk.StringVar,
        row: int,
        col: int,
        tooltip: str | None = None,
    ) -> None:
        label_widget = ttk.Label(parent, text=label)
        label_widget.grid(row=row, column=col, sticky="w")
        entry_widget = ttk.Entry(parent, textvariable=variable, width=12)
        entry_widget.grid(row=row, column=col + 1, sticky="w")
        if tooltip:
            self._add_tooltip(label_widget, tooltip)
            self._add_tooltip(entry_widget, tooltip)

    def _build_markers_tab(self, parent: ttk.Frame) -> None:
        label = ttk.Label(parent, text="Маркеры (id, частота MHz в строке)")
        label.pack(anchor="w")
        self._add_tooltip(
            label, "Формат: 1, 890.0 или просто 890.0 (id будет авто)."
        )
        self.markers_text = tk.Text(parent, height=12, width=40)
        self.markers_text.pack(fill="both", expand=True)
        self._add_tooltip(
            self.markers_text, "Каждая строка: id, частота в МГц."
        )

    def _add_tooltip(self, widget: tk.Widget, text: str) -> None:
        self.tooltips.append(ToolTip(widget, text))

    def _setup_log_copy(self) -> None:
        if not self.log_text:
            return
        self.log_menu = tk.Menu(self.root, tearoff=0)
        self.log_menu.add_command(label="Копировать", command=self.on_copy_log)
        self.log_text.bind("<Button-3>", self.show_log_menu)
        self.log_text.bind("<Button-2>", self.show_log_menu)
        self.log_text.bind("<Control-c>", self.on_copy_log)

    def show_log_menu(self, event: tk.Event) -> None:
        if not self.log_menu:
            return
        if not self.log_text or not self.log_text.tag_ranges("sel"):
            return
        self.log_menu.tk_popup(event.x_root, event.y_root)

    def on_toggle_csv(self) -> None:
        state = "normal" if self.save_csv_var.get() else "disabled"
        if self.csv_entry:
            self.csv_entry.configure(state=state)
        if self.csv_browse_button:
            self.csv_browse_button.configure(state=state)

    def log(self, message: str) -> None:
        if not self.log_text:
            return
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")

    def on_copy_log(self, _event: tk.Event | None = None) -> str:
        if not self.log_text:
            return "break"
        if not self.log_text.tag_ranges("sel"):
            return "break"
        content = self.log_text.get("sel.first", "sel.last")
        if not content:
            return "break"
        self.root.clipboard_clear()
        self.root.clipboard_append(content)
        return "break"

    def browse_image(self) -> None:
        initial_dir, initial_file = self._initial_dir_and_file(
            self.image_path_var.get().strip()
        )
        path = filedialog.askopenfilename(
            title="Выберите изображение",
            filetypes=[
                ("Изображения", "*.png *.jpg *.jpeg *.webp *.gif"),
                ("Все файлы", "*"),
            ],
            initialdir=initial_dir,
            initialfile=initial_file,
        )
        if path:
            self.image_path_var.set(path)

    def browse_output_csv(self) -> None:
        initial_dir, initial_file = self._initial_dir_and_file(
            self.output_csv_var.get().strip()
        )
        path = filedialog.asksaveasfilename(
            title="Выберите CSV для сохранения",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("Все файлы", "*")],
            initialdir=initial_dir,
            initialfile=initial_file or "spectrum.csv",
        )
        if path:
            self.output_csv_var.set(path)

    def browse_output_png(self) -> None:
        initial_dir, initial_file = self._initial_dir_and_file(
            self.output_png_var.get().strip()
        )
        path = filedialog.asksaveasfilename(
            title="Выберите PNG для сохранения",
            defaultextension=".png",
            filetypes=[("PNG", "*.png"), ("Все файлы", "*")],
            initialdir=initial_dir,
            initialfile=initial_file or "spectrum.png",
        )
        if path:
            self.output_png_var.set(path)

    def on_load_config(self) -> None:
        path = filedialog.askopenfilename(
            title="Открыть конфиг",
            filetypes=[("JSON", "*.json"), ("Все файлы", "*")],
        )
        if not path:
            return
        try:
            config = gen.load_config(path)
            self.populate_from_config(config)
            self.log(f"Конфиг загружен: {path}")
        except Exception as exc:
            messagebox.showerror("Ошибка загрузки", str(exc))

    def on_save_config(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Сохранить конфиг",
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("Все файлы", "*")],
        )
        if not path:
            return
        try:
            config = self.build_config()
            Path(path).write_text(json.dumps(config, indent=2), encoding="utf-8")
            self.log(f"Конфиг сохранён: {path}")
        except Exception as exc:
            messagebox.showerror("Ошибка сохранения", str(exc))

    def on_generate(self) -> None:
        try:
            config = self.build_config()
        except Exception as exc:
            messagebox.showerror("Ошибка конфигурации", str(exc))
            return

        image_path = self.image_path_var.get().strip()
        output_csv = self.output_csv_var.get().strip()
        output_png = self.output_png_var.get().strip()
        if not image_path or not output_png:
            messagebox.showerror(
                "Ошибка генерации", "Заполните путь к изображению и PNG."
            )
            return
        if self.save_csv_var.get() and not output_csv:
            messagebox.showerror(
                "Ошибка генерации", "Укажите путь для CSV или отключите сохранение."
            )
            return

        image_path_obj = Path(image_path).expanduser()
        output_png_obj = Path(output_png).expanduser()
        output_csv_obj = (
            Path(output_csv).expanduser() if self.save_csv_var.get() else None
        )
        output_csv_obj, output_png_obj = self._ensure_unique_outputs(
            output_csv_obj, output_png_obj
        )
        if output_csv_obj and str(output_csv_obj) != output_csv:
            self.log("Имя CSV занято, сохранено как:")
            self.log(f"  CSV: {output_csv_obj}")
            self.output_csv_var.set(str(output_csv_obj))
        if str(output_png_obj) != output_png:
            self.log("Имя PNG занято, сохранено как:")
            self.log(f"  PNG: {output_png_obj}")
            self.output_png_var.set(str(output_png_obj))

        try:
            gen.generate_outputs(
                image_path_obj,
                output_csv_obj,
                output_png_obj,
                config,
            )
        except Exception as exc:
            self.log(str(exc))
            messagebox.showerror("Ошибка генерации", str(exc))
            return

        if output_csv_obj:
            self.log(f"Созданы файлы: {output_csv_obj}, {output_png_obj}")
            messagebox.showinfo("Готово", "График и CSV успешно созданы.")
        else:
            self.log(f"Создан файл: {output_png_obj}")
            messagebox.showinfo("Готово", "График успешно создан.")

    def populate_from_config(self, config: dict) -> None:
        self.config = deepcopy(config)
        default_dir = self.default_output_dir()
        default_image = Path(gen.IMAGE_PATH)
        self.image_path_var.set(
            str(default_image) if default_image.exists() else ""
        )
        self.output_csv_var.set(str(default_dir / "spectrum.csv"))
        self.output_png_var.set(str(default_dir / "spectrum.png"))

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
        self.trace_green_min_var.set(str(config.get("trace_green_min", 80)))
        self.trace_green_delta_var.set(str(config.get("trace_green_delta", 30)))
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
        self.on_toggle_csv()

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
        config["trace_green_min"] = int(self.trace_green_min_var.get())
        config["trace_green_delta"] = int(self.trace_green_delta_var.get())
        config["random_seed"] = int(self.random_seed_var.get())
        config["random_variation"] = float(self.random_variation_var.get())

        if not self.ul_mid_ranges_text:
            raise ValueError("Не задан список UL диапазонов.")
        config["ul_mid_ranges_mhz"] = parse_range_lines(
            self.ul_mid_ranges_text.get("1.0", "end")
        )

        if not self.dl_ranges_text:
            raise ValueError("Не задан список DL диапазонов.")
        config["dl_ranges_mhz"] = parse_range_lines(
            self.dl_ranges_text.get("1.0", "end")
        )

        if not self.suppress_ranges_text:
            raise ValueError("Не задан список подавляемых диапазонов.")
        config["suppress_ranges_mhz"] = parse_range_lines(
            self.suppress_ranges_text.get("1.0", "end")
        )

        if not self.markers_text:
            raise ValueError("Не заданы маркеры.")
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
