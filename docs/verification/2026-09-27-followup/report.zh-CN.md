# CPDataKit 四项收尾验收

日期：2026-09-27。基点与当前 HEAD：`034f431e45a3403debcb2ad8a2d1522ae09e8a11`。版本：`0.9.2`。

最终结果：**1421 passed, 1 skipped, 40 warnings in 150.05s (0:02:30)**，精确覆盖率 **90.0592% → 90.0655%**。

## 基线与检查范围

基线命令：

```powershell
.venv\Scripts\python -m pytest -q --cov=cpdatakit --cov-report=term-missing
.venv\Scripts\python -m ruff check .
.venv\Scripts\python -m ruff format --check .
```

基线输出：`1409 passed, 1 skipped, 40 warnings in 151.90s (0:02:31)`；覆盖率显示 90%，精确值 90.0592163286%；Ruff 与格式检查均通过。

证据：[baseline-pytest.txt](baseline-pytest.txt)、[baseline-coverage.json](baseline-coverage.json)、[baseline-ruff-check.txt](baseline-ruff-check.txt)、[baseline-ruff-format.txt](baseline-ruff-format.txt)。

### T1 包成熟度元数据

- 问题：发布 classifier 仍声明 Alpha。

- 修复前证据：`.venv\Scripts\python -m pytest -q tests/test_v06_release_metadata.py -k project_metadata_advertises_beta_development_status` → **1 failed, 12 deselected**；真实差异为 `3 - Alpha != 4 - Beta`，见 [t1-red.txt](t1-red.txt)。

- 修复后证据：同一命令 → **1 passed, 12 deselected in 0.12s**；`python -m build` 成功，wheel `METADATA` 为 `Development Status :: 4 - Beta`，见 [t1-green.txt](t1-green.txt)、[final-build.txt](final-build.txt)、[t1-wheel-metadata.json](t1-wheel-metadata.json)。

- 改动文件：`pyproject.toml:23`；`tests/test_v06_release_metadata.py:16–19`；`CHANGELOG.md:7–10`。

- 新增测试：`test_project_metadata_advertises_beta_development_status` 断言开发状态 classifier 唯一且为 Beta。

- 未做 / 存疑：采用 A；CITATION 与 v0.9.2 release notes 的成熟度核对结果为空，保持原文件，见 [t1-maturity-audit.json](t1-maturity-audit.json)。

### T2 原子写权限兜底

- 问题：权限保留的 OS 异常曾中断正常文本发布。

- 修复前证据：`.venv\Scripts\python -m pytest -q tests/test_review_atomic_text.py` → **7 failed, 22 passed**；PermissionError/OSError 从权限复制路径向上传播，见 [t2-red.txt](t2-red.txt)。

- 修复后证据：同一命令 → **29 passed in 1.97s**，见 [t2-green.txt](t2-green.txt)。

- 改动文件：`src/cpdatakit/_atomic.py:67–78`；`tests/test_review_atomic_text.py:3,138–189`；`CHANGELOG.md:12–14`。

- 新增测试：`test_permission_copy_failure_publishes_content_and_warns` 覆盖三个 writer × 两类 OS 异常，断言新内容、成功返回和 warning；`test_content_failure_after_permission_fallback_preserves_target` 断言内容写入失败仍抛错、旧文件完整、暂存清理。

- 未做 / 存疑：卷/API 故障采用注入复现；正常 NTFS 权限及继承策略保持原有真实断言，原有 staging 失败和 force 行为测试全部保留。

### T3 两处残留

- 问题：比较说明残留尾部空格，旧 diff 检查证据为 0 字节。

- 修复前证据：`.venv\Scripts\python -m pytest -q tests/test_followup_cleanup.py` → **2 failed**，分别检出字符串多余空格与空证据，见 [t3-red.txt](t3-red.txt)。

- 修复后证据：同一命令 → **2 passed in 0.32s**；证据文件记录真实 `git diff --check` 命令、退出码、stdout、stderr、HEAD 和 UTC 时间，见 [t3-green.txt](t3-green.txt)。

- 改动文件：`src/cpdatakit/comparison.py:25`；`docs/verification/2026-09-27-review-fixes/final-diff-check.txt:1–12`；`tests/test_followup_cleanup.py:1–30`；`CHANGELOG.md:15`。

- 新增测试：`test_comparison_contents_has_exact_sentence_without_trailing_space` 校验 JSON 与 Markdown 中的原句；`test_diff_check_evidence_records_command_exit_code_and_streams` 校验执行记录及退出码。

