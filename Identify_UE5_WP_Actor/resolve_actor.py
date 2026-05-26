import sys
import re
import subprocess
from pathlib import Path

def extract_actor_label(file_path):
    # World Partition actor files are binary; read raw bytes and mine printable strings.
    with open(file_path, "rb") as f:
        data = f.read()

    # Keep ASCII-ish sequences of length >= 4 to reduce garbage.
    strings = re.findall(rb"[\x20-\x7E]{4,}", data)
    strings = [s.decode("utf-8", errors="ignore") for s in strings]

    matches = []

    # In these files, "ActorLabel" is typically followed by its value.
    for i in range(len(strings) - 1):
        if strings[i] == "ActorLabel":
            value = strings[i + 1]

            # Filter known non-label tokens that appear near metadata.
            if value not in ("ActorMetaData", "None"):
                matches.append(value)

    # UE often stores a schema/default first and the real label second.
    if len(matches) >= 2:
        return matches[1]

    if len(matches) == 1:
        return matches[0]

    return "NOT_FOUND"


def parse_selected_files(argv):
    # Expected SourceTree parameters: "$REPO" "$FILE"
    # Fallback: also supports direct file paths in argv.
    repo_path = None
    raw_file_tokens = []

    if len(argv) >= 3:
        repo_path = Path(argv[1])
        raw_file_tokens = argv[2:]
    elif len(argv) == 2:
        raw_file_tokens = [argv[1]]
    else:
        return []

    files = []

    for token in raw_file_tokens:
        # SourceTree may provide multiple selected files in one argument.
        # Split on newline or semicolon and ignore empty entries.
        parts = [p.strip() for p in re.split(r"[\r\n;]+", token) if p.strip()]

        for part in parts:
            p = Path(part)

            if not p.is_absolute() and repo_path is not None:
                p = repo_path / p

            files.append(p)

    # Keep order, remove duplicates.
    deduped = []
    seen = set()
    for p in files:
        key = str(p).lower()
        if key not in seen:
            deduped.append(p)
            seen.add(key)

    return deduped


def list_changed_files(repo_path):
    # Includes staged, unstaged, and untracked files.
    cmd = ["git", "-C", str(repo_path), "status", "--porcelain"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return []

    files = []
    for line in result.stdout.splitlines():
        if len(line) < 4:
            continue

        path_part = line[3:]
        if " -> " in path_part:
            path_part = path_part.split(" -> ", 1)[1]

        files.append(repo_path / path_part)

    deduped = []
    seen = set()
    for p in files:
        key = str(p).lower()
        if key not in seen:
            deduped.append(p)
            seen.add(key)

    return deduped

def main():
    pause = "--pause" in sys.argv[1:]
    all_changed = "--all-changed" in sys.argv[1:]
    include_non_uasset = "--include-non-uasset" in sys.argv[1:]
    args = [
        sys.argv[0]
    ] + [
        a
        for a in sys.argv[1:]
        if a not in ("--pause", "--all-changed", "--include-non-uasset")
    ]

    # SourceTree can pass one file or many selected files depending on config.
    if len(args) < 2:
        print("No file provided")
        if pause:
            input()
        return

    file_paths = parse_selected_files(args)
    if all_changed and len(args) >= 2:
        repo_path = Path(args[1])
        if repo_path.exists():
            file_paths = list_changed_files(repo_path)

    if not file_paths:
        print("No files could be parsed from arguments")
        if pause:
            input()
        return

    for file_path in file_paths:
        file_name = file_path.stem

        if not file_path.exists():
            print(f"{file_name} → FILE_NOT_FOUND")
            continue

        if not file_path.is_file():
            continue

        if not include_non_uasset and file_path.suffix.lower() != ".uasset":
            continue

        try:
            label = extract_actor_label(file_path)
        except OSError:
            print(f"{file_name} → READ_ERROR")
            continue

        # Keep output compact: one line per file for quick scanning.
        print(f"{file_name} → {label}")

    print()

    # Optional pause mode for manual runs from a GUI shell.
    if pause:
        input("Press Enter to close...")

if __name__ == "__main__":
    main()