"""Shared validation for both import formats: names, images, labels, resources."""

import re
from dataclasses import dataclass, field
from typing import Any

from app.schemas.imports import Finding, Resources, Severity

MAX_WORKLOADS = 20
MAX_REPLICAS = 5
MAX_PORTS = 10
MAX_CONTAINERS = 1  # one container per workload (no sidecars in the MVP)
MAX_ENV_NAMES = 200
MAX_ARGS = 50
MAX_ARG_LENGTH = 1000

DEFAULT_RESOURCES = Resources(
    cpu_request="50m", memory_request="64Mi", cpu_limit="500m", memory_limit="256Mi"
)
MAX_CPU_MILLI = 1000
MAX_MEMORY_MI = 1024

# Names AutoResilience uses inside an import namespace.
RESERVED_PREFIX = "autoresilience-"

DNS_LABEL = re.compile(r"^[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?$")
ENV_NAME = re.compile(r"^[-._a-zA-Z][-._a-zA-Z0-9]*$")
# A Docker image reference: [registry[:port]/]path[:tag][@sha256:digest].
_COMPONENT = r"[a-z0-9]+(?:(?:[._]|__|-+)[a-z0-9]+)*"
IMAGE_REF = re.compile(
    rf"^(?:(?P<registry>[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)*(?::[0-9]{{1,5}})?)/)?"
    rf"(?P<path>{_COMPONENT}(?:/{_COMPONENT})*)"
    r"(?::(?P<tag>[\w][\w.-]{0,127}))?"
    r"(?:@(?P<digest>sha256:[a-f0-9]{64}))?$"
)
LABEL_KEY = re.compile(
    r"^(?:[a-z0-9]([-a-z0-9.]{0,251}[a-z0-9])?/)?[A-Za-z0-9]([-A-Za-z0-9_.]{0,61}[A-Za-z0-9])?$"
)
LABEL_VALUE = re.compile(r"^(?:[A-Za-z0-9]([-A-Za-z0-9_.]{0,61}[A-Za-z0-9])?)?$")
# ${VAR}, ${VAR:-x}, $VAR; "$$" is Compose's escape for a literal "$".
INTERPOLATION = re.compile(r"(?<!\$)\$(?:\{[^}]*\}|[A-Za-z_][A-Za-z0-9_]*)")
SENSITIVE = re.compile(
    r"(password|passwd|secret|token|api[_-]?key|private[_-]?key|credential)",
    re.IGNORECASE,
)
_CPU = re.compile(r"^(?:(\d+)m|(\d+(?:\.\d+)?))$")
_MEM = re.compile(r"^(\d+(?:\.\d+)?)(Ki|Mi|Gi|K|M|G|k|m|g|b|B)?$")
_MEM_FACTOR_MI = {
    None: 1 / (1024 * 1024),
    "b": 1 / (1024 * 1024),
    "B": 1 / (1024 * 1024),
    "Ki": 1 / 1024,
    "K": 1 / 1024,
    "k": 1 / 1024,
    "Mi": 1,
    "M": 1,
    "m": 1,
    "Gi": 1024,
    "G": 1024,
    "g": 1024,
}


@dataclass
class Findings:
    items: list[Finding] = field(default_factory=list)

    def add(
        self,
        severity: Severity,
        code: str,
        message: str,
        *,
        subject: str | None = None,
        path: str | None = None,
        hint: str | None = None,
    ) -> None:
        self.items.append(
            Finding(
                severity=severity,
                code=code,
                subject=subject,
                path=path,
                message=message,
                hint=hint,
            )
        )

    def block(self, code: str, message: str, **kw: Any) -> None:
        self.add("blocking", code, message, **kw)

    def warn(self, code: str, message: str, **kw: Any) -> None:
        self.add("warning", code, message, **kw)

    def info(self, code: str, message: str, **kw: Any) -> None:
        self.add("info", code, message, **kw)

    @property
    def blocking(self) -> bool:
        return any(f.severity == "blocking" for f in self.items)

    def sorted(self) -> list[Finding]:
        order = {"blocking": 0, "warning": 1, "info": 2}
        return sorted(
            self.items,
            key=lambda f: (order[f.severity], f.subject or "", f.path or "", f.code),
        )


