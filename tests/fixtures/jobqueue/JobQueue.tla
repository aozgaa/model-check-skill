---- MODULE JobQueue ----
(* Model of jobqueue.py (uncommitted): multiple worker threads pull jobs
   from a shared list. Intent (module docstring, jobqueue.py:3-4):
   "A job must be processed exactly once."
   Safety half checked here as the invariant AtMostOnce. *)
EXTENDS Naturals, FiniteSets

CONSTANTS
    Workers,    \* jobqueue.py:52-55  the worker threads (bound in .cfg)
    Jobs        \* jobqueue.py:50     job ids, as naturals so the ordered
                \*                    scan of self.jobs can pick the minimum

ASSUME Jobs \subseteq Nat \ {0}

NoJob == 0      \* "job is None" sentinel, jobqueue.py:43

VARIABLES
    claimed,    \* jobqueue.py:14  Job.claimed          [Jobs -> BOOLEAN]
    processed,  \* jobqueue.py:15  Job.processed_count  [Jobs -> Nat]
    pc,         \* implicit: each worker's position in worker(), jobqueue.py:40-46
    target      \* jobqueue.py:42  worker-local `job` returned by next_unclaimed()

vars == <<claimed, processed, pc, target>>

TypeOK ==
    /\ claimed \in [Jobs -> BOOLEAN]
    /\ processed \in [Jobs -> 0 .. Cardinality(Workers)]
    /\ pc \in [Workers -> {"scan", "claim", "process", "done"}]
    /\ target \in [Workers -> Jobs \cup {NoJob}]

Init ==
    /\ claimed = [j \in Jobs |-> FALSE]     \* jobqueue.py:14
    /\ processed = [j \in Jobs |-> 0]       \* jobqueue.py:15
    /\ pc = [w \in Workers |-> "scan"]      \* jobqueue.py:41 top of worker loop
    /\ target = [w \in Workers |-> NoJob]

\* First unclaimed job in list order, matching the `for` loop at jobqueue.py:25-27.
MinUnclaimed == CHOOSE j \in Jobs :
                    /\ ~claimed[j]
                    /\ \A k \in Jobs : ~claimed[k] => j <= k

\* jobqueue.py:23-28  next_unclaimed(): UNLOCKED read-only scan of job.claimed.
\* Atomic-snapshot pick is sound here because claimed is monotone (see MAPPING.md).
Scan(w) ==
    /\ pc[w] = "scan"
    /\ IF \E j \in Jobs : ~claimed[j]
         THEN /\ target' = [target EXCEPT ![w] = MinUnclaimed]   \* jobqueue.py:27
              /\ pc' = [pc EXCEPT ![w] = "claim"]                \* jobqueue.py:45 next
         ELSE /\ pc' = [pc EXCEPT ![w] = "done"]                 \* jobqueue.py:44 return
              /\ UNCHANGED target
    /\ UNCHANGED <<claimed, processed>>

\* jobqueue.py:30-33  claim(): sets job.claimed = True under self.lock.
\* The lock covers only this write; the Scan above already happened without it,
\* so two workers may both reach here with the same target.
Claim(w) ==
    /\ pc[w] = "claim"
    /\ claimed' = [claimed EXCEPT ![target[w]] = TRUE]           \* jobqueue.py:33
    /\ pc' = [pc EXCEPT ![w] = "process"]                        \* jobqueue.py:46 next
    /\ UNCHANGED <<processed, target>>

\* jobqueue.py:35-37  process(): unlocked increment of job.processed_count.
Process(w) ==
    /\ pc[w] = "process"
    /\ processed' = [processed EXCEPT ![target[w]] = @ + 1]      \* jobqueue.py:36
    /\ pc' = [pc EXCEPT ![w] = "scan"]                           \* jobqueue.py:41 loop
    /\ UNCHANGED <<claimed, target>>

\* jobqueue.py:44  all workers returned; stutter so TLC's deadlock check passes.
Terminating ==
    /\ \A w \in Workers : pc[w] = "done"
    /\ UNCHANGED vars

Next == (\E w \in Workers : Scan(w) \/ Claim(w) \/ Process(w)) \/ Terminating

Spec == Init /\ [][Next]_vars

\* Intent from docstring jobqueue.py:3-4: "A job must be processed exactly once."
\* Safety half: never MORE than once.
AtMostOnce == \A j \in Jobs : processed[j] <= 1
====
