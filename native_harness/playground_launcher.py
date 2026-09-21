"""Small Windows launcher for the native physics playground.

Keeping Unicorn in the normal Python process avoids a PyInstaller/Unicorn
native-library crash while still giving the local test build a single EXE
entry point.
"""
from __future__ import annotations

import ctypes
import shutil
import subprocess
import sys
from pathlib import Path


def find_script():
    executable_dir = Path(sys.executable).resolve().parent
    candidates = (
        executable_dir / "native_playground.py",
        executable_dir.parent / "native_playground.py",
        Path.cwd() / "native_playground.py",
        Path.cwd() / "native_harness" / "native_playground.py",
    )
    return next((path for path in candidates if path.is_file()), None)


def main():
    script = find_script()
    self_test = "--self-test" in sys.argv
    interpreter = shutil.which("python.exe" if self_test else "pythonw.exe")
    if script is None or interpreter is None:
        detail = "native_playground.py" if script is None else "pythonw.exe"
        ctypes.windll.user32.MessageBoxW(None, f"필요한 파일을 찾지 못했습니다: {detail}",
                                         "LostWeapon Native Playground", 0x10)
        return 2
    command = [interpreter, str(script), *sys.argv[1:]]
    if self_test:
        return subprocess.run(command, cwd=str(script.parent)).returncode
    subprocess.Popen(command, cwd=str(script.parent), creationflags=0x08000000)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
