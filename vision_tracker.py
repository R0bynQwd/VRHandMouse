import argparse
import atexit
import ctypes
import ctypes.wintypes as wintypes
import math
import signal
import sys
import time
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
import threading

import cv2
import mediapipe as mp


user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
kernel32_mutex = ctypes.WinDLL("kernel32", use_last_error=True)
shell32 = ctypes.windll.shell32
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_WHEEL = 0x0800
SPI_SETCURSORS = 0x0057
OCR_NORMAL = 32512
IDC_HAND = 32649
IDC_SIZEALL = 32646
IDC_CROSS = 32515
IMAGE_CURSOR = 2
IMAGE_ICON = 1
HWND_TOPMOST = -1
SWP_SHOWWINDOW = 0x0040
SW_HIDE = 0
SW_SHOW = 5
LR_LOADFROMFILE = 0x0010
LR_DEFAULTSIZE = 0x0040
ERROR_ALREADY_EXISTS = 183
WM_USER = 0x0400
WM_APP_TRAY = WM_USER + 1
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205
WM_CLOSE = 0x0010
WM_DESTROY = 0x0002
NIM_ADD = 0x00000000
NIM_MODIFY = 0x00000001
NIM_DELETE = 0x00000002
NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004
NIF_INFO = 0x00000010
NIIF_INFO = 0x00000001
IDI_APPLICATION = 32512
MF_STRING = 0x00000000
MF_GRAYED = 0x00000001
TPM_RETURNCMD = 0x0100
TPM_NONOTIFY = 0x0080
MB_ICONWARNING = 0x00000030
VK_ESCAPE = 0x1B
VK_CONTROL = 0x11
VK_SHIFT = 0x10
KEYEVENTF_KEYUP = 0x0002
WHEEL_DELTA = 120

WINDOW_TITLE = "VR Hand Controller"
CURSOR_MARGIN = 0.08
CALIBRATION_MARGIN = 0.02
MIN_CALIBRATION_SPAN = 0.18
CALIBRATION_PINCH_DOWN_RATIO = 0.42
CALIBRATION_PINCH_UP_RATIO = 0.60
CALIBRATION_CLICK_COOLDOWN = 0.18
MOVE_SMOOTHING = 0.35
CURSOR_DEADZONE = 6
PINCH_DOWN_RATIO = 0.33
PINCH_UP_RATIO = 0.52
PINCH_DRAG_SECONDS = 1.5
PINCH_DRAG_MOVE_RATIO = 0.25
PINCH_TAP_MOVE_RATIO = 0.14
DOUBLE_TAP_GAP = 0.35
RIGHT_CLICK_DOWN_RATIO = 0.31
RIGHT_CLICK_UP_RATIO = 0.48
SCROLL_DOWN_RATIO = 0.34
SCROLL_UP_RATIO = 0.50
SCROLL_HOLD_SECONDS = 0.24
SCROLL_TRIGGER_DELTA = 0.018
TOGGLE_TOUCH_RATIO = 0.52
TOGGLE_MIN_WRIST_RATIO = 0.45
TOGGLE_HOLD_SECONDS = 0.08
TOGGLE_COOLDOWN_SECONDS = 1.10
EXIT_X_MIN_SPAN_RATIO = 0.85
EXIT_X_HOLD_SECONDS = 0.35
DUAL_GRAB_ENTER_RATIO = 0.36
DUAL_GRAB_EXIT_RATIO = 0.54
DUAL_GRAB_HOLD_SECONDS = 0.22
DUAL_RELEASE_SECONDS = 0.16
TWO_HAND_SUPPRESS_SECONDS = 0.25
ZOOM_TRIGGER_DELTA = 0.03
ROTATION_TRIGGER_DELTA = 0.16
ROTATION_DRAG_PIXELS = 28
NO_HANDS_SECONDS = 0.14

CURSOR_BY_MODE = {
    "cursor": IDC_HAND,
    "drag": IDC_SIZEALL,
    "scroll": IDC_SIZEALL,
    "three_d": IDC_CROSS,
}

_cleanup_ref = None
_runtime_for_cleanup = None


def runtime_root():
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parent


def clamp(value, minimum, maximum):
    return max(minimum, min(value, maximum))


def point_distance(point_a, point_b):
    return math.hypot(point_a[0] - point_b[0], point_a[1] - point_b[1])


def point_orientation(point_a, point_b, point_c):
    return (point_b[0] - point_a[0]) * (point_c[1] - point_a[1]) - (point_b[1] - point_a[1]) * (point_c[0] - point_a[0])


def segments_intersect(point_a, point_b, point_c, point_d):
    orientation_1 = point_orientation(point_a, point_b, point_c)
    orientation_2 = point_orientation(point_a, point_b, point_d)
    orientation_3 = point_orientation(point_c, point_d, point_a)
    orientation_4 = point_orientation(point_c, point_d, point_b)
    return orientation_1 * orientation_2 < 0 and orientation_3 * orientation_4 < 0


def wrap_angle_delta(delta):
    while delta > math.pi:
        delta -= 2 * math.pi
    while delta < -math.pi:
        delta += 2 * math.pi
    return delta


def map_normalized_to_screen(value, screen_size):
    usable = clamp((value - CURSOR_MARGIN) / (1 - (CURSOR_MARGIN * 2)), 0.0, 1.0)
    return int(usable * screen_size)


def map_calibrated_to_screen(value, screen_size, lower_bound, upper_bound):
    if lower_bound is None or upper_bound is None or upper_bound - lower_bound < MIN_CALIBRATION_SPAN:
        return map_normalized_to_screen(value, screen_size)

    lower = clamp(lower_bound - CALIBRATION_MARGIN, 0.0, 1.0)
    upper = clamp(upper_bound + CALIBRATION_MARGIN, 0.0, 1.0)
    if upper - lower < MIN_CALIBRATION_SPAN:
        return map_normalized_to_screen(value, screen_size)

    usable = clamp((value - lower) / (upper - lower), 0.0, 1.0)
    return int(usable * screen_size)


def move_cursor(x, y):
    user32.SetCursorPos(int(x), int(y))


def hide_console():
    console = kernel32.GetConsoleWindow()
    if console:
        user32.ShowWindow(console, SW_HIDE)


def show_console():
    console = kernel32.GetConsoleWindow()
    if console:
        user32.ShowWindow(console, SW_SHOW)
        user32.SetForegroundWindow(console)


def acquire_single_instance_mutex():
    mutex_name = "Local\\VRHandControllerSingleton"
    ctypes.set_last_error(0)
    mutex_handle = kernel32_mutex.CreateMutexW(None, False, mutex_name)
    if not mutex_handle:
        return None, False
    return mutex_handle, ctypes.get_last_error() != ERROR_ALREADY_EXISTS


def set_left_button(is_down):
    event = MOUSEEVENTF_LEFTDOWN if is_down else MOUSEEVENTF_LEFTUP
    user32.mouse_event(event, 0, 0, 0, 0)


def click_left_button(double=False):
    count = 2 if double else 1
    for index in range(count):
        user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        if double and index == 0:
            time.sleep(0.05)


def click_right_button():
    user32.mouse_event(MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
    user32.mouse_event(MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)


def send_scroll(notches):
    if not notches:
        return

    direction = 1 if notches > 0 else -1
    for _ in range(abs(notches)):
        user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, direction * WHEEL_DELTA, 0)


def send_zoom(notches):
    if not notches:
        return

    user32.keybd_event(VK_CONTROL, 0, 0, 0)
    try:
        direction = 1 if notches > 0 else -1
        for _ in range(abs(notches)):
            user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, direction * WHEEL_DELTA, 0)
    finally:
        user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)


def send_rotation_drag(steps):
    if not steps:
        return

    user32.keybd_event(VK_SHIFT, 0, 0, 0)
    try:
        for _ in range(abs(steps)):
            delta_x = ROTATION_DRAG_PIXELS if steps > 0 else -ROTATION_DRAG_PIXELS
            user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            user32.mouse_event(MOUSEEVENTF_MOVE, delta_x, 0, 0, 0)
            user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    finally:
        user32.keybd_event(VK_SHIFT, 0, KEYEVENTF_KEYUP, 0)


