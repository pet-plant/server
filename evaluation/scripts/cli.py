"""Unified Command-Line Interface (CLI) for the Pet-Plant Performance Evaluation Suite."""

from __future__ import annotations

import argparse
import io
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path


class _TeeWriter(io.TextIOBase):
    """Write to *real* stdout and an in-memory buffer at the same time.

    Used during ``cmd_run`` so the operator sees live progress while every
    printed line is also captured for ``run.log``.
    """

    def __init__(self, real: io.TextIOBase) -> None:
        self._real = real
        self._buf = io.StringIO()

    def write(self, s: str) -> int:  # type: ignore[override]
        self._real.write(s)
        self._buf.write(s)
        return len(s)

    def flush(self) -> None:
        self._real.flush()
        self._buf.flush()

    def getvalue(self) -> str:
        return self._buf.getvalue()

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
_SRC_DIR = _REPO_ROOT / "src"
if _SRC_DIR.exists() and str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

import evaluation
from evaluation.common.config import EvaluationConfig
from evaluation.common.loaders import (
    ManifestValidationError,
    load_end_to_end_manifest,
)
from evaluation.common.reporting import (
    EvaluationRunSummary,
    ScopeExecutionResult,
    get_git_commit,
    write_run_report,
)
from evaluation.end_to_end.run import run_end_to_end_evaluation
from evaluation.llm.run import run_llm_evaluation
from evaluation.scripts.cleanup import clean_evaluation_reports
from evaluation.vlm.run import run_vlm_evaluation

ALL_SCOPES = [
    "vlm",
    "llm",
    "end_to_end",
]

SCOPE_RUNNERS = {
    "vlm": run_vlm_evaluation,
    "llm": run_llm_evaluation,
    "end_to_end": run_end_to_end_evaluation,
}


