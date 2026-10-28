---
name: API artifact working directory
description: Development service commands for API artifacts run from the artifact directory.
---

For an API artifact's development workflow, resolve script paths from that artifact's directory (for example, invoke its local `main.py`). Production commands may instead be rooted at the workspace and use the artifact-relative path.

**Why:** A workspace-relative script path was prefixed with the artifact directory a second time and prevented startup.

**How to apply:** When configuring an API artifact workflow, distinguish development and production working directories; check startup logs after changing command paths.
