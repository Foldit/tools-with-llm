# code-review

一个基于 LLM 的最小化 code review MVP：读取任务配置，提取分支 diff，补充上下文，调用模型生成 review 报告。

## 运行前提

- Python 3.10+
- 本机可用 `git`
- 可访问一个 OpenAI 兼容接口
- 安装依赖：`pip install requests`

## 配置

编辑 [config/config.json](d:\tools-with-llms\tools-with-llm\code-review\config\config.json)：

- `llm.base_url`：模型接口地址
- `llm.api_key`：接口密钥
- `llm.model`：模型名
- `report.output_dir`：报告输出目录

## 准备输入

编辑 [content.json](d:\tools-with-llms\tools-with-llm\code-review\content.json)，至少填写这几项：

- `repo_path`：待审核仓库的本地路径
- `target_branch`：基线分支
- `source_branch`：待审核分支
- `manual_requirement`：需求说明

示例：

```json
{
	"action": "run_code_review_mvp",
	"repo_path": "D:/your-repo",
	"target_branch": "main",
	"source_branch": "feature/order-filter",
	"manual_requirement": "新增订单筛选能力，支持按状态和创建时间筛选，刷新页面后保留筛选条件。",
	"devops_url": "",
	"devops_text": "",
	"output_path": "./output/review-report.md"
}
```

## 运行

注意：当前脚本依赖相对路径，需在 `code-review/scripts` 目录下执行。

```powershell
cd code-review/scripts
python chat_handler.py
```

执行完成后，会在终端输出结果，并生成 Markdown 报告。

## 当前限制

- 默认只审查 `src/` 和 `packages/` 下的变更，可在 [config/config.json](d:\tools-with-llms\tools-with-llm\code-review\config\config.json) 中修改 `allowed_source_roots`
- 当前入口固定读取 [content.json](d:\tools-with-llms\tools-with-llm\code-review\content.json)
