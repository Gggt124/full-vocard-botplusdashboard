from pathlib import Path


def test_command_check_allows_whitelist_in_dm_for_owners():
    text = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
    assert 'startswith("whitelist")' in text
    assert "bot_access_user" in text
    assert 'ephemeral=True' in text
    # Existing guild-only message must become ephemeral
    assert 'send_message("This command can only be used in guilds!", ephemeral=True)' in text


def test_command_check_logs_warning_on_dm_whitelist_denial():
    """Section 5: unauthorized /whitelist (including DM) must WARNING-log user id + DM."""
    text = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
    # Carve-out denial branch must log before denying non-Owners in DMs
    assert 'func.logger.warning(' in text
    assert "Unauthorized /whitelist attempt by user %s in %s" in text
    assert '"DM"' in text
