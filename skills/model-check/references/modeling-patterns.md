# Modeling code as TLA+ — patterns and TLC reference

Cookbook for translating source code (threads, locks, queues, state machines) into a
checkable TLA+ spec while preserving a line-level mapping back to source.

## The modeling recipe

1. **Shared state → VARIABLES.** Every piece of memory that more than one
   thread/process/handler touches becomes a variable.
   Thread-local data usually becomes a function `local \in Threads -> Value` or is
   folded into `pc`.
2. **Program counter per thread.** `pc \in Threads -> Labels`, where each label names a
   *source location* (e.g. `"check"`, `"claim"`, `"process"`). Labels are the backbone
   of the source mapping — pick label names after the code.
3. **Atomicity boundaries decide correctness.** One TLA+ action = one block of code that
   cannot be interleaved.
   Anything between two actions CAN be interleaved.
   When unsure, split: a read of shared state followed by a write based on it must be
   TWO actions unless the code holds a lock across both.
   Modeling too coarse (one action for check+act) silently hides the bug you are looking
   for.
4. **Locks.** `lock \in Threads \cup {NoThread}`. Acquire:
   `lock = NoThread /\ lock' = t`. Release: `lock' = NoThread`. An action that runs
   “while holding the lock” gets guard `lock = t`.
5. **Keep it finite and tiny.** 2 threads and 2–3 items find the vast majority of
   interleaving bugs and keep traces readable.
   Put bounds in the .cfg (CONSTANTS), not in the module.
