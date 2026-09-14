#!/usr/bin/env python3
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) \
    if os.path.basename(os.path.dirname(os.path.abspath(__file__))) == "scripts" \
    else os.getcwd()

README_PATH = os.path.join(REPO_ROOT, "README.md")
MARKER = "## Scripts"

EXCLUDE_DIRS = {".git", ".github", "__pycache__", "node_modules", ".venv", "venv"}
EXCLUDE_FILES = {os.path.basename(__file__)}

LANG_STYLE = {
    ".py": "python",
    ".js": "c-style",
    ".ts": "c-style",
    ".jsx": "c-style",
    ".tsx": "c-style",
    ".go": "c-style",
    ".c": "c-style",
    ".h": "c-style",
    ".cpp": "c-style",
    ".hpp": "c-style",
    ".java": "c-style",
    ".rs": "c-style",
    ".php": "c-style",
    ".cs": "c-style",
    ".sh": "hash",
    ".bash": "hash",
    ".zsh": "hash",
    ".rb": "hash",
    ".pl": "hash",
}


def find_scripts(root):
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS and not d.startswith(".")]
        for fname in filenames:
            if fname in EXCLUDE_FILES:
                continue
            ext = os.path.splitext(fname)[1].lower()
            if ext in LANG_STYLE:
                found.append(os.path.join(dirpath, fname))
    return sorted(found)


def strip_shebang(lines):
    idx = 0
    if lines and lines[0].startswith("#!"):
        idx = 1
    while idx < len(lines) and lines[idx].strip() == "":
        idx += 1
    return idx


def extract_python_docstring(lines, idx):
    if idx >= len(lines):
        return None
    line = lines[idx]
    stripped = line.strip()
    quote = None
    for q in ('"""', "'''"):
        if stripped.startswith(q):
            quote = q
            break
    if quote is None:
        return None

    rest_of_line = stripped[len(quote):]
    if quote in rest_of_line:
        return rest_of_line.split(quote)[0].strip()

    body = [rest_of_line] if rest_of_line.strip() else []
    for line in lines[idx + 1:]:
        if quote in line:
            body.append(line.split(quote)[0])
            break
        body.append(line.rstrip("\n"))
    return "\n".join(body).strip()


def extract_c_style_block(lines, idx):
    if idx >= len(lines):
        return None
    stripped = lines[idx].strip()
    if not stripped.startswith("/*"):
        return None

    rest_of_line = stripped[2:]
    if "*/" in rest_of_line:
        return rest_of_line.split("*/")[0].strip(" *")

    body = [rest_of_line] if rest_of_line.strip() else []
    for line in lines[idx + 1:]:
        if "*/" in line:
            body.append(line.split("*/")[0])
            break
        cleaned = line.rstrip("\n")
        cleaned = re.sub(r"^\s*\*\s?", "", cleaned)
        body.append(cleaned)
    return "\n".join(body).strip()


def extract_hash_block(lines, idx):
    body = []
    for line in lines[idx:]:
        stripped = line.rstrip("\n")
        if not stripped.strip().startswith("#"):
            break
        body.append(re.sub(r"^\s*#!?\s?", "", stripped))
    if not body:
        return None
    return "\n".join(body).strip()


def extract_description(filepath):
    ext = os.path.splitext(filepath)[1].lower()
    style = LANG_STYLE.get(ext)
    if style is None:
        return None

    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    idx = strip_shebang(lines)

    if style == "python":
        return extract_python_docstring(lines, idx)
    if style == "c-style":
        return extract_c_style_block(lines, idx)
    if style == "hash":
        return extract_hash_block(lines, idx)
    return None


def build_scripts_section(root):
    entries = []
    for path in find_scripts(root):
        rel = os.path.relpath(path, root)
        desc = extract_description(path)
        entries.append((rel, desc))

    lines = [MARKER, ""]
    if not entries:
        lines.append("_No scripts found yet._")
        lines.append("")
        return "\n".join(lines)

    for rel, desc in entries:
        lines.append(f"### `{rel}`")
        lines.append("")
        if desc:
            lines.append("```")
            lines.append(desc)
            lines.append("```")
        else:
            lines.append("_No description found._")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def update_readme(root):
    if not os.path.exists(README_PATH):
        print(f"README.md not found at {README_PATH}", file=sys.stderr)
        sys.exit(1)

    with open(README_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    if MARKER not in content:
        print(f"Marker '{MARKER}' not found in README.md", file=sys.stderr)
        sys.exit(1)

    before = content.split(MARKER, 1)[0].rstrip() + "\n\n"
    section = build_scripts_section(root)
    new_content = before + section

    if new_content != content:
        with open(README_PATH, "w", encoding="utf-8") as f:
            f.write(new_content)
        print("README.md updated.")
        return True

    print("README.md already up to date.")
    return False


if __name__ == "__main__":
    update_readme(REPO_ROOT)