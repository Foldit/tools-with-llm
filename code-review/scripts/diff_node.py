import re
import subprocess
import time
from common import truncate_text


HUNK_HEADER_RE = re.compile(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def classify_git_error(exc: Exception) -> str:
    if isinstance(exc, subprocess.TimeoutExpired):
        return "git_timeout"
    if isinstance(exc, subprocess.CalledProcessError):
        stderr = (exc.stderr or "").lower()
        if "not a git repository" in stderr:
            return "git_not_repo"
        if "unknown revision" in stderr or "bad revision" in stderr:
            return "git_bad_revision"
        if "could not read" in stderr or "permission denied" in stderr:
            return "git_io_error"
        return "git_command_failed"
    return "git_unknown_error"


def run_cmd(cmd: list[str], timeout_seconds: int = 30, max_retries: int = 1,
            retry_backoff_seconds: float = 1.0) -> str:
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
                timeout=timeout_seconds
            )
            return result.stdout
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as exc:
            last_error = exc
            classification = classify_git_error(exc)
            can_retry = classification in {"git_timeout", "git_io_error"}
            if attempt >= max_retries or not can_retry:
                raise RuntimeError(f"[{classification}] git command failed: {' '.join(cmd)}") from exc
            time.sleep(retry_backoff_seconds * (attempt + 1))

    raise RuntimeError("[git_unknown_error] unexpected command failure") from last_error


def allowed_file(path: str, allowed_roots: list[str], excluded_exts: list[str]) -> bool:
    if any(path.endswith(ext) for ext in excluded_exts):
        return False
    if not allowed_roots:
        return True
    return any(path.startswith(root) for root in allowed_roots)


def parse_name_status(output: str, allowed_roots: list[str], excluded_exts: list[str]):
    files = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status = parts[0]
        path = parts[-1]
        if allowed_file(path, allowed_roots, excluded_exts):
            item = {
                "path": path,
                "status": status
            }
            if len(parts) > 2:
                item["old_path"] = parts[1]
            files.append(item)
    return files


def build_diff_text(repo_path: str, target_branch: str, source_branch: str, changed_files: list[dict]) -> str:
    if not changed_files:
        return ""

    cmd = [
        "git", "-C", repo_path, "diff", "--unified=3",
        f"{target_branch}...{source_branch}", "--"
    ]
    cmd.extend(item["path"] for item in changed_files)
    return run_cmd(cmd)


def build_file_diff(repo_path: str, target_branch: str, source_branch: str, path: str,
                    timeout_seconds: int, max_retries: int, retry_backoff_seconds: float) -> str:
    cmd = [
        "git", "-C", repo_path, "diff", "--unified=3",
        f"{target_branch}...{source_branch}", "--", path
    ]
    return run_cmd(
        cmd,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        retry_backoff_seconds=retry_backoff_seconds
    )


def parse_hunks_with_stats(diff_text: str, strict_validation: bool = False) -> tuple[list[dict], list[str]]:
    hunks = []
    anomalies = []
    lines = diff_text.splitlines()
    index = 0

    while index < len(lines):
        line = lines[index]
        match = HUNK_HEADER_RE.match(line)
        if not match:
            index += 1
            continue

        old_start = int(match.group(1))
        old_count = int(match.group(2) or "1")
        new_start = int(match.group(3))
        new_count = int(match.group(4) or "1")
        hunk = {
            "header": line,
            "old_start": old_start,
            "old_count": old_count,
            "new_start": new_start,
            "new_count": new_count
        }

        index += 1
        old_seen = 0
        new_seen = 0
        while index < len(lines) and not HUNK_HEADER_RE.match(lines[index]):
            body_line = lines[index]
            if body_line.startswith("-") and not body_line.startswith("---"):
                old_seen += 1
            elif body_line.startswith("+") and not body_line.startswith("+++"):
                new_seen += 1
            elif body_line.startswith(" ") or body_line == "":
                old_seen += 1
                new_seen += 1
            index += 1

        if strict_validation:
            old_valid = old_seen == old_count
            new_valid = new_seen == new_count
            if not old_valid or not new_valid:
                anomalies.append(
                    f"invalid_hunk_counts:{line}:seen(old={old_seen},new={new_seen})"
                )

        hunks.append(hunk)

    return hunks, anomalies


def parse_hunks(diff_text: str) -> list[dict]:
    hunks, _ = parse_hunks_with_stats(diff_text, strict_validation=False)
    return hunks


def determine_file_strategy(item: dict, file_diff: str, max_hunks_per_file: int) -> tuple[str, bool, int]:
    status = item.get("status", "")
    hunks, _ = parse_hunks_with_stats(file_diff, strict_validation=False)
    total_hunks = len(hunks)
    hunks_truncated = total_hunks > max_hunks_per_file > 0
    omitted_hunks = max(0, total_hunks - max_hunks_per_file) if max_hunks_per_file > 0 else 0

    if status.startswith("R"):
        return "rename-local-first", hunks_truncated, omitted_hunks
    if len(file_diff) > 20000:
        return "large-file-local-first", hunks_truncated, omitted_hunks
    if total_hunks > 8:
        return "multi-hunk-local-first", hunks_truncated, omitted_hunks
    return "standard", hunks_truncated, omitted_hunks


