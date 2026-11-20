"""Thin ctypes layer over the Win32 APIs GhostText needs."""
import ctypes
from ctypes import wintypes as wt

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

LRESULT = ctypes.c_ssize_t
ULONG_PTR = ctypes.c_size_t

# ---- constants -------------------------------------------------------------
WH_KEYBOARD_LL = 13
WH_MOUSE_LL = 14
WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x100, 0x101, 0x104, 0x105
WM_LBUTTONDOWN, WM_RBUTTONDOWN, WM_MBUTTONDOWN, WM_MOUSEWHEEL = 0x201, 0x204, 0x207, 0x20A
WM_APP = 0x8000
WM_QUIT = 0x12
WM_DESTROY = 0x02
LLKHF_INJECTED = 0x10

VK_BACK, VK_TAB, VK_RETURN = 0x08, 0x09, 0x0D
VK_SHIFT, VK_CONTROL, VK_MENU, VK_CAPITAL, VK_ESCAPE, VK_SPACE = 0x10, 0x11, 0x12, 0x14, 0x1B, 0x20
VK_PRIOR, VK_NEXT, VK_END, VK_HOME, VK_LEFT, VK_UP, VK_RIGHT, VK_DOWN = range(0x21, 0x29)
VK_DELETE = 0x2E
VK_LWIN, VK_RWIN = 0x5B, 0x5C
VK_LSHIFT, VK_RSHIFT, VK_LCONTROL, VK_RCONTROL, VK_LMENU, VK_RMENU = range(0xA0, 0xA6)
VK_PACKET = 0xE7

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x2
KEYEVENTF_UNICODE = 0x4

# Marker stamped on every event we inject so our own hook can ignore it.
GHOST_MAGIC = 0x47484F53

WS_POPUP = 0x80000000
WS_EX_TOPMOST = 0x8
WS_EX_TRANSPARENT = 0x20
WS_EX_TOOLWINDOW = 0x80
WS_EX_LAYERED = 0x80000
WS_EX_NOACTIVATE = 0x8000000
SW_HIDE, SW_SHOWNOACTIVATE = 0, 4
ULW_ALPHA = 2
AC_SRC_OVER, AC_SRC_ALPHA = 0, 1
HWND_TOPMOST = wt.HWND(-1)
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x1, 0x2, 0x10

GWL_STYLE = -16
ES_PASSWORD = 0x20
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
ERROR_ALREADY_EXISTS = 183


# ---- structures ------------------------------------------------------------
class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wt.DWORD), ("scanCode", wt.DWORD), ("flags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ULONG_PTR)]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("pt", wt.POINT), ("mouseData", wt.DWORD), ("flags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ULONG_PTR)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wt.LONG), ("dy", wt.LONG), ("mouseData", wt.DWORD),
                ("dwFlags", wt.DWORD), ("time", wt.DWORD), ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wt.DWORD), ("wParamL", wt.WORD), ("wParamH", wt.WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wt.DWORD), ("u", _INPUTUNION)]


class GUITHREADINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("flags", wt.DWORD), ("hwndActive", wt.HWND),
                ("hwndFocus", wt.HWND), ("hwndCapture", wt.HWND), ("hwndMenuOwner", wt.HWND),
                ("hwndMoveSize", wt.HWND), ("hwndCaret", wt.HWND), ("rcCaret", wt.RECT)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", ctypes.c_byte), ("BlendFlags", ctypes.c_byte),
                ("SourceConstantAlpha", ctypes.c_ubyte), ("AlphaFormat", ctypes.c_byte)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG),
                ("biPlanes", wt.WORD), ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
                ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", wt.LONG),
                ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD), ("biClrImportant", wt.DWORD)]


HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wt.WPARAM, wt.LPARAM)
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [("cbSize", wt.UINT), ("style", wt.UINT), ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                ("hInstance", wt.HINSTANCE), ("hIcon", wt.HICON), ("hCursor", wt.HANDLE),
                ("hbrBackground", wt.HBRUSH), ("lpszMenuName", wt.LPCWSTR),
                ("lpszClassName", wt.LPCWSTR), ("hIconSm", wt.HICON)]


# ---- prototypes ------------------------------------------------------------
def _proto(fn, res, *args):
    fn.restype = res
    fn.argtypes = list(args)
    return fn


