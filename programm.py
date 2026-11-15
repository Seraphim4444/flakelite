#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FlakeLite — бесплатный новогодний снег поверх рабочего стола Windows.

Один файл, Qt 6 (PySide6), без внешних картинок и интернета.

Запуск:
    python programm.py
    pythonw programm.py            (без чёрного окна консоли)
    python programm.py --fps       (показать счётчик кадров)
    python programm.py --exit-after 10   (автовыход, для проверок)
"""

from __future__ import annotations

import argparse
import ctypes
import datetime
import json
import math
import os
import random
import sys
import time
from ctypes import wintypes
from pathlib import Path

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QAction, QActionGroup, QColor, QCursor, QFont, QGuiApplication, QIcon, QImage,
    QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QPolygonF,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QHBoxLayout, QLabel, QMenu,
    QMessageBox, QPushButton, QSlider, QSystemTrayIcon, QVBoxLayout, QWidget,
)

# В сборке без консоли stdout/stderr бывают None или битым handle —
# тогда print() падает с OSError [Errno 22]. Уводим вывод в devnull.
if getattr(sys, "frozen", False) or sys.stdout is None:
    try:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    except Exception:
        sys.stdout = None
if getattr(sys, "frozen", False) or sys.stderr is None:
    try:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    except Exception:
        sys.stderr = None

APP_NAME = "FlakeLite"
APP_VERSION = "0.2.3"
APP_DIR = Path(__file__).resolve().parent if not getattr(sys, "frozen", False) \
    else Path(sys.executable).resolve().parent

# --------------------------------------------------------------------------
# Win32
# --------------------------------------------------------------------------

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)

SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN = 76, 77
SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 78, 79
SPI_GETWORKAREA = 0x0030

GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
MONITOR_DEFAULTTONEAREST = 2


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG), ("top", wintypes.LONG),
        ("right", wintypes.LONG), ("bottom", wintypes.LONG),
    ]


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", RECT),
        ("rcWork", RECT),
        ("dwFlags", wintypes.DWORD),
    ]


user32.GetSystemMetrics.argtypes = [ctypes.c_int]
user32.GetSystemMetrics.restype = ctypes.c_int
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
user32.GetWindowRect.restype = wintypes.BOOL
user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
user32.MonitorFromWindow.restype = wintypes.HANDLE
user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MONITORINFO)]
user32.GetMonitorInfoW.restype = wintypes.BOOL
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.restype = ctypes.c_int

if ctypes.sizeof(ctypes.c_void_p) == 8:
    _get_long = user32.GetWindowLongPtrW
    _get_long.argtypes = [wintypes.HWND, ctypes.c_int]
    _get_long.restype = ctypes.c_ssize_t
    _set_long = user32.SetWindowLongPtrW
    _set_long.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    _set_long.restype = ctypes.c_ssize_t
else:  # 32-битный Python
    _get_long = user32.GetWindowLongW
    _get_long.argtypes = [wintypes.HWND, ctypes.c_int]
    _get_long.restype = ctypes.c_long
    _set_long = user32.SetWindowLongW
    _set_long.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
    _set_long.restype = ctypes.c_long

kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)
]
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
user32.EnumWindows.restype = wintypes.BOOL
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.IsIconic.argtypes = [wintypes.HWND]
user32.IsIconic.restype = wintypes.BOOL
user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindow.restype = wintypes.BOOL
user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
user32.GetCursorPos.restype = wintypes.BOOL
user32.WindowFromPoint.argtypes = [wintypes.POINT]
user32.WindowFromPoint.restype = wintypes.HWND
user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int,
                                  wintypes.UINT, wintypes.UINT]
user32.RegisterHotKey.restype = wintypes.BOOL
user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
user32.UnregisterHotKey.restype = wintypes.BOOL
user32.SystemParametersInfoW.argtypes = [wintypes.UINT, wintypes.UINT,
                                         ctypes.c_void_p, wintypes.UINT]
user32.SystemParametersInfoW.restype = wintypes.BOOL
dwmapi.DwmGetWindowAttribute.argtypes = [
    wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD
]
dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long


def set_dpi_awareness() -> None:
    """До создания QApplication: координаты Win32 должны совпадать с пикселями."""
    try:
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # PER_MONITOR_AWARE_V2
        return
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass


def virtual_screen() -> QRect:
    return QRect(
        user32.GetSystemMetrics(SM_XVIRTUALSCREEN),
        user32.GetSystemMetrics(SM_YVIRTUALSCREEN),
        user32.GetSystemMetrics(SM_CXVIRTUALSCREEN),
        user32.GetSystemMetrics(SM_CYVIRTUALSCREEN),
    )


def work_area() -> QRect:
    """Рабочий стол без панели задач (физические пиксели)."""
    r = RECT()
    try:
        if user32.SystemParametersInfoW(SPI_GETWORKAREA, 0,
                                        ctypes.byref(r), 0):
            return QRect(r.left, r.top, r.right - r.left, r.bottom - r.top)
    except Exception:
        pass
    return virtual_screen()


def cursor_physical() -> QPoint:
    pt = wintypes.POINT()
    if user32.GetCursorPos(ctypes.byref(pt)):
        return QPoint(int(pt.x), int(pt.y))
    return QPoint(0, 0)


def window_from_point(pt: QPoint) -> int:
    try:
        return int(user32.WindowFromPoint(wintypes.POINT(pt.x(), pt.y())))
    except Exception:
        return 0


def window_class(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    n = user32.GetClassNameW(hwnd, buf, 256)
    return buf.value[:n] if n else ""


def window_pid(hwnd: int) -> int:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value)


def process_name(hwnd: int) -> str:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return ""
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value).lower()
    finally:
        kernel32.CloseHandle(h)
    return ""


def notification_state() -> int:
    """0 = неизвестно, 2 busy, 3 d3d-fullscreen, 4 presentation, 6 quiet."""
    state = ctypes.c_int(0)
    try:
        hr = shell32.SHQueryUserNotificationState(ctypes.byref(state))
        if hr == 0:
            return state.value
    except Exception:
        pass
    return 0


def foreground_fullscreen_app() -> str:
    """Имя процесса, если активное окно занимает целый монитор (и это не рабочий стол)."""
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return ""
    cls = window_class(hwnd)
    if cls in ("Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"):
        return ""

    rect = RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return ""

    mon = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
    if not mon:
        return ""
    mi = MONITORINFO()
    mi.cbSize = ctypes.sizeof(MONITORINFO)
    if not user32.GetMonitorInfoW(mon, ctypes.byref(mi)):
        return ""

    m = mi.rcMonitor
    fw = rect.right - rect.left
    fh = rect.bottom - rect.top
    mw = m.right - m.left
    mh = m.bottom - m.top
    if fw < mw - 2 or fh < mh - 2:
        return ""
    if abs(rect.left - m.left) > 2 or abs(rect.top - m.top) > 2:
        return ""
    return process_name(hwnd)


# --------------------------------------------------------------------------
# Конфиг
# --------------------------------------------------------------------------

DEFAULT_CONFIG = {
    "weather": "steady",          # light | steady | blizzard
    "density": 1.0,               # множитель количества снежинок
    "wind": 0.0,                  # -1..1
    "quality": 60,                # целевой FPS: 20 | 30 | 60
    "show_fps": False,
    "paused": False,
    "pause_on_fullscreen": True,
    "pause_apps": [],             # например ["cs2.exe", "dota2.exe"]
    "garland": True,
    "tree": True,
    "countdown": True,
    "auto_fireworks": True,
    "auto_santa": True,
    "auto_plow": True,
    "old_wallpaper": "",
    "wallpaper_active": False,
    "wallpaper_caption": True,
    "snow_on_windows": True,
    "autostart": False,
    "hud_visible": True,
    "hud_pos": None,
    "show_donate": True,
}


def config_path() -> Path:
    local = APP_DIR / "config.json"
    try:
        if local.exists():
            local.touch(exist_ok=True)
            return local
        probe = APP_DIR / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return local
    except Exception:
        appdata = Path(os.environ.get("APPDATA", str(Path.home()))) / APP_NAME
        appdata.mkdir(parents=True, exist_ok=True)
        return appdata / "config.json"


def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    path = config_path()
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for k, v in data.items():
                    if k in cfg:
                        cfg[k] = v
    except Exception:
        pass
    return cfg


def save_config(cfg: dict) -> None:
    try:
        path = config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


# --------------------------------------------------------------------------
# Маленькие утилиты
# --------------------------------------------------------------------------

def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


def make_snowflake_icon(px: int = 64) -> QIcon:
    """Иконка рисуется кодом: ни одного внешнего файла."""
    pm = QPixmap(px, px)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setPen(QPen(QColor(236, 246, 255), max(1.5, px / 20.0),
                  Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    cx = cy = px / 2.0
    radius = px * 0.40
    for i in range(6):
        a = math.radians(i * 60.0)
        dx, dy = math.cos(a), math.sin(a)
        p.drawLine(QPointF(cx - dx * radius, cy - dy * radius),
                   QPointF(cx + dx * radius, cy + dy * radius))
        for k in (0.48, 0.74):
            bx, by = cx + dx * radius * k, cy + dy * radius * k
            for side in (-1.0, 1.0):
                a2 = a + side * math.radians(34.0)
                p.drawLine(QPointF(bx, by),
                           QPointF(bx + math.cos(a2) * radius * 0.30,
                                   by + math.sin(a2) * radius * 0.30))
    p.end()
    return QIcon(pm)


# --------------------------------------------------------------------------
# Снег
# --------------------------------------------------------------------------

WEATHER = {
    # count — при плотности 1.0 и среднем качестве
    "light":    dict(count=240,  speed=(16, 44),  size=(0.7, 1.9), wind=0.55),
    "steady":   dict(count=480,  speed=(30, 78),  size=(0.9, 2.4), wind=1.0),
    "blizzard": dict(count=820,  speed=(60, 145), size=(1.0, 2.8), wind=2.3),
}


class Flake:
    __slots__ = ("x", "y", "r", "vy", "vx", "ph", "amp", "freq", "depth",
                 "streak", "g")

    def __init__(self) -> None:
        self.x = self.y = self.r = 0.0
        self.vy = self.vx = 0.0
        self.ph = self.amp = self.freq = 0.0
        self.depth = 0.0
        self.streak = False
        self.g = 0.0


class Ball:
    """Снежок, который катают, ставят на сугроб и роняют."""

    __slots__ = ("x", "y", "r", "vx", "vy", "g", "drift", "adx", "ah",
                 "falling")

    def __init__(self, x: float, y: float, r: float) -> None:
        self.x = x
        self.y = y
        self.r = r
        self.vx = 0.0
        self.vy = 0.0
        self.g = 780.0
        self.drift = None          # сугроб, на котором лежит шар
        self.adx = 0.0             # смещение от левого края сугроба
        self.ah = r                # высота центра над кромкой сугроба
        self.falling = True


class Snowman:
    """Три шара, которые держатся вместе и падают с окна всей фигурой."""

    __slots__ = ("balls", "drift", "adx", "ah", "falling", "vx", "vy", "g")

    def __init__(self, balls: list[Ball], drift, adx: float,
                 ah: float) -> None:
        self.balls = balls
        self.drift = drift
        self.adx = adx
        self.ah = ah
        self.falling = False
        self.vx = 0.0
        self.vy = 0.0
        self.g = 760.0


class SnowSystem:
    """Частицы снегопада. Сугробы добавятся на следующем этапе."""

    def __init__(self, width: int, height: int) -> None:
        self.w = max(1, width)
        self.h = max(1, height)
        self.flakes: list[Flake] = []
        self.weather = "steady"
        self.density = 1.0
        self.quality_scale = 1.0
        self.wind = 0.0
        self.t = 0.0
        self.gust = 1.0
        self.last_wind_px = 0.0
        self.landing = None

    # -- параметры ------------------------------------------------------
    def set_weather(self, weather: str, density: float = 1.0) -> None:
        self.weather = weather if weather in WEATHER else "steady"
        self.density = clamp(density, 0.2, 2.0)
        for f in self.flakes:
            f.streak = self.weather == "blizzard" and f.depth > 0.35
        self._sync_count()

    def set_quality_scale(self, scale: float) -> None:
        self.quality_scale = clamp(scale, 0.30, 1.0)
        self._sync_count()

    def set_wind(self, wind: float) -> None:
        self.wind = clamp(wind, -1.0, 1.0)

    def stir(self, x: float, y: float, radius: float,
             dx: float, dy: float) -> None:
        """Курсор разгоняет снежинки рядом с собой."""
        r2 = radius * radius
        for f in self.flakes:
            ddx = f.x - x
            ddy = f.y - y
            d2 = ddx * ddx + ddy * ddy
            if d2 >= r2:
                continue
            t = 1.0 - d2 / r2
            f.vx += dx * 2.2 * t + ddx * 0.35 * t
            f.y += dy * 0.5 * t
            f.x += ddx * 0.05 * t

    def shed(self, x: float, y: float, vx: float, vy: float,
             r: float, depth: float = 0.6) -> None:
        """Оторвавшаяся от сугроба снежинка: падает и ложится на пол."""
        if len(self.flakes) > self.target_count() + 140:
            return
        f = Flake()
        f.x = float(x)
        f.y = float(y)
        f.r = float(r)
        f.vx = float(vx)
        f.vy = float(vy)
        f.depth = clamp(depth, 0.0, 1.0)
        f.ph = random.uniform(0.0, math.tau)
        f.amp = random.uniform(3.0, 12.0)
        f.freq = random.uniform(0.8, 2.2)
        f.streak = False
        f.g = random.uniform(620.0, 900.0)
        self.flakes.append(f)

    def resize(self, width: int, height: int) -> None:
        self.w = max(1, width)
        self.h = max(1, height)
        for f in self.flakes:
            f.x = clamp(f.x, 0.0, float(self.w))
            f.y = clamp(f.y, -float(self.h) * 0.3, float(self.h))

    def target_count(self) -> int:
        base = WEATHER[self.weather]["count"]
        return max(20, int(base * self.density * self.quality_scale))

    def _sync_count(self) -> None:
        want = self.target_count()
        while len(self.flakes) > want:
            self.flakes.pop()
        while len(self.flakes) < want:
            f = Flake()
            self._spawn(f, initial=True)
            self.flakes.append(f)

    # -- частицы --------------------------------------------------------
    def _spawn(self, f: Flake, initial: bool = False) -> None:
        cfg = WEATHER[self.weather]
        d = random.random()
        f.depth = d
        f.r = lerp(cfg["size"][0], cfg["size"][1], d) * random.uniform(0.85, 1.15)
        f.vy = lerp(cfg["speed"][0], cfg["speed"][1], d) * random.uniform(0.8, 1.2)
        f.vx = random.uniform(-8.0, 8.0)
        f.x = random.uniform(-30.0, self.w + 30.0)
        f.y = random.uniform(0.0, self.h) if initial else random.uniform(-60.0, -4.0)
        f.ph = random.uniform(0.0, math.tau)
        f.amp = random.uniform(5.0, 22.0) * (0.45 + d)
        f.freq = random.uniform(0.35, 1.4)
        f.streak = self.weather == "blizzard" and d > 0.35
        f.g = 0.0

    def update(self, dt: float) -> None:
        dt = min(dt, 0.05)
        self.t += dt
        cfg = WEATHER[self.weather]
        # Порывы ветра: медленная волна + быстрая рябь, 0.4..1.2
        self.gust = (0.72
                     + 0.30 * math.sin(self.t * 0.21)
                     + 0.14 * math.sin(self.t * 0.67 + 1.7))
        wind_px = clamp(self.wind * 250.0 * cfg["wind"] * self.gust, -460.0, 460.0)
        self.last_wind_px = wind_px
        h = float(self.h)
        w = float(self.w)
        landing = self.landing
        for f in self.flakes:
            prev_y = f.y
            if f.vx != 0.0:
                f.vx -= f.vx * min(0.9, dt * 1.6)
            f.x += (f.vx + wind_px * (0.35 + f.depth) +
                    math.sin(self.t * f.freq + f.ph) * f.amp) * dt
            if f.g > 0.0:
                f.vy = min(f.vy + f.g * dt, 620.0)
            f.y += f.vy * dt
            if landing is not None:
                drift = landing(f.x, prev_y, f.y)
                if drift is not None:
                    drift.add(f.x, f.r)
                    self._spawn(f)
                    continue
            if f.y > h + 6.0:
                self._spawn(f)
            elif f.x < -40.0:
                f.x = w + 35.0
            elif f.x > w + 40.0:
                f.x = -35.0


# --------------------------------------------------------------------------
# Сугробы
# --------------------------------------------------------------------------

class Drift:
    """Поле высот снега вдоль горизонтальной кромки: снег растёт вверх от y."""

    __slots__ = ("x", "y", "w", "cell", "n", "h", "cap", "kind", "hwnd",
                 "_version", "_pix", "_pix_version", "_pix_t", "_draw_y")

    def __init__(self, x: float, width: float, y: float,
                 cell: float = 5.0, cap: float = 26.0,
                 kind: str = "bottom", hwnd: int = 0) -> None:
        self.x = float(x)
        self.y = float(y)
        self.w = float(width)
        self.cell = float(cell)
        self.n = max(3, int(self.w / self.cell) + 1)
        self.h = [0.0] * self.n
        self.cap = float(cap)
        self.kind = kind
        self.hwnd = hwnd
        self._version = 0
        self._pix = None
        self._pix_version = -1
        self._pix_t = 0.0
        self._draw_y = self.y

    # -- геометрия ------------------------------------------------------
    def contains(self, x: float) -> bool:
        return self.x <= x <= self.x + (self.n - 1) * self.cell

    def _edge_k(self, i: int) -> float:
        """0 у торцов окна, 1 в середине: сугроб плавно сходит на нет."""
        if self.kind != "window":
            return 1.0
        d = min(i * self.cell, (self.n - 1 - i) * self.cell)
        edge = min(34.0, max(14.0, (self.n - 1) * self.cell * 0.05))
        t = clamp(d / edge, 0.0, 1.0)
        return t * t * (3.0 - 2.0 * t)

    def _cap_at(self, i: int) -> float:
        """Живая неровная кромка вместо идеально плоского «стола»."""
        w1 = 0.5 + 0.5 * math.sin(i * 0.41 + 0.8)
        w2 = 0.5 + 0.5 * math.sin(i * 1.13 + 2.1)
        return self.cap * (0.90 + 0.06 * w1 + 0.04 * w2)

    def surface(self, x: float) -> float:
        u = (x - self.x) / self.cell
        i = int(math.floor(u))
        if i < 0:
            return self.y
        if i >= self.n - 1:
            return self.y - self.h[self.n - 1] * self._edge_k(self.n - 1)
        t = u - i
        h = self.h[i] * (1.0 - t) + self.h[i + 1] * t
        k = self._edge_k(i) * (1.0 - t) + self._edge_k(i + 1) * t
        return self.y - h * k

    def move_to(self, x: float, y: float) -> None:
        # Позицию рисуем напрямую, поле высот при этом не меняется —
        # поэтому пересобирать пиксмап при перетаскивании окна не нужно.
        self.x = float(x)
        self.y = float(y)

    def resize_width(self, width: float) -> None:
        n = max(3, int(width / self.cell) + 1)
        self.w = float(width)
        if n == self.n:
            return
        old = self.h
        new = [0.0] * n
        for i in range(min(n, len(old))):
            new[i] = old[i]
        self.h = new
        self.n = n
        self._version += 1

    # -- снег -----------------------------------------------------------
    def add(self, x: float, radius: float) -> None:
        i = int((x - self.x) / self.cell)
        if not (0 <= i < self.n):
            return
        k = self._edge_k(i)
        if k <= 0.0:
            return
        v = self.h[i] + (2.2 + radius * 1.4) * k
        self._version += 1
        cap = self._cap_at(i)
        if v > cap:
            over = v - cap
            self.h[i] = cap
            # пересыпаем излишек соседям — сугроб растёт вширь
            if i > 0:
                j = i - 1
                self.h[j] = min(self._cap_at(j),
                                self.h[j] + over * 0.55 * self._edge_k(j))
            if i + 1 < self.n:
                j = i + 1
                self.h[j] = min(self._cap_at(j),
                                self.h[j] + over * 0.55 * self._edge_k(j))
        else:
            self.h[i] = v

    def settle(self) -> None:
        """Медленно разравниваем бугры, чтобы сугроб выглядел живым."""
        h = self.h
        n = self.n
        changed = False
        for i in range(1, n - 1):
            avg = (h[i - 1] + h[i + 1]) * 0.5
            delta = avg - h[i]
            if delta > 0.02:
                h[i] = min(self._cap_at(i), h[i] + delta * 0.07)
                changed = True
        if changed:
            self._version += 1

    def wipe(self, x: float, y: float, radius: float,
             strength: float = 1.0) -> float:
        """Смести снег курсором. Возвращает, сколько снято."""
        if not (self.y - self.cap - 26.0 <= y <= self.y + 26.0):
            return 0.0
        cell = self.cell
        i0 = int((x - radius - self.x) / cell)
        i1 = int((x + radius - self.x) / cell)
        if i1 < 0 or i0 >= self.n:
            return 0.0
        removed = 0.0
        for i in range(max(0, i0), min(self.n, i1 + 1)):
            cx = self.x + i * cell
            t = 1.0 - abs(cx - x) / radius
            if t <= 0.0:
                continue
            d = self.h[i] * min(1.0, t * 1.7) * strength
            if d > 0.0:
                self.h[i] -= d
                removed += d
        if removed > 0.0:
            self._version += 1
        return removed

    def clear(self) -> None:
        self.h = [0.0] * self.n
        self._version += 1

    def is_empty(self) -> bool:
        for v in self.h:
            if v > 0.12:
                return False
        return True

    # -- рисование ------------------------------------------------------
    def _display_heights(self) -> list[float]:
        n = self.n
        h = [self.h[i] * self._edge_k(i) for i in range(n)]
        # два прохода лёгкого сглаживания убирают «ступеньки» из ячеек
        for _ in range(2):
            src = h
            h = src[:]
            for i in range(1, n - 1):
                h[i] = src[i - 1] * 0.25 + src[i] * 0.5 + src[i + 1] * 0.25
        return h

    def _build_pixmap(self) -> None:
        hgt = int(self.cap) + 6
        wpx = int((self.n - 1) * self.cell) + 1
        if wpx <= 0:
            return
        pm = QPixmap(wpx, hgt)
        pm.fill(Qt.GlobalColor.transparent)
        pp = QPainter(pm)
        pp.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        base = float(hgt - 1)
        grad = QLinearGradient(0.0, base - self.cap, 0.0, base)
        grad.setColorAt(0.0, QColor(255, 255, 255, 252))
        grad.setColorAt(0.45, QColor(247, 252, 255, 244))
        grad.setColorAt(1.0, QColor(208, 228, 246, 238))

        n = self.n
        cell = self.cell
        cap = self.cap
        h = self._display_heights()

        # Гладкая кривая по кромке: квадратичные сегменты вместо ломаной.
        top = QPainterPath(QPointF(0.0, base - min(cap, h[0])))
        for i in range(1, n - 1):
            x = i * cell
            y = base - min(cap, h[i])
            y2 = base - min(cap, h[i + 1])
            top.quadTo(QPointF(x, y), QPointF(x + cell * 0.5, (y + y2) * 0.5))
        top.lineTo(QPointF((n - 1) * cell, base - min(cap, h[n - 1])))

        body = QPainterPath(top)
        body.lineTo(QPointF((n - 1) * cell, base))
        body.lineTo(QPointF(0.0, base))
        body.closeSubpath()

        pp.setPen(Qt.PenStyle.NoPen)
        pp.setBrush(grad)
        pp.drawPath(body)

        # мягкий блик по кромке: контур читается, но не «режет» глаз
        pp.setBrush(Qt.BrushStyle.NoBrush)
        pp.setPen(QPen(QColor(255, 255, 255, 135), 1.0,
                       Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        pp.drawPath(top)
        pp.end()

        self._pix = pm
        self._draw_y = self.y - (hgt - 1)

    def paint(self, p: QPainter) -> None:
        if max(self.h) < 0.12:
            return
        now = time.perf_counter()
        if (self._pix is None
                or (self._pix_version != self._version and now - self._pix_t > 0.05)):
            self._build_pixmap()
            self._pix_t = now
            self._pix_version = self._version
        if self._pix is not None:
            p.drawPixmap(QPointF(self.x, self.y - (self._pix.height() - 1)), self._pix)


class WindowTracker:
    """Следит за настоящими окнами Windows и держит сугроб на каждом."""

    MAX_WINDOWS = 7
    SKIP_CLASSES = {
        "Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd",
        "Windows.UI.Core.CoreWindow", "ApplicationFrameWindow", "TaskListThumbnailWnd",
    }

    def __init__(self, overlay: "Overlay") -> None:
        self.overlay = overlay
        self.drifts: dict[int, Drift] = {}
        self._miss: dict[int, int] = {}
        self._order: list[int] = []          # сверху вниз по z
        self._zlist: list[tuple] = []        # все видимые окна в z-порядке
        self._cb = WNDENUMPROC(self._on_window)
        self._acc = 0.0
        self._settle_acc = 0.0
        self._ox = 0
        self._oy = 0

    # -- перечисление ---------------------------------------------------
    def _on_window(self, hwnd: int, _lparam: int) -> bool:
        try:
            self._consider(hwnd)
        except Exception:
            pass
        return True

    def _consider(self, hwnd: int) -> None:
        u = user32
        if not u.IsWindowVisible(hwnd) or u.IsIconic(hwnd):
            return

        pid = wintypes.DWORD()
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == os.getpid():
            return

        cloaked = wintypes.DWORD(0)
        if dwmapi.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(cloaked),
                                        ctypes.sizeof(cloaked)) == 0 and cloaked.value:
            return

        rect = RECT()
        if dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(rect),
                                        ctypes.sizeof(rect)) != 0:
            if not u.GetWindowRect(hwnd, ctypes.byref(rect)):
                return

        w = rect.right - rect.left
        h = rect.bottom - rect.top
        if w < 40 or h < 40:
            return

        mon = u.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
        if not mon:
            return
        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(MONITORINFO)
        if not u.GetMonitorInfoW(mon, ctypes.byref(mi)):
            return

        m = mi.rcMonitor
        if rect.bottom <= m.top or rect.top >= m.bottom:
            return
        if rect.right <= m.left or rect.left >= m.right:
            return

        # Кандидат — окно, на кромку которого можно класть снег.
        # Важно: все видимые окна попадают в список, чтобы полноэкранное
        # приложение (его мы не украшаем) закрывало кромки окон под ним.
        cand = True
        if window_class(hwnd) in self.SKIP_CLASSES:
            cand = False
        if _get_long(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW:
            cand = False
        if w < 140 or h < 80:
            cand = False
        if rect.top <= m.top + 2:          # развёрнуто/полный экран
            cand = False
        if rect.top >= m.bottom - 70:      # почти целиком за нижним краем
            cand = False

        self._zlist.append((hwnd,
                            (rect.left - self._ox) / self.overlay.dpr,
                            (rect.top - self._oy) / self.overlay.dpr,
                            w / self.overlay.dpr, h / self.overlay.dpr, cand))

    def refresh(self) -> None:
        self._zlist = []
        vs = virtual_screen()
        self._ox, self._oy = vs.x(), vs.y()
        user32.EnumWindows(self._cb, 0)
        z = self._zlist

        # Верхнюю кромку окна не видно, если её закрыло ЛЮБОЕ окно выше,
        # включая полноэкранное, которое само снегом не украшается.
        kept: list[tuple] = []
        for idx, item in enumerate(z):
            hwnd, x, y, w, h, cand = item
            if not cand:
                continue
            probes = (x + w * 0.25, x + w * 0.5, x + w * 0.75)
            covered = 0
            for px in probes:
                for j in range(idx):
                    _h, ox, oy, ow, oh, _c = z[j]
                    if ox <= px <= ox + ow and oy <= y + 1 <= oy + oh:
                        covered += 1
                        break
            if covered >= 2:
                continue
            kept.append((hwnd, x, y, w))
            if len(kept) >= self.MAX_WINDOWS:
                break

        if not self.overlay.cfg.get("snow_on_windows", True):
            kept = []
            self.drifts.clear()
            self._miss.clear()

        seen: set[int] = set()
        order: list[int] = []
        for hwnd, x, y, w in kept:
            seen.add(hwnd)
            order.append(hwnd)
            d = self.drifts.get(hwnd)
            if d is None:
                self.drifts[hwnd] = Drift(x, w, y, cell=7.0, cap=15.0,
                                          kind="window", hwnd=hwnd)
            else:
                d.move_to(x, y)
                d.resize_width(w)
            self._miss[hwnd] = 0

        for hwnd in list(self.drifts):
            if hwnd in seen:
                continue
            self._miss[hwnd] = self._miss.get(hwnd, 0) + 1
            if self._miss[hwnd] >= 2:
                self.drifts.pop(hwnd, None)
                self._miss.pop(hwnd, None)

        self._order = order
        self.overlay.on_windows_changed()

        if self.overlay.debug_windows:
            print("--- windows %d ---" % len(kept), flush=True)
            for hwnd, x, y, w in kept:
                d = self.drifts.get(hwnd)
                hmax = max(d.h) if d is not None else 0.0
                print("  %8d %-28s %-18s x=%4d y=%4d w=%4d hmax=%4.1f" % (
                    hwnd, window_class(hwnd)[:28], process_name(hwnd)[:18],
                    x, y, w, hmax), flush=True)

    # -- слежение за окнами ---------------------------------------------
    def follow(self, snow: "SnowSystem", dt: float) -> None:
        """Каждый кадр подтягивает сугробы к их окнам.

        Раньше позиции обновлялись раз в 0.4 с — окно уезжало, а снег
        догонял рывком. Теперь рассинхрон максимум в один кадр.
        """
        if not self.drifts:
            return
        vs = virtual_screen()
        ox, oy = vs.x(), vs.y()
        dpr = self.overlay.dpr or 1.0
        for hwnd, d in list(self.drifts.items()):
            if not user32.IsWindow(hwnd) or user32.IsIconic(hwnd):
                self._drop(hwnd, d, snow)
                continue
            rect = RECT()
            if dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(rect),
                                            ctypes.sizeof(rect)) != 0:
                if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                    self._drop(hwnd, d, snow)
                    continue
            x = (rect.left - ox) / dpr
            y = (rect.top - oy) / dpr
            w = (rect.right - rect.left) / dpr
            if w < 60.0 or y <= 2.0:
                self._drop(hwnd, d, snow)
                continue
            dx = x - d.x
            dy = y - d.y
            d.move_to(x, y)
            if abs(w - d.w) > 1.0:
                d.resize_width(w)
            if (abs(dx) + abs(dy) > 0.8) and dt > 0.0:
                self._shed_move(d, snow, dx, dy, dt)

    def _drop(self, hwnd: int, d: Drift, snow: "SnowSystem") -> None:
        self._shed_all(d, snow)
        self.drifts.pop(hwnd, None)
        self._miss.pop(hwnd, None)
        if hwnd in self._order:
            self._order = [h for h in self._order if h != hwnd]
        self.overlay.on_windows_changed()

    @staticmethod
    def _shed_move(d: Drift, snow: "SnowSystem", dx: float, dy: float,
                   dt: float) -> None:
        speed = math.hypot(dx, dy) / max(dt, 1e-3)
        if speed < 120.0:
            return
        sig = 1.0 if dx >= 0.0 else -1.0
        if abs(dx) >= abs(dy):
            ex = d.x + (6.0 if sig > 0.0 else d.w - 6.0)   # отстающий край
        else:
            ex = d.x + d.w * 0.5
        surf = d.surface(ex)
        if surf >= d.y - 0.5:
            return
        removed = d.wipe(ex, surf, 13.0, clamp(speed / 900.0, 0.02, 0.14))
        n = int(clamp(removed / 1.6, 0.0, 3.0))
        for _ in range(n):
            snow.shed(ex + random.uniform(-10.0, 10.0),
                      surf - random.uniform(0.0, 4.0),
                      -sig * random.uniform(18.0, 55.0),
                      random.uniform(8.0, 26.0),
                      random.uniform(0.9, 1.8), 0.55)

    @staticmethod
    def _shed_all(d: Drift, snow: "SnowSystem") -> None:
        """Окно свернули/закрыли — весь снег с кромки падает вниз."""
        if max(d.h) < 0.2:
            return
        n = int(clamp(d.w / 22.0, 10.0, 52.0))
        for _ in range(n):
            x = d.x + random.uniform(0.0, d.w)
            sy = d.surface(x)
            if sy >= d.y - 0.2:
                continue
            snow.shed(x + random.uniform(-6.0, 6.0),
                      sy + random.uniform(-2.0, 2.0),
                      random.uniform(-35.0, 35.0),
                      random.uniform(6.0, 28.0),
                      random.uniform(1.0, 2.2), 0.6)
        d.h = [0.0] * d.n

    # -- цикл -----------------------------------------------------------
    def tick(self, dt: float) -> None:
        self._acc += dt
        if self._acc >= 0.4:
            self._acc = 0.0
            self.refresh()

        self._settle_acc += dt
        if self._settle_acc >= 0.06:
            self._settle_acc = 0.0
            for d in self.drifts.values():
                d.settle()

    def paint_order(self) -> list[Drift]:
        # рисуем от нижних окон к верхним
        return [self.drifts[h] for h in reversed(self._order) if h in self.drifts]


# --------------------------------------------------------------------------
# Украшения: гирлянды, ёлка, счётчик, салют, Дед Мороз
# --------------------------------------------------------------------------

LIGHT_COLORS = (
    (255, 92, 92), (255, 190, 78), (126, 236, 148),
    (104, 198, 255), (204, 138, 255), (255, 255, 255),
)

_LIGHT_CACHE: dict[tuple[int, int], QPixmap] = {}


def light_pix(ci: int, level: int) -> QPixmap:
    """Готовая лампочка с ореолом: 6 цветов × 8 уровней яркости."""
    key = (ci % len(LIGHT_COLORS), level)
    pm = _LIGHT_CACHE.get(key)
    if pm is not None:
        return pm
    r, g, b = LIGHT_COLORS[key[0]]
    k = (level + 1) / 8.0
    pm = QPixmap(20, 20)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    grad = QRadialGradient(QPointF(10.0, 10.0), 10.0)
    grad.setColorAt(0.0, QColor(r, g, b, int(215 * k)))
    grad.setColorAt(0.34, QColor(r, g, b, int(95 * k)))
    grad.setColorAt(1.0, QColor(r, g, b, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(grad)
    p.drawEllipse(QRectF(0.0, 0.0, 20.0, 20.0))
    p.setBrush(QColor(min(255, r + 70), min(255, g + 70), min(255, b + 70),
                      int(255 * k)))
    p.drawEllipse(QPointF(10.0, 10.0), 2.7, 2.7)
    p.end()
    _LIGHT_CACHE[key] = pm
    return pm


def draw_light(p: QPainter, x: float, y: float, ci: int, level: int) -> None:
    p.drawPixmap(QPointF(x - 10.0, y - 10.0), light_pix(ci, level))


class Tree:
    """Ёлка в углу экрана: ровные ярусы, снег на ветках, звезда и огни."""

    def __init__(self) -> None:
        self.h = 0
        self.pix: QPixmap | None = None
        self.w = 0
        self.lights: list[tuple[float, float, int]] = []
        self.star = QPointF(0.0, 0.0)
        self.star_r = 10.0

    def build(self, height: int) -> None:
        height = int(clamp(int(height), 200, 380))
        if height == self.h and self.pix is not None:
            return
        self.h = height
        w = int(height * 0.72)
        self.w = w
        pm = QPixmap(w, height)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(Qt.PenStyle.NoPen)

        cx = w * 0.5
        base = float(height) - 6.0
        trunk_h = height * 0.13

        # ствол (виден под нижним ярусом)
        p.setBrush(QColor(98, 68, 46))
        p.drawRoundedRect(QRectF(cx - w * 0.045, base - trunk_h,
                                 w * 0.09, trunk_h), 2.0, 2.0)
        p.setBrush(QColor(74, 50, 34))
        p.drawRect(QRectF(cx - w * 0.045, base - trunk_h * 0.55,
                          w * 0.09, trunk_h * 0.55))

        tiers = 4
        th = height * 0.30
        step_y = height * 0.165
        yb0 = base - height * 0.075
        snow_pen = QPen(QColor(245, 251, 255, 242),
                        max(2.4, height * 0.013),
                        Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        tier_geo: list[tuple[float, float, float]] = []   # (yb, top, half)

        for i in range(tiers):
            yb = yb0 - i * step_y
            half = w * (0.455 - i * 0.094)
            top = yb - th * (1.0 - i * 0.045)
            tier_geo.append((yb, top, half))

            grad = QLinearGradient(0.0, top, 0.0, yb)
            grad.setColorAt(0.0, QColor(32 + i * 4, 104 + i * 5, 62 + i * 4))
            grad.setColorAt(0.55, QColor(22 + i * 3, 84 + i * 4, 50 + i * 3))
            grad.setColorAt(1.0, QColor(13 + i * 2, 62 + i * 3, 38 + i * 2))

            body = QPainterPath(QPointF(cx, top))
            body.quadTo(cx + half * 0.56, top + th * 0.46, cx + half, yb)
            body.quadTo(cx, yb + th * 0.115, cx - half, yb)
            body.quadTo(cx - half * 0.56, top + th * 0.46, cx, top)
            body.closeSubpath()
            p.setBrush(grad)
            p.drawPath(body)

            # снежная кромка на ветках — мягкая, округлая
            rim = QPainterPath(QPointF(cx - half, yb - height * 0.004))
            rim.quadTo(cx, yb + th * 0.105, cx + half, yb - height * 0.004)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(snow_pen)
            p.drawPath(rim)
            p.setBrush(QColor(247, 252, 255, 232))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(cx, yb + th * 0.055),
                          half * 0.13, max(1.6, height * 0.007))
            p.drawEllipse(QPointF(cx - half * 0.88, yb - height * 0.006),
                          half * 0.075, max(1.3, height * 0.006))
            p.drawEllipse(QPointF(cx + half * 0.88, yb - height * 0.006),
                          half * 0.075, max(1.3, height * 0.006))

        # звезда точно над вершиной
        yb_top, top_top, half_top = tier_geo[-1]
        self.star = QPointF(cx, top_top - height * 0.018)
        self.star_r = max(7.5, height * 0.052)
        # маленькая снежная шапка на макушке
        p.setBrush(QColor(248, 252, 255, 238))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, top_top + height * 0.012),
                      half_top * 0.24, max(2.0, height * 0.009))
        p.end()

        self.pix = pm

        # огни: детерминированно, по ярусам, чтобы не висли в воздухе
        rnd = random.Random(2027)
        lights: list[tuple[float, float, int]] = []
        per_tier = (6, 5, 4, 3)
        for i, (yb, top, half) in enumerate(tier_geo):
            for _ in range(per_tier[i]):
                u = rnd.uniform(0.18, 0.78)          # 0 — низ яруса, 1 — верх
                y = yb - (yb - top) * u
                spread = half * (1.0 - u) * 0.82
                x = cx + rnd.choice((-1.0, 1.0)) * rnd.uniform(0.25, 1.0) * spread
                lights.append((x, y, rnd.randrange(len(LIGHT_COLORS))))
        self.lights = lights

    def paint(self, p: QPainter, x_right: float, y_bottom: float, t: float) -> None:
        self.build(int(self.h or 280))
        if self.pix is None:
            return
        x = x_right - self.w
        y = y_bottom - self.h
        p.drawPixmap(QPointF(x, y), self.pix)

        # звезда
        cx = x + self.star.x()
        cy = y + self.star.y()
        r = self.star_r
        pulse = 0.65 + 0.35 * math.sin(t * 2.2)
        p.setPen(Qt.PenStyle.NoPen)
        glow = QRadialGradient(QPointF(cx, cy), r * 3.4)
        glow.setColorAt(0.0, QColor(255, 238, 170, int(120 * pulse)))
        glow.setColorAt(1.0, QColor(255, 220, 120, 0))
        p.setBrush(glow)
        p.drawEllipse(QPointF(cx, cy), r * 3.4, r * 3.4)
        p.setBrush(QColor(255, 228, 126, 255))
        star = []
        for i in range(10):
            a = -math.pi / 2.0 + i * math.pi / 5.0
            rr = r if i % 2 == 0 else r * 0.44
            star.append(QPointF(cx + math.cos(a) * rr, cy + math.sin(a) * rr))
        p.drawPolygon(QPolygonF(star))

        # мигающие огни: у каждого свой ритм, но без резких вспышек
        for i, (lx, ly, ci) in enumerate(self.lights):
            ph = t * 1.9 + i * 0.83
            level = int((0.5 + 0.5 * math.sin(ph)) * 7.99)
            draw_light(p, x + lx, y + ly, ci, level)


class Fireworks:
    """Салют: ракеты со шлейфом и разноцветные искры."""

    def __init__(self) -> None:
        self.rockets: list[list[float]] = []
        self.sparks: list[list[float]] = []
        self.run_for = 0.0
        self._next = 0.0

    def start(self, seconds: float = 7.0) -> None:
        self.run_for = max(self.run_for, seconds)

    def _color(self) -> tuple[int, int, int]:
        return random.choice((
            (255, 120, 120), (255, 205, 110), (140, 245, 165),
            (130, 205, 255), (215, 150, 255), (255, 255, 255),
        ))

    def _launch(self, w: int, h: int) -> None:
        x = random.uniform(w * 0.18, w * 0.82)
        target = random.uniform(h * 0.12, h * 0.42)
        vy = -math.sqrt(2.0 * 240.0 * max(60.0, h * 0.86 - target))
        self.rockets.append([x, float(h) + 6.0, random.uniform(-32.0, 32.0),
                             vy, target, 0.0])

    def burst(self, x: float, y: float) -> None:
        r, g, b = self._color()
        n = random.randint(70, 104)
        two = random.random() < 0.45
        r2, g2, b2 = self._color()
        for i in range(n):
            a = random.uniform(0.0, math.tau)
            sp = random.uniform(60.0, 235.0)
            use2 = two and i % 2 == 0
            self.sparks.append([
                x, y,
                math.cos(a) * sp, math.sin(a) * sp,
                1.25 + random.random() * 0.75,
                (r2, g2, b2) if use2 else (r, g, b),
            ])

    def tick(self, dt: float, w: int, h: int) -> None:
        if self.run_for > 0.0:
            self.run_for -= dt
            self._next -= dt
            if self._next <= 0.0:
                self._next = random.uniform(0.45, 1.0)
                self._launch(w, h)

        alive: list[list[float]] = []
        for rk in self.rockets:
            rk[2] *= 0.995
            rk[5] += dt
            rk[0] += rk[2] * dt
            rk[1] += rk[3] * dt
            rk[3] += 240.0 * dt
            if rk[1] <= rk[4] or rk[3] >= 0.0:
                self.burst(rk[0], rk[1])
            else:
                alive.append(rk)
        self.rockets = alive

        keep: list[list[float]] = []
        for sp in self.sparks:
            sp[4] -= dt
            if sp[4] <= 0.0:
                continue
            sp[2] *= 0.985
            sp[3] = sp[3] * 0.985 + 118.0 * dt
            sp[0] += sp[2] * dt
            sp[1] += sp[3] * dt
            keep.append(sp)
        self.sparks = keep

    def paint(self, p: QPainter) -> None:
        p.setPen(Qt.PenStyle.NoPen)
        for rk in self.rockets:
            p.setBrush(QColor(255, 240, 200, 220))
            p.drawEllipse(QPointF(rk[0], rk[1]), 2.4, 2.4)
            p.setBrush(QColor(255, 220, 150, 90))
            p.drawEllipse(QPointF(rk[0], rk[1] + 9.0), 1.7, 9.0)

        spark_pen = QPen(Qt.GlobalColor.white, 1.8)
        spark_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for sp in self.sparks:
            r, g, b = sp[5]
            life = min(1.0, sp[4] / 1.2)
            col = QColor(r, g, b, int(40 + 210 * life))
            spark_pen.setColor(col)
            p.setPen(spark_pen)
            p.drawLine(QPointF(sp[0], sp[1]),
                       QPointF(sp[0] - sp[2] * 0.035, sp[1] - sp[3] * 0.035))


class Santa:
    """Дед Мороз со Снегурочкой на санях, изредка пролетающие по небу."""

    def __init__(self) -> None:
        self.active = False
        self.t = 0.0
        self.dur = 17.0
        self.y = 200.0
        self.x0 = 0.0
        self.x1 = 0.0
        self.scale = 1.0
        self.dir = 1
        self.cool = random.uniform(90.0, 170.0)

    def start(self, w: int, h: int) -> None:
        self.active = True
        self.t = 0.0
        self.dur = random.uniform(13.0, 20.0)
        # Верхняя половина экрана, каждый раз новая высота.
        self.y = random.uniform(h * 0.10, h * 0.44)
        self.dir = random.choice((-1, 1))
        if self.dir > 0:
            self.x0, self.x1 = -380.0, float(w) + 400.0
        else:
            self.x0, self.x1 = float(w) + 380.0, -400.0
        self.scale = clamp(h / 1080.0, 0.78, 1.45)
        self.cool = random.uniform(95.0, 195.0)

    def tick(self, dt: float, w: int, h: int, auto: bool) -> None:
        if self.active:
            self.t += dt
            if self.t >= self.dur:
                self.active = False
        if not self.active and auto:
            self.cool -= dt
            if self.cool <= 0.0:
                self.start(w, h)

    def paint(self, p: QPainter, t: float) -> None:
        if not self.active:
            return
        u = self.t / self.dur
        x = lerp(self.x0, self.x1, u)
        y = self.y + math.sin(u * math.pi * 2.0) * 11.0
        s = self.scale
        d = float(self.dir)

        def fx(v: float) -> float:
            return x + v * s * d

        def fy(v: float) -> float:
            return y + v * s

        # звёздный след позади саней
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(9):
            a = 0.55 - i * 0.052
            p.setBrush(QColor(255, 240, 200, int(125 * a)))
            p.drawEllipse(QPointF(fx(-118.0 - i * 25.0),
                                  fy(18.0 + math.sin(t * 3.0 + i) * 4.0)),
                          2.3 * s, 2.3 * s)

        # тёплое свечение упряжки
        glow = QRadialGradient(QPointF(fx(70.0), fy(-22.0)), 175.0 * s)
        glow.setColorAt(0.0, QColor(255, 214, 150, 48))
        glow.setColorAt(1.0, QColor(255, 200, 120, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(glow)
        p.drawEllipse(QPointF(fx(70.0), fy(-22.0)), 175.0 * s, 175.0 * s)

        deer = QColor(72, 54, 44, 246)
        deer_dark = QColor(54, 39, 33, 246)
        harness = QColor(214, 196, 156, 210)

        # упряжь: сани → первый олень → второй олень
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(harness, 1.7 * s, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(fx(48.0), fy(5.0)), QPointF(fx(76.0), fy(-3.0)))
        p.drawLine(QPointF(fx(105.0), fy(-3.0)), QPointF(fx(137.0), fy(-3.0)))

        # ---- олени (впереди саней, по направлению движения) ----
        for k, center in enumerate((88.0, 148.0)):
            bob = math.sin(t * 6.2 + k * 1.7) * 2.2 * s
            by = fy(2.0) + bob
            cx = fx(center)

            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(deer)
            p.drawRoundedRect(QRectF(cx - 15.0 * s, by - 10.0 * s,
                                     31.0 * s, 19.0 * s),
                              8.0 * s, 8.0 * s)
            # шея и голова
            p.drawEllipse(QPointF(fx(center + 18.0), by - 13.0 * s),
                          7.0 * s, 6.6 * s)
            p.drawEllipse(QPointF(fx(center + 25.0), by - 10.0 * s),
                          4.4 * s, 3.4 * s)
            # ухо
            p.drawEllipse(QPointF(fx(center + 15.0), by - 19.0 * s),
                          2.6 * s, 3.4 * s)
            # хвост
            p.drawEllipse(QPointF(fx(center - 17.0), by - 7.0 * s),
                          3.2 * s, 4.0 * s)

            # рога
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(deer_dark, 1.7 * s, Qt.PenStyle.SolidLine,
                          Qt.PenCapStyle.RoundCap))
            p.drawLine(QPointF(fx(center + 17.0), by - 19.0 * s),
                       QPointF(fx(center + 13.0), by - 31.0 * s))
            p.drawLine(QPointF(fx(center + 15.0), by - 26.0 * s),
                       QPointF(fx(center + 22.0), by - 32.0 * s))
            p.drawLine(QPointF(fx(center + 19.0), by - 19.0 * s),
                       QPointF(fx(center + 24.0), by - 29.0 * s))

            # ноги в противофазе
            p.setPen(QPen(deer_dark, 2.9 * s, Qt.PenStyle.SolidLine,
                          Qt.PenCapStyle.RoundCap))
            swing = math.sin(t * 7.4 + k * 1.3) * 5.0 * s
            for li, lx in enumerate((-11.0, -2.0, 7.0, 14.0)):
                sgn = 1.0 if li in (1, 3) else -1.0
                p.drawLine(QPointF(fx(center + lx), by + 7.0 * s),
                           QPointF(fx(center + lx + sgn * swing * 0.7),
                                   by + 24.0 * s))

            # красный ошейник
            p.setPen(QPen(QColor(178, 36, 46, 235), 3.0 * s,
                          Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(QPointF(fx(center + 10.0), by - 11.0 * s),
                       QPointF(fx(center + 12.0), by + 3.0 * s))
            p.setPen(Qt.PenStyle.NoPen)

        # ---- сани ----
        # полозья
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(222, 230, 240, 240), 3.2 * s,
                      Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        runner = QPainterPath(QPointF(fx(-70.0), fy(19.0)))
        runner.lineTo(fx(30.0), fy(19.0))
        runner.quadTo(fx(51.0), fy(19.0), fx(51.0), fy(9.0))
        runner.quadTo(fx(51.0), fy(3.0), fx(40.0), fy(3.0))
        p.drawPath(runner)
        p.drawLine(QPointF(fx(-48.0), fy(19.0)),
                   QPointF(fx(-52.0), fy(31.0)))

        # корпус
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(160, 30, 42, 248))
        p.drawPolygon(QPolygonF([
            QPointF(fx(-70.0), fy(-26.0)),
            QPointF(fx(-55.0), fy(-29.0)),
            QPointF(fx(-46.0), fy(-6.0)),
            QPointF(fx(24.0), fy(-9.0)),
            QPointF(fx(43.0), fy(0.0)),
            QPointF(fx(36.0), fy(11.0)),
            QPointF(fx(-70.0), fy(13.0)),
        ]))
        # белая окантовка борта
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(246, 248, 252, 225), 2.1 * s,
                      Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(fx(-67.0), fy(-21.0)),
                   QPointF(fx(-49.0), fy(-4.0)))
        p.drawLine(QPointF(fx(-47.0), fy(-5.0)),
                   QPointF(fx(32.0), fy(-1.0)))

        # ---- мешок с подарками ----
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(122, 88, 60, 240))
        p.drawEllipse(QPointF(fx(-57.0), fy(-29.0)),
                      10.5 * s, 9.5 * s)
        p.setBrush(QColor(248, 238, 230, 235))
        p.drawEllipse(QPointF(fx(-56.0), fy(-38.0)), 4.2 * s, 3.6 * s)

        # ---- посох Деда Мороза (за фигурами) ----
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(116, 76, 44, 245), 2.8 * s,
                      Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(fx(-17.0), fy(-15.0)),
                   QPointF(fx(-25.0), fy(-83.0)))
        # снежинка на посохе
        p.setPen(QPen(QColor(222, 243, 255, 235), 1.4 * s,
                      Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        cx, cy = fx(-25.0), fy(-85.0)
        for ang in (0.0, math.pi / 3.0, math.pi * 2.0 / 3.0):
            p.drawLine(QPointF(cx - math.cos(ang) * 4.0 * s,
                               cy - math.sin(ang) * 4.0 * s),
                       QPointF(cx + math.cos(ang) * 4.0 * s,
                               cy + math.sin(ang) * 4.0 * s))
        p.setBrush(QColor(235, 249, 255, 245))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), 1.8 * s, 1.8 * s)

        # ---- Снегурочка: голубая шуба, кокошник и коса ----
        p.setPen(QPen(QColor(24, 68, 110, 245), 1.7 * s))
        p.setBrush(QColor(86, 176, 224, 252))
        p.drawEllipse(QPointF(fx(-36.0), fy(-37.0)),
                      10.5 * s, 15.5 * s)
        p.setPen(Qt.PenStyle.NoPen)
        # белая опушка по низу шубы
        p.setBrush(QColor(248, 251, 255, 245))
        p.drawRoundedRect(QRectF(fx(-47.0), fy(-24.0),
                                 21.0 * s, 4.0 * s), 2.0 * s, 2.0 * s)
        # белая полоса спереди
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(246, 251, 255, 240), 1.9 * s,
                      Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(fx(-27.5), fy(-49.0)),
                   QPointF(fx(-27.0), fy(-25.0)))
        p.setPen(Qt.PenStyle.NoPen)

        # коса
        p.setBrush(QColor(240, 210, 140, 250))
        for bx, by, br in ((-38.5, -54.0, 2.7), (-41.5, -47.0, 2.5),
                           (-43.5, -40.0, 2.3), (-45.5, -33.5, 2.0)):
            p.drawEllipse(QPointF(fx(bx), fy(by)), br * s, br * s)
        # синий бант на конце косы
        p.setBrush(QColor(58, 136, 200, 248))
        for side in (-1.0, 1.0):
            p.drawEllipse(QPointF(fx(-48.0 + side * 2.2), fy(-30.5)),
                          2.6 * s, 1.9 * s)

        # меховая опушка воротника
        p.setBrush(QColor(248, 251, 255, 248))
        p.drawEllipse(QPointF(fx(-33.0), fy(-51.0)), 7.6 * s, 3.4 * s)
        # лицо и волосы
        p.setBrush(QColor(248, 231, 178, 252))
        p.drawEllipse(QPointF(fx(-33.0), fy(-58.0)), 6.1 * s, 6.3 * s)
        p.setBrush(QColor(250, 224, 208, 252))
        p.drawEllipse(QPointF(fx(-31.5), fy(-56.0)), 4.8 * s, 5.0 * s)
        p.setBrush(QColor(48, 44, 56, 235))
        p.drawEllipse(QPointF(fx(-29.4), fy(-57.6)), 1.0 * s, 1.0 * s)
        p.setBrush(QColor(238, 158, 158, 170))
        p.drawEllipse(QPointF(fx(-28.6), fy(-54.2)), 1.2 * s, 0.8 * s)

        # кокошник
        p.setBrush(QColor(140, 208, 240, 252))
        p.setPen(QPen(QColor(24, 68, 110, 245), 1.5 * s))
        kok = QPainterPath(QPointF(fx(-38.0), fy(-60.0)))
        kok.quadTo(fx(-37.0), fy(-72.0), fx(-32.0), fy(-73.0))
        kok.quadTo(fx(-27.0), fy(-72.0), fx(-26.0), fy(-60.0))
        kok.closeSubpath()
        p.drawPath(kok)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(249, 252, 255, 248))
        p.drawRoundedRect(QRectF(fx(-38.5), fy(-62.0),
                                 13.0 * s, 3.2 * s), 1.6 * s, 1.6 * s)
        # жемчужинки на кокошнике
        p.setBrush(QColor(255, 255, 255, 235))
        for dx, dy in ((-35.0, -65.0), (-32.0, -69.0), (-29.0, -65.0)):
            p.drawEllipse(QPointF(fx(dx), fy(dy)), 1.0 * s, 1.0 * s)

        # рука Снегурочки
        p.setBrush(QColor(86, 176, 224, 252))
        p.drawEllipse(QPointF(fx(-26.0), fy(-41.0)), 4.8 * s, 4.3 * s)
        p.setBrush(QColor(249, 252, 255, 245))
        p.drawEllipse(QPointF(fx(-23.0), fy(-38.0)), 2.9 * s, 2.7 * s)

        # ---- Дед Мороз ----
        p.setPen(QPen(QColor(92, 20, 28, 150), 1.3 * s))
        p.setBrush(QColor(190, 36, 46, 252))
        coat = QPainterPath(QPointF(fx(-14.0), fy(-51.0)))
        coat.quadTo(fx(-19.0), fy(-30.0), fx(-16.0), fy(-17.0))
        coat.lineTo(fx(13.0), fy(-19.0))
        coat.quadTo(fx(17.0), fy(-36.0), fx(12.0), fy(-50.0))
        coat.closeSubpath()
        p.drawPath(coat)
        p.setPen(Qt.PenStyle.NoPen)
        # белая опушка по низу шубы
        p.setBrush(QColor(250, 247, 242, 245))
        p.drawRoundedRect(QRectF(fx(-16.5), fy(-21.5),
                                 30.0 * s, 4.6 * s), 2.3 * s, 2.3 * s)
        # белая полоса спереди
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(250, 247, 242, 240), 2.0 * s,
                      Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(fx(10.5), fy(-49.0)),
                   QPointF(fx(12.0), fy(-22.0)))
        p.setPen(Qt.PenStyle.NoPen)

        # пояс с пряжкой
        p.setPen(QPen(QColor(72, 46, 36, 235), 3.0 * s,
                      Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(fx(-13.0), fy(-29.0)),
                   QPointF(fx(8.0), fy(-29.0)))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(236, 196, 92, 245))
        p.drawRoundedRect(QRectF(fx(-4.0), fy(-31.5),
                                 7.0 * s, 5.0 * s), 1.5 * s, 1.5 * s)

        # борода и лицо
        p.setBrush(QColor(250, 242, 235, 252))
        p.drawEllipse(QPointF(fx(3.0), fy(-47.0)),
                      10.5 * s, 8.8 * s)
        p.setBrush(QColor(250, 222, 202, 252))
        p.drawEllipse(QPointF(fx(6.0), fy(-56.0)),
                      7.0 * s, 7.0 * s)
        p.setBrush(QColor(214, 64, 58, 250))
        p.drawEllipse(QPointF(fx(12.0), fy(-53.0)),
                      2.3 * s, 2.1 * s)
        p.setBrush(QColor(48, 40, 38, 235))
        p.drawEllipse(QPointF(fx(8.0), fy(-58.0)),
                      1.2 * s, 1.2 * s)
        # седая бровь
        p.setBrush(QColor(240, 238, 232, 230))
        p.drawEllipse(QPointF(fx(6.5), fy(-61.0)), 3.0 * s, 1.1 * s)

        # шапка: высокий боярский колпак с меховой опушкой
        p.setPen(QPen(QColor(92, 20, 28, 160), 1.2 * s))
        p.setBrush(QColor(200, 40, 50, 252))
        hat = QPainterPath(QPointF(fx(-4.0), fy(-64.0)))
        hat.lineTo(QPointF(fx(-3.0), fy(-78.0)))
        hat.quadTo(fx(4.0), fy(-84.0), fx(11.0), fy(-77.0))
        hat.lineTo(QPointF(fx(12.0), fy(-64.0)))
        hat.closeSubpath()
        p.drawPath(hat)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(252, 250, 246, 252))
        p.drawRoundedRect(QRectF(fx(-5.0), fy(-67.0),
                                 18.0 * s, 5.0 * s), 2.5 * s, 2.5 * s)
        # снежный кристалл на шапке
        p.setBrush(QColor(225, 242, 255, 240))
        p.drawEllipse(QPointF(fx(4.5), fy(-73.0)), 1.8 * s, 1.8 * s)

        # рука с посохом
        p.setBrush(QColor(250, 242, 235, 252))
        p.drawEllipse(QPointF(fx(-16.0), fy(-35.0)), 3.2 * s, 3.0 * s)

        # рука с поводьями
        p.setBrush(QColor(190, 36, 46, 252))
        p.drawEllipse(QPointF(fx(16.0), fy(-38.0)),
                      6.0 * s, 5.2 * s)
        p.setBrush(QColor(250, 242, 235, 252))
        p.drawEllipse(QPointF(fx(23.0), fy(-34.0)),
                      3.2 * s, 3.0 * s)

        # поводья к первому оленю
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(214, 196, 156, 220), 1.5 * s,
                      Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(fx(25.0), fy(-33.0)),
                   QPointF(fx(105.0), fy(-18.0)))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(Qt.BrushStyle.NoBrush)



# --------------------------------------------------------------------------
# Снегоуборщик
# --------------------------------------------------------------------------

class Plow:
    """Маленькая снегоуборочная машина проезжает по нижнему сугробу."""

    def __init__(self) -> None:
        self.active = False
        self.t = 0.0
        self.x = 0.0
        self.x1 = 0.0
        self.cool = random.uniform(260.0, 420.0)
        self.speed = 120.0

    def start(self, w: int) -> None:
        self.active = True
        self.t = 0.0
        self.x = -190.0
        self.x1 = float(w) + 190.0
        self.cool = random.uniform(300.0, 520.0)

    def tick(self, dt: float, overlay: "Overlay", auto: bool) -> None:
        if self.active:
            self.t += dt
            self.x += self.speed * dt
            y = overlay.bottom.surface(self.x)
            for d in overlay._drifts_cache:
                d.wipe(self.x - 40.0, y, 46.0, 1.0)
                d.wipe(self.x + 18.0, y, 30.0, 0.9)
            if self.x > self.x1:
                self.active = False
        elif auto:
            self.cool -= dt
            if self.cool <= 0.0:
                self.start(int(overlay.lw))

    def paint(self, p: QPainter, overlay: "Overlay", t: float) -> None:
        if not self.active:
            return
        x = self.x
        y = overlay.bottom.surface(x) + 2.0

        # отвал впереди
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(196, 214, 232, 245))
        p.drawPolygon(QPolygonF([
            QPointF(x + 52.0, y - 6.0),
            QPointF(x + 30.0, y - 40.0),
            QPointF(x + 44.0, y - 42.0),
            QPointF(x + 70.0, y - 4.0),
        ]))
        p.setBrush(QColor(150, 172, 196, 245))
        p.drawPolygon(QPolygonF([
            QPointF(x + 52.0, y - 6.0),
            QPointF(x + 30.0, y - 40.0),
            QPointF(x + 36.0, y - 41.0),
            QPointF(x + 58.0, y - 6.0),
        ]))

        # кузов
        p.setBrush(QColor(240, 168, 42, 250))
        p.drawRoundedRect(QRectF(x - 46.0, y - 34.0, 84.0, 26.0), 5.0, 5.0)
        p.setBrush(QColor(216, 138, 28, 250))
        p.drawRoundedRect(QRectF(x - 46.0, y - 16.0, 84.0, 8.0), 3.0, 3.0)
        # кабина
        p.setBrush(QColor(250, 196, 70, 250))
        p.drawRoundedRect(QRectF(x - 30.0, y - 58.0, 42.0, 26.0), 6.0, 6.0)
        p.setBrush(QColor(40, 66, 92, 235))
        p.drawRoundedRect(QRectF(x - 24.0, y - 53.0, 30.0, 14.0), 3.0, 3.0)
        # снег на крыше и кузове
        p.setBrush(QColor(248, 252, 255, 250))
        p.drawRoundedRect(QRectF(x - 31.0, y - 61.0, 44.0, 6.0), 3.0, 3.0)
        p.drawRoundedRect(QRectF(x - 45.0, y - 37.0, 82.0, 5.0), 2.5, 2.5)
        # маячок
        flash = 0.45 + 0.55 * abs(math.sin(t * 6.0))
        p.setBrush(QColor(255, 150, 40, int(255 * flash)))
        p.drawEllipse(QPointF(x - 9.0, y - 63.0), 3.4, 3.0)
        p.setBrush(QColor(255, 190, 90, int(120 * flash)))
        p.drawEllipse(QPointF(x - 9.0, y - 63.0), 8.0, 7.0)

        # колёса
        for wx, wr in ((x - 30.0, 11.0), (x + 20.0, 11.0)):
            p.setBrush(QColor(34, 38, 44, 250))
            p.drawEllipse(QPointF(wx, y - 7.0), wr, wr)
            p.setBrush(QColor(120, 132, 146, 250))
            p.drawEllipse(QPointF(wx, y - 7.0), wr * 0.45, wr * 0.45)
            p.setPen(QPen(QColor(176, 190, 204, 220), 1.6))
            a = self.t * 9.0
            p.drawLine(QPointF(wx - math.cos(a) * wr * 0.8, y - 7.0),
                       QPointF(wx + math.cos(a) * wr * 0.8, y - 7.0))
            p.setPen(Qt.PenStyle.NoPen)

        # снежная струя из-под отвала
        p.setBrush(QColor(238, 248, 255, 190))
        for i in range(5):
            px = x + 58.0 + i * 7.0
            py = y - 8.0 - math.sin(t * 9.0 + i) * 6.0 - i * 2.0
            p.drawEllipse(QPointF(px, py), 3.4 - i * 0.4, 3.0 - i * 0.3)


# --------------------------------------------------------------------------
# Открытка и обои
# --------------------------------------------------------------------------

SPI_SETDESKWALLPAPER = 20


def set_system_wallpaper(path: str) -> bool:
    try:
        return bool(user32.SystemParametersInfoW(SPI_SETDESKWALLPAPER, 0,
                                                 str(path), 3))
    except Exception:
        return False


def current_wallpaper() -> str:
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop")
        val, _ = winreg.QueryValueEx(key, "Wallpaper")
        winreg.CloseKey(key)
        return str(val)
    except Exception:
        return ""


def pictures_dir() -> Path:
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders")
        val, _ = winreg.QueryValueEx(key, "My Pictures")
        winreg.CloseKey(key)
        return Path(os.path.expandvars(str(val)))
    except Exception:
        return Path.home() / "Pictures"


def _mix(a: QColor, b: QColor, t: float) -> QColor:
    """Плавно смешать два цвета (включая прозрачность)."""
    t = clamp(t, 0.0, 1.0)
    return QColor(
        int(round(a.red() + (b.red() - a.red()) * t)),
        int(round(a.green() + (b.green() - a.green()) * t)),
        int(round(a.blue() + (b.blue() - a.blue()) * t)),
        int(round(a.alpha() + (b.alpha() - a.alpha()) * t)),
    )


def _smooth01(t: float) -> float:
    t = clamp(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


# Палитра суток: час, небо сверху вниз (5 цветов), свет на снегу,
# яркость звёзд, высота сугробов. Между строками всё плавно смешивается.
WALL_PALETTE = (
    (0.0,  "#04061a", "#09102e", "#131e49", "#1e2a59", "#2d346d",
     "#29305f", 1.00, 1.00),
    (3.5,  "#05071c", "#0b1234", "#17214f", "#232c61", "#353b76",
     "#2c346a", 0.98, 1.00),
    (5.6,  "#0d1034", "#262157", "#4b316f", "#8a4874", "#d06d7e",
     "#6f3d6b", 0.40, 0.97),
    (6.9,  "#2b245c", "#6d3b78", "#c45c7b", "#f28d6b", "#ffc681",
     "#dc7f66", 0.00, 0.93),
    (8.3,  "#4c7bab", "#8faecc", "#e9bb8e", "#ffd49c", "#ffebbd",
     "#eab77a", 0.00, 0.87),
    (11.2, "#1f5fa2", "#4389c7", "#7fb9e2", "#bcdff4", "#e6f4fd",
     "#9fc9e8", 0.00, 0.77),
    (14.4, "#2d6eac", "#5e9dd2", "#97c9ea", "#d2eaf8", "#f6ecd7",
     "#b4d4ea", 0.00, 0.73),
    (16.6, "#3d4080", "#804f86", "#d16482", "#fa9c65", "#ffd28c",
     "#df876b", 0.04, 0.82),
    (18.3, "#191b4c", "#3b2868", "#6f3b75", "#a54d6f", "#d47572",
     "#70406a", 0.55, 0.90),
    (20.2, "#05081e", "#0a1130", "#14204c", "#202b5c", "#31376e",
     "#2b3366", 0.96, 0.98),
    (24.0, "#04061a", "#09102e", "#131e49", "#1e2a59", "#2d346d",
     "#29305f", 1.00, 1.00),
)


def _wall_state(when: datetime.datetime):
    """Цвета неба, яркость звёзд и высота сугробов для текущего часа."""
    hour = when.hour + when.minute / 60.0 + when.second / 3600.0
    for i in range(len(WALL_PALETTE) - 1):
        a = WALL_PALETTE[i]
        b = WALL_PALETTE[i + 1]
        if a[0] <= hour <= b[0]:
            span = b[0] - a[0]
            u = _smooth01((hour - a[0]) / span) if span > 0.0 else 0.0
            colors = [_mix(QColor(a[k]), QColor(b[k]), u)
                      for k in range(1, 6)]
            light = _mix(QColor(a[6]), QColor(b[6]), u)
            stars = lerp(a[7], b[7], u)
            snow = lerp(a[8], b[8], u)
            return colors, light, stars, snow, hour
    row = WALL_PALETTE[0]
    return ([QColor(row[k]) for k in range(1, 6)], QColor(row[6]),
            1.0, 1.0, hour)


def _phase_name(hour: float) -> str:
    if 5.0 <= hour < 9.0:
        return "утро"
    if 9.0 <= hour < 16.5:
        return "день"
    if 16.5 <= hour < 20.0:
        return "вечер"
    return "ночь"


def draw_hill(p: QPainter, w: int, base_y: float, amp: float, phase: float,
              color_top: QColor, color_bottom: QColor,
              rim: QColor | None = None) -> None:
    pts: list[tuple[float, float]] = []
    steps = 32
    for i in range(steps + 1):
        x = w * i / steps
        y = (base_y
             - amp * math.sin(x / w * math.pi * 2.2 + phase)
             - amp * 0.45 * math.sin(x / w * math.pi * 5.1 + phase * 1.7))
        pts.append((x, y))
    path = QPainterPath(QPointF(pts[0][0], pts[0][1]))
    for x, y in pts[1:]:
        path.lineTo(x, y)
    path.lineTo(float(w), float(base_y + 400))
    path.lineTo(0.0, float(base_y + 400))
    path.closeSubpath()
    grad = QLinearGradient(0.0, base_y - amp * 1.6, 0.0, base_y + 160.0)
    grad.setColorAt(0.0, color_top)
    grad.setColorAt(1.0, color_bottom)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(grad)
    p.drawPath(path)
    if rim is not None:
        rim_path = QPainterPath(QPointF(pts[0][0], pts[0][1]))
        for x, y in pts[1:]:
            rim_path.lineTo(x, y)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(rim, max(1.0, w / 1200.0),
                      Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawPath(rim_path)


def make_wallpaper(w: int, h: int,
                   when: datetime.datetime | None = None,
                   caption: bool = True) -> QImage:
    """Зимний пейзаж, который живёт по часам: утро, день, вечер, ночь."""
    if when is None:
        when = datetime.datetime.now()
    img = QImage(int(w), int(h), QImage.Format.Format_ARGB32_Premultiplied)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    sky_colors, light, stars, snow, hour = _wall_state(when)
    top, high, mid, low, horizon = sky_colors
    hh = float(h)
    horizon_y = hh * 0.70
    moon_size = min(w, h)
    sc = h / 720.0

    sky = QLinearGradient(0.0, 0.0, 0.0, horizon_y)
    sky.setColorAt(0.0, top)
    sky.setColorAt(0.28, high)
    sky.setColorAt(0.56, mid)
    sky.setColorAt(0.80, low)
    sky.setColorAt(1.0, horizon)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(sky)
    p.drawRect(QRectF(0.0, 0.0, float(w), float(h)))

    # ---- солнце: встаёт слева, садится справа ----
    sun = None
    sun_u = (hour - 7.15) / (16.85 - 7.15)
    if 0.0 <= sun_u <= 1.0:
        elev = math.sin(math.pi * sun_u)
        alpha = clamp(elev * 3.2, 0.0, 1.0)
        sun = (w * (0.09 + 0.82 * sun_u),
               hh * (0.69 - 0.52 * elev), elev, alpha)

    # ---- луна: восходит вечером справа, к утру уходит влево ----
    moon = None
    moonrise, moonset = 16.9, 7.05
    if hour >= moonrise:
        moon_u = (hour - moonrise) / (24.0 - moonrise + moonset)
    elif hour <= moonset:
        moon_u = (hour + 24.0 - moonrise) / (24.0 - moonrise + moonset)
    else:
        moon_u = -1.0
    if 0.0 <= moon_u <= 1.0:
        elev = math.sin(math.pi * moon_u)
        alpha = clamp(elev * 3.0, 0.0, 1.0)
        moon = (w * (0.90 - 0.80 * moon_u),
                hh * (0.68 - 0.54 * elev), elev, alpha)

    # тёплое зарево вокруг солнца
    if sun is not None and sun[3] > 0.02:
        sx, sy, _elev, sa = sun
        halo = QRadialGradient(QPointF(sx, sy), moon_size * 0.48)
        halo.setColorAt(0.0, QColor(255, 196, 128, int(100 * sa)))
        halo.setColorAt(0.45, QColor(255, 150, 96, int(38 * sa)))
        halo.setColorAt(1.0, QColor(255, 120, 80, 0))
        p.setBrush(halo)
        p.drawEllipse(QPointF(sx, sy), moon_size * 0.48, moon_size * 0.48)

    rnd = random.Random(2027)
    # звёзды
    p.setPen(Qt.PenStyle.NoPen)
    for _ in range(230):
        sx = rnd.uniform(0.0, w)
        sy = rnd.uniform(0.0, horizon_y * 0.94)
        a = int(rnd.randint(45, 215) * stars)
        r = rnd.uniform(0.6, 1.9)
        if a > 3:
            p.setBrush(QColor(236, 246, 255, a))
            p.drawEllipse(QPointF(sx, sy), r, r)
    for _ in range(7):
        sx = rnd.uniform(w * 0.05, w * 0.95)
        sy = rnd.uniform(h * 0.03, h * 0.42)
        a = int(220 * stars)
        if a > 4:
            p.setBrush(QColor(255, 255, 255, a))
            p.drawEllipse(QPointF(sx, sy), 2.0, 2.0)
            p.setBrush(QColor(205, 228, 255, int(70 * stars)))
            p.drawEllipse(QPointF(sx, sy), 6.0, 6.0)

    # солнце
    if sun is not None and sun[3] > 0.02:
        sx, sy, elev, sa = sun
        base_r = moon_size * (0.050 + 0.012 * (1.0 - elev))
        warm = clamp(1.0 - elev, 0.0, 1.0)
        core = _mix(QColor(255, 248, 214), QColor(255, 146, 66), warm)
        halo = QRadialGradient(QPointF(sx, sy), base_r * 4.0)
        halo.setColorAt(0.0, QColor(core.red(), core.green(), core.blue(),
                                    int(120 * sa)))
        halo.setColorAt(0.35, QColor(255, 176, 110, int(42 * sa)))
        halo.setColorAt(1.0, QColor(255, 132, 88, 0))
        p.setBrush(halo)
        p.drawEllipse(QPointF(sx, sy), base_r * 4.0, base_r * 4.0)
        p.setBrush(core)
        p.drawEllipse(QPointF(sx, sy), base_r, base_r)
        p.setBrush(QColor(255, 255, 240, int(180 * sa)))
        p.drawEllipse(QPointF(sx - base_r * 0.22, sy - base_r * 0.22),
                      base_r * 0.45, base_r * 0.34)

    # луна
    if moon is not None and moon[3] > 0.02:
        mx, my, _elev, ma = moon
        mr = moon_size * 0.034
        glow = QRadialGradient(QPointF(mx, my), mr * 5.0)
        glow.setColorAt(0.0, QColor(196, 220, 255, int(90 * ma)))
        glow.setColorAt(0.45, QColor(150, 186, 235, int(28 * ma)))
        glow.setColorAt(1.0, QColor(120, 160, 220, 0))
        p.setBrush(glow)
        p.drawEllipse(QPointF(mx, my), mr * 5.0, mr * 5.0)
        p.setBrush(QColor(248, 249, 255, int(255 * ma)))
        p.drawEllipse(QPointF(mx, my), mr, mr)
        p.setBrush(QColor(218, 224, 238, int(85 * ma)))
        for dx, dy, rr in ((-0.30, -0.22, 0.26), (0.25, 0.14, 0.18),
                           (0.06, -0.44, 0.12), (-0.12, 0.36, 0.10)):
            p.drawEllipse(QPointF(mx + mr * dx, my + mr * dy),
                          mr * rr, mr * rr)

    # ---- дальние сопки ----
    hill_amp = 32.0 * sc
    draw_hill(p, w, h * 0.675, hill_amp, 0.7,
              _mix(QColor("#5b7d9b"), light, 0.46),
              _mix(QColor("#3a5875"), light, 0.55),
              _mix(QColor("#a8c2da"), light, 0.35))

    # ---- лес на дальнем плане ----
    forest = _mix(QColor("#1c3044"), light, 0.28)
    cap = _mix(QColor("#eef6ff"), light, 0.10)
    p.setPen(Qt.PenStyle.NoPen)
    for _ in range(28):
        tx = rnd.uniform(0.0, w)
        ty = (h * 0.675
              - hill_amp * math.sin(tx / w * math.pi * 2.2 + 0.7)
              - hill_amp * 0.45 * math.sin(
                  tx / w * math.pi * 5.1 + 0.7 * 1.7)
              + 5.0 * sc)
        th = rnd.uniform(26.0, 64.0) * sc
        tw = th * 0.38
        p.setBrush(forest)
        p.drawPolygon(QPolygonF([
            QPointF(tx, ty - th),
            QPointF(tx + tw, ty),
            QPointF(tx - tw, ty),
        ]))
        p.setBrush(QColor(cap.red(), cap.green(), cap.blue(), 205))
        p.drawPolygon(QPolygonF([
            QPointF(tx, ty - th),
            QPointF(tx + tw * 0.52, ty - th * 0.40),
            QPointF(tx - tw * 0.52, ty - th * 0.40),
        ]))

    # ---- сугробы: ночью наметает, днём чуть подтаивает ----
    lift = max(0.0, snow - 0.68) * hh * 0.20
    snow_far = _mix(QColor("#b7cce4"), light, 0.42)
    snow_mid = _mix(QColor("#dbe9f8"), light, 0.27)
    snow_near = _mix(QColor("#f8fbff"), light, 0.12)
    draw_hill(p, w, h * 0.792 - lift * 0.35,
              (24.0 + 12.0 * snow) * sc, 2.1,
              snow_far, _mix(snow_far, QColor("#7e9cbb"), 0.35),
              QColor(238, 247, 255, 170))
    draw_hill(p, w, h * 0.872 - lift * 0.68,
              (28.0 + 16.0 * snow) * sc, 4.3,
              snow_mid, _mix(snow_mid, QColor("#8aa8c6"), 0.30),
              QColor(250, 253, 255, 200))
    draw_hill(p, w, h * 0.958 - lift,
              (16.0 + 28.0 * snow) * sc, 1.4,
              snow_near, _mix(snow_near, QColor("#a9c2dc"), 0.24),
              QColor(255, 255, 255, 220))

    # снежинки
    p.setPen(Qt.PenStyle.NoPen)
    for _ in range(250):
        sx = rnd.uniform(0.0, w)
        sy = rnd.uniform(0.0, h * 0.985)
        r = rnd.uniform(0.8, 3.0) * sc
        a = int(rnd.randint(75, 215) * (0.60 + 0.40 * stars))
        p.setBrush(QColor(255, 255, 255, a))
        p.drawEllipse(QPointF(sx, sy), r, r)

    # поздравление
    font = QFont("Segoe Script")
    font.setPixelSize(int(h * 0.062))
    p.setFont(font)
    text = "С Новым годом!"
    rect = QRectF(0.0, h * 0.29, float(w), h * 0.16)
    p.setPen(QColor(6, 12, 24, 150))
    for dx, dy in ((-2.0, 2.0), (2.0, 2.0), (0.0, 3.0), (2.0, -1.0)):
        p.drawText(rect.translated(dx, dy),
                   Qt.AlignmentFlag.AlignCenter, text)
    p.setPen(QColor(255, 251, 242))
    p.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)

    font2 = QFont("Segoe UI")
    font2.setPixelSize(int(h * 0.017))
    p.setFont(font2)
    if caption:
        sub = ("FlakeLite · %s · снег на рабочем столе" % _phase_name(hour))
        sub_rect = QRectF(0.0, h * 0.452, float(w), h * 0.05)
        p.setPen(QColor(8, 18, 32, 135))
        p.drawText(sub_rect.translated(1.5, 1.5),
                   Qt.AlignmentFlag.AlignCenter, sub)
        p.setPen(QColor(238, 246, 255, 205))
        p.drawText(sub_rect, Qt.AlignmentFlag.AlignCenter, sub)

    p.end()
    return img


# --------------------------------------------------------------------------
# Оверлей
# --------------------------------------------------------------------------

class Overlay(QWidget):
    def __init__(self, core: "Core") -> None:
        super().__init__(None)
        self.core = core
        self.cfg = core.cfg

        self.dpr = 1.0
        self.px = self.py = 0
        self.pw = self.ph = 1
        self.lw = self.lh = 1          # логические размеры окна

        self._t = 0.0
        self._last = time.perf_counter()
        self._frames = 0
        self._fps_t0 = self._last
        self.fps = 0.0
        self.frame_ms = 0.0
        self.flake_ms = 0.0
        self.drift_ms = 0.0
        self._fps_hist: list[float] = []
        self._frame_budget_ms = 1000.0 / max(10, int(self.cfg["quality"]))

        self.snow = SnowSystem(1, 1)
        self._last_weather = (None, None)
        self.bottom = Drift(0, 1, 1, cell=5.0, cap=30.0, kind="bottom")
        self.windows = WindowTracker(self)
        self._drifts_cache = [self.bottom]
        self.snow.landing = self._landing
        self._settle_acc = 0.0
        self.debug_windows = False

        # --- игра со снегом (инструменты включаются сами, по наведению) ---
        self.placed: list[Ball] = []
        self.snowmen: list[Snowman] = []
        self._dragging = False
        self._drag_ball: Ball | None = None
        self._drag_total = 0.0
        self._press_active = False
        self._press_pos = QPointF(-5000.0, -5000.0)
        self._right_drag = False
        self._interact_hold = 0.0
        self._last_cur: QPointF | None = None
        self._hover = QPointF(-5000.0, -5000.0)
        self._mouse_hint = 0.0
        self._work_bottom = 0.0
        self.setMouseTracking(True)

        # --- украшения ---
        self.tree = Tree()
        self.tree.h = 280
        self.fireworks = Fireworks()
        self.santa = Santa()
        self.plow = Plow()
        self.hotkey_vk = 0
        self._countdown_text = ""
        self._countdown_t = 0.0
        self._clock = datetime.datetime.now()
        # Готовые кисти по глубине: не создаём QColor на каждую снежинку каждый кадр
        self._flake_colors = [
            QColor(214, 230, 252, int(lerp(130, 200, i / 7.0))) for i in range(8)
        ]

        self._setup_window()
        self._apply_geometry()
        self._apply_weather()

        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self._tick)

        self.show()
        self._apply_native_styles()
        self.hotkey_ok = self._register_hotkey()
        self.start()

    # -- окно -----------------------------------------------------------
    def _setup_window(self) -> None:
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.NoDropShadowWindowHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def _apply_geometry(self) -> None:
        phys = virtual_screen()
        self.px, self.py = phys.x(), phys.y()
        self.pw, self.ph = max(1, phys.width()), max(1, phys.height())
        scr = QGuiApplication.primaryScreen()
        self.dpr = scr.devicePixelRatio() if scr else 1.0
        if self.dpr <= 0:
            self.dpr = 1.0
        self.setGeometry(QRect(round(self.px / self.dpr), round(self.py / self.dpr),
                               max(1, round(self.pw / self.dpr)),
                               max(1, round(self.ph / self.dpr))))
        self.lw = max(1.0, self.pw / self.dpr)
        self.lh = max(1.0, self.ph / self.dpr)
        # Панель задач не должна попадать в «снежную» зону внизу экрана.
        try:
            wa = work_area()
            self._work_bottom = clamp((wa.bottom() - self.py) / self.dpr,
                                      0.0, self.lh)
        except Exception:
            self._work_bottom = self.lh
        self.snow.resize(int(self.lw), int(self.lh))
        self.bottom.move_to(0, self.lh)
        self.bottom.resize_width(self.lw)
        if hasattr(self, "tree"):
            self.tree.h = int(clamp(self.lh * 0.29, 210, 380))

    def on_windows_changed(self) -> None:
        self._drifts_cache = [self.bottom] + list(self.windows.drifts.values())

    def _landing(self, x: float, y0: float, y1: float,
                 allow_empty: bool = True) -> Drift | None:
        """На какую кромку села снежинка: верх окна или низ экрана."""
        best = None
        best_surf = 1e18
        for d in self._drifts_cache:
            if (not allow_empty and d.kind == "window"
                    and d.is_empty()):
                continue
            if d.x <= x <= d.x + d.w:
                s = d.surface(x)
                if y0 <= s <= y1 and s < best_surf:
                    best = d
                    best_surf = s
        return best

    def _apply_native_styles(self) -> None:
        hwnd = int(self.winId())
        self.hwnd = hwnd
        ex = _get_long(hwnd, GWL_EXSTYLE)
        ex |= WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
        if not self.core.interactive:
            ex |= WS_EX_TRANSPARENT
        _set_long(hwnd, GWL_EXSTYLE, ex)

    def _register_hotkey(self) -> bool:
        try:
            user32.RegisterHotKey.argtypes = [
                wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
            user32.RegisterHotKey.restype = wintypes.BOOL
            self.hotkey_vk = 0
            hwnd = int(self.winId())
            for vk in (0x7B, 0x7A, 0x79, 0x78):      # F12, F11, F10, F9
                ctypes.set_last_error(0)
                if user32.RegisterHotKey(hwnd, 0x4B1, 0x4000, vk):
                    self.hotkey_vk = vk
                    return True
            return False
        except Exception:
            return False

    def nativeEvent(self, event_type, message):  # noqa: N802
        try:
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == 0x0312 and int(msg.wParam) == 0x4B1:
                self.core.take_postcard()
                return True, 0
        except Exception:
            pass
        return super().nativeEvent(event_type, message)

    # -- открытка ---------------------------------------------------------
    def make_postcard(self) -> Path | None:
        scr = QGuiApplication.primaryScreen()
        if scr is None:
            return None
        shot = scr.grabWindow(0)
        if shot.isNull():
            return None
        img = shot.toImage().convertToFormat(
            QImage.Format.Format_ARGB32_Premultiplied)
        w, h = img.width(), img.height()
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # виньетка
        vig = QRadialGradient(QPointF(w * 0.5, h * 0.45), max(w, h) * 0.78)
        vig.setColorAt(0.5, QColor(0, 0, 0, 0))
        vig.setColorAt(1.0, QColor(6, 14, 26, 105))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(vig)
        p.drawRect(QRectF(0.0, 0.0, float(w), float(h)))

        # рамка с инеем
        m = max(12.0, h * 0.017)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(236, 246, 255, 235), m * 0.62))
        p.drawRoundedRect(QRectF(m, m, w - 2 * m, h - 2 * m), m * 1.3, m * 1.3)
        p.setPen(QPen(QColor(255, 226, 158, 170), max(1.0, m * 0.09)))
        p.drawRoundedRect(QRectF(m * 2.1, m * 2.1, w - 4.2 * m, h - 4.2 * m),
                          m * 0.9, m * 0.9)

        # поздравление
        font = QFont("Segoe Script")
        font.setPixelSize(int(h * 0.048))
        p.setFont(font)
        box = QRectF(m * 2.6, h - m * 2.6 - h * 0.11,
                     w - m * 5.2, h * 0.085)
        p.setPen(QColor(6, 16, 30, 150))
        p.drawText(box.translated(3.0, 3.0),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                   "С Новым годом!")
        p.setPen(QColor(255, 250, 240))
        p.drawText(box,
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                   "С Новым годом!")

        font2 = QFont("Segoe UI")
        font2.setPixelSize(max(11, int(h * 0.0155)))
        p.setFont(font2)
        p.setPen(QColor(240, 246, 252, 190))
        p.drawText(QRectF(m * 2.6, h - m * 2.6 - h * 0.022,
                          w - m * 5.2, h * 0.03),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                   "FlakeLite · " + datetime.datetime.now().strftime("%d.%m.%Y"))
        p.end()

        folder = pictures_dir() / "FlakeLite"
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except Exception:
            return None
        name = "otkrytka_%s.png" % datetime.datetime.now().strftime(
            "%Y-%m-%d_%H-%M-%S")
        path = folder / name
        if not img.save(str(path), "PNG"):
            return None
        return path

    def set_click_through(self, through: bool) -> None:
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, through)
        self._cursor_shape = None
        self.setCursor(Qt.CursorShape.ArrowCursor)
        hwnd = int(self.winId())
        ex = _get_long(hwnd, GWL_EXSTYLE)
        if through:
            ex |= WS_EX_TRANSPARENT
        else:
            ex &= ~WS_EX_TRANSPARENT
        _set_long(hwnd, GWL_EXSTYLE, ex)

    # -- цикл -----------------------------------------------------------
    def start(self) -> None:
        self._last = time.perf_counter()
        self.timer.start(int(1000 / max(10, int(self.cfg["quality"]))))

    def stop(self) -> None:
        self.timer.stop()

    def apply_config(self) -> None:
        self._frame_budget_ms = 1000.0 / max(10, int(self.cfg["quality"]))
        self.start()
        self.update()

    def _apply_weather(self) -> None:
        self.snow.set_weather(self.cfg["weather"], float(self.cfg["density"]))
        self.snow.set_wind(float(self.cfg["wind"]))
        self._last_weather = (self.cfg["weather"], self.cfg["density"])

    def _tick(self) -> None:
        try:
            self._tick_body()
        except Exception:
            # Один плохой кадр не должен убивать весь снег
            import traceback
            traceback.print_exc()
            self.core._errors = getattr(self.core, "_errors", 0) + 1

    def _tick_body(self) -> None:
        now = time.perf_counter()
        dt = now - self._last
        self._last = now

        try:
            self.windows.follow(self.snow, dt)
            self.windows.tick(dt)
        except Exception:
            # Проблема с одним окном не должна останавливать снегопад.
            pass
        self._settle_acc += dt
        if self._settle_acc >= 0.06:
            self._settle_acc = 0.0
            self.bottom.settle()

        self.snow.update(dt)
        self._update_figures(dt)
        cur = self._auto_hover(dt)
        self._track_cursor(cur)

        # украшения и время
        self.fireworks.tick(dt, int(self.lw), int(self.lh))
        self.santa.tick(dt, int(self.lw), int(self.lh),
                        bool(self.cfg.get("auto_santa", True)))
        self.plow.tick(dt, self, bool(self.cfg.get("auto_plow", True)))
        self._countdown_t -= dt
        if self._countdown_t <= 0.0:
            self._countdown_t = 0.5
            self._clock = datetime.datetime.now()
            self._update_countdown()
            self._auto_fireworks()

        self.update()

        # счётчик кадров
        self._frames += 1
        span = now - self._fps_t0
        if span >= 0.5:
            self.fps = self._frames / span
            self._frames = 0
            self._fps_t0 = now
            self.core.report_fps(self.fps)
            self._adapt_quality()

    # -- курсор и игра ---------------------------------------------------
    def _to_model(self, posf: QPointF) -> QPointF:
        return QPointF(posf.x(), posf.y())

    def _cursor_model(self) -> QPointF:
        g = QCursor.pos()
        return QPointF((g.x() - self.px) / self.dpr,
                       (g.y() - self.py) / self.dpr)

    def _cursor_over_own_ui(self) -> bool:
        """Курсор над панелью/меню/треем — им нельзя мешать."""
        hwnd = window_from_point(cursor_physical())
        if not hwnd:
            return False
        if hwnd == int(getattr(self, "hwnd", 0) or 0):
            return False
        return window_pid(hwnd) == os.getpid()

    def _snow_hit(self, pos: QPointF, expand: bool = False) -> Drift | None:
        """Сугроб под курсором. Ниже кромки окна не лезем: там заголовок."""
        x, y = pos.x(), pos.y()
        best = None
        best_d = 1e18
        for d in self._drifts_cache:
            if max(d.h) < 0.45 or not d.contains(x):
                continue
            surf = d.surface(x)
            if d.y - surf < 0.35:
                continue
            top = surf - (19.0 if expand else 8.0)
            bot = d.y - 2.0
            if d.kind == "bottom":
                bot = min(bot, self._work_bottom - 2.0)
            if bot <= top or not (top <= y <= bot):
                continue
            dist = abs(y - surf)
            if dist < best_d:
                best = d
                best_d = dist
        return best

    def _figure_hit(self, pos: QPointF,
                    expand: bool = True) -> tuple[Ball, Snowman | None] | None:
        margin = 9.0 if expand else 4.0
        best: tuple[Ball, Snowman | None] | None = None
        best_d = 1e18
        for sm in reversed(self.snowmen):
            for b in sm.balls:
                d = math.hypot(pos.x() - b.x, pos.y() - b.y)
                if d <= b.r + margin and d < best_d:
                    best = (b, sm)
                    best_d = d
        for b in self.placed:
            d = math.hypot(pos.x() - b.x, pos.y() - b.y)
            if d <= b.r + margin and d < best_d:
                best = (b, None)
                best_d = d
        return best

    def _auto_hover(self, dt: float) -> QPointF:
        """Снег сам «просыпается» под курсором — без кнопки «Играть»."""
        cur = self._cursor_model()
        self._hover = cur
        if self._press_active or self._drag_ball is not None or self._right_drag:
            self._interact_hold = 0.22
        else:
            hot = (self._figure_hit(cur, self.core.interactive) is not None
                   or self._snow_hit(cur, self.core.interactive) is not None)
            if hot:
                self._interact_hold = 0.22
            else:
                self._interact_hold = max(0.0, self._interact_hold - dt)

        want = self._interact_hold > 0.0 or self._press_active \
            or self._right_drag or self._drag_ball is not None
        own = False
        if want and not self._press_active:
            own = self._cursor_over_own_ui()
            if own:
                want = False
        if want != bool(self.core.interactive):
            if self.core.verbose:
                hwnd = window_from_point(cursor_physical())
                print("hover: want=%s cur=(%.0f,%.0f) own=%s hwnd=%d cls=%s" % (
                    want, cur.x(), cur.y(), own, hwnd,
                    window_class(hwnd)[:24]), flush=True)
            self.core.set_auto_interactive(want)
        self._update_cursor(cur)
        return cur

    def _update_cursor(self, cur: QPointF) -> None:
        if not self.core.interactive:
            return
        if self._drag_ball is not None:
            shape = Qt.CursorShape.ClosedHandCursor
        elif self._figure_hit(cur, True) is not None:
            shape = Qt.CursorShape.PointingHandCursor
        elif self._snow_hit(cur, True) is not None:
            shape = Qt.CursorShape.OpenHandCursor
        else:
            shape = Qt.CursorShape.ArrowCursor
        if getattr(self, "_cursor_shape", None) != shape:
            self._cursor_shape = shape
            self.setCursor(shape)

    def _track_cursor(self, cur: QPointF | None = None) -> None:
        if cur is None:
            cur = self._cursor_model()
        prev = self._last_cur
        self._last_cur = cur
        if self.core.interactive or prev is None:
            return
        dx = cur.x() - prev.x()
        dy = cur.y() - prev.y()
        speed = math.hypot(dx, dy)
        if speed < 5.0:
            return
        self._sweep(prev, cur, 8.0, min(1.0, speed / 45.0))

    def _sweep(self, p0: QPointF, p1: QPointF, radius: float,
               strength: float) -> None:
        dx = p1.x() - p0.x()
        dy = p1.y() - p0.y()
        dist = math.hypot(dx, dy)
        steps = max(1, int(dist / 8.0))
        for k in range(1, steps + 1):
            x = p0.x() + dx * k / steps
            y = p0.y() + dy * k / steps
            for d in self._drifts_cache:
                d.wipe(x, y, radius, strength * 0.85)
        # снежинки разлетаются в сторону движения
        self.snow.stir(p1.x(), p1.y(), max(26.0, radius * 2.0),
                       dx * 0.85 * strength, dy * 0.85 * strength)

    # -- физика шаров и снеговиков ---------------------------------------
    def _drift_near(self, x: float, bottom: float) -> Drift | None:
        """Ближайшая кромка, на которую можно поставить шар."""
        best = None
        best_d = 1e18
        for d in self._drifts_cache:
            if not d.contains(x):
                continue
            if d.kind == "window" and max(d.h) < 0.35:
                continue
            surf = d.surface(x)
            dist = abs(surf - bottom)
            if dist < 42.0 and dist < best_d:
                best = d
                best_d = dist
        return best

    @staticmethod
    def _anchor_ball(b: Ball, d: Drift) -> None:
        b.drift = d
        b.adx = b.x - d.x
        b.ah = d.surface(b.x) - b.y
        b.falling = False
        b.vx = b.vy = 0.0

    def _update_ball(self, b: Ball, dt: float) -> bool:
        if not b.falling and b.drift is not None:
            d = b.drift
            nx = d.x + b.adx
            if (d not in self._drifts_cache
                    or nx < d.x - 2.0 or nx > d.x + d.w + 2.0
                    or (d.kind == "window"
                        and (d.is_empty() or d.y - d.surface(nx) < 0.30))):
                b.drift = None
                b.falling = True
                b.vy = max(40.0, b.vy)
                if self.core.verbose:
                    print("ball falls: x=%.0f y=%.0f" % (b.x, b.y), flush=True)
                return True
            b.x = nx
            b.y = d.surface(nx) - b.ah
            return True

        b.falling = True
        prev_bottom = b.y + b.r
        b.vy = min(760.0, b.vy + b.g * dt)
        b.x += b.vx * dt
        b.y += b.vy * dt
        b.vx *= max(0.0, 1.0 - dt * 0.55)
        new_bottom = b.y + b.r
        land = self._landing(b.x, min(prev_bottom, new_bottom),
                             max(prev_bottom, new_bottom),
                             allow_empty=False)
        if land is not None and b.vy >= 0.0:
            b.y = land.surface(b.x) - b.r
            self._anchor_ball(b, land)
            if self.core.verbose:
                print("ball landed: x=%.0f y=%.0f" % (b.x, b.y), flush=True)
        if b.y - b.r > self.lh + 90.0 or b.x < -240.0 or b.x > self.lw + 240.0:
            return False
        return True

    def _update_snowman(self, sm: Snowman, dt: float) -> bool:
        base = sm.balls[0]
        if not sm.falling and sm.drift is not None:
            d = sm.drift
            nx = d.x + sm.adx
            if (d not in self._drifts_cache
                    or nx < d.x - 2.0 or nx > d.x + d.w + 2.0
                    or (d.kind == "window"
                        and (d.is_empty() or d.y - d.surface(nx) < 0.30))):
                sm.drift = None
                sm.falling = True
                sm.vy = max(50.0, sm.vy)
                if self.core.verbose:
                    print("snowman falls: x=%.0f y=%.0f" % (
                        base.x, base.y), flush=True)
                return True
            ny = d.surface(nx) - sm.ah
            dx = nx - base.x
            dy = ny - base.y
            for b in sm.balls:
                b.x += dx
                b.y += dy
            return True

        sm.falling = True
        prev_bottom = base.y + base.r
        sm.vy = min(760.0, sm.vy + sm.g * dt)
        dx = sm.vx * dt
        dy = sm.vy * dt
        for b in sm.balls:
            b.x += dx
            b.y += dy
        sm.vx *= max(0.0, 1.0 - dt * 0.5)
        new_bottom = base.y + base.r
        land = self._landing(base.x, min(prev_bottom, new_bottom),
                             max(prev_bottom, new_bottom),
                             allow_empty=False)
        if land is not None and sm.vy >= 0.0:
            dy = land.surface(base.x) - base.r - base.y
            for b in sm.balls:
                b.y += dy
            sm.drift = land
            sm.adx = base.x - land.x
            sm.ah = base.r
            sm.falling = False
            sm.vx = sm.vy = 0.0
            if self.core.verbose:
                print("snowman landed: x=%.0f y=%.0f" % (
                    base.x, base.y), flush=True)
        if base.y - base.r > self.lh + 120.0 \
                or base.x < -260.0 or base.x > self.lw + 260.0:
            return False
        return True

    def _update_figures(self, dt: float) -> None:
        if self.placed:
            for b in list(self.placed):
                if not self._update_ball(b, dt):
                    try:
                        self.placed.remove(b)
                    except ValueError:
                        pass
        for sm in list(self.snowmen):
            if not self._update_snowman(sm, dt):
                try:
                    self.snowmen.remove(sm)
                except ValueError:
                    pass

    def clear_snow(self) -> None:
        for d in self._drifts_cache:
            d.clear()
        self.update()

    # -- мышь ------------------------------------------------------------
    def mousePressEvent(self, event) -> None:  # noqa: N802
        if not self.core.interactive:
            return
        pos = self._to_model(event.position())
        self._hover = pos
        self._press_active = True
        self._press_pos = pos
        self._drag_total = 0.0

        if event.button() == Qt.MouseButton.RightButton:
            self._right_drag = True
            self._sweep(pos, pos, 30.0, 0.85)
            event.accept()
            return

        if event.button() != Qt.MouseButton.LeftButton:
            event.accept()
            return

        hit = self._figure_hit(pos, True)
        if hit is not None:
            ball, sm = hit
            if sm is not None:
                self._break_snowman(sm)
            else:
                self._break_ball(ball)
            event.accept()
            return

        self._dragging = True
        self._drag_ball = Ball(pos.x(), pos.y(), 7.0)
        event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        pos = self._to_model(event.position())
        prev = self._hover
        self._hover = pos
        if not self._press_active:
            self._update_cursor(pos)
            return
        self._drag_total += math.hypot(pos.x() - prev.x(), pos.y() - prev.y())
        if self._right_drag:
            self._sweep(prev, pos, 30.0, 0.85)
        elif self._drag_ball is not None:
            self._roll_ball(self._drag_ball, pos)
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._drag_ball is not None:
            b = self._drag_ball
            self._drag_ball = None
            pos = self._to_model(event.position())
            self._roll_ball(b, pos)
            bottom = b.y + b.r
            d = self._drift_near(b.x, bottom)
            if d is not None:
                b.y = d.surface(b.x) - b.r
                self._anchor_ball(b, d)
            else:
                b.drift = None
                b.falling = True
                b.vx = 0.0
                b.vy = max(20.0, b.vy)
            self.placed.append(b)
            self._try_snowman()
            if self.core.verbose:
                print("place ball: placed=%d snowmen=%d x=%.0f y=%.0f r=%.1f" % (
                    len(self.placed), len(self.snowmen), b.x, b.y, b.r),
                    flush=True)
        self._dragging = False
        self._right_drag = False
        self._press_active = False
        self.update()
        event.accept()

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = QPointF(-5000.0, -5000.0)

    def _roll_ball(self, b: Ball, pos: QPointF) -> None:
        dx = pos.x() - b.x
        dy = pos.y() - b.y
        dist = math.hypot(dx, dy)
        if dist < 0.5:
            return
        steps = max(1, int(dist / 8.0))
        gained = 0.0
        for k in range(1, steps + 1):
            x = b.x + dx * k / steps
            y = b.y + dy * k / steps
            for d in self._drifts_cache:
                gained += d.wipe(x, y, max(12.0, b.r * 0.9), 0.9)
            self.snow.stir(x, y, b.r * 2.0, dx / steps * 0.6, dy / steps * 0.6)
        b.x, b.y = pos.x(), pos.y()
        b.r = min(34.0, b.r + gained * 0.075)

    def _try_snowman(self) -> None:
        if len(self.snowmen) >= 4 or len(self.placed) < 3:
            return
        trio = self.placed[-3:]
        xs = [b.x for b in trio]
        ys = [b.y for b in trio]
        if max(xs) - min(xs) > 190.0 or max(ys) - min(ys) > 240.0:
            return
        if any(b.drift is None or b.drift not in self._drifts_cache
               for b in trio):
            return

        ref = max(trio, key=lambda z: z.y)
        d = ref.drift
        if d is None or d not in self._drifts_cache:
            d = self.bottom
        if any(b.drift is not d for b in trio):
            return
        cx = sum(xs) / 3.0
        cx = clamp(cx, d.x + 34.0, d.x + max(35.0, d.w - 34.0))
        surf = d.surface(cx)
        self.placed = self.placed[:-3]

        r1 = max(16.0, max(b.r for b in trio))
        r2 = r1 * 0.72
        r3 = r1 * 0.50
        base = Ball(cx, surf - r1, r1)
        mid = Ball(cx, base.y - (r1 + r2) * 0.92, r2)
        head = Ball(cx, mid.y - (r2 + r3) * 0.92, r3)
        for b in (base, mid, head):
            b.drift = d
            b.adx = cx - d.x
            b.ah = surf - b.y
            b.falling = False
        self.snowmen.append(Snowman([base, mid, head], d, base.adx, base.ah))

    def _puff(self, x: float, y: float, radius: float) -> None:
        n = int(clamp(radius * 1.25, 8.0, 28.0))
        for _ in range(n):
            a = random.uniform(0.0, math.tau)
            sp = random.uniform(35.0, 145.0)
            self.snow.shed(
                x + math.cos(a) * radius * 0.55,
                y + math.sin(a) * radius * 0.55,
                math.cos(a) * sp, math.sin(a) * sp + 12.0,
                random.uniform(1.0, 2.4), 0.7)

    def _break_ball(self, b: Ball) -> None:
        try:
            self.placed.remove(b)
        except ValueError:
            pass
        self._puff(b.x, b.y, b.r)
        if self.core.verbose:
            print("break ball: placed=%d" % len(self.placed), flush=True)

    def _break_snowman(self, sm: Snowman) -> None:
        try:
            self.snowmen.remove(sm)
        except ValueError:
            return
        for b in sm.balls:
            self._puff(b.x, b.y, max(10.0, b.r * 0.9))
        if self.core.verbose:
            print("break snowman: snowmen=%d" % len(self.snowmen), flush=True)

    def clear_figures(self) -> None:
        while self.placed:
            self._break_ball(self.placed[-1])
        while self.snowmen:
            self._break_snowman(self.snowmen[-1])
        self.update()


    def _adapt_quality(self) -> None:
        """Если кадры не успевают — потихоньку уменьшаем количество снежинок."""
        target = float(self.cfg["quality"])
        self._fps_hist.append(self.fps)
        if len(self._fps_hist) > 8:
            self._fps_hist.pop(0)
        if len(self._fps_hist) < 4:
            return
        avg = sum(self._fps_hist[-4:]) / 4.0
        if avg < target * 0.80 and self.snow.quality_scale > 0.35:
            self.snow.set_quality_scale(self.snow.quality_scale - 0.12)
            self._fps_hist.clear()
        elif avg > target * 0.97 and self.snow.quality_scale < 1.0:
            self.snow.set_quality_scale(min(1.0, self.snow.quality_scale + 0.06))
            self._fps_hist.clear()

    # -- рисование ------------------------------------------------------
    def _draw_ball(self, p: QPainter, b: Ball) -> None:
        g = QRadialGradient(QPointF(b.x - b.r * 0.35, b.y - b.r * 0.35), b.r * 1.7)
        g.setColorAt(0.0, QColor(255, 255, 255, 255))
        g.setColorAt(0.62, QColor(244, 250, 255, 252))
        g.setColorAt(1.0, QColor(201, 221, 241, 252))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawEllipse(QPointF(b.x, b.y), b.r, b.r)

    def _paint_balls(self, p: QPainter) -> None:
        for b in self.placed:
            self._draw_ball(p, b)
        if self._drag_ball is not None:
            self._draw_ball(p, self._drag_ball)
        for sm in self.snowmen:
            base, mid, head = sm.balls
            for b in sm.balls:
                self._draw_ball(p, b)

            # руки-веточки
            arm_r = max(1.4, mid.r * 0.10)
            arm = QPen(QColor(96, 70, 46), arm_r,
                       Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            p.setPen(arm)
            p.drawLine(QPointF(mid.x - mid.r * 0.86, mid.y - mid.r * 0.10),
                       QPointF(mid.x - mid.r * 2.05, mid.y - mid.r * 0.85))
            p.drawLine(QPointF(mid.x + mid.r * 0.86, mid.y - mid.r * 0.10),
                       QPointF(mid.x + mid.r * 2.05, mid.y - mid.r * 0.85))

            # пуговицы
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(52, 64, 80, 220))
            for k in (-0.28, 0.12, 0.52):
                p.drawEllipse(QPointF(mid.x, mid.y + mid.r * k),
                              mid.r * 0.085, mid.r * 0.085)

            # глаза
            eye = max(1.3, head.r * 0.11)
            for s in (-1.0, 1.0):
                p.drawEllipse(QPointF(head.x + s * head.r * 0.31,
                                      head.y - head.r * 0.22), eye, eye)

            # морковка
            p.setBrush(QColor(238, 150, 48))
            p.drawPolygon(QPolygonF([
                QPointF(head.x + head.r * 0.08, head.y + head.r * 0.02),
                QPointF(head.x + head.r * 0.82, head.y + head.r * 0.17),
                QPointF(head.x + head.r * 0.10, head.y + head.r * 0.28),
            ]))

            # ведро
            p.setBrush(QColor(126, 138, 154))
            p.drawPolygon(QPolygonF([
                QPointF(head.x - head.r * 0.56, head.y - head.r * 0.60),
                QPointF(head.x + head.r * 0.56, head.y - head.r * 0.60),
                QPointF(head.x + head.r * 0.40, head.y - head.r * 1.06),
                QPointF(head.x - head.r * 0.40, head.y - head.r * 1.06),
            ]))

    def _update_countdown(self) -> None:
        now = self._clock
        target = datetime.datetime(now.year + 1, 1, 1)
        secs = int((target - now).total_seconds())
        if secs <= 0:
            self._countdown_text = "С НОВЫМ ГОДОМ!"
            return
        days, rem = divmod(secs, 86400)
        hours, rem = divmod(rem, 3600)
        mins, sec = divmod(rem, 60)
        if days > 0:
            self._countdown_text = "До Нового года %d дн.  %02d:%02d:%02d" % (
                days, hours, mins, sec)
        else:
            self._countdown_text = "До Нового года  %02d:%02d:%02d" % (
                hours, mins, sec)

    def _auto_fireworks(self) -> None:
        if not self.cfg.get("auto_fireworks", True):
            return
        now = self._clock
        new_year = ((now.month == 12 and now.day == 31 and now.hour >= 23)
                    or (now.month == 1 and now.day == 1 and now.hour == 0
                        and now.minute <= 8))
        if new_year and self.fireworks.run_for <= 0.0:
            self.fireworks.start(1.2)

    def _paint_garlands(self, p: QPainter) -> None:
        if not self.cfg.get("garland", True):
            return
        t = self.snow.t
        for idx, d in enumerate(self.windows.paint_order()):
            if d.w < 170.0:
                continue
            n = int(clamp(d.w / 54.0, 5.0, 16.0))
            x0 = d.x + 10.0
            span = d.w - 20.0
            sag = clamp(d.w * 0.022, 6.0, 18.0)
            pts: list[tuple[float, float]] = []
            for i in range(n):
                u = i / (n - 1.0)
                pts.append((x0 + span * u,
                            d.y + 2.0 + sag * math.sin(math.pi * u)))

            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(158, 176, 196, 120), 1.0))
            path = QPainterPath(QPointF(pts[0][0], d.y))
            for px, py in pts:
                path.lineTo(px, py)
            path.lineTo(pts[-1][0], d.y)
            p.drawPath(path)

            p.setPen(Qt.PenStyle.NoPen)
            for i, (px, py) in enumerate(pts):
                level = int((0.5 + 0.5 * math.sin(t * 2.4 + i * 0.85 + idx))
                            * 7.99)
                draw_light(p, px, py, i + idx, level)

    def _paint_countdown(self, p: QPainter) -> None:
        if not self.cfg.get("countdown", True) or not self._countdown_text:
            return
        text = self._countdown_text
        font = QFont("Segoe UI Semibold")
        font.setPixelSize(15)
        p.setFont(font)
        fm = p.fontMetrics()
        w = fm.horizontalAdvance(text) + 34.0
        rect = QRectF(self.lw - w - 16.0, 12.0, w, 34.0)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(10, 26, 40, 165))
        p.drawRoundedRect(rect, 9.0, 9.0)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(255, 224, 150, 120), 1.2))
        p.drawRoundedRect(rect, 9.0, 9.0)
        p.setPen(QColor(255, 240, 205))
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)

    def _paint_hover(self, p: QPainter) -> None:
        if self._hover.x() < -1000.0 or self._hover.y() < -1000.0:
            return
        if self._drag_ball is not None and self._dragging:
            pen = QPen(QColor(220, 240, 255, 170), 1.7,
                       Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(self._drag_ball.x, self._drag_ball.y),
                          self._drag_ball.r + 3.0, self._drag_ball.r + 3.0)
            return
        hit = self._figure_hit(self._hover, True)
        if hit is not None:
            b, _sm = hit
            p.setPen(QPen(QColor(255, 230, 160, 190), 1.6,
                          Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(b.x, b.y), b.r + 5.0, b.r + 5.0)
            return
        if self._snow_hit(self._hover, True) is None:
            return
        pen = QPen(QColor(214, 236, 255, 120), 1.4, Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(self._hover, 15.0, 15.0)

    def _paint_flakes(self, p: QPainter) -> None:
        p.setPen(Qt.PenStyle.NoPen)
        colors = self._flake_colors
        for f in self.snow.flakes:
            if f.streak:
                continue
            p.setBrush(colors[int(f.depth * 7.999)])
            p.drawEllipse(QPointF(f.x, f.y), f.r, f.r)

        if self.snow.weather == "blizzard":
            # Метель: близкие снежинки рисуем штрихами по ветру
            wpx = self.snow.last_wind_px
            p.setBrush(Qt.BrushStyle.NoBrush)
            for f in self.snow.flakes:
                if not f.streak:
                    continue
                col = colors[int(f.depth * 7.999)]
                p.setPen(QPen(col, max(1.0, f.r * 0.85),
                              Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                p.drawLine(QPointF(f.x, f.y),
                           QPointF(f.x - wpx * 0.028, f.y - f.vy * 0.028))

    def paintEvent(self, event) -> None:  # noqa: N802
        t0 = time.perf_counter()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # В режиме игры окно должно ловить мышь даже над прозрачными местами:
        # Windows пропускает клики сквозь полностью прозрачные пиксели слоя,
        # поэтому заливаем фон почти невидимой белой плёнкой (альфа 1/255).
        if self.core.interactive:
            p.fillRect(QRectF(0.0, 0.0, self.lw, self.lh), QColor(255, 255, 255, 1))

        self._paint_flakes(p)
        t1 = time.perf_counter()
        # сугробы поверх снежинок: снег «впитывается» в кромку
        for d in self.windows.paint_order():
            d.paint(p)
        self.bottom.paint(p)
        self.plow.paint(p, self, self.snow.t)

        self._paint_garlands(p)
        if self.cfg.get("tree", True):
            self.tree.paint(p, self.lw - 24.0, self.lh - 2.0, self.snow.t)
        self._paint_balls(p)
        self.santa.paint(p, self.snow.t)
        self.fireworks.paint(p)
        if self.core.interactive:
            self._paint_hover(p)
        self._paint_countdown(p)
        t2 = time.perf_counter()

        if self.cfg["show_fps"]:
            self._paint_fps(p)

        p.end()
        t3 = time.perf_counter()
        self.flake_ms = (t1 - t0) * 1000.0
        self.drift_ms = (t2 - t1) * 1000.0
        self.frame_ms = (t3 - t0) * 1000.0
        self.core.report_frame_ms(self.frame_ms)

    def _paint_fps(self, p: QPainter) -> None:
        text = "FLAKELITE  %.0f FPS  %.1f+%.1f ms  flakes %d  drifts %d" % (
            self.fps, self.flake_ms, self.drift_ms,
            len(self.snow.flakes), len(self.windows.drifts) + 1)
        font = QFont("Segoe UI")
        font.setPixelSize(13)
        p.setFont(font)
        rect = QRectF(12, 10, 470, 26)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(12, 22, 38, 150))
        p.drawRoundedRect(rect, 7, 7)
        p.setPen(QColor(214, 235, 255))
        p.drawText(rect.adjusted(10, 0, 0, 0),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)


# --------------------------------------------------------------------------
# Автозапуск
# --------------------------------------------------------------------------

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def autostart_command() -> str:
    if getattr(sys, "frozen", False):
        return '"%s"' % sys.executable
    exe = Path(sys.executable)
    pyw = exe.with_name("pythonw.exe")
    if not pyw.exists():
        pyw = exe
    return '"%s" "%s"' % (pyw, Path(__file__).resolve())


def autostart_enabled() -> bool:
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY)
        try:
            val, _ = winreg.QueryValueEx(key, APP_NAME)
            return bool(val)
        finally:
            winreg.CloseKey(key)
    except Exception:
        return False


def set_autostart(enable: bool) -> bool:
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                             winreg.KEY_SET_VALUE)
        try:
            if enable:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ,
                                  autostart_command())
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                except FileNotFoundError:
                    pass
        finally:
            winreg.CloseKey(key)
        return True
    except Exception:
        return False


# --------------------------------------------------------------------------
# Панель управления
# --------------------------------------------------------------------------

HUD_STYLE = """
QPushButton {
    background: rgba(30, 50, 74, 235);
    color: #e6f1ff;
    border: 1px solid rgba(130, 176, 220, 110);
    border-radius: 6px;
    padding: 4px 6px;
    font-size: 12px;
}
QPushButton:hover { background: rgba(44, 72, 104, 245); }
QPushButton:checked { background: #3d7db6; border-color: #82c4ff; }
QCheckBox { color: #dce9f7; font-size: 12px; }
QLabel { color: #eaf3ff; font-size: 12px; }
QSlider::groove:horizontal {
    height: 4px; background: rgba(120, 156, 190, 120); border-radius: 2px;
}
QSlider::handle:horizontal {
    width: 14px; margin: -6px 0; border-radius: 7px; background: #8fd0ff;
}
"""


class Hud(QWidget):
    """Компактная панель управления поверх всех окон."""

    def __init__(self, core: "Core") -> None:
        super().__init__(None)
        self.core = core
        self.cfg = core.cfg
        self._drag: QPoint | None = None
        self.setWindowTitle("FlakeLite — панель")
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet(HUD_STYLE)
        self.setFixedWidth(330)
        self._build()
        pos = self.cfg.get("hud_pos") or [24, 56]
        self.move(int(pos[0]), int(pos[1]))
        self.sync()

    # -- сборка ----------------------------------------------------------
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(7)

        head = QHBoxLayout()
        title = QLabel("FlakeLite")
        title.setStyleSheet("font-size:15px; font-weight:600; color:#f4f9ff;")
        head.addWidget(title)
        head.addStretch(1)
        btn_close = QPushButton("×")
        btn_close.setFixedSize(24, 24)
        btn_close.setToolTip("Спрятать панель (снег останется)")
        btn_close.clicked.connect(self.hide_panel)
        head.addWidget(btn_close)
        root.addLayout(head)

        row = QHBoxLayout()
        row.setSpacing(5)
        self.weather_btns: dict[str, QPushButton] = {}
        group = QButtonGroup(self)
        for key, name in (("light", "Лёгкий"), ("steady", "Ровный"),
                          ("blizzard", "Метель")):
            b = QPushButton(name)
            b.setCheckable(True)
            b.clicked.connect(lambda _c=False, k=key: self.core.set_weather(k))
            group.addButton(b)
            row.addWidget(b)
            self.weather_btns[key] = b
        root.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(QLabel("Ветер"))
        self.wind = QSlider(Qt.Orientation.Horizontal)
        self.wind.setRange(-10, 10)
        self.wind.setToolTip("Сила и направление ветра")
        self.wind.valueChanged.connect(
            lambda v: self.core.set_wind(v / 10.0) if v != int(round(
                float(self.core.cfg["wind"]) * 10)) else None)
        row.addWidget(self.wind, 1)
        root.addLayout(row)

        hint = QLabel("Играется само: проведите мышью по снегу — покатится "
                      "снежок. Клик по шару или снеговику — разобрать, "
                      "правой кнопкой — смести снег.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#9fc4e2; font-size:11px;")
        root.addWidget(hint)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.chk: dict[str, QCheckBox] = {}
        for key, name in (("garland", "Гирлянда"), ("tree", "Ёлка"),
                          ("countdown", "Счётчик")):
            c = QCheckBox(name)
            c.toggled.connect(lambda v, k=key: self.core.set_decor(k, v))
            row.addWidget(c)
            self.chk[key] = c
        row.addStretch(1)
        root.addLayout(row)

        row = QHBoxLayout()
        row.setSpacing(5)
        b_fw = QPushButton("Салют")
        b_fw.clicked.connect(lambda: self.core.overlay.fireworks.start(9.0))
        row.addWidget(b_fw)
        b_santa = QPushButton("Дед Мороз")
        b_santa.setToolTip("Дед Мороз и Снегурочка на санях")
        b_santa.clicked.connect(lambda: self.core.overlay.santa.start(
            int(self.core.overlay.lw), int(self.core.overlay.lh)))
        row.addWidget(b_santa)
        b_post = QPushButton("Открытка")
        b_post.clicked.connect(self.core.take_postcard)
        row.addWidget(b_post)
        row.addStretch(1)
        root.addLayout(row)

        row = QHBoxLayout()
        row.setSpacing(5)
        b_wall = QPushButton("Зимние обои")
        b_wall.setToolTip("Обои меняются по часам: утро, день, вечер и ночь")
        b_wall.clicked.connect(self.core.set_wallpaper)
        row.addWidget(b_wall)
        b_plow = QPushButton("Снегоуборщик")
        b_plow.setToolTip("Позвать снегоуборщик на нижний сугроб")
        b_plow.clicked.connect(lambda: self.core.overlay.plow.start(
            int(self.core.overlay.lw)))
        row.addWidget(b_plow)
        row.addStretch(1)
        root.addLayout(row)

        self.chk_wall_caption = QCheckBox("Подпись на обоях")
        self.chk_wall_caption.setToolTip(
            "Показывать надпись «FlakeLite · время суток» на зимних обоях")
        self.chk_wall_caption.toggled.connect(self.core.set_wallpaper_caption)
        root.addWidget(self.chk_wall_caption)

        row = QHBoxLayout()
        self.chk_auto = QCheckBox("Автозапуск")
        self.chk_auto.setToolTip("Запускать FlakeLite вместе с Windows")
        self.chk_auto.toggled.connect(self.core.set_autostart_checked)
        row.addWidget(self.chk_auto)
        row.addStretch(1)
        b_hide = QPushButton("Пауза")
        b_hide.clicked.connect(self.core.toggle_pause)
        row.addWidget(b_hide)
        b_quit = QPushButton("Выход")
        b_quit.clicked.connect(self.core.quit)
        row.addWidget(b_quit)
        root.addLayout(row)

        self.donate_lbl = QLabel(
            "❤ Поддержать автора — совсем не обязательно, но очень приятно.\n"
            "Альфа-Банк: 2200 1530 1480 8720\n"
            "Телефон: +7 (904) 306-36-00")
        self.donate_lbl.setWordWrap(True)
        self.donate_lbl.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        self.donate_lbl.setStyleSheet(
            "color:#ffc2d2; font-size:11px; padding-top:2px;")
        root.addWidget(self.donate_lbl)

        self.chk_donate = QCheckBox("Показывать просьбу о поддержке")
        self.chk_donate.setToolTip("Скрыть или снова показать надпись о донате")
        self.chk_donate.toggled.connect(self.core.set_donate_visible)
        root.addWidget(self.chk_donate)

    # -- состояние -------------------------------------------------------
    def sync(self) -> None:
        cfg = self.cfg
        for key, btn in self.weather_btns.items():
            btn.blockSignals(True)
            btn.setChecked(cfg.get("weather") == key)
            btn.blockSignals(False)
        val = int(round(clamp(float(cfg.get("wind", 0.0)), -1.0, 1.0) * 10))
        if self.wind.value() != val:
            self.wind.blockSignals(True)
            self.wind.setValue(val)
            self.wind.blockSignals(False)
        for key, chk in self.chk.items():
            chk.blockSignals(True)
            chk.setChecked(bool(cfg.get(key, True)))
            chk.blockSignals(False)
        self.chk_auto.blockSignals(True)
        self.chk_auto.setChecked(bool(cfg.get("autostart", False)))
        self.chk_auto.blockSignals(False)
        self.chk_wall_caption.blockSignals(True)
        self.chk_wall_caption.setChecked(
            bool(cfg.get("wallpaper_caption", True)))
        self.chk_wall_caption.blockSignals(False)
        show_donate = bool(cfg.get("show_donate", True))
        self.chk_donate.blockSignals(True)
        self.chk_donate.setChecked(show_donate)
        self.chk_donate.blockSignals(False)
        self.donate_lbl.setVisible(show_donate)

    def hide_panel(self) -> None:
        self.cfg["hud_visible"] = False
        save_config(self.cfg)
        self.hide()
        self.core._refresh_menu_checks()

    # -- перетаскивание ---------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(0.5, 0.5, self.width() - 1.0, self.height() - 1.0)
        p.setPen(QPen(QColor(120, 170, 216, 150), 1.2))
        p.setBrush(QColor(10, 24, 40, 210))
        p.drawRoundedRect(rect, 12.0, 12.0)
        p.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag is not None:
            self.move(event.globalPosition().toPoint() - self._drag)
            event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._drag is not None:
            self._drag = None
            self.cfg["hud_pos"] = [self.x(), self.y()]
            save_config(self.cfg)


# --------------------------------------------------------------------------
# Ядро приложения
# --------------------------------------------------------------------------

class Core:
    def __init__(self, qapp: QApplication, cfg: dict) -> None:
        self.qapp = qapp
        self.cfg = cfg
        self.interactive = False
        self.game_hidden = False
        self._hide_streak = 0
        self._show_streak = 0
        self._fps = 0.0
        self._frame_ms = 0.0
        self._fps_samples: list[float] = []
        self._benchmark: list[float] = []
        self.verbose = False

        self.overlay = Overlay(self)
        self.overlay.hide()

        self.icon = make_snowflake_icon(64)
        qapp.setWindowIcon(self.icon)

        self.tray = QSystemTrayIcon(self.icon, qapp)
        self.tray.setToolTip("%s — снег на рабочем столе" % APP_NAME)
        self.menu = self._build_menu()
        self.tray.setContextMenu(self.menu)
        self.tray.show()

        self.hud = Hud(self)
        if self.cfg.get("hud_visible", True):
            self.hud.show()

        # Раз в секунду: не пора ли спрятаться под игру
        self.guard = QTimer()
        self.guard.setTimerType(Qt.TimerType.CoarseTimer)
        self.guard.timeout.connect(self._guard_tick)
        self.guard.start(900)

        # Зимние обои живут по часам: обновляем их понемногу, пока программа
        # запущена. Полноценной «живой обоины» Windows без службы не умеет.
        self.wall_timer = QTimer()
        self.wall_timer.setTimerType(Qt.TimerType.VeryCoarseTimer)
        self.wall_timer.timeout.connect(self._refresh_dynamic_wallpaper)
        self.wall_timer.start(150000)

        # Если обои уже стоят, сразу приводим их к текущему времени суток.
        cur_wall = current_wallpaper().lower()
        if "wallpaper_flakelite" in cur_wall:
            self.cfg["wallpaper_active"] = True
        elif self.cfg.get("wallpaper_active"):
            self.cfg["wallpaper_active"] = False
        if self.cfg.get("wallpaper_active"):
            QTimer.singleShot(1200, self._refresh_dynamic_wallpaper)

        # Пустой таймер, чтобы Python обрабатывал Ctrl+C в цикле Qt
        self._pump = QTimer()
        self._pump.timeout.connect(lambda: None)
        self._pump.start(250)

        qapp.screenAdded.connect(self._screens_changed)
        qapp.screenRemoved.connect(self._screens_changed)
        qapp.primaryScreenChanged.connect(self._screens_changed)

        self._apply_state()

    # -- жизненный цикл -------------------------------------------------
    def _screens_changed(self, *_args) -> None:
        self.overlay._apply_geometry()
        self.overlay.update()

    def _apply_state(self) -> None:
        if self.cfg["paused"] or self.game_hidden:
            self.overlay.stop()
            self.set_auto_interactive(False)
            if self.game_hidden:
                self.overlay.hide()
            elif not self.overlay.isVisible():
                self.overlay.show()
        else:
            self.overlay.show()
            self.overlay.start()

        want_hud = bool(self.cfg.get("hud_visible", True)) and not self.game_hidden
        if want_hud:
            if not self.hud.isVisible():
                self.hud.show()
        elif self.hud.isVisible():
            self.hud.hide()
        self._refresh_menu_checks()

    def _fullscreen_now(self) -> bool:
        """Есть ли сейчас полноэкранное приложение.

        QUNS_BUSY (2) намеренно не используем: этот же статус Windows
        выставляет из-за нашего оверлея, покрывающего весь экран, —
        получался цикл «спрятали → статус пропал → показали → статус вернулся».
        """
        if notification_state() in (3, 4):       # D3D-фуллскрин / презентация
            return True

        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return False
        if hwnd == int(self.overlay.winId()) or hwnd == int(self.hud.winId()):
            return False
        if window_pid(hwnd) == os.getpid():      # наши же окна
            return False

        fg = foreground_fullscreen_app()
        if fg:
            return True

        blocked = {str(x).lower() for x in self.cfg.get("pause_apps", [])}
        if blocked and process_name(hwnd) in blocked:
            return True
        return False

    def _guard_tick(self) -> None:
        if not self.cfg["pause_on_fullscreen"]:
            if self.game_hidden:
                self.game_hidden = False
                self._hide_streak = self._show_streak = 0
                self._apply_state()
            return

        want_hide = self._fullscreen_now()
        if want_hide:
            self._hide_streak += 1
            self._show_streak = 0
        else:
            self._show_streak += 1
            self._hide_streak = 0

        # Подтверждаем состояние два тика подряд (~1.8 с): alt-tab и
        # короткие всплывающие окна не должны дёргать снег.
        if not self.game_hidden:
            if self._hide_streak >= 2:
                self.game_hidden = True
                if self.verbose:
                    print("pause: True state:", notification_state(),
                          "fg:", process_name(user32.GetForegroundWindow()),
                          flush=True)
                self._apply_state()
        elif self._show_streak >= 2:
            self.game_hidden = False
            if self.verbose:
                print("pause: False state:", notification_state(),
                      flush=True)
            self._apply_state()

    # -- меню -----------------------------------------------------------
    def _build_menu(self) -> QMenu:
        menu = QMenu()

        self.act_pause = QAction("Пауза", menu)
        self.act_pause.setCheckable(True)
        self.act_pause.triggered.connect(self.toggle_pause)
        menu.addAction(self.act_pause)

        self.act_hud = QAction("Панель управления", menu)
        self.act_hud.setCheckable(True)
        self.act_hud.triggered.connect(self.toggle_hud)
        menu.addAction(self.act_hud)

        menu.addSeparator()

        self.weather_group = QActionGroup(menu)
        self.weather_group.setExclusive(True)
        self.weather_actions: dict[str, QAction] = {}
        for key, title in (("light", "Лёгкий снег"),
                           ("steady", "Ровный снег"),
                           ("blizzard", "Метель")):
            act = QAction(title, menu)
            act.setCheckable(True)
            act.triggered.connect(lambda _c=False, k=key: self.set_weather(k))
            self.weather_group.addAction(act)
            menu.addAction(act)
            self.weather_actions[key] = act

        menu.addSeparator()

        # Ветер
        wind_menu = menu.addMenu("Ветер")
        self.wind_group = QActionGroup(menu)
        self.wind_group.setExclusive(True)
        self.wind_actions: list[tuple[float, QAction]] = []
        for value, title in (
            (-1.0, "Сильный влево"),
            (-0.5, "Слабый влево"),
            (0.0, "Штиль"),
            (0.5, "Слабый вправо"),
            (1.0, "Сильный вправо"),
        ):
            act = QAction(title, menu)
            act.setCheckable(True)
            act.triggered.connect(lambda _c=False, v=value: self.set_wind(v))
            self.wind_group.addAction(act)
            wind_menu.addAction(act)
            self.wind_actions.append((value, act))

        # Качество
        quality_menu = menu.addMenu("Качество")
        self.quality_group = QActionGroup(menu)
        self.quality_group.setExclusive(True)
        self.quality_actions: dict[int, QAction] = {}
        for q, title in ((20, "Экономно (20 FPS)"),
                         (30, "Обычно (30 FPS)"),
                         (60, "Плавно (60 FPS)")):
            act = QAction(title, menu)
            act.setCheckable(True)
            act.triggered.connect(lambda _c=False, v=q: self.set_quality(v))
            self.quality_group.addAction(act)
            quality_menu.addAction(act)
            self.quality_actions[q] = act

        menu.addSeparator()

        self.act_clear = QAction("Смести весь снег", menu)
        self.act_clear.triggered.connect(lambda: self.overlay.clear_snow())
        menu.addAction(self.act_clear)

        self.act_clear_figures = QAction("Разобрать снеговиков и шары", menu)
        self.act_clear_figures.triggered.connect(
            lambda: self.overlay.clear_figures())
        menu.addAction(self.act_clear_figures)

        self.act_snow_windows = QAction("Сугробы на окнах", menu)
        self.act_snow_windows.setCheckable(True)
        self.act_snow_windows.triggered.connect(
            lambda: self.toggle_decor("snow_on_windows"))
        menu.addAction(self.act_snow_windows)

        menu.addSeparator()

        # Украшения
        self.act_garland = QAction("Гирлянда на окнах", menu)
        self.act_garland.setCheckable(True)
        self.act_garland.triggered.connect(lambda: self.toggle_decor("garland"))
        menu.addAction(self.act_garland)

        self.act_tree = QAction("Ёлка", menu)
        self.act_tree.setCheckable(True)
        self.act_tree.triggered.connect(lambda: self.toggle_decor("tree"))
        menu.addAction(self.act_tree)

        self.act_countdown = QAction("Счётчик до Нового года", menu)
        self.act_countdown.setCheckable(True)
        self.act_countdown.triggered.connect(lambda: self.toggle_decor("countdown"))
        menu.addAction(self.act_countdown)

        act_fw = QAction("Салют!", menu)
        act_fw.triggered.connect(lambda: self.overlay.fireworks.start(9.0))
        menu.addAction(act_fw)

        act_santa = QAction("Дед Мороз и Снегурочка", menu)
        act_santa.triggered.connect(
            lambda: self.overlay.santa.start(int(self.overlay.lw),
                                             int(self.overlay.lh)))
        menu.addAction(act_santa)

        act_plow = QAction("Снегоуборщик", menu)
        act_plow.triggered.connect(
            lambda: self.overlay.plow.start(int(self.overlay.lw)))
        menu.addAction(act_plow)

        menu.addSeparator()

        self.act_postcard = QAction("Открытка с экрана", menu)
        vk = int(getattr(self.overlay, "hotkey_vk", 0) or 0)
        names = {0x7B: "F12", 0x7A: "F11", 0x79: "F10", 0x78: "F9"}
        if vk in names:
            self.act_postcard.setText("Открытка с экрана  (%s)" % names[vk])
        self.act_postcard.triggered.connect(self.take_postcard)
        menu.addAction(self.act_postcard)

        wall_menu = menu.addMenu("Зимние обои")
        act_wall = QAction("Поставить зимние обои", wall_menu)
        act_wall.triggered.connect(self.set_wallpaper)
        wall_menu.addAction(act_wall)
        act_wall_back = QAction("Вернуть прежние обои", wall_menu)
        act_wall_back.triggered.connect(self.restore_wallpaper)
        wall_menu.addAction(act_wall_back)

        self.act_wall_caption = QAction("Подпись на обоях", menu)
        self.act_wall_caption.setCheckable(True)
        self.act_wall_caption.triggered.connect(self.toggle_wall_caption)
        menu.addAction(self.act_wall_caption)

        menu.addSeparator()

        self.act_donate = QAction("Просьба о поддержке", menu)
        self.act_donate.setCheckable(True)
        self.act_donate.triggered.connect(self.toggle_donate)
        menu.addAction(self.act_donate)

        act_thanks = QAction("❤ Поддержать автора", menu)
        act_thanks.triggered.connect(self.show_donate_info)
        menu.addAction(act_thanks)

        menu.addSeparator()

        self.act_fps = QAction("Показывать FPS", menu)
        self.act_fps.setCheckable(True)
        self.act_fps.triggered.connect(self.toggle_fps)
        menu.addAction(self.act_fps)

        self.act_hide = QAction("Спрятать снег (пауза)", menu)
        self.act_hide.triggered.connect(self.toggle_pause)
        menu.addAction(self.act_hide)

        menu.addSeparator()
        act_quit = QAction("Выход", menu)
        act_quit.triggered.connect(self.quit)
        menu.addAction(act_quit)

        return menu

    def _refresh_menu_checks(self) -> None:
        self.act_pause.setChecked(bool(self.cfg["paused"]))
        if hasattr(self, "act_hud"):
            self.act_hud.setChecked(bool(self.hud.isVisible()))
        if hasattr(self, "hud"):
            self.hud.sync()
        self.act_fps.setChecked(bool(self.cfg["show_fps"]))
        self.act_garland.setChecked(bool(self.cfg.get("garland", True)))
        self.act_snow_windows.setChecked(
            bool(self.cfg.get("snow_on_windows", True)))
        self.act_tree.setChecked(bool(self.cfg.get("tree", True)))
        self.act_countdown.setChecked(bool(self.cfg.get("countdown", True)))
        if hasattr(self, "act_donate"):
            self.act_donate.setChecked(
                bool(self.cfg.get("show_donate", True)))
        if hasattr(self, "act_wall_caption"):
            self.act_wall_caption.setChecked(
                bool(self.cfg.get("wallpaper_caption", True)))
        act = self.weather_actions.get(self.cfg["weather"])
        if act:
            act.setChecked(True)
        wind = float(self.cfg["wind"])
        for value, action in self.wind_actions:
            action.setChecked(abs(value - wind) < 0.01)
        qact = self.quality_actions.get(int(self.cfg["quality"]))
        if qact:
            qact.setChecked(True)

    # -- действия --------------------------------------------------------
    def toggle_hud(self) -> None:
        visible = not self.hud.isVisible()
        self.cfg["hud_visible"] = visible
        save_config(self.cfg)
        if visible:
            self.hud.show()
            self.hud.raise_()
        else:
            self.hud.hide()
        self._refresh_menu_checks()

    def set_decor(self, key: str, value: bool) -> None:
        if key not in ("garland", "tree", "countdown"):
            return
        self.cfg[key] = bool(value)
        save_config(self.cfg)
        self.overlay.update()
        self._refresh_menu_checks()

    def set_autostart_checked(self, value: bool) -> None:
        ok = set_autostart(bool(value))
        self.cfg["autostart"] = bool(value) if ok else autostart_enabled()
        save_config(self.cfg)
        self._refresh_menu_checks()

    def set_weather(self, key: str) -> None:
        self.cfg["weather"] = key
        save_config(self.cfg)
        self.overlay._apply_weather()
        self._refresh_menu_checks()

    def set_wind(self, value: float) -> None:
        self.cfg["wind"] = clamp(value, -1.0, 1.0)
        self.overlay.snow.set_wind(float(self.cfg["wind"]))
        save_config(self.cfg)
        self._refresh_menu_checks()

    def set_quality(self, quality: int) -> None:
        self.cfg["quality"] = int(quality)
        save_config(self.cfg)
        self.overlay.apply_config()
        self._refresh_menu_checks()

    def toggle_pause(self) -> None:
        self.cfg["paused"] = not bool(self.cfg["paused"])
        save_config(self.cfg)
        self._apply_state()

    def toggle_fps(self) -> None:
        self.cfg["show_fps"] = not bool(self.cfg["show_fps"])
        save_config(self.cfg)
        self.overlay.update()
        self._refresh_menu_checks()

    def set_donate_visible(self, value: bool) -> None:
        self.cfg["show_donate"] = bool(value)
        save_config(self.cfg)
        self._refresh_menu_checks()

    def toggle_donate(self) -> None:
        self.set_donate_visible(not bool(self.cfg.get("show_donate", True)))

    def set_wallpaper_caption(self, value: bool) -> None:
        value = bool(value)
        if value == bool(self.cfg.get("wallpaper_caption", True)):
            return
        self.cfg["wallpaper_caption"] = value
        save_config(self.cfg)
        self._refresh_menu_checks()
        if "wallpaper_flakelite" in current_wallpaper().lower():
            self._render_wallpaper()

    def toggle_wall_caption(self) -> None:
        self.set_wallpaper_caption(
            not bool(self.cfg.get("wallpaper_caption", True)))

    def show_donate_info(self) -> None:
        card = "2200 1530 1480 8720"
        box = QMessageBox()
        box.setWindowTitle("FlakeLite — спасибо!")
        box.setIcon(QMessageBox.Icon.Information)
        box.setTextFormat(Qt.TextFormat.PlainText)
        box.setText(
            "Спасибо, что пользуетесь FlakeLite!\n\n"
            "Программа бесплатная и останется бесплатной. Я очень старался "
            "сделать её лёгкой, красивой и новогодней. Если она вам нравится "
            "и есть желание поддержать автора — буду очень благодарен. "
            "Это совсем не обязательно.\n\n"
            "Альфа-Банк: %s\n"
            "Телефон: +7 (904) 306-36-00\n\n"
            "Надпись можно скрыть галочкой «Показывать просьбу о поддержке» "
            "в панели управления или в меню трея." % card)
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        copy_btn = box.addButton("Скопировать номер карты",
                                 QMessageBox.ButtonRole.ActionRole)
        box.exec()
        if box.clickedButton() is copy_btn:
            QGuiApplication.clipboard().setText(card)
            self.tray.showMessage(APP_NAME, "Номер карты скопирован",
                                  QSystemTrayIcon.MessageIcon.Information, 3000)

    def set_auto_interactive(self, value: bool) -> None:
        """Оверлей ловит мышь только рядом со снегом — кнопки не нужны."""
        value = bool(value)
        if value == bool(self.interactive):
            return
        self.interactive = value
        self.overlay.set_click_through(not value)
        self.overlay.update()
        if self.verbose:
            print("interact:", value, flush=True)

    def take_postcard(self) -> None:
        path = self.overlay.make_postcard()
        icon = QSystemTrayIcon.MessageIcon
        if path is None:
            self.tray.showMessage(APP_NAME, "Не удалось сохранить открытку",
                                  icon.Warning, 5000)
            return
        self.tray.showMessage(APP_NAME, "Открытка сохранена:\n%s" % path,
                              icon.Information, 8000)

    def _wallpaper_slot_path(self) -> Path:
        """Два чередующихся файла: Windows не перечитывает тот же путь."""
        cur = current_wallpaper().lower()
        slot = 1 if "wallpaper_flakelite_0" in cur else 0
        return config_path().parent / ("wallpaper_flakelite_%d.png" % slot)

    def _render_wallpaper(self) -> bool:
        scr = QGuiApplication.primaryScreen()
        if scr is None:
            return False
        old = current_wallpaper()
        if old and "wallpaper_flakelite" not in old.lower():
            self.cfg["old_wallpaper"] = old
        dpr = scr.devicePixelRatio() or 1.0
        w = int(scr.size().width() * dpr)
        h = int(scr.size().height() * dpr)
        scale = max(1.0, 1280.0 / max(1, w), 720.0 / max(1, h))
        w = int(w * scale)
        h = int(h * scale)
        img = make_wallpaper(max(1280, w), max(720, h),
                             datetime.datetime.now(),
                             bool(self.cfg.get("wallpaper_caption", True)))
        path = self._wallpaper_slot_path()
        if not img.save(str(path), "PNG"):
            return False
        self.cfg["wallpaper_active"] = True
        save_config(self.cfg)
        return set_system_wallpaper(str(path))

    def _refresh_dynamic_wallpaper(self) -> None:
        if not self.cfg.get("wallpaper_active"):
            return
        if self.cfg.get("paused") or self.game_hidden:
            return
        cur = current_wallpaper()
        if cur and "wallpaper_flakelite" not in cur.lower():
            # Пользователь поставил свои обои — больше не трогаем.
            self.cfg["wallpaper_active"] = False
            self.cfg["old_wallpaper"] = ""
            save_config(self.cfg)
            return
        self._render_wallpaper()

    def set_wallpaper(self) -> None:
        if self._render_wallpaper():
            self.tray.showMessage(
                APP_NAME,
                "Зимние обои включены: небо, солнце и сугробы\n"
                "меняются вместе с временем суток",
                QSystemTrayIcon.MessageIcon.Information, 5000)
        else:
            self.tray.showMessage(APP_NAME, "Не удалось сменить обои",
                                  QSystemTrayIcon.MessageIcon.Warning, 5000)

    def restore_wallpaper(self, quiet: bool = False) -> None:
        self.cfg["wallpaper_active"] = False
        old = str(self.cfg.get("old_wallpaper") or "")
        ok = False
        if old and "wallpaper_flakelite" not in old.lower():
            ok = set_system_wallpaper(old)
        if ok:
            self.cfg["old_wallpaper"] = ""
        save_config(self.cfg)
        if quiet:
            return
        if ok:
            self.tray.showMessage(APP_NAME, "Прежние обои возвращены",
                                  QSystemTrayIcon.MessageIcon.Information, 4000)
        elif old:
            self.tray.showMessage(APP_NAME, "Не удалось вернуть прежние обои",
                                  QSystemTrayIcon.MessageIcon.Warning, 5000)

    def restore_wallpaper_on_exit(self) -> None:
        """При выходе не оставляем зимние обои включёнными."""
        cur = current_wallpaper().lower()
        if "wallpaper_flakelite" in cur:
            self.restore_wallpaper(quiet=True)
            return
        # Пользователь уже поставил другие обои — их не трогаем.
        if self.cfg.get("wallpaper_active") or self.cfg.get("old_wallpaper"):
            self.cfg["wallpaper_active"] = False
            self.cfg["old_wallpaper"] = ""
            save_config(self.cfg)

    def toggle_decor(self, key: str) -> None:
        self.cfg[key] = not bool(self.cfg.get(key, True))
        save_config(self.cfg)
        self.overlay.update()
        self._refresh_menu_checks()

    def report_fps(self, fps: float) -> None:
        self._fps = fps
        self._fps_samples.append(fps)
        if len(self._fps_samples) > 20:
            self._fps_samples.pop(0)

    def report_frame_ms(self, ms: float) -> None:
        self._frame_ms = ms
        self._benchmark.append(ms)
        if len(self._benchmark) > 4000:
            self._benchmark.pop(0)

    def stats(self) -> str:
        if not self._fps_samples:
            return "нет данных"
        avg_fps = sum(self._fps_samples) / len(self._fps_samples)
        if self._benchmark:
            ms = sorted(self._benchmark)
            p50 = ms[len(ms) // 2]
            p95 = ms[min(len(ms) - 1, int(len(ms) * 0.95))]
        else:
            p50 = p95 = 0.0
        return "fps avg %.1f | paint p50 %.2f ms | p95 %.2f ms | flake %.2f | drift %.2f | flakes %d | drifts %d" % (
            avg_fps, p50, p95, self.overlay.flake_ms, self.overlay.drift_ms,
            len(self.overlay.snow.flakes), len(self.overlay.windows.drifts) + 1)

    def quit(self) -> None:
        self.restore_wallpaper_on_exit()
        save_config(self.cfg)
        try:
            user32.UnregisterHotKey(int(self.overlay.winId()), 0x4B1)
        except Exception:
            pass
        self.overlay.timer.stop()
        self.guard.stop()
        self.wall_timer.stop()
        self.tray.hide()
        self.qapp.quit()


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def parse_args(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="FlakeLite — новогодний снег на рабочем столе")
    ap.add_argument("--fps", action="store_true", help="показать счётчик кадров")
    ap.add_argument("--weather", choices=sorted(WEATHER), help="режим снега")
    ap.add_argument("--wind", type=float, help="-1..1, ветер")
    ap.add_argument("--quality", type=int, choices=(20, 30, 60), help="целевой FPS")
    ap.add_argument("--density", type=float, help="плотность снега 0.2..2")
    ap.add_argument("--no-pause", action="store_true",
                    help="не прятаться при полноэкранных приложениях (для проверок)")
    ap.add_argument("--verbose", action="store_true", help="печатать события паузы")
    ap.add_argument("--no-hud", action="store_true", help="не показывать панель")
    ap.add_argument("--dump-windows", action="store_true",
                    help="печатать окна, на которые ложится снег")
    ap.add_argument("--exit-after", type=float, default=0.0, help="выйти через N секунд")
    ap.add_argument("--reset-config", action="store_true", help="сбросить настройки")
    return ap.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    set_dpi_awareness()

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    qapp = QApplication(sys.argv[:1])
    qapp.setQuitOnLastWindowClosed(False)
    qapp.setApplicationName(APP_NAME)
    qapp.setApplicationDisplayName(APP_NAME)

    cfg = dict(DEFAULT_CONFIG) if args.reset_config else load_config()
    if args.fps:
        cfg["show_fps"] = True
    if args.weather:
        cfg["weather"] = args.weather
    if args.wind is not None:
        cfg["wind"] = clamp(args.wind, -1.0, 1.0)
    if args.quality:
        cfg["quality"] = args.quality
    if args.density is not None:
        cfg["density"] = clamp(args.density, 0.2, 2.0)
    if args.no_pause:
        cfg["pause_on_fullscreen"] = False
    if args.no_hud:
        cfg["hud_visible"] = False
    cfg["autostart"] = autostart_enabled()

    core = Core(qapp, cfg)
    core.verbose = bool(args.verbose)
    core.overlay.debug_windows = bool(args.dump_windows)
    core._apply_state()

    if args.exit_after > 0:
        QTimer.singleShot(int(args.exit_after * 1000), core.quit)

    code = qapp.exec()
    # Страховка: если приложение закрыли не через меню, обои всё равно
    # возвращаем на прежние.
    core.restore_wallpaper_on_exit()
    try:
        print("stats:", core.stats(), flush=True)
    except Exception:
        pass
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))