"""The package, the Ansible collection and the Claude Code plugin ship under one version."""

import json
from pathlib import Path

import yaml

import expkit

ROOT = Path(__file__).resolve().parent.parent


def test_galaxy_version_matches_package():
    assert yaml.safe_load((ROOT / "galaxy.yml").read_text())["version"] == expkit.__version__


def test_plugin_version_matches_package():
    manifest = json.loads((ROOT / "plugin/.claude-plugin/plugin.json").read_text())
    assert manifest["version"] == expkit.__version__


def test_marketplace_entry_points_at_the_plugin():
    market = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())
    manifest = json.loads((ROOT / "plugin/.claude-plugin/plugin.json").read_text())
    (entry,) = market["plugins"]
    assert entry["name"] == manifest["name"]  # install id and skill prefix must agree
    assert (ROOT / entry["source"] / ".claude-plugin/plugin.json").is_file()


def test_every_skill_has_frontmatter_name_matching_its_dir():
    for skill in (ROOT / "plugin/skills").iterdir():
        text = (skill / "SKILL.md").read_text()
        front = yaml.safe_load(text.split("---")[1])
        assert front["name"] == skill.name
        assert len(front["description"]) > 40
