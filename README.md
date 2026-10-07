# expkit

A shared toolkit for running experiments the same way in every repo. You declare an
experiment once (question, hypotheses, assumptions, design, outcomes, statistical plan).
The toolkit then freezes it as a pre-registration, runs it locally or on SLURM clusters,
collects and stores the data, analyses it, and writes the report.

It ships as two parts that version together:

- **`expkit`**, a Python package and CLI: validation, freezing, power analysis, run orchestration,
  collection, upload, statistics, reports.
- **A Claude Code plugin**: skills, hooks and a protocol-reviewer subagent that drive the CLI.

Status: **planning**. See [`docs/plans/shared-experiment-toolkit.md`](docs/plans/shared-experiment-toolkit.md).

Its first two users are [`felipedreis/dl2l`](https://github.com/felipedreis/dl2l) and
[`felipedreis/snake_rl`](https://github.com/felipedreis/snake_rl).
