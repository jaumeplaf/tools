"""
Discard git changes of UE5 World Partition actor files whose ActorLabel matches a string.

World Partition stores one .uasset per actor (One File Per Actor) with a random file
name, so the actor's real name is only found inside the binary (ActorLabel). This
script lists every changed file in the repo, resolves each actor label (from the
working copy and from HEAD, so deleted / renamed actors are found too), asks for a
search string, shows the matches and, after confirmation, discards their changes:

  - modified / deleted / renamed-from  -> restored to HEAD (index + working tree)
  - untracked / newly added            -> unstaged and deleted from disk

Usage:
  SourceTree custom action:  Script: discard_actor_by_name.exe   Parameters: "$REPO"
  GitHub Desktop / manual:   run it from inside the repo (or pass the repo path)

  Optional arguments:
    --name <text>           skip the prompt and use <text>
    --yes                   don't ask for confirmation
    --include-non-uasset    also consider non-.uasset files (matched by file name only)
    --dry-run               only list what would be discarded

Matching is case-insensitive "contains". Use * and ? for wildcards (e.g. flower_0*).
Search terms separated by commas are OR'ed (e.g. "flower, rock_big").
"""

import sys
import re
import os
import subprocess
from fnmatch import fnmatch
from pathlib import Path


# ---------------------------------------------------------------- label parsing

def extract_actor_label_from_bytes(data):
    # World Partition actor files are binary; mine printable strings.
    strings = re.findall(rb"[\x20-\x7E]{4,}", data)
    strings = [s.decode("utf-8", errors="ignore") for s in strings]

    matches = []
    # "ActorLabel" is typically followed by its value.
    for i in range(len(strings) - 1):
        if strings[i] == "ActorLabel":
            value = strings[i + 1]
            if value not in ("ActorMetaData", "None"):
                matches.append(value)

    # UE often stores a schema/default first and the real label second.
    if len(matches) >= 2:
        return matches[1]
    if len(matches) == 1:
        return matches[0]
    return None


# ---------------------------------------------------------------- git helpers

def git(repo, *args, input_bytes=None, check=True):
    result = subprocess.run(
        ["git", "-C", str(repo), "--literal-pathspecs", *args],
        input=input_bytes,
        capture_output=True,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed:\n{result.stderr.decode(errors='ignore')}"
        )
    return result


