import os
from common import truncate_text


def read_text_file(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def detect_file_type(file_path: str) -> str:
    if file_path.endswith(".tsx"):
        return "tsx"
    if file_path.endswith(".ts"):
        return "ts"
    if file_path.endswith(".vue"):
        return "vue"
    if file_path.endswith(".jsx"):
        return "jsx"
    if file_path.endswith(".js"):
        return "js"
    return "other"


def main(inputs: dict) -> dict:
    task = inputs["task"]
    diff_result = inputs["diff_result"]
    repo_path = task["repo_path"]
    max_context_chars_per_file = inputs.get("max_context_chars_per_file", 8000)

    files = []
    for item in diff_result["changed_files"]:
        rel_path = item["path"]
        abs_path = os.path.join(repo_path, rel_path)
        content = read_text_file(abs_path)
        if not content:
            continue

        files.append({
            "file": rel_path,
            "status": item["status"],
            "file_type": detect_file_type(rel_path),
            "snippet": truncate_text(content, max_context_chars_per_file)
        })

    return {"context_bundle": {"files": files}}