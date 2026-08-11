from pathlib import Path


def test_dashboard_invite_uses_canonical_permissions():
    path = Path(__file__).resolve().parents[1] / "assets" / "js" / "objects.js"
    text = path.read_text(encoding="utf-8")
    assert "permissions=2184538176" not in text
    assert "permissions=2184572096" in text