class CursorController:
    def __init__(self):
        self.current_mode = "default"

    def set_mode(self, mode):
        if mode == self.current_mode:
            return

        cursor_id = CURSOR_BY_MODE.get(mode)
        if cursor_id is None:
            self.restore()
            return

        cursor = user32.LoadCursorW(0, cursor_id)
        cursor_copy = user32.CopyImage(cursor, IMAGE_CURSOR, 0, 0, 0)
        if cursor_copy:
            user32.SetSystemCursor(cursor_copy, OCR_NORMAL)
            self.current_mode = mode

    def restore(self):
        user32.SystemParametersInfoW(SPI_SETCURSORS, 0, None, 0)
        self.current_mode = "default"


HINSTANCE = wintypes.HANDLE
HICON = wintypes.HANDLE
HCURSOR = wintypes.HANDLE
HBRUSH = wintypes.HANDLE
LRESULT = wintypes.LPARAM


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", HICON),
        ("szTip", ctypes.c_wchar * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", ctypes.c_wchar * 256),
        ("uTimeoutOrVersion", wintypes.UINT),
        ("szInfoTitle", ctypes.c_wchar * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", ctypes.c_byte * 16),
        ("hBalloonIcon", HICON),
    ]


WNDPROC = ctypes.WINFUNCTYPE(
    LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", HINSTANCE),
        ("hIcon", HICON),
        ("hCursor", HCURSOR),
        ("hbrBackground", HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", wintypes.POINT),
        ("lPrivate", wintypes.DWORD),
    ]


user32.DefWindowProcW.argtypes = [
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
]
user32.DefWindowProcW.restype = LRESULT
kernel32_mutex.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
kernel32_mutex.CreateMutexW.restype = wintypes.HANDLE


class TrayIconManager:
    EXIT_COMMAND_ID = 1001
    CAMERA_COMMAND_ID = 1002

    def __init__(self, root_dir):
        self.root_dir = Path(root_dir)
        self.class_name = "VRHandControllerTrayIcon"
        self.hinstance = kernel32.GetModuleHandleW(None)
        self.hwnd = None
        self.hicon = None
        self._nid = None
        self._thread = None
        self._ready = threading.Event()
        self._wndproc = None
        self._exit_requested = threading.Event()
        self._camera_toggle_requested = threading.Event()
        self._state_lock = threading.Lock()
        self._camera_enabled = True

    def _find_icon_path(self):
        icon_path = self.root_dir / "icon.ico"
        return icon_path if icon_path.exists() else None

    def _load_icon(self):
        icon_path = self._find_icon_path()
        if icon_path is not None:
            icon = user32.LoadImageW(
                None,
                str(icon_path),
                IMAGE_ICON,
                0,
                0,
                LR_LOADFROMFILE | LR_DEFAULTSIZE,
            )
            if icon:
                return icon
        return user32.LoadIconW(None, IDI_APPLICATION)

    def _create_notify_icon(self):
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self.hwnd
        nid.uID = 1
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = WM_APP_TRAY
        nid.hIcon = self.hicon
        nid.szTip = "VR Hand Controller"
        shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))
        self._nid = nid

    def _show_context_menu(self):
        if not self.hwnd:
            return

        menu_handle = user32.CreatePopupMenu()
        if not menu_handle:
            return

        try:
            with self._state_lock:
                camera_enabled = self._camera_enabled
            camera_label = "Dezactiveaza camera" if camera_enabled else "Activeaza camera"
            user32.AppendMenuW(menu_handle, MF_STRING | MF_GRAYED, 0, "Fotache Vasile")
            user32.AppendMenuW(menu_handle, MF_STRING, self.CAMERA_COMMAND_ID, camera_label)
            user32.AppendMenuW(menu_handle, MF_STRING, self.EXIT_COMMAND_ID, "EXIT")
            cursor_pos = wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(cursor_pos))
            user32.SetForegroundWindow(self.hwnd)
            command = user32.TrackPopupMenu(
                menu_handle,
                TPM_RETURNCMD | TPM_NONOTIFY,
                cursor_pos.x,
                cursor_pos.y,
                0,
                self.hwnd,
                None,
            )
            if command == self.EXIT_COMMAND_ID:
                self._exit_requested.set()
            elif command == self.CAMERA_COMMAND_ID:
                self._camera_toggle_requested.set()
        finally:
            user32.DestroyMenu(menu_handle)

    def _run(self):
        @WNDPROC
        def window_proc(hwnd, message, wparam, lparam):
            if message == WM_APP_TRAY and lparam == WM_LBUTTONDBLCLK:
                show_console()
                return 0
            if message == WM_APP_TRAY and lparam == WM_RBUTTONUP:
                self._show_context_menu()
                return 0
            if message == WM_CLOSE:
                if self._nid is not None:
                    shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._nid))
                    self._nid = None
                user32.DestroyWindow(hwnd)
                return 0
            if message == WM_DESTROY:
                user32.PostQuitMessage(0)
                return 0
            return user32.DefWindowProcW(hwnd, message, wparam, lparam)

        self._wndproc = window_proc
        window_class = WNDCLASSW()
        window_class.lpfnWndProc = self._wndproc
        window_class.hInstance = self.hinstance
        window_class.lpszClassName = self.class_name
        user32.RegisterClassW(ctypes.byref(window_class))

        self.hwnd = user32.CreateWindowExW(
            0,
            self.class_name,
            self.class_name,
            0,
            0,
            0,
            0,
            0,
            None,
            None,
            self.hinstance,
            None,
        )
        self.hicon = self._load_icon()
        if self.hwnd:
            self._create_notify_icon()
        self._ready.set()

        message = MSG()
        while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(message))
            user32.DispatchMessageW(ctypes.byref(message))

    def start(self):
        self._thread = threading.Thread(target=self._run, name="tray-icon", daemon=True)
        self._thread.start()
        self._ready.wait(timeout=3.0)
        return self.hwnd is not None

    def consume_exit_request(self):
        if not self._exit_requested.is_set():
            return False
        self._exit_requested.clear()
        return True

    def consume_camera_toggle_request(self):
        if not self._camera_toggle_requested.is_set():
            return False
        self._camera_toggle_requested.clear()
        return True

    def set_camera_enabled(self, enabled):
        with self._state_lock:
            self._camera_enabled = enabled

    def show_balloon(self, title, message):
        if self._nid is None:
            return
        nid = NOTIFYICONDATAW()
        ctypes.memmove(ctypes.byref(nid), ctypes.byref(self._nid), ctypes.sizeof(NOTIFYICONDATAW))
        nid.uFlags = NIF_INFO
        nid.szInfoTitle = title
        nid.szInfo = message
        nid.dwInfoFlags = NIIF_INFO
        shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))

    def show_emulation_status(self, enabled, hint=None):
        message = "Activ" if enabled else "Dezactivat"
        if hint:
            message = f"{message}\n{hint}"
        self.show_balloon("VR Hand Controller", message)

    def stop(self):
        self._exit_requested.clear()
        self._camera_toggle_requested.clear()
        if self.hwnd:
            user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None


@dataclass
class HandSample:
    raw_label: str
    confidence: float
    wrist: tuple
    thumb_tip: tuple
    index_tip: tuple
    middle_tip: tuple
    ring_tip: tuple
    pinky_tip: tuple
    thumb_ip: tuple
    index_pip: tuple
    middle_pip: tuple
    ring_pip: tuple
    pinky_pip: tuple
    index_mcp: tuple
    middle_mcp: tuple
    pinky_mcp: tuple
    hand_scale: float
    pinch_ratio: float
    zoom_pinch_ratio: float
    right_click_ratio: float
    scroll_ratio: float
    thumb_extended: bool
    index_extended: bool
    middle_extended: bool
    ring_extended: bool
    pinky_extended: bool
    open_palm: bool
    fist_closed: bool
    extended_count: int
    rotation_angle: float
    center_x: float
    slot: str = "Unknown"


