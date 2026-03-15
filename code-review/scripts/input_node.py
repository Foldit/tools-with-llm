import os
import subprocess
from common import expand_path


def is_git_repo(repo_path: str) -> bool:
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip() == "true"
    except Exception:
        return False


def branch_exists(repo_path: str, branch: str) -> bool:
    try:
        subprocess.run(
            ["git", "-C", repo_path, "rev-parse", "--verify", branch],
            capture_output=True,
            text=True,
            check=True
        )
        return True
    except Exception:
        return False


def main(inputs: dict) -> dict:
    repo_path = expand_path(inputs.get("repo_path", "").strip())
    target_branch = inputs.get("target_branch", "").strip()
    source_branch = inputs.get("source_branch", "").strip()
    manual_requirement = inputs.get("manual_requirement", "").strip()
    devops_url = inputs.get("devops_url", "").strip()
    devops_text = inputs.get("devops_text", "").strip()
    output_path = expand_path(inputs.get("output_path", "./output/review-report.md").strip())
    config_overrides = inputs.get("config_overrides", {})

    if not repo_path:
        raise ValueError("repo_path is required")
    if not os.path.exists(repo_path):
        raise ValueError(f"repo_path does not exist: {repo_path}")
    if not is_git_repo(repo_path):
        raise ValueError(f"not a git repository: {repo_path}")

    if not target_branch:
        raise ValueError("target_branch is required")
    if not source_branch:
        raise ValueError("source_branch is required")

    if not branch_exists(repo_path, target_branch):
        raise ValueError(f"target_branch not found: {target_branch}")
    if not branch_exists(repo_path, source_branch):
        raise ValueError(f"source_branch not found: {source_branch}")

    if not manual_requirement:
        raise ValueError("manual_requirement is required")

    task = {
        "repo_path": repo_path,
        "target_branch": target_branch,
        "source_branch": source_branch,
        "manual_requirement": manual_requirement,
        "devops_url": devops_url,
        "devops_text": devops_text,
        "output_path": output_path,
        "config_overrides": config_overrides
    }
    return {"task": task}