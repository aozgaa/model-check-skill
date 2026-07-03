# model-check

A Claude Code plugin for debugging state machines and concurrent systems with TLA+ model
checking. LLMs are weak at exhaustively reasoning about interleavings; TLC is not.
The plugin has Claude build a TLA+ model of the code under test, checks invariants
exhaustively, and — crucially — forces every counterexample to be mapped back to
concrete source lines, an explicit interleaving scenario, and (where feasible) a failing
test.

## Pieces

| Path | Role |
| --- | --- |
| `skills/model-check/` | The workflow skill: when/how to model, check, and back-map |
| `agents/tla-modeler.md` | Subagent that writes the spec + mapping and runs TLC |
| `scripts/tlc` | Runner: enforces layout, runs TLC (`tla2tools.jar`), logs to `traces/` |
| `scripts/layout_hook.py` | Hooks: layout reminders on write; blocks stopping while a counterexample lacks its back-mapped scenario |
| `tla2tools.jar` | TLA+ tools v1.8.0 (TLC model checker) |

## Enforced layout (in the target repo)

```
verification/<System>/
  <Module>.tla        # the spec; every VARIABLE/action carries a \* file:line comment
  <Module>.cfg        # TLC config: CONSTANTS, SPECIFICATION/INIT+NEXT, INVARIANT...
  MAPPING.md          # source <-> model tables (state, actions + atomicity argument)
  traces/
    <Module>-<ts>.log          # every TLC run (written by scripts/tlc)
    <Module>-<ts>.scenario.md  # REQUIRED per counterexample: back-mapped interleaving + repro/test
```

`scripts/tlc` refuses to run without the `.cfg` and `MAPPING.md`; the Stop hook refuses
to end the task while any counterexample log has no `.scenario.md`.

## Requirements

Java (any recent JRE) on PATH. Everything else ships with the plugin.

## Install

### Claude Code

The repo doubles as a single-plugin marketplace.
From a local clone (or a GitHub `owner/repo` reference once pushed):

```
/plugin marketplace add /path/to/model-check
/plugin install model-check@model-check
```

That registers everything: the skill, the `tla-modeler` agent (dispatchable as
`model-check:tla-modeler`), the hooks, and `${CLAUDE_PLUGIN_ROOT}` for `scripts/tlc`.
Verify with `/plugin` → Manage plugins.

### Codex CLI

Codex runs the skill but has no plugin layer, so the hook-based enforcement (layout
reminders, the stop gate) does not apply — only the runner’s own refusals do.
Clone the repo and link the skill into Codex’s skills directory (`~/.codex/skills/`, or
the cross-runtime alias `~/.agents/skills/`):

```
git clone <this-repo> ~/r/model-check
mkdir -p ~/.codex/skills
ln -s ~/r/model-check/skills/model-check ~/.codex/skills/model-check
```

Where the skill says `${CLAUDE_PLUGIN_ROOT}`, use the checkout path: the runner is
`~/r/model-check/scripts/tlc` and finds `tla2tools.jar` relative to itself (or set
`TLA2TOOLS_JAR` explicitly).
There is no subagent dispatch either; follow the skill’s workflow inline.

## Testing

```
python3 -m unittest discover -s tests
```

Deterministic and zero-token: the LLM is faked by `tests/fake_agent.py`, which replays a
scripted transcript of tool calls (file writes, runner invocations) and simulates the
harness firing this plugin’s hooks around them — only the plugin’s real machinery
(`scripts/tlc`, `scripts/layout_hook.py`, real TLC) executes.
`tests/fixtures/jobqueue/` holds golden artifacts from a verified agent run of a genuine
TOCTOU race; `test_pipeline.py` replays that run end-to-end and asserts the machinery
blocks a non-compliant stop and admits a compliant one.