@dataclass
class HoldTimer:
    started_at: float = 0.0
    active: bool = False

    def update(self, condition, now, threshold):
        if condition:
            if not self.active:
                self.active = True
                self.started_at = now
                return False
            return now - self.started_at >= threshold

        self.reset()
        return False

    def reset(self):
        self.started_at = 0.0
        self.active = False

    def elapsed(self, now):
        if not self.active:
            return 0.0
        return now - self.started_at


class RuntimeContext:
    def __init__(self, cursor_controller):
        self.cursor_controller = cursor_controller
        self.left_button_down = False
        self.preview_enabled = False
        self.tray_manager = None
        self.instance_mutex = None

    def release_left_button(self):
        if self.left_button_down:
            set_left_button(False)
            self.left_button_down = False

    def cleanup(self):
        self.release_left_button()
        if self.tray_manager is not None:
            self.tray_manager.stop()
            self.tray_manager = None
        if self.instance_mutex is not None:
            kernel32.CloseHandle(self.instance_mutex)
            self.instance_mutex = None
        self.cursor_controller.restore()
        if self.preview_enabled:
            cv2.destroyAllWindows()


class CalibrationOverlay:
    TARGETS = ("top_left", "top_right", "bottom_left", "bottom_right", "center")

    def __init__(self, screen_width, screen_height):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.root = tk.Tk()
        self.root.title("VR Calibration")
        self.root.configure(bg="#0f172a")
        self.root.geometry(f"{self.screen_width}x{self.screen_height}+0+0")
        self.root.attributes("-topmost", True)
        self.root.overrideredirect(True)
        self.root.resizable(False, False)
        self.exit_requested = False
        self.root.protocol("WM_DELETE_WINDOW", self.request_exit)
        self.root.bind("<Escape>", lambda _event: self.request_exit())

        self.status_var = tk.StringVar(
            value="Calibrare: muta cursorul cu mana si da click pe fiecare tinta."
        )
        self.status_label = tk.Label(
            self.root,
            textvariable=self.status_var,
            font=("Segoe UI", 24, "bold"),
            fg="#e5e7eb",
            bg="#0f172a",
            pady=24,
        )
        self.status_label.pack(side="top", fill="x")
        self.instructions_label = tk.Label(
            self.root,
            text="Dupa calibrare apare o fereastra separata cu ghidul gesturilor.",
            font=("Segoe UI", 13, "bold"),
            fg="#cbd5e1",
            bg="#0f172a",
            justify="center",
            padx=36,
            pady=8,
        )
        self.instructions_label.pack(side="top", fill="x")
        self.exit_button = tk.Button(
            self.root,
            text="EXIT",
            font=("Segoe UI", 13, "bold"),
            bg="#b91c1c",
            fg="white",
            activebackground="#991b1b",
            activeforeground="white",
            relief="raised",
            bd=4,
            padx=18,
            pady=8,
            command=self.request_exit,
        )
        self.exit_button.pack(side="bottom", pady=(8, 18))

        self.latest_hand_point = None
        self.samples = {}
        self.completed = False
        self.buttons = {}

        labels = {
            "top_left": "Stanga\nsus",
            "top_right": "Dreapta\nsus",
            "bottom_left": "Stanga\njos",
            "bottom_right": "Dreapta\njos",
            "center": "Centru",
        }

        for target_id in self.TARGETS:
            button = tk.Button(
                self.root,
                text=labels[target_id],
                font=("Segoe UI", 18, "bold"),
                width=10,
                height=3,
                bg="#2563eb",
                fg="white",
                activebackground="#1d4ed8",
                activeforeground="white",
                relief="raised",
                bd=4,
                command=lambda current=target_id: self._register_click(current),
            )
            self.buttons[target_id] = button

        user32.SetWindowPos(
            self.root.winfo_id(),
            HWND_TOPMOST,
            0,
            0,
            self.screen_width,
            self.screen_height,
            SWP_SHOWWINDOW,
        )
        self.root.update_idletasks()
        header_height = self.status_label.winfo_height() + self.instructions_label.winfo_height()
        footer_height = self.exit_button.winfo_height() + 26
        usable_height = max(1, self.screen_height - header_height - footer_height)
        sample_button = next(iter(self.buttons.values()))
        button_half_width = max(60, sample_button.winfo_reqwidth() // 2)
        button_half_height = max(35, sample_button.winfo_reqheight() // 2)
        margin_x = max(button_half_width + 24, int(self.screen_width * 0.08))
        margin_y = max(button_half_height + 24, int(usable_height * 0.10))
        y_offset = header_height
        positions = {
            "top_left": (margin_x, y_offset + margin_y),
            "top_right": (self.screen_width - margin_x, y_offset + margin_y),
            "bottom_left": (margin_x, y_offset + usable_height - margin_y),
            "bottom_right": (self.screen_width - margin_x, y_offset + usable_height - margin_y),
            "center": (self.screen_width // 2, y_offset + (usable_height // 2)),
        }
        for target_id, (x_pos, y_pos) in positions.items():
            self.buttons[target_id].place(x=x_pos, y=y_pos, anchor="center")
        self.root.update()
        self.root.focus_force()

    def request_exit(self):
        self.exit_requested = True
        self.close()

    def _register_click(self, target_id):
        if self.completed or target_id in self.samples or self.latest_hand_point is None:
            return

        self.samples[target_id] = self.latest_hand_point
        self.buttons[target_id].configure(text="OK", state="disabled", bg="#16a34a")
        remaining = len(self.TARGETS) - len(self.samples)
        if remaining == 0:
            self.completed = True
            self.status_var.set("Calibrare finalizata. Se aplica noile limite.")
        else:
            self.status_var.set(f"Calibrare: au ramas {remaining} tinte.")

    def update(self):
        try:
            self.root.update_idletasks()
            self.root.update()
            return True
        except tk.TclError:
            return False

    def build_bounds(self):
        if not self.completed:
            return None

        left_bound = (self.samples["top_left"][0] + self.samples["bottom_left"][0]) / 2
        right_bound = (self.samples["top_right"][0] + self.samples["bottom_right"][0]) / 2
        top_bound = (self.samples["top_left"][1] + self.samples["top_right"][1]) / 2
        bottom_bound = (self.samples["bottom_left"][1] + self.samples["bottom_right"][1]) / 2
        center_x, center_y = self.samples["center"]

        left_bound = min(left_bound, center_x)
        right_bound = max(right_bound, center_x)
        top_bound = min(top_bound, center_y)
        bottom_bound = max(bottom_bound, center_y)

        return {
            "x_min": left_bound,
            "x_max": right_bound,
            "y_min": top_bound,
            "y_max": bottom_bound,
        }

    def close(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass


class GestureGuideOverlay:
    def __init__(self, screen_width, screen_height):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.closed = False
        self.root = tk.Tk()
        self.root.title("VR Gesture Guide")
        self.root.configure(bg="#0f172a")
        width = min(1320, max(980, self.screen_width - 160))
        height = min(430, max(360, self.screen_height - 240))
        pos_x = max(0, (self.screen_width - width) // 2)
        pos_y = max(0, (self.screen_height - height) // 2)
        self.root.geometry(f"{width}x{height}+{pos_x}+{pos_y}")
        self.root.attributes("-topmost", True)
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.bind("<Escape>", lambda _event: self.close())

        title_label = tk.Label(
            self.root,
            text="Ghid gesturi",
            font=("Segoe UI", 24, "bold"),
            fg="#e5e7eb",
            bg="#0f172a",
            pady=12,
        )
        title_label.pack(side="top", fill="x")
        subtitle_label = tk.Label(
            self.root,
            text="Verifica gesturile de mai jos, apoi apasa 'Am inteles' pentru a continua.",
            font=("Segoe UI", 12, "bold"),
            fg="#cbd5e1",
            bg="#0f172a",
            pady=4,
        )
        subtitle_label.pack(side="top", fill="x")

        gesture_frame = tk.Frame(self.root, bg="#0f172a")
        gesture_frame.pack(side="top", fill="x", padx=24, pady=(8, 10))
        gesture_cards = (
            (
                "Click / Drag",
                "Aratatorul misca cursorul.\nMare + aratator = click sau drag.",
                self._draw_click_gesture,
            ),
            (
                "Triunghi",
                "Cu ambele maini:\nactiveaza sau dezactiveaza emularea.",
                self._draw_triangle_gesture,
            ),
            (
                "Scroll",
                "Mare + mijlociu dreapta:\nmisca mana sus/jos pentru wheel.",
                self._draw_scroll_gesture,
            ),
            (
                "3D / Zoom",
                "Mare + inelar pe ambele maini:\nintri in modul 3D / zoom.",
                self._draw_zoom_gesture,
            ),
        )
        for index, (title, description, draw_callback) in enumerate(gesture_cards):
            card = self._create_gesture_card(gesture_frame, title, description, draw_callback)
            card.grid(row=0, column=index, padx=10, sticky="nsew")
            gesture_frame.grid_columnconfigure(index, weight=1)

        close_button = tk.Button(
            self.root,
            text="Am inteles",
            font=("Segoe UI", 12, "bold"),
            bg="#2563eb",
            fg="white",
            activebackground="#1d4ed8",
            activeforeground="white",
            relief="raised",
            bd=3,
            padx=18,
            pady=8,
            command=self.close,
        )
        close_button.pack(side="bottom", pady=(6, 16))
        self.root.update()
        self.root.focus_force()

    def _create_gesture_card(self, parent, title, description, draw_callback):
        card = tk.Frame(parent, bg="#111827", bd=1, relief="solid", padx=10, pady=8)
        title_label = tk.Label(card, text=title, font=("Segoe UI", 12, "bold"), fg="#f8fafc", bg="#111827")
        title_label.pack()
        canvas = tk.Canvas(card, width=180, height=76, bg="#1e293b", highlightthickness=0)
        canvas.pack(pady=6)
        draw_callback(canvas)
        description_label = tk.Label(
            card,
            text=description,
            font=("Segoe UI", 10, "bold"),
            fg="#cbd5e1",
            bg="#111827",
            justify="center",
        )
        description_label.pack()
        return card

    def _draw_hand(self, canvas, center_x, center_y, mirror=False, highlights=None, accent="#fbbf24"):
        highlights = set(highlights or ())
        direction = -1 if mirror else 1
        palm_color = "#475569"
        default_color = "#94a3b8"
        wrist = (center_x, center_y + 16)
        palm_top = (center_x, center_y + 2)
        canvas.create_oval(center_x - 14, center_y - 4, center_x + 14, center_y + 24, fill=palm_color, outline="")
        finger_positions = {
            "thumb": (center_x + direction * 24, center_y + 4),
            "index": (center_x + direction * 12, center_y - 20),
            "middle": (center_x + direction * 3, center_y - 26),
            "ring": (center_x - direction * 6, center_y - 22),
            "pinky": (center_x - direction * 14, center_y - 12),
        }
        for finger_name, tip in finger_positions.items():
            color = accent if finger_name in highlights else default_color
            canvas.create_line(palm_top[0], palm_top[1], tip[0], tip[1], fill=color, width=4, smooth=True)
            canvas.create_oval(tip[0] - 6, tip[1] - 6, tip[0] + 6, tip[1] + 6, fill=color, outline="")
        canvas.create_line(wrist[0], wrist[1], wrist[0], wrist[1] + 10, fill=default_color, width=4)
        return finger_positions

    def _draw_click_gesture(self, canvas):
        fingers = self._draw_hand(canvas, 62, 34, highlights=("thumb", "index"), accent="#fbbf24")
        canvas.create_line(fingers["thumb"][0], fingers["thumb"][1], fingers["index"][0], fingers["index"][1], fill="#fbbf24", width=3, dash=(3, 2))
        canvas.create_line(132, 18, 132, 56, fill="#34d399", width=4, arrow="last")
        canvas.create_rectangle(118, 58, 146, 66, fill="#34d399", outline="")

    def _draw_triangle_gesture(self, canvas):
        left_fingers = self._draw_hand(canvas, 52, 34, highlights=("thumb", "index"), accent="#f87171")
        right_fingers = self._draw_hand(canvas, 128, 34, mirror=True, highlights=("thumb", "index"), accent="#60a5fa")
        canvas.create_line(left_fingers["thumb"][0], left_fingers["thumb"][1], right_fingers["thumb"][0], right_fingers["thumb"][1], fill="#f8fafc", width=3)
        canvas.create_line(left_fingers["index"][0], left_fingers["index"][1], right_fingers["index"][0], right_fingers["index"][1], fill="#f8fafc", width=3)

    def _draw_scroll_gesture(self, canvas):
        fingers = self._draw_hand(canvas, 62, 34, highlights=("thumb", "middle"), accent="#c084fc")
        canvas.create_line(fingers["thumb"][0], fingers["thumb"][1], fingers["middle"][0], fingers["middle"][1], fill="#c084fc", width=3, dash=(3, 2))
        canvas.create_line(138, 18, 138, 58, fill="#22d3ee", width=4, arrow="both")

    def _draw_zoom_gesture(self, canvas):
        left_fingers = self._draw_hand(canvas, 52, 34, highlights=("thumb", "ring"), accent="#4ade80")
        right_fingers = self._draw_hand(canvas, 128, 34, mirror=True, highlights=("thumb", "ring"), accent="#fb7185")
        canvas.create_line(left_fingers["thumb"][0], left_fingers["thumb"][1], left_fingers["ring"][0], left_fingers["ring"][1], fill="#4ade80", width=3, dash=(3, 2))
        canvas.create_line(right_fingers["thumb"][0], right_fingers["thumb"][1], right_fingers["ring"][0], right_fingers["ring"][1], fill="#fb7185", width=3, dash=(3, 2))
        canvas.create_line(84, 24, 96, 24, fill="#f8fafc", width=3, arrow="both")

    def update(self):
        try:
            self.root.update_idletasks()
            self.root.update()
            return not self.closed
        except tk.TclError:
            self.closed = True
            return False

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            self.root.destroy()
        except tk.TclError:
            pass


def register_cleanup_handlers(runtime_context):
    global _cleanup_ref, _runtime_for_cleanup
    _runtime_for_cleanup = runtime_context

    def cleanup(*_args):
        if _runtime_for_cleanup is not None:
            _runtime_for_cleanup.cleanup()

    atexit.register(cleanup)
    for signal_name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        sig = getattr(signal, signal_name, None)
        if sig is not None:
            signal.signal(sig, lambda *_args: cleanup())

    handler_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_uint)

    @handler_type
    def console_handler(_ctrl_type):
        cleanup()
        return False

    _cleanup_ref = console_handler
    kernel32.SetConsoleCtrlHandler(_cleanup_ref, True)


def set_process_dpi_aware():
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass


def landmark_tuple(landmarks, index):
    point = landmarks[index]
    return (point.x, point.y)


def build_hand_samples(mp_hands, results):
    if not results.multi_hand_landmarks:
        return []

    samples = []
    for index, hand_landmarks in enumerate(results.multi_hand_landmarks):
        landmarks = hand_landmarks.landmark
        wrist = landmark_tuple(landmarks, mp_hands.HandLandmark.WRIST)
        thumb_tip = landmark_tuple(landmarks, mp_hands.HandLandmark.THUMB_TIP)
        thumb_ip = landmark_tuple(landmarks, mp_hands.HandLandmark.THUMB_IP)
        index_tip = landmark_tuple(landmarks, mp_hands.HandLandmark.INDEX_FINGER_TIP)
        index_pip = landmark_tuple(landmarks, mp_hands.HandLandmark.INDEX_FINGER_PIP)
        index_mcp = landmark_tuple(landmarks, mp_hands.HandLandmark.INDEX_FINGER_MCP)
        middle_tip = landmark_tuple(landmarks, mp_hands.HandLandmark.MIDDLE_FINGER_TIP)
        middle_pip = landmark_tuple(landmarks, mp_hands.HandLandmark.MIDDLE_FINGER_PIP)
        middle_mcp = landmark_tuple(landmarks, mp_hands.HandLandmark.MIDDLE_FINGER_MCP)
        ring_tip = landmark_tuple(landmarks, mp_hands.HandLandmark.RING_FINGER_TIP)
        ring_pip = landmark_tuple(landmarks, mp_hands.HandLandmark.RING_FINGER_PIP)
        pinky_tip = landmark_tuple(landmarks, mp_hands.HandLandmark.PINKY_TIP)
        pinky_pip = landmark_tuple(landmarks, mp_hands.HandLandmark.PINKY_PIP)
        pinky_mcp = landmark_tuple(landmarks, mp_hands.HandLandmark.PINKY_MCP)
        palm_width = point_distance(index_mcp, pinky_mcp)
        palm_height = point_distance(wrist, middle_mcp)
        hand_scale = max((palm_width + palm_height) / 2, 0.01)

        thumb_extended = point_distance(thumb_tip, index_mcp) / hand_scale >= 0.72
        index_extended = point_distance(index_tip, wrist) > point_distance(index_pip, wrist) * 1.10
        middle_extended = point_distance(middle_tip, wrist) > point_distance(middle_pip, wrist) * 1.10
        ring_extended = point_distance(ring_tip, wrist) > point_distance(ring_pip, wrist) * 1.10
        pinky_extended = point_distance(pinky_tip, wrist) > point_distance(pinky_pip, wrist) * 1.10
        extended_count = sum((index_extended, middle_extended, ring_extended, pinky_extended))
        classification = results.multi_handedness[index].classification[0]

        samples.append(
            HandSample(
                raw_label=classification.label,
                confidence=classification.score,
                wrist=wrist,
                thumb_tip=thumb_tip,
                index_tip=index_tip,
                middle_tip=middle_tip,
                ring_tip=ring_tip,
                pinky_tip=pinky_tip,
                thumb_ip=thumb_ip,
                index_pip=index_pip,
                middle_pip=middle_pip,
                ring_pip=ring_pip,
                pinky_pip=pinky_pip,
                index_mcp=index_mcp,
                middle_mcp=middle_mcp,
                pinky_mcp=pinky_mcp,
                hand_scale=hand_scale,
                pinch_ratio=point_distance(thumb_tip, index_tip) / hand_scale,
                zoom_pinch_ratio=point_distance(thumb_tip, ring_tip) / hand_scale,
                right_click_ratio=point_distance(thumb_tip, pinky_tip) / hand_scale,
                scroll_ratio=point_distance(thumb_tip, middle_tip) / hand_scale,
                thumb_extended=thumb_extended,
                index_extended=index_extended,
                middle_extended=middle_extended,
                ring_extended=ring_extended,
                pinky_extended=pinky_extended,
                open_palm=thumb_extended and index_extended and middle_extended and ring_extended and pinky_extended,
                fist_closed=extended_count <= 1,
                extended_count=extended_count,
                rotation_angle=math.atan2(index_mcp[1] - wrist[1], index_mcp[0] - wrist[0]),
                center_x=(wrist[0] + index_mcp[0] + pinky_mcp[0]) / 3,
            )
        )

    return samples


def assign_hand_slots(samples, previous_slots):
    if not samples:
        return {}

    samples = list(samples)
    if len(samples) == 1:
        sample = samples[0]
        if sample.raw_label in ("Left", "Right"):
            sample.slot = sample.raw_label
        elif previous_slots:
            sample.slot = min(previous_slots, key=lambda key: point_distance(sample.wrist, previous_slots[key]))
        else:
            sample.slot = "Right" if sample.center_x >= 0.5 else "Left"
        return {sample.slot: sample}

    if len(samples) >= 2 and "Left" in previous_slots and "Right" in previous_slots:
        first = samples[0]
        second = samples[1]
        direct_cost = point_distance(first.wrist, previous_slots["Left"]) + point_distance(second.wrist, previous_slots["Right"])
        crossed_cost = point_distance(first.wrist, previous_slots["Right"]) + point_distance(second.wrist, previous_slots["Left"])
        if direct_cost <= crossed_cost:
            first.slot = "Left"
            second.slot = "Right"
        else:
            first.slot = "Right"
            second.slot = "Left"
        return {first.slot: first, second.slot: second}

    left_sample = next((sample for sample in samples if sample.raw_label == "Left"), None)
    right_sample = next((sample for sample in samples if sample.raw_label == "Right"), None)
    if left_sample is not None and right_sample is not None and left_sample is not right_sample:
        left_sample.slot = "Left"
        right_sample.slot = "Right"
        return {"Left": left_sample, "Right": right_sample}

    ordered = sorted(samples, key=lambda sample: sample.center_x)
    ordered[0].slot = "Left"
    ordered[-1].slot = "Right"
    return {"Left": ordered[0], "Right": ordered[-1]}


def detect_triangle_toggle(hands):
    if len(hands) < 2:
        return False

    first_hand = hands[0]
    second_hand = hands[1]
    average_scale = max((first_hand.hand_scale + second_hand.hand_scale) / 2, 0.01)
    thumb_touch_ratio = point_distance(first_hand.thumb_tip, second_hand.thumb_tip) / average_scale
    index_touch_ratio = point_distance(first_hand.index_tip, second_hand.index_tip) / average_scale
    wrist_distance_ratio = point_distance(first_hand.wrist, second_hand.wrist) / average_scale
    fingers_ready = all(
        hand.index_extended and hand.middle_extended and hand.extended_count >= 2
        for hand in (first_hand, second_hand)
    )

    return (
        fingers_ready
        and first_hand.slot != second_hand.slot
        and thumb_touch_ratio <= TOGGLE_TOUCH_RATIO
        and index_touch_ratio <= TOGGLE_TOUCH_RATIO
        and wrist_distance_ratio >= TOGGLE_MIN_WRIST_RATIO
    )


def detect_exit_x(hands):
    if len(hands) < 2:
        return False

    first_hand = hands[0]
    second_hand = hands[1]
    average_scale = max((first_hand.hand_scale + second_hand.hand_scale) / 2, 0.01)
    wrist_distance_ratio = point_distance(first_hand.wrist, second_hand.wrist) / average_scale
    index_distance_ratio = point_distance(first_hand.index_tip, second_hand.index_tip) / average_scale
    fingers_ready = all(
        hand.index_extended and hand.middle_extended and hand.pinch_ratio >= PINCH_UP_RATIO
        for hand in (first_hand, second_hand)
    )

    return (
        fingers_ready
        and first_hand.slot != second_hand.slot
        and wrist_distance_ratio >= EXIT_X_MIN_SPAN_RATIO
        and index_distance_ratio >= EXIT_X_MIN_SPAN_RATIO
        and segments_intersect(first_hand.wrist, first_hand.index_tip, second_hand.wrist, second_hand.index_tip)
    )


def draw_debug_overlay(image, mode, status_text, emulation_enabled, slots, debug_metrics):
    overlay = image.copy()
    cv2.rectangle(overlay, (10, 10), (760, 230), (12, 18, 30), -1)
    cv2.addWeighted(overlay, 0.72, image, 0.28, 0, image)
    lines = [
        f"Mod: {mode}",
        f"Emulare: {'ON' if emulation_enabled else 'OFF'}",
        status_text,
    ]

    for slot_name in ("Left", "Right"):
        hand = slots.get(slot_name)
        if hand is None:
            lines.append(f"{slot_name}: lipsa")
        else:
                lines.append(
                f"{slot_name}: pinch={hand.pinch_ratio:.2f} right={hand.right_click_ratio:.2f} open={'da' if hand.open_palm else 'nu'} fist={'da' if hand.fist_closed else 'nu'} ext={hand.extended_count}"
            )

    if debug_metrics:
        lines.extend(debug_metrics)

    for index, line in enumerate(lines):
        cv2.putText(
            image,
            line,
            (24, 36 + index * 22),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (230, 230, 230),
            1,
        )


def present_frame(image, args, mode, status_text, emulation_enabled, slots, debug_metrics):
    if not args.debug_preview:
        return bool(user32.GetAsyncKeyState(VK_ESCAPE) & 0x8000)

    draw_debug_overlay(image, mode, status_text, emulation_enabled, slots, debug_metrics)
    cv2.imshow(WINDOW_TITLE, image)
    key = cv2.waitKey(1) & 0xFF
    return key == ord("q") or bool(user32.GetAsyncKeyState(VK_ESCAPE) & 0x8000)


def parse_args():
    parser = argparse.ArgumentParser(description="VR hand controller")
    parser.add_argument(
        "--debug-preview",
        action="store_true",
        help="Afiseaza preview OpenCV pentru diagnostic; implicit ruleaza headless.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    if not hasattr(mp, "solutions"):
        print(
            "Eroare: versiunea instalata de mediapipe nu expune API-ul legacy 'solutions'. "
            "Foloseste mediapipe 0.10.18 pentru acest script."
        )
        return

    set_process_dpi_aware()
    cursor_controller = CursorController()
    runtime_context = RuntimeContext(cursor_controller)
    instance_mutex, is_primary_instance = acquire_single_instance_mutex()
    if not is_primary_instance:
        if instance_mutex is not None:
            kernel32.CloseHandle(instance_mutex)
        message = "Aplicatia ruleaza deja. Inchide instanta existenta inainte sa o pornesti din nou."
        print(message)
        return
    runtime_context.instance_mutex = instance_mutex
    runtime_context.preview_enabled = args.debug_preview
    tray_manager = TrayIconManager(runtime_root())
    runtime_context.tray_manager = tray_manager
    register_cleanup_handlers(runtime_context)
    if tray_manager.start():
        hide_console()
    tray_manager.set_camera_enabled(True)

    screen_width = user32.GetSystemMetrics(0)
    screen_height = user32.GetSystemMetrics(1)
    mp_hands = mp.solutions.hands
    hands = mp_hands.Hands(
        static_image_mode=False,
        max_num_hands=2,
        model_complexity=0,
        min_detection_confidence=0.55,
        min_tracking_confidence=0.55,
    )

    def open_camera():
        capture = cv2.VideoCapture(0)
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        if capture.isOpened():
            return capture
        capture.release()
        return None

    cap = open_camera()
    if cap is None:
        print("Eroare: Nu s-a putut accesa camera web.")
        return

    camera_enabled = True
    emulation_enabled = False
    current_mode = "disabled"
    status_text = "Calibrare initiala in curs."
    smooth_x = screen_width / 2
    smooth_y = screen_height / 2
    prev_slot_positions = {}
    last_toggle_at = 0.0
    toggle_timer = HoldTimer()
    dual_enter_timer = HoldTimer()
    dual_exit_timer = HoldTimer()
    scroll_enter_timer = HoldTimer()
    exit_x_timer = HoldTimer()
    no_hands_timer = HoldTimer()
    right_click_ready = True
    pinch_active = False
    pinch_started_at = 0.0
    pinch_anchor_cursor = (smooth_x, smooth_y)
    last_tap_time = 0.0
    zoom_reference = None
    zoom_residual = 0.0
    rotation_reference = None
    rotation_residual = 0.0
    scroll_reference_y = None
    scroll_residual = 0.0
    two_hand_seen_at = None
    toggle_ready = True
    last_visible_count = 0
    calibration_overlay = CalibrationOverlay(screen_width, screen_height)
    gesture_guide_overlay = None
    calibration_bounds = None
    calibration_click_ready = True
    calibration_click_cooldown_until = 0.0

    print(
        "Pornire tracking rescris de la zero. Ruleaza headless implicit; foloseste --debug-preview doar pentru diagnostic."
    )
    print(
        "Calibrare initiala: foloseste mana pentru a muta cursorul si da click pe cele 5 tinte fullscreen."
    )

    def set_mode(new_mode):
        nonlocal current_mode
        if current_mode == new_mode:
            return

        if current_mode == "drag" and new_mode != "drag":
            runtime_context.release_left_button()

        if new_mode in ("disabled", "no_hands"):
            cursor_controller.restore()
        else:
            cursor_controller.set_mode(new_mode)

        current_mode = new_mode

    def close_calibration_overlay():
        nonlocal calibration_overlay
        if calibration_overlay is not None:
            calibration_overlay.close()
            calibration_overlay = None

    def close_gesture_guide_overlay():
        nonlocal gesture_guide_overlay
        if gesture_guide_overlay is not None:
            gesture_guide_overlay.close()
            gesture_guide_overlay = None

    def ensure_calibration_overlay():
        nonlocal calibration_overlay
        if calibration_overlay is None and calibration_bounds is None:
            calibration_overlay = CalibrationOverlay(screen_width, screen_height)

    def ensure_gesture_guide_overlay():
        nonlocal gesture_guide_overlay
        if gesture_guide_overlay is None:
            gesture_guide_overlay = GestureGuideOverlay(screen_width, screen_height)

    def reset_runtime_state():
        nonlocal prev_slot_positions, zoom_reference, zoom_residual, rotation_reference
        nonlocal rotation_residual, scroll_reference_y, scroll_residual, pinch_active
        nonlocal right_click_ready, two_hand_seen_at, last_visible_count, smooth_x, smooth_y
        nonlocal calibration_click_ready, calibration_click_cooldown_until

        prev_slot_positions = {}
        zoom_reference = None
        zoom_residual = 0.0
        rotation_reference = None
        rotation_residual = 0.0
        scroll_reference_y = None
        scroll_residual = 0.0
        pinch_active = False
        right_click_ready = True
        two_hand_seen_at = None
        last_visible_count = 0
        smooth_x = screen_width / 2
        smooth_y = screen_height / 2
        calibration_click_ready = True
        calibration_click_cooldown_until = 0.0
        toggle_timer.reset()
        dual_enter_timer.reset()
        dual_exit_timer.reset()
        scroll_enter_timer.reset()
        exit_x_timer.reset()
        no_hands_timer.reset()
        runtime_context.release_left_button()

    def disable_camera_runtime(reason_text, balloon_text):
        nonlocal camera_enabled, cap, emulation_enabled, status_text

        camera_enabled = False
        tray_manager.set_camera_enabled(False)
        if cap is not None:
            cap.release()
            cap = None
        close_calibration_overlay()
        close_gesture_guide_overlay()
        reset_runtime_state()
        emulation_enabled = False
        set_mode("disabled")
        status_text = reason_text
        print(reason_text)
        tray_manager.show_balloon("VR Hand Controller", balloon_text)

    try:
        while True:
            if runtime_context.tray_manager is not None and runtime_context.tray_manager.consume_exit_request():
                status_text = "EXIT din tray. Inchid aplicatia."
                print(status_text)
                break

            if runtime_context.tray_manager is not None and runtime_context.tray_manager.consume_camera_toggle_request():
                if camera_enabled:
                    disable_camera_runtime("Camera dezactivata din tray.", "Camera dezactivata.")
                else:
                    reopened_cap = open_camera()
                    if reopened_cap is None:
                        tray_manager.show_balloon("VR Hand Controller", "Nu am putut reactiva camera.")
                    else:
                        cap = reopened_cap
                        camera_enabled = True
                        tray_manager.set_camera_enabled(True)
                        reset_runtime_state()
                        ensure_calibration_overlay()
                        status_text = "Camera reactivata din tray."
                        print(status_text)
                        tray_manager.show_balloon("VR Hand Controller", "Camera activata.")

            if not camera_enabled:
                time.sleep(0.05)
                continue

            if gesture_guide_overlay is not None:
                if not gesture_guide_overlay.update():
                    close_gesture_guide_overlay()
                else:
                    time.sleep(0.05)
                    continue

            if cap is None or not cap.isOpened():
                cap = open_camera()
                if cap is None:
                    disable_camera_runtime(
                        "Camera indisponibila. Reactiv-o din tray cand revine.",
                        "Camera indisponibila. Foloseste tray pentru reactivare.",
                    )
                    continue

            success, image = cap.read()
            if not success:
                disable_camera_runtime(
                    "Citirea camerei a esuat. Camera a fost dezactivata.",
                    "Citirea camerei a esuat. Reactiv-o din tray.",
                )
                continue

            image = cv2.flip(image, 1)
            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            results = hands.process(image_rgb)
            raw_hands = build_hand_samples(mp_hands, results)
            slots = assign_hand_slots(raw_hands, prev_slot_positions)
            visible_hands = [sample for sample in (slots.get("Left"), slots.get("Right")) if sample is not None]
            visible_count = len(visible_hands)
            if visible_count != last_visible_count:
                dual_enter_timer.reset()
                dual_exit_timer.reset()
                no_hands_timer.reset()
                zoom_reference = None
                zoom_residual = 0.0
                rotation_reference = None
                rotation_residual = 0.0
                scroll_enter_timer.reset()
                exit_x_timer.reset()
                scroll_reference_y = None
                scroll_residual = 0.0
                if visible_count == 0:
                    prev_slot_positions = {}
                    pinch_active = False
                    right_click_ready = True
                    if current_mode in ("drag", "scroll", "three_d"):
                        set_mode("no_hands")
                last_visible_count = visible_count

            prev_slot_positions = {slot_name: sample.wrist for slot_name, sample in slots.items()}
            debug_metrics = []
            now = time.monotonic()

            if calibration_overlay is not None:
                if not calibration_overlay.update():
                    if calibration_overlay.exit_requested:
                        print("EXIT din calibrare. Inchid aplicatia.")
                    else:
                        print("Eroare: fereastra de calibrare s-a inchis.")
                    break
                if calibration_overlay.exit_requested:
                    print("EXIT din calibrare. Inchid aplicatia.")
                    break

                if not visible_hands:
                    pinch_active = False
                    status_text = "Calibrare: introdu mana in cadru si click pe tinta curenta."
                    if present_frame(image, args, "cursor", status_text, True, slots, debug_metrics):
                        break
                    continue

                primary_hand = slots.get("Right") or slots.get("Left") or visible_hands[0]
                target_x = map_normalized_to_screen(primary_hand.index_tip[0], screen_width - 1)
                target_y = map_normalized_to_screen(primary_hand.index_tip[1], screen_height - 1)
                if math.hypot(target_x - smooth_x, target_y - smooth_y) < CURSOR_DEADZONE and not pinch_active:
                    target_x = smooth_x
                    target_y = smooth_y

                smooth_x += (target_x - smooth_x) * MOVE_SMOOTHING
                smooth_y += (target_y - smooth_y) * MOVE_SMOOTHING
                move_cursor(smooth_x, smooth_y)
                calibration_overlay.latest_hand_point = primary_hand.index_tip
                set_mode("cursor")

                if primary_hand.pinch_ratio >= CALIBRATION_PINCH_UP_RATIO:
                    calibration_click_ready = True
                    pinch_active = False
                elif (
                    calibration_click_ready
                    and now >= calibration_click_cooldown_until
                    and primary_hand.pinch_ratio <= CALIBRATION_PINCH_DOWN_RATIO
                ):
                    click_left_button(double=False)
                    if calibration_overlay.exit_requested:
                        print("EXIT din calibrare. Inchid aplicatia.")
                        break
                    calibration_click_ready = False
                    calibration_click_cooldown_until = now + CALIBRATION_CLICK_COOLDOWN
                    pinch_active = True
                    status_text = "Calibrare: click pe tinta detectat."
                else:
                    status_text = "Calibrare: pinch scurt pentru click pe tinta."

                if calibration_overlay.completed:
                    calibration_bounds = calibration_overlay.build_bounds()
                    calibration_overlay.close()
                    calibration_overlay = None
                    ensure_gesture_guide_overlay()
                    runtime_context.release_left_button()
                    pinch_active = False
                    calibration_click_ready = True
                    emulation_enabled = False
                    set_mode("disabled")
                    status_text = "Calibrare terminata. Emularea este oprita; foloseste triunghiul pentru activare."
                    print(status_text)
                    if runtime_context.tray_manager is not None:
                        runtime_context.tray_manager.show_emulation_status(
                            False, "Pentru activare: gestul de triunghi."
                        )

                if present_frame(image, args, current_mode, status_text, emulation_enabled, slots, debug_metrics):
                    break
                continue

            if visible_count >= 2:
                if two_hand_seen_at is None:
                    two_hand_seen_at = now
            else:
                two_hand_seen_at = None

            triangle_active = detect_triangle_toggle(visible_hands)
            if not triangle_active:
                toggle_ready = True
                toggle_timer.reset()
            elif toggle_ready and now - last_toggle_at >= TOGGLE_COOLDOWN_SECONDS:
                if toggle_timer.update(True, now, TOGGLE_HOLD_SECONDS):
                    emulation_enabled = not emulation_enabled
                    last_toggle_at = now
                    toggle_ready = False
                    toggle_timer.reset()
                    dual_enter_timer.reset()
                    dual_exit_timer.reset()
                    no_hands_timer.reset()
                    pinch_active = False
                    zoom_reference = None
                    zoom_residual = 0.0
                    rotation_reference = None
                    rotation_residual = 0.0
                    scroll_enter_timer.reset()
                    exit_x_timer.reset()
                    scroll_reference_y = None
                    scroll_residual = 0.0
                    runtime_context.release_left_button()
                    if emulation_enabled:
                        set_mode("no_hands")
                        status_text = "Emulare mouse reactivata."
                    else:
                        set_mode("disabled")
                        status_text = "Emulare mouse dezactivata."
                    if runtime_context.tray_manager is not None:
                        runtime_context.tray_manager.show_emulation_status(emulation_enabled)
                    print(status_text)
            else:
                toggle_timer.reset()

            debug_metrics.append(f"triunghi={'da' if triangle_active else 'nu'}")

            if not emulation_enabled:
                exit_x_timer.reset()
                status_text = "Emulare dezactivata. Foloseste gestul de triunghi pentru reactivare."
                set_mode("disabled")
                if present_frame(image, args, current_mode, status_text, emulation_enabled, slots, debug_metrics):
                    break
                continue

            if not visible_hands:
                pinch_active = False
                right_click_ready = True
                dual_enter_timer.reset()
                scroll_enter_timer.reset()
                exit_x_timer.reset()
                zoom_reference = None
                rotation_reference = None
                scroll_reference_y = None
                if no_hands_timer.update(True, now, NO_HANDS_SECONDS):
                    set_mode("no_hands")

                if present_frame(image, args, current_mode, status_text, emulation_enabled, slots, debug_metrics):
                    break
                continue

            no_hands_timer.reset()
            primary_hand = slots.get("Right") or slots.get("Left") or visible_hands[0]
            right_hand = slots.get("Right")
            left_hand = slots.get("Left")
            two_hand_lock = len(visible_hands) >= 2 and two_hand_seen_at is not None and now - two_hand_seen_at < TWO_HAND_SUPPRESS_SECONDS

            dual_grab_candidate = (
                left_hand is not None
                and right_hand is not None
                and left_hand.zoom_pinch_ratio <= DUAL_GRAB_ENTER_RATIO
                and right_hand.zoom_pinch_ratio <= DUAL_GRAB_ENTER_RATIO
            )
            dual_grab_held = (
                left_hand is not None
                and right_hand is not None
                and left_hand.zoom_pinch_ratio <= DUAL_GRAB_EXIT_RATIO
                and right_hand.zoom_pinch_ratio <= DUAL_GRAB_EXIT_RATIO
            )
            debug_metrics.append(f"dual_grab={'da' if dual_grab_candidate else 'nu'}")

            scroll_candidate = (
                right_hand is not None
                and left_hand is None
                and right_hand.slot == "Right"
                and right_hand.scroll_ratio <= SCROLL_DOWN_RATIO
                and right_hand.pinch_ratio >= PINCH_UP_RATIO
                and not triangle_active
            )
            debug_metrics.append(f"scroll={'da' if scroll_candidate or current_mode == 'scroll' else 'nu'}")
            exit_x_active = not triangle_active and not dual_grab_candidate and detect_exit_x(visible_hands)
            debug_metrics.append(f"exit_x={'da' if exit_x_active else 'nu'}")

            if exit_x_timer.update(exit_x_active, now, EXIT_X_HOLD_SECONDS):
                status_text = "Gest X detectat. Inchid aplicatia."
                print(status_text)
                break
            if not exit_x_active:
                exit_x_timer.reset()

            if current_mode == "three_d" and (left_hand is None or right_hand is None):
                set_mode("cursor")
                zoom_reference = None
                zoom_residual = 0.0
                rotation_reference = None
                rotation_residual = 0.0
                dual_exit_timer.reset()

            if current_mode == "three_d":
                if dual_exit_timer.update(not dual_grab_held, now, DUAL_RELEASE_SECONDS):
                    set_mode("cursor")
                    status_text = "Iesire din modul 3D."
                    zoom_reference = None
                    zoom_residual = 0.0
                    rotation_reference = None
                    rotation_residual = 0.0
                    dual_exit_timer.reset()
                else:
                    if dual_grab_held:
                        dual_exit_timer.reset()
                    if left_hand is not None and right_hand is not None:
                        distance_now = point_distance(left_hand.index_tip, right_hand.index_tip)
                        if zoom_reference is not None:
                            zoom_residual += distance_now - zoom_reference
                            zoom_steps = 0
                            while zoom_residual >= ZOOM_TRIGGER_DELTA:
                                zoom_steps += 1
                                zoom_residual -= ZOOM_TRIGGER_DELTA
                            while zoom_residual <= -ZOOM_TRIGGER_DELTA:
                                zoom_steps -= 1
                                zoom_residual += ZOOM_TRIGGER_DELTA
                            if zoom_steps:
                                send_zoom(zoom_steps)

                        if rotation_reference is not None:
                            rotation_residual += wrap_angle_delta(right_hand.rotation_angle - rotation_reference)
                            rotation_steps = 0
                            while rotation_residual >= ROTATION_TRIGGER_DELTA:
                                rotation_steps += 1
                                rotation_residual -= ROTATION_TRIGGER_DELTA
                            while rotation_residual <= -ROTATION_TRIGGER_DELTA:
                                rotation_steps -= 1
                                rotation_residual += ROTATION_TRIGGER_DELTA
                            if rotation_steps:
                                send_rotation_drag(rotation_steps)

                        zoom_reference = distance_now
                        rotation_reference = right_hand.rotation_angle
                    status_text = "Mod 3D: zoom din distanta mainilor, rotire din mana dreapta."

                if present_frame(image, args, current_mode, status_text, emulation_enabled, slots, debug_metrics):
                    break
                continue

            if current_mode == "scroll":
                if right_hand is None or left_hand is not None or right_hand.scroll_ratio >= SCROLL_UP_RATIO:
                    set_mode("cursor")
                    scroll_enter_timer.reset()
                    scroll_reference_y = None
                    scroll_residual = 0.0
                    status_text = "Scroll incheiat."
                else:
                    if scroll_reference_y is not None:
                        scroll_residual += scroll_reference_y - right_hand.wrist[1]
                        scroll_steps = 0
                        while scroll_residual >= SCROLL_TRIGGER_DELTA:
                            scroll_steps += 1
                            scroll_residual -= SCROLL_TRIGGER_DELTA
                        while scroll_residual <= -SCROLL_TRIGGER_DELTA:
                            scroll_steps -= 1
                            scroll_residual += SCROLL_TRIGGER_DELTA
                        if scroll_steps:
                            send_scroll(scroll_steps)
                    scroll_reference_y = right_hand.wrist[1]
                    status_text = "Scroll activ: misca mana dreapta sus/jos."

                if present_frame(image, args, current_mode, status_text, emulation_enabled, slots, debug_metrics):
                    break
                continue

            if dual_enter_timer.update(dual_grab_candidate and not triangle_active, now, DUAL_GRAB_HOLD_SECONDS):
                runtime_context.release_left_button()
                pinch_active = False
                right_click_ready = True
                zoom_reference = None
                zoom_residual = 0.0
                rotation_reference = None
                rotation_residual = 0.0
                set_mode("three_d")
                status_text = "Mod 3D activat."
                if present_frame(image, args, current_mode, status_text, emulation_enabled, slots, debug_metrics):
                    break
                continue
            if not dual_grab_candidate:
                dual_enter_timer.reset()

            if scroll_enter_timer.update(scroll_candidate, now, SCROLL_HOLD_SECONDS):
                runtime_context.release_left_button()
                pinch_active = False
                right_click_ready = False
                scroll_reference_y = right_hand.wrist[1]
                scroll_residual = 0.0
                set_mode("scroll")
                status_text = "Scroll activat."
                if present_frame(image, args, current_mode, status_text, emulation_enabled, slots, debug_metrics):
                    break
                continue
            if not scroll_candidate:
                scroll_enter_timer.reset()

            target_x = map_calibrated_to_screen(
                primary_hand.index_tip[0],
                screen_width - 1,
                calibration_bounds["x_min"] if calibration_bounds else None,
                calibration_bounds["x_max"] if calibration_bounds else None,
            )
            target_y = map_calibrated_to_screen(
                primary_hand.index_tip[1],
                screen_height - 1,
                calibration_bounds["y_min"] if calibration_bounds else None,
                calibration_bounds["y_max"] if calibration_bounds else None,
            )
            if math.hypot(target_x - smooth_x, target_y - smooth_y) < CURSOR_DEADZONE and not pinch_active:
                target_x = smooth_x
                target_y = smooth_y

            smooth_x += (target_x - smooth_x) * MOVE_SMOOTHING
            smooth_y += (target_y - smooth_y) * MOVE_SMOOTHING
            move_cursor(smooth_x, smooth_y)
            status_text = "Mouse activ: aratatorul muta cursorul."

            set_mode("drag" if current_mode == "drag" else "cursor")

            suppress_single_hand = triangle_active or dual_grab_candidate or scroll_candidate or two_hand_lock
            if current_mode == "drag":
                if primary_hand.pinch_ratio > PINCH_DOWN_RATIO:
                    runtime_context.release_left_button()
                    pinch_active = False
                    set_mode("cursor")
                    status_text = "Drag incheiat."
                else:
                    status_text = "Drag activ."
            elif not suppress_single_hand:
                pinch_move_ratio = point_distance(
                    (smooth_x / max(screen_width, 1), smooth_y / max(screen_height, 1)),
                    (pinch_anchor_cursor[0] / max(screen_width, 1), pinch_anchor_cursor[1] / max(screen_height, 1)),
                )
                if not pinch_active and primary_hand.pinch_ratio <= PINCH_DOWN_RATIO:
                    pinch_active = True
                    pinch_started_at = now
                    pinch_anchor_cursor = (smooth_x, smooth_y)
                    status_text = "Pinch detectat: astept click sau drag."
                elif pinch_active and primary_hand.pinch_ratio >= PINCH_UP_RATIO:
                    held_time = now - pinch_started_at
                    if held_time < PINCH_DRAG_SECONDS and pinch_move_ratio <= PINCH_TAP_MOVE_RATIO:
                        if now - last_tap_time <= DOUBLE_TAP_GAP:
                            click_left_button(double=True)
                            last_tap_time = 0.0
                            status_text = "Dublu click stanga."
                        else:
                            click_left_button(double=False)
                            last_tap_time = now
                            status_text = "Click stanga."
                    pinch_active = False
                elif pinch_active:
                    held_time = now - pinch_started_at
                    if held_time >= PINCH_DRAG_SECONDS or pinch_move_ratio >= PINCH_DRAG_MOVE_RATIO:
                        set_left_button(True)
                        runtime_context.left_button_down = True
                        set_mode("drag")
                        status_text = "Drag activat."
                else:
                    status_text = "Mouse activ: aratatorul muta cursorul."
            else:
                pinch_active = False

            if current_mode == "cursor" and right_hand is not None and primary_hand.slot == "Right" and not suppress_single_hand:
                if right_click_ready and not right_hand.fist_closed and right_hand.right_click_ratio <= RIGHT_CLICK_DOWN_RATIO:
                    click_right_button()
                    right_click_ready = False
                    status_text = "Click dreapta."
                elif not right_click_ready and right_hand.right_click_ratio >= RIGHT_CLICK_UP_RATIO:
                    right_click_ready = True
            else:
                right_click_ready = True

            if present_frame(image, args, current_mode, status_text, emulation_enabled, slots, debug_metrics):
                break
    finally:
        if calibration_overlay is not None:
            calibration_overlay.close()
        if gesture_guide_overlay is not None:
            gesture_guide_overlay.close()
        runtime_context.cleanup()
        if cap is not None:
            cap.release()


if __name__ == "__main__":
    main()
