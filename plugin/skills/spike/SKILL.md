---
name: spike
description: Run or interpret the expkit Phase 0 environment spike, which checks whether a runner environment (local, the Raspberry Pi SLURM cluster, or CCAD) supports what expkit's callbacks depend on, such as SLURM job-end email, SLURM afterany dependency jobs, outbound HTTPS from compute nodes, and on the Pi only a detached login-node process and cron. Use when the user asks to run the spike, check what a cluster allows, or read spike results.
---

# expkit environment spike

The spike answers, per environment, the questions in section 7.3 of
`docs/plans/shared-experiment-toolkit.md` in the expkit repo. It has two phases so that
nothing waits on a cluster over a VPN that drops idle connections.

## Run it

The user runs these from a checkout of expkit on a machine that can reach the cluster (for
CCAD, that means on the CEFET VPN). A cloud session cannot reach the Pi or CCAD, so if you
are in one, give the user the commands instead of running them.

1. Start: `ansible-playbook -i inventories/<env> playbooks/spike.yml -e spike_mail_user=<address>`.
   It probes the login node and (on SLURM) submits a 2-task array job plus a finalize job with
   `--dependency=afterany` on it, which emails the address when it ends. On the Pi only it also
   starts a detached heartbeat. It returns at once.
2. Wait for the SLURM email (note when it arrives, and whether it went to spam), or 30 minutes.
   **CCAD forbids cron and long-running or detached login-node processes**: never start
   anything there that outlives the SSH command, and never set `expkit_login_daemons_allowed`
   to true for CCAD.
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

- **SLURM email arrives** (with `MailProg` set): it is the completion signal; the Gmail bridge
  (plan 7.1a) turns it into a PR comment.
- **No email** (no `MailProg`, blocked or in spam): fix delivery (spam filter, or `msmtp` on
  the Pi), or fall back to the agent's long safety-net check-in.
- **Dependency verdict is not "yes"**: completion detection cannot rely on `afterany`;
  say so in the plan before Phase 3.
- **Compute nodes reach the hosts** (expected on the Pi, not on CCAD): the finalize job uploads
  to HF by itself. Otherwise collection is `expkit collect` from a machine on the VPN (plan 7.4).
- **Pi only, heartbeat and cron**: record them; they are options for the Pi controller.
