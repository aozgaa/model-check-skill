# Scenario: AtMostOnce violated (trace JobQueue-20260703T010232Z.log)

Invariant `AtMostOnce` (`\A j \in Jobs : processed[j] <= 1`, from the docstring
"A job must be processed exactly once", jobqueue.py:3-4) is violated: job 1
ends with `processed_count = 2`. Model values `w1`/`w2` are two worker threads
(jobqueue.py:52-55); job 1 is the first `Job` in the list (jobqueue.py:50).

| # | Action | Thread | Source | What happens |
|---|---|---|---|---|
| 1 | Init | — | jobqueue.py:49-57 | 2 jobs unclaimed, both workers at top of `worker` loop |
| 2 | Scan(w2) | worker 2 | jobqueue.py:25-27 `next_unclaimed` | w2 scans WITHOUT the lock, sees job 1 unclaimed, returns it (`target[w2] = 1`) |
| 3 | Scan(w1) | worker 1 | jobqueue.py:25-27 `next_unclaimed` | w1 ALSO scans and sees job 1 still unclaimed — w2 has not claimed yet, so w1 gets the SAME job |
| 4 | Claim(w2) | worker 2 | jobqueue.py:32-33 `claim` | w2 takes the lock, sets `job1.claimed = True`, releases |
| 5 | Claim(w1) | worker 1 | jobqueue.py:32-33 `claim` | w1 takes the lock and sets `job1.claimed = True` AGAIN — `claim` never re-checks the flag, so the lock does not help |
| 6 | Process(w2) | worker 2 | jobqueue.py:36 `process` | `job1.processed_count` 0 -> 1 |
| 7 | Process(w1) | worker 1 | jobqueue.py:36 `process` | `job1.processed_count` 1 -> 2 — **AtMostOnce violated** |

## Root cause

Check-then-act without a spanning lock. The check
(`next_unclaimed`, jobqueue.py:23-28) deliberately runs unlocked (its
docstring even claims "read-only scan, so no lock needed"), and the act
(`claim`, jobqueue.py:30-33) holds `self.lock` only for the write and never
re-verifies `job.claimed`. Any number of workers can pass the check for the
same job before the first one claims it; the lock then serializes the
redundant writes but prevents nothing.

## Reproducing in practice

Required interleaving: both workers must return from `next_unclaimed()`
(steps 2-3) before either calls `claim()` (step 4). The window at
jobqueue.py:42-45 is a few instructions wide, so it is forced
deterministically in the test by wrapping `Dispatcher.next_unclaimed` so
that a successful scan waits on a `threading.Barrier(2)` — both workers
complete the scan, then both proceed to claim.

## Test case

`tests/test_jobqueue_race.py::test_job_processed_at_most_once`
(fails on current code with: job 0 processed 2 times).

Run from the project root: `python3 -m pytest tests/test_jobqueue_race.py`
(or `python3 tests/test_jobqueue_race.py` without pytest).

## Fix direction (not applied)

Make check and act one critical section: hold `self.lock` across the scan
and the claim (e.g. a `claim_next()` that finds AND flags the job under one
lock acquisition), or re-check `job.claimed` inside the lock and retry.
