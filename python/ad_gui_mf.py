"""Preview the sum of two sine-wave components for an Active Driver."""

import math
from fractions import Fraction
import tkinter as tk
from tkinter import ttk


def frequency_gcd(frequencies):
    """Find the common fundamental using decimal rather than binary fractions."""
    fractions = [Fraction(str(frequency)) for frequency in frequencies if frequency > 0]
    if not fractions:
        return 0.0
    denominator = math.lcm(*(value.denominator for value in fractions))
    numerator = math.gcd(*(value.numerator * (denominator // value.denominator)
                           for value in fractions))
    return float(Fraction(numerator, denominator))


def sample_waveform(components):
    """Return a period and (time, amplitude) samples; zero Hz adds zero."""
    for amplitude, frequency in components:
        if not math.isfinite(amplitude) or not math.isfinite(frequency):
            raise ValueError("Amplitude and frequency must be finite numbers")
        if frequency < 0:
            raise ValueError("Frequency must be zero or positive")
    frequencies = [frequency for _, frequency in components if frequency > 0]
    fundamental = frequency_gcd(frequencies)
    if frequencies and fundamental == 0:
        raise ValueError("Common frequency is too small to plot")
    period = 1 / fundamental if fundamental else 1.0
    if not math.isfinite(period):
        raise ValueError("Frequency is too small to plot")
    cycles = max(frequencies, default=0) * period
    if not math.isfinite(cycles):
        raise ValueError("Frequency range is too large to plot")
    count = max(1000, math.ceil(min(cycles, 1000) * 40))
    samples = []
    for index in range(count + 1):
        time = period * (index / count)
        value = sum(amplitude * math.sin(math.tau * (frequency * time))
                    for amplitude, frequency in components)
        if not math.isfinite(value):
            raise ValueError("Combined amplitude is too large to plot")
        samples.append((time, value))
    return period, samples


def normalize_waveform(components, samples):
    """Apply one shared gain based on the peak of the summed waveform."""
    peak = max(abs(value) for _, value in samples)
    if peak == 0:
        return [0.0 for _ in components], [(time, 0.0) for time, _ in samples]
    amplitudes = [amplitude / peak for amplitude, _ in components]
    if not all(math.isfinite(amplitude) for amplitude in amplitudes):
        raise ValueError("Normalized amplitude is too large to plot")
    return amplitudes, [(time, value / peak) for time, value in samples]


def trigger_timing(frequency):
    """Return the fewest whole periods giving a whole-millisecond interval."""
    if frequency == 0:
        return None
    period_ms = Fraction(1000) / Fraction(str(frequency))
    return period_ms.denominator, period_ms.numerator


class ActiveDriverMultiFrequencyGui:
    def __init__(self, root):
        root.title("Active Driver — Multi Frequency")
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        frame = ttk.Frame(root, padding=12)
        frame.grid(sticky="nsew")
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(3, weight=1)
        frame.rowconfigure(4, weight=1)
        self.fields = {}
        for row, fields in enumerate([
            [("ad_ip", "IP", "10.0.1.30"), ("ad_port", "Port", "2000")],
            [("host_ip", "Local IP", ""), ("host_port", "Local port", "2000")],
        ]):
            for column, (name, label, default) in enumerate(fields):
                ttk.Label(frame, text=label).grid(
                    row=row, column=column * 2, sticky="w", padx=(0, 8), pady=4)
                value = tk.StringVar(value=default)
                self.fields[name] = value
                ttk.Entry(frame, textvariable=value, width=20).grid(
                    row=row, column=column * 2 + 1, sticky="ew", padx=(0, 12), pady=4)

        components_frame = ttk.LabelFrame(frame, text="Sine-wave components", padding=8)
        components_frame.grid(row=2, column=0, columnspan=4, sticky="ew", pady=(8, 12))
        components_frame.columnconfigure(1, weight=1)
        components_frame.columnconfigure(2, weight=1)
        components_frame.columnconfigure(3, weight=1)
        components_frame.columnconfigure(4, weight=1)
        for column, label in enumerate(["Component", "Amplitude", "Frequency (Hz)",
                                        "Precompensate", "Normalized amplitude"]):
            ttk.Label(components_frame, text=label).grid(
                row=0, column=column, sticky="w", padx=8, pady=4)
        self.components = []
        self.normalized_amplitudes = []
        for row, defaults in enumerate([("1", "60"), ("0", "0")], start=1):
            ttk.Label(components_frame, text=str(row)).grid(row=row, column=0, padx=8)
            values = []
            for column, default in enumerate(defaults, start=1):
                value = tk.StringVar(value=default)
                ttk.Entry(components_frame, textvariable=value, width=16).grid(
                    row=row, column=column, sticky="ew", padx=8, pady=4)
                values.append(value)
            self.components.append(values)
            ttk.Label(components_frame, text="1").grid(
                row=row, column=3, sticky="w", padx=8, pady=4)
            normalized = tk.StringVar()
            self.normalized_amplitudes.append(normalized)
            ttk.Entry(components_frame, textvariable=normalized, width=20,
                      state="readonly").grid(
                row=row, column=4, sticky="ew", padx=8, pady=4)

        timing_frame = ttk.Frame(frame)
        timing_frame.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(0, 8))
        self.gcd_frequency = tk.StringVar()
        self.duration = tk.StringVar()
        self.trigger_interval = tk.StringVar()
        for column, (label, value) in enumerate([
            ("GCD frequency (Hz)", self.gcd_frequency),
            ("Duration (periods)", self.duration),
            ("Trigger interval (ms)", self.trigger_interval),
        ]):
            timing_frame.columnconfigure(column * 2 + 1, weight=1)
            ttk.Label(timing_frame, text=label).grid(
                row=0, column=column * 2, sticky="w", padx=(0, 8))
            ttk.Entry(timing_frame, textvariable=value, width=12, state="readonly").grid(
                row=0, column=column * 2 + 1, sticky="ew", padx=(0, 12))

        self.canvas = tk.Canvas(frame, width=680, height=320, background="white",
                                highlightthickness=1, highlightbackground="#aaaaaa")
        self.canvas.grid(row=4, column=0, columnspan=4, sticky="nsew")
        self.status = tk.StringVar()
        ttk.Label(frame, textvariable=self.status, wraplength=680).grid(
            row=5, column=0, columnspan=4, sticky="w", pady=(8, 0))
        self.canvas.bind("<Configure>", self.update_plot)
        for component in self.components:
            for value in component:
                value.trace_add("write", self.update_plot)
        self.update_plot()

    def update_plot(self, *_):
        self.canvas.delete("all")
        self.gcd_frequency.set("")
        self.duration.set("")
        self.trigger_interval.set("")
        for value in self.normalized_amplitudes:
            value.set("")
        try:
            components = [(float(amplitude.get()), float(frequency.get()))
                          for amplitude, frequency in self.components]
            period, samples = sample_waveform(components)
            amplitudes, samples = normalize_waveform(components, samples)
            for value, amplitude in zip(self.normalized_amplitudes, amplitudes):
                value.set(f"{amplitude:.12g}")
            fundamental = frequency_gcd([frequency for _, frequency in components])
            self.gcd_frequency.set(f"{fundamental:.12g}")
            timing = trigger_timing(fundamental)
            if timing is None:
                self.duration.set("N/A")
                self.trigger_interval.set("N/A")
            else:
                duration, interval_ms = timing
                self.duration.set(str(duration))
                self.trigger_interval.set(str(interval_ms))
        except ValueError as exc:
            self.status.set(f"Enter numeric amplitudes and frequencies. {exc}")
            return

        width = max(self.canvas.winfo_width(), 200)
        height = max(self.canvas.winfo_height(), 160)
        left, top, right, bottom = 70, 30, width - 20, height - 50
        scale = 1.0

        def y_position(value):
            return top + (1 - value / scale) * (bottom - top) / 2

        self.canvas.create_text((left + right) / 2, 14, text="Normalized sum of components")
        for index in range(5):
            fraction = index / 4
            x = left + fraction * (right - left)
            self.canvas.create_line(x, top, x, bottom, fill="#eeeeee")
            self.canvas.create_text(x, bottom + 14, text=f"{period * fraction:.4g}")
            value = scale * (1 - 2 * fraction)
            y = y_position(value)
            self.canvas.create_line(left, y, right, y, fill="#eeeeee")
            self.canvas.create_text(left - 8, y, text=f"{value:.3g}", anchor="e")
        self.canvas.create_rectangle(left, top, right, bottom, outline="#888888")
        self.canvas.create_line(left, y_position(0), right, y_position(0), fill="#aaaaaa")
        self.canvas.create_text((left + right) / 2, height - 10, text="Time (s)")
        self.canvas.create_text(12, (top + bottom) / 2, text="Normalized amplitude", angle=90)
        points = []
        for time, value in samples:
            points.extend((left + (time / period) * (right - left), y_position(value)))
        self.canvas.create_line(*points, fill="#1565c0", width=2)
        if any(frequency > 0 for _, frequency in components):
            self.status.set(f"One period of the GCD frequency: {period:.6g} s. "
                            "Zero Hz contributes zero.")
        else:
            self.status.set("Both frequencies are zero; showing a flat waveform over 1 second.")


def main():
    root = tk.Tk()
    ActiveDriverMultiFrequencyGui(root)
    root.mainloop()


if __name__ == "__main__":
    main()
