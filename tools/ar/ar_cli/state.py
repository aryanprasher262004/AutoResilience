"""~/.autoresilience/state.json: what this tool created. The source of truth for cleanup.

A cluster is deleted by `ar uninstall` only when `cluster_created_by_ar` is true, i.e.
this tool ran `kind create cluster` for it. An adopted cluster (one that already existed,
e.g. from scripts/dev-cluster.sh) is never deleted.

`imported_clusters` records each read-only discovery import (`ar cluster import`): the
cluster's fingerprint (kube-system namespace UID, checked before every write) and
whether this tool created the identity namespace there.
"""

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

SCHEMA = 1


@dataclass
class State:
    cluster_name: str | None = None
    cluster_created_by_ar: bool = False
    installed_at: str | None = None
    web_port: int = 3000
    api_port: int = 8000
    imported_clusters: list[dict[str, Any]] = field(default_factory=list)
    schema: int = SCHEMA


def load(path: Path) -> State | None:
    try:
        raw = json.loads(path.read_text())
    except FileNotFoundError:
        return None
    if not isinstance(raw, dict) or raw.get("schema") != SCHEMA:
        raise ValueError(f"{path}: unsupported state file (expected schema {SCHEMA})")
    known = {f.name for f in fields(State)}
    return State(**{k: v for k, v in raw.items() if k in known})


def save(path: Path, state: State) -> None:
    write_private(path, json.dumps(asdict(state), indent=2, sort_keys=True) + "\n")


def write_private(path: Path, content: str) -> None:
    """Write atomically, readable only by the current user (0600 on POSIX)."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as handle:
        handle.write(content)
    os.replace(tmp, path)
