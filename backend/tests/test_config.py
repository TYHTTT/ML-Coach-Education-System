import pytest
from pydantic import ValidationError
from app.core.config import Settings


def test_dify_configuration_and_secret_redaction():
    settings = Settings(_env_file=None, dify_api_key="app-secret", dify_inputs={"tenant": "education"})
    assert settings.dify_api_key.get_secret_value() == "app-secret"
    assert "app-secret" not in repr(settings)
    assert not hasattr(settings, "embedding_dimension")


@pytest.mark.parametrize("timeout", [0, -1, 601])
def test_invalid_dify_timeout_is_rejected(timeout):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, dify_timeout_seconds=timeout)