SetWindowsHookExW = _proto(user32.SetWindowsHookExW, wt.HHOOK, ctypes.c_int, HOOKPROC, wt.HINSTANCE, wt.DWORD)
CallNextHookEx = _proto(user32.CallNextHookEx, LRESULT, wt.HHOOK, ctypes.c_int, wt.WPARAM, wt.LPARAM)
UnhookWindowsHookEx = _proto(user32.UnhookWindowsHookEx, wt.BOOL, wt.HHOOK)
GetMessageW = _proto(user32.GetMessageW, wt.BOOL, ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT)
TranslateMessage = _proto(user32.TranslateMessage, wt.BOOL, ctypes.POINTER(wt.MSG))
DispatchMessageW = _proto(user32.DispatchMessageW, LRESULT, ctypes.POINTER(wt.MSG))
PostMessageW = _proto(user32.PostMessageW, wt.BOOL, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)
PostThreadMessageW = _proto(user32.PostThreadMessageW, wt.BOOL, wt.DWORD, wt.UINT, wt.WPARAM, wt.LPARAM)
SendInput = _proto(user32.SendInput, wt.UINT, wt.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
GetAsyncKeyState = _proto(user32.GetAsyncKeyState, ctypes.c_short, ctypes.c_int)
GetKeyState = _proto(user32.GetKeyState, ctypes.c_short, ctypes.c_int)
ToUnicodeEx = _proto(user32.ToUnicodeEx, ctypes.c_int, wt.UINT, wt.UINT, ctypes.POINTER(ctypes.c_ubyte),
                     wt.LPWSTR, ctypes.c_int, wt.UINT, wt.HKL)
GetKeyboardLayout = _proto(user32.GetKeyboardLayout, wt.HKL, wt.DWORD)
GetForegroundWindow = _proto(user32.GetForegroundWindow, wt.HWND)
GetWindowThreadProcessId = _proto(user32.GetWindowThreadProcessId, wt.DWORD, wt.HWND, ctypes.POINTER(wt.DWORD))
GetGUIThreadInfo = _proto(user32.GetGUIThreadInfo, wt.BOOL, wt.DWORD, ctypes.POINTER(GUITHREADINFO))
ClientToScreen = _proto(user32.ClientToScreen, wt.BOOL, wt.HWND, ctypes.POINTER(wt.POINT))
GetWindowRect = _proto(user32.GetWindowRect, wt.BOOL, wt.HWND, ctypes.POINTER(wt.RECT))
GetClassNameW = _proto(user32.GetClassNameW, ctypes.c_int, wt.HWND, wt.LPWSTR, ctypes.c_int)
GetWindowLongW = _proto(user32.GetWindowLongW, wt.LONG, wt.HWND, ctypes.c_int)
GetCurrentThreadId = _proto(kernel32.GetCurrentThreadId, wt.DWORD)
GetModuleHandleW = _proto(kernel32.GetModuleHandleW, wt.HMODULE, wt.LPCWSTR)
OpenProcess = _proto(kernel32.OpenProcess, wt.HANDLE, wt.DWORD, wt.BOOL, wt.DWORD)
CloseHandle = _proto(kernel32.CloseHandle, wt.BOOL, wt.HANDLE)
QueryFullProcessImageNameW = _proto(kernel32.QueryFullProcessImageNameW, wt.BOOL, wt.HANDLE, wt.DWORD,
                                    wt.LPWSTR, ctypes.POINTER(wt.DWORD))
CreateMutexW = _proto(kernel32.CreateMutexW, wt.HANDLE, ctypes.c_void_p, wt.BOOL, wt.LPCWSTR)

RegisterClassExW = _proto(user32.RegisterClassExW, wt.ATOM, ctypes.POINTER(WNDCLASSEXW))
CreateWindowExW = _proto(user32.CreateWindowExW, wt.HWND, wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD,
                         ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                         wt.HWND, wt.HMENU, wt.HINSTANCE, ctypes.c_void_p)
DefWindowProcW = _proto(user32.DefWindowProcW, LRESULT, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)
ShowWindow = _proto(user32.ShowWindow, wt.BOOL, wt.HWND, ctypes.c_int)
SetWindowPos = _proto(user32.SetWindowPos, wt.BOOL, wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int,
                      ctypes.c_int, ctypes.c_int, wt.UINT)
UpdateLayeredWindow = _proto(user32.UpdateLayeredWindow, wt.BOOL, wt.HWND, wt.HDC, ctypes.POINTER(wt.POINT),
                             ctypes.POINTER(wt.SIZE), wt.HDC, ctypes.POINTER(wt.POINT), wt.COLORREF,
                             ctypes.POINTER(BLENDFUNCTION), wt.DWORD)
GetDC = _proto(user32.GetDC, wt.HDC, wt.HWND)
ReleaseDC = _proto(user32.ReleaseDC, ctypes.c_int, wt.HWND, wt.HDC)
CreateCompatibleDC = _proto(gdi32.CreateCompatibleDC, wt.HDC, wt.HDC)
DeleteDC = _proto(gdi32.DeleteDC, wt.BOOL, wt.HDC)
CreateDIBSection = _proto(gdi32.CreateDIBSection, wt.HBITMAP, wt.HDC, ctypes.POINTER(BITMAPINFOHEADER),
                          wt.UINT, ctypes.POINTER(ctypes.c_void_p), wt.HANDLE, wt.DWORD)
SelectObject = _proto(gdi32.SelectObject, wt.HGDIOBJ, wt.HDC, wt.HGDIOBJ)
DeleteObject = _proto(gdi32.DeleteObject, wt.BOOL, wt.HGDIOBJ)
GetDpiForWindow = _proto(user32.GetDpiForWindow, wt.UINT, wt.HWND)


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.UINT), ("dwTime", wt.DWORD)]


