from app.core.security import digest_token, generate_token, hash_password, verify_password


def test_password_hash_uses_argon2id() -> None:
    encoded = hash_password("correct horse battery staple")
    assert encoded.startswith("$argon2id$")
    assert verify_password("correct horse battery staple", encoded)
    assert not verify_password("wrong", encoded)


def test_generated_token_is_only_persisted_as_digest() -> None:
    raw = generate_token()
    digest = digest_token(raw)
    assert raw != digest
    assert len(digest) == 64
