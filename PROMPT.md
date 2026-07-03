I would like us to create a claude plugin to aid in debugging state machines and concurrent systems.
LLM's are quite ppor are reasoning about complex interactions, so we'd like to offload that responsibility to a model
checker. We should use something like tlaplus:
```
% wget https://github.com/tlaplus/tlaplus/releases/download/v1.7.4/tla2tools.jar
...
% java -jar tla2tools.jar
TLC2 Version 2.19 of 08 August 2024 (rev: 5a47802)
Error: Error: Missing input TLA+ module.
Usage: java tlc2.TLC [-option] inputfile
```
I would like you to write up a skill which uses a subagent to:
a) model the source code/domain under test with tlaplus, preserving a mapping between source code lines and state
   machine state/transitions
b) determine invariants/properties of interest, and encode those in the model
c) run the model checker to find violations
d) use the mapping back to source to reconstruct explicit scenarios/inputs that could cause the violation
a) where possible, deliver an explicit test case which causes the violation

The plugin layer should provide hooks for running the model checker and enforce a regular structure to the modeling
repo/subdir (eg: model files go in thie subdir, constraints go in this subdir, if a violation is found, the completion
of the task _must_ include back-mapping to source and explicit input scenarios)
