import json
import sys
from pathlib import Path

from common import safe_json_loads, build_upload_failed_reply
from review_runner import run_review_task


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_TASK_PATH = BASE_DIR / "content.json"


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


def resolve_task_path(argv: list[str]) -> Path:
    if len(argv) >= 2 and argv[1].strip():
        return Path(argv[1]).expanduser().resolve()
    return DEFAULT_TASK_PATH


def read_task_file(task_path: Path) -> str:
    if not task_path.exists():
        raise FileNotFoundError(f"task file not found: {task_path}")
    return task_path.read_text(encoding="utf-8")


def main():
    print("开始执行code review...")

    try:
        task_path = resolve_task_path(sys.argv)
        attachment_text = read_task_file(task_path)
        result = handle_chat_message(attachment_text)
    except Exception as e:
        result = json.dumps({
            "status": "error",
            "message": str(e)
        }, ensure_ascii=False, indent=2)

    print(result)


if __name__ == "__main__":
    main()