# daily diary

A tiny CLI you can use to journal your day and track todos, with an LLM
friend attached. Pick a vibe and it will encourage you, call you out, just
listen, or roast you (lovingly).

```
+------------------------------------------------+
|  daily diary                                   |
|    2026-05-07  -  mood: coach  -  chat on      |
+------------------------------------------------+
> /todo write the report
+ added #1 write the report

  Coach: when are you doing it? block off a time and tell me.

> kept getting distracted today
  Coach: by what, specifically? if it's the same thing tomorrow,
  we have a pattern, not a bad day.
```

## What it does

- Logs free-form journal entries to a daily markdown file.
- Tracks todos. Unfinished todos roll forward to the next day automatically.
- After every entry, the bot replies in whatever personality you picked.
- Saves chat history per day so the bot remembers your day's context.
- Works with any OpenAI-compatible API: OpenAI, OpenRouter, Groq, Ollama.

## Install

```bash
pip install -r requirements.txt
cp .env.example .env
# edit .env and put in your DIARY_API_KEY (or point DIARY_BASE_URL at Ollama)
```

## Run

```bash
python diary.py
```

Optional flags:

```bash
python diary.py --mood roast            # change personality for this session
python diary.py --dir ~/Documents/diary # custom storage location
python diary.py --no-chat               # logging-only, no LLM calls
python diary.py --list-moods            # show available personalities
```

## Personalities

| key           | vibe                                              |
| ------------- | ------------------------------------------------- |
| `cheerleader` | hype, encouraging, celebrates small wins          |
| `coach`       | kind but firm, calls out repeated procrastination |
| `friend`      | chill, conversational, mostly just listens        |
| `roast`       | playfully brutal, loving roasts only              |

Switch mid-session with `/mood <key>`.

## Commands

While the app is running:

| command          | what it does                            |
| ---------------- | --------------------------------------- |
| `/todo <text>`   | add a todo                              |
| `/done <id>`     | mark a todo done                        |
| `/undone <id>`   | reopen a todo                           |
| `/rm <id>`       | delete a todo                           |
| `/todos`         | list today's todos                      |
| `/log`           | print the path to today's log file      |
| `/mood <key>`    | change personality                      |
| `/quiet`         | toggle bot replies on/off               |
| `/help`          | show help                               |
| `/exit`          | save and quit (Ctrl+C also works)       |

Anything that doesn't start with `/` is treated as a journal entry and the
bot replies to it.

## Where stuff is saved

By default, everything goes under `./entries/`:

```
entries/
  2026-05-07/
    log.md       # human-readable journal + bot replies
    todos.json   # today's todo list
    chat.json    # raw chat history (for LLM context)
```

`log.md` is meant to be read directly, like a regular diary.

## Configuration

All env vars (also settable in `.env`):

| variable         | purpose                                                |
| ---------------- | ------------------------------------------------------ |
| `DIARY_API_KEY`  | API key. Falls back to `OPENAI_API_KEY`.               |
| `DIARY_BASE_URL` | Custom API endpoint. Falls back to `OPENAI_BASE_URL`.  |
| `DIARY_MODEL`    | Model name. Default: `gpt-4o-mini`.                    |
| `DIARY_DIR`      | Where to store entries. Default: `./entries`.          |
| `DIARY_MOOD`     | Default personality.                                   |

### Using local Ollama

```bash
ollama pull llama3.1
ollama serve
```

In `.env`:

```
DIARY_BASE_URL=http://localhost:11434/v1
DIARY_MODEL=llama3.1
```

No API key needed.

## Notes

- Your entries never leave your machine except via the LLM API call you
  configure. The `entries/` directory is gitignored.
- If you don't set up an API key, the app still runs in logging-only mode.
