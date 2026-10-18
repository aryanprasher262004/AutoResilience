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


def test_discovery_clusters_are_parsed_from_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "DISCOVERY_CLUSTERS", '[{"context": "kind-staging", "namespaces": ["shop"]}]'
    )
    [cluster] = Settings().discovery_clusters
    assert (cluster.context, cluster.namespaces) == ("kind-staging", ["shop"])


@pytest.mark.parametrize(
    ("clusters", "message"),
    [
        ([{"context": "kind-x", "namespaces": ["shop"]}], "execution context"),
        (
            [
                {"context": "a", "namespaces": ["shop"]},
                {"context": "a", "namespaces": ["web"]},
            ],
            "listed twice",
        ),
        ([{"context": "a", "namespaces": ["kube-system"]}], "system namespace"),
        ([{"context": "a", "namespaces": ["Bad_Name"]}], "not a namespace name"),
    ],
)
def test_unsafe_discovery_clusters_are_refused(
    clusters: list[dict[str, object]], message: str
) -> None:
    settings = Settings.model_validate(
        {"kube_context": "kind-x", "discovery_clusters": clusters}
    )
    with pytest.raises(ConfigurationError, match=message):
        check_runtime(settings)


def test_discovery_cluster_needs_at_least_one_namespace() -> None:
    with pytest.raises(ValueError):
        Settings.model_validate(
            {"discovery_clusters": [{"context": "a", "namespaces": []}]}
        )
