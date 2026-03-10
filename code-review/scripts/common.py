import json
import os
import re
from pathlib import Path


def ensure_dir(path: str):
    Path(path).mkdir(parents=True, exist_ok=True)


def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write_text(path: str, content: str):
    ensure_dir(str(Path(path).parent))
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def safe_json_loads(text: str):
    try:
        return json.loads(text)
    except Exception:
        return None


def truncate_text(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + "\n\n[TRUNCATED]\n"


def expand_path(path: str) -> str:
    return os.path.abspath(os.path.expanduser(path))


def render_template(template: str, variables: dict) -> str:
    result = template
    for key, value in variables.items():
        placeholder = "{{" + key + "}}"
        if isinstance(value, str):
            result = result.replace(placeholder, value)
        else:
            result = result.replace(placeholder, json.dumps(value, ensure_ascii=False, indent=2))
    return result


def extract_json_block(text: str):
    if not text:
        return None

    fenced = re.findall(r"```json\s*(\{.*?\})\s*```", text, flags=re.S)
    for block in fenced:
        parsed = safe_json_loads(block)
        if parsed is not None:
            return parsed

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start:end + 1]
        parsed = safe_json_loads(candidate)
        if parsed is not None:
            return parsed

    return None


def detect_review_intent(text: str) -> bool:
    if not text:
        return False

    keywords = [
        "审核代码",
        "代码审核",
        "code review",
        "review code",
        "review branch",
        "审核分支"
    ]
    lowered = text.lower()
    return any(k.lower() in lowered for k in keywords)


def build_missing_fields_reply():
    return """可以开始审核，但我还缺少最少必要信息。请补下面 4 项中的缺失项：

- repo_path：本地仓库路径
- target_branch：基线分支
- source_branch：待审核分支
- manual_requirement：人工需求说明

你也可以直接粘贴完整 JSON，例如：

{
  "action": "run_code_review_mvp",
  "repo_path": "/workspace/project-a",
  "target_branch": "main",
  "source_branch": "feature/your-branch",
  "manual_requirement": "请填写人工需求说明",
  "devops_url": "",
  "devops_text": "",
  "output_path": "/tmp/review-report.md"
}
"""


def build_upload_failed_reply():
    return """我检测到你想发起代码审核，但当前无法可靠读取你上传的 JSON 配置文件。

为了避免误读配置，请直接把任务 JSON 粘贴到聊天框中。可使用下面模板：

{
  "action": "run_code_review_mvp",
  "repo_path": "/workspace/project-a",
  "target_branch": "main",
  "source_branch": "feature/your-branch",
  "manual_requirement": "请填写人工需求说明",
  "devops_url": "",
  "devops_text": "",
  "output_path": "/tmp/review-report.md"
}

如果你不想贴 JSON，也可以至少告诉我这 4 项：
1. repo_path
2. target_branch
3. source_branch
4. manual_requirement
"""