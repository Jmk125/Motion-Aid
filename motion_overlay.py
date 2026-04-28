"""
Motion Sickness Mitigation Overlay  (tkinter edition)
======================================================
Fullscreen transparent overlay — dots float over your desktop driven by
Phyphox accelerometer/gyroscope data over local HTTP.

Requirements:
    pip install requests

(tkinter ships with Python on Windows — no extra install needed)

Phyphox Setup:
    - Open Phyphox → "Acceleration without g"
    - Tap ⋮ → Allow remote access
    - Note the IP shown (e.g. 192.168.1.42) and enter it in the settings panel

Controls:
    - Gear icon (bottom-right) → open/close settings
    - ESC → quit
"""

import tkinter as tk
import threading
import time
import math
import random
import json
import os
import sys

try:
    import requests
except ImportError:
    sys.exit("Please install requests:  pip install requests")

# ── Transparent color (must match canvas bg) ─────────────────────────────────
CHROMA = "black"   # tkinter makes this color fully transparent on Windows

# ── Settings ──────────────────────────────────────────────────────────────────
DEFAULT_SETTINGS = {
    "phyphox_ip":         "192.168.1.100",
    "phyphox_port":       "8080",
    "dot_count":          55,
    "dot_size":           5,
    "dot_opacity":        210,
    "dot_color":          "#ffffff",
    "visual_style":       "Dots",
    "motion_sensitivity": 3.5,
    "smoothing":          0.10,
    "parallax_layers":    3,
    "drift_speed":        0.35,
    "rotation_enabled":   True,
    "poll_rate_hz":       20,
    "glow_enabled":       False,
    "damping_ratio":      1.05,
    "sensor_tau":         0.18,
    "max_accel":          4.0,
    "swap_xy":            False,
    "invert_x":           False,
    "invert_y":           False,
    "gear_x":             -1,   # -1 = use default bottom-right
    "gear_y":             -1,
}

SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "motion_overlay_settings.json")

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE) as f:
                return {**DEFAULT_SETTINGS, **json.load(f)}
        except Exception:
            pass
    return dict(DEFAULT_SETTINGS)

def save_settings(s):
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump(s, f, indent=2)
    except Exception:
        pass

# ── Phyphox poller ────────────────────────────────────────────────────────────
class PhyphoxPoller:
    def __init__(self, settings):
        self.s         = settings
        self.acc_x     = 0.0
        self.acc_y     = 0.0
        self.gyr_z     = 0.0
        self.connected = False
        self._running  = True
        threading.Thread(target=self._loop, daemon=True).start()

    def _url(self):
        return (f"http://{self.s['phyphox_ip']}:{self.s['phyphox_port']}"
                f"/get?accX&accY&gyrZ")

    def _loop(self):
        while self._running:
            try:
                r    = requests.get(self._url(), timeout=0.4)
                buf  = r.json()["buffer"]
                self.acc_x     = (buf.get("accX", {}).get("buffer") or [0])[-1] or 0.0
                self.acc_y     = (buf.get("accY", {}).get("buffer") or [0])[-1] or 0.0
                self.gyr_z     = (buf.get("gyrZ", {}).get("buffer") or [0])[-1] or 0.0
                self.connected = True
            except Exception:
                self.connected = False
            time.sleep(1.0 / max(1, self.s.get("poll_rate_hz", 20)))

    def stop(self):
        self._running = False

# ── Dot particle ──────────────────────────────────────────────────────────────
class Dot:
    def __init__(self, sw, sh, layer, n_layers):
        self.sw     = sw
        self.sh     = sh
        self.x      = random.uniform(0, sw)
        self.y      = random.uniform(0, sh)
        self.vx     = 0.0
        self.vy     = 0.0
        self.depth  = 1.0 - (layer / max(1, n_layers)) * 0.7

    def update(self, dx, dy, rot, dt, s):
        sens  = s["motion_sensitivity"]
        smth  = s["smoothing"]
        drift = s["drift_speed"]
        df    = self.depth

        # Velocity-driven inertial cue:
        # sustained accel keeps dots moving, then they damp quickly when accel drops.
        tgt_vx = -dx * sens * df * 180.0
        tgt_vy =  dy * sens * df * 180.0
        response_tau = max(0.03, 0.28 - smth * 0.22)  # higher smoothing => quicker response
        blend = 1.0 - math.exp(-dt / response_tau)
        self.vx += (tgt_vx - self.vx) * blend
        self.vy += (tgt_vy - self.vy) * blend

        if s["rotation_enabled"] and abs(rot) > 0.03:
            cx, cy = self.sw / 2, self.sh / 2
            rx, ry = self.x - cx, self.y - cy
            rot_gain = sens * df * 0.020
            self.vx += (-ry * rot * rot_gain)
            self.vy += ( rx * rot * rot_gain)

        drag = max(0.1, float(s.get("damping_ratio", 1.05))) * 1.8
        decay = math.exp(-drag * dt)
        self.vx *= decay
        self.vy *= decay

        self.x += self.vx * dt
        self.y += self.vy * dt - (drift * df * 20.0 * dt)

        # Wrap position
        m = 50
        if self.x < -m:
            self.x = self.sw + m
        elif self.x > self.sw + m:
            self.x = -m
        if self.y < -m:
            self.y = self.sh + m
        elif self.y > self.sh + m:
            self.y = -m

