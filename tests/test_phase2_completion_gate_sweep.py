"""
Phase 2 Completion Gate (docs/IMPLEMENTATION_ROADMAP.md, "Phase 2 Completion Gate specifics"):
"re-run the audit's own AST-based sweep script (or an equivalent) that originally found the 188
candidate endpoints, against the post-fix codebase, and confirm it now returns zero unresolved
candidates -- the same proof standard the audit itself used to declare Finding 18 'final.'"

scripts/check_entity_access_sweep.py is that equivalent -- see its own docstring for the full
methodology (the original audit never committed its sweep as a reusable script, so this rebuilds it
to the same stated standard: every route handler taking a raw entity_id parameter, guarded or not, by
any of the access-check patterns this codebase actually uses). This test makes that check a permanent
regression, not a one-off script run: if a future change removes an access check from any of the
1058+ routes across app/routers/, or adds a new unguarded entity_id-taking endpoint, this test fails
immediately rather than waiting for the next manual audit.
"""
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from check_entity_access_sweep import sweep  # noqa: E402


def test_zero_unresolved_entity_access_candidates_repo_wide():
    total, unresolved = sweep()
    assert total > 500, (
        f"Expected 500+ route handlers with a raw entity_id parameter across app/routers/, found "
        f"{total} -- the sweep's own discovery may be broken (or router files were removed)."
    )
    assert not unresolved, (
        f"{len(unresolved)} route handler(s) take a raw entity_id parameter with no recognized "
        f"access check and are not on the sweep's KNOWN_EXCEPTIONS allowlist: {unresolved}"
    )