def check_name(value: Any, what: str, findings: Findings, path: str) -> str | None:
    if not isinstance(value, str) or not DNS_LABEL.match(value):
        findings.block(
            "invalid_name",
            f"{what} name {str(value)[:80]!r} is not a valid Kubernetes name",
            path=path,
            hint="Use at most 63 lowercase letters, digits and '-', starting and "
            "ending with a letter or digit.",
        )
        return None
    if value.startswith(RESERVED_PREFIX):
        findings.block(
            "reserved_name",
            f"{what} name {value!r} uses the reserved prefix {RESERVED_PREFIX!r}",
            path=path,
            hint="Rename it; AutoResilience names its own objects with that prefix.",
        )
        return None
    return value


def check_image(value: Any, subject: str, findings: Findings, path: str) -> str | None:
    if not isinstance(value, str) or not value.strip():
        findings.block("missing_image", "No image is given", subject=subject, path=path)
        return None
    if INTERPOLATION.search(value):
        findings.block(
            "unresolved_variable",
            f"The image {value[:120]!r} contains a variable",
            subject=subject,
            path=path,
            hint="Variables are never resolved (.env files are not read). Write the "
            "image reference out in full.",
        )
        return None
    match = IMAGE_REF.match(value) if len(value) <= 255 else None
    if match is None:
        findings.block(
            "invalid_image",
            f"{value[:120]!r} is not a valid image reference",
            subject=subject,
            path=path,
        )
        return None
    if match["digest"]:
        findings.info(
            "image_pinned",
            f"{value} is pinned by digest: the deployment is reproducible",
            subject=subject,
            path=path,
        )
    elif not match["tag"] or match["tag"] == "latest":
        findings.warn(
            "image_not_pinned",
            f"{value} has no version tag (or 'latest'): what runs may change between "
            "deployments",
            subject=subject,
            path=path,
            hint="Use an explicit version tag, or better a digest (@sha256:...).",
        )
    return value


def check_labels(
    raw: Any, subject: str, findings: Findings, path: str
) -> dict[str, str]:
    labels: dict[str, str] = {}
    if raw is None:
        return labels
    if not isinstance(raw, dict):
        findings.block("invalid_labels", "Labels must be a mapping", path=path)
        return labels
    for key, value in raw.items():
        if (
            not isinstance(value, str)
            or not LABEL_KEY.match(key)
            or not (LABEL_VALUE.match(value))
        ):
            findings.block(
                "invalid_label",
                f"Label {str(key)[:80]!r} is not a valid Kubernetes label",
                subject=subject,
                path=path,
            )
            continue
        if (
            key.startswith("autoresilience.io/")
            or key == "app.kubernetes.io/managed-by"
        ):
            findings.block(
                "reserved_label",
                f"Label {key!r} is reserved for AutoResilience's ownership tracking",
                subject=subject,
                path=path,
                hint="Remove it; ownership labels are added by the import.",
            )
            continue
        labels[key] = value
    return labels