# ── Colour helpers ────────────────────────────────────────────────────────────
def hex_to_rgb(h):
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

def blend_to_black(hex_col, opacity_0_1):
    r, g, b = hex_to_rgb(hex_col)
    r2 = max(1, int(r * opacity_0_1))
    g2 = max(1, int(g * opacity_0_1))
    b2 = max(1, int(b * opacity_0_1))
    return f"#{r2:02x}{g2:02x}{b2:02x}"

class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip = None
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")

    def _show(self, _event=None):
        if self.tip or not self.text:
            return
        x = self.widget.winfo_rootx() + 14
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self.tip = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.attributes("-topmost", True)
        tw.transient(self.widget.winfo_toplevel())
        tw.wm_geometry(f"+{x}+{y}")
        tw.lift()
        tk.Label(tw, text=self.text, justify="left",
                 bg="#1d1d2b", fg="#e8e8ff",
                 relief="solid", bd=1, padx=6, pady=4,
                 font=("Segoe UI", 8)).pack()

    def _hide(self, _event=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None

# ── Settings window ───────────────────────────────────────────────────────────
class SettingsWindow:
    COLORS = [
        ("#ffffff", "White"),
        ("#b4dcff", "Ice Blue"),
        ("#ffdca0", "Warm"),
        ("#a0ffcc", "Mint"),
        ("#ffa0c8", "Rose"),
    ]

    def __init__(self, parent, settings, poller, on_rebuild, on_gear_move, on_quit, sw, sh):
        self.settings   = settings
        self.poller     = poller
        self.on_rebuild  = on_rebuild
        self.on_gear_move = on_gear_move
        self.on_quit      = on_quit
        self.SW, self.SH  = sw, sh
        self._tips        = []

        self.win = tk.Toplevel(parent)
        self.win.title("Motion Overlay Settings")
        self.win.configure(bg="#12121e")
        self.win.resizable(False, False)
        self.win.attributes("-topmost", True)
        self.win.overrideredirect(True)  # hide OS title bar for cleaner look
        self.win.protocol("WM_DELETE_WINDOW", self.close)

        self._status_job = None
        self._build()
        self._update_status()

    def _build(self):
        w   = self.win
        sw  = self.SW
        sh  = self.SH
        PAD = dict(padx=14, pady=4)

        # ── Fixed header (title + status) ────────────────────────────────────
        header = tk.Frame(w, bg="#12121e")
        header.pack(fill="x")

        tk.Label(header, text="⚙  Motion Overlay Settings",
                 bg="#12121e", fg="#c8dcff",
                 font=("Segoe UI", 13, "bold")).pack(pady=(14, 2))

        self.status_var = tk.StringVar(value="Checking…")
        self.status_lbl = tk.Label(header, textvariable=self.status_var,
                                   bg="#12121e", fg="#50dc78",
                                   font=("Segoe UI", 9))
        self.status_lbl.pack(pady=(0, 6))
        # Drag window by header (since we removed the native title bar)
        header.bind("<ButtonPress-1>", self._start_drag)
        header.bind("<B1-Motion>", self._drag_win)
        for child in header.winfo_children():
            child.bind("<ButtonPress-1>", self._start_drag)
            child.bind("<B1-Motion>", self._drag_win)

        tk.Frame(header, bg="#2a2a40", height=1).pack(fill="x", padx=14)

        # ── Fixed footer (save/close) ─────────────────────────────────────────
        footer = tk.Frame(w, bg="#12121e")
        footer.pack(side="bottom", fill="x")
        tk.Frame(footer, bg="#2a2a40", height=1).pack(fill="x", padx=14)
        bf = tk.Frame(footer, bg="#12121e")
        bf.pack(pady=10)
        bsave = tk.Button(bf, text="💾  Save", bg="#3256a0", fg="#ddeeff",
                          font=("Segoe UI", 10), relief="flat", padx=10, pady=4,
                          cursor="hand2", command=self._save)
        bsave.pack(side="left", padx=6)
        self._tip(bsave, "Save all current settings to motion_overlay_settings.json.")
        bclose = tk.Button(bf, text="✕  Close", bg="#2a1a2a", fg="#c080c0",
                           font=("Segoe UI", 10), relief="flat", padx=10, pady=4,
                           cursor="hand2", command=self.close)
        bclose.pack(side="left", padx=6)
        self._tip(bclose, "Close the settings window.")
        bexit = tk.Button(bf, text="⏻  Exit App", bg="#602020", fg="#ffd0d0",
                          font=("Segoe UI", 10), relief="flat", padx=10, pady=4,
                          cursor="hand2", command=self.on_quit)
        bexit.pack(side="left", padx=6)
        self._tip(bexit, "Stop the overlay application.")
        self._save_lbl = tk.Label(footer, text="", bg="#12121e", fg="#70e090",
                                  font=("Segoe UI", 9))
        self._save_lbl.pack(pady=(0, 6))

        # ── Scrollable body ───────────────────────────────────────────────────
        # Canvas + scrollbar sit between header and footer
        scroll_frame = tk.Frame(w, bg="#12121e")
        scroll_frame.pack(fill="both", expand=True)

        scrollbar = tk.Scrollbar(scroll_frame, orient="vertical",
                                 bg="#2a2a44", troughcolor="#12121e",
                                 activebackground="#5060a0")
        scrollbar.pack(side="right", fill="y")

        self._scroll_canvas = tk.Canvas(scroll_frame, bg="#12121e",
                                        highlightthickness=0,
                                        yscrollcommand=scrollbar.set)
        self._scroll_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self._scroll_canvas.yview)

        # Inner frame that holds all the actual content
        inner = tk.Frame(self._scroll_canvas, bg="#12121e")
        self._scroll_canvas_window = self._scroll_canvas.create_window(
            (0, 0), window=inner, anchor="nw")

        # Resize the scroll region when content changes
        def on_inner_configure(e):
            self._scroll_canvas.configure(
                scrollregion=self._scroll_canvas.bbox("all"))
        inner.bind("<Configure>", on_inner_configure)

        # Stretch inner frame to fill canvas width
        def on_canvas_configure(e):
            self._scroll_canvas.itemconfig(
                self._scroll_canvas_window, width=e.width)
        self._scroll_canvas.bind("<Configure>", on_canvas_configure)

        # Mouse wheel scrolling
        def on_mousewheel(e):
            self._scroll_canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        self._scroll_canvas.bind("<MouseWheel>", on_mousewheel)
        inner.bind("<MouseWheel>", on_mousewheel)

        # Now build all content into `inner` instead of `w`
        c = inner  # alias — all content packs into here

        # ── IP / port ─────────────────────────────────────────────────────────
        tk.Frame(c, bg="#2a2a40", height=1).pack(fill="x", padx=14, pady=(10, 4))
        row0 = tk.Frame(c, bg="#12121e")
        row0.pack(fill="x", **PAD)
        tk.Label(row0, text="Phyphox IP", bg="#12121e", fg="#b0b0c0",
                 font=("Segoe UI", 10), width=13, anchor="w").pack(side="left")
        self.ip_var = tk.StringVar(value=self.settings["phyphox_ip"])
        self.ip_var.trace_add("write",
            lambda *_: self.settings.update({"phyphox_ip": self.ip_var.get()}))
        tk.Entry(row0, textvariable=self.ip_var, bg="#1e1e30", fg="#e0e0f0",
                 insertbackground="white", relief="flat", width=16,
                 font=("Segoe UI", 10)).pack(side="left", padx=(0, 8))
        tk.Label(row0, text="Port", bg="#12121e", fg="#b0b0c0",
                 font=("Segoe UI", 10)).pack(side="left")
        self.port_var = tk.StringVar(value=self.settings["phyphox_port"])
        self.port_var.trace_add("write",
            lambda *_: self.settings.update({"phyphox_port": self.port_var.get()}))
        tk.Entry(row0, textvariable=self.port_var, bg="#1e1e30", fg="#e0e0f0",
                 insertbackground="white", relief="flat", width=6,
                 font=("Segoe UI", 10)).pack(side="left")

        tk.Frame(c, bg="#2a2a40", height=1).pack(fill="x", padx=14, pady=6)

        # ── Visual style ───────────────────────────────────────────────────────
        style_row = tk.Frame(c, bg="#12121e")
        style_row.pack(fill="x", padx=14, pady=2)
        tk.Label(style_row, text="Visual Style", bg="#12121e", fg="#b0b0c0",
                 font=("Segoe UI", 10), width=13, anchor="w").pack(side="left")
        self._style_var = tk.StringVar(value=self.settings.get("visual_style", "Dots"))
        style_menu = tk.OptionMenu(style_row, self._style_var, "Dots", "Snowflakes", "Grid")
        style_menu.config(bg="#1e1e30", fg="#e0e0f0", activebackground="#2a2a44",
                          activeforeground="#ffffff", relief="flat", highlightthickness=0,
                          font=("Segoe UI", 10), width=12)
        style_menu["menu"].config(bg="#1e1e30", fg="#e0e0f0",
                                  activebackground="#2a2a44", activeforeground="#ffffff")
        style_menu.pack(side="left")
        self._tip(style_menu, "Choose between particles or a single moving grid.")
        def on_style(*_):
            self.settings["visual_style"] = self._style_var.get()
            self.on_rebuild()
        self._style_var.trace_add("write", on_style)

        # ── Sliders ───────────────────────────────────────────────────────────
        self._svars = {}
        sliders = [
            ("Dot Count",          "dot_count",          10,  200, True),
            ("Dot Size",           "dot_size",            2,   22,  True),
            ("Opacity",            "dot_opacity",         20,  255, True),
            ("Motion Sensitivity", "motion_sensitivity",  0.5, 10.0,False),
            ("Smoothing",          "smoothing",           0.01,1.0, False),
            ("Damping Ratio",      "damping_ratio",       0.7, 1.8, False),
            ("Drift Speed",        "drift_speed",         0.0, 2.5, False),
            ("Parallax Layers",    "parallax_layers",     1,   5,   True),
            ("Poll Rate (Hz)",     "poll_rate_hz",        5,   60,  True),
            ("Sensor Filter Tau",  "sensor_tau",          0.05,0.7, False),
            ("Max Accel (m/s²)",   "max_accel",           1.0, 12.0,False),
        ]
        for args in sliders:
            self._make_slider(c, *args, PAD)

        tk.Frame(c, bg="#2a2a40", height=1).pack(fill="x", padx=14, pady=6)

        # ── Toggles ───────────────────────────────────────────────────────────
        tog = tk.Frame(c, bg="#12121e")
        tog.pack(fill="x", **PAD)
        self._rot_var = tk.BooleanVar(value=self.settings["rotation_enabled"])
        self._rot_var.trace_add("write",
            lambda *_: self.settings.update({"rotation_enabled": self._rot_var.get()}))
        rot_cb = tk.Checkbutton(tog, text="Rotation Effect", variable=self._rot_var,
                                bg="#12121e", fg="#b0b0c0", selectcolor="#1e1e30",
                                activebackground="#12121e", activeforeground="#c8dcff",
                                font=("Segoe UI", 10))
        rot_cb.pack(side="left", padx=(0, 20))
        self._tip(rot_cb, "Use gyroscope Z to add turn-based rotational flow.")

        self._glow_var = tk.BooleanVar(value=self.settings.get("glow_enabled", False))
        self._glow_var.trace_add("write",
            lambda *_: self.settings.update({"glow_enabled": self._glow_var.get()}))
        glow_cb = tk.Checkbutton(tog, text="Glow Effect", variable=self._glow_var,
                                 bg="#12121e", fg="#b0b0c0", selectcolor="#1e1e30",
                                 activebackground="#12121e", activeforeground="#c8dcff",
                                 font=("Segoe UI", 10))
        glow_cb.pack(side="left")
        self._tip(glow_cb, "Draw soft glow halos around each dot.")

        tk.Frame(c, bg="#2a2a40", height=1).pack(fill="x", padx=14, pady=6)

        # ── Axis calibration ──────────────────────────────────────────────────
        tk.Label(c, text="Sensor Axis Calibration", bg="#12121e", fg="#b0b0c0",
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=14)
        tk.Label(c, text="Use these if motion goes the wrong way for your phone mount.",
                 bg="#12121e", fg="#707090", font=("Segoe UI", 8)).pack(anchor="w", padx=14)

        ac = tk.Frame(c, bg="#12121e")
        ac.pack(fill="x", padx=14, pady=4)

        self._swap_xy_var = tk.BooleanVar(value=self.settings.get("swap_xy", False))
        self._swap_xy_var.trace_add("write",
            lambda *_: self.settings.update({"swap_xy": self._swap_xy_var.get()}))
        swap_cb = tk.Checkbutton(ac, text="Swap X/Y", variable=self._swap_xy_var,
                                 bg="#12121e", fg="#b0b0c0", selectcolor="#1e1e30",
                                 activebackground="#12121e", activeforeground="#c8dcff",
                                 font=("Segoe UI", 10))
        swap_cb.pack(side="left", padx=(0, 16))
        self._tip(swap_cb, "Swap sensor horizontal/vertical axes.")

        self._inv_x_var = tk.BooleanVar(value=self.settings.get("invert_x", False))
        self._inv_x_var.trace_add("write",
            lambda *_: self.settings.update({"invert_x": self._inv_x_var.get()}))
        invx_cb = tk.Checkbutton(ac, text="Invert X", variable=self._inv_x_var,
                                 bg="#12121e", fg="#b0b0c0", selectcolor="#1e1e30",
                                 activebackground="#12121e", activeforeground="#c8dcff",
                                 font=("Segoe UI", 10))
        invx_cb.pack(side="left", padx=(0, 16))
        self._tip(invx_cb, "Flip left/right motion direction.")

        self._inv_y_var = tk.BooleanVar(value=self.settings.get("invert_y", False))
        self._inv_y_var.trace_add("write",
            lambda *_: self.settings.update({"invert_y": self._inv_y_var.get()}))
        invy_cb = tk.Checkbutton(ac, text="Invert Y", variable=self._inv_y_var,
                                 bg="#12121e", fg="#b0b0c0", selectcolor="#1e1e30",
                                 activebackground="#12121e", activeforeground="#c8dcff",
                                 font=("Segoe UI", 10))
        invy_cb.pack(side="left")
        self._tip(invy_cb, "Flip up/down motion direction.")

        tk.Frame(c, bg="#2a2a40", height=1).pack(fill="x", padx=14, pady=6)

        # ── Color swatches ────────────────────────────────────────────────────
        tk.Label(c, text="Dot Color", bg="#12121e", fg="#b0b0c0",
                 font=("Segoe UI", 10)).pack(anchor="w", padx=14)
        sf = tk.Frame(c, bg="#12121e")
        sf.pack(padx=14, pady=4, anchor="w")
        self._swatch_btns = []
        for hex_col, name in self.COLORS:
            btn = tk.Button(sf, bg=hex_col, width=3, height=1,
                            relief="flat", cursor="hand2",
                            command=lambda h=hex_col: self._set_color(h))
            btn.pack(side="left", padx=3)
            self._swatch_btns.append((btn, hex_col))
        self._refresh_swatches()

        tk.Frame(c, bg="#2a2a40", height=1).pack(fill="x", padx=14, pady=6)

        # ── Gear icon position ────────────────────────────────────────────────
        tk.Label(c, text="⚙  Icon Position",
                 bg="#12121e", fg="#b0b0c0",
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=14, pady=(4, 0))
        tk.Label(c, text="Drag the ⚙ icon directly on screen, or use the sliders below.",
                 bg="#12121e", fg="#707090",
                 font=("Segoe UI", 8)).pack(anchor="w", padx=14, pady=(0, 6))

        gear_frame = tk.Frame(c, bg="#12121e")
        gear_frame.pack(fill="x", padx=14, pady=2)

        # X slider
        xf = tk.Frame(gear_frame, bg="#12121e")
        xf.pack(fill="x")
        xtop = tk.Frame(xf, bg="#12121e")
        xtop.pack(fill="x")
        tk.Label(xtop, text="X Position", bg="#12121e", fg="#b0b0c0",
                 font=("Segoe UI", 9), anchor="w").pack(side="left")
        self._gx_lbl = tk.Label(xtop, bg="#12121e", fg="#82b4ff",
                                 font=("Segoe UI", 9, "bold"), width=7, anchor="e")
        self._gx_lbl.pack(side="right")
        cur_gx = self.settings.get("gear_x", -1)
        if cur_gx < 0: cur_gx = sw - 30
        self._gx_var = tk.DoubleVar(value=cur_gx)
        def on_gx(v):
            val = int(round(float(v)))
            self.settings["gear_x"] = val
            self._gx_lbl.config(text=str(val))
            self.on_gear_move(val, self.settings.get("gear_y", -1))
        tk.Scale(xf, variable=self._gx_var, from_=10, to=sw - 10,
                 orient="horizontal", resolution=1,
                 bg="#12121e", fg="#b0b0c0", troughcolor="#2a2a44",
                 highlightthickness=0, sliderrelief="flat",
                 activebackground="#82b4ff",
                 command=on_gx, showvalue=False, length=300).pack(fill="x")
        self._gx_lbl.config(text=str(int(cur_gx)))

        # Y slider
        yf = tk.Frame(gear_frame, bg="#12121e")
        yf.pack(fill="x")
        ytop = tk.Frame(yf, bg="#12121e")
        ytop.pack(fill="x")
        tk.Label(ytop, text="Y Position", bg="#12121e", fg="#b0b0c0",
                 font=("Segoe UI", 9), anchor="w").pack(side="left")
        self._gy_lbl = tk.Label(ytop, bg="#12121e", fg="#82b4ff",
                                 font=("Segoe UI", 9, "bold"), width=7, anchor="e")
        self._gy_lbl.pack(side="right")
        cur_gy = self.settings.get("gear_y", -1)
        if cur_gy < 0: cur_gy = sh - 30
        self._gy_var = tk.DoubleVar(value=cur_gy)
        def on_gy(v):
            val = int(round(float(v)))
            self.settings["gear_y"] = val
            self._gy_lbl.config(text=str(val))
            self.on_gear_move(self.settings.get("gear_x", -1), val)
        tk.Scale(yf, variable=self._gy_var, from_=10, to=sh - 10,
                 orient="horizontal", resolution=1,
                 bg="#12121e", fg="#b0b0c0", troughcolor="#2a2a44",
                 highlightthickness=0, sliderrelief="flat",
                 activebackground="#82b4ff",
                 command=on_gy, showvalue=False, length=300).pack(fill="x")
        self._gy_lbl.config(text=str(int(cur_gy)))

        # Bottom padding inside scroll area
        tk.Frame(c, bg="#12121e", height=10).pack()

        # Set a sensible fixed window height so it fits on screen
        win_h = min(sh - 80, 680)
        self.win.geometry(f"360x{win_h}")

    def _make_slider(self, parent, label, key, lo, hi, is_int, PAD):
        frame = tk.Frame(parent, bg="#12121e")
        frame.pack(fill="x", padx=14, pady=2)
        top   = tk.Frame(frame, bg="#12121e")
        top.pack(fill="x")
        tk.Label(top, text=label, bg="#12121e", fg="#b0b0c0",
                 font=("Segoe UI", 9), anchor="w").pack(side="left")
        val_lbl = tk.Label(top, bg="#12121e", fg="#82b4ff",
                           font=("Segoe UI", 9, "bold"), width=7, anchor="e")
        val_lbl.pack(side="right")

        var = tk.DoubleVar(value=self.settings[key])
        self._svars[key] = var

        def on_change(v, k=key, il=is_int, vl=val_lbl):
            val = int(round(float(v))) if il else round(float(v), 3)
            self.settings[k] = val
            vl.config(text=str(val))
            if k in ("dot_count", "parallax_layers"):
                self.on_rebuild()

        scale = tk.Scale(frame, variable=var, from_=lo, to=hi, orient="horizontal",
                         resolution=(1 if is_int else 0.01),
                         bg="#12121e", fg="#b0b0c0", troughcolor="#2a2a44",
                         highlightthickness=0, sliderrelief="flat",
                         activebackground="#82b4ff",
                         command=on_change, showvalue=False, length=300)
        scale.pack(fill="x")
        self._tip(scale, self._slider_tip(key))

        v0 = self.settings[key]
        val_lbl.config(text=str(int(v0) if is_int else round(v0, 3)))

    def _slider_tip(self, key):
        tips = {
            "dot_count": "Number of particles on screen.",
            "dot_size": "Base dot radius before depth scaling.",
            "dot_opacity": "Overall particle brightness/opacity.",
            "motion_sensitivity": "How strongly sensor motion drives dot movement.",
            "smoothing": "Responsiveness of motion velocity tracking.",
            "damping_ratio": "How quickly movement decays after motion subsides.",
            "drift_speed": "Ambient upward drift speed.",
            "parallax_layers": "Depth layers for parallax effect.",
            "poll_rate_hz": "How often Phyphox data is requested.",
            "sensor_tau": "Sensor low-pass time constant (higher = steadier).",
            "max_accel": "Clamp on acceleration spikes (m/s²).",
        }
        return tips.get(key, "")

    def _tip(self, widget, text):
        self._tips.append(ToolTip(widget, text))

    def _start_drag(self, event):
        self._drag_off_x = event.x_root - self.win.winfo_x()
        self._drag_off_y = event.y_root - self.win.winfo_y()

    def _drag_win(self, event):
        x = event.x_root - getattr(self, "_drag_off_x", 0)
        y = event.y_root - getattr(self, "_drag_off_y", 0)
        self.win.geometry(f"+{x}+{y}")

    def sync_gear_sliders(self, gx, gy):
        """Called from outside when gear is dragged on canvas."""
        try:
            self._gx_var.set(gx)
            self._gy_var.set(gy)
            self._gx_lbl.config(text=str(int(gx)))
            self._gy_lbl.config(text=str(int(gy)))
        except Exception:
            pass

    def _set_color(self, h):
        self.settings["dot_color"] = h
        self._refresh_swatches()

    def _refresh_swatches(self):
        cur = self.settings.get("dot_color", "#ffffff")
        for btn, h in self._swatch_btns:
            btn.config(relief="solid" if h == cur else "flat",
                       bd=2 if h == cur else 0)

    def _save(self):
        save_settings(self.settings)
        self._save_lbl.config(text="✓ Saved!")
        self.win.after(2000, lambda: self._save_lbl.config(text=""))

    def _update_status(self):
        if not self.win.winfo_exists():
            return
        if self.poller.connected:
            self.status_var.set(
                f"● Connected  |  "
                f"ax={self.poller.acc_x:+.2f}  "
                f"ay={self.poller.acc_y:+.2f}  "
                f"gz={self.poller.gyr_z:+.2f}")
            self.status_lbl.config(fg="#50dc78")
        else:
            self.status_var.set("● No signal — check IP and start Phyphox remote")
            self.status_lbl.config(fg="#e06060")
        self._status_job = self.win.after(500, self._update_status)

    def close(self):
        if self._status_job:
            try:
                self.win.after_cancel(self._status_job)
            except Exception:
                pass
        try:
            self.win.destroy()
        except Exception:
            pass

