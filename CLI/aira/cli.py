#!/usr/bin/env python3
"""
AIRA CLI — AI-Induced Risk Audit
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from aira import __version__
    from aira.llm import LLMConfig, LLMRoutingError, provider_health_snapshot
    from aira.collector import collect_public_repos
    from aira.research import ResearchSubmissionError, check_research_connection, submit_aggregate_research
    from aira.scanner import (
        AIRAScanner,
        ScanResult,
        ScanTargetError,
        ScannerExecutionError,
        ScannerInputError,
        describe_empty_scan_result,
        result_to_json,
        result_to_yaml,
        validate_scan_target,
    )
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from aira import __version__
    from aira.llm import LLMConfig, LLMRoutingError, provider_health_snapshot
    from aira.collector import collect_public_repos
    from aira.research import ResearchSubmissionError, check_research_connection, submit_aggregate_research
    from aira.scanner import (
        AIRAScanner,
        ScanResult,
        ScanTargetError,
        ScannerExecutionError,
        ScannerInputError,
        describe_empty_scan_result,
        result_to_json,
        result_to_yaml,
        validate_scan_target,
    )


class C:
    RED = "\033[91m"
    YELLOW = "\033[93m"
    GREEN = "\033[92m"
    BLUE = "\033[94m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"
    CYAN = "\033[96m"


SEVERITY_COLOR = {"HIGH": C.RED, "MEDIUM": C.YELLOW, "LOW": C.DIM}
STATUS_COLOR = {"PASS": C.GREEN, "FAIL": C.RED, "UNKNOWN": C.YELLOW}
FAIL_THRESHOLD = {"none": None, "low": {"LOW", "MEDIUM", "HIGH"}, "medium": {"MEDIUM", "HIGH"}, "high": {"HIGH"}}
EXIT_OK = 0

# Exit codes: 1 = scan findings exceeded --fail-on; 2 = invalid input / usage / output path errors;
# 3 = LLM/research/collection operational failure (distinct from findings for automation).
EXIT_FINDINGS_THRESHOLD = 1
EXIT_INPUT_OR_USAGE = 2
EXIT_OPERATIONAL_FAILURE = 3

BANNER = f"""
{C.BOLD}{C.BLUE}  ╔═══════════════════════════════════════╗
  ║   AIRA — AI-Induced Risk Audit v{__version__}   ║
  ║   Bagelle Parris Vargas Consulting    ║
  ╚═══════════════════════════════════════╝{C.RESET}