GetLastInputInfo = _proto(user32.GetLastInputInfo, wt.BOOL, ctypes.POINTER(LASTINPUTINFO))
GetTickCount = _proto(kernel32.GetTickCount, wt.DWORD)


def last_input_tick():
    lii = LASTINPUTINFO(cbSize=ctypes.sizeof(LASTINPUTINFO))
    GetLastInputInfo(ctypes.byref(lii))
    return lii.dwTime


def set_dpi_aware():
    try:
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # per-monitor v2
    except Exception:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass


def key_down(vk):
    return bool(GetAsyncKeyState(vk) & 0x8000)


def process_name(hwnd):
    """Executable name (e.g. 'chrome.exe') of the process that owns hwnd."""
    pid = wt.DWORD()
    GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    h = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wt.DWORD(1024)
        if QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return buf.value.rsplit("\\", 1)[-1]
        return ""
    finally:
        CloseHandle(h)


def class_name(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    GetClassNameW(hwnd, buf, 256)
    return buf.value


def gui_thread_info(hwnd=None):
    hwnd = hwnd or GetForegroundWindow()
    tid = GetWindowThreadProcessId(hwnd, None)
    gti = GUITHREADINFO(cbSize=ctypes.sizeof(GUITHREADINFO))
    if not GetGUIThreadInfo(tid, ctypes.byref(gti)):
        return None
    return gti


def _key_input(vk=0, scan=0, flags=0):
    inp = INPUT(type=INPUT_KEYBOARD)
    inp.ki = KEYBDINPUT(vk, scan, flags, 0, GHOST_MAGIC)
    return inp


def send_text(text, backspaces=0):
    """Type `text` into the focused app, optionally after `backspaces` Backspace presses."""
    events = []
    for _ in range(backspaces):
        events += [_key_input(VK_BACK), _key_input(VK_BACK, flags=KEYEVENTF_KEYUP)]
    for ch in text:
        if ch == "\n":
            events += [_key_input(VK_RETURN), _key_input(VK_RETURN, flags=KEYEVENTF_KEYUP)]
            continue
        units = ch.encode("utf-16-le")
        for i in range(0, len(units), 2):
            code = int.from_bytes(units[i:i + 2], "little")
            events += [_key_input(0, code, KEYEVENTF_UNICODE),
                       _key_input(0, code, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP)]
    if not events:
        return 0
    arr = (INPUT * len(events))(*events)
    return SendInput(len(events), arr, ctypes.sizeof(INPUT))


REPLAY_MAGIC = 0x47484F52  # keys we held back during an injection and now re-send
LLKHF_EXTENDED = 0x1
KEYEVENTF_EXTENDEDKEY = 0x1


def send_paced(text, backspaces=0, gap=0.004):
    """Like send_text, but one Backspace at a time: many apps (e.g. Win11 Notepad)
    drop Backspaces that arrive in a single batch."""
    import time
    for _ in range(backspaces):
        send_text("", backspaces=1)
        time.sleep(gap)
    if text:
        send_text(text)


def replay_key(vk, scan, up, extended):
    flags = (KEYEVENTF_KEYUP if up else 0) | (KEYEVENTF_EXTENDEDKEY if extended else 0)
    inp = INPUT(type=INPUT_KEYBOARD)
    inp.ki = KEYBDINPUT(vk, scan, flags, 0, REPLAY_MAGIC)
    SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def single_instance(name="Local\\GhostText.SingleInstance"):
    handle = CreateMutexW(None, False, name)
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        return None
    return handle
