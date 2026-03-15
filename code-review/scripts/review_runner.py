import json
import os
from pathlib import Path

import tiktoken

from common import read_text, render_template, expand_path
from input_node import main as input_main
from diff_node import main as diff_main
from context_node import main as context_main
from report_node import main as report_main
from llm_client import LLMClient


BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config" / "config.json"
PROMPTS_DIR = BASE_DIR / "prompts"


def deep_merge_dict(base: dict, overrides: dict) -> dict:
    merged = dict(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(config_overrides: dict | None = None) -> dict:

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)

    if config_overrides:
        config = deep_merge_dict(config, config_overrides)

    if "report" in config and "output_dir" in config["report"]:
        config["report"]["output_dir"] = expand_path(config["report"]["output_dir"])

    return config


def load_prompt(name: str) -> str:
    return read_text(str(PROMPTS_DIR / name))


def build_llm(config: dict) -> LLMClient:
    llm = config["llm"]
    return LLMClient(
        base_url=llm["base_url"],
        api_key=llm["api_key"],
        model=llm["model"],
        temperature=llm.get("temperature", 0.2),
        timeout=llm.get("timeout", 120),
        max_retries=llm.get("max_retries", 2),
        retry_backoff_seconds=llm.get("retry_backoff_seconds", 1)
    )


def get_model_encoding(model_name: str):
    try:
        return tiktoken.encoding_for_model(model_name)
    except KeyError:
        return tiktoken.get_encoding("cl100k_base")


def count_message_tokens(model_name: str, messages: list[str]) -> int:
    encoding = get_model_encoding(model_name)
    return sum(len(encoding.encode(message)) for message in messages if message)


def truncate_prompt_by_tokens(model_name: str, text: str, max_tokens: int) -> str:
    encoding = get_model_encoding(model_name)
    tokens = encoding.encode(text)
    if len(tokens) <= max_tokens:
        return text
    truncated = encoding.decode(tokens[:max_tokens])
    return truncated + "\n\n[TRUNCATED_FOR_TOKEN_BUDGET]\n"


def prepare_prompt_with_budget(config: dict, step_name: str, system_prompt: str, user_prompt: str) -> tuple[str, list[str]]:
    warnings = []
    should_count = config.get("other", {}).get("cal_token", False)
    strategy = config.get("other", {}).get("token_overflow_strategy", "error")
    if strategy == "truncate_retry":
        should_count = True

    if not should_count:
        return user_prompt, warnings

    max_tokens = config["llm"].get("max_tokens")
    if not max_tokens:
        return user_prompt, warnings

    model_name = config["llm"]["model"]
    total_tokens = count_message_tokens(model_name, [system_prompt, user_prompt])
    print(f"{step_name} prompt token 数量: {total_tokens}")

    if total_tokens <= max_tokens:
        return user_prompt, warnings

    message = (
        f"{step_name} prompt token 数量 ({total_tokens}) 超过上限 ({max_tokens})，"
        "请缩小输入范围或调整配置。"
    )
    if strategy == "warn":
        print(f"警告: {message}")
        warnings.append(message)
        return user_prompt, warnings

    if strategy == "truncate_retry":
        system_tokens = count_message_tokens(model_name, [system_prompt])
        reserved = max(16, int(max_tokens * 0.05))
        user_budget = max(max_tokens - system_tokens - reserved, 32)
        truncated_user_prompt = truncate_prompt_by_tokens(model_name, user_prompt, user_budget)
        new_total_tokens = count_message_tokens(model_name, [system_prompt, truncated_user_prompt])

        while new_total_tokens > max_tokens and user_budget > 16:
            user_budget = max(int(user_budget * 0.8), 16)
            truncated_user_prompt = truncate_prompt_by_tokens(model_name, user_prompt, user_budget)
            new_total_tokens = count_message_tokens(model_name, [system_prompt, truncated_user_prompt])

        warnings.append(
            f"{step_name} token overflow handled by truncation: before={total_tokens}, after={new_total_tokens}"
        )
        if new_total_tokens > max_tokens:
            raise ValueError(
                f"{step_name} token overflow persists after truncation: {new_total_tokens} > {max_tokens}"
            )
        return truncated_user_prompt, warnings

    raise ValueError(message)


def validate_finding_schema(item: dict, index: int) -> tuple[dict | None, str | None]:
    if not isinstance(item, dict):
        return None, f"finding[{index}] is not an object"

    evidence = item.get("evidence")
    evidence_obj = evidence if isinstance(evidence, dict) else {}
    evidence_file = evidence_obj.get("file") or item.get("file")
    evidence_line = evidence_obj.get("line")
    evidence_snippet = evidence_obj.get("snippet") if isinstance(evidence_obj.get("snippet"), str) else ""

    if not evidence_file or evidence_line in (None, "") or not evidence_snippet:
        return None, f"finding[{index}] missing required evidence(file,line,snippet)"

    normalized = {
        "severity": item.get("severity", "medium"),
        "title": item.get("title", ""),
        "category": item.get("category", ""),
        "file": item.get("file", evidence_file),
        "evidence": {
            "file": evidence_file,
            "line": evidence_line,
            "snippet": evidence_snippet
        },
        "impact": item.get("impact", ""),
        "recommendation": item.get("recommendation", ""),
        "needs_manual_confirmation": bool(item.get("needs_manual_confirmation", False))
    }
    return normalized, None


