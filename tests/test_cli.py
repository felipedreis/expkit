from pathlib import Path

import pytest

import expkit
from expkit import cli, doctor

FIXTURE = Path(__file__).parent / "fixtures" / "spike_ccad.json"


def test_version(capsys):
    assert cli.main(["version"]) == 0
    assert capsys.readouterr().out.strip() == expkit.__version__


def test_spike_report(capsys):
    assert cli.main(["spike-report", str(FIXTURE)]) == 0
    out = capsys.readouterr().out
    assert out.startswith("### ccad")
    assert "| Can compute nodes reach GitHub, HF and Anthropic? | **no** |" in out


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("ansible-playbook [core 2.17.14]", (2, 17)),
        ("ansible-playbook 2.9.27", (2, 9)),
        ("garbage", None),
    ],
)
def test_parse_ansible_version(text, expected):
    assert doctor.parse_ansible_version(text) == expected


def test_check_python():
    assert doctor.check_python((3, 11, 0)).ok
    assert not doctor.check_python((3, 10, 9)).ok
