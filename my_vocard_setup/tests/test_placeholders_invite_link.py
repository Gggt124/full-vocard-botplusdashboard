from pathlib import Path

from voicelink.invite_permissions import BOT_INVITE_PERMISSIONS


def test_placeholders_invite_link_uses_canonical_permissions():
    text = (Path(__file__).resolve().parents[1] / "voicelink" / "placeholders.py").read_text(
        encoding="utf-8"
    )
    assert "2184260928" not in text
    assert "BOT_INVITE_PERMISSIONS" in text or str(BOT_INVITE_PERMISSIONS) in text