def normalize_review_result(raw_result: dict) -> tuple[dict, list[str]]:
    warnings = []
    if not isinstance(raw_result, dict):
        warnings.append("review_result is not an object, fallback to safe default")
        raw_result = {}

    findings_raw = raw_result.get("findings", [])
    if not isinstance(findings_raw, list):
        warnings.append("findings is not an array, replaced with empty list")
        findings_raw = []

    normalized_findings = []
    for index, item in enumerate(findings_raw):
        normalized, error = validate_finding_schema(item, index)
        if error:
            warnings.append(error)
            continue
        normalized_findings.append(normalized)

    coverage = raw_result.get("coverage_assessment", {})
    if not isinstance(coverage, dict):
        warnings.append("coverage_assessment is not an object, fallback to empty")
        coverage = {}

    normalized = {
        "summary": raw_result.get("summary", ""),
        "overall_decision": raw_result.get("overall_decision", "approved_with_suggestions"),
        "findings": normalized_findings,
        "coverage_assessment": {
            "covered": coverage.get("covered", []),
            "possibly_missing": coverage.get("possibly_missing", []),
            "unclear_points": coverage.get("unclear_points", [])
        }
    }
    return normalized, warnings


def run_requirement_step(llm: LLMClient, task: dict, config: dict) -> dict:
    system_prompt = load_prompt("requirement_system.txt")
    user_template = load_prompt("requirement_user.txt")
    user_prompt = render_template(user_template, {
        "task.manual_requirement": task["manual_requirement"],
        "task.devops_url": task.get("devops_url", ""),
        "task.devops_text": task.get("devops_text", "")
    })

    user_prompt, token_warnings = prepare_prompt_with_budget(config, "requirement_step", system_prompt, user_prompt)
    result = llm.chat_json(system_prompt, user_prompt)
    normalized = {
        "title": result.get("title", ""),
        "business_goal": result.get("business_goal", []),
        "acceptance_criteria": result.get("acceptance_criteria", []),
        "out_of_scope": result.get("out_of_scope", []),
        "risk_points": result.get("risk_points", []),
        "unclear_points": result.get("unclear_points", []),
        "main_source": result.get("main_source", "manual_requirement"),
        "summary": result.get("summary", "")
    }
    if token_warnings:
        normalized["warnings"] = token_warnings
    return normalized


def run_review_step(llm: LLMClient, config: dict, requirement_summary: dict, diff_result: dict, context_bundle: dict) -> dict:
    system_prompt = load_prompt("review_system.txt")
    user_template = load_prompt("review_user.txt")
    user_prompt = render_template(user_template, {
        "requirement_summary": requirement_summary,
        "diff_result.changed_files": diff_result["changed_files"],
        "diff_result.commit_list": diff_result["commit_list"],
        "diff_result.diff_text": diff_result["diff_text"],
        "context_bundle": context_bundle
    })

    user_prompt, token_warnings = prepare_prompt_with_budget(config, "review_step", system_prompt, user_prompt)
    result = llm.chat_json(system_prompt, user_prompt)
    normalized, schema_warnings = normalize_review_result(result)
    warnings = token_warnings + schema_warnings
    if warnings:
        normalized["warnings"] = warnings
    return normalized


def run_review_task(task_input: dict) -> dict:
    print("加载配置...")
    config = load_config(task_input.get("config_overrides", {}))

    validated = input_main(task_input)
    task = validated["task"]

    if not task.get("output_path"):
        name = f"review-{task['source_branch'].replace('/', '_')}.md"
        task["output_path"] = os.path.join(config["report"]["output_dir"], name)

    print("查找差异内容...")
    diff_result = diff_main({
        "task": task,
        "max_files": config["review"]["max_files"],
        "warning_max_files": config["review"].get("warning_max_files"),
        "max_diff_chars": config["review"]["max_diff_chars"],
        "warning_max_diff_chars": config["review"].get("warning_max_diff_chars"),
        "allowed_source_roots": config["review"]["allowed_source_roots"],
        "excluded_extensions": config["review"]["excluded_extensions"],
        "diff_timeout_seconds": config["review"].get("diff_timeout_seconds", 30),
        "diff_max_retries": config["review"].get("diff_max_retries", 1),
        "diff_retry_backoff_seconds": config["review"].get("diff_retry_backoff_seconds", 1),
        "strict_hunk_validation": config["review"].get("strict_hunk_validation", True),
        "max_hunks_per_file": config["review"].get("max_hunks_per_file", 12),
        "warning_max_hunks_per_file": config["review"].get("warning_max_hunks_per_file")
    })["diff_result"]

    print("获取差异内容上下文...")
    context_bundle = context_main({
        "task": task,
        "diff_result": diff_result,
        "max_context_chars_per_file": config["review"]["max_context_chars_per_file"],
        "context_lines_before_hunk": config["review"].get("context_lines_before_hunk", 20),
        "context_lines_after_hunk": config["review"].get("context_lines_after_hunk", 20),
        "max_context_snippets_per_file": config["review"].get("max_context_snippets_per_file", 6),
        "context_ranges_hard_limit": config["review"].get("context_ranges_hard_limit", config["review"].get("max_context_snippets_per_file", 6)),
        "context_ranges_soft_warning": config["review"].get("context_ranges_soft_warning"),
        "max_symbol_context_lines": config["review"].get("max_symbol_context_lines", 160),
        "warning_max_context_chars_per_file": config["review"].get("warning_max_context_chars_per_file")
    })["context_bundle"]

    print("加载LLM...")
    llm = build_llm(config)

    print("整理需求...")
    requirement_summary = run_requirement_step(llm, task, config)

    print("进行code review...")
    review_result = run_review_step(llm, config, requirement_summary, diff_result, context_bundle)

    print("生成报告...")
    report_result = report_main({
        "task": task,
        "requirement_summary": requirement_summary,
        "diff_result": diff_result,
        "context_bundle": context_bundle,
        "review_result": review_result
    })

    print("报告路径:", report_result["report_path"])
    return {
        "status": "success",
        "report_path": report_result["report_path"],
        "review_result": review_result
    }