- 未做 / 存疑：原句语义保持一致；106 列的单行赋值使用本行 `E501`/`fmt: skip` 注释保持格式，Ruff 通过。旧证据目录仅改指定文件。

### T4 string 缺失声明守卫

- 问题：schema 接受的 string 缺失声明会在数据校验时被拒绝。

- 修复前证据：`.venv\Scripts\python -m pytest -q tests/test_followup_schema_missing_strings.py` → **3 failed, 1 passed**，factory、mapping、JSON 入口均为 `DID NOT RAISE SchemaError`，见 [t4-red.txt](t4-red.txt)。

- 修复后证据：同一命令 → **5 passed in 0.14s**；与旧数据层测试合跑为 **17 passed in 0.92s**，见 [t4-green.txt](t4-green.txt)、[t4-legacy-green.txt](t4-legacy-green.txt)。

- 改动文件：`src/cpdatakit/schema.py:109–114`；`tests/test_followup_schema_missing_strings.py:1–52`；`tests/test_review_missing_strings.py:4,14,18–42,45–47,67–69,91–93`；`CHANGELOG.md:10`。

- 新增测试：`test_schema_rejects_missing_text_declarations_with_field_and_action` 覆盖三个声明入口及字段/建议；`test_string_without_missing_and_numeric_missing_declarations_remain_valid` 校验有效组合；`test_raw_historical_declaration_is_rechecked_at_public_schema_boundary` 校验直接数据类对象经过真实守卫。

- 未做 / 存疑：历史数据测试使用直接 FieldSchema/ProfileSchema 对象，并在测试夹具中回放旧声明准入规则；数据校验、CLI 和 HDF5 写读保持真实调用。生产新增守卫集中在 `_validate_field`，公开签名保持不变。

保留数据层覆盖的实证：在独立进程中临时移除原有缺失文本检查，旧 12 项测试产生 **5 failed, 7 passed**；恢复正常实现后 12 项通过，见 [t4-data-layer-mutation.txt](t4-data-layer-mutation.txt)。变异在进程内完成。

## 最终验证

```powershell
.venv\Scripts\python -m pytest -q --cov=cpdatakit --cov-fail-under=90 --cov-report=term-missing --cov-report=json:docs/verification/2026-09-27-followup/final-coverage.json
.venv\Scripts\python -m ruff check .
.venv\Scripts\python -m ruff format --check .
```

输出：**1421 passed, 1 skipped, 40 warnings in 150.05s (0:02:30)**；精确覆盖率 **90.0654746915%**，90% 门槛通过；Ruff 和格式检查通过。公共签名、schema、comparison 相关测试另有 **30 passed in 0.94s**。

证据：[final-pytest.txt](final-pytest.txt)、[final-coverage.json](final-coverage.json)、[related.txt](related.txt)。

## 总表

| 项目 | 结果 | 定向验证 |
| --- | --- | --- |
| T1 | 通过 | classifier 测试通过，wheel METADATA 为 Beta |
| T2 | 通过 | 29 passed |
| T3 | 通过 | 2 passed |
| T4 | 通过 | 新守卫与历史数据层合计 17 passed |

全量通过用例 **1409 → 1421**，跳过 **1 → 1**；覆盖率 **90.0592% → 90.0655%**。

`git diff --stat` 实际输出：

```text
 CHANGELOG.md                                       | 10 +++++
 .../2026-09-27-review-fixes/final-diff-check.txt   | 12 ++++++
 pyproject.toml                                     |  2 +-
 src/cpdatakit/_atomic.py                           | 21 ++++++-----
 src/cpdatakit/comparison.py                        |  4 +-
 src/cpdatakit/schema.py                            |  6 +++
 tests/test_review_atomic_text.py                   | 44 ++++++++++++++++++++--
 tests/test_review_missing_strings.py               | 38 ++++++++++++++++---
 tests/test_v06_release_metadata.py                 |  6 +++
 9 files changed, 120 insertions(+), 23 deletions(-)
```

另外新增 `tests/test_followup_cleanup.py`、`tests/test_followup_schema_missing_strings.py` 及任务指定的 `docs/verification/2026-09-27-followup/` 证据目录。

既有文档的修改集合为 `CHANGELOG.md` 和 T3 指定的 diff 记录；147 个保护文件的 SHA-256 均与基线一致，含 README、docs/superpowers、release notes、CITATION 和公共契约快照，见 [document-scope-check.json](document-scope-check.json)。

本轮为 Windows / Python 3.12 本地验收；HEAD 与版本保持原值，Git 提交、推送和标签操作均未执行。
