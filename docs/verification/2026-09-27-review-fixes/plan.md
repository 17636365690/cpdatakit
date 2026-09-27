# CPDataKit 审查修复实施计划

**目标：** 完成任务书的 7 组修复，并清理项目说明中的防御性表述。

**依据：** 用户提供的《任务书：修复 CPDataKit 代码审查发现的 7 组问题》及本轮补充要求。
**仓库基点：** `6122189`，v0.9.1。使用本克隆独立 `.venv`，Python 3.12。
**方法：** 每组先保留真实 RED 输出，再修改实现并用相同命令记录 GREEN。
证据保存在本目录；最终报告逐项列出命令、结果、文件行号和实际完成范围。

## 设计与执行顺序

1. **基线。** `python -m pytest -q --cov=cpdatakit --cov-report=term-missing`；
   同时保存精确覆盖率 JSON、环境清单和 Ruff 基线。以本机真实结果为准。
2. **P0-1。** 在 `validation.py` 的字符串校验中提前报告缺失文本，采用方案 B。
   `tests/test_review_missing_strings.py` 覆盖 `allow_missing=True/False`、CSV/JSON、
   缺失哨兵和 CLI 校验/转换的一致性。保留 HDF5 现有编码。
3. **P0-2。** `validation.py` 为 schema 假定单位增加 warning；`io/__init__.py`
   添加可选 `units_source_json`，保留 `units_json` 和 1.0 格式；旧文件来源记为 unknown。
   `inspection.py`、`reporting.py` 和比较读取/展示保留字段 `unit_source`。
   `tests/test_review_unit_sources.py` 覆盖原始声明、假定、历史文件和再写入。
4. **P1-1。** `formats/base.py` 和 NetCDF/Zarr/Parquet `load` 增加默认 None 的 limits，
   `application/data_access.py` 透传。显式 limits 使用与 inspect 相同的输入字节/记录规则，
   Zarr 执行 store inventory。`tests/test_review_read_limits.py` 使用真实后端及链接探针。
5. **P1-2。** `catalog/sqlite.py` 统一读取异常、明确 busy timeout、启用 WAL；
   `update_job` 在同一连接的 IMMEDIATE 事务中读取、合并、更新。
   `tests/test_review_catalog.py` 注入连接/查询错误，并以真实 SQLite 和两个线程验证字段保留。
6. **P1-3。** `_atomic.py` 提供文本暂存/发布路径，reporting、inspection、schema 三个 writer
   共用；保持 force、权限、平台换行和异常契约。
   `tests/test_review_atomic_text.py` 注入部分写入异常、并发目标和发布失败，并检查旧内容。
7. **P2-1。** `jobs/manager.py` 区分正常 JobCancelled 与取消期间异常；保留 CANCELLED 状态，
   真实异常有 error 和日志。`tests/test_review_cancellation.py` 使用事件同步实际线程。
8. **P2-2。** 删除 `_portable_provenance` 重复白名单判断，保留固定字段投影；
   DAMASK detect 的打开失败改为带原始 cause 的 DataReadError；安全文档对齐 host 校验；
   审计无断言测试并补真实输出/失败分支断言。逐个记录证据。
9. **文字清理。** 扫描所有受版本管理的说明、示例、历史计划及界面文案；删除项目非目标、
   免责声明和“不能做什么”叙述，保留已有能力、操作步骤、来源、测试结果和运行时错误契约。
   中文 README 先改，英文同步对应含义；不重排无关段落。
10. **整体验证。** 更新 `[Unreleased]`，运行完整 pytest + coverage（精确值至少 90%）、
    Ruff check/format、构建和相关实际命令验收；回读证据并生成中文逐项报告。

## 保持的工程约定

- 公共参数保持兼容，新增参数提供默认值；运行依赖、约束文件、schema 两版本结构和软件版本保持原样。
- line-length 100、target py312；按 Added / Changed / Fixed 更新 Changelog。
- 本轮交付为工作区修改及验证记录，Git 提交与发布由用户另行指示。

## 每组验证命令

使用 `.venv/Scripts/python -m pytest -q tests/test_review_<主题>.py` 保存 RED/GREEN；
关联原有测试随后运行。文档事实和死代码删除使用源码回读、现有行为测试及 mutation 探针核查，
具体命令与输出在最终证据报告中列出。
