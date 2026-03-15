# code-review

一个基于 LLM 的最小化 code review MVP：读取任务配置，提取分支 diff，补充上下文，调用模型生成 review 报告。

## 运行前提

- Python 3.10+
- 本机可用 `git`
- 可访问一个 OpenAI 兼容接口
- 安装依赖：`pip install -r requirements.txt`

`tree-sitter` 相关依赖用于 TS/JS 的 AST 级上下文抽取；如果环境中缺失，会自动回退到启发式符号抽取和 hunk 邻域抽取。

当前上下文引擎支持可解释输出：每个文件会记录 `context_strategy`、`strategy_chain`、`strategy_confidence`、`fallback_reason`，便于判断为什么发生了策略降级。

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

如果你想临时覆盖默认阈值，可以在任务 JSON 中增加 `config_overrides`，例如：

```json
{
	"repo_path": "D:/your-repo",
	"target_branch": "main",
	"source_branch": "feature/order-filter",
	"manual_requirement": "新增订单筛选能力",
	"config_overrides": {
		"review": {
			"max_files": 10,
			"warning_max_files": 6,
			"max_symbol_context_lines": 120
		}
	}
}
```

## 运行

脚本默认读取 `code-review/content.json`，也支持显式传入任务文件路径，不再依赖当前工作目录。

```powershell
python code-review/scripts/chat_handler.py
```

或：

```powershell
python code-review/scripts/chat_handler.py code-review/content.json
```

执行完成后，会在终端输出结果，并生成 Markdown 报告。

## 配置补充

- `llm.max_retries`：LLM 请求失败时的最大重试次数
- `llm.retry_backoff_seconds`：重试退避基数秒数
- `other.cal_token`：是否在每次 LLM 调用前计算 prompt token
- `other.token_overflow_strategy`：token 超限处理策略，支持 `error`、`warn`、`truncate_retry`
- `review.context_lines_before_hunk`：每个 diff hunk 前额外带入的上下文行数
- `review.context_lines_after_hunk`：每个 diff hunk 后额外带入的上下文行数
- `review.max_context_snippets_per_file`：每个文件最多保留多少段 hunk 邻域上下文
- `review.context_ranges_hard_limit`：单文件上下文 range 硬上限（按 range 截断，不再按字符强截断）
- `review.context_ranges_soft_warning`：单文件上下文 range 告警阈值（超过时记录 warning）
- `review.max_symbol_context_lines`：函数/类/组件块允许扩展的最大行数，超过则回退到 hunk 邻域
- `review.warning_max_files`：变更文件数告警阈值，不改变硬限制 `max_files`
- `review.warning_max_diff_chars`：diff 大小告警阈值，不改变硬限制 `max_diff_chars`
- `review.warning_max_context_chars_per_file`：单文件上下文字符数告警阈值，不改变硬限制 `max_context_chars_per_file`
- `review.diff_timeout_seconds`：每条 git diff/log/name-status 命令超时时间
- `review.diff_max_retries`：git 命令最大重试次数（仅对可重试错误生效）
- `review.diff_retry_backoff_seconds`：git 命令重试退避秒数
- `review.strict_hunk_validation`：是否启用 hunk 计数严格校验并统计异常
- `review.max_hunks_per_file`：单文件最多保留的 hunk 数（超出后局部优先）
- `review.warning_max_hunks_per_file`：单文件 hunk 数告警阈值

## 新增行为说明

### 1) 上下文策略可解释性

上下文摘要与每个文件条目新增以下字段：

- `strategy_chain`：完整策略链路（例如 AST 失败后降级到 heuristic/hunk）
- `strategy_confidence`：最终策略置信度
- `fallback_reason`：降级原因（例如 `ast_parse_failed`、`symbol_too_large`、`unsupported_file_type`）
- `omitted_ranges`：按 range 硬限制裁剪掉的区间

### 2) 截断机制升级（按 range）

- 由原先按字符强截断改为按 range 优先级截断，优先保留靠近 hunk 的 symbol 片段
- 超出 `context_ranges_hard_limit` 时会在报告中展示 `omitted_ranges`
- `warning_max_context_chars_per_file` 仍保留为告警，不会强制字符截断正文

### 3) Diff 可靠性增强

- git 命令支持超时、重试与错误分类（例如 `git_timeout`、`git_bad_revision`）
- hunk 解析支持严格校验并产出 `hunk_anomalies`
- 针对重命名/大文件/多 hunk 文件增加局部优先策略：
	- `rename-local-first`
	- `large-file-local-first`
	- `multi-hunk-local-first`

### 4) 评审质量护栏

- review 结果增加 schema 归一化与降级处理
- `findings` 要求 evidence 必填（`file` + `line` + `snippet`），不满足会被丢弃并写入 warning
- token 超限支持 `truncate_retry`：自动收缩 user prompt 直到预算内再重试

## 当前限制

- 默认只审查 `src/` 和 `packages/` 下的变更，可在 [config/config.json](d:\tools-with-llms\tools-with-llm\code-review\config\config.json) 中修改 `allowed_source_roots`
- TS/JS/JSX/TSX 在安装 `tree-sitter` 依赖后会优先走 AST 级符号抽取；复杂语法或未安装依赖时仍可能回退到启发式或 hunk 邻域
- 目前 AST 级符号抽取仍主要覆盖 TS/JS/JSX/TSX（Vue 通过 script block 间接支持）；其他语言以启发式/hunk 为主
