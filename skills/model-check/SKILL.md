---
name: model-check
description: Use when debugging or reviewing concurrent code and state machines — race conditions, deadlocks, lost updates, double-processing, TOCTOU bugs, protocol/lifecycle errors, or any behavior that depends on thread/event interleavings too numerous to reason through by hand. Also use when asked to verify invariants of a design before implementing it.
---

# model-check: TLA+ model checking with source back-mapping

Don't reason about interleavings by hand — model the code in TLA+, let TLC
enumerate the state space, then map every counterexample back to source. The
deliverable is never "TLC found a violation"; it is a source-level scenario a
human can follow and, where feasible, a failing test.

## Workflow

1. **Create the layout** in the target repo (the runner and hooks refuse to
   work without it):

   ```
   verification/<System>/
     <Module>.tla   <Module>.cfg   MAPPING.md   traces/
   ```

2. **Dispatch the modeling subagent** — `model-check:tla-modeler` — one model
   per dispatch. Its prompt must contain: the source files (paths) and the
   suspected property or bug symptom; the model directory
   `verification/<System>/`; and the runner path
   `${CLAUDE_PLUGIN_ROOT}/scripts/tlc`.

3. **Check the completion contract.** The subagent's work is complete only
   when every slot is filled:

   - `<Module>.tla` — every VARIABLE and action carries a `\* file:line` comment
   - `<Module>.cfg` — small finite constants (2 threads / 2–3 items)
   - `MAPPING.md` — state table + action table with an atomicity argument per action
   - `traces/<Module>-<ts>.log` — written by the runner; never run the jar directly
   - per counterexample: `traces/<Module>-<ts>.scenario.md` — per-step table
     (trace state → thread → source file:line → effect), root cause, repro
   - a failing test committed to the project's test layout, referenced from
     the scenario file
   - if NO violation: the report states the bounds checked (constants, state
     count) — "passed at 2×2" is a bounded claim, not a proof

4. **Relay results** in source terms. Quote the scenario table, not raw TLC
   states.

## Test cases: deterministic first

A stress loop (`setswitchinterval` + retry until it fires) proves the race is
real but makes a poor regression test. Prefer, in order:

1. **Deterministic forcing** — inject a barrier/hook at the race window
   (monkeypatch the method that performs the stale read, pause one thread
   between check and act) so the test fails every run on buggy code.
2. **Labeled stress test** — only when no seam exists; mark it as
   probabilistic in its docstring and state the trigger conditions.

## Fix verification

After a fix, re-run the SAME spec against an updated model (or better: model
the fixed algorithm in a `<Module>Fixed.tla` first, check it, then implement).
A fix is verified when the previously-failing invariant passes at the same
bounds and the failing test passes.

**Reference:** `references/modeling-patterns.md` — modeling recipe, spec/cfg
skeletons, TLC output/exit codes, MAPPING.md and scenario.md formats, pitfalls.
