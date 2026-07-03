# model-check

A Claude Code plugin for debugging state machines and concurrent systems with
TLA+ model checking. LLMs are weak at exhaustively reasoning about
interleavings; TLC is not. The plugin has Claude build a TLA+ model of the
code under test, checks invariants exhaustively, and — crucially — forces
every counterexample to be mapped back to concrete source lines, an explicit
interleaving scenario, and (where feasible) a failing test.

## Pieces

| Path | Role |
|---|---|
| `skills/model-check/` | The workflow skill: when/how to model, check, and back-map |
| `agents/tla-modeler.md` | Subagent that writes the spec + mapping and runs TLC |
| `scripts/tlc` | Runner: enforces layout, runs TLC (`tla2tools.jar`), logs to `traces/` |
| `scripts/layout-hook.py` | Hooks: layout reminders on write; blocks stopping while a counterexample lacks its back-mapped scenario |
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

`scripts/tlc` refuses to run without the `.cfg` and `MAPPING.md`; the Stop hook
refuses to end the task while any counterexample log has no `.scenario.md`.

## Requirements

Java (any recent JRE) on PATH. Everything else ships with the plugin.