def cmd_validate(config: EvaluationConfig) -> int:
    """Validate all manifest schemas without executing model runs."""
    base_datasets = Path(__file__).resolve().parent.parent / "datasets"
    print(f"Validating dataset manifests under {base_datasets}...")

    errors: list[str] = []

    # 1. VLM scenarios
    vlm_manifest = base_datasets / "vlm" / "scenarios.json"
    if vlm_manifest.exists():
        try:
            import json
            with open(vlm_manifest, encoding="utf-8") as f:
                vlm_data = json.load(f)
            case_count = len(vlm_data.get("cases", []))
            print(f"  [PASS] VLM Scenarios: {case_count} valid case(s)")
        except Exception as err:
            errors.append(f"VLM Scenarios: {err}")
    else:
        print("  [WARN] VLM Scenarios: scenarios.json not found")

    # 2. LLM advice cases
    llm_manifest = base_datasets / "llm" / "advice_cases.json"
    if llm_manifest.exists():
        try:
            import json
            with open(llm_manifest, encoding="utf-8") as f:
                llm_data = json.load(f)
            case_count = len(llm_data.get("cases", []))
            print(f"  [PASS] LLM Advice Cases: {case_count} valid case(s)")
        except Exception as err:
            errors.append(f"LLM Advice Cases: {err}")
    else:
        print("  [WARN] LLM Advice Cases: advice_cases.json not found")

    # 3. End-to-end scenarios
    e2e_manifest = base_datasets / "end_to_end" / "scenarios.json"
    if e2e_manifest.exists():
        try:
            scenarios = load_end_to_end_manifest(e2e_manifest)
            print(f"  [PASS] End-to-End Scenarios: {len(scenarios)} valid scenario(s)")
        except ManifestValidationError as err:
            errors.append(f"End-to-End: {err}")
    else:
        print("  [WARN] End-to-End: scenarios.json not found")

    # 4. Sample knowledge
    try:
        from evaluation.common.sample_knowledge import load_all_sample_knowledge
        knowledge = load_all_sample_knowledge()
        if knowledge:
            total_problems = sum(len(k.problems) for k in knowledge)
            print(f"  [PASS] Sample Knowledge: {len(knowledge)} species, {total_problems} problems")
        else:
            print("  [WARN] Sample Knowledge: no knowledge files found in sample/knowldge/")
    except ImportError as e:
        print(f"  [SKIP] Sample Knowledge: dependencies unavailable ({e})")

    # 5. Final condition dataset
    final_dir = base_datasets / "final"
    eval_jsonl = final_dir / "eval.jsonl"
    species_json = final_dir / "species.json"
    if eval_jsonl.exists() and species_json.exists():
        try:
            from evaluation.vlm.final_dataset import load_final_dataset
            ds = load_final_dataset(final_dir, verify_images=False)
            print(f"  [PASS] Final Dataset: {len(ds)} samples across {len(ds.species_meta)} species")
        except Exception as err:
            errors.append(f"Final Dataset: {err}")
    else:
        print("  [WARN] Final Dataset: eval.jsonl or species.json not found")

    if errors:
        print("\nValidation Failed with errors:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 2

    print("\nAll manifests passed schema validation successfully.")
    return 0


def cmd_clean(args: argparse.Namespace) -> int:
    """Safely clean generated evaluation run reports."""
    is_dry_run = not args.yes
    keep_latest = not args.include_latest

    try:
        deleted, bytes_freed = clean_evaluation_reports(
            dry_run=is_dry_run,
            keep_latest=keep_latest,
        )
        mode_str = "[DRY-RUN]" if is_dry_run else "[DELETED]"
        print(f"{mode_str} Identified {len(deleted)} item(s) to remove ({bytes_freed / 1024:.1f} KB).")
        for p in deleted:
            print(f"  - {p.name}")
        if is_dry_run and deleted:
            print("\nRe-run with '--yes' to confirm actual deletion.")
        return 0
    except Exception as e:
        print(f"Cleanup error: {e}", file=sys.stderr)
        return 2


def cmd_run(args: argparse.Namespace, config: EvaluationConfig) -> int:
    """Execute evaluation scopes and produce reports."""
    if args.fast:
        config.fast_mode = True
    if args.enable_judge:
        config.enable_judge = True
    if getattr(args, "mode", None):
        config.execution_mode = args.mode

    scopes_to_run = [args.scope] if args.scope else ALL_SCOPES
    for s in scopes_to_run:
        if s not in ALL_SCOPES:
            print(f"Unknown scope: '{s}'. Available: {ALL_SCOPES}", file=sys.stderr)
            return 2

    run_id = f"run_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    start_time = time.perf_counter()

    try:
        from evaluation.common.config import runtime_models

        from core.config import get_settings

        models = runtime_models(get_settings())
        active_llm = f"{models.llm_model} ({models.llm_provider})"
        embedding_model = (
            f"{models.embedding_model} ({models.embedding_provider})"
            if models.embedding_model
            else "unset"
        )
        vlm_model = f"{models.vlm_model} ({models.vlm_provider})" if models.vlm_model else "unset"
    except Exception:
        active_llm = "unset"
        embedding_model = "unset"
        vlm_model = "unset"

    models_used = {
        "vlm_model": vlm_model,
        "llm_model": active_llm,
        "embedding_model": embedding_model,
        "execution_mode": config.execution_mode,
    }

    # -- Tee stdout so every printed line goes to the terminal AND a buffer
    #    that we'll write as run.log when the report is saved.
    tee = _TeeWriter(sys.stdout)  # type: ignore[arg-type]
    sys.stdout = tee  # type: ignore[assignment]
    try:
        print(f"Starting evaluation run [{run_id}]...")
        print(f"Scopes: {', '.join(scopes_to_run)}")
        print(f"Mode: {config.execution_mode} | Models: VLM={models_used['vlm_model']}, LLM={models_used['llm_model']}")
        print(f"Options: fast_mode={config.fast_mode}, enable_judge={config.enable_judge}\n")

        scope_results: dict[str, ScopeExecutionResult] = {}
        any_failed = False

        for scope_name in scopes_to_run:
            runner_fn = SCOPE_RUNNERS[scope_name]
            print(f"\n--- Running scope: {scope_name} ---")
            try:
                res = runner_fn(config)
                scope_results[scope_name] = res
                print(f"--- Scope {scope_name}: [{res.status}] ({res.passed_cases}/{res.total_cases} cases, {res.duration_seconds:.2f}s) ---")
                if res.status == "FAIL":
                    any_failed = True
            except Exception as e:
                print(f"[ERROR] {e}")
                scope_results[scope_name] = ScopeExecutionResult(
                    scope_name=scope_name,
                    status="FAIL",
                    duration_seconds=0.0,
                    total_cases=0,
                    passed_cases=0,
                    skip_reason=f"Crash during execution: {e}",
                )
                any_failed = True

        total_duration = time.perf_counter() - start_time
        overall_status = "FAIL" if any_failed else "PASS"

        summary = EvaluationRunSummary(
            run_id=run_id,
            timestamp_utc=datetime.now(UTC).isoformat(),
            duration_seconds=total_duration,
            overall_status=overall_status,
            scopes=scope_results,
            git_commit=get_git_commit(),
            models_used=models_used,
        )

        print(f"\n=======================================================")
        print(f"Evaluation Run Completed: {overall_status}")
        print(f"Active Models: {models_used}")
    finally:
        # Always restore stdout before writing the report so any file-write
        # errors print normally and the tee buffer is fully flushed.
        sys.stdout = tee._real

    captured_log = tee.getvalue()
    out_dir = write_run_report(
        summary,
        config.reports_dir,
        keep_latest=config.keep_latest,
        run_log=captured_log,
    )

    print(f"Report Directory: {out_dir}")
    if config.keep_latest:
        print(f"Latest Mirror:    {config.reports_dir / 'latest'}")
    print(f"=======================================================\n")

    return 1 if any_failed else 0


def cmd_evaluate_photos(args: argparse.Namespace, config: EvaluationConfig) -> int:
    """Batch evaluate photos against criteria, tracking pass/fail counts and averages."""
    images_dir = args.images_dir
    manifest_path = args.manifest

    print(f"Executing Batch Photo Criteria Evaluation on: {images_dir}")
    if manifest_path:
        print(f"Using ground-truth manifest: {manifest_path}")

    from evaluation.vlm.run import evaluate_batch_photos

    summary = evaluate_batch_photos(
        photos_dir=images_dir,
        config=config,
        manifest_path=manifest_path,
    )

    total = summary["total_photos"]
    success = summary["successful_photos"]
    failed = summary["failed_photos"]
    rate = summary["success_rate_pct"]

    print("\n" + "=" * 65)
    print("BATCH PHOTO CRITERIA EVALUATION REPORT")
    print("=" * 65)
    print(f"Total Photos Evaluated: {total}")
    print(f"Successful Photos:      {success}  ({rate:.1f}% pass rate)")
    print(f"Failed Photos:          {failed}")
    print("-" * 65)
    print("AVERAGE METRIC RESULTS ACROSS ALL PHOTOS:")
    print(f"  - Average Structured F1 Score:  {summary['avg_f1_score']:.2f}%")
    print(f"  - Average Precision:            {summary['avg_precision']:.2f}%")
    print(f"  - Average Recall:               {summary['avg_recall']:.2f}%")
    print(f"  - Average Accuracy:             {summary['avg_accuracy']:.2f}%")
    print("=" * 65)

    print("\nPER-PHOTO CRITERIA BREAKDOWN:")
    for p in summary.get("photo_details", []):
        status_tag = "[PASS]" if p["passed"] else "[FAIL]"
        acc = p.get("accuracy", 0.0)
        f1 = p.get("f1_score", 0.0)
        prec = p.get("precision", 0.0)
        rec = p.get("recall", 0.0)
        print(f"  {status_tag} {p['filename']:<28} | Acc: {acc:>5.1f}% | F1: {f1:>5.1f}% | Prec: {prec:>5.1f}% | Rec: {rec:>5.1f}%")
        if not p["passed"] and "error" in p:
            print(f"         Reason: {p['error']}")

    print("=" * 65 + "\n")
    return 0 if failed == 0 else 1


def cmd_evaluate_final(args: argparse.Namespace, config: EvaluationConfig) -> int:
    """Run VLM condition evaluation on the 505-sample final houseplant benchmark dataset."""
    from evaluation.vlm.run import run_final_dataset_evaluation

    res = run_final_dataset_evaluation(
        config=config,
        dataset_dir=args.dataset_dir,
        limit=args.limit,
        predictions_file=args.predictions_file,
        use_mock=args.use_mock,
        results_json_path=args.results_json,
    )
    return 0 if res.status == "PASS" else 1



def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="evaluation",
        description="Pet-Plant Performance Evaluation Suite CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # 1. run command
    p_run = subparsers.add_parser("run", help="Run evaluation scopes and generate reports.")
    p_run.add_argument(
        "--scope",
        choices=ALL_SCOPES,
        help="Run only the specified scope.",
    )
    p_run.add_argument(
        "--mode",
        choices=["in_memory", "http"],
        default="in_memory",
        help="Pipeline execution mode: in_memory (fast SQLite) or http (FastAPI endpoints).",
    )
    p_run.add_argument(
        "--fast",
        action="store_true",
        help="Run in fast mode with truncated scenario sets for quick smoke checks.",
    )
    p_run.add_argument(
        "--enable-judge",
        action="store_true",
        help="Enable optional LLM-as-a-judge (requires configured API credentials).",
    )
    p_run.add_argument(
        "--cleanup",
        action="store_true",
        help="Automatically clean up test database fixtures after the evaluation run.",
    )

    # 2. validate command
    subparsers.add_parser("validate", help="Validate evaluation dataset manifests and schemas.")

    # 3. clean command
    p_clean = subparsers.add_parser("clean", help="Safely clean generated evaluation reports.")
    p_clean.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Simulate cleanup without deleting (default).",
    )
    p_clean.add_argument(
        "--yes",
        action="store_true",
        help="Confirm deletion of generated evaluation reports.",
    )
    p_clean.add_argument(
        "--include-latest",
        action="store_true",
        help="Also remove the evaluation/reports/latest/ mirror.",
    )

    # 4. setup-fixtures command
    subparsers.add_parser(
        "setup-fixtures",
        help="Seed baseline database catalog species, test user, and device fixtures.",
    )

    # 5. cleanup-fixtures command
    subparsers.add_parser(
        "cleanup-fixtures",
        help="Safely remove test fixtures, test plants, and run records from the database.",
    )

    # 6. evaluate-photos command
    p_photos = subparsers.add_parser(
        "evaluate-photos",
        help="Batch evaluate photos against botanical criteria, report pass/fail counts and aggregate averages.",
    )
    p_photos.add_argument(
        "--images-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "datasets" / "images",
        help="Directory containing plant photos to evaluate.",
    )
    p_photos.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Optional custom manifest path with ground-truth criteria per photo.",
    )

    # 7. evaluate-final command
    p_final = subparsers.add_parser(
        "evaluate-final",
        help="Run VLM evaluation on final 505-sample houseplant condition dataset (health_status & symptoms).",
    )
    p_final.add_argument(
        "--dataset-dir",
        type=Path,
        default=None,
        help="Path to final dataset directory containing eval.jsonl, species.json, images/.",
    )
    p_final.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional maximum number of samples to evaluate (e.g. 5 or 10).",
    )
    p_final.add_argument(
        "--predictions-file",
        type=Path,
        default=None,
        help="Custom path to cached predictions JSONL.",
    )
    p_final.add_argument(
        "--use-mock",
        action="store_true",
        help="Use simulated mock predictions without calling live VLM backend.",
    )
    p_final.add_argument(
        "--results-json",
        type=Path,
        default=None,
        help="Custom output file for detailed evaluation metrics JSON.",
    )

    args = parser.parse_args(argv)
    config = EvaluationConfig.load()

    if args.command == "run":
        res = cmd_run(args, config)
        if getattr(args, "cleanup", False):
            print("\nRunning post-run fixture cleanup...")
            from scripts.cleanup_evaluation_fixtures import cleanup_fixtures
            cleanup_fixtures()
            print("Post-run database cleanup completed.")
        return res
    elif args.command == "evaluate-photos":
        return cmd_evaluate_photos(args, config)
    elif args.command == "evaluate-final":
        return cmd_evaluate_final(args, config)
    elif args.command == "validate":
        return cmd_validate(config)
    elif args.command == "clean":
        return cmd_clean(args)
    elif args.command == "setup-fixtures":
        from scripts.init_evaluation_fixtures import setup_fixtures
        seeded = setup_fixtures()
        print("Database fixtures successfully initialized:")
        for k, v in seeded.items():
            print(f"  {k}: {v}")
        return 0
    elif args.command == "cleanup-fixtures":
        from scripts.cleanup_evaluation_fixtures import cleanup_fixtures
        deleted = cleanup_fixtures()
        print("Database test fixtures cleaned up successfully:")
        for k, v in deleted.items():
            if v > 0:
                print(f"  {k}: {v} deleted")
        if not any(deleted.values()):
            print("  (Database was already clean, 0 test records found)")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
