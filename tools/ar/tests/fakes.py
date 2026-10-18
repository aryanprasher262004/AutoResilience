"""A scripted Runner: records every argv and answers by argv prefix."""

import io
from collections.abc import Callable, Sequence
from pathlib import Path

from ar_cli.paths import Paths
from ar_cli.runner import CommandError, Result, Runner

ROOT = Path(__file__).resolve().parents[3]

Answer = Result | Callable[[list[str], bytes | None], Result]

READ_ONLY = (
    ("kind", "get"),
    ("kind", "version"),
    ("kubectl", "version"),
    ("helm", "version"),
    ("docker", "info"),
    ("docker", "ps"),
    ("docker", "inspect"),
    ("docker", "compose", "version"),
    ("kubectl", "config", "get-contexts"),
    ("kubectl", "config", "view"),
)


def ok(stdout: str | bytes = "") -> Result:
    return Result(0, stdout.encode() if isinstance(stdout, str) else stdout, "")


def fail(stderr: str = "boom", code: int = 1) -> Result:
    return Result(code, b"", stderr)


class FakeRunner(Runner):
    def __init__(self, tools: Sequence[str] = ("docker", "kind", "kubectl", "helm")) -> None:
        self.tools = set(tools)
        self.calls: list[list[str]] = []
        self.inputs: list[bytes | None] = []
        self.rules: list[tuple[tuple[str, ...], Answer]] = []
        self.envs: list[object] = []
        self.helm_envs: list[object] = []

    def on(self, *prefix: str, answer: Answer) -> None:
        """Later rules win, so tests can override defaults."""
        self.rules.insert(0, (prefix, answer))

    def which(self, name: str) -> str | None:
        return f"/usr/bin/{name}" if name in self.tools else None

    def _answer(self, argv: list[str], input: bytes | None) -> Result:
        for prefix, answer in self.rules:
            if tuple(argv[: len(prefix)]) == prefix or _contains(argv, prefix):
                return answer(argv, input) if callable(answer) else answer
        return ok()

    def run(
        self,
        argv: Sequence[str],
        *,
        input: bytes | None = None,
        check: bool = True,
        timeout: float | None = 120,
        env: object = None,
    ) -> Result:
        argv = list(argv)
        if argv[0] == "helm":
            self.helm_envs.append(env)
        assert all(isinstance(a, str) for a in argv), argv
        self.calls.append(argv)
        self.inputs.append(input)
        result = self._answer(argv, input)
        if check and not result.ok:
            raise CommandError(argv, result)
        return result

    def stream(self, argv: Sequence[str], *, timeout: float | None = 1800, env: object = None) -> None:
        self.envs.append(env)
        self.run(argv, env=env)

    def writes(self) -> list[list[str]]:
        return [c for c in self.calls if not is_read_only(c)]


def _contains(argv: list[str], prefix: tuple[str, ...]) -> bool:
    """Match a subsequence anywhere (e.g. compose subcommands after the fixed flags)."""
    n = len(prefix)
    return n > 1 and any(tuple(argv[i : i + n]) == prefix for i in range(len(argv) - n + 1))


def is_read_only(argv: list[str]) -> bool:
    if tuple(argv[:2]) in {r[:2] for r in READ_ONLY if len(r) == 2} or tuple(argv[:3]) in READ_ONLY:
        return True
    if argv[0] == "kubectl" and len(argv) > 3:
        verb = argv[3] if argv[3] not in ("-n",) else argv[5]
        return verb in {"get", "auth"}
    if argv[:2] == ["docker", "compose"]:
        return "ps" in argv or "logs" in argv
    return False


def paths(tmp: Path) -> Paths:
    return Paths(root=ROOT, home=tmp / "home")


class TTY(io.StringIO):
    def isatty(self) -> bool:
        return True


class NoTTY(io.StringIO):
    def isatty(self) -> bool:
        return False
