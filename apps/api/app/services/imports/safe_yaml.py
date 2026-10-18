"""A YAML loader for untrusted import files: data only, bounded, unambiguous.

On top of PyYAML's SafeLoader (plain data types, no object construction):
  - a byte limit before parsing and a document limit while parsing;
  - no aliases (`*ref`): they allow exponential expansion ("billion laughs");
  - a nesting depth limit;
  - duplicate mapping keys and non-string keys are errors, not "last one wins";
  - custom tags (`!reset`, `!override`, `!!python/...`) are errors.
Nothing is ever executed, interpolated or read from disk.
"""

from typing import Any

import yaml
from yaml.constructor import ConstructorError
from yaml.events import AliasEvent
from yaml.nodes import MappingNode, Node

MAX_BYTES = 256 * 1024
MAX_DOCUMENTS = 50
MAX_DEPTH = 32


class YamlInputError(Exception):
    """The input is not acceptable YAML; the message is safe to show (no content)."""


class _Loader(yaml.SafeLoader):
    def __init__(self, stream: str) -> None:
        super().__init__(stream)
        self._depth = 0

    def compose_node(self, parent: Node | None, index: Any) -> Node | None:
        if self.check_event(AliasEvent):
            event = self.peek_event()
            raise YamlInputError(
                f"YAML aliases (*{event.anchor}) are not supported (line "
                f"{event.start_mark.line + 1}); write the values out instead"
            )
        self._depth += 1
        if self._depth > MAX_DEPTH:
            raise YamlInputError(f"Nesting deeper than {MAX_DEPTH} levels")
        try:
            return super().compose_node(parent, index)  # type: ignore[no-any-return]
        finally:
            self._depth -= 1

    def construct_mapping(self, node: Node, deep: bool = False) -> dict[Any, Any]:
        if isinstance(node, MappingNode):
            seen: set[str] = set()
            for key_node, _ in node.value:
                if key_node.tag == "tag:yaml.org,2002:merge":
                    raise YamlInputError(
                        f"YAML merge keys (<<) are not supported (line "
                        f"{key_node.start_mark.line + 1})"
                    )
                key = self.construct_object(key_node, deep=True)
                if not isinstance(key, str):
                    raise YamlInputError(
                        f"Non-string mapping key at line {key_node.start_mark.line + 1}"
                    )
                if key in seen:
                    raise YamlInputError(
                        f"Duplicate key {key!r} at line {key_node.start_mark.line + 1}"
                    )
                seen.add(key)
        return super().construct_mapping(node, deep=deep)  # type: ignore[arg-type]


def load_documents(text: str, max_documents: int = MAX_DOCUMENTS) -> list[Any]:
    """All documents in `text`, empty ones skipped. Raises YamlInputError."""
    size = len(text.encode())
    if size > MAX_BYTES:
        raise YamlInputError(
            f"The file is {size // 1024} KiB; imports are limited to "
            f"{MAX_BYTES // 1024} KiB"
        )
    if "\x00" in text:
        raise YamlInputError("The file contains NUL bytes; it is not a text file")
    loader = _Loader(text)
    documents: list[Any] = []
    try:
        while loader.check_node():
            if len(documents) >= max_documents:
                raise YamlInputError(f"More than {max_documents} YAML documents")
            document = loader.construct_document(loader.get_node())
            if document is not None:
                documents.append(document)
    except ConstructorError as exc:
        mark = exc.problem_mark
        where = f" (line {mark.line + 1})" if mark else ""
        raise YamlInputError(
            f"Unsupported YAML tag or value{where}: only plain data is accepted"
        ) from None
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = f" at line {mark.line + 1}, column {mark.column + 1}" if mark else ""
        problem = getattr(exc, "problem", None) or "invalid YAML"
        raise YamlInputError(f"Not valid YAML{where}: {problem}") from None
    finally:
        loader.dispose()
    return documents
