from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


def _load_validate_module() -> ModuleType:
    repo_root = Path(__file__).resolve().parents[2]
    path = repo_root / ".github" / "scripts" / "pr-template" / "validate.py"
    spec = importlib.util.spec_from_file_location("pr_template_validate", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VALID_BODY = """## Summary

- Fix a real issue.

## Type of change

- [x] Bug fix
- [ ] Feature
- [ ] Refactor / chore
- [ ] Docs
- [ ] Test / CI
- [ ] Breaking change

## Test coverage

- [x] Unit tests added / updated
- [ ] Integration tests added / updated
- [ ] E2E tests added / updated
- [ ] Manual verification completed
- [ ] Existing tests cover this change
- [ ] Not applicable

## Coverage rationale

Added focused unit coverage for the validator behavior.
"""


def test_validate_pr_body_accepts_leading_bom() -> None:
    validate = _load_validate_module()

    result = validate.validate_pr_body("\ufeff" + VALID_BODY)

    assert result.ok, result.errors
