"""Ensure runtime_inviters exists on the bot class init signature via source contract.

We assert the attribute is assigned in Vocard.__init__ by reading main.py,
because constructing Vocard requires a live discord token/intents setup.
"""

from pathlib import Path


def test_vocard_init_assigns_runtime_inviters():
    main_src = Path(__file__).resolve().parents[1] / "main.py"
    text = main_src.read_text(encoding="utf-8")
    assert "self.runtime_inviters" in text
    assert "set()" in text
    # Must be in __init__, before setup_hook loads cogs
    init_idx = text.index("def __init__(self")
    setup_idx = text.index("async def setup_hook")
    runtime_idx = text.index("self.runtime_inviters")
    assert init_idx < runtime_idx < setup_idx
