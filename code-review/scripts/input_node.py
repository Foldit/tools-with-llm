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


def normalize_requirement_images(inputs: dict) -> list[dict]:
    image_inputs = (
        inputs.get("requirement_images")
        or inputs.get("ui_images")
        or inputs.get("design_images")
        or []
    )

    if image_inputs is None:
        return []
    if not isinstance(image_inputs, list):
        raise ValueError("requirement_images must be an array")

    normalized = []
    for index, item in enumerate(image_inputs):
        source = ""
        note = ""
        detail = "auto"

        if isinstance(item, str):
            source = item.strip()
        elif isinstance(item, dict):
            source = str(item.get("path") or item.get("url") or item.get("source") or "").strip()
            note = str(item.get("note") or item.get("description") or "").strip()
            detail = str(item.get("detail") or "auto").strip() or "auto"
        else:
            raise ValueError(f"requirement_images[{index}] must be a string or object")

        if not source:
            raise ValueError(f"requirement_images[{index}] source is empty")

        is_remote = source.startswith("http://") or source.startswith("https://")
        is_data_url = source.startswith("data:")
        if not is_remote and not is_data_url:
            source = expand_path(source)
            if not os.path.exists(source):
                raise ValueError(f"requirement_images[{index}] path does not exist: {source}")

        normalized.append({
            "source": source,
            "note": note,
            "detail": detail
        })

    return normalized


def main(inputs: dict) -> dict:
    repo_path = expand_path(inputs.get("repo_path", "").strip())
    target_branch = inputs.get("target_branch", "").strip()
    source_branch = inputs.get("source_branch", "").strip()
    manual_requirement = inputs.get("manual_requirement", "").strip()
    devops_url = inputs.get("devops_url", "").strip()
    devops_text = inputs.get("devops_text", "").strip()
    requirement_image_notes = str(inputs.get("requirement_image_notes", "")).strip()
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

    requirement_images = normalize_requirement_images(inputs)

    task = {
        "repo_path": repo_path,
        "target_branch": target_branch,
        "source_branch": source_branch,
        "manual_requirement": manual_requirement,
        "devops_url": devops_url,
        "devops_text": devops_text,
        "requirement_images": requirement_images,
        "requirement_image_notes": requirement_image_notes,
        "output_path": output_path,
        "config_overrides": config_overrides
    }
    return {"task": task}