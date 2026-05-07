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

Run these commands on Windows from the repository root:

```powershell
python -m pip install pyinstaller
pyinstaller --onefile --windowed --name "Love Letter" love-letter/main.py
```

Your executable will be created at:

```text
dist/Love Letter.exe
```

Tip: send the `.exe` with a short note so the recipient knows it is from you.
