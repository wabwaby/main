# Project Atrocities

A tiny Python desktop app: an envelope opens, hearts float around, and a custom
message types itself out on screen.

## Run it

```bash
python3 project-atrocities/main.py
```

The app only uses Python's standard library (`tkinter`), so there are no Python
package dependencies to install. If your Linux Python install is very minimal and
you see `No module named 'tkinter'`, install Tkinter with:

```bash
sudo apt install python3-tk
```

On Windows, Python from python.org includes Tkinter by default when installed
with the standard options.

## Customize it

Open `project-atrocities/main.py` and edit the section named `Make it yours`:

- `RECIPIENT_NAME`
- `SENDER_NAME`
- `LETTER_LINES`
- `FINAL_PROMPT`
- `YES_REPLY`
- `NO_REPLY`

You can also tweak the colors in the `Theme` section.

## Make it a Windows `.exe`

Run this command on Windows from the repository root:

```powershell
python project-atrocities/build_exe.py
```

Or double-click:

```text
project-atrocities/build_exe.bat
```

The build script installs PyInstaller if you do not already have it.

Your executable will be created at:

```text
dist/ProjectAtrocities.exe
```

Important: build the `.exe` on Windows. PyInstaller packages for the operating
system it is running on, so a Linux or macOS computer cannot directly create the
Windows `.exe` with this script.

Tip: send the `.exe` with a short note so the recipient knows it is from you.

## If Windows says it cannot access the `.exe`

That usually means Windows Security blocked or quarantined the PyInstaller file.
Try this:

1. Move the project folder somewhere simple, like `Desktop\ProjectAtrocities`.
2. Rebuild by double-clicking `project-atrocities/build_exe.bat`.
3. Open `dist/ProjectAtrocities.exe`.
4. If it still fails, open **Windows Security**.
5. Go to **Virus & threat protection** > **Protection history**.
6. Look for a recent blocked item related to `ProjectAtrocities.exe`.
7. If you trust the file because you built it yourself, choose **Allow** or
   **Restore**, then try opening it again.

PyInstaller apps can trigger false positives because they bundle Python into one
file. Do not send or run the file if Windows Security reports something you do
not recognize or trust.
