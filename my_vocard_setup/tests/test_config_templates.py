import json
from pathlib import Path

from ip_preference import IP_PREFERENCE_DEFAULTS

SETUP_DIR = Path(__file__).resolve().parents[1]
ENV_EXAMPLE = SETUP_DIR / ".env.example"
SETTINGS_EXAMPLE = SETUP_DIR / "settings Example.json"

REQUIRED_ENV_KEYS = [
    "TOKEN",
    "CLIENT_ID",
    "GENIUS_TOKEN",
    "MONGODB_URL",
    "MONGODB_NAME",
    "YOUTUBE_OAUTH_REFRESH_TOKEN",
    "YOUTUBE_POT_TOKEN",
    "YOUTUBE_POT_VISITOR_DATA",
    "IP_PREFERENCE",
    "IP_BLOCKS",
    "YT_CIPHER_HOST",
    "REMOTE_CIPHER_URL",
    "YT_CIPHER_API_TOKEN",
    "CLOUDFLARED_TOKEN",
]

FORBIDDEN_SECRET_FRAGMENTS = [
    "eouc2pn8-IcnqIYxQRimPaLQSWrMs-Yn",
    "2600:1900:4080:5ba::/64",
    "eyJhIjoiMTkwYTQ3OTczMjVjNTJkNzY1ZDFkOTRmYjcxM2U1MjQi",
]


def _parse_env_keys(text: str) -> set[str]:
    keys: set[str] = set()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        keys.add(stripped.split("=", 1)[0].strip())
    return keys


def test_env_example_exists_and_has_required_keys():
    assert ENV_EXAMPLE.is_file()
    keys = _parse_env_keys(ENV_EXAMPLE.read_text(encoding="utf-8"))
    missing = [k for k in REQUIRED_ENV_KEYS if k not in keys]
    assert missing == []


def test_env_example_has_no_forbidden_secrets():
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    for fragment in FORBIDDEN_SECRET_FRAGMENTS:
        assert fragment not in text


def test_ip_preference_defaults_cover_all_modes():
    assert set(IP_PREFERENCE_DEFAULTS) == {"ipv4", "ipv6", "dual"}


def test_ip_preference_ipv4_defaults():
    assert IP_PREFERENCE_DEFAULTS["ipv4"] == {
        "YT_CIPHER_HOST": "0.0.0.0",
        "REMOTE_CIPHER_URL": "http://127.0.0.1:8001",
    }


def test_ip_preference_ipv6_and_dual_defaults():
    expected = {
        "YT_CIPHER_HOST": "::",
        "REMOTE_CIPHER_URL": "http://[::1]:8001",
    }
    assert IP_PREFERENCE_DEFAULTS["ipv6"] == expected
    assert IP_PREFERENCE_DEFAULTS["dual"] == expected


COMPOSE_FILE = SETUP_DIR / "docker-compose.yml"


def test_compose_has_no_forbidden_secrets():
    text = COMPOSE_FILE.read_text(encoding="utf-8")
    for fragment in FORBIDDEN_SECRET_FRAGMENTS:
        assert fragment not in text


def test_compose_wires_cipher_and_cloudflared_from_env():
    text = COMPOSE_FILE.read_text(encoding="utf-8")
    assert "YT_CIPHER_HOST:?Set YT_CIPHER_HOST in .env" in text
    assert "YT_CIPHER_API_TOKEN:?Set YT_CIPHER_API_TOKEN in .env" in text
    assert "CLOUDFLARED_TOKEN:?Set CLOUDFLARED_TOKEN in .env" in text


LAVALINK_YML = SETUP_DIR / "lavalink" / "application.yml"


def test_lavalink_yml_has_no_forbidden_secrets():
    text = LAVALINK_YML.read_text(encoding="utf-8")
    for fragment in FORBIDDEN_SECRET_FRAGMENTS:
        assert fragment not in text


def test_lavalink_yml_uses_env_placeholders():
    text = LAVALINK_YML.read_text(encoding="utf-8")
    assert "${REMOTE_CIPHER_URL" in text
    assert "${YT_CIPHER_API_TOKEN" in text
    assert "${IP_BLOCKS" in text
    assert "${YOUTUBE_OAUTH_REFRESH_TOKEN" in text
    assert "${YOUTUBE_POT_TOKEN" in text
    assert "${YOUTUBE_POT_VISITOR_DATA" in text


def test_settings_example_has_bot_token_fields():
    data = json.loads(SETTINGS_EXAMPLE.read_text(encoding="utf-8"))
    assert "token" in data
    assert "client_id" in data
    assert "genius_token" in data
    nodes = data["nodes"]
    assert "tokens" in nodes["DEFAULT"]["yt_ratelimit"]
    assert isinstance(nodes["DEFAULT"]["yt_ratelimit"]["tokens"], list)
    # Spec: no new IP / YouTube-plugin settings keys
    assert "IP_PREFERENCE" not in data
    assert "YOUTUBE_OAUTH_REFRESH_TOKEN" not in data


def test_config_reads_token_fields_from_env_fallback(monkeypatch):
    monkeypatch.setenv("TOKEN", "env-bot-token")
    monkeypatch.setenv("CLIENT_ID", "123456789012345678")
    monkeypatch.setenv("GENIUS_TOKEN", "env-genius-token")
    monkeypatch.setenv("MONGODB_URL", "mongodb://localhost:27017")
    monkeypatch.setenv("MONGODB_NAME", "vocard_test")

    from voicelink.config import Config

    # Reset singleton if needed for clean construct
    Config._instance = None

    cfg = Config(
        {
            "token": "",
            "client_id": 0,
            "genius_token": "",
            "mongodb_url": "",
            "mongodb_name": "",
        }
    )
    assert cfg.token == "env-bot-token"
    assert cfg.client_id == 123456789012345678
    assert cfg.genius_token == "env-genius-token"
