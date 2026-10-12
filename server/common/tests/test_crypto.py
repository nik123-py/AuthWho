import os

import pytest

from server.common.crypto import CryptoError, decrypt, encrypt


KEY = bytes(range(32))


def test_round_trip_returns_plaintext():
    blob = encrypt(b'{"values": [1.5, 2.5]}', KEY)
    assert decrypt(blob, KEY) == b'{"values": [1.5, 2.5]}'


def test_ciphertext_does_not_contain_plaintext_and_is_randomised():
    plaintext = b"[[1, 1201.3, 1, 0], [2, 1288.9, 1, 0]]"
    first = encrypt(plaintext, KEY)
    second = encrypt(plaintext, KEY)
    assert plaintext not in first
    assert first != second


def test_wrong_key_fails():
    blob = encrypt(b"secret", KEY)
    with pytest.raises(CryptoError):
        decrypt(blob, os.urandom(32))


def test_tampered_ciphertext_fails():
    blob = bytearray(encrypt(b"secret", KEY))
    blob[-1] ^= 0x01
    with pytest.raises(CryptoError):
        decrypt(bytes(blob), KEY)


def test_associated_data_must_match():
    blob = encrypt(b"secret", KEY, aad=b"session-a")
    assert decrypt(blob, KEY, aad=b"session-a") == b"secret"
    with pytest.raises(CryptoError):
        decrypt(blob, KEY, aad=b"session-b")


@pytest.mark.parametrize("bad_key", [b"", b"short", bytes(16), bytes(33)])
def test_key_must_be_32_bytes(bad_key):
    with pytest.raises(CryptoError):
        encrypt(b"x", bad_key)
