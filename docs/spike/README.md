# Phase 0 spike: what each environment allows

Section 7 of the plan (callbacks instead of polling) depends on facts about the clusters that
nobody has checked yet. This spike checks them before Phase 3 builds on them.

| # | Question | Why it matters |
|---|---|---|
| 1 | Can the **login node** reach `api.github.com`, `huggingface.co`, `api.anthropic.com`? | The CCAD relay uploads to HF and posts the callback from there. |
| 2 | Can **compute nodes** reach them? | If yes (expected on the Pi), the finalize job notifies by itself, with no relay. |
| 3 | Does a **detached login-node process** survive the SSH session and the VPN dropping? | The relay is such a process. |
| 4 | Is **cron** allowed on the login node? | Fallback for the relay if 3 is "no". |
| 5 | Does an **`afterany` dependency job** start only after every array task ended? | That job is how completion is detected without polling. |
| 6 | Can a **routine's API trigger** wake an *existing* session, or only start a new one? | Decides whether `claude_routine` can replace `github_pr` as the default callback. |
| 7 | Does a **PR comment posted with your token** wake a session subscribed to that PR? | The default callback (`github_pr`) relies on it. |

Questions 1 to 5 are answered by `playbooks/spike.yml`; 6 and 7 by the manual steps below.

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
ansible-playbook -i inventories/ccad playbooks/spike.yml                   # start; returns at once
# disconnect, let the VPN drop, wait at least 30 minutes (the heartbeat runs for 2 h)
ansible-playbook -i inventories/ccad playbooks/spike.yml -e spike_phase=check
expkit spike-report spike-results/ccad.json                               # verdict table
ansible-playbook -i inventories/ccad playbooks/spike.yml -e spike_phase=check -e spike_cleanup=true
```

`spike-results/` is gitignored because the raw JSON holds host and user names. Paste only
the verdict tables under "Findings" below.

What the start phase leaves on the cluster, under `$HOME/expkit/spike` (CCAD) or
`/mnt/dl2l-shared/expkit/spike` (Pi): the rendered scripts, `login.json`, a heartbeat that
appends a timestamp every 60 s for 2 h, a 2-task array job (1 CPU, 512 MB, under 10 min) and
a finalize job that depends on it. On CCAD both jobs go to `short` / `short_qos`.

## Question 6: routine API trigger into an existing session

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
