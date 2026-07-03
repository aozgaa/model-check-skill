#!/usr/bin/env python3
"""Claude Code hook for the model-check plugin.

PostToolUse (Write|Edit): when a .tla spec is written, remind about missing
sibling .cfg / MAPPING.md so the layout is completed before TLC runs.

Stop: block ending the turn while any TLC counterexample log lacks its
back-mapped .scenario.md — a found violation without a source-level scenario
is an incomplete result.
"""

import json
import os
import re
import sys

VIOLATION_RE = re.compile(
    r"Error: (Invariant .* is violated|Deadlock reached"
    r"|Temporal properties were violated|Action property .* is violated)"
)
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".tlc-meta"}


def post_tool_use(data):
    path = (data.get("tool_input") or {}).get("file_path") or ""
    if not path.endswith(".tla"):
        return 0
    d = os.path.dirname(os.path.abspath(path))
    if os.path.basename(d) == "traces":  # TTrace specs etc. are exempt
        return 0
    missing = []
    cfg = os.path.splitext(path)[0] + ".cfg"
    if not os.path.exists(cfg):
        missing.append(f"{os.path.basename(cfg)} (TLC config)")
    if not os.path.exists(os.path.join(d, "MAPPING.md")):
        missing.append("MAPPING.md (source <-> model mapping table)")
    if missing:
        print(
            "model-check layout: before running scripts/tlc, this model dir "
            "still needs: " + "; ".join(missing),
            file=sys.stderr,
        )
        return 2  # feed reminder back to Claude; Write itself already succeeded
    return 0


def unmapped_violations(root):
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [n for n in dirnames if n not in SKIP_DIRS]
        if os.path.basename(dirpath) != "traces":
            continue
        dirnames[:] = []  # don't descend further inside traces/
        for name in filenames:
            if not name.endswith(".log"):
                continue
            log = os.path.join(dirpath, name)
            try:
                with open(log, encoding="utf-8", errors="replace") as f:
                    if not VIOLATION_RE.search(f.read()):
                        continue
            except OSError:
                continue
            scenario = log[: -len(".log")] + ".scenario.md"
            if not os.path.exists(scenario):
                found.append((log, scenario))
    return found


def stop(data):
    if data.get("stop_hook_active"):
        return 0  # already continued once for this; don't loop forever
    pending = unmapped_violations(data.get("cwd") or os.getcwd())
    if not pending:
        return 0
    lines = [
        "model-check: TLC found counterexample(s) that are not yet mapped "
        "back to source. For each, write the .scenario.md (per-step source "
        "file:line interleaving, using the model dir's MAPPING.md) and, where "
        "feasible, an executable failing test:"
    ]
    lines += [f"  {log} -> missing {scenario}" for log, scenario in pending]
    json.dump({"decision": "block", "reason": "\n".join(lines)}, sys.stdout)
    return 0


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    event = data.get("hook_event_name", "")
    if event == "PostToolUse":
        return post_tool_use(data)
    if event in ("Stop", "SubagentStop"):
        return stop(data)
    return 0


if __name__ == "__main__":
    sys.exit(main())
