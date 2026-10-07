# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

expkit is a shared experiment toolkit used across repos (first users: `felipedreis/dl2l` and
`felipedreis/snake_rl`). An experiment is declared once (question, hypotheses, assumptions,
design, outcomes, statistical plan), frozen as a pre-registration, run on local / Raspberry Pi
SLURM / CCAD HPC environments, collected, stored on HuggingFace, analysed, and reported, and
the agent is called back when results are ready instead of polling.

The design and the phase plan are in `docs/plans/shared-experiment-toolkit.md`. Read it before
changing anything structural. Phase 0 (this skeleton + `docs/spike/`) is in progress.

## Three parts, one version

| Part | Where | Notes |
|---|---|---|
| Python package + `expkit` CLI | `src/expkit/`, `pyproject.toml` | the deterministic logic; hooks and skills call it |
| Ansible collection `felipedreis.expkit` | `galaxy.yml`, `playbooks/`, `roles/`, `inventories/`, `meta/` | generalised from dl2l's `ansible/` |
| Claude Code plugin | `plugin/` (skills, later hooks and agents), marketplace in `.claude-plugin/` | thin: orchestrates the CLI |

The version lives in `src/expkit/__init__.py`, `galaxy.yml` and `plugin/.claude-plugin/plugin.json`;
`tests/test_versions.py` fails if they differ. Release = push tag `vX.Y.Z` (see
`.github/workflows/release.yml`). Add an entry to `CHANGELOG.md` for user-visible changes.

## Commands

```sh
uv venv .venv -p 3.11 && uv pip install -p .venv/bin/python -e '.[dev]'   # or python -m venv + pip
export PATH=$PWD/.venv/bin:$PATH

pytest -q                       # unit tests
ruff check . && ruff format --check .
ansible-lint                    # production profile; `--offline` if galaxy.ansible.com is unreachable
ansible-playbook -i inventories/local playbooks/spike.yml --syntax-check
ansible-galaxy collection build --output-path dist
claude plugin validate . && claude plugin validate ./plugin
```

In a sandbox whose stderr is non-blocking, Ansible refuses to start; run it as
`ansible-playbook ... < /dev/null 2>&1 | cat`.

## Rules

- **Keep the cluster knowledge.** Roles moved from dl2l carry comments recording live-cluster
  findings (CCAD qos per partition, per-job port ranges, the sandbox rebuild race,
  `delegate_to` needing `ansible_connection: ssh`, Ansible async polling hanging over the VPN,
  the $HOME disk quota). Keep those comments when moving or editing code; they are why the
  code looks the way it does.
- **Nothing waits on a cluster over the VPN.** The CEFET VPN drops idle connections. Plays
  submit and return; completion is detected cluster-side and reported by callback.
- **No secrets or PII in the repo.** The CCAD username is a CPF: it comes from
  `$CCAD_USERNAME` or a gitignored `.env.local`, and is never printed. Notifier tokens live on
  the clusters in a `0600` file written by provisioning. `spike-results/` is gitignored.
- **Judgement in Python, facts in Ansible.** Roles gather and act; decisions (verdicts,
  validation, statistics) live in `src/expkit/` where they are unit-tested.
- **Projects own their specifics.** Anything about one project (dl2l's JVM roles, snake_rl's
  agents) belongs in that project's `expkit.yml`, cell entrypoint or outcomes module, never in
  this repo. Inventories hold only facts about machines.
- Ansible: FQCN modules, `ansible-lint` production profile, role variables prefixed with the
  role name; shared inventory variables are prefixed `expkit_` (or `ccad_` for CCAD facts).