def enrich_changed_files(repo_path: str, target_branch: str, source_branch: str, changed_files: list[dict],
                         strict_hunk_validation: bool, max_hunks_per_file: int,
                         diff_timeout_seconds: int, diff_max_retries: int,
                         diff_retry_backoff_seconds: float) -> tuple[list[dict], str, list[str]]:
    enriched_files = []
    file_diffs = []
    anomalies = []

    for item in changed_files:
        file_diff = build_file_diff(
            repo_path,
            target_branch,
            source_branch,
            item["path"],
            timeout_seconds=diff_timeout_seconds,
            max_retries=diff_max_retries,
            retry_backoff_seconds=diff_retry_backoff_seconds
        )
        hunks, hunk_anomalies = parse_hunks_with_stats(file_diff, strict_validation=strict_hunk_validation)

        strategy, hunks_truncated, omitted_hunks = determine_file_strategy(item, file_diff, max_hunks_per_file)
        if max_hunks_per_file > 0:
            hunks = hunks[:max_hunks_per_file]

        enriched_item = {
            **item,
            "hunks": hunks,
            "diff_scope_strategy": strategy,
            "hunks_truncated": hunks_truncated,
            "omitted_hunks": omitted_hunks
        }
        enriched_files.append(enriched_item)

        for anomaly in hunk_anomalies:
            anomalies.append(f"{item['path']}:{anomaly}")

        if file_diff:
            file_diffs.append(file_diff.strip())

    return enriched_files, "\n\n".join(file_diffs), anomalies


def main(inputs: dict) -> dict:
    task = inputs["task"]
    repo_path = task["repo_path"]
    target_branch = task["target_branch"]
    source_branch = task["source_branch"]

    max_files = inputs.get("max_files", 20)
    max_diff_chars = inputs.get("max_diff_chars", 120000)
    warning_max_files = inputs.get("warning_max_files")
    warning_max_diff_chars = inputs.get("warning_max_diff_chars")
    allowed_roots = inputs.get("allowed_source_roots", ["src/", "packages/"])
    excluded_exts = inputs.get("excluded_extensions", [])
    diff_timeout_seconds = inputs.get("diff_timeout_seconds", 30)
    diff_max_retries = inputs.get("diff_max_retries", 1)
    diff_retry_backoff_seconds = inputs.get("diff_retry_backoff_seconds", 1.0)
    strict_hunk_validation = inputs.get("strict_hunk_validation", True)
    max_hunks_per_file = inputs.get("max_hunks_per_file", 12)
    warning_max_hunks_per_file = inputs.get("warning_max_hunks_per_file")

    name_status_output = run_cmd([
        "git", "-C", repo_path, "diff", "--name-status",
        f"{target_branch}...{source_branch}"
    ], timeout_seconds=diff_timeout_seconds, max_retries=diff_max_retries,
        retry_backoff_seconds=diff_retry_backoff_seconds)
    all_changed_files = parse_name_status(name_status_output, allowed_roots, excluded_exts)
    changed_files = all_changed_files[:max_files]

    commit_output = run_cmd([
        "git", "-C", repo_path, "log", "--oneline",
        f"{target_branch}..{source_branch}"
    ], timeout_seconds=diff_timeout_seconds, max_retries=diff_max_retries,
        retry_backoff_seconds=diff_retry_backoff_seconds)
    commit_list = [line.strip() for line in commit_output.splitlines() if line.strip()]

    changed_files, raw_diff_text, hunk_anomalies = enrich_changed_files(
        repo_path,
        target_branch,
        source_branch,
        changed_files,
        strict_hunk_validation=strict_hunk_validation,
        max_hunks_per_file=max_hunks_per_file,
        diff_timeout_seconds=diff_timeout_seconds,
        diff_max_retries=diff_max_retries,
        diff_retry_backoff_seconds=diff_retry_backoff_seconds
    )
    diff_text = truncate_text(raw_diff_text, max_diff_chars)
    skipped_file_count = max(0, len(all_changed_files) - len(changed_files))
    diff_truncated = len(raw_diff_text) > len(diff_text)
    skipped_files = [item["path"] for item in all_changed_files[max_files:]]
    warnings = []

    if warning_max_files is not None and len(all_changed_files) > warning_max_files:
        warnings.append(
            f"changed file count {len(all_changed_files)} exceeds warning_max_files={warning_max_files}"
        )
    if warning_max_diff_chars is not None and len(raw_diff_text) > warning_max_diff_chars:
        warnings.append(
            f"diff size {len(raw_diff_text)} exceeds warning_max_diff_chars={warning_max_diff_chars}"
        )
    if warning_max_hunks_per_file is not None:
        over_hunk_limit = [
            item["path"] for item in changed_files
            if len(item.get("hunks", [])) > warning_max_hunks_per_file
        ]
        if over_hunk_limit:
            warnings.append(
                f"hunk count warning for files={','.join(over_hunk_limit)} > "
                f"warning_max_hunks_per_file={warning_max_hunks_per_file}"
            )
    if hunk_anomalies:
        warnings.append(f"hunk anomalies detected={len(hunk_anomalies)}")

    return {
        "diff_result": {
            "changed_files": changed_files,
            "commit_list": commit_list,
            "diff_text": diff_text,
            "skipped_files": skipped_files,
            "warnings": warnings,
            "hunk_anomalies": hunk_anomalies,
            "diff_truncated": diff_truncated,
            "change_summary": [
                f"changed_files_count={len(changed_files)}",
                f"filtered_changed_files_total={len(all_changed_files)}",
                f"skipped_files_due_to_limit={skipped_file_count}",
                f"commit_count={len(commit_list)}",
                f"files_with_hunks={sum(1 for item in changed_files if item.get('hunks'))}",
                f"hunk_anomalies={len(hunk_anomalies)}",
                f"diff_truncated={str(diff_truncated).lower()}"
            ]
        }
    }