"""Preview Active Driver sine-wave components and a MEG waveform."""


"""
This code was majority writted by AI.  It may not read well.
"""

import math
from fractions import Fraction
import tkinter as tk
from tkinter import ttk
from udp import ActiveDriverUdp, find_adapter_for_ip

def get_ad_version(ad_ip, ad_port, host_port) -> str:
    _, host_ip, _ = find_adapter_for_ip(ad_ip)
    if host_ip is None:
        return "AD_NOT_FOUND"

    with ActiveDriverUdp(ad_ip=ad_ip, ad_port=ad_port, host_ip=host_ip, host_port=host_port) as ad:
        return ad.QueryVersion_smart()


def frequency_gcd(frequencies):
    """Find the common fundamental using decimal rather than binary fractions."""
    fractions = [Fraction(str(frequency)) for frequency in frequencies if frequency > 0]
    if not fractions:
        return 0.0
    denominator = math.lcm(*(value.denominator for value in fractions))
    numerator = math.gcd(*(value.numerator * (denominator // value.denominator)
                           for value in fractions))
    return float(Fraction(numerator, denominator))


def acoustic_waveform(components, *, period=None):
    """Sample 1024 points over a shared or fundamental period; zero Hz adds zero."""
    for amplitude, frequency in components:
        if not math.isfinite(amplitude) or not math.isfinite(frequency):
            raise ValueError("Amplitude and frequency must be finite numbers")
        if frequency < 0:
            raise ValueError("Frequency must be zero or positive")
    frequencies = [frequency for _, frequency in components if frequency > 0]
    fundamental = frequency_gcd(frequencies)
    if frequencies and fundamental == 0:
        raise ValueError("Common frequency is too small to plot")
    if period is None:
        period = 1 / fundamental if fundamental else 1.0
    if not math.isfinite(period):
        raise ValueError("Frequency is too small to plot")
    cycles = max(frequencies, default=0) * period
    if not math.isfinite(cycles):
        raise ValueError("Frequency range is too large to plot")
    count = 1024
    samples = []
    for index in range(count):
        time = period * (index / (count - 1))
        value = sum(amplitude * math.sin(math.tau * (frequency * time))
                    for amplitude, frequency in components)
        if not math.isfinite(value):
            raise ValueError("Combined amplitude is too large to plot")
        samples.append((time, value))
    return period, samples


def meg_waveform(amplitude, frequency, slew_rate, *, waveform_type="11",
                 lobes=1, period=None):
    """Sample a slew-limited MEG of type 121 or 11 in mT/m.

    Type 121 crosses zero at T/4 and 3T/4. Type 11 transitions from +A to
    -A across T/2. T = 1/frequency; slew is in mT/m/s. Peaks are capped
    at the requested amplitude. Render lobes full periods, then zero.
    Zero Hz produces a flat zero.
    """
    if waveform_type not in ("121", "11"):
        raise ValueError("MEG waveform type must be 121 or 11")
    if not math.isfinite(amplitude):
        raise ValueError("Amplitude must be a finite number")
    if not math.isfinite(slew_rate) or slew_rate < 0:
        raise ValueError("MEG slew rate must be a finite, nonnegative number")
    if not isinstance(lobes, int) or isinstance(lobes, bool) or lobes < 1:
        raise ValueError("MEG lobes must be a positive whole number")
    if period is None and frequency > 0:
        period = lobes / frequency
    # Reuse the sine sampler's time grid and frequency/period validation.
    period, time_grid = acoustic_waveform([(0.0, frequency)], period=period)
    samples = []
    for time, _ in time_grid:
        phase = (frequency * time) % 1.0
        value = 0.0
        if (frequency > 0 and time < lobes / frequency
                and amplitude != 0 and slew_rate > 0):
            if waveform_type == "121":
                distance_from_zero = (abs(phase - 0.5) - 0.25) / frequency
            else:
                distance_from_zero = (0.5 - phase) / frequency
            value = max(-abs(amplitude), min(abs(amplitude),
                                             distance_from_zero * slew_rate))
            if amplitude < 0:
                value = -value
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


def calculate_menc(normalized_amplitude, frequency, gain, period,
                   meg_samples):
    """Integrate the scaled acoustic component times physical MEG (mT/m).

    Physical MEG already includes its amplitude: normalized MEG * amplitude.
    Both waveforms use the same 1024-point grid over the plotted interval.
    """
    if not math.isfinite(gain):
        raise ValueError("Gain must be a finite number")
    _, samples = acoustic_waveform(
        [(normalized_amplitude * gain, frequency)], period=period)
    products = []
    for (time, value), (meg_time, meg_value) in zip(samples, meg_samples, strict=True):
        if time != meg_time:
            raise ValueError("MENC waveforms must use the same time grid")
        product = value * meg_value
        if not math.isfinite(product):
            raise ValueError("MENC integrand must be finite")
        products.append((time, product))
    integral = math.fsum((t1 - t0) * (v0 / 2 + v1 / 2)
                         for (t0, v0), (t1, v1) in zip(products, products[1:]))
    if not math.isfinite(integral):
        raise ValueError("MENC integral is too large")
    return integral


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
        components_frame.columnconfigure(5, weight=1)
        for column, label in enumerate(["Component", "Amplitude", "Frequency (Hz)",
                                        "Gain", "Normalized amplitude", "MENC"]):
            ttk.Label(components_frame, text=label).grid(
                row=0, column=column, sticky="w", padx=8, pady=4)
        self.components = []
        self.normalized_amplitudes = []
        self.gain = []
        self.menc_values = []
        for row, defaults in enumerate([("1", "60"), ("0.5", "90"), ("30", "60")], start=1):
            is_meg = row == 3
            if is_meg:
                meg_label = ttk.Frame(components_frame)
                meg_label.grid(row=row, column=0, padx=8)
                ttk.Label(meg_label, text="MEG").grid(row=0, column=0)
                self.meg_type = tk.StringVar(value="11")
                ttk.Combobox(meg_label, textvariable=self.meg_type,
                             values=("121", "11"), state="readonly", width=4).grid(
                                 row=0, column=1, padx=(4, 0))
            else:
                ttk.Label(components_frame, text=str(row)).grid(
                    row=row, column=0, padx=8)
            values = []
            for column, default in enumerate(defaults, start=1):
                value = tk.StringVar(value=default)
                cell = ttk.Frame(components_frame)
                cell.grid(row=row, column=column, sticky="ew", padx=8, pady=4)
                cell.columnconfigure(0, weight=1)
                ttk.Entry(cell, textvariable=value, width=16).grid(
                    row=0, column=0, sticky="ew")
                if is_meg and column == 1:
                    ttk.Label(cell, text="mT/m").grid(row=0, column=1, padx=(4, 0))
                values.append(value)
            if is_meg:
                self.meg = values
                self.meg_slew = tk.StringVar(value="180000")
                slew_cell = ttk.Frame(components_frame)
                slew_cell.grid(row=row + 1, column=1, sticky="ew", padx=8, pady=4)
                slew_cell.columnconfigure(0, weight=1)
                ttk.Entry(slew_cell, textvariable=self.meg_slew, width=10).grid(
                    row=0, column=0, sticky="ew")
                ttk.Label(slew_cell, text="Slew (mT/m/s)").grid(
                    row=0, column=1, padx=(4, 0))
                self.meg_lobes = tk.StringVar(value="1")
                lobes_cell = ttk.Frame(components_frame)
                lobes_cell.grid(row=row, column=3, sticky="ew", padx=8, pady=4)
                lobes_cell.columnconfigure(1, weight=1)
                ttk.Label(lobes_cell, text="Lobes").grid(row=0, column=0, padx=(0, 4))
                ttk.Entry(lobes_cell, textvariable=self.meg_lobes, width=10).grid(
                    row=0, column=1, sticky="ew")
            else:
                self.components.append(values)
                gain = tk.StringVar(value="1")
                self.gain.append(gain)
                ttk.Label(components_frame, textvariable=gain).grid(
                    row=row, column=3, sticky="w", padx=8, pady=4)
                menc = tk.StringVar()
                self.menc_values.append(menc)
                ttk.Entry(components_frame, textvariable=menc, width=16,
                          state="readonly").grid(
                    row=row, column=5, sticky="ew", padx=8, pady=4)
            normalized = tk.StringVar()
            if is_meg:
                self.meg_normalized_amplitude = normalized
            else:
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
        for component in [*self.components, self.meg]:
            for value in component:
                value.trace_add("write", self.update_plot)
        self.meg_slew.trace_add("write", self.update_plot)
        self.meg_type.trace_add("write", self.update_plot)
        self.meg_lobes.trace_add("write", self.update_plot)
        for value in self.gain:
            value.trace_add("write", self.update_plot)
        self.update_plot()

    def update_plot(self, *_):
        self.canvas.delete("all")
        self.gcd_frequency.set("")
        self.duration.set("")
        self.trigger_interval.set("")
        for value in self.normalized_amplitudes:
            value.set("")
        for value in self.menc_values:
            value.set("")
        self.meg_normalized_amplitude.set("")
        try:
            components = [(float(amplitude.get()), float(frequency.get()))
                          for amplitude, frequency in self.components]
            meg = [(float(self.meg[0].get()), float(self.meg[1].get()))]
            lobes = int(self.meg_lobes.get())
            if lobes < 1:
                raise ValueError("MEG lobes must be a positive whole number")
            period, _ = acoustic_waveform(components)
            if meg[0][1] > 0:
                period = max(period, lobes / meg[0][1])
            _, samples = acoustic_waveform(components, period=period)
            amplitudes, samples = normalize_waveform(components, samples)
            component_samples = [acoustic_waveform([(amplitude, frequency)],
                                                   period=period)[1]
                                 for amplitude, (_, frequency) in zip(amplitudes, components)]
            _, physical_meg_samples = meg_waveform(
                *meg[0], float(self.meg_slew.get()),
                waveform_type=self.meg_type.get(), lobes=lobes, period=period)
            meg_amplitude = abs(meg[0][0])
            meg_samples = [(time, value / meg_amplitude if meg_amplitude else 0.0)
                           for time, value in physical_meg_samples]
            meg_peak = max(abs(value) for _, value in meg_samples)
            self.meg_normalized_amplitude.set(f"{meg_peak:.3f}")
            for value, amplitude in zip(self.normalized_amplitudes, amplitudes):
                value.set(f"{amplitude:.3f}")
            for value, amplitude, (_, frequency), gain in zip(
                    self.menc_values, amplitudes, components, self.gain):
                menc = calculate_menc(amplitude, frequency,
                                      float(gain.get()), period,
                                      physical_meg_samples)
                value.set(f"{menc:.6g}")
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
            self.status.set(f"Enter numeric amplitudes, frequencies, slew rate, "
                            f"and a positive whole number of MEG lobes. {exc}")
            return

        width = max(self.canvas.winfo_width(), 200)
        height = max(self.canvas.winfo_height(), 160)
        left, top, right, bottom = 70, 30, width - 20, height - 50
        scale = max(1.0, *(abs(value) for waveform in component_samples
                           for _, value in waveform))

        def y_position(value):
            return top + (1 - value / scale) * (bottom - top) / 2

        self.canvas.create_text((left + right) / 2, 14,
                                text="Normalized waveforms: components, sum, and MEG")
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
        for waveform, color, label, offset, dash in [
            (samples, "#1565c0", "Component sum", 0, ()),
            (meg_samples, "#e65100", f"MEG ({self.meg_type.get()})", 140, ()),
            (component_samples[0], "#2e7d32", "Signal 1", 250, (6, 3)),
            (component_samples[1], "#8e24aa", "Signal 2", 350, (3, 3)),
        ]:
            points = []
            for time, value in waveform:
                points.extend((left + (time / period) * (right - left), y_position(value)))
            self.canvas.create_line(*points, fill=color, width=2, dash=dash)
            self.canvas.create_text(left + 8 + offset, top + 12, text=label,
                                    fill=color, anchor="w")
        if any(frequency > 0 for _, frequency in components + meg):
            self.status.set(f"Plot interval: {period:.6g} s. "
                            "Zero Hz contributes zero.")
        else:
            self.status.set("All frequencies are zero; showing flat waveforms over 1 second.")


def main():
    root = tk.Tk()
    ActiveDriverMultiFrequencyGui(root)
    root.mainloop()


if __name__ == "__main__":
    main()
