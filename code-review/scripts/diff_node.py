import re
import subprocess
from common import truncate_text


HUNK_HEADER_RE = re.compile(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def run_cmd(cmd: list[str]) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', check=True)
    return result.stdout


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


def build_file_diff(repo_path: str, target_branch: str, source_branch: str, path: str) -> str:
    cmd = [
        "git", "-C", repo_path, "diff", "--unified=3",
        f"{target_branch}...{source_branch}", "--", path
    ]
    return run_cmd(cmd)


def parse_hunks(diff_text: str) -> list[dict]:
    hunks = []
    for line in diff_text.splitlines():
        match = HUNK_HEADER_RE.match(line)
        if not match:
            continue

        old_start = int(match.group(1))
        old_count = int(match.group(2) or "1")
        new_start = int(match.group(3))
        new_count = int(match.group(4) or "1")
        hunks.append({
            "header": line,
            "old_start": old_start,
            "old_count": old_count,
            "new_start": new_start,
            "new_count": new_count
        })
    return hunks


def enrich_changed_files(repo_path: str, target_branch: str, source_branch: str, changed_files: list[dict]) -> tuple[list[dict], str]:
    enriched_files = []
    file_diffs = []

    for item in changed_files:
        file_diff = build_file_diff(repo_path, target_branch, source_branch, item["path"])
        enriched_item = {
            **item,
            "hunks": parse_hunks(file_diff)
        }
        enriched_files.append(enriched_item)
        if file_diff:
            file_diffs.append(file_diff.strip())

    return enriched_files, "\n\n".join(file_diffs)


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

    name_status_output = run_cmd([
        "git", "-C", repo_path, "diff", "--name-status",
        f"{target_branch}...{source_branch}"
    ])
    all_changed_files = parse_name_status(name_status_output, allowed_roots, excluded_exts)
    changed_files = all_changed_files[:max_files]

    commit_output = run_cmd([
        "git", "-C", repo_path, "log", "--oneline",
        f"{target_branch}..{source_branch}"
    ])
    commit_list = [line.strip() for line in commit_output.splitlines() if line.strip()]

    changed_files, raw_diff_text = enrich_changed_files(repo_path, target_branch, source_branch, changed_files)
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

    return {
        "diff_result": {
            "changed_files": changed_files,
            "commit_list": commit_list,
            "diff_text": diff_text,
            "skipped_files": skipped_files,
            "warnings": warnings,
            "diff_truncated": diff_truncated,
            "change_summary": [
                f"changed_files_count={len(changed_files)}",
                f"filtered_changed_files_total={len(all_changed_files)}",
                f"skipped_files_due_to_limit={skipped_file_count}",
                f"commit_count={len(commit_list)}",
                f"files_with_hunks={sum(1 for item in changed_files if item.get('hunks'))}",
                f"diff_truncated={str(diff_truncated).lower()}"
            ]
        }
    }