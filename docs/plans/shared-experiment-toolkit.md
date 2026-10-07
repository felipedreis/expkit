# Plan: a shared experiment toolkit (skills, scripts, hooks, tools) used across repos

Status: **draft, awaiting approval**. Nothing has been built yet and no new repository has been
created.

## 1. Why

There are two experimental workflows today, and each has half of what we want.

| | dl2l | snake_rl |
|---|---|---|
| Declarative spec | `experiments/<name>.yml`: conditions, trials, image, extract, upload, analysis module | none; the design is prose in `PROTOCOL.md` plus a bash `run.sh` |
| Hypotheses / assumptions | prose in the report, written after the run (dev cycle step 5) | **pre-registered** in `PROTOCOL.md` (direction, rationale, pilot effect), frozen with SHA-256 hashes before any confirmatory run |
| Sample size | `stats.required_n`, used ad hoc | rough power section in the protocol |
| Execution | Ansible: local docker-compose, Pi (SLURM + Docker), CCAD (SLURM + Singularity, submit/rescue with `DONE` sentinels) | `xargs -P 8` over `snake-run` on one machine |
| Collection | `dl2l_data.extract` (Arrow → DuckDB → Parquet) + `manifest.json` | JSON per run under `results/`, committed to git |
| Storage | HuggingFace dataset `felipedreis/dl2l-experiments`, always uploaded | git only |
| Analysis | `dl2l_analysis` (Kruskal-Wallis + Bonferroni MWU, Cliff's delta, survival) + per-experiment `run(cfg)` | one-off `analyze.py`: exact permutation tests, Holm, bootstrap CIs, Hedges' g, decision rule |
| Report | `ReportBuilder`: Purpose / Assumptions / Hypothesis / Results / Analysis | `REPORT.md`: recap, verdict table, deviations, limitations, hash check |

The goal is one toolkit, in its own repo, that any project can adopt. It should take an
experiment from a declarative definition (question, hypotheses, assumptions, design) through
running, collecting, analysing and storing, to a report, with the same conventions everywhere.
It should keep the strengths of both: dl2l's environment-agnostic execution and guaranteed data
preservation, and snake_rl's pre-registration discipline.

## 2. What we ship, and how

One repo (working name **`felipedreis/expkit`**, see open question Q1) holding two things that
version together:

1. **A Python package, `expkit`** (CLI + library). It holds everything deterministic: schema
   validation, freezing, power analysis, run orchestration, collection, upload, statistics,
   report rendering. Installed per project with
   `pip install "expkit @ git+https://github.com/felipedreis/expkit@vX.Y.Z"` (pinned tag),
   or run without installing via `uvx`.
2. **A Claude Code plugin** (the same repo is also a plugin marketplace). It holds the skills,
   hooks, slash commands and a reviewer subagent, which drive the CLI. Installed with
   `/plugin marketplace add felipedreis/expkit` and then `/plugin install expkit`.

Rule of thumb: **anything that must give the same answer twice lives in the CLI; the skills only
orchestrate, ask questions, and write prose.** Hooks call the CLI, so they never duplicate its
logic.

```
expkit/
  .claude-plugin/
    plugin.json            # plugin manifest
    marketplace.json       # makes the repo installable as a marketplace
  skills/                  # one dir per skill, SKILL.md + references (section 5)
  agents/protocol-reviewer.md
  hooks/hooks.json         # + hooks/*.py thin wrappers over the CLI (section 6)
  src/expkit/
    spec/                  # JSON Schema + pydantic models, validate, migrate
    freeze.py              # hashing, provenance, verify
    power.py               # analytic + simulation-based power
    run/                   # backends: local, slurm (+ container wrappers), submit/rescue state
    collect/               # artifact sync, manifest, extractor hook
    store/                 # upload backends: huggingface (first), local
    stats/                 # tests, corrections, effect sizes, CIs, decision rule
    report/                # report model + markdown renderer + figure helpers
    cli.py
  envs/                    # shareable environment profiles: ccad.yml, pi.yml, local.yml
  templates/               # new-experiment scaffolds (spec, analysis.py, report)
  tests/                   # unit tests + golden tests against real past experiments
  docs/
```

## 3. The experiment spec (the core of the design)

One YAML file per experiment. It merges dl2l's `experiments/<name>.yml` (the *how*) with
snake_rl's `PROTOCOL.md` (the *why* and the *what counts as evidence*), so the protocol stops
being prose that can drift from the code. Prose still has a place: free-text fields, and an
optional `protocol.md` next to the spec that the spec links to and that gets frozen with it.

Sketch, using the snake_rl MFEC experiment as the worked example:

```yaml
schema: expkit/v1
id: mfec_dqn_nec
title: MFEC vs DQN vs NEC on Snake
status: draft            # draft -> frozen -> running -> collected -> analysed -> reported
question: >
  How does MFEC compare with DQN and NEC on final play quality, data efficiency,
  robustness to noise channels, and a larger board?

design:
  factors:
    agent:  [random, dqn, nec, mfec]
    config:
      C1: {size: 7,  distractors: 0, steps: 40000}
      C2: {size: 7,  distractors: 4, steps: 40000}
      C3: {size: 10, distractors: 0, steps: 60000}
  cells: full_factorial    # or an explicit list of conditions (dl2l's style)
  replication:
    unit: run              # the unit of analysis
    seeds: 101-110         # explicit, never reused from the pilot
  labels:  {random: Random, dqn: DQN, nec: NEC, mfec: MFEC}
  colors:  {dqn: "#2a78d6", nec: "#eb6834", mfec: "#1baf7a", random: "#8a8984"}

outcomes:
  late:  {role: primary,   description: "mean score/episode, steps (S/2, S]"}
  early: {role: primary,   description: "mean score/episode, steps (5k, 10k]"}
  rate_late: {role: secondary, description: "fruit per 1000 steps, 2nd half"}

hypotheses:
  - id: H1a
    where: {config: C1}
    outcome: late
    claim: {a: {agent: mfec}, b: {agent: dqn}, direction: greater}
    rationale: "States repeat often on a clean 7x7 board; episodic tables excel there."
    pilot: {a: 1.54, b: 0.97, n: 5}
  # ...

assumptions:
  - id: A1
    text: "Runs with different seeds are independent samples."
  # ...

analysis:
  test: permutation_exact       # | mann_whitney | welch_t | kruskal+posthoc | logrank ...
  sides: two
  correction: holm              # | bonferroni | none
  alpha: 0.05
  effect_sizes: [mean_diff_bootstrap_ci, hedges_g]
  decision_rule: directional    # supported / contradicted / not supported
  missing: {rerun: 1, then: exclude_and_report}
  power: {method: simulation, target: 0.8, from: pilot}
  module: analysis.py           # project code: run outputs -> one row per run x outcome

run:
  adapter: snake                # names an adapter in the project's expkit.toml (section 4)
  parallel: 8
  env_defaults: {OMP_NUM_THREADS: 1}

collect:
  artifacts: "results/exp_mfec/**/*.json"

store:
  backend: huggingface
  repo: felipedreis/snake-rl-experiments
  prefix: mfec_dqn_nec
  enabled: true                 # validator refuses false unless status is a smoke run
```

Points worth calling out:

- **Hypotheses are data, not prose.** Each one names an outcome, a comparison, a direction and a
  rationale. That lets the CLI compute power per hypothesis, build the verdict table, and apply
  the decision rule without any per-experiment code. snake_rl's `HYPOTHESES` list in
  `analyze.py` is exactly this, hand-written; we lift it into the spec.
- **Conditions come from either a factorial or an explicit list.** dl2l's
  `conditions: [{key, simulation, label, color}]` is the explicit-list form; snake_rl's
  agent × config grid is the factorial form. Both lower to the same internal list of cells.
- **Project-specific detail stays in the project.** The spec says *what* to run; how one cell
  becomes a process is the project's adapter (section 4). The spec can carry arbitrary
  per-cell parameters (`simulation:` for dl2l, `size`/`steps` for snake) that the adapter reads.
- **`analysis.module`** is the only per-experiment code: it turns raw outputs into a tidy
  table (one row per run, one column per outcome). Every test, correction, CI, figure and the
  verdict table is generic from there.
- **Migration from dl2l's schema is mechanical.** An `expkit spec migrate` command converts the
  existing `experiments/*.yml` (adds empty `hypotheses`/`assumptions`/`outcomes`, marks them
  `status: reported` and `legacy: true` so they aren't held to the freezing rules).

## 4. Project integration: `expkit.toml` and adapters

Each project adds one small file at its root, so the toolkit knows the local conventions:

```toml
[project]
name = "dl2l"
experiments_dir = "experiments"
reports_dir = "docs/reports"
figures_dir = "docs/reports/figures"

[adapters.dl2l]
# How one (condition, trial) cell becomes work. Templated with the cell's parameters.
cell = "scripts/run-cell.sh --simulation {simulation} --trial {trial} --out {cell_dir}"
container = "ghcr.io/felipedreis/dl2l:{image_tag}"   # optional
extract = "python3 -m dl2l_data.extract --experiment {id} --condition {key} --trial {trial} --out {data_dir} --raw-dir {cell_dir}/raw"

[adapters.snake]
cell = ".venv/bin/snake-run {agent} {seed} {steps} {distractors} {size} --results {cell_dir}"
```

That split is what makes the tool generic: dl2l's 469-line CCAD `run_trial.sh.j2` (four
Singularity instances, port allocation, the live-cluster fixes it records) stays in dl2l as its
cell script. expkit only owns what is the same for every project: fan out cells, run them on an
environment, track them, collect them.

## 5. Execution backends and environments

**Recommendation: the run engine is Python, in expkit; Ansible stays in dl2l for provisioning
(and, during migration, as the dl2l runner until parity is shown).** Reasons:

- snake_rl has no need for Ansible, and the dynamic `include_role: "trial_runner_{{ dl2l_env }}"`
  layer is already the most intricate part of dl2l's infra.
- The generic parts of the CCAD flow (sbatch array per condition, persisted job ids,
  `DONE` sentinels, rescue that is safe to repeat, sync-back, gating upload on all trials done)
  are a few hundred lines of testable Python. The project-specific parts move into the cell
  script anyway.

Backends:

| Backend | Covers | Mode |
|---|---|---|
| `local` | snake today; dl2l on the Mac via docker compose inside the cell script | blocking, process pool with `parallel: N` |
| `slurm` | Pi cluster, CCAD | **submit / rescue**: `expkit run` submits and returns; `expkit rescue` checks sentinels, syncs back, and moves on once all cells are done. Safe to repeat. |
| container wrapper | `docker` (local, Pi) or `singularity` (CCAD) around the cell | composes with either backend |

Environment profiles (`envs/ccad.yml`, `envs/pi.yml`, `envs/local.yml`) carry the facts that are
the same for every project on that machine: host, partition and qos pairs (`short`/`short_qos`,
learned the hard way), CPU/memory defaults, shared FS paths, registry, container runtime. A
project can override them in `expkit.toml`. **Secrets and PII never live there**: the CCAD
username keeps coming from a gitignored `.env.local`, the HF token from the environment.

State for each run lives in `.expkit/runs/<id>/` (job ids, per-cell status, timestamps), so
`expkit status` works across sessions and machines and the VPN-drop pattern is the default, not
a special case.

## 6. Freezing and provenance (pre-registration as a tool)

`expkit freeze <id>`:

1. validates the spec (schema, files exist, seeds disjoint from any `pilot.seeds`, every
   hypothesis references a declared outcome and condition, `store.enabled` is true);
2. requires a clean git tree;
3. writes `FROZEN.json`: UTC time, git commit, SHA-256 of the spec, `protocol.md`, the analysis
   module and the adapter's cell script, plus the container digest when there is one;
4. sets `status: frozen`.

`expkit run` refuses a confirmatory run unless the spec is frozen and the hashes still match
(`--exploratory` skips this and labels everything that comes out of it as exploratory).
`expkit analyze` and `expkit report` re-verify the hashes and put the result in the report.
Changing a frozen file is allowed, but only through `expkit deviate <id> "<reason>"`, which
appends to a deviations log that the report includes verbatim. That is snake_rl's
`FROZEN.sha256` + "Deviations" section, enforced instead of remembered.

Every collected cell also gets provenance in `manifest.json` (extending dl2l's manifest):
spec hash, git commit, image digest, environment, host, seed, wall-clock, exit status.

## 7. Statistics and reports

`expkit.stats` merges the two existing implementations and adds nothing exotic:

- from snake_rl `analyze.py`: exact and Monte Carlo permutation tests, Holm, percentile
  bootstrap CIs, Hedges' g, the supported / contradicted / not-supported decision rule;
- from dl2l `stats.py`: Kruskal-Wallis + Bonferroni Mann-Whitney, Cliff's delta, ICC and design
  effect, `required_n`, Kaplan-Meier / log-rank;
- `expkit power`: analytic where a closed form exists, otherwise simulation from pilot data
  under the declared test and correction. This is how dev-cycle step 5c ("determine the sample
  size through a statistical method") becomes one command.

The report is generated from the spec plus results, with fixed sections that satisfy both
repos' conventions:

1. **Purpose** (question, from the spec)
2. **Assumptions** (from the spec)
3. **Hypotheses** (from the spec, with rationale and pilot)
4. **Design and methods** (conditions, replication, tests, power; generated)
5. **Results** (descriptives table, verdict table, figures; generated)
6. **Analysis** (interpretation; written by the human or the `report` skill, never generated)
7. **Deviations** (from the deviations log), **Limitations**, **Provenance** (hash check, data
   location on HF, commit)

Figures follow the existing palette-from-spec approach (`dl2l_analysis.figures`) and the
`dataviz` conventions already used in snake_rl's learning-curve figure.

## 8. Claude Code skills, agent and hooks

Skills (namespaced `expkit:` once installed):

| Skill | What it does |
|---|---|
| `design` | Interviews the user (question, mechanism, outcomes, what result would change their mind), drafts the spec and `protocol.md`, insists on directional hypotheses with rationale and on a pilot when effect sizes are unknown. Runs `expkit validate`. |
| `power` | Runs `expkit power`, explains the result, proposes a trial count, records the reasoning in the spec. |
| `review-protocol` | Hands the draft to the `protocol-reviewer` subagent: an adversarial reader looking for unfalsifiable or undirected hypotheses, seed reuse from the pilot, too many outcomes, underpowered tests, outcomes defined after looking at data, missing-data rules. |
| `freeze` | Validates, freezes, commits the frozen files. |
| `run` | Picks the environment, launches, and for SLURM explains the submit/rescue flow (and can schedule a check-in to rescue later). |
| `status` | Lists every experiment and its lifecycle state, in-flight jobs, cells done/failed. |
| `analyze` | Runs the frozen analysis; anything extra is labelled exploratory. |
| `report` | Renders the generated sections and writes the Analysis/Limitations prose, keeping claims to what the verdict table supports. |
| `publish` | Uploads data, verifies it landed on HF, links it from the report. |
| `adopt` | One-time onboarding of a repo: writes `expkit.toml`, an adapter, CLAUDE.md lines, and migrates existing specs. |

Hooks (each a thin script that calls the CLI; all can be disabled per project):

| Event | Hook | Effect |
|---|---|---|
| `PreToolUse` Edit/Write | **frozen-guard** | Blocks edits to files listed in a `FROZEN.json` unless a matching deviation was logged; the block message says how to log one. |
| `PostToolUse` Edit/Write on a spec | **validate-on-save** | Runs `expkit validate`, feeds errors back immediately. |
| `PreToolUse` Bash | **data-preservation** | Blocks `rm -rf` of collected data dirs or raw dumps that `manifest.json` says were never uploaded. |
| `SessionStart` | **in-flight summary** | One line per experiment that is running or waiting for rescue, so a new session knows CCAD jobs are pending. |
| `Stop` | **lifecycle nudge** | If an experiment reached `analysed` this session without a report, says so once. |

## 9. Phases

Each phase ends with something usable and a concrete acceptance check. The strongest checks
reuse past experiments as golden tests: if the new tool reproduces their numbers, it is right.

**Phase 0: decisions and skeleton.** Answer the open questions; create the repo; plugin
manifest, package skeleton, CI (lint, type check, tests), release tags.
*Accept:* the plugin installs in a fresh session; `expkit --version` works from a pinned tag.

**Phase 1: spec, validate, freeze.** JSON Schema + models, `validate`, `freeze`, `verify`,
`deviate`, `spec migrate`; `design`, `review-protocol`, `freeze` skills; frozen-guard and
validate-on-save hooks.
*Accept:* snake_rl's `mfec_dqn_nec` written as a spec validates, and its existing hypotheses
lower to the same list as `analyze.py`'s `HYPOTHESES`; all six dl2l specs migrate and validate.

**Phase 2: stats, power, report.** Port both stats modules, decision rule, report renderer,
`power`, `analyze`, `report` skills.
*Accept:* run against the existing `results/exp_mfec`, expkit reproduces snake_rl's
`results.md` numbers exactly (same seeds, same RNG seed 0 for the bootstrap) and the same seven
verdicts. One dl2l report's Kruskal/MWU table is reproduced from its HF data.

**Phase 3: run engine.** `local` and `slurm` backends, container wrappers, run state, `status`,
`rescue`; env profiles for local, Pi, CCAD; `run`, `status` skills; SessionStart hook.
*Accept:* a snake_rl sweep runs locally through expkit; a small snake_rl sweep runs on CCAD
(pure Python, no containers: a cheap way to shake out the SLURM backend); then dl2l's `smoke`
experiment runs on CCAD through its cell script, with submit/rescue.

**Phase 4: collect and store.** Artifact sync, generic manifest with provenance, extractor
hook, HF upload backend, `publish` skill, data-preservation hook.
*Accept:* snake_rl's experiment is uploaded to an HF dataset and the report links it; a dl2l run
through expkit produces a byte-identical Parquet tree to the Ansible path.

**Phase 5: adopt both repos.** `adopt` skill; snake_rl moves to the spec (its `docs/experiments/`
layout keeps working); dl2l runs experiments through expkit while the Ansible path stays
available until two real experiments have gone through cleanly, then the duplicated code
(`dl2l_analysis.stats/report/config`, `validate_experiment.py`, trial-runner roles) is removed
and dl2l's CLAUDE.md dev cycle points at the skills.
*Accept:* one new pre-registered experiment in each repo, done end to end with the toolkit.

## 10. Open questions (need your call)

- **Q1. Repo name and visibility.** Proposed `felipedreis/expkit`, public (makes plugin and
  `pip install git+...` simplest). Alternatives: `labkit`, `research-kit`; private works too but
  needs a token in every environment that installs it.
- **Q2. Execution engine.** Recommended above: Python run engine in expkit, Ansible kept only for
  provisioning. The alternative is to publish the Ansible roles as a shared collection and make
  snake_rl use Ansible too: less new code, but heavier for small Python projects.
- **Q3. Data store for snake_rl.** Its results are in git today. Proposed: a separate HF dataset
  (`felipedreis/snake-rl-experiments`), or a shared `felipedreis/experiments` dataset with one
  prefix per project. Shared is simpler to browse; separate keeps access and size apart.
- **Q4. How strict is pre-registration by default?** Proposed: confirmatory runs require a
  freeze; `--exploratory` is always available and labels its outputs. dl2l's past experiments
  never froze anything, so this is a real change in how dl2l works.
- **Q5. Spec location in each repo.** Keep `experiments/<id>.yml` (dl2l) and allow a directory
  form `docs/experiments/<id>/experiment.yml` (snake_rl, where protocol, report and figures sit
  together)? Proposed: support both; the directory form is the default for new projects.
- **Q6. Python baseline.** 3.11+ with pydantic, pyyaml, numpy, scipy, pandas, matplotlib;
  `huggingface_hub` and `duckdb` as optional extras. Fine for CCAD's conda env?

## 11. Risks

- **Rewriting proven CCAD logic.** The live-cluster findings in dl2l's roles were expensive.
  Mitigation: the project-specific half moves verbatim into dl2l's cell script; expkit only
  takes the generic half; dl2l keeps the Ansible path until parity is shown on real runs.
- **The spec growing into a programming language.** Mitigation: anything that needs logic goes
  in the analysis module or the cell script; the schema only gets fields that the CLI acts on.
- **Hooks getting in the way.** Mitigation: every hook is fast, has a clear message saying how
  to proceed, and can be turned off in `expkit.toml`.
- **Version skew across repos.** Mitigation: projects pin a tag in both `pip` and the plugin; the
  spec carries `schema: expkit/v1` and `expkit spec migrate` handles upgrades.
