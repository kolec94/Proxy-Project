"""Visible participant application; closing this window stops all traffic."""
import asyncio
import os
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from proxy_sdk.client import Client
from proxy_sdk.storage import State

DISCLOSURE = (
    "Proxy Project shares your internet connection with third-party proxy customers.\n"
    "Their requests leave through your home's public IP address. This may affect\n"
    "your data allowance, network performance, or IP reputation. Only the exact\n"
    "domains you approve below and destination port 443 are allowed in this pilot.\n\n"
    "The daily cap counts relayed request and response bytes. Actual ISP usage\n"
    "can be roughly twice that amount, plus encryption and protocol overhead.\n"
    "No compensation is promised by this software. Only join with authority\n"
    "to share this device and internet connection. You may pause or withdraw\n"
    "at any time. Closing the window stops sharing; it never starts on boot."
)


class App:
    def __init__(self, root):
        self.root = root
        root.title("Proxy Project — Participant pilot")
        root.geometry("760x680")
        self.events = queue.SimpleQueue()
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local/share")) / "ProxyProject"
        self.state = State(base / "participant.json")
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.thread.start()
        self.client = Client(self.state, status=self.events.put)
        frame = ttk.Frame(root, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Your connection stays under your control", font=("Segoe UI", 15, "bold")).pack(anchor="w")
        ttk.Label(frame, text=DISCLOSURE, justify="left", wraplength=710).pack(anchor="w", pady=12)
        self.fields = {}
        for key, label, default in [
            ("gateway", "Gateway HTTPS origin", self.state.data.get("gateway", "https://")),
            ("grant", "One-time enrollment code", ""),
            ("hosts", "Allowed domains separated by commas", ",".join(self.state.data.get("hosts", []))),
            ("cap", "Daily relay payload cap in decimal MB (1–1000)", str(self.state.data["cap"] // 1_000_000)),
        ]:
            row = ttk.Frame(frame)
            row.pack(fill="x", pady=3)
            ttk.Label(row, text=label, width=38).pack(side="left")
            var = tk.StringVar(value=default)
            ttk.Entry(row, textvariable=var, show="*" if key == "grant" else "").pack(side="left", fill="x", expand=True)
            self.fields[key] = var
        self.consent = tk.BooleanVar(value=False)
        ttk.Checkbutton(frame, text="I understand and consent to sharing under these limits.", variable=self.consent).pack(anchor="w", pady=8)
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x")
        self.enroll_button = ttk.Button(buttons, text="Enroll paused", command=self.enroll)
        self.enroll_button.pack(side="left", padx=3)
        ttk.Button(buttons, text="Start", command=lambda: self.submit(self.client.start())).pack(side="left", padx=3)
        ttk.Button(buttons, text="Pause", command=lambda: self.submit(self.client.pause())).pack(side="left", padx=3)
        ttk.Button(buttons, text="Withdraw consent", command=self.withdraw).pack(side="left", padx=3)
        self.status = tk.StringVar(value="Paused. Enrollment or explicit Start required.")
        ttk.Label(frame, textvariable=self.status, wraplength=710).pack(anchor="w", pady=12)
        self.summary = tk.StringVar()
        ttk.Label(frame, textvariable=self.summary, wraplength=710).pack(anchor="w")
        ttk.Label(frame, text="Enrolled limits are shown below. To change them, withdraw and re-enroll.\n"
                             "Editing fields alone does not change the active policy.", wraplength=710).pack(anchor="w", pady=8)
        self.closing = False
        root.protocol("WM_DELETE_WINDOW", self.quit)
        self.poll()

    def submit(self, coro):
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        def done(f):
            try:
                f.result()
            except Exception as error:
                self.events.put("Action failed: " + str(error))
        future.add_done_callback(done)
        return future

    def enroll(self):
        if not self.consent.get():
            messagebox.showinfo("Consent required", "Read the disclosure and select the consent checkbox first.")
            return
        try:
            cap = int(self.fields["cap"].get()) * 1_000_000
            hosts = [h.strip() for h in self.fields["hosts"].get().split(",") if h.strip()]
            self.submit(self.client.enroll(self.fields["gateway"].get().strip(),
                                          self.fields["grant"].get().strip(), hosts, cap))
            self.fields["grant"].set("")
        except ValueError:
            messagebox.showerror("Invalid limit", "Enter a whole number of MB from 1 to 1000.")

    def withdraw(self):
        if messagebox.askyesno("Withdraw consent", "Stop all sharing and revoke this device's credential?"):
            self.submit(self.client.withdraw())

    def poll(self):
        while not self.events.empty():
            self.status.set(self.events.get())
        d = self.state.data
        self.summary.set(f"Enrolled domains: {', '.join(d.get('hosts', [])) or 'none'}\n"
                         f"Used: {d.get('used', 0):,} / {d['cap']:,} relay bytes for UTC day {d.get('day') or 'not started'}")
        self.enroll_button.configure(state="disabled" if d.get("token") else "normal")
        if not self.closing:
            self.root.after(300, self.poll)

    def quit(self):
        self.closing = True
        self.status.set("Stopping connections…")
        future = self.submit(self.client.pause())
        def wait():
            if future.done():
                self.loop.call_soon_threadsafe(self.loop.stop)
                self.root.destroy()
            else:
                self.root.after(100, wait)
        wait()


def main():
    root = tk.Tk()
    try:
        App(root)
    except Exception:
        messagebox.showerror("Cannot start", "Participant state could not be read. Sharing has not started. Contact the pilot operator.")
        root.destroy()
        return
    root.mainloop()


if __name__ == "__main__":
    main()
