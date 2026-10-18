from typing import Literal

from pydantic import BaseModel

EnvironmentCheckName = Literal["database", "kubernetes", "prometheus"]


class EnvironmentCheck(BaseModel):
    name: EnvironmentCheckName
    status: Literal["pass", "fail"]
    # Human-readable; never credentials, tokens or kubeconfig content.
    detail: str


class Environment(BaseModel):
    """What this API process is connected to, as observed by the API itself."""

    runtime_mode: Literal["development", "local-stack"]
    # The kubeconfig context name only; None means the current-context fallback.
    kube_context: str | None
    # Scheme, host and port only (any userinfo is dropped).
    prometheus_url: str
    checks: list[EnvironmentCheck]
