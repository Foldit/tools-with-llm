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


def load_config() -> dict:

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)

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
        timeout=llm.get("timeout", 120)
    )


def run_requirement_step(llm: LLMClient, task: dict) -> dict:
    system_prompt = load_prompt("requirement_system.txt")
    user_template = load_prompt("requirement_user.txt")
    user_prompt = render_template(user_template, {
        "task.manual_requirement": task["manual_requirement"],
        "task.devops_url": task.get("devops_url", ""),
        "task.devops_text": task.get("devops_text", "")
    })

    result = llm.chat_json(system_prompt, user_prompt)
    return {
        "title": result.get("title", ""),
        "business_goal": result.get("business_goal", []),
        "acceptance_criteria": result.get("acceptance_criteria", []),
        "out_of_scope": result.get("out_of_scope", []),
        "risk_points": result.get("risk_points", []),
        "unclear_points": result.get("unclear_points", []),
        "main_source": result.get("main_source", "manual_requirement"),
        "summary": result.get("summary", "")
    }


def run_review_step(llm: LLMClient, requirement_summary: dict, diff_result: dict, context_bundle: dict) -> dict:
    system_prompt = load_prompt("review_system.txt")
    user_template = load_prompt("review_user.txt")
    user_prompt = render_template(user_template, {
        "requirement_summary": requirement_summary,
        "diff_result.changed_files": diff_result["changed_files"],
        "diff_result.commit_list": diff_result["commit_list"],
        "diff_result.diff_text": diff_result["diff_text"],
        "context_bundle": context_bundle
    })

    result = llm.chat_json(system_prompt, user_prompt)
    return {
        "summary": result.get("summary", ""),
        "overall_decision": result.get("overall_decision", "approved_with_suggestions"),
        "findings": result.get("findings", []),
        "coverage_assessment": result.get("coverage_assessment", {
            "covered": [],
            "possibly_missing": [],
            "unclear_points": []
        })
    }


def run_review_task(task_input: dict) -> dict:
    print("加载配置...")
    config = load_config()

    validated = input_main(task_input)
    task = validated["task"]

    if not task.get("output_path"):
        name = f"review-{task['source_branch'].replace('/', '_')}.md"
        task["output_path"] = os.path.join(config["report"]["output_dir"], name)

    print("查找差异内容...")
    diff_result = diff_main({
        "task": task,
        "max_files": config["review"]["max_files"],
        "max_diff_chars": config["review"]["max_diff_chars"],
        "allowed_source_roots": config["review"]["allowed_source_roots"],
        "excluded_extensions": config["review"]["excluded_extensions"]
    })["diff_result"]

    print("获取差异内容上下文...")
    context_bundle = context_main({
        "task": task,
        "diff_result": diff_result,
        "max_context_chars_per_file": config["review"]["max_context_chars_per_file"]
    })["context_bundle"]

    print("加载LLM...")
    llm = build_llm(config)

    print("整理需求...")
    requirement_summary = run_requirement_step(llm, task)

    model_name = config["llm"]["model"]
    
    if config.get("other", {}).get("cal_token", False):

        user_template = load_prompt("requirement_user.txt")
        user_prompt = render_template(user_template, {
            "task.manual_requirement": task["manual_requirement"],
            "task.devops_url": task.get("devops_url", ""),
            "task.devops_text": task.get("devops_text", "")
        })

        try:
            # 尝试获取对应模型的特定编码（如 gpt-4o, gpt-3.5-turbo 等）
            encoding = tiktoken.encoding_for_model(model_name)
        except KeyError:
            # 如果模型名称不在 tiktoken 默认支持列表中，回退到目前最常用的 cl100k_base
            encoding = tiktoken.get_encoding("cl100k_base")
            

        exact_tokens = len(encoding.encode(user_prompt))
        print(f"当前任务上下文的精确 Token 数目为: {exact_tokens}")

        if exact_tokens > config["llm"]["max_tokens"]:
            print(f"\n⚠️ 警告: 实际 Token 数量 ({exact_tokens}) 已超过 {config["llm"]["max_tokens"]} 上限！")
            choice = input("继续执行极大概率会导致接口报错或截断。是否仍要强制执行？(y/n): ").strip().lower()
            if choice != 'y':
                print("已取消本次 Code Review。")
                return {
                    "status": "cancelled",
                    "report_path": "",
                    "review_result": {
                        "overall_decision": "cancelled",
                        "summary": f"用户因 Token 数过大 ({exact_tokens}) 手动取消了本次审核。"
                    }
                }

    print("进行code review...")
    review_result = run_review_step(llm, requirement_summary, diff_result, context_bundle)

    print("生成报告...")
    report_result = report_main({
        "task": task,
        "requirement_summary": requirement_summary,
        "diff_result": diff_result,
        "review_result": review_result
    })

    print("报告路径:", report_result["report_path"])
    return {
        "status": "success",
        "report_path": report_result["report_path"],
        "review_result": review_result
    }