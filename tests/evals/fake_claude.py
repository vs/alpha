"""A stand-in for `claude -p`: logs each call and replays scripted replies.

$FAKE_CLAUDE_DIR/replies.jsonl holds one reply per line, consumed in order:
{"stdout": <object or string>, "exit": 0, "stderr": "", "run": <shell or null>}.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

folder = Path(os.environ["FAKE_CLAUDE_DIR"])
prompt = sys.stdin.read()
with (folder / "calls.jsonl").open("a") as log:
    log.write(
        json.dumps({"argv": sys.argv[1:], "cwd": os.getcwd(), "stdin": prompt}) + "\n"
    )
replies = (folder / "replies.jsonl").read_text().splitlines()
if not replies:
    sys.exit("fake claude: no reply left")
(folder / "replies.jsonl").write_text("".join(line + "\n" for line in replies[1:]))
reply = json.loads(replies[0])
if reply.get("run"):
    subprocess.run(reply["run"], shell=True, check=True)
out = reply.get("stdout", "")
sys.stdout.write(out if isinstance(out, str) else json.dumps(out))
sys.stderr.write(reply.get("stderr", ""))
sys.exit(reply.get("exit", 0))
