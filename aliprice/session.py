"""Session and credential management for AliExpress requests.

The tracker can run anonymously (good enough for tracking a known URL), but
to discover the items *you* normally see in the app — your wishlist, cart,
or any logged-in page — it needs to make requests as you. This module
manages a small JSON config file at ``~/.aliprice/config.json`` containing
either a raw ``Cookie`` header string copied from your browser, or a path
to a Netscape-format ``cookies.txt`` file exported with an extension like
"Get cookies.txt LOCALLY".
"""

from __future__ import annotations

import http.cookiejar
import json
import os
from dataclasses import asdict, dataclass, field
from typing import Optional

import requests

from .scraper import DEFAULT_USER_AGENT


DEFAULT_CONFIG_PATH = os.environ.get(
    "ALIPRICE_CONFIG",
    os.path.join(os.path.expanduser("~"), ".aliprice", "config.json"),
)


@dataclass
class Config:
    cookie_string: Optional[str] = None
    cookies_file: Optional[str] = None
    user_agent: str = DEFAULT_USER_AGENT
    region: Optional[str] = None
    currency: Optional[str] = None

    def has_session(self) -> bool:
        return bool(self.cookie_string or self.cookies_file)


def load_config(path: str = DEFAULT_CONFIG_PATH) -> Config:
    if not os.path.exists(path):
        return Config()
    with open(path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            return Config()
    return Config(**{k: v for k, v in data.items() if k in Config.__dataclass_fields__})


def save_config(config: Config, path: str = DEFAULT_CONFIG_PATH) -> str:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(asdict(config), f, indent=2)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def _parse_cookie_string(cookie: str) -> dict[str, str]:
    """Parse a raw ``Cookie:`` header value into a name -> value dict."""
    jar: dict[str, str] = {}
    for chunk in cookie.split(";"):
        chunk = chunk.strip()
        if not chunk or "=" not in chunk:
            continue
        name, _, value = chunk.partition("=")
        jar[name.strip()] = value.strip()
    return jar


def build_session(config: Optional[Config] = None) -> requests.Session:
    """Construct a ``requests.Session`` pre-populated with the user's cookies."""
    cfg = config or load_config()
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": cfg.user_agent or DEFAULT_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
    )

    if cfg.cookies_file and os.path.exists(os.path.expanduser(cfg.cookies_file)):
        jar = http.cookiejar.MozillaCookieJar()
        try:
            jar.load(os.path.expanduser(cfg.cookies_file), ignore_discard=True, ignore_expires=True)
            session.cookies = jar  # type: ignore[assignment]
        except (OSError, http.cookiejar.LoadError):
            pass

    if cfg.cookie_string:
        for name, value in _parse_cookie_string(cfg.cookie_string).items():
            session.cookies.set(name, value, domain=".aliexpress.com")

    return session
