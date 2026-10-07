import json
from pathlib import Path

import pytest

from expkit import spike

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "spike_ccad.json").read_text())


def by_question(vs):
    return {v.question.split("?")[0]: v for v in vs}


@pytest.mark.parametrize(
    ("code", "ok"),
    [
        ("200", True),
        ("404", True),
        ("301", True),
        ("000", False),
        ("", False),
        (None, False),
        ("curl: (6)", False),
    ],
)
def test_reachable(code, ok):
    assert spike.reachable(code) is ok


def test_ccad_like_fixture():
    vs = by_question(spike.verdicts(FIXTURE))
    assert vs["Can the login node reach GitHub, HF and Anthropic"].answer == "yes"
    assert vs["Can compute nodes reach GitHub, HF and Anthropic"].answer == "no"
    # CCAD policy: these are never run there, and the report says so.
    assert vs["Is cron allowed on the login node"].answer == "skipped"
    assert vs["Does a detached login-node process survive"].answer == "skipped"
    dep = vs["Does an afterany dependency job start only after every array task ended"]
    assert dep.answer == "yes"
    mail = vs["Does SLURM email when the finalize job ends"]
    assert mail.answer == "check inbox"
    assert "Job_id=4243" in mail.detail


def test_daemon_tests_run_where_allowed():
    raw = {
        **FIXTURE,
        "login_daemons_allowed": True,
        "heartbeat": {"beats": 121, "first": 0, "last": 7200, "pid_alive": False},
        "login": {**FIXTURE["login"], "crontab": "allowed (empty)"},
    }
    vs = by_question(spike.verdicts(raw))
    assert vs["Does a detached login-node process survive the SSH session"].answer == "yes"
    assert vs["Is cron allowed on the login node"].answer == "yes"


def test_mail_not_requested():
    assert spike.mail_verdict({"mail_requested": False}).answer == "skipped"


def test_mail_without_mailprog():
    raw = {"mail_requested": True, "login": {"slurm_mail": ""}}
    assert spike.mail_verdict(raw).answer == "no"


def test_heartbeat_killed_early():
    hb = {"beats": 5, "first": 0, "last": 240, "pid_alive": False, "now": 3600}
    assert spike.heartbeat_verdict(hb, interval_s=60, planned_s=7200).answer == "no"


def test_heartbeat_still_running():
    hb = {"beats": 31, "first": 0, "last": 1800, "pid_alive": True, "now": 1830}
    assert spike.heartbeat_verdict(hb, interval_s=60, planned_s=7200).answer == "yes"


def test_heartbeat_alive_but_stale_is_not_trusted():
    # pid reused by another process: the log stopped long ago.
    hb = {"beats": 3, "first": 0, "last": 120, "pid_alive": True, "now": 3600}
    assert spike.heartbeat_verdict(hb, interval_s=60, planned_s=7200).answer == "no"


def test_heartbeat_never_wrote():
    assert spike.heartbeat_verdict({"beats": 0}, 60, 7200).answer == "no"


def test_dependency_saw_running_task():
    v = spike.dependency_verdict(["1_1|COMPLETED|x", "1_2|RUNNING|Unknown"], True)
    assert v.answer == "no"


def test_dependency_cancelled_counts_as_terminal():
    assert spike.dependency_verdict(["1_1|CANCELLED by 123|x"], True).answer == "yes"


def test_dependency_never_ran():
    assert spike.dependency_verdict([], False).answer == "no"


def test_partial_hosts():
    probes = [
        {
            "https_api.github.com": "200",
            "https_huggingface.co": "000",
            "https_api.anthropic.com": "200",
        }
    ]
    assert spike._hosts_verdict("q", probes).answer == "partial"


def test_local_env_skips_slurm_questions():
    raw = {**FIXTURE, "scheduler": "none"}
    questions = [v.question for v in spike.verdicts(raw)]
    assert not any("compute" in q or "afterany" in q or "email" in q for q in questions)


def test_cron_missing_is_no():
    assert spike.cron_verdict({"crontab": "missing"}).answer == "no"


def test_markdown_lists_every_verdict_and_tools():
    vs = spike.verdicts(FIXTURE)
    md = spike.to_markdown("ccad", FIXTURE, vs)
    assert md.count("\n| ") == len(vs) + 1  # header + one row per verdict
    assert "`sbatch`: slurm 23.02.7" in md
