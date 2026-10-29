"""Send text commands to an Active Driver from a desktop GUI."""

import ipaddress
import math
import queue
import threading
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

if __package__:
    from .udp import ActiveDriverUdp, find_adapter_for_ip
else:
    from udp import ActiveDriverUdp, find_adapter_for_ip


class ActiveDriverGui:
    def __init__(self, root):
        self.root = root
        self.events = queue.Queue()
        self.busy = False
        root.title("Active Driver")
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        frame = ttk.Frame(root, padding=12)
        frame.grid(sticky="nsew")
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(7, weight=1)
        self.fields = {}
        for row, (name, label, default) in enumerate([
            ("ad_ip", "Active Driver IP", "10.0.1.30"),
            ("ad_port", "Active Driver port", "2000"),
            ("host_ip", "Host IP (blank = auto-detect)", ""),
            ("host_port", "Host response port", "2000"),
            ("timeout", "Response timeout (seconds)", "0.2"),
            ("command", "Command", "?V"),
        ]):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=4)
            value = tk.StringVar(value=default)
            entry = ttk.Entry(frame, textvariable=value, width=36)
            entry.grid(row=row, column=1, sticky="ew", pady=4)
            self.fields[name] = value
            if name == "command":
                entry.bind("<Return>", lambda event: self.send())
                entry.focus_set()
        self.send_button = ttk.Button(frame, text="Send command", command=self.send)
        self.send_button.grid(row=6, column=1, sticky="e", pady=8)
        ttk.Label(frame, text="Response").grid(row=7, column=0, sticky="nw")
        self.response = ScrolledText(frame, width=60, height=16, state="disabled", wrap="word")
        self.response.grid(row=7, column=1, sticky="nsew")
        self.status = tk.StringVar(value="Ready")
        ttk.Label(frame, textvariable=self.status).grid(row=8, column=0, columnspan=2, sticky="w", pady=(8, 0))
        root.after(50, self.poll_events)

    def append_response(self, text):
        self.response.configure(state="normal")
        self.response.insert("end", text + "\n")
        self.response.see("end")
        self.response.configure(state="disabled")

    def send(self):
        if self.busy:
            return
        try:
            values = {name: field.get().strip() for name, field in self.fields.items()}
            ipaddress.IPv4Address(values["ad_ip"])
            if values["host_ip"]:
                ipaddress.IPv4Address(values["host_ip"])
            for name in ("ad_port", "host_port"):
                values[name] = int(values[name])
                if not 1 <= values[name] <= 65535:
                    raise ValueError("Ports must be between 1 and 65535")
            values["timeout"] = float(values["timeout"])
            if not math.isfinite(values["timeout"]) or values["timeout"] <= 0:
                raise ValueError("Response timeout must be a positive, finite number")
            if not values["command"]:
                raise ValueError("Enter a command")
            values["command"].encode("ascii")
        except ValueError as exc:
            self.status.set(f"Error: {exc}")
            return
        self.busy = True
        self.send_button.configure(state="disabled")
        self.status.set("Waiting for responses…")
        self.response.configure(state="normal")
        self.response.delete("1.0", "end")
        self.response.configure(state="disabled")
        threading.Thread(target=self.exchange, args=(values,), daemon=True).start()

    def exchange(self, values):
        try:
            host_ip = values["host_ip"]
            if not host_ip:
                _, host_ip, _ = find_adapter_for_ip(values["ad_ip"])
                if host_ip is None:
                    raise ValueError(f"No network adapter found for {values['ad_ip']}; enter a Host IP")
            received = False
            with ActiveDriverUdp(values["ad_ip"], values["ad_port"], host_ip, values["host_port"]) as driver:
                driver.SendCmd(values["command"])
                responses = driver.GetUdpResponse(values["timeout"])
                while responses != [""]:
                    for response in responses:
                        self.events.put(("response", response))
                        received = True
                    responses = driver.GetUdpResponse(values["timeout"])
            self.events.put(("done", "Ready" if received else "No response received"))
        except Exception as exc:
            self.events.put(("error", str(exc)))

    def poll_events(self):
        try:
            while True:
                kind, text = self.events.get_nowait()
                if kind == "response":
                    self.append_response(text)
                else:
                    self.busy = False
                    self.send_button.configure(state="normal")
                    self.status.set(f"Error: {text}" if kind == "error" else text)
                    if kind == "error":
                        self.append_response(f"Error: {text}")
        except queue.Empty:
            pass
        self.root.after(50, self.poll_events)


def main():
    root = tk.Tk()
    ActiveDriverGui(root)
    root.mainloop()


if __name__ == "__main__":
    main()
