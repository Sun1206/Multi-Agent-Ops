from app.services.events import sanitize_metadata


def test_recursive_sensitive_values_are_redacted() -> None:
    value = {
        "authorization": "Token raw",
        "nested": [{"password": "secret"}, {"safe": "visible"}],
        "ssh_private_key": "private",
        "kubeconfig": {"token": "nested-raw"},
    }
    assert sanitize_metadata(value) == {
        "authorization": "***",
        "nested": [{"password": "***"}, {"safe": "visible"}],
        "ssh_private_key": "***",
        "kubeconfig": "***",
    }


def test_legacy_certificate_and_private_key_fields_are_redacted() -> None:
    assert sanitize_metadata({"nested": {"cert_content": "certificate", "key_content": "private"}}) == {
        "nested": {"cert_content": "***", "key_content": "***"}
    }
