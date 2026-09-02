#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
| Tester | Platform | Status |
| ----------------------- | ----------- | ------ |
| Darcy Shen <da@liii.pro>| Linux (X11) | Passed |
| intern (Windows)        | Windows     |        |

Automated end-to-end UI test for issue 1257 (same cases as
https://github.com/MoganLab/mogan/pull/4477 ):

1. New draft filename uses '_' between date and time
   (draft_YYYYMMDD_HHMMSS.tmu, optional -N suffix).
2. Legacy names draft_YYYYMMDDHHMMSS.tmu still open with a rendered tab title:
   - Case A today / this week
   - Case B last week / this year
   - Case C last year

Windows notes (this file):
- Prefer installed binary build/packages/stem/data/bin/MoganSTEM.exe
  (xmake b stem && xmake install stem).
- Focus via Win32 SetForegroundWindow (no X11).
- Screenshots go to the system temp directory (not /tmp).
- Do not lock the screen; the script needs the mouse and keyboard.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta

import numpy as np
from PIL import Image, ImageGrab

try:
    import pynput  # noqa: F401
except ImportError:
    pynput_path = os.path.expanduser("~/git/pynput/lib")
    if os.path.exists(pynput_path):
        sys.path.insert(0, pynput_path)

from pynput.keyboard import Controller as KeyboardController
from pynput.keyboard import Key
from pynput.mouse import Button
from pynput.mouse import Controller as MouseController

IS_WINDOWS = os.name == "nt"


def find_repo_root():
    cur = os.path.abspath(os.path.dirname(__file__))
    while cur != os.path.dirname(cur):
        if os.path.exists(os.path.join(cur, "TeXmacs")) and os.path.exists(
            os.path.join(cur, "src")
        ):
            return cur
        cur = os.path.dirname(cur)
    return os.path.abspath(".")


def find_mogan_binary(repo_root):
    candidates = [
        os.path.join(repo_root, "build", "packages", "stem", "data", "bin", "MoganSTEM.exe"),
        os.path.join(repo_root, "build", "windows", "x64", "release", "MoganSTEM.exe"),
        os.path.join(repo_root, "build", "windows", "x64", "releasedbg", "MoganSTEM.exe"),
        os.path.join(repo_root, "build", "linux", "x86_64", "release", "moganstem"),
        os.path.join(repo_root, "build", "linux", "x86_64", "debug", "moganstem"),
        os.path.join(repo_root, "build", "linux", "x86_64", "releasedbg", "moganstem"),
        os.path.join(
            repo_root,
            "build",
            "macosx",
            "arm64",
            "release",
            "MoganSTEM.app",
            "Contents",
            "MacOS",
            "MoganSTEM",
        ),
        os.path.join(
            repo_root,
            "build",
            "macosx",
            "x86_64",
            "release",
            "MoganSTEM.app",
            "Contents",
            "MacOS",
            "MoganSTEM",
        ),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    raise FileNotFoundError(
        "Mogan binary not found. Build stem first "
        "(Windows: xmake b stem && xmake install stem)."
    )


def find_no_name_dir():
    candidates = []
    if not IS_WINDOWS:
        try:
            xdg_docs = subprocess.check_output(
                ["xdg-user-dir", "DOCUMENTS"], text=True
            ).strip()
            if xdg_docs:
                candidates.append(os.path.join(xdg_docs, "LiiiSTEM", "no_name"))
        except Exception:
            pass

    home = os.path.expanduser("~")
    candidates.extend(
        [
            os.path.join(home, "文档", "LiiiSTEM", "no_name"),
            os.path.join(home, "Documents", "LiiiSTEM", "no_name"),
            os.path.join(home, "LiiiSTEM", "no_name"),
        ]
    )
    for d in candidates:
        if os.path.exists(d):
            return d
    target = os.path.join(home, "Documents", "LiiiSTEM", "no_name")
    os.makedirs(target, exist_ok=True)
    return target


def _windows_focus_mogan():
    """Raise a Mogan STEM / Liii STEM top-level window (Win32)."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    EnumWindows = user32.EnumWindows
    EnumWindowsProc = ctypes.WINFUNCTYPE(
        ctypes.c_bool, wintypes.HWND, wintypes.LPARAM
    )
    GetWindowTextW = user32.GetWindowTextW
    GetWindowTextLengthW = user32.GetWindowTextLengthW
    IsWindowVisible = user32.IsWindowVisible
    ShowWindow = user32.ShowWindow
    SetForegroundWindow = user32.SetForegroundWindow
    SW_RESTORE = 9

    found = []

    def callback(hwnd, _lparam):
        if not IsWindowVisible(hwnd):
            return True
        n = GetWindowTextLengthW(hwnd)
        if n <= 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        GetWindowTextW(hwnd, buf, n + 1)
        title = buf.value
        if "Mogan STEM" in title or "Liii STEM" in title or "MoganSTEM" in title:
            found.append(hwnd)
            return False
        return True

    EnumWindows(EnumWindowsProc(callback), 0)
    if not found:
        return
    hwnd = found[0]
    ShowWindow(hwnd, SW_RESTORE)
    SetForegroundWindow(hwnd)


def focus_mogan_window():
    if IS_WINDOWS:
        try:
            _windows_focus_mogan()
        except Exception:
            pass
        return
    try:
        import Xlib.display
        import Xlib.protocol.event
        import Xlib.X

        d = Xlib.display.Display()
        root = d.screen().root

        def find_mogan(win):
            try:
                name = win.get_wm_name()
                if name and ("Liii STEM" in name or "Mogan STEM" in name):
                    return win
                for child in win.query_tree().children:
                    res = find_mogan(child)
                    if res:
                        return res
            except Exception:
                pass
            return None

        w = find_mogan(root)
        if w:
            net_active = d.intern_atom("_NET_ACTIVE_WINDOW")
            cm = Xlib.protocol.event.ClientMessage(
                window=w,
                client_type=net_active,
                data=(32, [2, Xlib.X.CurrentTime, 0, 0, 0]),
            )
            root.send_event(
                cm,
                event_mask=Xlib.X.SubstructureRedirectMask
                | Xlib.X.SubstructureNotifyMask,
            )
            w.set_input_focus(Xlib.X.RevertToParent, Xlib.X.CurrentTime)
            w.configure(stack_mode=Xlib.X.Above)
            d.sync()
    except Exception:
        pass


def terminate_process(proc):
    if not proc:
        return
    if IS_WINDOWS:
        try:
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                capture_output=True,
                check=False,
            )
        except Exception:
            pass
        try:
            proc.wait(timeout=5)
        except Exception:
            pass
        return
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()


def wait_for_mogan(timeout=None):
    """Give the GUI time to come up (Windows install tree is slower)."""
    if timeout is None:
        timeout = 12.0 if IS_WINDOWS else 3.5
    end = time.time() + timeout
    while time.time() < end:
        focus_mogan_window()
        time.sleep(0.5)


def ctrl_key(keyboard, char):
    with keyboard.pressed(Key.ctrl):
        keyboard.press(char)
        keyboard.release(char)


def verify_tab_title_rendered(screenshot_path):
    img = Image.open(screenshot_path)
    w, h = img.size
    tab_crop = img.crop((0, 0, min(w, 800), min(h, 120)))
    arr = np.array(tab_crop.convert("L"))
    dark_pixels = np.sum(arr < 100)
    print(f"[1257] Tab bar text dark pixels count: {dark_pixels}")
    return dark_pixels > 200


def screenshot_path(name):
    return os.path.join(tempfile.gettempdir(), name)


def run_test():
    repo_root = find_repo_root()
    bin_path = find_mogan_binary(repo_root)
    no_name_dir = find_no_name_dir()
    print(f"[1257] Using Mogan binary: {bin_path}")
    print(f"[1257] Monitoring draft directory: {no_name_dir}")
    print(f"[1257] Platform: {'Windows' if IS_WINDOWS else sys.platform}")

    os.makedirs(no_name_dir, exist_ok=True)
    existing_files = set(os.listdir(no_name_dir))

    env = os.environ.copy()
    env["TEXMACS_PATH"] = os.path.join(repo_root, "TeXmacs")

    created_temp_files = []
    new_tmu_path = None
    matched_file = None

    print("\n[1257] --- Step 1: Creating new draft and testing new naming format ---")
    print("[1257] Launching Mogan...")
    proc = subprocess.Popen([bin_path], env=env, cwd=repo_root)
    keyboard = KeyboardController()
    mouse = MouseController()

    try:
        wait_for_mogan()
        focus_mogan_window()
        time.sleep(0.5)
        mouse.position = (500, 500)
        time.sleep(0.3)
        mouse.click(Button.left)
        time.sleep(0.5)

        print("[1257] Creating new tab (Ctrl+T)...")
        ctrl_key(keyboard, "t")
        time.sleep(2.0)

        print("[1257] Typing 'hello draft 1257'...")
        keyboard.type("hello draft 1257")
        time.sleep(1.0)

        print("[1257] Triggering preview (Ctrl+P) to auto-save draft...")
        ctrl_key(keyboard, "p")
        time.sleep(4.0 if IS_WINDOWS else 3.5)

        current_files = set(os.listdir(no_name_dir))
        diff_files = current_files - existing_files
        tmu_files = [f for f in diff_files if f.endswith(".tmu")]
        for f in diff_files:
            created_temp_files.append(os.path.join(no_name_dir, f))

        print(f"[1257] New files detected in draft dir: {diff_files}")
        if not tmu_files:
            print("[1257] ERROR: No .tmu draft file was created after previewing.")
            return 1

        pattern = re.compile(r"^draft_(\d{8})_(\d{6})(-\d+)?\.tmu$")
        for f in tmu_files:
            m = pattern.match(f)
            if m:
                matched_file = f
                print(
                    f"[1257] Valid draft filename: '{f}' "
                    f"(Date={m.group(1)}, Time={m.group(2)}, Separator='_')"
                )
                break

        if not matched_file:
            print(
                f"[1257] ERROR: Created files {tmu_files} do not match "
                "'draft_YYYYMMDD_HHMMSS.tmu'."
            )
            return 1
        new_tmu_path = os.path.join(no_name_dir, matched_file)
    finally:
        print("[1257] Terminating first Mogan instance...")
        terminate_process(proc)

    if not matched_file or not new_tmu_path:
        return 1

    print("\n[1257] --- Step 2: Testing 3 legacy draft filename compatibility cases ---")
    now = datetime.now()
    today_legacy_name = re.sub(
        r"^draft_(\d{8})_(\d{6})", r"draft_\1\2", matched_file
    )
    today_legacy_path = os.path.join(no_name_dir, today_legacy_name)

    last_week_dt = now - timedelta(days=7)
    last_week_legacy_path = os.path.join(
        no_name_dir, f"draft_{last_week_dt.strftime('%Y%m%d%H%M%S')}.tmu"
    )

    last_year_dt = now.replace(year=now.year - 1)
    last_year_legacy_path = os.path.join(
        no_name_dir, f"draft_{last_year_dt.strftime('%Y%m%d%H%M%S')}.tmu"
    )

    test_cases = [
        (
            "Case A (Today / This week)",
            today_legacy_path,
            screenshot_path("1257_legacy_today.png"),
        ),
        (
            "Case B (Last week / This year)",
            last_week_legacy_path,
            screenshot_path("1257_legacy_last_week.png"),
        ),
        (
            "Case C (Last year / Past year)",
            last_year_legacy_path,
            screenshot_path("1257_legacy_last_year.png"),
        ),
    ]

    for label, target_path, shot in test_cases:
        print(f"\n[1257] [{label}] Copying '{new_tmu_path}' -> '{target_path}'")
        shutil.copyfile(new_tmu_path, target_path)
        created_temp_files.append(target_path)

        print(
            f"[1257] [{label}] Launching Mogan to open legacy draft: "
            f"{os.path.basename(target_path)}"
        )
        proc_legacy = subprocess.Popen([bin_path, target_path], env=env, cwd=repo_root)
        try:
            wait_for_mogan()
            focus_mogan_window()
            time.sleep(0.5)
            img = ImageGrab.grab()
            img.save(shot)
            print(f"[1257] [{label}] Saved screenshot to {shot}")
            if not verify_tab_title_rendered(shot):
                print(f"[1257] ERROR: [{label}] Tab title was not rendered properly.")
                return 1
            print(
                f"[1257] [{label}] PASS: Legacy draft opened and tab title rendered."
            )
        finally:
            print(f"[1257] [{label}] Terminating Mogan instance...")
            terminate_process(proc_legacy)

    print("\n[1257] --- Step 3: Cleaning up temporary test files ---")
    for p in created_temp_files:
        try:
            if os.path.exists(p):
                os.remove(p)
                print(f"[1257] Removed temp file: {p}")
        except Exception as e:
            print(f"[1257] Warning: Failed to remove {p}: {e}")

    print(
        "\n[1257] ALL TESTS PASSED: New draft format and 3 legacy compatibility "
        "cases verified!"
    )
    return 0


if __name__ == "__main__":
    sys.exit(run_test())
