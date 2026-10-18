import pytest

from app.core.config import ConfigurationError, Settings, check_runtime


def test_local_stack_requires_an_explicit_kube_context() -> None:
    with pytest.raises(ConfigurationError, match="explicit KUBE_CONTEXT"):
        check_runtime(Settings(runtime_mode="local-stack", kube_context=None))
    with pytest.raises(ConfigurationError):
        check_runtime(Settings(runtime_mode="local-stack", kube_context=""))


def test_local_stack_with_context_and_development_fallback_are_accepted() -> None:
    check_runtime(Settings(runtime_mode="local-stack", kube_context="kind-x"))
    check_runtime(Settings(runtime_mode="development", kube_context=None))


def test_runtime_mode_is_read_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RUNTIME_MODE", "local-stack")
    monkeypatch.setenv("KUBE_CONTEXT", "kind-autoresilience")
    settings = Settings()
    assert (settings.runtime_mode, settings.kube_context) == (
        "local-stack",
        "kind-autoresilience",
    )
    monkeypatch.setenv("RUNTIME_MODE", "production")
    with pytest.raises(ValueError):
        Settings()