6. **Invariants from intent, not from code.** Sources: docstrings/comments ("exactly
   once", “never negative”), asserts, API contracts, domain rules.
   Always include `TypeOK`. Encode “at most once” style properties as state invariants
   over history-counting variables (e.g. `processedCount`).

## Spec skeleton (two threads racing on check-then-act)

```tla
---- MODULE JobQueue ----
EXTENDS Naturals, FiniteSets

CONSTANTS Workers, Jobs          \* small finite sets, bound in .cfg

VARIABLES
    claimed,        \* jobqueue.py:14  Job.claimed        [Jobs -> BOOLEAN]
    processed,      \* jobqueue.py:15  Job.processed_count [Jobs -> Nat]
    pc,             \* implicit: each worker's position in worker()
    target          \* worker-local: which job the worker saw as unclaimed

vars == <<claimed, processed, pc, target>>
NoJob == CHOOSE j : j \notin Jobs

TypeOK ==
    /\ claimed \in [Jobs -> BOOLEAN]
    /\ processed \in [Jobs -> Nat]
    /\ pc \in [Workers -> {"scan", "claim", "process", "done"}]
    /\ target \in [Workers -> Jobs \cup {NoJob}]

Init ==
    /\ claimed = [j \in Jobs |-> FALSE]
    /\ processed = [j \in Jobs |-> 0]
    /\ pc = [w \in Workers |-> "scan"]
    /\ target = [w \in Workers |-> NoJob]

\* jobqueue.py:25-29  next_unclaimed(): unlocked read of job.claimed
Scan(w) ==
    /\ pc[w] = "scan"
    /\ IF \E j \in Jobs : ~claimed[j]
         THEN \E j \in Jobs : ~claimed[j] /\ target' = [target EXCEPT ![w] = j]
                /\ pc' = [pc EXCEPT ![w] = "claim"]
         ELSE pc' = [pc EXCEPT ![w] = "done"] /\ UNCHANGED target
    /\ UNCHANGED <<claimed, processed>>

\* jobqueue.py:31-34  claim(): sets claimed under the lock — but the scan above
\* already happened, so two workers may both reach here with the same target.
Claim(w) ==
    /\ pc[w] = "claim"
    /\ claimed' = [claimed EXCEPT ![target[w]] = TRUE]
    /\ pc' = [pc EXCEPT ![w] = "process"]
    /\ UNCHANGED <<processed, target>>

\* jobqueue.py:36-38  process()
Process(w) ==
    /\ pc[w] = "process"
    /\ processed' = [processed EXCEPT ![target[w]] = @ + 1]
    /\ pc' = [pc EXCEPT ![w] = "scan"]
    /\ UNCHANGED <<claimed, target>>

Next == \E w \in Workers : Scan(w) \/ Claim(w) \/ Process(w)
Spec == Init /\ [][Next]_vars

\* Intent from module docstring: "A job must be processed exactly once."
AtMostOnce == \A j \in Jobs : processed[j] <= 1
====
```

Points worth copying: every variable and action carries a `\* file:line` comment; labels
(`"scan"`, `"claim"`, ...) name source steps; the worker-local variable `target`
captures the stale read that makes the race expressible.

## .cfg skeleton

```
CONSTANTS
    Workers = {w1, w2}
    Jobs = {j1, j2}
SPECIFICATION Spec
INVARIANT TypeOK
INVARIANT AtMostOnce
```

- `w1`, `j1`, ... are model values: bare identifiers, no quotes.
- Use `INIT Init` / `NEXT Next` instead of `SPECIFICATION` only when there is no
  fairness/liveness; `SPECIFICATION Spec` is the safer default.
- Liveness ("every job eventually processed") goes under `PROPERTY` and needs fairness
  conjuncts (`WF_vars(...)`) in `Spec`.

## Running TLC and reading its output

Run through the plugin’s runner (enforces layout, saves the log):

```
${CLAUDE_PLUGIN_ROOT}/scripts/tlc verification/<System>/<Module>.tla
```

- Module name MUST equal the file basename.
- Exit codes: 0 = no violation; 12 = safety violation (invariant/deadlock); 13 =
  liveness violation; anything else = the spec itself is broken (parse/semantic/config
  error) — fix the spec, don’t interpret it as a result.
- TLC checks for deadlock by default.
  If threads legitimately stop (e.g. workers exit), either model an explicit `done`
  self-loop/stutter or pass `-deadlock` (confusingly, that flag DISABLES deadlock
  checking).
- A counterexample prints as `State 1`, `State 2 <Claim(w2) line 42...>`, ... Each
  `<ActionName(...)>` header names the action and its module line; the variable values
  below are the state AFTER that action.
- TLC also writes a `_TTrace_*.tla` spec that replays the trace; the runner moves it
  into `traces/`.

## MAPPING.md format

One table for state, one for actions.
Line numbers refer to the commit being modeled; note the commit hash at the top.

```markdown
# Model <-> source mapping (jobqueue.py @ a1b2c3d)

## State
| Model variable | Source | Meaning |
|---|---|---|
| claimed[j] | jobqueue.py:14 `Job.claimed` | claim flag per job |
| pc[w] = "claim" | jobqueue.py:52 (between next_unclaimed and claim) | worker about to claim |

## Actions
| Action | Source | Atomicity argument |
|---|---|---|
| Scan(w) | jobqueue.py:25-29 `next_unclaimed` | unlocked scan; separate action from Claim because no lock spans them |
| Claim(w) | jobqueue.py:31-34 `claim` | holds self.lock |
```

The “Atomicity argument” column is not decoration: it records WHY the code was split
into these actions, which is where modeling errors hide.

## traces/<Module>-<ts>.scenario.md format

Back-map every trace step, then give the concrete repro:

```markdown
# Scenario: AtMostOnce violated (trace <Module>-<ts>.log)

| # | Action | Thread | Source | What happens |
|---|---|---|---|---|
| 2 | Scan(w1) | worker 1 | jobqueue.py:27 | w1 sees j1 unclaimed |
| 3 | Scan(w2) | worker 2 | jobqueue.py:27 | w2 ALSO sees j1 unclaimed — stale read |
| ... |

## Root cause
Check (next_unclaimed, jobqueue.py:25-29) and act (claim, jobqueue.py:31-34)
are not atomic: the lock is only held for the write.

## Reproducing in practice
Interleaving: both workers must complete next_unclaimed() before either calls
claim(). Force it in a test by <injection point / barrier / monkeypatch>.

## Test case
tests/test_jobqueue_race.py::test_double_processing (fails on current code)
```

## Common pitfalls

| Symptom | Cause / fix |
| --- | --- |
| “Cannot find source file” / parse error at ---- | Module name != file basename, or missing `====` terminator |
| cfg parse error | Quoted model values, or expressions in cfg (cfg takes only names/literals; define expressions in the module) |
| Deadlock reported at end of run | Threads terminate; add `-deadlock` flag or model a `done` stutter step |
| State explosion / TLC runs forever | Constants too big; shrink to 2 threads / 2-3 items; add a `CONSTRAINT` bounding counters |
| Invariant holds but bug exists in code | Actions too coarse — a check and an act were merged into one atomic action; split them |
| Violation in model but not plausible in code | Actions too fine, or model allows transitions code forbids; re-check the mapping’s atomicity argument |
