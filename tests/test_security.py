from src.security import LoginThrottle, hash_password, verify_password
import pytest


def test_password_roundtrip_and_salt():
    encoded = hash_password("una clave suficientemente larga")
    assert verify_password("una clave suficientemente larga", encoded)
    assert not verify_password("una clave incorrecta", encoded)
    assert encoded != hash_password("una clave suficientemente larga")
    assert not verify_password("anything", "broken")
    assert not verify_password("anything", "pbkdf2_sha256$1$abc$def")
    with pytest.raises(ValueError):
        hash_password("short")


def test_lockout_shared_key_and_expiration():
    throttle = LoginThrottle(limit=3, window=60)
    for at in [100, 101, 102]:
        throttle.failure("juan", now=at)
    assert throttle.remaining("juan", now=103) > 0
    assert throttle.remaining("other", now=103) == 0
    assert throttle.remaining("juan", now=161) == 0
    throttle.success("juan")
    assert throttle.remaining("juan", now=162) == 0
