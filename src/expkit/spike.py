"""Turn the raw JSON written by `playbooks/spike.yml -e spike_phase=check` into verdicts.

Phase 0 has to answer, per environment (see docs/plans/shared-experiment-toolkit.md, 7.3):

- Can the login node and the compute nodes reach GitHub, HuggingFace and Anthropic's API?
- Does a detached process on the login node survive the SSH session (and the VPN) going away?
- Is cron allowed on the login node (the fallback if long-lived processes are not)?
- Does a job submitted with --dependency=afterany start only after every array task ended?

The playbook only gathers facts; the judgement lives here so it can be unit-tested.
"""

from __future__ import annotations

from dataclasses import dataclass

TERMINAL_STATES = {
    "COMPLETED",
    "FAILED",
    "CANCELLED",
    "TIMEOUT",
    "OUT_OF_MEMORY",
    "NODE_FAIL",
    "PREEMPTED",
    "BOOT_FAIL",
    "DEADLINE",
}
CALLBACK_HOSTS = ("api.github.com", "huggingface.co", "api.anthropic.com")


@dataclass
class Verdict:
    question: str
    answer: str  # "yes", "no", "partial" or "unknown"
    detail: str


def reachable(code: str | None) -> bool:
    """curl's %{http_code} is a 3-digit status for any HTTP answer and 000 when it got none."""
    code = (code or "").strip()
    return len(code) == 3 and code.isdigit() and code != "000"


def _hosts_verdict(question: str, probes: list[dict], hosts=CALLBACK_HOSTS) -> Verdict:
    if not probes:
        return Verdict(question, "unknown", "no probe output was collected")
    rows, all_ok, any_ok = [], True, False
    for h in hosts:
        codes = [p.get(f"https_{h}") for p in probes]
        ok = all(reachable(c) for c in codes)
        all_ok &= ok
        any_ok |= any(reachable(c) for c in codes)
        rows.append(f"{h}: {', '.join(c or 'missing' for c in codes)}")
    answer = "yes" if all_ok else ("partial" if any_ok else "no")
    return Verdict(question, answer, "; ".join(rows))


def heartbeat_verdict(hb: dict, interval_s: int, planned_s: int) -> Verdict:
    q = "Does a detached login-node process survive the SSH session?"
    beats = hb.get("beats") or 0
    first, last, now = hb.get("first"), hb.get("last"), hb.get("now")
    if beats < 2 or first is None or last is None:
        return Verdict(q, "no", f"only {beats} heartbeat(s) were written")
    lived = (last - first) / 60
    finished = (last - first) >= planned_s - 2 * interval_s
    alive = bool(hb.get("pid_alive"))
    fresh = now is not None and now - last <= 2 * interval_s
    if finished or (alive and fresh):
        state = "ran its full course" if finished else "is still running"
        return Verdict(q, "yes", f"it {state}: {beats} beats over {lived:.0f} min")
    return Verdict(q, "no", f"it stopped after {lived:.0f} min ({beats} beats); killed or reaped")


def cron_verdict(login: dict) -> Verdict:
    q = "Is cron allowed on the login node?"
    raw = login.get("crontab", "")
    if raw.startswith("allowed"):
        return Verdict(q, "yes", raw)
    if raw.startswith("denied") or raw == "missing":
        return Verdict(q, "no", raw)
    return Verdict(q, "unknown", raw or "not probed")


def dependency_verdict(sacct_lines: list[str], finalize_done: bool) -> Verdict:
    q = "Does an afterany dependency job start only after every array task ended?"
    if not finalize_done:
        return Verdict(q, "no", "the finalize job never wrote FINALIZE_DONE")
    states = [line.split("|")[1] for line in sacct_lines if line.count("|") >= 1]
    if not states:
        return Verdict(q, "unknown", "finalize ran, but sacct returned nothing to check")
    pending = [s for s in states if s.split()[0] not in TERMINAL_STATES]
    if pending:
        return Verdict(q, "no", f"finalize saw non-terminal array tasks: {pending}")
    return Verdict(q, "yes", f"finalize saw {len(states)} array task(s), all ended: {states}")


def verdicts(raw: dict, interval_s: int = 60, planned_s: int = 7200) -> list[Verdict]:
    login = raw.get("login") or {}
    out = [
        _hosts_verdict(
            "Can the login node reach GitHub, HF and Anthropic?", [login] if login else []
        ),
        heartbeat_verdict(
            {**(raw.get("heartbeat") or {}), "now": raw.get("now")}, interval_s, planned_s
        ),
        cron_verdict(login),
    ]
    if raw.get("scheduler") == "slurm":
        out.append(
            _hosts_verdict(
                "Can compute nodes reach GitHub, HF and Anthropic?", raw.get("compute") or []
            )
        )
        out.append(dependency_verdict(raw.get("sacct") or [], bool(raw.get("finalize_done"))))
    return out


def to_markdown(env: str, raw: dict, vs: list[Verdict]) -> str:
    lines = [f"### {env}", "", "| Question | Answer | Detail |", "|---|---|---|"]
    lines += [f"| {v.question} | **{v.answer}** | {v.detail} |" for v in vs]
    login = raw.get("login") or {}
    tools = {k[4:]: v for k, v in login.items() if k.startswith("ver_")}
    if tools:
        lines += [
            "",
            "Tools on the login node: " + "; ".join(f"`{k}`: {v}" for k, v in tools.items()),
        ]
    return "\n".join(lines) + "\n"
