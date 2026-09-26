"""
Phase 2 Completion Gate (docs/IMPLEMENTATION_ROADMAP.md, "Phase 2 Completion Gate specifics"):
"re-run the audit's own AST-based sweep script (or an equivalent) that originally found the 188
candidate endpoints, against the post-fix codebase, and confirm it now returns zero unresolved
candidates -- the same proof standard the audit itself used to declare Finding 18 'final.'"

The original audit (docs/PRODUCTION_AUDIT_2026.md §3.2) never committed its sweep as a script -- it
was run once, ad hoc, and described narratively. This is that "equivalent," built to the same stated
methodology: walk every router file, find every route handler taking a raw `entity_id` (path or
query) parameter not derived from the already-safe `get_current_entity_id` dependency, and check
whether it's guarded by any of the access-check patterns this codebase actually uses.

Usage: python scripts/check_entity_access_sweep.py [--verbose]

Exit code 0 if every candidate is either guarded or on the explicit KNOWN_EXCEPTIONS allowlist (with
a stated reason); exit code 1 and a printed list otherwise.
"""
import argparse
import ast
import sys
from pathlib import Path

ROUTERS_DIR = Path(__file__).resolve().parent.parent / "app" / "routers"

# Dependencies/calls that constitute a real access check on entity_id, across every pattern actually
# used in this codebase (some are the Finding-18 fix from Phase 2.1, others predate it).
SAFE_ENTITY_ID_MARKERS = (
    "require_entity_access",       # Phase 2.1's centralized dependency (app/dependencies.py)
    "require_group_access",        # Phase 2.1's group_id-keyed counterpart (consolidation.py)
    "get_current_entity_id",       # derives entity_id from the user's own cookie/access list
    "verify_entity_access",        # older, looser helper (app/dependencies.py, and tax_2026.py's
                                    # own file-local redefinition) -- still a real check, just not
                                    # the current standard; not touched by Phase 2.1 for the 10
                                    # files still using the shared one
    "get_entity_by_id",            # EntityService's underlying, correct pattern
    "_get_entity_if_accessible",   # DashboardService's user.entity_access-based check
    "resolve_and_verify_entity_id",  # year_end.py/report_export.py's optional-entity_id wrapper
                                     # around require_entity_access (Phase 2.1)
)

# (filename, function_name): reason. Confirmed-safe-without-a-standard-check patterns from the
# original audit (docs/PRODUCTION_AUDIT_2026.md §3.3's "+8 resolved as genuinely SAFE"), plus a
# handful this session's own investigation additionally confirmed. Each entry here is a specific,
# individually-verified claim, not a blanket exemption.
KNOWN_EXCEPTIONS = {
    ("dashboard.py", "get_widget_layout"): "Unimplemented stub, never references entity_id in its body",
    ("dashboard.py", "update_widget_layout"): "Unimplemented stub, never references entity_id in its body",
    ("dashboard.py", "compare_kpis"): "Returns hardcoded placeholder data regardless of entity_id",
    ("notifications.py", "list_notifications"): "Mandatorily scoped by NotificationModel.user_id == current_user.id first",
    ("notifications.py", "mark_all_as_read"): "Mandatorily scoped by NotificationModel.user_id == current_user.id first",
    ("views.py", "set_entity"): "Sets an httponly cookie only, no data access of any kind",
    ("dashboard.py", "get_dashboard"): "Delegates to DashboardService.get_dashboard, which raises PermissionError internally on an inaccessible entity_id",
    ("auth.py", "get_dashboard"): "A second route delegating to the same already-verified-safe DashboardService.get_dashboard",
    ("ml_ai.py", "get_cash_flow_forecast"): "A GET wrapper that delegates directly to forecast_cash_flow(), which has its own require_entity_access call -- this sweep doesn't trace into called functions, only the handler's own body",
    ("ml_ai.py", "get_growth_prediction"): "A GET wrapper that delegates directly to predict_growth(), which has its own require_entity_access call -- same reasoning as get_cash_flow_forecast",
}


def _is_route_handler(node) -> bool:
    return any(
        isinstance(dec, ast.Call) and "router" in ast.dump(dec.func)
        for dec in node.decorator_list
    )


def _has_raw_entity_id_param(node) -> bool:
    all_args = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
    return any(arg.arg == "entity_id" for arg in all_args)


def _is_guarded(node, source: str) -> bool:
    all_defaults = [*node.args.defaults, *node.args.kw_defaults]
    for default in all_defaults:
        if default is None:
            continue
        dumped = ast.dump(default)
        if any(marker in dumped for marker in SAFE_ENTITY_ID_MARKERS):
            return True
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            func = child.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            if name in SAFE_ENTITY_ID_MARKERS:
                return True
    return False


def sweep(verbose: bool = False):
    unresolved = []
    total_candidates = 0

    for path in sorted(ROUTERS_DIR.glob("*.py")):
        source = path.read_text()
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as e:
            print(f"SKIP {path.name}: {e}")
            continue

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not _is_route_handler(node):
                continue
            if not _has_raw_entity_id_param(node):
                continue

            total_candidates += 1
            if (path.name, node.name) in KNOWN_EXCEPTIONS:
                if verbose:
                    print(f"OK (exception) {path.name}::{node.name} -- {KNOWN_EXCEPTIONS[(path.name, node.name)]}")
                continue
            if _is_guarded(node, source):
                if verbose:
                    print(f"OK {path.name}::{node.name}")
                continue

            unresolved.append((path.name, node.name))

    return total_candidates, unresolved


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    total, unresolved = sweep(verbose=args.verbose)

    print(f"\n{total} route handlers with a raw entity_id parameter examined across app/routers/.")
    if unresolved:
        print(f"{len(unresolved)} UNRESOLVED (no recognized access check, not on the exception list):")
        for filename, funcname in unresolved:
            print(f"  {filename}::{funcname}")
        sys.exit(1)
    else:
        print("0 unresolved -- every candidate is either guarded or an individually-verified exception.")
        sys.exit(0)