def find_repo_root(start):
    r = subprocess.run(
        ["git", "-C", str(start), "rev-parse", "--show-toplevel"],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        return None
    return Path(r.stdout.strip())


class Change:
    def __init__(self, xy, path, orig_path=None):
        self.xy = xy                # two-letter porcelain status, e.g. " M", "D ", "??"
        self.path = path            # repo-relative, forward slashes
        self.orig_path = orig_path  # for renames/copies: path in HEAD
        self.labels = []            # labels found (working copy and/or HEAD)

    @property
    def is_untracked(self):
        return self.xy == "??"

    @property
    def is_new(self):
        # Not present in HEAD under this path.
        return self.is_untracked or self.xy[0] in ("A", "R", "C")

    def describe(self):
        x, y = self.xy[0], self.xy[1]
        if self.xy == "??":
            return "new"
        if "D" in (x, y):
            return "deleted"
        if x == "A":
            return "added"
        if x == "R":
            return "renamed"
        return "modified"


def list_changes(repo):
    # -z: NUL separated, no quoting; -uall: list every untracked file, not just dirs.
    out = git(repo, "status", "--porcelain=v1", "-z", "-uall").stdout
    entries = out.split(b"\0")
    changes = []
    i = 0
    while i < len(entries):
        entry = entries[i]
        i += 1
        if len(entry) < 4:
            continue
        xy = entry[:2].decode()
        path = entry[3:].decode("utf-8", errors="surrogateescape")
        orig = None
        if xy[0] in ("R", "C"):
            # Next entry is the original path.
            orig = entries[i].decode("utf-8", errors="surrogateescape")
            i += 1
        if xy == "!!":
            continue
        changes.append(Change(xy, path, orig))
    return changes


def read_head_blobs(repo, paths):
    """Return {path: bytes} for paths that exist in HEAD, using one cat-file process."""
    if not paths:
        return {}
    proc = subprocess.Popen(
        ["git", "-C", str(repo), "cat-file", "--batch"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    blobs = {}
    try:
        for p in paths:
            proc.stdin.write(f"HEAD:{p}\n".encode("utf-8", errors="surrogateescape"))
            proc.stdin.flush()
            header = proc.stdout.readline().decode(errors="ignore").strip()
            if header.endswith("missing") or header.endswith("ambiguous"):
                continue
            parts = header.split()
            if len(parts) < 3:
                continue
            size = int(parts[2])
            data = proc.stdout.read(size)
            proc.stdout.read(1)  # trailing newline
            blobs[p] = data
    finally:
        proc.stdin.close()
        proc.wait()
    return blobs


def nul_list(paths):
    return b"".join(p.encode("utf-8", errors="surrogateescape") + b"\0" for p in paths)


# ---------------------------------------------------------------- matching

def build_matcher(text):
    terms = [t.strip().lower() for t in text.split(",") if t.strip()]

    def matches(value):
        v = value.lower()
        for t in terms:
            if "*" in t or "?" in t:
                if fnmatch(v, f"*{t}*"):
                    return True
            elif t in v:
                return True
        return False

    return matches, terms


# ---------------------------------------------------------------- discard

def discard(repo, changes):
    restore_paths = []  # exist in HEAD -> restore index + worktree from HEAD
    remove_paths = []   # not in HEAD   -> unstage (if staged) and delete

    for c in changes:
        if c.is_new:
            remove_paths.append(c.path)
            if c.orig_path and c.xy[0] == "R":
                restore_paths.append(c.orig_path)
        else:
            restore_paths.append(c.path)

    if restore_paths:
        git(repo, "restore", "--source=HEAD", "--staged", "--worktree",
            "--pathspec-from-file=-", "--pathspec-file-nul",
            input_bytes=nul_list(restore_paths))

    staged_new = [c.path for c in changes if c.is_new and not c.is_untracked]
    if staged_new:
        git(repo, "rm", "--cached", "-q", "-f", "--ignore-unmatch",
            "--pathspec-from-file=-", "--pathspec-file-nul",
            input_bytes=nul_list(staged_new))

    failed = []
    for p in remove_paths:
        fp = repo / p
        try:
            if fp.exists():
                fp.unlink()
            # Clean up now-empty parent folders (UE leaves deep hashed dirs).
            parent = fp.parent
            while parent != repo and parent.exists() and not any(parent.iterdir()):
                parent.rmdir()
                parent = parent.parent
        except OSError as e:
            failed.append(f"{p}: {e}")

    return len(restore_paths), len(remove_paths), failed


# ---------------------------------------------------------------- main

def wait_exit(interactive):
    if interactive:
        try:
            input("\nPress Enter to close...")
        except EOFError:
            pass


def main():
    argv = sys.argv[1:]
    flags = {"--yes", "--include-non-uasset", "--dry-run", "--pause"}
    name_arg = None
    rest = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--name" and i + 1 < len(argv):
            name_arg = argv[i + 1]
            i += 2
            continue
        if a not in flags:
            rest.append(a)
        i += 1

    assume_yes = "--yes" in argv
    include_non_uasset = "--include-non-uasset" in argv
    dry_run = "--dry-run" in argv
    interactive = sys.stdin is not None and sys.stdin.isatty()

    start = Path(rest[0]) if rest else Path.cwd()
    repo = find_repo_root(start)
    if repo is None and interactive:
        typed = input("Not inside a git repo. Repo path: ").strip().strip('"')
        repo = find_repo_root(Path(typed)) if typed else None
    if repo is None:
        print("Could not find a git repository.")
        wait_exit(interactive)
        return 1

    print(f"Repo: {repo}")
    print("Reading changed files...")
    changes = list_changes(repo)

    if not include_non_uasset:
        changes = [c for c in changes if c.path.lower().endswith(".uasset")]

    if not changes:
        print("No changed .uasset files.")
        wait_exit(interactive)
        return 0

    # Labels from the working copy.
    for c in changes:
        fp = repo / c.path
        if fp.is_file() and fp.suffix.lower() == ".uasset":
            try:
                label = extract_actor_label_from_bytes(fp.read_bytes())
                if label:
                    c.labels.append(label)
            except OSError:
                pass

    # Labels from HEAD (needed for deleted actors, and catches renamed labels).
    head_paths = {}
    for c in changes:
        if not c.is_new:
            head_paths[c.path] = c
        elif c.orig_path:
            head_paths[c.orig_path] = c
    blobs = read_head_blobs(repo, list(head_paths))
    for p, data in blobs.items():
        if p.lower().endswith(".uasset"):
            label = extract_actor_label_from_bytes(data)
            c = head_paths[p]
            if label and label not in c.labels:
                c.labels.append(label)

    print(f"{len(changes)} changed file(s) scanned.\n")

    query = name_arg
    if query is None:
        if not interactive:
            print("No --name given and no console to prompt.")
            return 1
        query = input("Discard changes of actors whose name contains: ").strip()
    if not query:
        print("Nothing entered, aborting.")
        wait_exit(interactive)
        return 0

    matches, _ = build_matcher(query)
    selected = [
        c for c in changes
        if any(matches(l) for l in c.labels) or matches(Path(c.path).stem)
    ]

    if not selected:
        print(f'No changed actors match "{query}".')
        wait_exit(interactive)
        return 0

    print(f'\n{len(selected)} file(s) match "{query}":\n')
    for c in sorted(selected, key=lambda c: (c.labels[0] if c.labels else "").lower()):
        label = " / ".join(c.labels) if c.labels else "(no label)"
        print(f"  [{c.describe():8}] {label:40}  {Path(c.path).name}")

    if dry_run:
        print("\nDry run, nothing changed.")
        wait_exit(interactive)
        return 0

    if not assume_yes:
        answer = input(f"\nDiscard ALL changes of these {len(selected)} file(s)? "
                       "This cannot be undone. [y/N]: ").strip().lower()
        if answer not in ("y", "yes"):
            print("Cancelled.")
            wait_exit(interactive)
            return 0

    try:
        restored, removed, failed = discard(repo, selected)
    except RuntimeError as e:
        print(f"\nERROR: {e}")
        wait_exit(interactive)
        return 1

    print(f"\nDone. Restored {restored} file(s) to HEAD, removed {removed} new file(s).")
    for f in failed:
        print(f"  could not delete {f}")

    wait_exit(interactive)
    return 0


if __name__ == "__main__":
    sys.exit(main())
