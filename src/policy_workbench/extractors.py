"""Content extraction helpers for prompt-bearing policy files."""

from __future__ import annotations


def extract_yaml_text_field(raw_yaml: str) -> str:
    """Extract prompt text from a YAML ``text`` field.

    Supported forms:
    - block scalar: ``text: |`` or ``text: >``
    - inline scalar: ``text: some value``

    The parser is intentionally narrow and deterministic: it only extracts the
    `text` value needed for prompt composition workflows and avoids introducing
    a broad YAML dependency for this single-purpose behavior.
    """

    lines = raw_yaml.splitlines()
    for index, line in enumerate(lines):
        stripped = line.lstrip()
        parent_indent = len(line) - len(stripped)

        if not stripped.startswith("text:"):
            continue

        remainder = stripped[len("text:") :].strip()

        # Inline scalar form: `text: some prompt`.
        if remainder and remainder[0] not in {"|", ">"}:
            return remainder.strip("'\"").strip()

        # Multiline scalar form. We consume indented lines until indentation
        # returns to the parent level.
        block_lines: list[str] = []
        block_indent: int | None = None

        for block_line in lines[index + 1 :]:
            block_stripped = block_line.lstrip()
            current_indent = len(block_line) - len(block_stripped)

            if block_stripped == "":
                if block_indent is not None:
                    block_lines.append("")
                continue

            if current_indent <= parent_indent:
                break

            if block_indent is None:
                block_indent = current_indent

            block_lines.append(block_line[block_indent:].rstrip())

        return "\n".join(block_lines).strip()

    return ""
