# Love Letter App

A tiny Python "love letter exe" style app: an envelope opens, hearts float around,
and a custom message types itself out on screen.

## Run it

```bash
python3 love-letter/main.py
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

Open `love-letter/main.py` and edit the section named `Make it yours`:

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
python love-letter/build_exe.py
```

Or double-click:

```text
love-letter/build_exe.bat
```

The build script installs PyInstaller if you do not already have it.

Your executable will be created at:

```text
dist/Love Letter.exe
```

Important: build the `.exe` on Windows. PyInstaller packages for the operating
system it is running on, so a Linux or macOS computer cannot directly create the
Windows `.exe` with this script.

Tip: send the `.exe` with a short note so the recipient knows it is from you.
