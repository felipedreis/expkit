# Phase 0 spike: what each environment allows

Section 7 of the plan (callbacks instead of polling) depends on facts about the clusters that
nobody has checked yet. This spike checks them before Phase 3 builds on them.

| # | Question | Why it matters |
|---|---|---|
| 1 | Does **SLURM send job-end email** (and does it arrive, how late, not in spam)? | SLURM's email from the finalize job is the completion signal on every cluster. |
| 2 | Does an **`afterany` dependency job** start only after every array task ended? | That finalize job is how completion is detected without polling. |
| 3 | Can **compute nodes** reach `api.github.com`, `huggingface.co`, `api.anthropic.com`? | If yes (expected on the Pi), the finalize job uploads to HF itself. On CCAD we expect no. |
| 4 | Can the **login node** reach them? | Recorded for completeness; nothing on CCAD's login node runs after our SSH command returns. |
| 5 | Pi only: does a **detached process** survive, and is **cron** allowed on the controller? | Our own hardware, so these are options there. Never tested on CCAD (policy). |
| 6 | Can a **routine's API trigger** wake an *existing* session, or only start a new one? | Decides the fallback channel of the email bridge. |
| 7 | Does a **PR comment posted with your token** wake a session subscribed to that PR? | The email bridge's default action relies on it. |

Questions 1 to 5 are answered by `playbooks/spike.yml` (plus your inbox for question 1); 6 and
7 by the manual steps below.

**CCAD policy:** no cron and no long-running or detached processes on the login node. The
CCAD inventory sets `expkit_login_daemons_allowed: false`, so there the spike runs only short
commands inside its own SSH session plus two tiny SLURM jobs.

## Prerequisites (on the machine you run Ansible from)

```sh
git clone https://github.com/felipedreis/expkit && cd expkit
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
export PATH=$PWD/.venv/bin:$PATH
ansible-galaxy collection install ansible.posix
expkit doctor          # Python >= 3.11, ansible-core >= 2.16, outbound HTTPS
```

For CCAD: connect to the CEFET VPN, and either `export CCAD_USERNAME=<cpf>` or put
`CCAD_USERNAME=<cpf>` in a `.env.local` at the repo root (gitignored; it is PII).

## Questions 1 to 5: the playbook

Run for `pi` and `ccad` (and `local` if you like; it skips the SLURM questions):

```sh
ansible-playbook -i inventories/ccad playbooks/spike.yml \
  -e spike_mail_user=<you>+expkit@gmail.com                               # start; returns at once
# wait for the "Slurm Job_id=... Name=expkit_spike_finalize Ended" email (note when it arrives),
# or 30 minutes if it never comes; on the Pi, also disconnect so the heartbeat test means something
ansible-playbook -i inventories/ccad playbooks/spike.yml -e spike_phase=check \
  -e spike_mail_user=<you>+expkit@gmail.com
expkit spike-report spike-results/ccad.json                               # verdict table
ansible-playbook -i inventories/ccad playbooks/spike.yml -e spike_phase=check -e spike_cleanup=true
```

`spike-results/` is gitignored because the raw JSON holds host and user names. Paste only
the verdict tables under "Findings" below.

What the start phase leaves on the cluster, under `$HOME/expkit/spike` (CCAD) or
`/mnt/dl2l-shared/expkit/spike` (Pi): the rendered scripts, `login.json`, a 2-task array job
(1 CPU, 512 MB, under 10 min) and a finalize job that depends on it and emails you when it
ends. On CCAD both jobs go to `short` / `short_qos`. On the Pi only, it also starts a heartbeat
that appends a timestamp every 60 s for 2 h.

## Question 6: routine API trigger into an existing session

Already set up: the routine `expkit spike: callback test` (`trig_01H28pQS4UzFQVrhacubPHm6`) is
bound to the Phase 0 session, so skip step 1.

1. In the Claude Code session that should be woken, ask Claude to create a poke-only routine
   bound to that session ("expkit spike: callback"). Note its `trig_...` id.
2. At [claude.ai/code/routines](https://claude.ai/code/routines), open that routine, **Edit →
   Add another trigger → API**, copy the URL and generate a token.
3. From any machine (ideally the CCAD login node, which also answers question 1 for real):

   ```sh
   curl -sS -X POST "<routine URL>" \
     -H "Authorization: Bearer $EXPKIT_ROUTINE_TOKEN" \
     -H "anthropic-beta: experimental-cc-routine-2026-04-01" \
     -H "anthropic-version: 2023-06-01" \
     -H "Content-Type: application/json" \
     -d '{"text": "expkit spike: callback test"}'
   ```

4. Record whether the response's `claude_code_session_id` is the bound session (the session
   wakes with the payload) or a new one. Revoke the token afterwards.

## Question 7: PR comment wakes the subscribed session

1. Claude opens a throwaway PR in expkit and subscribes the session to it.
2. You post a comment on it with a fine-grained token limited to "Pull requests: write" on
   this repo (the token the notifier will use):

   ```sh
   curl -sS -X POST https://api.github.com/repos/felipedreis/expkit/issues/<PR>/comments \
     -H "Authorization: Bearer $EXPKIT_GH_TOKEN" \
     -d '{"body": "expkit spike: callback test"}'
   ```

3. Record whether the session woke on its own, and how long it took.

## Findings

_None yet. Paste each environment's `expkit spike-report` table here, plus the answers to
questions 6 and 7, then update section 7 of the plan to match._