def check_strings(
    raw: Any, subject: str, findings: Findings, path: str
) -> list[str] | None:
    """A command/args list of plain strings, with no unresolved variables."""
    if raw is None:
        return None
    if isinstance(raw, str):
        findings.block(
            "shell_string_command",
            "A command given as one string would need a shell to split it",
            subject=subject,
            path=path,
            hint='Write it as a list, e.g. ["podinfo", "--port=9898"].',
        )
        return None
    if not isinstance(raw, list) or not all(
        isinstance(a, str | int | float) and not isinstance(a, bool) for a in raw
    ):
        findings.block(
            "invalid_command", "Must be a list of strings", subject=subject, path=path
        )
        return None
    values = [str(a) for a in raw]
    if len(values) > MAX_ARGS or any(len(a) > MAX_ARG_LENGTH for a in values):
        findings.block(
            "command_too_long",
            f"At most {MAX_ARGS} arguments of {MAX_ARG_LENGTH} characters",
            subject=subject,
            path=path,
        )
        return None
    if any(INTERPOLATION.search(a) for a in values):
        findings.block(
            "unresolved_variable",
            "The command contains a variable",
            subject=subject,
            path=path,
            hint="Variables are never resolved (.env files are not read). Write the "
            "values out, without credentials.",
        )
        return None
    if any(SENSITIVE.search(a) for a in values):
        findings.warn(
            "sensitive_argument",
            "An argument looks like it carries a credential; it would be visible in "
            "the plan and in the cluster",
            subject=subject,
            path=path,
            hint="Remove credentials from the file; test deployments should not need "
            "real ones.",
        )
    return [a.replace("$$", "$") for a in values]


def cpu_milli(value: Any) -> int | None:
    match = _CPU.match(str(value).strip()) if value is not None else None
    if not match:
        return None
    return int(match[1]) if match[1] else round(float(match[2]) * 1000)


def memory_mi(value: Any) -> float | None:
    match = _MEM.match(str(value).strip()) if value is not None else None
    if not match:
        return None
    return float(match[1]) * _MEM_FACTOR_MI[match[2]]


def resources(
    limits: dict[str, Any],
    requests: dict[str, Any],
    subject: str,
    findings: Findings,
    path: str,
) -> Resources:
    """Within the caps; anything absent gets the conservative default."""
    out = DEFAULT_RESOURCES.model_copy()
    for kind, given in (("limit", limits), ("request", requests)):
        cpu, memory = given.get("cpu"), given.get("memory")
        if cpu is not None:
            milli = cpu_milli(cpu)
            if milli is None or milli <= 0 or milli > MAX_CPU_MILLI:
                findings.block(
                    "resource_out_of_bounds",
                    f"CPU {kind} {cpu!r} is not between 1m and {MAX_CPU_MILLI}m",
                    subject=subject,
                    path=path,
                )
            else:
                setattr(out, f"cpu_{kind}", f"{milli}m")
        if memory is not None:
            mi = memory_mi(memory)
            if mi is None or mi < 4 or mi > MAX_MEMORY_MI:
                findings.block(
                    "resource_out_of_bounds",
                    f"Memory {kind} {memory!r} is not between 4Mi and {MAX_MEMORY_MI}Mi",
                    subject=subject,
                    path=path,
                )
            else:
                setattr(out, f"memory_{kind}", f"{int(mi)}Mi")
    # Both are well-formed here (defaults or validated above).
    if (cpu_milli(out.cpu_request) or 0) > (cpu_milli(out.cpu_limit) or 0):
        out.cpu_request = out.cpu_limit
    if (memory_mi(out.memory_request) or 0) > (memory_mi(out.memory_limit) or 0):
        out.memory_request = out.memory_limit
    return out


def env_names(
    names: list[str], subject: str, findings: Findings, path: str
) -> list[str]:
    valid = sorted({n for n in names if ENV_NAME.match(n)})[:MAX_ENV_NAMES]
    if valid:
        sensitive = [n for n in valid if SENSITIVE.search(n)]
        findings.warn(
            "environment_not_copied",
            f"{len(valid)} environment variable(s) are not set in the test deployment: "
            + ", ".join(valid[:12])
            + (" ..." if len(valid) > 12 else ""),
            subject=subject,
            path=path,
            hint="Values are never read, stored or copied"
            + (f" ({len(sensitive)} look like credentials)" if sensitive else "")
            + ". If the service needs them to start, give it safe defaults in the "
            "image or as command arguments.",
        )
    return valid
