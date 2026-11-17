"""Shared by tests that sign in with a hand-made session cookie: switches
the authenticator check off (it needs the database). The MFA behaviour
itself is tested in test_mfa.py."""
from unittest.mock import patch

_patches = [
    patch("blueprints.admin.mfa.session_state", return_value="ok"),
    patch("blueprints.admin.mfa.mfa_service.enabled_at", return_value=None),
    patch("blueprints.admin.mfa.mfa_service.any_enabled", return_value=False),
]


def start():
    for p in _patches:
        p.start()


def stop():
    for p in _patches:
        p.stop()
