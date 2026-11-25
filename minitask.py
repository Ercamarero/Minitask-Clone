"""MiniTask Clon - grabador/reproductor de ratón y teclado.

Proyecto independiente: es un clon, no el programa original.
Atajos globales:  F8 = grabar / parar grabación     F9 = reproducir / parar
Requiere:  pip install pynput
"""
import ctypes
import json
import math
import os
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox

from pynput import keyboard, mouse

try:  # coordenadas reales en pantallas con escala DPI
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

APP_NAME = "MiniTask Clon"


def resource_path(name):
    """Ruta de un recurso, tanto desde el código como dentro del .exe."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


HOTKEY_REC = keyboard.Key.f8
HOTKEY_PLAY = keyboard.Key.f9

# ---------- límites de seguridad para archivos cargados ----------
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_EVENTS = 300_000
MAX_SECONDS = 24 * 3600
MAX_COORD = 100_000

# ---------- diseño: un fondo, una tinta, un acento ----------
BG = "#121513"
SURFACE = "#1d211f"
SURFACE_HI = "#272c29"
INK = "#edebe4"
MUTED = "#8f958f"
ACCENT = "#ff5b38"
FONT = "Segoe UI"


def key_to_str(key):
    if isinstance(key, keyboard.Key):
        return "key:" + key.name
    if getattr(key, "char", None):
        return "char:" + key.char
    return "vk:%s" % key.vk


def str_to_key(s):
    kind, _, val = s.partition(":")
    if kind == "key":
        return keyboard.Key[val]
    if kind == "char":
        return keyboard.KeyCode.from_char(val)
    return keyboard.KeyCode.from_vk(int(val))


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _coord(v):
    return isinstance(v, int) and not isinstance(v, bool) and -MAX_COORD <= v <= MAX_COORD


def validate_events(data):
    """Devuelve la lista si es una grabación válida; lanza ValueError si no."""
    if not isinstance(data, list) or not data:
        raise ValueError("El archivo no contiene una grabación.")
    if len(data) > MAX_EVENTS:
        raise ValueError("Demasiados eventos.")
    last_t = 0.0
    buttons = set(mouse.Button.__members__)
    keys = set(keyboard.Key.__members__)
    for ev in data:
        if not isinstance(ev, dict):
            raise ValueError("Evento no válido.")
        t = ev.get("t")
        if not _num(t) or t < last_t or t > MAX_SECONDS:
            raise ValueError("Tiempo no válido.")
        last_t = t
        kind = ev.get("type")
        if kind == "move":
            ok = _coord(ev.get("x")) and _coord(ev.get("y"))
        elif kind == "click":
            ok = (_coord(ev.get("x")) and _coord(ev.get("y"))
                  and ev.get("b") in buttons and isinstance(ev.get("p"), bool))
        elif kind == "scroll":
            ok = (_coord(ev.get("x")) and _coord(ev.get("y"))
                  and all(isinstance(ev.get(k), int) and not isinstance(ev.get(k), bool)
                          and abs(ev[k]) <= 1000 for k in ("dx", "dy")))
        elif kind == "key":
            k = ev.get("k")
            ok = isinstance(ev.get("p"), bool) and isinstance(k, str) and len(k) <= 40
            if ok:
                typ, _, val = k.partition(":")
                if typ == "key":
                    ok = val in keys
                elif typ == "char":
                    ok = len(val) == 1
                elif typ == "vk":
                    ok = val.isdigit() and 0 <= int(val) <= 255
                else:
                    ok = False
        else:
            ok = False
        if not ok:
            raise ValueError("Evento no válido.")
    return data


class FlatButton(tk.Button):
    """Botón plano, de un solo color, con foco visible y estado al pasar el ratón."""

    def __init__(self, master, bg, fg, hover, **kw):
        kw.setdefault("font", (FONT, 12, "bold"))
        super().__init__(master, bg=bg, fg=fg, activebackground=hover, activeforeground=fg,
                         relief="flat", bd=0, cursor="hand2", highlightthickness=2,
                         highlightbackground=bg, highlightcolor=INK, **kw)
        self._bg, self._hover = bg, hover
        self.bind("<Enter>", lambda e: self.config(bg=self._hover))
        self.bind("<Leave>", lambda e: self.config(bg=self._bg))

    def restyle(self, bg, fg, hover):
        self._bg, self._hover = bg, hover
        self.config(bg=bg, fg=fg, activebackground=hover, activeforeground=fg,
                    highlightbackground=bg)


class Stepper(tk.Frame):
    """Etiqueta a la izquierda; menos / valor / más a la derecha."""

    def __init__(self, master, label, get_text, step, name):
        super().__init__(master, bg=BG)
        self.step, self.get_text = step, get_text
        tk.Label(self, text=label, bg=BG, fg=INK, font=(FONT, 11), anchor="w").pack(side="left")
        box = tk.Frame(self, bg=SURFACE)
        box.pack(side="right")
        self.minus = FlatButton(box, SURFACE, INK, SURFACE_HI, text="−", width=3,
                                command=lambda: step(-1))
        self.plus = FlatButton(box, SURFACE, INK, SURFACE_HI, text="+", width=3,
                               command=lambda: step(1))
        self.value = tk.Label(box, bg=SURFACE, fg=INK, font=(FONT, 11, "bold"), width=9)
        self.minus.pack(side="left")
        self.value.pack(side="left")
        self.plus.pack(side="left")
        self.minus.config(takefocus=1)
        self.plus.config(takefocus=1)
        self.refresh()

    def refresh(self):
        self.value.config(text=self.get_text())


class App:
    def __init__(self, root):
        self.root = root
        root.title(APP_NAME)
        try:
            root.iconbitmap(resource_path("icon.ico"))
        except tk.TclError:
            pass
        root.geometry("380x440")
        root.resizable(False, False)
        root.configure(bg=BG)
        root.attributes("-topmost", True)
        self.dark_titlebar()

        self.events = []
        self.from_file = False  # grabación cargada de un archivo: pedir confirmación
        self.recording = False
        self.playing = False
        self.t0 = 0.0
        self.last_move = 0.0
        self.reps_n = 1       # 0 = infinito
        self.speed_x = 1.0
        self.q = queue.Queue()
        self.mctl = mouse.Controller()
        self.kctl = keyboard.Controller()

        pad = 24
        main = tk.Frame(root, bg=BG)
        main.pack(fill="both", expand=True, padx=pad, pady=pad)

        # estado: lo grande, grande
        self.state = tk.Label(main, text="Listo", bg=BG, fg=INK, anchor="w",
                              font=(FONT, 34, "bold"))
        self.state.pack(fill="x")
        self.detail = tk.Label(main, text="Pulsa F8 para grabar", bg=BG, fg=MUTED, anchor="w",
                               font=(FONT, 11))
        self.detail.pack(fill="x", pady=(0, 20))

        # acciones principales
        row = tk.Frame(main, bg=BG)
        row.pack(fill="x")
        row.columnconfigure((0, 1), weight=1, uniform="a")
        self.btn_rec = FlatButton(row, SURFACE, INK, SURFACE_HI, text="Grabar  F8",
                                  command=self.toggle_rec, pady=22)
        self.btn_play = FlatButton(row, INK, BG, "#ffffff", text="Reproducir  F9",
                                   command=self.toggle_play, pady=22)
        self.btn_rec.grid(row=0, column=0, sticky="we", padx=(0, 6))
        self.btn_play.grid(row=0, column=1, sticky="we", padx=(6, 0))

        # ajustes
        self.s_reps = Stepper(main, "Repeticiones", self.reps_text, self.step_reps, "reps")
        self.s_speed = Stepper(main, "Velocidad", self.speed_text, self.step_speed, "speed")
        self.s_reps.pack(fill="x", pady=(26, 8))
        self.s_speed.pack(fill="x")

        # archivo
        files = tk.Frame(main, bg=BG)
        files.pack(fill="x", side="bottom")
        files.columnconfigure((0, 1), weight=1, uniform="b")
        FlatButton(files, BG, INK, SURFACE, text="Guardar…", font=(FONT, 11),
                   command=self.save, pady=8).grid(row=0, column=0, sticky="we", padx=(0, 6))
        FlatButton(files, BG, INK, SURFACE, text="Abrir…", font=(FONT, 11),
                   command=self.load, pady=8).grid(row=0, column=1, sticky="we", padx=(6, 0))

        # escuchas globales
        self.k_listener = keyboard.Listener(on_press=self.on_press, on_release=self.on_release)
        self.m_listener = mouse.Listener(on_move=self.on_move, on_click=self.on_click,
                                         on_scroll=self.on_scroll)
        self.k_listener.start()
        self.m_listener.start()
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.poll()

    def dark_titlebar(self):
        try:
            self.root.update()
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 20, ctypes.byref(ctypes.c_int(1)), ctypes.sizeof(ctypes.c_int))
        except Exception:
            pass

    # ---------- ajustes ----------
    def reps_text(self):
        return "Infinito" if self.reps_n == 0 else str(self.reps_n)

    def speed_text(self):
        return "%.2g×" % self.speed_x

    def step_reps(self, d):
        if self.playing:
            return
        self.reps_n = max(0, min(100000, self.reps_n + d * (1 if self.reps_n < 10 else 5)))
        self.s_reps.refresh()

    def step_speed(self, d):
        if self.playing:
            return
        self.speed_x = max(0.25, min(10.0, round(self.speed_x + d * 0.25, 2)))
        self.s_speed.refresh()

    # ---------- cola de acciones desde hilos ----------
    def poll(self):
        try:
            while True:
                self.q.get_nowait()()
        except queue.Empty:
            pass
        if self.recording:
            self.show("Grabando", "%d eventos · %.1f s" % (len(self.events), self.now()), ACCENT)
        self.root.after(80, self.poll)

    def show(self, state, detail, color=INK):
        self.state.config(text=state, fg=color)
        self.detail.config(text=detail)

    # ---------- grabación ----------
    def now(self):
        return time.perf_counter() - self.t0

    def add(self, **ev):
        ev["t"] = round(self.now(), 4)
        self.events.append(ev)

    def toggle_rec(self):
        if self.playing:
            return
        if self.recording:
            self.recording = False
            self.btn_rec.restyle(SURFACE, INK, SURFACE_HI)
            self.btn_rec.config(text="Grabar  F8")
            self.show("Listo", "%d eventos grabados" % len(self.events))
        else:
            self.events = []
            self.from_file = False
            self.t0 = time.perf_counter()
            self.recording = True
            self.btn_rec.restyle(ACCENT, BG, "#ff7255")
            self.btn_rec.config(text="Parar  F8")
            self.show("Grabando", "0 eventos · 0.0 s", ACCENT)

    def on_move(self, x, y):
        if self.recording and self.now() - self.last_move > 0.01:
            self.last_move = self.now()
            self.add(type="move", x=x, y=y)

    def on_click(self, x, y, button, pressed):
        if self.recording:
            self.add(type="click", x=x, y=y, b=button.name, p=pressed)

    def on_scroll(self, x, y, dx, dy):
        if self.recording:
            self.add(type="scroll", x=x, y=y, dx=dx, dy=dy)

    def on_press(self, key):
        if key == HOTKEY_REC:
            self.q.put(self.toggle_rec)
        elif key == HOTKEY_PLAY:
            self.q.put(self.toggle_play)
        elif self.recording:
            self.add(type="key", k=key_to_str(key), p=True)

    def on_release(self, key):
        if key in (HOTKEY_REC, HOTKEY_PLAY):
            return
        if self.recording:
            self.add(type="key", k=key_to_str(key), p=False)

    # ---------- reproducción ----------
    def toggle_play(self):
        if self.recording:
            return
        if self.playing:
            self.playing = False
            return
        if not self.events:
            self.show("Vacío", "Graba algo primero con F8", MUTED)
            return
        if self.from_file:
            # una grabación de un archivo ajeno pulsa teclas y clics en tu equipo
            if not messagebox.askyesno(APP_NAME,
                    "Esta grabación viene de un archivo.\nReproducirla controlará tu ratón y "
                    "teclado.\n\n¿Solo si confías en su origen: continuar?"):
                return
            self.from_file = False
        self.playing = True
        self.btn_play.restyle(ACCENT, BG, "#ff7255")
        self.btn_play.config(text="Parar  F9")
        threading.Thread(target=self.play_worker, args=(self.reps_n, self.speed_x),
                         daemon=True).start()

    def play_worker(self, reps, speed):
        n = 0
        pressed_keys, pressed_btns = set(), set()
        try:
            while self.playing and (reps == 0 or n < reps):
                n += 1
                label = "vuelta %d" % n if reps == 0 else "vuelta %d de %d" % (n, reps)
                self.q.put(lambda t=label: self.show("Reproduciendo", t, ACCENT))
                start = time.perf_counter()
                for ev in self.events:
                    if not self.playing:
                        break
                    self.wait_until(start + ev["t"] / speed)
                    if not self.playing:
                        break
                    self.do_event(ev, pressed_keys, pressed_btns)
                time.sleep(0.02)
        except Exception as exc:  # no dejar el hilo muerto en silencio
            self.q.put(lambda e=exc: self.show("Error", str(e)[:60], ACCENT))
        finally:
            for k in pressed_keys:
                self.kctl.release(k)
            for b in pressed_btns:
                self.mctl.release(b)
            self.playing = False
            self.q.put(self.after_play)

    def wait_until(self, target):
        """Espera en tramos cortos para poder parar con F9 al instante."""
        while self.playing:
            rest = target - time.perf_counter()
            if rest <= 0:
                return
            time.sleep(min(rest, 0.05))

    def after_play(self):
        self.btn_play.restyle(INK, BG, "#ffffff")
        self.btn_play.config(text="Reproducir  F9")
        if self.state.cget("text") != "Error":
            self.show("Listo", "%d eventos" % len(self.events))

    def do_event(self, ev, pk, pb):
        t = ev["type"]
        if t == "move":
            self.mctl.position = (ev["x"], ev["y"])
        elif t == "click":
            self.mctl.position = (ev["x"], ev["y"])
            btn = mouse.Button[ev["b"]]
            if ev["p"]:
                self.mctl.press(btn)
                pb.add(btn)
            else:
                self.mctl.release(btn)
                pb.discard(btn)
        elif t == "scroll":
            self.mctl.position = (ev["x"], ev["y"])
            self.mctl.scroll(ev["dx"], ev["dy"])
        elif t == "key":
            k = str_to_key(ev["k"])
            if ev["p"]:
                self.kctl.press(k)
                pk.add(k)
            else:
                self.kctl.release(k)
                pk.discard(k)

    # ---------- archivos ----------
    def save(self):
        if not self.events:
            messagebox.showinfo(APP_NAME, "No hay nada grabado.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".json",
                                            filetypes=[("Grabación", "*.json")])
        if path:
            try:
                with open(path, "w", encoding="utf-8") as fh:
                    json.dump(self.events, fh)
                self.show("Guardado", os.path.basename(path))
            except OSError as exc:
                messagebox.showerror(APP_NAME, "No se pudo guardar:\n%s" % exc)

    def load(self):
        if self.recording or self.playing:
            return
        path = filedialog.askopenfilename(filetypes=[("Grabación", "*.json")])
        if not path:
            return
        try:
            if os.path.getsize(path) > MAX_FILE_BYTES:
                raise ValueError("El archivo es demasiado grande.")
            with open(path, encoding="utf-8") as fh:
                data = validate_events(json.load(fh))
        except (OSError, ValueError, RecursionError) as exc:  # JSONDecodeError es ValueError
            messagebox.showerror(APP_NAME, "No se pudo abrir:\n%s" % exc)
            return
        self.events = data
        self.from_file = True
        self.show("Cargado", "%d eventos · %s" % (len(data), os.path.basename(path)))

    def close(self):
        self.playing = False
        self.k_listener.stop()
        self.m_listener.stop()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
