# Changelog

All three parts (Python package, Ansible collection, Claude Code plugin) share one version.

## 0.1.0 (unreleased)

Phase 0 of `docs/plans/shared-experiment-toolkit.md`:

- Repository layout: Python package `expkit`, Ansible collection `felipedreis.expkit`, Claude
  Code plugin and marketplace.
- Inventories for local, the Raspberry Pi cluster and CCAD, moved from dl2l (cluster facts only).
- `playbooks/spike.yml` and `expkit spike-report`: check what each environment allows
  (outbound HTTPS from login and compute nodes, detached processes, cron, SLURM afterany).
- `expkit doctor`: check the control machine (Python, ansible-core, outbound HTTPS).
- `spike` skill.
- CI (ruff, pytest, ansible-lint, playbook syntax checks, an end-to-end local spike, plugin
  validation) and a tag-driven release workflow.
