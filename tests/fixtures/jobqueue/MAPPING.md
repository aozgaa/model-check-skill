# Model <-> source mapping (jobqueue.py @ uncommitted)

Source under test: `jobqueue.py` (project root; not a git repo, so no commit
hash — file dated 2026-07-02).

Property modeled (from the module docstring, jobqueue.py:3-4): "A job must be
processed exactly once." The safety half — never processed MORE than once —
is the invariant `AtMostOnce`. (The liveness half, "eventually processed at
least once", is not checked; see Notes.)

## State

| Model variable | Source | Meaning |
|---|---|---|
| `claimed[j]` | jobqueue.py:14 `Job.claimed` | claim flag per job; only ever set `False -> True` (jobqueue.py:33), never reset — monotone |
| `processed[j]` | jobqueue.py:15 `Job.processed_count` | how many times job j has been processed |
| `pc[w] = "scan"` | jobqueue.py:41-42 (top of `worker` loop, about to call `next_unclaimed`) | worker looking for work |
| `pc[w] = "claim"` | jobqueue.py:45 (between `next_unclaimed` return and `claim` call) | worker holds a stale scan result — the race window |
| `pc[w] = "process"` | jobqueue.py:46 (about to call `process`) | worker committed to its target |
| `pc[w] = "done"` | jobqueue.py:44 (`return` from `worker`) | worker thread exited |
| `target[w]` | jobqueue.py:42 local variable `job` in `worker` | which job the worker's scan returned; `NoJob` (0) models `None` |
| CONSTANT `Workers` | jobqueue.py:52-55 threads created in `run()` | 2 workers in the .cfg (matches `num_workers=2` default) |
| CONSTANT `Jobs` | jobqueue.py:50 `jobs` list | naturals so list order is model order; 2 jobs in the .cfg (source default is 4; 2 suffice) |

## Actions

| Action | Source | Atomicity argument |
|---|---|---|
| `Scan(w)` | jobqueue.py:23-28 `next_unclaimed()` | Runs with NO lock. The loop reads one `job.claimed` per step, but since `claimed` is monotone (only `False -> True`), the whole scan linearizes at the read that returns: any job it returns was the first unclaimed job at that instant, and a `None` return means all jobs were claimed at the final read. So one atomic "pick the minimum unclaimed job" action is behavior-equivalent — neither hides nor invents interleavings. `MinUnclaimed` (not a nondeterministic pick) mirrors the ordered `for` loop, so the model cannot claim a later job while an earlier one is free, which the code also cannot do. Kept a SEPARATE action from `Claim` because no lock spans scan and claim — that gap is the race window. |
| `Claim(w)` | jobqueue.py:30-33 `claim()` | The write `job.claimed = True` is under `self.lock` (jobqueue.py:32), so it is one atomic action. The lock is otherwise irrelevant: no other code path acquires it, so no lock variable is modeled. Crucially the guard is only `pc[w] = "claim"` — NOT `~claimed[target[w]]` — because the code re-checks nothing before claiming. |
| `Process(w)` | jobqueue.py:35-37 `process()` | `job.processed_count += 1` (jobqueue.py:36) is an unlocked read-modify-write. Modeling it as one atomic increment is the COARSEST sound choice for `AtMostOnce`: even with atomic increments, two workers processing the same job yield `processed = 2`. (Splitting it finer would only add a lost-update race on the counter itself, which would mask double-processing as `processed = 1`.) |
| `Terminating` | jobqueue.py:44 `return` | Pure stutter once every `pc[w] = "done"`; exists only so TLC's deadlock check does not flag legitimate thread exit. |

## Notes / deliberate abstractions

- `time.sleep(0.001)` (jobqueue.py:37) is dropped: it only widens real-time
  race windows; the model already allows all interleavings.
- The GIL makes each single attribute read/write atomic, which the action
  granularity above respects.
- Liveness ("every job eventually processed at least once") would need
  fairness (`WF_vars`) and a `PROPERTY`; the dispatched property's failure
  mode is over-processing, so only the safety invariant is checked.
