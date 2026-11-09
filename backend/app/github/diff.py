"""Parse a unified diff into what the PR check needs: each file's new-side lines."""

import re
from dataclasses import dataclass, field

HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


@dataclass
class FileDiff:
    path: str
    added: dict[int, str] = field(default_factory=dict)  # new line number -> text
    context: dict[int, str] = field(default_factory=dict)

    def new_lines(self) -> set[int]:
        return set(self.added) | set(self.context)


@dataclass
class Diff:
    files: dict[str, FileDiff]
    raw: str

    def has_lines(self, path: str, start: int, end: int) -> bool:
        """True when every line in [start, end] is on the new side of a hunk and one was added."""
        file = self.files.get(path)
        if file is None or start < 1 or end < start:
            return False
        lines = set(range(start, end + 1))
        return lines <= file.new_lines() and bool(lines & set(file.added))

    def numbered(self) -> str:
        """The diff with new-side line numbers, so a model can cite real lines."""
        out: list[str] = []
        for file in self.files.values():
            out.append(f"--- {file.path}")
            for n in sorted(file.new_lines()):
                marker = "+" if n in file.added else " "
                out.append(f"{n:>5} {marker} {file.added.get(n, file.context.get(n, ''))}")
        return "\n".join(out)


def parse_diff(raw: str) -> Diff:
    files: dict[str, FileDiff] = {}
    current: FileDiff | None = None
    line_no = 0
    for line in raw.splitlines():
        if line.startswith("+++ "):
            path = line[4:].strip()
            if path == "/dev/null":
                current = None
                continue
            path = path[2:] if path.startswith("b/") else path
            current = files.setdefault(path, FileDiff(path))
            continue
        if line.startswith(("--- ", "diff --git", "index ", "new file", "deleted file")):
            continue
        match = HUNK.match(line)
        if match:
            line_no = int(match.group(1))
            continue
        if current is None:
            continue
        if line.startswith("+"):
            current.added[line_no] = line[1:]
            line_no += 1
        elif line.startswith(" "):
            current.context[line_no] = line[1:]
            line_no += 1
        elif line.startswith("-") or line.startswith("\\"):
            continue
    return Diff(files=files, raw=raw)
