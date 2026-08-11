"""Manual IP preference → recommended cipher bind/URL defaults.

Compose and Lavalink do not read IP_PREFERENCE at runtime; operators copy
these defaults into YT_CIPHER_HOST / REMOTE_CIPHER_URL in `.env`.
"""

from __future__ import annotations

IP_PREFERENCE_DEFAULTS: dict[str, dict[str, str]] = {
    "ipv4": {
        "YT_CIPHER_HOST": "0.0.0.0",
        "REMOTE_CIPHER_URL": "http://127.0.0.1:8001",
    },
    "ipv6": {
        "YT_CIPHER_HOST": "::",
        "REMOTE_CIPHER_URL": "http://[::1]:8001",
    },
    "dual": {
        "YT_CIPHER_HOST": "::",
        "REMOTE_CIPHER_URL": "http://[::1]:8001",
    },
}
