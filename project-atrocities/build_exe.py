"""Build Project Atrocities into a Windows .exe.

Run this from the repository root after customizing main.py:

    python project-atrocities/build_exe.py

The finished file will be written to:

    dist/ProjectAtrocities.exe
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


APP_NAME = "ProjectAtrocities"
OLD_OUTPUT_NAMES = ("Project Atrocities.exe",)


def run(command: list[str]) -> None:
    print("+", " ".join(command))
    subprocess.run(command, check=True)


def ensure_windows() -> None:
    if sys.platform == "win32":
        return

    raise SystemExit(
        "This builder must run on Windows to create a Windows .exe.\n"
        "PyInstaller packages apps for the operating system it is running on, "
        "so open this folder on a Windows computer and run this script there."
    )


def ensure_pyinstaller() -> None:
    check = subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--version"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if check.returncode == 0:
        return

    print("PyInstaller is not installed yet. Installing it with pip...")
    run([sys.executable, "-m", "pip", "install", "--upgrade", "pyinstaller"])


def build_exe() -> Path:
    repo_root = Path(__file__).resolve().parents[1]
    app_entry = repo_root / "project-atrocities" / "main.py"
    dist_dir = repo_root / "dist"
    build_dir = repo_root / "build"
    icon_file = repo_root / "project-atrocities" / "icon.ico"

    for old_name in OLD_OUTPUT_NAMES:
        old_output = dist_dir / old_name
        if old_output.exists():
            old_output.unlink()

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name",
        APP_NAME,
        "--distpath",
        str(dist_dir),
        "--workpath",
        str(build_dir),
        "--specpath",
        str(build_dir),
    ]

    if icon_file.exists():
        command.extend(["--icon", str(icon_file)])

    command.append(str(app_entry))
    run(command)

    exe_path = dist_dir / f"{APP_NAME}.exe"
    if not exe_path.exists():
        raise SystemExit(f"Build finished, but expected file was not found: {exe_path}")

    return exe_path


def main() -> None:
    os.chdir(Path(__file__).resolve().parents[1])
    ensure_windows()
    ensure_pyinstaller()
    exe_path = build_exe()
    print()
    print("Done. Send this file:")
    print(exe_path)
    print()
    print(
        "If Windows blocks it, open Windows Security > Virus & threat protection "
        "> Protection history, then allow/restore it if you trust the file."
    )


if __name__ == "__main__":
    main()
