import json
import sys

from common import (
    safe_json_loads,
    extract_json_block,
    detect_review_intent,
    build_missing_fields_reply,
    build_upload_failed_reply,
)
from review_runner import run_review_task


def parse_chat_message(text: str):
    parsed = safe_json_loads(text)
    if parsed is not None:
        return {
            "mode": "json",
            "task": parsed
        }

    return {
        "mode": "unknown",
        "task": None
    }


def validate_min_fields(task: dict):
    required = ["repo_path", "target_branch", "source_branch", "manual_requirement"]
    missing = [k for k in required if not task.get(k)]
    return missing


def format_success_reply(result: dict) -> str:
    review_result = result.get("review_result", {})
    return json.dumps({
        "status": result.get("status", "success"),
        "report_path": result.get("report_path", ""),
        "overall_decision": review_result.get("overall_decision", ""),
        "summary": review_result.get("summary", "")
    }, ensure_ascii=False, indent=2)


def handle_chat_message(attachment_text: str) -> str:
    parsed = parse_chat_message(attachment_text)
    
    task = parsed["task"]

    if task is None:
        return build_upload_failed_reply()

    try:
        result = run_review_task(task)
        return format_success_reply(result)
    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": str(e)
        }, ensure_ascii=False, indent=2)


def main():
    print("开始执行code review...")
    with open('.././content.json', "r", encoding="utf-8") as f:
        attachment_text = f.read()

    result = handle_chat_message(attachment_text)
    print(result)


if __name__ == "__main__":
    main()