# ── Main overlay app ──────────────────────────────────────────────────────────
class OverlayApp:
    def __init__(self):
        self.settings      = load_settings()
        self.poller        = PhyphoxPoller(self.settings)
        self.settings_win  = None

        self.sdx = self.sdy = self.srot = 0.0
        self.cue_x = self.cue_y = 0.0
        self._dots    = []
        self._dot_ids = {}
        self._grid_ids = []
        self._grid_phase_x = 0.0
        self._grid_phase_y = 0.0
        self._prev_count  = -1
        self._prev_layers = -1
        self._prev_style  = None

        self._build_window()
        self._build_dots()
        self._last_t = time.perf_counter()
        self._loop()
        self.root.mainloop()

    # ── Window ────────────────────────────────────────────────────────────────
    def _build_window(self):
        self.root = tk.Tk()
        self.root.title("MotionOverlay")

        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.SW, self.SH = sw, sh

        self.root.geometry(f"{sw}x{sh}+0+0")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-transparentcolor", CHROMA)
        self.root.configure(bg=CHROMA)

        self.canvas = tk.Canvas(self.root, width=sw, height=sh,
                                bg=CHROMA, highlightthickness=0)
        self.canvas.pack()

        # Gear button — position from settings, default bottom-right
        gx = self.settings.get("gear_x", -1)
        gy = self.settings.get("gear_y", -1)
        if gx < 0: gx = sw - 30
        if gy < 0: gy = sh - 30
        self._gear_x = gx
        self._gear_y = gy
        self._gear_dragging  = False
        self._gear_drag_off  = (0, 0)
        self._gear_did_drag  = False

        self._gear = self.canvas.create_text(
            gx, gy, text="⚙",
            fill="#6878a0", font=("Segoe UI Symbol", 22), tags="gear")

        self.canvas.tag_bind("gear", "<Enter>",
            lambda e: self.canvas.itemconfig("gear", fill="#c8dcff"))
        self.canvas.tag_bind("gear", "<Leave>",
            lambda e: self.canvas.itemconfig("gear", fill="#6878a0"))
        self.canvas.tag_bind("gear", "<ButtonPress-1>",   self._gear_press)
        self.canvas.tag_bind("gear", "<B1-Motion>",       self._gear_drag)
        self.canvas.tag_bind("gear", "<ButtonRelease-1>", self._gear_release)

        self.root.bind("<Escape>", lambda e: self._quit())

    # ── Gear drag ────────────────────────────────────────────────────────────
    def _gear_press(self, event):
        self._gear_dragging = True
        self._gear_did_drag = False
        self._gear_drag_off = (event.x - self._gear_x, event.y - self._gear_y)

    def _gear_drag(self, event):
        self._gear_did_drag = True
        nx = max(10, min(self.SW - 10, event.x - self._gear_drag_off[0]))
        ny = max(10, min(self.SH - 10, event.y - self._gear_drag_off[1]))
        self._move_gear(nx, ny)

    def _gear_release(self, event):
        self._gear_dragging = False
        if not self._gear_did_drag:
            # it was a click, not a drag — open settings
            self._toggle_settings()

    def _move_gear(self, x, y):
        self._gear_x = x
        self._gear_y = y
        self.settings["gear_x"] = x
        self.settings["gear_y"] = y
        self.canvas.coords(self._gear, x, y)
        # keep settings sliders in sync if panel is open
        if self.settings_win and self.settings_win.win.winfo_exists():
            self.settings_win.sync_gear_sliders(x, y)

    # ── Dots ──────────────────────────────────────────────────────────────────
    def _build_dots(self):
        for ids in self._dot_ids.values():
            for i in ids:
                self.canvas.delete(i)
        for gid in self._grid_ids:
            self.canvas.delete(gid)
        self._dots    = []
        self._dot_ids = {}
        self._grid_ids = []

        n      = self.settings["dot_count"]
        layers = max(1, self.settings["parallax_layers"])
        style  = self.settings.get("visual_style", "Dots")
        self._prev_count  = n
        self._prev_layers = layers
        self._prev_style  = style

        if style == "Grid":
            self._build_grid()
            return

        for i in range(n):
            d = Dot(self.SW, self.SH, i % layers, layers)
            self._dots.append(d)
            self._dot_ids[id(d)] = self._make_items(d)

    def _make_items(self, dot):
        style = self.settings.get("visual_style", "Dots")
        ids = []
        if style == "Snowflakes":
            ids.append(self.canvas.create_text(
                dot.x, dot.y, text="❄", fill="#ffffff",
                font=("Segoe UI Symbol", max(8, int(self.settings["dot_size"] * 2.2)))))
            return ids
        if self.settings.get("glow_enabled", True):
            for _ in range(3):
                ids.append(self.canvas.create_oval(0, 0, 1, 1,
                                                   outline="", fill=CHROMA))
        else:
            ids.append(self.canvas.create_oval(0, 0, 1, 1,
                                               outline="", fill=CHROMA))
        return ids

    def _redraw_dot(self, dot):
        ids   = self._dot_ids[id(dot)]
        s     = self.settings
        style = s.get("visual_style", "Dots")
        size  = s["dot_size"]
        base  = s["dot_color"]
        op    = s["dot_opacity"] / 255.0
        depth = dot.depth
        x, y  = dot.x, dot.y
        r     = max(1, int(size * (0.4 + depth * 0.6)))
        do    = op * (0.35 + depth * 0.65)
        glow  = s.get("glow_enabled", True)

        if style == "Snowflakes":
            col = blend_to_black(base, do)
            self.canvas.coords(ids[0], x, y)
            self.canvas.itemconfig(
                ids[0], text="❄", fill=col,
                font=("Segoe UI Symbol", max(8, int(size * (1.5 + depth)))))
            return

        if glow and len(ids) == 3:
            for oid, (ring_r, ring_op) in zip(
                    ids, [(int(r * 2.0), do * 0.28), (int(r * 1.45), do * 0.55), (r, do)]):
                # hide near-black rings with chroma so they go transparent
                # rather than rendering as a dark halo
                col = blend_to_black(base, ring_op) if ring_op >= 0.08 else CHROMA
                self.canvas.coords(oid,
                    x - ring_r, y - ring_r, x + ring_r, y + ring_r)
                self.canvas.itemconfig(oid, fill=col)
        else:
            col = blend_to_black(base, do)
            self.canvas.coords(ids[0], x - r, y - r, x + r, y + r)
            self.canvas.itemconfig(ids[0], fill=col)

    def _build_grid(self):
        s = self.settings
        spacing = max(20, int(s["dot_size"] * 10))
        color = blend_to_black(s["dot_color"], s["dot_opacity"] / 255.0 * 0.55)
        self._grid_phase_x = 0.0
        self._grid_phase_y = 0.0
        margin = spacing * 3
        for x in range(-margin, self.SW + margin + 1, spacing):
            self._grid_ids.append(self.canvas.create_line(
                x, -margin, x, self.SH + margin, fill=color, width=1))
        for y in range(-margin, self.SH + margin + 1, spacing):
            self._grid_ids.append(self.canvas.create_line(
                -margin, y, self.SW + margin, y, fill=color, width=1))

    def _redraw_grid(self, cue_x, cue_y, dt):
        if not self._grid_ids:
            return
        s = self.settings
        spacing = max(20, int(s["dot_size"] * 10))
        color = blend_to_black(s["dot_color"], s["dot_opacity"] / 255.0 * 0.55)
        self._grid_phase_x = (self._grid_phase_x - cue_x * s["motion_sensitivity"] * dt * 45.0) % spacing
        self._grid_phase_y = (self._grid_phase_y + cue_y * s["motion_sensitivity"] * dt * 45.0) % spacing
        margin = spacing * 3

        idx = 0
        x0 = -margin + self._grid_phase_x
        x = x0
        while x <= self.SW + margin:
            lid = self._grid_ids[idx]
            self.canvas.coords(lid, x, -margin, x, self.SH + margin)
            self.canvas.itemconfig(lid, fill=color)
            idx += 1
            x += spacing
        y0 = -margin + self._grid_phase_y
        y = y0
        while y <= self.SH + margin and idx < len(self._grid_ids):
            lid = self._grid_ids[idx]
            self.canvas.coords(lid, -margin, y, self.SW + margin, y)
            self.canvas.itemconfig(lid, fill=color)
            idx += 1
            y += spacing

    # ── Loop ─────────────────────────────────────────────────────────────────
    def _loop(self):
        now = time.perf_counter()
        dt  = min(now - self._last_t, 0.05)
        self._last_t = now

        s     = self.settings
        ax = self.poller.acc_x
        ay = self.poller.acc_y

        if s.get("swap_xy", False):
            ax, ay = ay, ax
        if s.get("invert_x", False):
            ax = -ax
        if s.get("invert_y", False):
            ay = -ay

        accel_cap = max(0.5, float(s.get("max_accel", 4.0)))
        raw_x = max(-accel_cap, min(accel_cap, ax))
        raw_y = max(-accel_cap, min(accel_cap, ay))
        raw_r = self.poller.gyr_z if s["rotation_enabled"] else 0.0

        # Framerate-independent sensor low-pass filter:
        # alpha = 1 - exp(-dt / tau). Larger tau => steadier, less twitchy.
        tau = max(0.02, float(s.get("sensor_tau", 0.18)))
        sa  = 1.0 - math.exp(-dt / tau)
        self.sdx  += (raw_x - self.sdx)  * sa
        self.sdy  += (raw_y - self.sdy)  * sa
        self.srot += (raw_r - self.srot) * sa

        # Inertial cue integrator:
        # - integrates acceleration into a short-lived "motion intent"
        # - suppresses tiny opposite-sign blips that cause rebound feel
        # - washes out to zero when acceleration is gone
        ix, iy = self.sdx, self.sdy
        if self.cue_x * ix < 0 and abs(ix) < (abs(self.cue_x) * 0.75):
            ix = 0.0
        if self.cue_y * iy < 0 and abs(iy) < (abs(self.cue_y) * 0.75):
            iy = 0.0

        cue_gain = 1.8
        washout = 1.35
        self.cue_x = (self.cue_x + ix * cue_gain * dt) * math.exp(-washout * dt)
        self.cue_y = (self.cue_y + iy * cue_gain * dt) * math.exp(-washout * dt)

        # Rebuild if dot count or layers changed
        if (s["dot_count"] != self._prev_count or
                s["parallax_layers"] != self._prev_layers or
                s.get("visual_style", "Dots") != self._prev_style):
            self._build_dots()

        if s.get("visual_style", "Dots") == "Grid":
            self._redraw_grid(self.cue_x, self.cue_y, dt)
        else:
            for dot in self._dots:
                dot.update(self.cue_x, self.cue_y, self.srot, dt, s)
                self._redraw_dot(dot)

        self.canvas.tag_raise("gear")
        self.root.after(16, self._loop)

    # ── Settings ─────────────────────────────────────────────────────────────
    def _toggle_settings(self):
        if self.settings_win and self.settings_win.win.winfo_exists():
            self.settings_win.close()
            self.settings_win = None
        else:
            self.settings_win = SettingsWindow(
                self.root, self.settings, self.poller,
                on_rebuild=self._build_dots,
                on_gear_move=self._move_gear,
                on_quit=self._quit,
                sw=self.SW, sh=self.SH)

    def _quit(self):
        self.poller.stop()
        save_settings(self.settings)
        self.root.destroy()


if __name__ == "__main__":
    OverlayApp()
