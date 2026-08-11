"""Tests for /whitelist add|remove branch classifiers used by the cog."""

from pathlib import Path

from voicelink.invite_permissions import (
    build_bot_invite_url,
    classify_whitelist_add,
    classify_whitelist_remove,
)


def test_add_classification():
    assert classify_whitelist_add(1, [1], set()) == "already_owner"
    assert classify_whitelist_add(2, [1], {2}) == "already_inviter"
    assert classify_whitelist_add(3, [1], set()) == "added"


def test_remove_classification():
    assert classify_whitelist_remove(1, [1], set()) == "cannot_remove_owner"
    assert classify_whitelist_remove(2, [1], {2}) == "removed"
    assert classify_whitelist_remove(3, [1], set()) == "not_in_list"


def test_add_always_returns_invite_with_canonical_perms():
    url = build_bot_invite_url(999)
    assert "permissions=2184572096" in url


def test_whitelist_cog_uses_shared_classifiers():
    """Regressions in cogs/whitelist.py must fail if classifiers are not wired."""
    cog_src = (Path(__file__).resolve().parents[1] / "cogs" / "whitelist.py").read_text(
        encoding="utf-8"
    )
    assert "classify_whitelist_add" in cog_src
    assert "classify_whitelist_remove" in cog_src
