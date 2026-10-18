"""The only way tools/ar runs programs: fixed argv lists, never a shell.

Every external command the CLI can run is built in code from constants and validated
values; nothing typed by a user is passed through as a command or manifest.
"""

import shutil
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Result:
    returncode: int
    stdout_bytes: bytes
    stderr: str

    @property
    def stdout(self) -> str:
        return self.stdout_bytes.decode(errors="replace")

    @property
    def ok(self) -> bool:
        return self.returncode == 0


class CommandError(Exception):
    def __init__(self, argv: Sequence[str], result: Result) -> None:
        self.argv = list(argv)
        self.result = result
        last = (result.stderr.strip() or result.stdout.strip()).splitlines()
        reason = last[-1] if last else f"exit status {result.returncode}"
        super().__init__(f"`{' '.join(argv[:3])} …` failed: {reason}")


class Runner:
    def which(self, name: str) -> str | None:
        return shutil.which(name)

    def run(
        self,
        argv: Sequence[str],
        *,
        input: bytes | None = None,
        check: bool = True,
        timeout: float | None = 120,
        env: Mapping[str, str] | None = None,
    ) -> Result:
        """Run and capture output."""
        try:
            done = subprocess.run(
                list(argv),
                input=input,
                capture_output=True,
                timeout=timeout,
                check=False,
                env=dict(env) if env is not None else None,
            )
        except FileNotFoundError:
            result = Result(127, b"", f"{argv[0]}: command not found")
        except subprocess.TimeoutExpired:
            result = Result(124, b"", f"timed out after {timeout:.0f}s")
        else:
            result = Result(done.returncode, done.stdout, done.stderr.decode(errors="replace"))
        if check and not result.ok:
            raise CommandError(argv, result)
        return result

    def stream(self, argv: Sequence[str], *, timeout: float | None = 1800) -> None:
        """Run with output shown to the user (long steps: builds, helm, kind create)."""
        try:
            code = subprocess.run(list(argv), timeout=timeout, check=False).returncode
        except FileNotFoundError:
            code = 127
        except subprocess.TimeoutExpired:
            code = 124
        if code != 0:
            raise CommandError(argv, Result(code, b"", f"exit status {code}"))
