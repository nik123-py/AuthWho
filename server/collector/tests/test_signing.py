import base64
import hashlib
import hmac

from server.collector.signing import b64url_decode, new_stream_key, sign, verify


def test_new_stream_key_is_32_random_bytes_in_unpadded_base64url():
    key = new_stream_key()
    assert "=" not in key and "+" not in key and "/" not in key
    assert len(b64url_decode(key)) == 32
    assert new_stream_key() != key


def test_sign_matches_hmac_sha256_over_raw_bytes():
    key = new_stream_key()
    body = b'{"v":1}'
    expected = base64.urlsafe_b64encode(
        hmac.new(b64url_decode(key), body, hashlib.sha256).digest()
    ).decode().rstrip("=")
    assert sign(key, body) == expected


def test_verify_accepts_padded_or_unpadded_and_rejects_tampering():
    key = new_stream_key()
    body = b'{"v":1,"seq":0}'
    sig = sign(key, body)
    assert verify(key, body, sig)
    assert verify(key, body, sig + "=")
    assert not verify(key, body + b" ", sig)
    assert not verify(new_stream_key(), body, sig)
    assert not verify(key, body, None)
    assert not verify(key, body, "")
    assert not verify(key, body, "é" * 43)
