"""Check that the control machine (the one running ansible-playbook) is ready for expkit."""

from __future__ import annotations

import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass

# Hosts the toolkit talks to: GitHub (tracking-PR callbacks), HuggingFace (data store),
# Anthropic (routine callbacks), GHCR (images), ntfy (push to the human).
HOSTS = ("api.github.com", "huggingface.co", "api.anthropic.com", "ghcr.io", "ntfy.sh")
MIN_PYTHON = (3, 11)
MIN_ANSIBLE = (2, 16)


@dataclass
class Check:
    name: str
    ok: bool
    detail: str


def check_python(version: tuple[int, ...] = sys.version_info[:3]) -> Check:
    ok = tuple(version[:2]) >= MIN_PYTHON
    shown = ".".join(map(str, version))
    return Check("python", ok, f"{shown} (need >= {'.'.join(map(str, MIN_PYTHON))})")


def parse_ansible_version(text: str) -> tuple[int, int] | None:
    """`ansible-playbook --version` prints e.g. 'ansible-playbook [core 2.17.14]' first."""
    for token in text.replace("[", " ").replace("]", " ").split():
        parts = token.split(".")
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            return int(parts[0]), int(parts[1])
    return None


def check_ansible() -> Check:
    exe = shutil.which("ansible-playbook")
    if not exe:
        return Check("ansible-core", False, "ansible-playbook not on PATH")
    out = subprocess.run(
        [exe, "--version"], capture_output=True, text=True, stdin=subprocess.DEVNULL
    ).stdout
    version = parse_ansible_version(out.splitlines()[0] if out else "")
    if version is None:
        return Check("ansible-core", False, f"could not parse version from {out[:60]!r}")
    ok = version >= MIN_ANSIBLE
    return Check("ansible-core", ok, f"{version[0]}.{version[1]} (need >= 2.16)")


def check_host(host: str, timeout: float = 10.0) -> Check:
    """Any HTTP response, even 401 or 404, means the host is reachable."""
    try:
        with urllib.request.urlopen(f"https://{host}/", timeout=timeout) as r:
            return Check(f"https {host}", True, str(r.status))
    except urllib.error.HTTPError as e:
        return Check(f"https {host}", True, str(e.code))
    except (urllib.error.URLError, OSError) as e:
        reason = getattr(e, "reason", e)
        return Check(f"https {host}", False, str(reason))


def run(hosts: bool = True) -> list[Check]:
    checks = [check_python(), check_ansible()]
    if hosts:
        checks += [check_host(h) for h in HOSTS]
    return checks
