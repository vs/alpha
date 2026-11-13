"""The secrets check: a betterleaks command on the files git doesn't ignore.

Usage, from the repo root: secret_scan.py betterleaks dir <flags...>
`betterleaks dir` reads gitignored files too (.env, .venv, a folder ignored by
its own .gitignore), where local secrets belong. So the scan gets only what
`git ls-files` lists: tracked files, and untracked ones git doesn't ignore.
Stdlib only.
"""

import shutil
import subprocess
import sys

BATCH = 1000  # paths per run, well under the OS limit on argument length


def listed_files() -> list[str] | None:
    listed = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        capture_output=True,
    )
    if listed.returncode != 0:
        why = listed.stderr.decode(errors="replace").strip()
        print(f"alpha: git ls-files failed: {why}")
        print("  Run the secrets check from the root of the git repository.")
        return None
    return [f for f in listed.stdout.decode(errors="surrogateescape").split("\0") if f]


def main(command: list[str]) -> int:
    if not command:
        print("usage: secret_scan.py betterleaks dir <flags...>")
        return 2
    if shutil.which(command[0]) is None:
        print(f"alpha: {command[0]} is not installed; run: mise install")
        return 1
    files = listed_files()
    if files is None:
        return 2
    if not files:
        print("alpha: git lists no files; nothing to scan for secrets")
        return 0
    worst = 0
    for start in range(0, len(files), BATCH):
        batch = files[start : start + BATCH]
        code = subprocess.run([*command, "--", *batch]).returncode
        worst = worst or code
    return worst


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
