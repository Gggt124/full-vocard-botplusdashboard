from pathlib import Path
import re


def test_update_version_is_v2_7_4_or_newer_for_whitelist_sync():
    text = (Path(__file__).resolve().parents[1] / "update.py").read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*"(v\d+\.\d+\.\d+)"', text)
    assert match, "update.__version__ not found"
    version = match.group(1)
    assert version != "v2.7.3", "Bump update.__version__ so setup_hook syncs /whitelist"
    assert version == "v2.7.4"
