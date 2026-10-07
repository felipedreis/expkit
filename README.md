# expkit

A shared toolkit for running experiments the same way in every repo. You declare an
experiment once (question, hypotheses, assumptions, design, outcomes, statistical plan).
The toolkit then freezes it as a pre-registration, runs it locally or on SLURM clusters,
collects and stores the data, analyses it, writes the report, and calls the agent back when
results are ready instead of having anyone poll.

It ships as three parts that version together:

- **An Ansible collection** (`felipedreis.expkit`): the local, Raspberry Pi and CCAD runners,
  generalised from dl2l.
- **`expkit`**, a Python package and CLI: validation, freezing, power analysis, statistics,
  reports, notifications.
- **A Claude Code plugin**: skills, hooks and a protocol-reviewer subagent that drive the CLI.

Its first two users are [`felipedreis/dl2l`](https://github.com/felipedreis/dl2l) and
[`felipedreis/snake_rl`](https://github.com/felipedreis/snake_rl).

## Status

**Phase 0** of [the plan](docs/plans/shared-experiment-toolkit.md): the skeleton, CI, and an
[environment spike](docs/spike/README.md) that checks what the Pi cluster and CCAD allow
before the callback design relies on it. Nothing runs experiments yet.

## Install

```sh
# Python package and CLI
pip install "expkit @ git+https://github.com/felipedreis/expkit@v0.1.0"
expkit doctor

# Ansible collection
ansible-galaxy collection install git+https://github.com/felipedreis/expkit.git,v0.1.0

# Claude Code plugin (inside Claude Code)
/plugin marketplace add felipedreis/expkit
/plugin install expkit@expkit
```

The repo is private, so each of these needs GitHub access to it (an SSH key or a token for
`pip` and `ansible-galaxy`; the Claude GitHub App for the plugin).

## Develop

See [CLAUDE.md](CLAUDE.md) for commands and conventions.
