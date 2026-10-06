# -*- coding: utf-8 -*-
"""
Win32 native WeChat RPA sender.
Features:
- 64-bit safe GlobalAlloc/SetClipboardData with CF_UNICODETEXT (Native Emoji & line break support)
- Windows Default Desktop attachment (penetrates background service / sandbox isolation)
- Automated search & switch to target chat (e.g. '文件传输助手') via Ctrl+F
- Focus positioning on chat input control
"""

import time
import ctypes
from typing import List, Callable, Optional
from dispatcher.renderer import RenderedPayload
from dispatcher.senders.base import BaseSender

# Windows Virtual Key Codes and flags
VK_CONTROL = 0x11
VK_V = 0x56
VK_F = 0x46
VK_RETURN = 0x0D
KEYEVENTF_KEYUP = 0x0002
SW_RESTORE = 9
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
CF_UNICODETEXT = 13

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# 64-bit explicit typing to prevent pointer truncation
kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = ctypes.c_void_p
kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
kernel32.GlobalUnlock.restype = ctypes.c_int

user32.OpenClipboard.argtypes = [ctypes.c_void_p]
user32.OpenClipboard.restype = ctypes.c_int
user32.CloseClipboard.argtypes = []
user32.CloseClipboard.restype = ctypes.c_int
user32.EmptyClipboard.argtypes = []
user32.EmptyClipboard.restype = ctypes.c_int
user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
user32.SetClipboardData.restype = ctypes.c_void_p


class RECT(ctypes.Structure):
    _fields_ = [
        ('left', ctypes.c_long),
        ('top', ctypes.c_long),
        ('right', ctypes.c_long),
        ('bottom', ctypes.c_long)
    ]


def attach_to_default_desktop():
    """挂载到当前 Windows 可见原生交互桌面"""
    try:
        h_default = user32.OpenDesktopW("Default", 0, False, 0x01FF)
        if h_default:
            user32.SetThreadDesktop(h_default)
            return h_default
    except Exception as e:
        print(f"attach_to_default_desktop error: {e}")
    return None


def set_clipboard_unicode(text: str) -> bool:
    """写入纯净 Unicode 文本到系统剪贴板"""
    attach_to_default_desktop()
    data = (text + '\0').encode('utf-16le')
    h_mem = kernel32.GlobalAlloc(0x0042, len(data))
    if not h_mem:
        return False
    ptr = kernel32.GlobalLock(h_mem)
    if not ptr:
        return False
    ctypes.memmove(ptr, data, len(data))
    kernel32.GlobalUnlock(h_mem)

    opened = False
    for _ in range(5):
        if user32.OpenClipboard(None):
            opened = True
            break
        time.sleep(0.05)
    if not opened:
        return False

    user32.EmptyClipboard()
    res = user32.SetClipboardData(CF_UNICODETEXT, h_mem)
    user32.CloseClipboard()
    return bool(res)


def find_wechat_hwnd():
    """查找微信 PC 端主窗口句柄"""
    attach_to_default_desktop()
    found = []

    def enum_cb(hwnd, lParam):
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls, 256)
        if cls.value == "WeChatMainWndForPC":
            found.append(hwnd)
        return True

    EnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
    user32.EnumWindows(EnumProc(enum_cb), 0)
    return found[0] if found else None


def simulate_paste():
    user32.keybd_event(VK_CONTROL, 0, 0, 0)
    time.sleep(0.05)
    user32.keybd_event(VK_V, 0, 0, 0)
    time.sleep(0.05)
    user32.keybd_event(VK_V, 0, KEYEVENTF_KEYUP, 0)
    time.sleep(0.05)
    user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)


def simulate_enter():
    user32.keybd_event(VK_RETURN, 0, 0, 0)
    time.sleep(0.05)
    user32.keybd_event(VK_RETURN, 0, KEYEVENTF_KEYUP, 0)


def simulate_search_shortcut():
    user32.keybd_event(VK_CONTROL, 0, 0, 0)
    time.sleep(0.05)
    user32.keybd_event(VK_F, 0, 0, 0)
    time.sleep(0.05)
    user32.keybd_event(VK_F, 0, KEYEVENTF_KEYUP, 0)
    time.sleep(0.05)
    user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)


def navigate_to_chat(target_name: str = "文件传输助手") -> bool:
    """唤醒微信并通过搜索定位到指定会话"""
    attach_to_default_desktop()
    hwnd = find_wechat_hwnd()
    if not hwnd:
        return False

    user32.ShowWindow(hwnd, SW_RESTORE)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.3)

    simulate_search_shortcut()
    time.sleep(0.3)

    set_clipboard_unicode(target_name)
    simulate_paste()
    time.sleep(0.5)

    simulate_enter()
    time.sleep(0.5)

    rect = RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w = rect.right - rect.left
    h = rect.bottom - rect.top
    click_x = rect.left + int(w * 0.65)
    click_y = rect.bottom - 75

    user32.SetCursorPos(click_x, click_y)
    time.sleep(0.05)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.05)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(0.2)
    return True


class WeChatWin32Sender(BaseSender):
    def __init__(self, interval_seq: float = 0.8, interval_body: float = 1.5):
        self.interval_seq = interval_seq
        self.interval_body = interval_body

    def dispatch(
        self,
        payloads: List[RenderedPayload],
        target_chat: str = "文件传输助手",
        on_progress: Optional[Callable[[int, int, str], None]] = None
    ) -> bool:
        if not navigate_to_chat(target_chat):
            raise RuntimeError(f"未能连接至微信客户端或找不到会话【{target_chat}】！请先启动并登录微信。")

        total_msgs = sum(len(p.to_chat_messages()) for p in payloads)
        current = 0

        for p in payloads:
            messages = p.to_chat_messages()
            for msg in messages:
                current += 1
                set_clipboard_unicode(msg)
                time.sleep(0.06)
                simulate_paste()
                time.sleep(0.12)
                simulate_enter()

                if on_progress:
                    on_progress(current, total_msgs, f"[{p.platform}] 发送: {msg[:20]}...")

                # 根据消息类型自适应等待
                if msg.startswith("序号"):
                    time.sleep(self.interval_seq)
                elif msg.startswith("以下是") or msg.startswith("【"):
                    time.sleep(1.0)
                else:
                    time.sleep(self.interval_body)

        return True
