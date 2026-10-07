---
name: spike
description: Run or interpret the expkit Phase 0 environment spike, which checks whether a runner environment (local, the Raspberry Pi SLURM cluster, or CCAD) allows what expkit's callbacks depend on, such as outbound HTTPS from login and compute nodes, a detached long-lived login-node process, cron, and SLURM afterany dependency jobs. Use when the user asks to run the spike, check what a cluster allows, or read spike results.
---

# expkit environment spike

The spike answers, per environment, the questions in section 7.3 of
`docs/plans/shared-experiment-toolkit.md` in the expkit repo. It has two phases so that
nothing waits on a cluster over a VPN that drops idle connections.

## Run it

The user runs these from a checkout of expkit on a machine that can reach the cluster (for
CCAD, that means on the CEFET VPN). A cloud session cannot reach the Pi or CCAD, so if you
are in one, give the user the commands instead of running them.

1. Start: `ansible-playbook -i inventories/<env> playbooks/spike.yml`. It probes the login
   node, starts a detached heartbeat, and (on SLURM) submits a 2-task array job plus a job
   with `--dependency=afterany` on it. It returns at once.
2. Wait at least 30 minutes. Disconnecting in between is the point: it shows whether the
   heartbeat survives the SSH session and the VPN dropping.
3. Check: the same command with `-e spike_phase=check`. It writes
   `spike-results/<env>.json` locally (gitignored: it holds host and user names).
4. Report: `expkit spike-report spike-results/<env>.json` prints a markdown verdict table.
5. Clean up: `-e spike_phase=check -e spike_cleanup=true` stops the heartbeat and deletes
   the remote spike directory.

For CCAD the username comes from `$CCAD_USERNAME` or a gitignored `.env.local` holding
`CCAD_USERNAME=<cpf>`. Never print it, and never paste raw spike JSON into a commit, an
issue or a PR.

## Interpret it

Record the verdict tables (not the raw JSON) in `docs/spike/README.md` under "Findings",
then update section 7 of the plan:

- **Login node reaches GitHub, HF and Anthropic** and **the heartbeat survives**: the
  login-node relay design in section 7.1 holds.
- **Heartbeat dies, cron allowed**: the relay becomes a cron entry that checks for
  `EXPERIMENT_DONE` (cheap cluster-side polling; the agent still never polls).
- **Neither**: fall back to SLURM `--mail-type=END` and the agent's long safety-net check-in.
- **Compute nodes reach the hosts** (expected on the Pi, not on CCAD): the finalize job can
  upload and notify by itself, with no relay.
- **Dependency verdict is not "yes"**: completion detection cannot rely on `afterany`;
  say so in the plan before Phase 3.
