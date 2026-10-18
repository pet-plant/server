"""Safe cleanup utility for generated evaluation reports and temporary run artifacts."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ALLOWED_REPORTS_DIR = (PROJECT_ROOT / "evaluation" / "reports").resolve()


class CleanupSecurityError(RuntimeError):
    """Raised when a cleanup path target violates allowlist boundaries."""


def verify_safe_path(target_dir: Path) -> Path:
    """
    Ensure the target path resolves strictly to ALLOWED_REPORTS_DIR or a subdirectory within it.
    Rejects any relative parent traversal or external symlinks.
    """
    resolved = target_dir.resolve()
    try:
        # relative_to will raise ValueError if resolved is not within ALLOWED_REPORTS_DIR
        resolved.relative_to(ALLOWED_REPORTS_DIR)
    except ValueError as e:
        raise CleanupSecurityError(
            f"Security violation: path {resolved} is outside allowed directory {ALLOWED_REPORTS_DIR}"
        ) from e

    # Ensure we never delete the root ALLOWED_REPORTS_DIR itself
    if resolved == ALLOWED_REPORTS_DIR:
        return resolved

    return resolved


def clean_evaluation_reports(
    reports_dir: Path | None = None,
    dry_run: bool = True,
    keep_latest: bool = True,
) -> tuple[list[Path], int]:
    """
    Safely delete generated evaluation reports.

    Rules:
    - Never deletes .gitkeep or README files.
    - Preserves reports/latest by default if keep_latest is True.
    - Strictly resolves targets within evaluation/reports/.
    - Returns (list_of_deleted_or_dryrun_paths, total_bytes_freed).
    """
    target_base = (reports_dir or ALLOWED_REPORTS_DIR).resolve()
    verified_root = verify_safe_path(target_base)

    if not verified_root.exists():
        return [], 0

    items_to_delete: list[Path] = []
    total_bytes = 0

    # Scan directories and files inside verified_root
    for child in verified_root.iterdir():
        # Never delete .gitkeep, README.md
        if child.name in (".gitkeep", "README.md", "README"):
            continue

        # Preserve 'latest/' if keep_latest is True
        if keep_latest and child.name == "latest":
            continue

        # Verify child is strictly safe
        verify_safe_path(child)

        items_to_delete.append(child)
        if child.is_dir():
            for root, _, files in os.walk(child):
                for f in files:
                    fp = Path(root) / f
                    total_bytes += fp.stat().st_size
        else:
            total_bytes += child.stat().st_size

    if not dry_run:
        for item in items_to_delete:
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink(missing_ok=True)

    return items_to_delete, total_bytes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Safely clean generated evaluation run reports from evaluation/reports/."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Simulate cleanup without deleting any files (default).",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm deletion of generated evaluation reports.",
    )
    parser.add_argument(
        "--include-latest",
        action="store_true",
        help="Also remove the evaluation/reports/latest/ mirror.",
    )

    args = parser.parse_args(argv)
    is_dry_run = not args.yes

    print(f"Target directory: {ALLOWED_REPORTS_DIR}")
    if is_dry_run:
        print("[DRY-RUN MODE] No files will be deleted. Use '--yes' to confirm deletion.")

    try:
        deleted_items, bytes_freed = clean_evaluation_reports(
            dry_run=is_dry_run,
            keep_latest=not args.include_latest,
        )

        if not deleted_items:
            print("No generated reports found to clean.")
            return 0

        action_label = "Would delete" if is_dry_run else "Deleted"
        print(f"\n{action_label} {len(deleted_items)} item(s) ({bytes_freed / 1024:.1f} KB):")
        for item in deleted_items:
            print(f"  - {item.name}{'/' if item.is_dir() else ''}")

        if is_dry_run:
            print("\nTo actually delete these reports, re-run with: evaluation clean --yes")
        else:
            print("\nCleanup completed successfully.")
        return 0

    except CleanupSecurityError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 2
    except Exception as err:
        print(f"Cleanup failed: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
