"""Mechanical doc-drift checks; verify.sh runs this on every push.

Checks that the doc set stays fixed (CONTRIBUTING.md "Keeping docs useful"), that relative links and
heading anchors resolve, that code paths named in CONTRIBUTING.md / architecture.md exist, that every
module appears in the architecture code map, and that every async task type is documented in api.md.
This only catches drift that can be detected mechanically; the end-of-phase review in CONTRIBUTING.md
covers the rest.
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROOT_DOCS = {"README.md", "CONTRIBUTING.md"}
DOCS = {"architecture.md", "api.md", "error-codes.md", "operations.md", "usage.md", "roadmap.md"}
GENERATED = {"openapi.json", "route-inventory.json"}
CODE_DIRS = ("app", "core", "adapters")

LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)\)")
CODE_SPAN = re.compile(r"`([^`\n]+)`")
PATH_LIKE = re.compile(r"^[\w.{},*-]+(/[\w.{},*-]*)+$")
BRACES = re.compile(r"\{([^{}]*)\}")


def slugify(heading: str) -> str:
    """GitHub-style anchor for a Markdown heading."""
    text = re.sub(r"[`*_\[\]()]", "", heading.strip().lower())
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def anchors(path: Path) -> set[str]:
    text = re.sub(r"```.*?```", "", path.read_text(encoding="utf-8"), flags=re.S)
    return {slugify(m.group(1)) for m in re.finditer(r"^#{1,6}\s+(.+?)\s*#*$", text, re.M)}


def expand(pattern: str) -> list[str]:
    match = BRACES.search(pattern)
    if not match:
        return [pattern]
    head, tail = pattern[: match.start()], pattern[match.end() :]
    return [variant for option in match.group(1).split(",") for variant in expand(head + option + tail)]


def git_ignored(path: str) -> bool:
    return subprocess.run(["git", "check-ignore", "-q", path], cwd=ROOT, check=False).returncode == 0


def markdown_files() -> list[Path]:
    return sorted([*(ROOT / name for name in ROOT_DOCS), *(ROOT / "docs").rglob("*.md")])


def check_doc_set(errors: list[str]) -> None:
    tracked = subprocess.run(["git", "ls-files", "*.md"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    root_md = {name for name in tracked.split() if "/" not in name}
    if root_md != ROOT_DOCS:
        errors.append(f"root Markdown files must be exactly {sorted(ROOT_DOCS)}, found {sorted(root_md)}")
    docs_files = {p.name for p in (ROOT / "docs").iterdir() if p.is_file()}
    if extra := docs_files - DOCS - GENERATED:
        errors.append(f"unexpected files in docs/ (extend an existing doc instead): {sorted(extra)}")
    if missing := DOCS - docs_files:
        errors.append(f"missing docs: {sorted(missing)}")
    adrs = sorted(p.name for p in (ROOT / "docs" / "adr").glob("*.md"))
    numbers = [int(m.group(1)) for name in adrs if (m := re.match(r"ADR-(\d{3})-[\w-]+\.md$", name))]
    if len(numbers) != len(adrs) or numbers != list(range(1, len(numbers) + 1)):
        errors.append(f"ADRs must be named ADR-NNN-slug.md and numbered 001.. without gaps: {adrs}")


def check_links(errors: list[str]) -> None:
    for doc in markdown_files():
        for target in LINK.findall(doc.read_text(encoding="utf-8")):
            if re.match(r"^[a-z]+:", target):  # http:, https:, mailto:
                continue
            file_part, _, anchor = target.partition("#")
            resolved = (doc.parent / file_part).resolve() if file_part else doc
            name = f"{doc.relative_to(ROOT)} -> {target}"
            if not resolved.exists():
                errors.append(f"broken link: {name}")
            elif anchor and resolved.suffix == ".md" and anchor not in anchors(resolved):
                errors.append(f"missing anchor: {name}")


def check_code_paths(errors: list[str]) -> None:
    for doc in (ROOT / "CONTRIBUTING.md", ROOT / "docs" / "architecture.md"):
        for span in CODE_SPAN.findall(doc.read_text(encoding="utf-8")):
            candidate = span.split()[0].split("#")[0].split(":")[0].rstrip(",")
            # Only repo-rooted paths: skips "POST/PUT", relative partial names and NNN placeholders.
            if not PATH_LIKE.match(candidate) or "NNN" in candidate:
                continue
            if not (ROOT / candidate.split("/")[0]).exists():
                continue
            for path in expand(candidate):
                if "*" in path:
                    found = any(ROOT.glob(path))
                else:
                    found = (ROOT / path).exists() or git_ignored(path)
                if not found:
                    errors.append(f"{doc.relative_to(ROOT)} names a path that does not exist: {path}")


def check_code_map(errors: list[str]) -> None:
    architecture = (ROOT / "docs" / "architecture.md").read_text(encoding="utf-8")
    for base in CODE_DIRS:
        for path in sorted((ROOT / base).rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            rel = path.relative_to(ROOT)
            # A sub-package (core/db, core/export, ...) only needs its folder mentioned.
            if len(rel.parts) > 2 and rel.parts[1] != "route_groups":
                name = rel.parts[1]
            elif path.stem == "__init__":
                continue
            else:
                name = path.stem
            if not re.search(rf"\b{re.escape(name)}\b", architecture):
                errors.append(f"docs/architecture.md code map does not mention {rel}")


def check_task_types(errors: list[str]) -> None:
    tree = ast.parse((ROOT / "core" / "task_service.py").read_text(encoding="utf-8"))
    api_doc = (ROOT / "docs" / "api.md").read_text(encoding="utf-8")
    for node in ast.walk(tree):
        if not (isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)):
            continue
        if node.target.id == "TASK_HANDLERS" and isinstance(node.value, ast.Dict):
            for key in node.value.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str) and f"`{key.value}`" not in api_doc:
                    errors.append(f"docs/api.md does not document task type `{key.value}`")


def main() -> int:
    errors: list[str] = []
    for check in (check_doc_set, check_links, check_code_paths, check_code_map, check_task_types):
        check(errors)
    for error in errors:
        print(f"docs: {error}", file=sys.stderr)
    if errors:
        return 1
    print("docs OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