"""


def print_banner() -> None:
    print(BANNER)


def build_llm_config(args: argparse.Namespace) -> LLMConfig:
    return LLMConfig(
        provider=getattr(args, "provider", "auto"),
        model=getattr(args, "model", None),
        base_url=getattr(args, "base_url", None),
        timeout_seconds=getattr(args, "timeout", 45),
        max_context_chars=getattr(args, "max_context_chars", 120_000),
    )


def print_summary(result: ScanResult) -> None:
    summary = result.summary
    metadata = result.metadata or {}
    print(f"\n{C.BOLD}{'═'*55}{C.RESET}")
    print(f"{C.BOLD}  SCAN SUMMARY{C.RESET}")
    print(f"{'═'*55}")
    print(f"  Target:          {result.target}")
    print(f"  Scanned at:      {result.scanned_at}")
    print(f"  Files scanned:   {summary['files_scanned']}")
    print(f"  Total findings:  {C.BOLD}{summary['findings_total']}{C.RESET}")
    if metadata.get("mode"):
        provider = metadata.get("provider") or metadata.get("engine")
        model = metadata.get("model") or "n/a"
        print(f"  Scan mode:       {metadata['mode']}")
        if provider:
            print(f"  Provider:        {provider}")
            print(f"  Model:           {model}")
        if metadata.get("truncated"):
            print(f"  Context:         {C.YELLOW}truncated for size{C.RESET}")
    print()
    print("  Severity breakdown:")
    print(f"    {C.RED}HIGH  : {summary['by_severity']['HIGH']}{C.RESET}")
    print(f"    {C.YELLOW}MEDIUM: {summary['by_severity']['MEDIUM']}{C.RESET}")
    print(f"    {C.DIM}LOW   : {summary['by_severity']['LOW']}{C.RESET}")
    print()
    print("  Check results:")
    print(f"    {C.GREEN}PASS   : {summary['checks_passed']}{C.RESET}")
    print(f"    {C.RED}FAIL   : {summary['checks_failed']}{C.RESET}")
    print(f"    {C.YELLOW}UNKNOWN: {summary['checks_unknown']}{C.RESET}")
    if metadata.get("notes"):
        print()
        print("  Notes:")
        for note in metadata["notes"]:
            print(f"    {C.YELLOW}- {note}{C.RESET}")
    print(f"{'═'*55}\n")


def print_check_results(result: ScanResult) -> None:
    print(f"{C.BOLD}  CHECK RESULTS{C.RESET}")
    print(f"{'─'*55}")
    for key, status in result.check_results.items():
        color = STATUS_COLOR.get(status, C.RESET)
        label = key.replace("_", " ").upper()
        print(f"  {color}{status:8}{C.RESET}  {label}")
    print()


def print_findings(result: ScanResult) -> None:
    findings = result.findings
    if not findings:
        print(f"  {C.GREEN}✓ No findings. All automated checks passed.{C.RESET}\n")
        print(f"  {C.YELLOW}Note: C07 (Parallel Logic Drift) and C12 (Source-to-Output Lineage)")
        print(f"  require human review and remain UNKNOWN.{C.RESET}\n")
        return

    print(f"{C.BOLD}  FINDINGS ({len(findings)} total){C.RESET}")
    print(f"{'─'*55}")
    current_check = None
    for finding in findings:
        if finding["check_id"] != current_check:
            current_check = finding["check_id"]
            print(f"\n  {C.BOLD}{C.CYAN}[{finding['check_id']}] {finding['check_name']}{C.RESET}")

        sev_color = SEVERITY_COLOR.get(finding["severity"], C.RESET)
        location = f"{finding.get('file') or '<unattributed>'}:{finding.get('line', 0)}"
        print(f"    {sev_color}[{finding['severity']:6}]{C.RESET}  {location}")
        print(f"             {finding['description']}")
        if finding.get("snippet"):
            print(f"             {C.DIM}→ {finding['snippet']}{C.RESET}")
    print()


def print_human_review_notice() -> None:
    print(f"{C.YELLOW}{'─'*55}")
    print("  REQUIRES HUMAN REVIEW (cannot be automated):")
    print("    C07 — Parallel Logic Drift")
    print("         Check: Does batch/streaming/sync/async share identical governance?")
    print("    C12 — Source-to-Output Lineage")
    print("         Check: Do all derived objects carry source + location metadata?")
    print(f"{'─'*55}{C.RESET}\n")


def print_health(snapshot: dict) -> None:
    print_banner()
    print(f"{C.BOLD}  PROVIDER HEALTH{C.RESET}")
    print(f"{'─'*55}")
    print(f"  Auto order:      {', '.join(snapshot['auto_provider_order'])}")
    print(f"  Configured:      {', '.join(snapshot['configured_providers']) or 'none'}")
    print(f"  Static fallback: {'yes' if snapshot['static_fallback'] else 'no'}")
    print()
    for name, info in snapshot["providers"].items():
        status = f"{C.GREEN}configured{C.RESET}" if info["configured"] else f"{C.DIM}not configured{C.RESET}"
        model = info.get("model") or "n/a"
        base = info.get("base_url") or "n/a"
        print(f"  {name:18} {status}")
        print(f"    model:        {model}")
        if base != "n/a":
            print(f"    base_url:     {base}")
        available_models = info.get("available_models") or []
        if available_models:
            preview = ", ".join(available_models[:8])
            more = " ..." if len(available_models) > 8 else ""
            print(f"    available:    {preview}{more}")
        if info.get("selected_model_available") is False:
            print(f"    selected:     {C.RED}not installed in Ollama{C.RESET}")
        elif info.get("selected_model_available") is True:
            print(f"    selected:     {C.GREEN}present in Ollama{C.RESET}")
        if info.get("message"):
            print(f"    note:         {info['message']}")
    print()


def print_research_health(snapshot: dict) -> None:
    print(f"{C.BOLD}  RESEARCH STORE HEALTH{C.RESET}")
    print(f"{'─'*55}")
    configured = f"{C.GREEN}yes{C.RESET}" if snapshot["configured"] else f"{C.RED}no{C.RESET}"
    reachable = f"{C.GREEN}yes{C.RESET}" if snapshot.get("reachable") else f"{C.RED}no{C.RESET}"
    print(f"  Backend:        {snapshot.get('backend', 'unknown')}")
    if snapshot.get("preferred_backend"):
        print(f"  Preferred:      {snapshot['preferred_backend']}")
    print(f"  Configured:     {configured}")
    if snapshot.get("table"):
        print(f"  Table:          {snapshot['table']}")
    if snapshot.get("path"):
        print(f"  Path:           {snapshot['path']}")
    print(f"  Reachable:      {reachable}")
    if snapshot.get("legacy_fallback"):
        print(f"  Mode:           {C.YELLOW}legacy compatibility fallback{C.RESET}")
    print(f"  Message:        {snapshot.get('message', 'n/a')}")
    print()


def print_providers() -> None:
    print_banner()
    print(f"{C.BOLD}  SUPPORTED PROVIDERS{C.RESET}")
    print(f"{'─'*55}")
    print("  openai-compatible")
    print("    Plug into any OpenAI-compatible local or hosted endpoint.")
    print("    Env: AIRA_OPENAI_BASE_URL / OPENAI_BASE_URL, AIRA_OPENAI_MODEL / OPENAI_MODEL")
    print()
    print("  ollama")
    print("    Local-first path for users already running Ollama.")
    print("    Env: AIRA_OLLAMA_MODEL / OLLAMA_MODEL, optional AIRA_OLLAMA_HOST / OLLAMA_HOST")
    print("    Use 'aira health --json' to see available models exposed by the running Ollama service.")
    print()
    print("  nvidia")
    print("    Fast cloud structured-output path via NVIDIA NIM.")
    print("    Default model: stepfun-ai/step-3.7-flash")
    print("    Env: AIRA_NVIDIA_API_KEY / NVIDIA_API_KEY, optional AIRA_NVIDIA_MODEL / NVIDIA_MODEL")
    print()
    print("  groq")
    print("    Fast cloud structured-output path.")
    print("    Env: AIRA_GROQ_API_KEY / GROQ_API_KEY, AIRA_GROQ_MODEL / GROQ_MODEL")
    print()
    print("  openrouter")
    print("    Optional rotating cloud fallback.")
    print("    Env: AIRA_OPENROUTER_API_KEY / OPENROUTER_API_KEY, AIRA_OPENROUTER_MODEL / OPENROUTER_MODEL")
    print()
    print("  Recommended CLI flow:")
    print("    1. local OpenAI-compatible endpoint, if you already have one")
    print("    2. Ollama")
    print("    3. NVIDIA NIM")
    print("    4. Groq")
    print("    5. OpenRouter")
    print()


def print_collection_summary(summary: dict) -> None:
    print(f"{C.BOLD}  PUBLIC DATA COLLECTION{C.RESET}")
    print(f"{'─'*55}")
    print(f"  Sampling method: {summary.get('sampling_method', 'n/a')}")
    print(f"  Sampling frame:  {summary.get('sampling_frame', 'n/a')}")
    print(f"  Submitted:       {'yes' if summary.get('submitted') else 'no'}")
    print()
    for sample in summary.get("samples", []):
        status = f"{C.GREEN}ok{C.RESET}" if not sample.get("error") else f"{C.RED}error{C.RESET}"
        duplicate = " duplicate" if sample.get("duplicate") else ""
        print(f"  {status}  {sample.get('sample_name')} @ {sample.get('sample_version')}{duplicate}")
        print(f"    repo:          {sample.get('repo')}")
        if sample.get("commit_sha"):
            print(f"    commit:        {sample.get('commit_sha')}")
        print(f"    findings:      {sample.get('findings_total', 0)}")
        print(f"    checks_failed: {sample.get('checks_failed', 0)}")
        if sample.get("research_submission_id"):
            print(f"    submission_id: {sample.get('research_submission_id')}")
        if sample.get("manifest_written"):
            print("    manifest:      written")
        if sample.get("error"):
            print(f"    error:         {sample.get('error')}")
    print()


def print_research_submission_status(response: dict) -> None:
    print(f"{C.BOLD}  RESEARCH SUBMISSION{C.RESET}")
    print(f"{'─'*55}")
    print(f"  Backend:         {response.get('backend', 'unknown')}")
    print(f"  Submission id:   {response.get('id') or 'created'}")
    if response.get("path"):
        print(f"  Output path:     {response['path']}")
    if response.get("legacy_fallback"):
        print(f"  Mode:            {C.YELLOW}legacy compatibility fallback{C.RESET}")
    dropped = response.get("dropped_optional_fields") or []
    if dropped:
        print(f"  Optional fields dropped: {', '.join(dropped)}")
    else:
        print("  Optional fields dropped: none")
    print()


def print_research_submission_error(message: str) -> None:
    print(f"{C.RED}Research submission failed: {message}{C.RESET}", file=sys.stderr)


def positive_int(flag_label: str):
    """Argparse type factory: require a positive base-10 integer."""

    def converter(value: str) -> int:
        try:
            parsed = int(value, 10)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(f"{flag_label} must be an integer") from exc
        if parsed <= 0:
            raise argparse.ArgumentTypeError(f"{flag_label} must be greater than 0")
        return parsed

    return converter


def has_scanner_errors(result: ScanResult) -> bool:
    return any(finding.get("check_id") == "SCANNER" for finding in result.findings)


def exit_code_for_llm_error(exc: LLMRoutingError) -> int:
    message = str(exc)
    if "No LLM providers are configured" in message or " is not configured" in message:
        return EXIT_INPUT_OR_USAGE
    return EXIT_OPERATIONAL_FAILURE


def write_text_output(out_file: str, content: str) -> None:
    """Write CLI output; raises ScanTargetError on missing parent dir or OS-level write failures."""
    path = Path(out_file).expanduser()
    parent = path.parent
    if not parent.exists():
        raise ScanTargetError(
            f"Output directory does not exist: {parent}. Create it first or choose another --out-file path."
        )
    try:
        path.write_text(content, encoding="utf-8")
    except OSError as exc:
        raise ScanTargetError(f"Could not write output file {path}: {exc}") from exc


def exit_code_for_result(result: ScanResult, fail_on: str) -> int:
    if has_scanner_errors(result):
        return EXIT_INPUT_OR_USAGE
    threshold = FAIL_THRESHOLD[fail_on]
    if threshold is None:
        return EXIT_OK
    if any(finding["severity"] in threshold for finding in result.findings):
        return EXIT_FINDINGS_THRESHOLD
    return EXIT_OK


def add_llm_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--engine", choices=["static", "llm", "hybrid"], default="static", help="Scan engine mode")
    parser.add_argument(
        "--provider",
        choices=["auto", "openai-compatible", "ollama", "nvidia", "groq", "openrouter"],
        default="auto",
        help="LLM provider to use when engine is llm or hybrid",
    )
    parser.add_argument("--model", help="Override provider model name")
    parser.add_argument("--base-url", help="Base URL for openai-compatible endpoints")
    parser.add_argument(
        "--timeout",
        type=positive_int("--timeout"),
        default=45,
        help="HTTP timeout for provider-assisted scans",
    )
    parser.add_argument(
        "--max-context-chars",
        type=positive_int("--max-context-chars"),
        default=120_000,
        help="Maximum source characters sent to LLM scans",
    )


def add_research_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--submit-research-aggregate",
        action="store_true",
        help="Submit aggregate-only scan metrics to the configured research backend",
    )
    parser.add_argument("--research-source", help="Override the source label used for research submission")
    parser.add_argument(
        "--research-timeout",
        type=positive_int("--research-timeout"),
        default=15,
        help="HTTP timeout for research backend submission",
    )
    parser.add_argument("--sample-name", help="Stable sample stream name for research schema v2 submissions")
    parser.add_argument("--sample-version", default=None, help="Sample version label for research schema v2 submissions")
    parser.add_argument(
        "--attribution-class",
        choices=["explicit_ai", "suspected_ai", "human_baseline", "unknown"],
        default=None,
        help="Attribution class for research schema v2 submissions",
    )
    parser.add_argument("--source-id", help="Stable source identifier for research schema v2 submissions")
    parser.add_argument(
        "--source-kind",
        choices=["repo", "directory", "dataset_file", "dataset_repo", "ci_run", "manual"],
        default=None,
        help="Source kind for research schema v2 submissions",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aira", description="AIRA — AI-Induced Risk Audit scanner")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser("scan", help="Scan a file or directory")
    scan_parser.add_argument("target", help="File or directory to scan")
    scan_parser.add_argument("--output", "-o", choices=["terminal", "yaml", "json"], default="terminal", help="Output format")
    scan_parser.add_argument("--exclude", "-e", help="Comma-separated list of directories, files, or glob patterns to exclude", default="")
    scan_parser.add_argument("--out-file", "-f", help="Write output to file instead of stdout", default=None)
    scan_parser.add_argument(
        "--fail-on",
        choices=["none", "low", "medium", "high"],
        default="high",
        help="Exit with code 1 when findings at or above this severity exist",
    )
    add_llm_arguments(scan_parser)
    add_research_arguments(scan_parser)

    health_parser = subparsers.add_parser("health", help="Show provider health/configuration")
    health_parser.add_argument("--json", action="store_true", help="Emit health snapshot as JSON")
    health_parser.add_argument(
        "--check-research",
        "--check-supabase",
        "--check-airtable",
        dest="check_research",
        action="store_true",
        help="Verify research backend connectivity (Supabase preferred; --check-airtable kept as legacy alias)",
    )
    health_parser.add_argument(
        "--research-timeout",
        type=positive_int("--research-timeout"),
        default=10,
        help="HTTP timeout for research connectivity checks",
    )
    add_llm_arguments(health_parser)

    providers_parser = subparsers.add_parser("providers", help="List supported providers and env vars")
    providers_parser.add_argument("--json", action="store_true", help="Emit provider health snapshot as JSON")
    add_llm_arguments(providers_parser)

    collect_parser = subparsers.add_parser("collect", help="Collect curated public repository samples")
    collect_parser.add_argument("manifest", help="Path to YAML/JSON collection manifest")
    collect_parser.add_argument("--output", "-o", choices=["terminal", "json"], default="terminal", help="Output format")
    collect_parser.add_argument("--out-file", "-f", help="Write collection summary to file instead of stdout", default=None)
    collect_parser.add_argument("--exclude", "-e", help="Comma-separated list of directories, files, or glob patterns to exclude", default="")
    collect_parser.add_argument("--submit-research-aggregate", action="store_true", help="Submit collected aggregate results to the configured research backend")
    collect_parser.add_argument(
        "--research-timeout",
        type=positive_int("--research-timeout"),
        default=15,
        help="HTTP timeout for research backend submission",
    )
    collect_parser.add_argument("--keep-repos", action="store_true", help="Keep cloned repos on disk after collection")
    collect_parser.add_argument("--checkout-root", help="Directory where repos should be cloned")
    add_llm_arguments(collect_parser)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "scan":
        target_arg = Path(args.target).expanduser()
        try:
            validate_scan_target(target_arg)
        except ScanTargetError as exc:
            prefix = "Path not found: " if "does not exist" in str(exc) else ""
            print(f"{C.RED}Input error: Invalid scan target: {prefix}{exc}{C.RESET}", file=sys.stderr)
            sys.exit(EXIT_INPUT_OR_USAGE)

        resolved_target = target_arg.resolve(strict=False)
        exclude = [item.strip() for item in args.exclude.split(",") if item.strip()]
        llm_config = build_llm_config(args)

        try:
            scanner = AIRAScanner(str(resolved_target), exclude_dirs=exclude)
            result = scanner.scan(mode=args.engine, llm_config=llm_config)
        except ScannerInputError as exc:
            label = "Cannot complete scan" if "No supported source files found" in str(exc) else "Input error"
            print(f"{C.RED}{label}: {exc}{C.RESET}", file=sys.stderr)
            sys.exit(EXIT_INPUT_OR_USAGE)
        except ScannerExecutionError as exc:
            print(f"{C.RED}Scan failed: {exc}{C.RESET}", file=sys.stderr)
            sys.exit(EXIT_OPERATIONAL_FAILURE)
        except LLMRoutingError as exc:
            print(f"{C.RED}LLM scan failed: {exc}{C.RESET}", file=sys.stderr)
            sys.exit(exit_code_for_llm_error(exc))
        except ScanTargetError as exc:
            print(f"{C.RED}Scan aborted: {exc}{C.RESET}", file=sys.stderr)
            sys.exit(EXIT_INPUT_OR_USAGE)
        except Exception as exc:
            print(f"{C.RED}Unexpected scan failure: {exc}{C.RESET}", file=sys.stderr)
            sys.exit(EXIT_OPERATIONAL_FAILURE)

        empty_reason = describe_empty_scan_result(scanner, result.files_scanned)
        if empty_reason:
            print(f"{C.RED}Cannot complete scan: {empty_reason}{C.RESET}", file=sys.stderr)
            sys.exit(EXIT_INPUT_OR_USAGE)

        research_response = None
        if args.submit_research_aggregate:
            try:
                research_response = submit_aggregate_research(
                    result,
                    source=args.research_source,
                    timeout_seconds=args.research_timeout,
                    submission_options={
                        "sample_name": args.sample_name,
                        "sample_version": args.sample_version,
                        "attribution_class": args.attribution_class,
                        "source_id": args.source_id,
                        "source_kind": args.source_kind,
                    },
                )
            except ResearchSubmissionError as exc:
                print_research_submission_error(str(exc))
                sys.exit(EXIT_OPERATIONAL_FAILURE)

        if args.output == "terminal":
            print_banner()
            print(f"  Scanning: {C.BOLD}{resolved_target}{C.RESET}")
            print(f"  {'─'*50}")
            print_summary(result)
            print_check_results(result)
            print_findings(result)
            print_human_review_notice()
            if research_response is not None:
                print_research_submission_status(research_response)
        else:
            output = result_to_yaml(result) if args.output == "yaml" else result_to_json(result)
            if args.out_file:
                try:
                    write_text_output(args.out_file, output)
                except ScanTargetError as exc:
                    print(f"{C.RED}Output error: {exc}{C.RESET}", file=sys.stderr)
                    sys.exit(EXIT_INPUT_OR_USAGE)
            else:
                print(output)
            if research_response is not None:
                dropped = research_response.get("dropped_optional_fields") or []
                dropped_msg = f" (dropped optional fields: {', '.join(dropped)})" if dropped else ""
                print(
                    f"Research submission succeeded: {research_response.get('backend', 'research')} record {research_response.get('id') or 'created'}{dropped_msg}",
                    file=sys.stderr,
                )

        exit_code = exit_code_for_result(result, args.fail_on)
        if args.output == "terminal":
            if has_scanner_errors(result):
                print(f"{C.RED}  ✗ Scan incomplete — scanner errors require attention before results are reliable.{C.RESET}\n")
            elif exit_code:
                print(f"{C.RED}  ✗ Scan complete — findings at or above '{args.fail_on}' require attention.{C.RESET}\n")
            else:
                print(f"{C.GREEN}  ✓ Scan complete — no findings at or above '{args.fail_on}'.{C.RESET}\n")
        sys.exit(exit_code)

    if args.command == "health":
        snapshot = provider_health_snapshot(build_llm_config(args))
        research_snapshot = check_research_connection(timeout_seconds=args.research_timeout) if args.check_research else None
        if args.json:
            payload = {"providers": snapshot}
            if research_snapshot is not None:
                payload["research"] = research_snapshot
            print(json.dumps(payload, indent=2))
        else:
            print_health(snapshot)
            if research_snapshot is not None:
                print_research_health(research_snapshot)

        exit_ok = research_snapshot["ok"] if research_snapshot is not None else snapshot["ok"]
        sys.exit(0 if exit_ok else 1)

    if args.command == "providers":
        if args.json:
            print(json.dumps(provider_health_snapshot(build_llm_config(args)), indent=2))
        else:
            print_providers()
        sys.exit(0)

    if args.command == "collect":
        llm_config = build_llm_config(args)
        exclude = [item.strip() for item in args.exclude.split(",") if item.strip()]
        try:
            summary = collect_public_repos(
                args.manifest,
                engine=args.engine,
                llm_config=llm_config,
                exclude_dirs=exclude,
                submit_research_aggregate_flag=args.submit_research_aggregate,
                timeout_seconds=args.research_timeout,
                keep_repos=args.keep_repos,
                checkout_root=args.checkout_root,
            )
        except (ValueError, ResearchSubmissionError, LLMRoutingError) as exc:
            print(f"{C.RED}Collection failed: {exc}{C.RESET}", file=sys.stderr)
            sys.exit(EXIT_OPERATIONAL_FAILURE)

        output = json.dumps(summary, indent=2) if args.output == "json" else None
        if args.output == "json":
            if args.out_file:
                try:
                    write_text_output(args.out_file, output)
                except ScanTargetError as exc:
                    print(f"{C.RED}Output error: {exc}{C.RESET}", file=sys.stderr)
                    sys.exit(EXIT_INPUT_OR_USAGE)
            else:
                print(output)
        else:
            print_banner()
            print_collection_summary(summary)
            if args.out_file:
                try:
                    write_text_output(args.out_file, json.dumps(summary, indent=2))
                except ScanTargetError as exc:
                    print(f"{C.RED}Output error: {exc}{C.RESET}", file=sys.stderr)
                    sys.exit(EXIT_INPUT_OR_USAGE)
        sys.exit(EXIT_OK if summary.get("ok") else EXIT_OPERATIONAL_FAILURE)

    raise AssertionError(f"unhandled command {args.command!r}")


if __name__ == "__main__":
    main()
