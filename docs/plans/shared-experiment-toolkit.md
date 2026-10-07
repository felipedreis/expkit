# Plan: expkit, a shared experiment toolkit for dl2l, snake_rl and later repos

Status: **v2 approved 2026-10-07; Phase 0 in progress** (skeleton done, environment spike
ready to run: see `docs/spike/README.md`). v1 is in git history. v2 changes direction on three
points the review asked for:

1. **Reuse the Ansible infrastructure.** dl2l's roles for the local machine, the Raspberry Pi
   cluster and CCAD become a shared Ansible collection, instead of being rewritten in Python.
2. **One reproducible setup for both projects.** Each project supplies only a small, fixed
   contract (section 4). snake_rl then runs on the Pi and CCAD with the same roles as dl2l.
   dl2l gets snake_rl's rigour: hypotheses written as configuration and checked by code.
3. **Callbacks instead of polling.** When results are ready, the toolkit wakes the agent
   (section 7), so nobody, human or model, has to keep checking on jobs.

## 1. What each repo brings today

| | dl2l | snake_rl |
|---|---|---|
| Declarative spec | `experiments/<name>.yml`: conditions, trials, image, extract, upload, analysis module | none; the design is prose in `PROTOCOL.md` plus a bash `run.sh` |
| Hypotheses and rigour | written in the report, after the run | **pre-registered**: directional hypotheses with rationale and pilot effect; protocol, `run.sh` and `analyze.py` frozen by SHA-256 before any confirmatory run; exact permutation tests, Holm, bootstrap CIs, Hedges' g, a fixed decision rule; deviations reported |
| Seeds | none: the simulator's randomness is unseeded, so a trial cannot be re-run identically | explicit seeds, disjoint from the pilot's |
| Execution | Ansible on 3 environments: local docker compose; Pi (SLURM + Docker); CCAD (SLURM + Singularity, submit then rescue, `DONE` sentinels, ports derived from job ids, image digest check, incremental collection under disk quota) | `xargs -P 8` on one machine |
| Collection and storage | Arrow → DuckDB → Parquet + `manifest.json`; always uploaded to HF `felipedreis/dl2l-experiments` | JSON per run committed to git |
| Analysis and report | `dl2l_analysis` (Kruskal-Wallis + Bonferroni MWU, Cliff's delta, ICC, survival) + `ReportBuilder` | one-off `analyze.py` + hand-written `REPORT.md` |

The Ansible roles encode months of live-cluster findings (qos per partition, the unique port
range per job, the sandbox rebuild race, `delegate_to` needing `ansible_connection: ssh`, the
async polling that hangs over the VPN, the disk quota). The plan keeps all of that and only
moves the dl2l-specific parts out.

## 2. What expkit ships

One repo, three parts that version together under one tag:

| Part | Holds | Installed by |
|---|---|---|
| **Ansible collection `felipedreis.expkit`** | playbooks and roles for image, trials, collection, upload, notification; inventories for local, Pi and CCAD | `ansible-galaxy collection install git+https://github.com/felipedreis/expkit.git,vX.Y.Z` (pinned in each project's `requirements.yml`) |
| **Python package `expkit`** | the deterministic parts: spec schema and validation, freeze and verify, power analysis, outcome evaluation, statistics, report rendering, the notifier, and a thin `expkit` CLI that calls `ansible-playbook` | `pip install "expkit @ git+https://github.com/felipedreis/expkit@vX.Y.Z"` |
| **Claude Code plugin** | skills, hooks and a protocol-reviewer subagent that drive the CLI | `/plugin marketplace add felipedreis/expkit`, then `/plugin install expkit` |

Rule of thumb: anything that must give the same answer twice lives in the collection or the
package. Skills only orchestrate, ask questions and write prose. Hooks call the CLI.

```
expkit/
  galaxy.yml                       # collection metadata
  playbooks/
    run_experiment.yml             # submit (and on local/Pi, wait); generalised from dl2l
    collect.yml                    # was "-e rescue=true": sync, verify, upload, notify
    provision.yml                  # per-env setup (from provision-pi.yml / provision-ccad.yml)
  roles/
    spec/                          # load + validate (calls `expkit validate`), apply defaults
    image_local/ image_pi/ image_ccad/      # build / buildx arm64 + push / pull SIF + sandbox
    runner_local/ runner_pi/ runner_ccad/   # cell matrix, SLURM arrays, sentinels, job-id state
    finalize/                      # per-experiment completion job (section 7)
    collect/                       # incremental sync + verify + cleanup (from ccad_collect.sh)
    upload/                        # HF dataset upload + manifest
    notify/                        # callback channels (section 7)
    templates/slurm_cell.sh.j2     # generic SLURM wrapper around the project's cell entrypoint
  inventories/{local,pi,ccad}/     # host facts shared by every project; no secrets
  src/expkit/                      # Python package (spec, freeze, power, outcomes, stats, report, notify, cli)
  .claude-plugin/{plugin.json,marketplace.json}
  skills/  agents/  hooks/
  templates/                       # scaffolds for `expkit adopt` and `expkit new`
  tests/                           # unit, golden, and ansible-lint / molecule for roles
  docs/
```

## 3. One reproducible setup

Reproducible means: the same frozen spec, the same image digest and the same seeds give the
same trial on any environment. Three decisions follow.

- **Every project runs from a container image, on every environment.** dl2l already does.
  snake_rl gains a small `Dockerfile` (python-slim + numpy + the package) built by CI for
  amd64 and arm64 and pushed to GHCR. The local machine and the Pi run it with Docker; CCAD
  pulls it as a Singularity SIF through the existing `image_ccad` digest-checked sandbox flow. A
  venv runtime stays available for quick local exploratory runs, but confirmatory runs need an
  image.
- **The freeze records the image digest, not a tag.** `latest` keeps moving; the frozen spec
  pins `ghcr.io/...@sha256:...`. This replaces the "pin with `-e dl2l_image=`" convention with
  something enforced.
- **Every trial has an explicit seed.** The runner assigns `seed = seeds[trial]` from the
  spec and passes it to the cell. snake_rl already accepts one. **dl2l does not seed its
  randomness today**: `RandomPositionFactory` seeds from `System.currentTimeMillis()`, and
  `RandomFilter`, `MemoryFilter`, `ActionProbabilityFilter` and `FullAppraisal` use self-seeding
  `new Random()` (the filters already have seeded constructors for tests), so
  porting dl2l includes a small change: a `seed` setting in the simulation config that seeds one
  generator per actor system, derived per creature. Without it, dl2l results can be repeated
  statistically but no single trial can be replayed. Akka's message scheduling stays
  nondeterministic either way, so the honest claim for dl2l is "same seed, same initial
  conditions and random streams", not "bit-identical runs". The report says so.

## 4. The per-project contract (the minimum each project must provide)

A project adopts expkit by adding **one manifest and three small pieces of code**. Nothing else
in the toolkit knows anything about the project.

### 4.1 `expkit.yml` at the project root

```yaml
project: snake_rl
image:
  name: ghcr.io/felipedreis/snake_rl      # CI builds and pushes; freeze pins the digest
  build: docker/Dockerfile                # used by image_local / image_pi when source: build
paths:
  experiments: docs/experiments           # one dir per experiment: experiment.yml, protocol.md, report
  data: data                              # local collected data (gitignored)
cell:
  entrypoint: expkit/cell.sh              # inside the image
  resources: {cpus: 1, mem: 2G, time: "00:30:00"}   # defaults; a spec can override per condition
  ports: 0                                # how many ports the cell needs (dl2l: 7)
outcomes: snake_rl.expkit_outcomes        # Python module, section 4.3
extract: null                             # optional, section 4.4
store:
  backend: huggingface
  repo: felipedreis/snake-rl-experiments
```

### 4.2 The cell entrypoint: run one trial

One executable that runs **one (condition, trial)** and exits. The runner calls it identically
on every environment, with everything it needs in environment variables:

| Variable | Meaning |
|---|---|
| `EXPKIT_EXPERIMENT`, `EXPKIT_CONDITION`, `EXPKIT_TRIAL` | identity of the cell |
| `EXPKIT_SEED` | the trial's seed |
| `EXPKIT_TRIAL_DIR` | where outputs must go; created by the runner |
| `EXPKIT_PORT_BASE` | start of a port range reserved for this cell (from the job id; the CCAD fix, generalised) |
| `EXPKIT_CPUS` | CPUs granted, so the cell can size thread pools and JVM flags |
| `EXPKIT_P_<NAME>` | every parameter of the condition, e.g. `EXPKIT_P_AGENT=mfec`, `EXPKIT_P_SIMULATION=simulations/x.conf` |

Contract: exit 0 on success, non-zero on failure; write only under `EXPKIT_TRIAL_DIR`. The
runner owns everything around it: the SLURM array, the `DONE` sentinel with the exit code, the
log file, teardown, retries, and provenance.

- **snake_rl's cell** is about three lines: `snake-run "$EXPKIT_P_AGENT" "$EXPKIT_SEED" ... --results "$EXPKIT_TRIAL_DIR"`.
- **dl2l's cell** is the bulk of today's `run_trial.sh.j2` and `dl2l_trial.sh.j2`, minus the
  generic parts: start manager, detector and holder on `EXPKIT_PORT_BASE+n`, wait for the
  holder, stop. The Singularity-versus-compose difference becomes a `runtime` switch inside
  dl2l's cell, because a cell that needs several cooperating processes is a project concern.
  The live-cluster notes in those templates move with that code.

### 4.3 The outcomes module: turn one trial's outputs into numbers

```python
# snake_rl/expkit_outcomes.py
from expkit.outcomes import outcome

@outcome("late", unit="trial")
def late(trial_dir, params):        # -> float
    ...                             # mean score per episode in (S/2, S]

@outcome("early", unit="trial")
def early(trial_dir, params): ...
```

Each function maps one trial's directory to a number (or, with `unit="entity"`, to a table of
one row per creature or episode, see section 5). Hypotheses refer to outcomes by name. This
module is the only analysis code an experiment usually needs, and it is shared by all of a
project's experiments rather than rewritten each time. dl2l's existing measures (survival time,
behavioural efficiency, accumulated nutrients, and so on, now spread over `analysis/legacy/`
and `analysis/experiments/`) become a dl2l outcomes registry.

### 4.4 Optional extractor

Runs on the cluster after the cell, before `DONE` is final: `extract: "python3 -m dl2l_data.extract ..."`. dl2l
keeps its Arrow → Parquet step exactly as it is. snake_rl has none.

That is the whole contract: **`expkit.yml`, a cell entrypoint, an outcomes module, an optional
extractor**, plus the Dockerfile the project already has or adds.

## 5. Hypotheses as configuration, checked by code

The experiment spec merges dl2l's `experiments/<name>.yml` with snake_rl's `PROTOCOL.md`.
Hypotheses are data that the engine evaluates, so the verdict table needs no hand-written code:

```yaml
schema: expkit/v1
id: mfec_dqn_nec
status: draft                     # draft -> frozen -> submitted -> collected -> analysed -> reported
question: How does MFEC compare with DQN and NEC on Snake?

design:
  factors:
    agent: [random, dqn, nec, mfec]
    config:
      C1: {size: 7,  distractors: 0, steps: 40000}
      C2: {size: 7,  distractors: 4, steps: 40000}
      C3: {size: 10, distractors: 0, steps: 60000}
  cells: full_factorial            # or an explicit `conditions:` list (dl2l's form)
  seeds: 101-110                   # trials = len(seeds)
  pilot_seeds: 1-5                 # validator rejects any overlap with seeds

outcomes:
  late:  {role: primary}
  early: {role: primary}
  rate_late: {role: secondary}

hypotheses:
  - id: H1a
    where: {config: C1}
    outcome: late
    compare: {a: {agent: mfec}, b: {agent: dqn}}
    direction: greater
    rationale: States repeat often on a clean 7x7 board; episodic tables excel there.
    pilot: {a: 1.54, b: 0.97, sd: 0.1, n: 5}

assumptions:
  - {id: A1, text: Runs with different seeds are independent samples.}

analysis:
  test: permutation_exact          # | permutation_mc | mann_whitney | welch_t | kruskal_posthoc | logrank
  sides: two
  correction: holm                 # over all confirmatory hypotheses
  alpha: 0.05
  effect_sizes: [mean_diff_bootstrap_ci, hedges_g]
  decision: directional            # supported / contradicted / not supported
  missing: {rerun: 1, then: exclude_and_report}
  power: {method: simulation, target: 0.8}

run:
  environments: [local, pi, ccad]  # where this spec is allowed to run
  resources: {cpus: 1}
  max_concurrent: 16               # the CCAD disk-quota lesson

notify: [github_pr, claude_routine]   # section 7
```

What the code does with it:

- **`expkit validate`** checks that every hypothesis names a declared outcome and conditions
  that exist, that the seeds do not overlap the pilot's, that `store` is enabled, and that the
  outcomes module defines every outcome.
- **`expkit power`** simulates each hypothesis under the declared test and correction, using
  the pilot effect and spread, and proposes the number of seeds. This implements dl2l's dev
  cycle step 5c ("choose the sample size by a statistical method").
- **`expkit analyze`** computes every outcome for every trial (from the outcomes module), runs
  the declared test per hypothesis, applies the correction and the decision rule, and writes
  `results.json` plus the descriptives and verdict tables. Anything not declared in the spec
  is labelled exploratory.

**The unit of analysis is explicit.** dl2l has many creatures per trial, and creatures in the
same trial are not independent. An outcome declared with `unit: entity` is reduced to one
number per trial by its declared `aggregate` (default: mean) before testing. Tests on the
creatures themselves are only allowed with a clustered method (mixed model, or permutation of
whole trials), and the report states the ICC and design effect, which `dl2l_analysis.stats`
already computes. This is the main rigour change for dl2l: the engine makes the unit a
declared, checked choice instead of a per-script habit, so a test can no longer count
creatures as independent samples by accident.

## 6. Freezing, provenance and deviations

`expkit freeze <id>` validates the spec, requires a clean git tree, resolves the image tag to a
digest, and writes `FROZEN.json`: the UTC time, git commit, image digest, and SHA-256 of the
spec, `protocol.md`, the outcomes module and the cell entrypoint. It sets `status: frozen`.

- `run_experiment.yml` refuses a confirmatory run unless the frozen hashes still match.
  `-e exploratory=true` skips the check and marks everything that comes out of it as exploratory.
- Changing a frozen file goes through `expkit deviate <id> "<reason>"`. That appends to a
  deviations log, which the report prints verbatim.
- Every collected trial gets provenance in `manifest.json`, extending dl2l's: spec hash, image
  digest, environment, node, SLURM job id, seed, exit code, wall-clock time, and sizes of the
  files it produced.

## 7. Callbacks: results wake the agent

The goal is that nobody polls. After submitting, the agent's turn ends. When the last trial
finishes, the toolkit itself sends a signal that starts the next step.

### 7.1 Who notices that the experiment finished

| Environment | Completion detection | Where the notifier runs |
|---|---|---|
| local | the playbook runs detached (`setsid nohup`); its last play is the notifier | the local machine |
| Pi | a **finalize job** submitted with `sbatch --dependency=afterany:<all array ids>`. SLURM starts it when every trial has ended, so nothing polls | a Pi node (internet access) |
| CCAD | the same finalize job; compute nodes have **no internet**, so it only writes `EXPERIMENT_DONE`. A tiny relay started detached on the login node (the `setsid nohup` pattern `image_ccad` already uses) waits for that file, then uploads and notifies | the login node, which has outbound access (it already pulls from GHCR) |

The finalize step does the collection work wherever the data is: verify every trial (a `DONE`
with exit code 0 *and* the expected outputs, the `ccad_collect.sh` lesson), upload to HF, write
the manifest, then notify. Because the data is already on HF by the time anyone is woken, **the
woken agent can analyse from anywhere, including a cloud session**, without the CEFET VPN. The
VPN is only needed to submit.

### 7.2 How the agent is woken (the `notify` role, pluggable)

| Channel | What it does | Wakes |
|---|---|---|
| `github_pr` (default) | Each confirmatory experiment lives on a **tracking pull request**: the spec and protocol are reviewed there before freezing, results and the report are pushed to it, and merging it means "reported". The notifier posts a comment on that PR: experiment id, trials ok/failed, HF path, manifest hash. | The session that submitted the experiment is subscribed to the PR, so the comment wakes **that same conversation**, with its context intact. |
| `claude_routine` | `POST https://api.anthropic.com/v1/claude_code/routines/<id>/fire` with a `text` payload (same fields). The routine's prompt is "an expkit experiment finished: run `/expkit:collect-analyze` for the experiment named in the payload". | A **new** cloud session, for when the original session is gone. |
| `ntfy` / email | A push or email to you with the same summary. | You. |
| `local_resume` | `claude --resume <session> -p "<summary>"` on the local machine. | A local CLI session. |

Several channels can be listed; the default is `github_pr` plus `ntfy`. The agent also keeps one
long fallback check-in (`send_later`, about every 4 hours) in case a notification is lost, but
that is a safety net, not the mechanism.

Security: the notifier's tokens (a fine-grained GitHub token that can only comment on the
project's repos, the routine token, the HF token) live in the cluster user's environment or a
`0600` file on the login node, are never in a repo, and are set up by `provision.yml`.
Notification text is data. The skills act on it only through `expkit` commands that re-read
the manifest from HF, never by following instructions in the comment.

### 7.3 Things to verify early (a Phase 0 spike)

- the CCAD login node allows a small long-lived user process, and reaches `api.github.com`,
  `huggingface.co` and `api.anthropic.com`. If long-lived processes are not allowed, fall back
  to `cron` on the login node, then to email via SLURM's `--mail-type=END`;
- whether a routine's API trigger can fire into an existing session rather than a new one;
- the Pi nodes reach the same three hosts.

## 8. Skills, agent and hooks

Skills (namespaced `expkit:` once installed):

| Skill | What it does |
|---|---|
| `adopt` | One-time project onboarding: writes `expkit.yml`, a cell entrypoint and an outcomes module from what the repo already has, adds CLAUDE.md lines, migrates existing specs (marked `legacy: true`). |
| `design` | Interviews you (question, mechanism, outcomes, what result would change your mind), drafts the spec and `protocol.md`, insists on directional hypotheses with a rationale, and on a pilot when effect sizes are unknown. Opens the tracking PR. |
| `pilot` | Runs an exploratory pilot on disjoint seeds and fills in the `pilot:` fields. |
| `power` | Runs `expkit power` and records the chosen number of seeds with its reasoning. |
| `review-protocol` | Hands the draft to the `protocol-reviewer` subagent, an adversarial reader looking for undirected or unfalsifiable hypotheses, pilot-seed reuse, too many primary outcomes, underpowered tests, pseudo-replication (creatures treated as independent), and outcomes defined after looking at data. |
| `freeze` | Validates, freezes and commits. |
| `submit` | Picks the environment, runs the playbook, subscribes to the tracking PR, arms the fallback check-in, and **ends the turn**. |
| `collect-analyze` | What a callback starts: verifies the manifest on HF, runs `expkit analyze`, renders the report, pushes to the tracking PR, and tells you the verdicts. |
| `report` | Writes the Analysis and Limitations prose, keeping claims within the verdict table. |
| `status` | Lists experiments by lifecycle state, with trials done or failed. |

Hooks (thin scripts over the CLI; each can be turned off in `expkit.yml`):

| Event | Hook | Effect |
|---|---|---|
| `PreToolUse` Edit/Write | frozen-guard | Blocks edits to files listed in a `FROZEN.json` unless a matching deviation is logged; the message says how to log one. |
| `PostToolUse` Edit/Write on a spec | validate-on-save | Runs `expkit validate` and returns the errors at once. |
| `PreToolUse` Bash | data-preservation | Blocks deleting data directories or raw dumps that the manifest says were never uploaded. |
| `SessionStart` | in-flight summary | One line per submitted experiment that is still running, so a new session knows. |

## 9. Porting each project

**snake_rl** (smaller, so it goes first and proves the contract):
1. Add the Dockerfile and a CI workflow publishing to GHCR (amd64 + arm64).
2. Add `expkit.yml`, `expkit/cell.sh`, and `expkit_outcomes.py` (the `late`, `early` and
   `rate_late` functions lifted from `analyze.py`).
3. Write `mfec_dqn_nec` as a spec. Acceptance: `expkit analyze` over the existing
   `results/exp_mfec` reproduces `results.md` and all seven verdicts exactly.
4. Run a new small experiment on the Pi, then on CCAD, through the shared roles.

**dl2l**:
1. Add the seed setting (section 3), with a test that the same seed gives the same initial world
   and the same random draws.
2. Move the project-specific parts of `trial_runner_*` and `common/templates/docker-compose.yml.j2`
   into `expkit/cell.sh` (with its compose and Singularity runtimes). Keep `dl2l_data.extract` as
   the extractor.
3. Build the outcomes registry from the measures in `analysis/legacy/` and
   `analysis/experiments/`.
4. Migrate the six `experiments/*.yml` as `legacy: true`, so they validate without hypotheses.
5. Run `smoke` through the collection on local, Pi and CCAD. Acceptance: the Parquet tree matches
   the current Ansible path for the same input, file for file (except for timestamps).
6. Then remove dl2l's own `ansible/` roles, `validate_experiment.py`, and the parts of
   `dl2l_analysis` that the package replaces, and update the CLAUDE.md dev cycle to the skills.

## 10. Phases

| Phase | Delivers | Accepted when |
|---|---|---|
| **0. Skeleton and spike** | repo layout, CI (ruff, pytest, ansible-lint), release tags, plugin installs; the section 7.3 checks done on the real clusters | `ansible-galaxy` and `pip` install from a tag; spike findings written into this plan |
| **1. Collection from dl2l's roles** | roles moved and generalised (`spec`, `image_*`, `runner_*`, `slurm_cell.sh.j2`, `collect`, `upload`); dl2l parts pulled out to `cell.sh` behind the contract | dl2l `smoke` runs through the collection on all three environments with output identical to today |
| **2. Spec, freeze, outcomes, stats** | schema + validation, freeze/verify/deviate, outcomes API, ported statistics, report renderer, power | snake_rl's `results.md` reproduced exactly; one dl2l report's tables reproduced from HF |
| **3. Callbacks** | `finalize` job, CCAD relay, `notify` channels, tracking-PR flow | a CCAD run submitted from one session wakes it with a PR comment and no polling; the same for the Pi |
| **4. Skills and hooks** | the section 8 skills, reviewer agent and hooks | one new experiment per repo goes design → freeze → submit → callback → report with only the decisions left to you |
| **5. Port and retire** | section 9 for both repos; dl2l's duplicated code removed | both repos run only through expkit |

Phase 1 comes before the spec work on purpose: moving the roles is the riskiest step (the
cluster lessons), and doing it first, with dl2l's current spec format, keeps dl2l working at every
step. Phase 2 can start in parallel on the Python side.

## 11. Decisions (2026-10-07)

All five open questions from the v2 draft were answered "yes":

1. **One tracking PR per experiment** is the default callback target and the experiment's
   lifecycle record (spec and protocol reviewed there, results and report pushed there, merge
   means "reported").
2. **Notifier tokens** live on each cluster in a `0600` file in the cluster user's home,
   written once by provisioning from the local `.env.local`.
3. **snake_rl data** goes to its own HF dataset, `felipedreis/snake-rl-experiments`.
4. **dl2l seeding** is its own dl2l issue, done before the port:
   [felipedreis/dl2l#95](https://github.com/felipedreis/dl2l/issues/95).
5. **Baseline:** Python 3.11+ and ansible-core 2.16+ on the control machine; numpy, scipy,
   pandas, pyyaml, pydantic, with `huggingface_hub` and `duckdb` as extras. The spike records
   what CCAD's conda environment actually has.

## 12. Risks

- **Breaking dl2l's cluster runs while moving the roles.** Mitigation: dl2l keeps its own
  `ansible/` until `smoke` matches on all three environments; the moved code keeps its comments.
- **CCAD login-node policy blocks the relay.** Mitigation: the cron and SLURM-mail fallbacks;
  the fallback check-in still catches it, just later.
- **Callback spam or loops.** Mitigation: one notification per experiment completion (plus one
  per failure batch); the notify role is idempotent per manifest hash.
- **The spec growing into a programming language.** Mitigation: logic goes in the outcomes
  module or the cell; the schema only gets fields the code acts on.
- **Version skew across repos.** Mitigation: each project pins one expkit tag for the
  collection, package and plugin; specs carry `schema: expkit/v1`, and `expkit spec migrate`
  handles upgrades.
