import subprocess
from common import truncate_text


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
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        status, path = parts
        if allowed_file(path, allowed_roots, excluded_exts):
            files.append({
                "path": path,
                "status": status
            })
    return files


def main(inputs: dict) -> dict:
    task = inputs["task"]
    repo_path = task["repo_path"]
    target_branch = task["target_branch"]
    source_branch = task["source_branch"]

    max_files = inputs.get("max_files", 20)
    max_diff_chars = inputs.get("max_diff_chars", 120000)
    allowed_roots = inputs.get("allowed_source_roots", ["src/", "packages/"])
    excluded_exts = inputs.get("excluded_extensions", [])

    name_status_output = run_cmd([
        "git", "-C", repo_path, "diff", "--name-status",
        f"{target_branch}...{source_branch}"
    ])
    changed_files = parse_name_status(name_status_output, allowed_roots, excluded_exts)[:max_files]

    commit_output = run_cmd([
        "git", "-C", repo_path, "log", "--oneline",
        f"{target_branch}..{source_branch}"
    ])
    commit_list = [line.strip() for line in commit_output.splitlines() if line.strip()]

    diff_text = run_cmd([
        "git", "-C", repo_path, "diff", "--unified=3",
        f"{target_branch}...{source_branch}"
    ])
    diff_text = truncate_text(diff_text, max_diff_chars)

    return {
        "diff_result": {
            "changed_files": changed_files,
            "commit_list": commit_list,
            "diff_text": diff_text,
            "change_summary": [
                f"changed_files_count={len(changed_files)}",
                f"commit_count={len(commit_list)}"
            ]
        }
    }