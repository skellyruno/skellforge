"""SkellForge Studio: local Tk desktop UI for visual layout, DSP chain and VST3 builds.

Run with: python -m skellforge studio
No backend server, no GitHub Actions, no network until CMake FetchContent needs
an uncached dependency. UI preview is an approximation, not a JUCE renderer.
"""
from __future__ import annotations

import copy
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .forge import ForgeError, create_project, validate_project
from .local import build_and_export, read_history, find_verified_vst3, install_verified_vst3
from .preview import render_real_preview, SCENES
from .studio import StudioError, load_studio, save_studio, regenerate, validate_studio
from .automation import available_parameters, registry_specs
from .skelllang import SkellLangError, import_to_studio_model, export_from_studio

BG = "#090b0b"
PANEL = "#141818"
RAISED = "#202727"
LINE = "#2e3a35"
GREEN = "#90ff44"
WHITE = "#f0f3ef"
MUTED = "#97a6a0"
RED = "#fd6974"


class StudioApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("SkellForge Studio - Windows VST3")
        self.root.geometry("1150x795")
        self.root.minsize(880, 650)
        self.root.configure(bg=BG)
        self.project: Path | None = None
        self.document: dict | None = None
        self.selected: str | None = None
        self.drag_origin = None
        self.busy = False
        self.events: queue.SimpleQueue = queue.SimpleQueue()
        self.latest_archive: Path | None = None
        self.latest_preview: dict | None = None
        self._setup_styles()
        self._render_shell()
        self.root.after(120, self._poll)
        self.root.protocol("WM_DELETE_WINDOW", self._close)

    def _setup_styles(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("Dark.TNotebook", background=BG, borderwidth=0)
        style.configure("Dark.TNotebook.Tab", background=RAISED, foreground=MUTED,
                        padding=(16, 10), font=("Segoe UI", 10, "bold"))
        style.map("Dark.TNotebook.Tab", background=[("selected", PANEL)],
                  foreground=[("selected", GREEN)])
        style.configure("Forge.TCombobox", fieldbackground=RAISED, background=RAISED,
                        foreground=WHITE, arrowcolor=GREEN, bordercolor=LINE)
        style.configure("Forge.TScrollbar", background=RAISED, troughcolor=BG, bordercolor=LINE)

    def label(self, parent, text, *, color=WHITE, size=10, bold=False, **kwargs):
        return tk.Label(parent, text=text, fg=color, bg=parent.cget("bg"),
                        font=("Segoe UI", size, "bold" if bold else "normal"), **kwargs)

    def button(self, parent, text, command, *, color=GREEN, fg=BG, width=None):
        return tk.Button(parent, text=text, command=command, bg=color, fg=fg,
                         activebackground=WHITE, activeforeground=BG, width=width,
                         relief="flat", bd=0, padx=12, pady=8,
                         font=("Segoe UI", 9, "bold"), cursor="hand2")

    def input(self, parent, value="", width=20):
        field = tk.Entry(parent, bg=RAISED, fg=WHITE, insertbackground=GREEN,
                         relief="flat", highlightthickness=1, highlightbackground=LINE,
                         highlightcolor=GREEN, font=("Consolas", 10), width=width)
        field.insert(0, str(value))
        return field

    def _render_shell(self):
        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", padx=18, pady=(12, 8))
        tk.Label(header, text="SKELL", bg=BG, fg=WHITE, font=("Segoe UI", 23, "bold")).pack(side="left")
        tk.Label(header, text="FORGE", bg=BG, fg=GREEN, font=("Segoe UI", 23, "bold")).pack(side="left")
        self.project_status = self.label(header, "NO PROJECT LOADED", color=MUTED, size=10)
        self.project_status.pack(side="right", padx=10)

        bar = tk.Frame(self.root, bg=PANEL)
        bar.pack(fill="x", padx=18, pady=(0, 10))
        self.button(bar, "NEW PLUGIN", self._new_project).pack(side="left", padx=8, pady=8)
        self.button(bar, "OPEN PROJECT", self._open_project, color=RAISED, fg=WHITE).pack(side="left", padx=5)
        self.button(bar, "SAVE DESIGN", self._save, color=RAISED, fg=GREEN).pack(side="left", padx=5)
        self.button(bar, "IMPORT .SKELL", self._import_skell, color=RAISED, fg=GREEN).pack(side="left", padx=5)
        self.button(bar, "EXPORT .SKELL", self._export_skell, color=RAISED, fg=GREEN).pack(side="left", padx=5)
        self.button(bar, "VALIDATE", self._validate, color=RAISED, fg=WHITE).pack(side="left", padx=5)
        self.button(bar, "BUILD VST3", lambda: self._switch_build(), color=GREEN).pack(side="right", padx=8)

        self.tabs = ttk.Notebook(self.root, style="Dark.TNotebook")
        self.tabs.pack(fill="both", expand=True, padx=18, pady=(0, 8))
        self.ui_tab = tk.Frame(self.tabs, bg=BG)
        self.dsp_tab = tk.Frame(self.tabs, bg=BG)
        self.build_tab = tk.Frame(self.tabs, bg=BG)
        self.tabs.add(self.ui_tab, text="UI DESIGNER")
        self.tabs.add(self.dsp_tab, text="DSP CHAIN")
        self.tabs.add(self.build_tab, text="LOCAL BUILD / EXPORT")
        self._ui_tab()
        self._dsp_tab()
        self._build_tab()
        footer = tk.Frame(self.root, bg=BG)
        footer.pack(fill="x", padx=20, pady=(0, 10))
        self.status = self.label(footer, "SkellForge Studio - local, Windows VST3 only", color=MUTED)
        self.status.pack(side="left")
        self.label(footer, "JUCE + PINNED SKELLCORE", color=GREEN, size=9, bold=True).pack(side="right")

    def _ui_tab(self):
        shell = tk.Frame(self.ui_tab, bg=BG)
        shell.pack(fill="both", expand=True)
        left = tk.Frame(shell, bg=PANEL, width=200)
        left.pack(side="left", fill="y", padx=(0, 8), pady=8)
        self.label(left, "COMPONENTS", color=GREEN, bold=True).pack(anchor="w", padx=12, pady=(12, 6))
        self.components_list = tk.Listbox(left, bg=PANEL, fg=WHITE,
                                          selectbackground="#34512c", selectforeground=WHITE,
                                          relief="flat", borderwidth=0, font=("Consolas", 10),
                                          width=25, height=18, highlightthickness=0)
        self.components_list.pack(fill="x", padx=6)
        self.components_list.bind("<<ListboxSelect>>", self._on_list_select)
        self.button(left, "+ ADD TEXT", self._add_text).pack(fill="x", padx=8, pady=(12, 4))
        self.button(left, "+ ADD FX KNOB", self._add_effect_knob).pack(fill="x", padx=8, pady=4)
        self.button(left, "+ ADD OUTPUT METER", self._add_meter).pack(fill="x", padx=8, pady=4)
        self.button(left, "REMOVE LABEL / KNOB / METER", self._remove_text, color=RAISED, fg=WHITE).pack(fill="x", padx=8, pady=4)
        self.label(left, "Drag to position. FX knobs\nconnect to host automation.\nSave before building.", color=MUTED, size=9,
                   justify="left").pack(anchor="w", padx=12, pady=12)

        center = tk.Frame(shell, bg=BG)
        center.pack(side="left", fill="both", expand=True, pady=8)
        self.label(center, "LAYOUT PREVIEW  •  drag to reposition  •  double-click to edit", color=MUTED, size=9).pack(anchor="w", padx=12, pady=(8, 6))
        self.canvas = tk.Canvas(center, bg="#101313", highlightthickness=1,
                                highlightbackground=LINE, height=460)
        self.canvas.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.preview_btn = self.button(center, "RENDER ACTUAL JUCE EDITOR", self._real_preview,
                                       color=RAISED, fg=GREEN)
        self.preview_btn.pack(fill="x", padx=8, pady=(0, 7))
        self.label(center, "Builds an actual JUCE preview. The canvas above is an approximate editor.",
                   color=MUTED, size=9).pack(anchor="w", padx=12, pady=(0, 6))
        self.canvas.bind("<Configure>", lambda _e: self._draw_canvas())
        self.canvas.bind("<Button-1>", self._canvas_down)
        self.canvas.bind("<B1-Motion>", self._canvas_move)
        self.canvas.bind("<ButtonRelease-1>", self._canvas_up)

        right = tk.Frame(shell, bg=PANEL, width=205)
        right.pack(side="right", fill="y", padx=(8, 0), pady=8)
        self.label(right, "INSPECTOR", color=GREEN, bold=True).pack(anchor="w", padx=12, pady=(12, 4))
        self.selected_title = self.label(right, "Select a control", color=MUTED)
        self.selected_title.pack(anchor="w", padx=12, pady=(0, 8))
        self.coord_inputs = {}
        for key in ("x", "y", "w", "h", "text"):
            self.label(right, key.upper(), color=MUTED, size=9).pack(anchor="w", padx=12, pady=(8, 2))
            inp = self.input(right, width=16)
            inp.pack(fill="x", padx=12)
            self.coord_inputs[key] = inp
        self.button(right, "APPLY CHANGES", self._apply_props).pack(fill="x", padx=12, pady=14)

    def _dsp_tab(self):
        self.label(self.dsp_tab, "SERIAL DSP CHAIN  •  stages process from top to bottom", color=GREEN, bold=True).pack(anchor="w", padx=20, pady=(18, 8))
        self.label(self.dsp_tab, "Gain, drive, and cutoff are host-automatable. New DSP blocks start bypassed; save, then build locally.", color=MUTED, size=9).pack(anchor="w", padx=20)
        panel = tk.Frame(self.dsp_tab, bg=PANEL)
        panel.pack(fill="both", expand=True, padx=16, pady=14)
        self.dsp_list = tk.Listbox(panel, bg=PANEL, fg=WHITE, selectbackground="#34512c",
                                   selectforeground=WHITE, relief="flat", borderwidth=0,
                                   font=("Consolas", 11), height=14, highlightthickness=0, exportselection=False)
        self.dsp_list.pack(side="left", fill="both", expand=True, padx=16, pady=16)
        right = tk.Frame(panel, bg=PANEL)
        right.pack(side="right", fill="y", padx=16, pady=16)
        for text, command in (("+ SATURATION", lambda: self._add_node("saturate")),
                              ("+ LOWPASS", lambda: self._add_node("lowpass")),
                              ("MOVE UP", lambda: self._move_node(-1)),
                              ("MOVE DOWN", lambda: self._move_node(1)),
                              ("TOGGLE BYPASS", self._toggle_node),
                              ("EDIT SETTINGS", self._edit_node),
                              ("REMOVE NODE", self._remove_node)):
            self.button(right, text, command, color=GREEN if text.startswith("+") else RAISED,
                        fg=BG if text.startswith("+") else WHITE).pack(fill="x", pady=5)
        self.label(self.dsp_tab, "Safe defaults: added effects are bypassed until enabled. No routing cycles or audio-thread allocations.", color=MUTED, size=9).pack(anchor="w", padx=20, pady=(0, 16))

    def _build_tab(self):
        top = tk.Frame(self.build_tab, bg=PANEL)
        top.pack(fill="x", padx=12, pady=(14, 8))
        self.label(top, "LOCAL WINDOWS VST3 BUILDER", color=GREEN, bold=True, size=12).pack(anchor="w", padx=14, pady=(12, 4))
        self.label(top, "Uses Visual Studio + CMake on your computer. GitHub Actions are not required.", color=MUTED).pack(anchor="w", padx=14)
        opt = tk.Frame(top, bg=PANEL)
        opt.pack(fill="x", padx=14, pady=10)
        self.label(opt, "JUCE path (optional)", color=MUTED, size=9).grid(row=0, column=0, sticky="w")
        self.juce_input = self.input(opt, width=37)
        self.juce_input.grid(row=1, column=0, padx=(0, 18))
        self.label(opt, "SkellCore repo path (optional)", color=MUTED, size=9).grid(row=0, column=1, sticky="w")
        self.core_input = self.input(opt, width=37)
        self.core_input.grid(row=1, column=1, padx=(0, 12))
        controls = tk.Frame(top, bg=PANEL)
        controls.pack(fill="x", padx=12, pady=(5, 14))
        self.build_btn = self.button(controls, "BUILD + VERIFY + EXPORT VST3", self._build)
        self.build_btn.pack(side="left", padx=2)
        self.button(controls, "INSTALL INTO VST3 FOLDER", self._install, color=RAISED, fg=GREEN).pack(side="left", padx=8)
        self.button(controls, "OPEN EXPORT FOLDER", self._show_export, color=RAISED, fg=WHITE).pack(side="left", padx=8)
        self.button(controls, "BUILD HISTORY", self._history, color=RAISED, fg=WHITE).pack(side="left", padx=4)
        self.label(self.build_tab, "BUILD LOG", color=MUTED, size=9, bold=True).pack(anchor="w", padx=16, pady=(12, 4))
        self.log_text = tk.Text(self.build_tab, bg="#0a0d0c", fg=WHITE, insertbackground=GREEN,
                                font=("Consolas", 9), wrap="word", state="disabled",
                                relief="flat", highlightthickness=1, highlightbackground=LINE)
        self.log_text.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.log_text.tag_config("success", foreground=GREEN)
        self.log_text.tag_config("error", foreground=RED)
        self.log_text.tag_config("progress", foreground="#c0d59b")

    def _notify(self, text, *, error=False):
        self.status.config(text=text, fg=RED if error else MUTED)

    def _new_project(self):
        if self.busy or (self.document is not None and not self._confirm_unsaved()):
            return
        window = tk.Toplevel(self.root)
        window.title("New SkellForge plugin")
        window.configure(bg=PANEL)
        window.resizable(False, False)
        entries = []
        for label, default in (("Plugin name", "Skell New Plugin"), ("4-character unique VST3 code", "SF92")):
            self.label(window, label, color=MUTED).pack(anchor="w", padx=20, pady=(15, 4))
            entry = self.input(window, default, width=35)
            entry.pack(padx=20)
            entries.append(entry)
        def create():
            parent = filedialog.askdirectory(parent=window, title="Choose a folder for the NEW plugin directory")
            if not parent:
                return
            name, code = entries[0].get().strip(), entries[1].get().strip()
            slug = "".join(ch.lower() for ch in name if ch.isascii() and ch.isalnum())
            try:
                target = create_project(name, Path(parent) / slug, code)
                window.destroy()
                self._load(target)
            except (ForgeError, StudioError, OSError, ValueError) as exc:
                messagebox.showerror("Project creation failed", str(exc), parent=window)
        self.button(window, "CREATE PLUGIN", create).pack(padx=20, pady=20, fill="x")
        window.grab_set()

    def _open_project(self):
        if self.busy:
            return
        if self.document is not None and not self._confirm_unsaved():
            return
        folder = filedialog.askdirectory(parent=self.root, title="Open an existing SkellForge project")
        if folder:
            try:
                self._load(Path(folder))
            except (ForgeError, StudioError, OSError, ValueError) as exc:
                messagebox.showerror("Open failed", str(exc), parent=self.root)

    def _load(self, path: Path):
        data = validate_project(path)
        studio = load_studio(path)
        self.project, self.document = path.resolve(), copy.deepcopy(studio)
        self.latest_preview = None
        self.selected = None
        self.project_status.config(text=f"{data['name']}  [{data['plugin_code']}]")
        self._refresh_lists()
        self._draw_canvas()
        self._notify("Loaded " + str(path))

    def _confirm_unsaved(self):
        # Explicit Save is required; never silently destroy an in-memory design.
        if self.project and self.document != load_studio(self.project):
            return messagebox.askyesno("Unsaved Studio changes", "Discard unsaved changes?", parent=self.root)
        return True

    def _close(self):
        if self.busy:
            messagebox.showwarning("Build active", "Finish the local build before closing Studio.", parent=self.root)
            return
        if self._confirm_unsaved():
            self.root.destroy()

    def _refresh_lists(self):
        self.components_list.delete(0, "end")
        self.dsp_list.delete(0, "end")
        if not self.document:
            return
        for comp in self.document["components"]:
            self.components_list.insert("end", f"{comp['id']}   [{comp['type']}]")
        for node in self.document["chain"]:
            extras = ""
            if node["type"] == "saturate":
                extras = f"drive={node['drive']:g}"
            elif node["type"] == "lowpass":
                extras = f"cutoff={node['cutoff_hz']:g} Hz"
            self.dsp_list.insert("end", f"{node['id']:<18} {node['type']:<9} {'ON' if node['enabled'] else 'BYPASS':<7} {extras}")

    def _on_list_select(self, _event=None):
        if not self.document or not self.components_list.curselection():
            return
        index = self.components_list.curselection()[0]
        self._select(self.document["components"][index]["id"])

    def _select(self, cid):
        self.selected = cid
        c = next((c for c in self.document["components"] if c["id"] == cid), None)
        if c is None:
            return
        self.selected_title.config(text=cid + "  [" + c["type"] + "]")
        for key, entry in self.coord_inputs.items():
            entry.delete(0, "end")
            entry.insert(0, c.get(key, "") if key == "text" else c[key])
        self._draw_canvas()

    def _preview_geometry(self):
        if not self.document:
            return (0, 0, 1)
        base = self.document["canvas"]
        cw, ch = max(self.canvas.winfo_width(), 1), max(self.canvas.winfo_height(), 1)
        scale = min((cw - 40) / base["width"], (ch - 40) / base["height"])
        scale = max(0.1, scale)
        return ((cw - base["width"] * scale) / 2, (ch - base["height"] * scale) / 2, scale)

    def _draw_canvas(self):
        if not hasattr(self, "canvas"):
            return
        cv = self.canvas
        cv.delete("all")
        if not self.document:
            cv.create_text(cv.winfo_width()/2, cv.winfo_height()/2, text="OPEN OR CREATE A PLUGIN",
                           fill=MUTED, font=("Segoe UI", 13, "bold"))
            return
        ox, oy, s = self._preview_geometry()
        base = self.document["canvas"]
        cv.create_rectangle(ox, oy, ox+base["width"]*s, oy+base["height"]*s,
                            fill="#111515", outline=LINE, width=2, tags=("background",))
        for c in self.document["components"]:
            x1, y1 = ox+c["x"]*s, oy+c["y"]*s
            x2, y2 = ox+(c["x"]+c["w"])*s, oy+(c["y"]+c["h"])*s
            name, kind = c["id"], c["type"]
            selected = name == self.selected
            if kind == "meter":
                cv.create_rectangle(x1, y1, x2, y2, fill="#172019", outline=LINE, tags=(name,))
                cv.create_text(x1+6*s, (y1+y2)/2, anchor="w",
                               text=c.get("text", "OUT"), fill=GREEN,
                               font=("Segoe UI", max(8, int(9*s))), tags=(name,))
            elif kind in ("gain_knob", "effect_knob"):
                diam = min(x2-x1, y2-y1)*0.7
                cx, cy = (x1+x2)/2, (y1+y2)/2
                cv.create_oval(cx-diam/2,cy-diam/2,cx+diam/2,cy+diam/2,
                               fill="#202726", outline="#54704f", width=3, tags=(name,))
                cv.create_line(cx,cy, cx-diam*.22,cy-diam*.22,fill=GREEN,width=3,tags=(name,))
                cv.create_text(cx, y2-9*s,
                               text="0 dB" if kind == "gain_knob" else c.get("text", "FX"),
                               fill=WHITE, font=("Consolas", 10), tags=(name,))
            elif kind == "skull":
                cv.create_text((x1+x2)/2, (y1+y2)/2, text="SKELL", fill=GREEN,
                               font=("Segoe UI", 13, "bold"), tags=(name,))
            elif kind == "title":
                title = self.project_status.cget("text").split("  [")[0]
                cv.create_text(x1+6, (y1+y2)/2, text=title, anchor="w",
                               fill=WHITE, font=("Segoe UI", max(9,int(14*s)), "bold"), tags=(name,))
            else:
                cv.create_text((x1+x2)/2, (y1+y2)/2,
                               text=c.get("text", "GAIN" if kind == "gain_label" else ""),
                               fill=GREEN if kind == "gain_label" else WHITE,
                               font=("Segoe UI", max(8,int(10*s))), tags=(name,))
            if selected:
                cv.create_rectangle(x1,y1,x2,y2,outline=GREEN,width=2,dash=(5,3),tags=(name,))

    def _canvas_down(self, event):
        if not self.document:
            return
        ox, oy, s = self._preview_geometry()
        hit = None
        for item in reversed(self.document["components"]):
            if ox+item["x"]*s <= event.x <= ox+(item["x"]+item["w"])*s and \
               oy+item["y"]*s <= event.y <= oy+(item["y"]+item["h"])*s:
                hit = item["id"]
                break
        if hit:
            self._select(hit)
            self.drag_origin = (event.x, event.y, next(c for c in self.document["components"] if c["id"] == hit)["x"],
                                next(c for c in self.document["components"] if c["id"] == hit)["y"])
        else:
            self.drag_origin = None

    def _canvas_move(self, event):
        if self.busy or not self.drag_origin or not self.document or not self.selected:
            return
        ox, oy, scale = self._preview_geometry()
        ex, ey, initial_x, initial_y = self.drag_origin
        item = next(c for c in self.document["components"] if c["id"] == self.selected)
        base = self.document["canvas"]
        item["x"] = max(0, min(base["width"]-item["w"], round(initial_x + (event.x-ex)/scale)))
        item["y"] = max(0, min(base["height"]-item["h"], round(initial_y + (event.y-ey)/scale)))
        self._draw_canvas()

    def _canvas_up(self, _event):
        self.drag_origin = None
        if self.selected and self.document:
            self._select(self.selected)

    def _apply_props(self):
        if self.busy or not self.document or not self.selected:
            return
        original = next(c for c in self.document["components"] if c["id"] == self.selected)
        candidate = copy.deepcopy(self.document)
        item = next(c for c in candidate["components"] if c["id"] == self.selected)
        try:
            for key in ("x","y","w","h"):
                item[key] = int(self.coord_inputs[key].get().strip())
            if item["type"] in ("text", "effect_knob", "meter"):
                item["text"] = self.coord_inputs["text"].get().strip()
            validate_studio(candidate)
            self.document = candidate
            self._select(original["id"])
            self._notify("Inspector updated. Click SAVE DESIGN to persist.")
        except (StudioError, ValueError) as exc:
            messagebox.showerror("Invalid layout", str(exc), parent=self.root)

    def _add_text(self):
        if self.busy or not self.document:
            return
        candidate = copy.deepcopy(self.document)
        ids = {c["id"] for c in candidate["components"]}
        idx = 1
        while f"text_{idx}" in ids:
            idx += 1
        identifier = f"text_{idx}"
        candidate["components"].append({"id": identifier, "type": "text", "text": "NEW LABEL",
                                        "x": 30, "y": 268, "w": 140, "h": 22})
        try:
            validate_studio(candidate)
            self.document = candidate
            self._refresh_lists()
            self._select(identifier)
        except StudioError as exc:
            messagebox.showerror("Cannot add label", str(exc), parent=self.root)

    def _add_meter(self):
        if self.busy or not self.document:
            return
        candidate = copy.deepcopy(self.document)
        ids = {item["id"] for item in candidate["components"]}
        n = 1
        while f"meter_{n}" in ids:
            n += 1
        name = f"meter_{n}"
        candidate["components"].append({
            "id": name, "type": "meter", "text": "OUT",
            "x": 24, "y": 272, "w": 160, "h": 24,
        })
        try:
            validate_studio(candidate)
            self.document = candidate
            self._refresh_lists()
            self._select(name)
        except StudioError as exc:
            messagebox.showerror("Cannot add audio meter", str(exc), parent=self.root)

    def _add_effect_knob(self):
        if self.busy or not self.document:
            return
        used = {c.get("parameter_id") for c in self.document["components"]
                if c["type"] == "effect_knob"}
        available = [spec for spec in available_parameters(self.document)
                     if spec["id"] not in used]
        if not available:
            messagebox.showinfo("No available DSP parameter",
                                "Add a saturation or lowpass DSP block first.",
                                parent=self.root)
            return
        dialog = tk.Toplevel(self.root)
        dialog.title("Add automatable DSP knob")
        dialog.configure(bg=PANEL)
        self.label(dialog, "Select a host-automatable parameter", color=MUTED).pack(
            anchor="w", padx=18, pady=(14, 6))
        lookup = {f"{spec['node']}  /  {spec['field']}": spec for spec in available}
        choice = ttk.Combobox(dialog, values=list(lookup), state="readonly",
                              width=35, style="Forge.TCombobox")
        choice.current(0)
        choice.pack(padx=18, pady=4)
        def create():
            spec = lookup[choice.get()]
            candidate = copy.deepcopy(self.document)
            reserved = {c["id"] for c in candidate["components"]}
            index = 1
            while f"effect_knob_{index}" in reserved:
                index += 1
            id_ = f"effect_knob_{index}"
            candidate["components"].append({
                "id": id_, "type": "effect_knob",
                "parameter_id": spec["id"], "text": spec["field"].replace("_", " ").upper(),
                "x": 260, "y": 148, "w": 110, "h": 110,
            })
            try:
                validate_studio(candidate)
                self.document = candidate
                self._refresh_lists()
                self._select(id_)
                dialog.destroy()
            except StudioError as exc:
                messagebox.showerror("Cannot add knob", str(exc), parent=dialog)
        self.button(dialog, "ADD AUTOMATABLE KNOB", create).pack(
            fill="x", padx=18, pady=(12, 18))
        dialog.grab_set()

    def _remove_text(self):
        if self.busy or not self.document or not self.selected:
            return
        candidate = copy.deepcopy(self.document)
        candidate["components"] = [c for c in candidate["components"]
                                   if c["id"] != self.selected or c["type"] not in ("text", "effect_knob", "meter")]
        if len(candidate["components"]) == len(self.document["components"]):
            self._notify("Built-in controls cannot be deleted.", error=True)
            return
        self.document = candidate
        self.selected = None
        self._refresh_lists()
        self._draw_canvas()

    def _selected_node(self):
        if not self.document or not self.dsp_list.curselection():
            return None, None
        idx = self.dsp_list.curselection()[0]
        return idx, self.document["chain"][idx]

    def _add_node(self, kind):
        if self.busy or not self.document:
            return
        candidate = copy.deepcopy(self.document)
        ids = {n["id"] for n in candidate["chain"]}
        ids.update(entry["node"] for entry in registry_specs(candidate))
        idx = 1
        while f"{kind}_{idx}" in ids:
            idx += 1
        node = {"id": f"{kind}_{idx}", "type": kind, "enabled": False}
        node.update({"drive": 2.0} if kind == "saturate" else {"cutoff_hz": 8000.0})
        candidate["chain"].append(node)
        try:
            validate_studio(candidate)
            self.document = candidate
            self._refresh_lists()
        except StudioError as exc:
            messagebox.showerror("Cannot add DSP node", str(exc), parent=self.root)

    def _move_node(self, direction):
        if self.busy:
            return
        idx, node = self._selected_node()
        if idx is None or idx == 0 or idx+direction <= 0 or idx+direction >= len(self.document["chain"]):
            return
        chain = self.document["chain"]
        chain[idx], chain[idx+direction] = chain[idx+direction], chain[idx]
        self._refresh_lists()
        self.dsp_list.selection_set(idx+direction)

    def _toggle_node(self):
        if self.busy:
            return
        idx, node = self._selected_node()
        if idx is None or idx == 0:
            self._notify("Built-in Gain is always enabled", error=True)
            return
        node["enabled"] = not node["enabled"]
        self._refresh_lists()
        self.dsp_list.selection_set(idx)

    def _remove_node(self):
        if self.busy:
            return
        idx, node = self._selected_node()
        if idx is None or idx == 0:
            return
        if not messagebox.askyesno("Remove DSP block",
                "Remove this DSP block? Its saved parameter IDs will be retired, "
                "not reused. Existing automation remains addressable.", parent=self.root):
            return
        candidate = copy.deepcopy(self.document)
        deleted_id = candidate["chain"][idx]["id"]
        del candidate["chain"][idx]
        candidate["components"] = [
            c for c in candidate["components"]
            if not (c["type"] == "effect_knob"
                    and c.get("parameter_id", "").startswith("fx_" + deleted_id + "_"))
        ]
        try:
            validate_studio(candidate)
            self.document = candidate
            self._refresh_lists()
            self._draw_canvas()
        except StudioError as exc:
            messagebox.showerror("Cannot remove DSP block", str(exc), parent=self.root)

    def _edit_node(self):
        if self.busy:
            return
        idx, node = self._selected_node()
        if idx is None or node["type"] == "gain":
            return
        key = "drive" if node["type"] == "saturate" else "cutoff_hz"
        param_id = f"fx_{node['id']}_{key}"
        if param_id in {spec["id"] for spec in registry_specs(self.document)}:
            messagebox.showinfo("Saved parameter default",
                "The initial value is locked to preserve existing DAW projects. "
                "Use the effect knob in FL Studio to change the value.", parent=self.root)
            return
        window = tk.Toplevel(self.root)
        window.title(f"Edit {node['id']}")
        window.configure(bg=PANEL)
        self.label(window, f"{key}  ({'1–10' if key == 'drive' else '20–20000 Hz'})",
                   color=MUTED).pack(anchor="w", padx=20, pady=(15,5))
        input_ = self.input(window, node[key])
        input_.pack(padx=20)
        def apply():
            candidate = copy.deepcopy(self.document)
            try:
                candidate["chain"][idx][key] = float(input_.get())
                validate_studio(candidate)
                self.document = candidate
                self._refresh_lists()
                self.dsp_list.selection_set(idx)
                window.destroy()
            except (StudioError, ValueError) as exc:
                messagebox.showerror("Invalid DSP setting", str(exc), parent=window)
        self.button(window, "APPLY", apply).pack(padx=20, pady=20, fill="x")
        window.grab_set()

    def _import_skell(self):
        if self.busy or not self.project or not self.document:
            self._notify("Open a project before importing SkellLang.", error=True)
            return
        filename = filedialog.askopenfilename(
            parent=self.root, title="Import a .skell design",
            filetypes=[("SkellLang source", "*.skell")])
        if not filename:
            return
        try:
            candidate = import_to_studio_model(self.project, Path(filename))
        except (SkellLangError, OSError, ValueError) as exc:
            messagebox.showerror("SkellLang import refused", str(exc), parent=self.root)
            return
        if not messagebox.askyesno("Import SkellLang",
                "Replace the current in-memory layout and DSP chain with this "
                "validated .skell design? Existing saved project files will stay "
                "unchanged until you click SAVE DESIGN.", parent=self.root):
            return
        self.document = candidate
        self.selected = None
        self._refresh_lists()
        self._draw_canvas()
        self._notify("SkellLang design imported in memory. Review and SAVE DESIGN.")

    def _export_skell(self):
        if self.busy or not self.project or not self.document:
            self._notify("Open a project before exporting SkellLang.", error=True)
            return
        try:
            if self.document != load_studio(self.project):
                messagebox.showinfo("Save design first",
                    "Save the current Studio design before exporting a lossless "
                    ".skell source file.", parent=self.root)
                return
        except (StudioError, OSError) as exc:
            messagebox.showerror("Cannot export", str(exc), parent=self.root)
            return
        destination = filedialog.asksaveasfilename(
            parent=self.root, title="Export SkellLang source",
            defaultextension=".skell", filetypes=[("SkellLang source", "*.skell")])
        if not destination:
            return
        try:
            path = export_from_studio(self.project, Path(destination))
            self._notify(f"Exported SkellLang: {path}")
        except (SkellLangError, OSError, ValueError) as exc:
            messagebox.showerror("SkellLang export refused", str(exc), parent=self.root)

    def _save(self):
        if self.busy or not self.document or not self.project:
            return False
        try:
            save_studio(self.project, self.document)
            changed = regenerate(self.project)
            self._notify(f"Design saved. Generated: {', '.join(changed) if changed else 'no code changes'}")
            return True
        except (StudioError, OSError, ValueError) as exc:
            messagebox.showerror("Save failed", str(exc), parent=self.root)
            return False

    def _validate(self):
        if not self.project:
            return
        try:
            validate_project(self.project)
            validate_studio(self.document)
            self._notify("Project identity and in-memory design validated. Build is a separate check.")
        except (ForgeError, StudioError) as exc:
            messagebox.showerror("Validation failed", str(exc), parent=self.root)

    def _switch_build(self):
        self.tabs.select(self.build_tab)

    def _write_log(self, text):
        self.log_text.config(state="normal")
        tag = "error" if text.startswith("ERROR") else "success" if text.startswith("SUCCESS") else "progress" if text.startswith("[") else ""
        self.log_text.insert("end", text + "\n", tag)
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def _build(self):
        if self.busy or not self.project or not self.document:
            self._notify("Open a project to build.", error=True)
            return
        try:
            if not self._save():
                return
            validate_project(self.project)
        except (ForgeError, StudioError, OSError) as exc:
            messagebox.showerror("Cannot build", str(exc), parent=self.root)
            return
        self.busy = True
        self.build_btn.config(state="disabled", text="BUILDING LOCALLY...")
        self.preview_btn.config(state="disabled")
        project = self.project
        juce = Path(self.juce_input.get().strip()) if self.juce_input.get().strip() else None
        core = Path(self.core_input.get().strip()) if self.core_input.get().strip() else None
        self._switch_build()
        self._write_log("=== NEW LOCAL BUILD ===")
        def work():
            try:
                result = build_and_export(project, juce_path=juce, core_path=core,
                                          parallel=2, log=lambda line: self.events.put(("log", line)))
                self.events.put(("done", result))
            except Exception as exc:  # thread boundary: convert failure to visible UI
                self.events.put(("error", str(exc)))
        threading.Thread(target=work, daemon=True, name="SkellForge-local-build").start()

    def _poll(self):
        while not self.events.empty():
            kind, payload = self.events.get()
            if kind == "log":
                self._write_log(payload)
            else:
                self.busy = False
                self.build_btn.config(state="normal", text="BUILD + VERIFY + EXPORT VST3")
                self.preview_btn.config(state="normal", text="RENDER ACTUAL JUCE EDITOR")
                if kind == "preview":
                    self.latest_preview = payload
                    self._notify("Verified real JUCE screenshots at 3 sizes")
                    self._write_log("PREVIEW VERIFIED: " + payload["preview_folder"])
                    self._show_real_preview(payload)
                elif kind == "done":
                    self.latest_archive = Path(payload["archive"])
                    self._notify(f"VST3 exported in {payload['duration_seconds']:.1f}s")
                    self._write_log("Build succeeded. Next: test in FL Studio (load, automate, save/reopen).")
                elif kind == "installed":
                    self._notify("Installed to selected VST3 folder; rescan plugins in FL Studio.")
                    self._write_log("INSTALLED: " + payload["installed"])
                    if payload["backup"]:
                        self._write_log("BACKUP: " + payload["backup"])
                    if payload.get("cleanup_warning"):
                        self._write_log("WARNING: " + payload["cleanup_warning"])
                else:
                    self._notify("Local build failed - see log.", error=True)
                    self._write_log("ERROR: " + payload)
        self.root.after(120, self._poll)

    def _real_preview(self):
        if self.busy or not self.project or not self.document:
            self._notify("Open a project before rendering the real editor.", error=True)
            return
        if not self._save():
            return
        self.busy = True
        self.build_btn.config(state="disabled")
        self.preview_btn.config(state="disabled", text="RENDERING JUCE...")
        project = self.project
        juce = Path(self.juce_input.get().strip()) if self.juce_input.get().strip() else None
        core = Path(self.core_input.get().strip()) if self.core_input.get().strip() else None
        self._write_log("=== REAL JUCE EDITOR PREVIEW ===")
        def work():
            try:
                result = render_real_preview(project, juce_path=juce, core_path=core,
                                             log=lambda line: self.events.put(("log", line)))
                self.events.put(("preview", result))
            except Exception as exc:
                self.events.put(("error", "JUCE preview failed: " + str(exc)))
        threading.Thread(target=work, daemon=True, name="SkellForge-real-juce-preview").start()

    def _show_real_preview(self, report):
        window = tk.Toplevel(self.root)
        window.title("SkellForge — actual JUCE editor screenshots")
        window.configure(bg=BG)
        self.label(window, "REAL GENERATED JUCE EDITOR", color=GREEN, bold=True).pack(
            anchor="w", padx=16, pady=(14, 5))
        self.label(window, "Rendered by SkellCore, not the schematic Tk canvas",
                   color=MUTED).pack(anchor="w", padx=16)
        picker = ttk.Combobox(window, values=list(SCENES), state="readonly",
                              style="Forge.TCombobox", width=24)
        picker.set("default")
        picker.pack(anchor="w", padx=16, pady=(8, 10))
        picture = tk.Label(window, bg=BG)
        picture.pack(padx=14, pady=(0, 12))
        def show(_event=None):
            chosen = picker.get()
            if chosen not in report["scenes"]:
                return
            try:
                screenshot = tk.PhotoImage(file=report["scenes"][chosen])
                # Avoid overflowing smaller laptop screens. This scales for display only;
                # full-resolution PNG files remain unchanged on disk.
                screen_width = max(350, self.root.winfo_screenwidth() - 80)
                screen_height = max(300, self.root.winfo_screenheight() - 240)
                factor = max(1, (screenshot.width() + screen_width - 1)//screen_width,
                             (screenshot.height() + screen_height - 1)//screen_height)
                if factor > 1:
                    screenshot = screenshot.subsample(factor, factor)
                picture.config(image=screenshot)
                picture.image = screenshot
            except tk.TclError as exc:
                messagebox.showerror("Cannot open JUCE screenshot", str(exc), parent=window)
        picker.bind("<<ComboboxSelected>>", show)
        show()

    def _install(self):
        if self.busy or not self.project:
            self._notify("Open a project and finish its build first.", error=True)
            return
        try:
            find_verified_vst3(self.project)
        except (ForgeError, OSError) as exc:
            messagebox.showerror("No valid built VST3", str(exc), parent=self.root)
            return
        folder = filedialog.askdirectory(parent=self.root,
                                         title="Choose a folder ALREADY configured in FL Studio's plugin paths")
        if not folder:
            return
        message = ("Replace/install the built VST3 into this folder?\n\n"
                   + folder + "\n\nExisting plugins with the same bundle name will be backed up "
                   "to your SkellForge project. Close FL Studio first.")
        if not messagebox.askyesno("Confirm local VST3 installation", message,
                                   parent=self.root):
            return
        self.busy = True
        self.build_btn.config(state="disabled", text="INSTALLING VST3...")
        self.preview_btn.config(state="disabled")
        project = self.project
        def work():
            try:
                output = install_verified_vst3(project, Path(folder))
                self.events.put(("installed", output))
            except Exception as exc:
                self.events.put(("error", "VST3 install failed: " + str(exc)))
        threading.Thread(target=work, daemon=True,
                         name="SkellForge-install-vst3").start()

    def _show_export(self):
        if not self.project:
            return
        destination = (self.project / "dist")
        destination.mkdir(exist_ok=True)
        import os
        if hasattr(os, "startfile"):
            os.startfile(str(destination))
        else:
            self._notify("Export folder: " + str(destination))

    def _history(self):
        if not self.project:
            return
        entries = read_history(self.project)
        self._write_log("=== LOCAL BUILD HISTORY ===")
        for entry in entries[:20]:
            self._write_log(f"{entry['timestamp_utc']} | {entry['status']} | "
                            f"{entry['duration_seconds']:.1f}s | {entry.get('archive') or entry.get('error', '')}")
        if not entries:
            self._write_log("No local builds recorded yet.")

    def run(self):
        self.root.mainloop()


def main():
    StudioApp().run()


if __name__ == "__main__":
    main()
