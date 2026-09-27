# CPDataKit 七组修复与文案清理交付报告

日期：2026-09-27。仓库：`<repository>`。

修复验收基点：`61221891763d18597b4b85dabc2aa0e058d11655`；验收时的软件版本为 `0.9.1`。

最终全量结果：**1409 passed, 1 skipped, 40 warnings in 150.16s (0:02:30)**。精确覆盖率 **89.7876% → 90.0592%**。

完成 7 组代码修复、112 个新增参数化回归用例和 49 份 Markdown 文档的相关文案调整。界面、报告和说明改为直接陈述已有能力；运行校验、错误提示、许可文本及真实测量记录按各自用途保留。

## 基线与最终验收

使用独立 `.venv`（Python 3.12.10），执行任务书指定的 editable dev 安装。[environment.txt](environment.txt) 保存完整环境。

```powershell
.venv\Scripts\python -m pytest -q --cov=cpdatakit --cov-report=term-missing
```

基线：`1297 passed, 1 skipped, 39 warnings in 150.23s (0:02:30)`。终端覆盖率四舍五入显示 90%，JSON 精确值为 89.7875607883%。见 [baseline.txt](baseline.txt)、[baseline-coverage.json](baseline-coverage.json)。

```powershell
.venv\Scripts\python -m pytest -q --cov=cpdatakit --cov-fail-under=85 --cov-report=term-missing --cov-report=json:docs/verification/2026-09-27-review-fixes/final-coverage.json
.venv\Scripts\python -m ruff check .
.venv\Scripts\python -m ruff format --check .
.venv\Scripts\python -m pip check
.venv\Scripts\python -m build --outdir .artifacts/review-fixes/dist
.venv\Scripts\python -m twine check .artifacts/review-fixes/dist/*
```

| 验收 | 实际结果 | 证据 |
| --- | --- | --- |
| pytest + coverage | 1409 passed，1 skipped；90.0592%；85% 门槛通过 | [final-pytest.txt](final-pytest.txt)、[final-coverage.json](final-coverage.json) |
| Ruff check | All checks passed! | [final-ruff-check.txt](final-ruff-check.txt) |
| Ruff format | 287 files already formatted | [final-ruff-format.txt](final-ruff-format.txt) |
| 依赖完整性 | No broken requirements found | [final-pip-check.txt](final-pip-check.txt) |
| wheel/sdist 构建 | 两种产物成功，版本仍为 0.9.1 | [build.txt](build.txt) |
| Twine | 两种产物 PASSED | [twine.txt](twine.txt) |
| git diff --check | exit 0 | [final-diff-check.txt](final-diff-check.txt) |

1 个跳过项是原有 batch recovery 的符号链接权限测试（Windows 无创建权限），与基线一致；本轮未新增 skip。见 [skip-reason.txt](skip-reason.txt)。40 条警告中，39 条为已有第三方/CF 解码提示，新增 1 条来自验证 Zarr 默认链接处理保持原行为的用例。

## 逐项交付

### P0-1 allow_missing / string

- 问题：允许缺失的字符串曾在校验时通过、在 HDF5 写出时失败。

- 实现：采用方案 B：在校验阶段返回字段级错误，沿用现有 HDF5 文本表示。这样只修正准入一致性，改动集中在既有校验层。允许缺失时使用 missing_string_value；禁止缺失时保留 missing_value，建议均为补齐文本或删除不完整记录。

- 修复前证据：`.venv\Scripts\python -m pytest -q tests/test_review_missing_strings.py` → **5 failed, 7 passed in 3.37s**。[P0-1-red.txt](P0-1-red.txt)。

- 修复后证据：同一命令与测试文件 → **12 passed in 0.85s**。[P0-1-final-green.txt](P0-1-final-green.txt)。完整覆盖率由上面的全量命令产生。

- 改动文件（修复验收时行号）：
  - [src/cpdatakit/validation.py](../../../src/cpdatakit/validation.py)：100–115、286–300、314–326。
  - [tests/test_review_missing_strings.py](../../../tests/test_review_missing_strings.py)：1–76。
  - [docs/data-format.md](../../../docs/data-format.md)：17–20、53–56、65–78、113–115、144–147。

- 新增测试：
  - `test_missing_text_validation_and_writer_agree`：None、pd.NA、NaN 在 allow_missing 的两种取值下均被判为无效，写出保留目标状态。
  - `test_cli_missing_text_is_invalid_before_conversion`：CSV/JSON 的 validate 返回 1，convert 返回非零且没有生成 HDF5。
  - `test_complete_text_still_validates_and_round_trips`：完整英文及中文字符串在两种 schema 设置下均完成写读往返。

- 未做 / 存疑：选用 B，保留现有格式编码。审查还修正了 false 分支原先建议“允许缺失”的误导信息。

### P0-2 单位来源

- 问题：schema 的默认单位曾与来源实际声明混在同一个输出键中。

- 实现：缺少确认的来源单位时发出 unit_not_declared warning；有效数据保持 valid=True。保留 units_json，新增可选 units_source_json（declared/assumed/unknown/unspecified）。旧文件可读，来源标为 unknown。检查、HTML/Markdown/JSON 报告和比较结果显示来源，重写和显式映射保留或更新来源。新增来源映射在校验和写出前均验证。

- 修复前证据：`.venv\Scripts\python -m pytest -q tests/test_review_unit_sources.py` → **8 failed in 1.91s**。[P0-2-red.txt](P0-2-red.txt)。

- 修复后证据：同一命令与测试文件 → **12 passed in 0.70s**。[P0-2-final-green.txt](P0-2-final-green.txt)。完整覆盖率由上面的全量命令产生。

- 改动文件（修复验收时行号）：
  - [src/cpdatakit/validation.py](../../../src/cpdatakit/validation.py)：100–115、286–300、314–326。
  - [src/cpdatakit/io/__init__.py](../../../src/cpdatakit/io/__init__.py)：151–163、429–447、471。
  - [src/cpdatakit/normalization.py](../../../src/cpdatakit/normalization.py)：170、203、206、211、222、228。
  - [src/cpdatakit/inspection.py](../../../src/cpdatakit/inspection.py)：15、180、201、294、324、425、694、764。
  - [src/cpdatakit/reporting.py](../../../src/cpdatakit/reporting.py)：12、21、125–126、141、149、410、492–496、502–503、507–509、581。
  - [src/cpdatakit/comparison.py](../../../src/cpdatakit/comparison.py)：47–57、243、286–293、348。
  - [tests/test_review_unit_sources.py](../../../tests/test_review_unit_sources.py)：1–155。
  - [docs/data-format.md](../../../docs/data-format.md)：17–20、53–56、65–78、113–115、144–147。
  - [README.zh-CN.md](../../../README.zh-CN.md)：20–21、39–42、136、157、162–163、165。
  - [README.md](../../../README.md)：27、53–56、132、195–196、218–219、234、242、244。

- 新增测试：
  - `test_undeclared_csv_unit_warns_without_invalidating`：CSV 缺单位会警告，字段、严重度、记录数准确，valid 保持 True。
  - `test_declared_source_unit_is_preserved`：来源声明 ms 时保留 ms 和原始数值，并标记 declared。
  - `test_assumed_units_remain_assumed_across_read_and_rewrite`：HDF5 有效单位键保持兼容，假定来源经过写读及再次写入仍为 assumed。
  - `test_legacy_file_unit_origin_is_unknown_and_stays_readable`：移除新属性构造旧格式，读回数据成功且单位来源为 unknown。
  - `test_invalid_unit_source_metadata_is_a_read_error`：损坏的来源属性容器或非法枚举报 DataReadError。
  - `test_inspection_and_reports_show_assumed_and_declared_units`：inspect、三种报告和 comparison 保留并展示 assumed/declared。
  - `test_explicit_mapping_declares_units_and_rename_preserves_assumptions`：明确单位映射可确认来源，改名映射保留原假定来源。
  - `test_invalid_unit_origins_are_rejected_before_publication`：非法来源容器和值在验证时返回错误，即便传入伪造有效结果也会在发布前拒绝，保留旧文件。

- 未做 / 存疑：采用向后兼容的可选属性，format_version 保持 1.0。继续检验量纲兼容，数值单位换算由显式 mapping 完成。

### P1-1 加载路径 ReadLimits

- 问题：NetCDF、Zarr、Parquet 的实际 load 曾没有限额入口。

- 实现：协议及三个 reader 增加 limits=None，load_value 透传。显式限制源存储字节数及所选非标量变量的源首维长度；Zarr 执行 inventory 的链接与字节检查。None 保留既有加载行为。原生格式经应用入口复用检查流程，直接原生读函数沿用原参数。

- 修复前证据：`.venv\Scripts\python -m pytest -q tests/test_review_read_limits.py` → **24 failed, 1 warning in 1.31s**。[P1-1-red.txt](P1-1-red.txt)。

- 修复后证据：同一命令与测试文件 → **28 passed, 1 warning in 0.88s**。[P1-1-final-green.txt](P1-1-final-green.txt)。完整覆盖率由上面的全量命令产生。

- 改动文件（修复验收时行号）：
  - [src/cpdatakit/formats/base.py](../../../src/cpdatakit/formats/base.py)：118–120。
  - [src/cpdatakit/formats/_selection.py](../../../src/cpdatakit/formats/_selection.py)：11–23、102–103。
  - [src/cpdatakit/formats/netcdf.py](../../../src/cpdatakit/formats/netcdf.py)：15、112–117、121–122、133。
  - [src/cpdatakit/formats/zarr.py](../../../src/cpdatakit/formats/zarr.py)：16、41、45–48、50–53、57、120–125、129–130、142。
  - [src/cpdatakit/formats/parquet.py](../../../src/cpdatakit/formats/parquet.py)：90–97、100–101、109–110。
  - [src/cpdatakit/application/data_access.py](../../../src/cpdatakit/application/data_access.py)：101–105、111–113。
  - [tests/test_review_read_limits.py](../../../tests/test_review_read_limits.py)：1–105。
  - [docs/selective-reading.md](../../../docs/selective-reading.md)：33–51、64–66、68、70–73。

- 新增测试：
  - `test_over_limit_load_raises_data_read_error`：四个真实后端通过 reader/application 两个入口，超字节或记录上限均抛 DataReadError。
  - `test_limits_none_and_sufficient_limits_preserve_selection`：None 和足够的限额保持原选择结果 [1,2]。
  - `test_zarr_load_rejects_real_directory_links`：显式限额拒绝根目录/内部目录的真实链接，None 保留原处理。Windows 使用 NTFS 目录联接，POSIX 测试路径使用符号链接。
  - `test_record_limit_checks_selected_variables`：首变量为标量或不同短维度时，所选长记录变量仍受限制。

- 未做 / 存疑：字节限额按源存储大小定义。直接原生读 API 保留现有接口；CSV/JSON 应用入口的记录检查发生在解析后，详情已写入选择性读取文档。本机真实链接测试对象为 NTFS 目录联接。

### P1-2 catalog 错误契约与并发

- 问题：读操作可能穿透 SQLite 原始异常，跨连接作业更新可能覆盖另一线程的字段。

- 实现：统一读取连接上下文转译 DatabaseError 为 CatalogError，保留 cause 并关闭连接；原生连接配置 30 秒 busy timeout，初始化/迁移完成后启用 WAL。update_job 在同一个 BEGIN IMMEDIATE 事务内读、合并、更新和取回结果。

- 修复前证据：`.venv\Scripts\python -m pytest -q tests/test_review_catalog.py` → **24 failed, 2 passed in 1.73s**。[P1-2-red.txt](P1-2-red.txt)。

- 修复后证据：同一命令与测试文件 → **28 passed in 0.74s**。[P1-2-final-green.txt](P1-2-final-green.txt)。完整覆盖率由上面的全量命令产生。

- 改动文件（修复验收时行号）：
  - [src/cpdatakit/catalog/sqlite.py](../../../src/cpdatakit/catalog/sqlite.py)：8、118–126、129–136、257、300、309、354、418、488、561–571、602、642–644、659、664–666、669、683、730。
  - [tests/test_review_catalog.py](../../../tests/test_review_catalog.py)：1–166。
  - [tests/test_catalog_paging_results.py](../../../tests/test_catalog_paging_results.py)：255、258–259、261–275、277–278。

- 新增测试：
  - `test_all_reads_translate_database_errors`：11 个读取入口分别覆盖连接失败和真实 SQLite authorizer 拒绝查询，统一抛 CatalogError。
  - `test_connections_enable_wal_and_wait_for_busy_writers`：实际连接的 journal_mode=wal、busy_timeout 和外键开关正确。
  - `test_two_real_threads_preserve_independent_job_fields`：两个真实线程使用真实 SQLite，在写入边界同步，最终同时保留 started_at、finished_at、operation_log 和 result。
  - `test_failed_job_update_rolls_back_the_transaction`：拒绝 UPDATE 时事务回滚，旧状态和时间保持原值。
  - `test_missing_job_update_retains_domain_error`：不存在的 job 返回领域错误，其他作业保持原值。
  - `test_native_connection_failure_is_wrapped_and_closed`：原生 connect/PRAGMA 配置失败均包装异常，并验证已打开的连接关闭。

- 未做 / 存疑：并发更新同一显式字段仍按事务提交顺序生效；本修复保证省略字段取自事务内的最新记录。原有并发 result 测试改用真实连接 trace 控制时序，保留并加强结果断言。

### P1-3 三处文本原子发布

- 问题：report、inspection 和 schema 曾直接截断目标文件写入。

- 实现：三个 writer 共用 _atomic.write_text_atomic：独占创建同目录暂存文件，在写内容前复制权限，写完后调用 publish_file。保留 force、UTF-8、平台换行和原异常类别。Windows 复制 DACL 及继承策略，POSIX 保留 owner/group/mode，Linux 同时复制访问 ACL。

- 修复前证据：`.venv\Scripts\python -m pytest -q tests/test_review_atomic_text.py` → **9 failed, 7 passed in 0.61s**。[P1-3-red.txt](P1-3-red.txt)。

- 修复后证据：同一命令与测试文件 → **25 passed in 0.72s**。[P1-3-final-green.txt](P1-3-final-green.txt)。完整覆盖率由上面的全量命令产生。

- 改动文件（修复验收时行号）：
  - [src/cpdatakit/_atomic.py](../../../src/cpdatakit/_atomic.py)：7、9、54–122。
  - [src/cpdatakit/reporting.py](../../../src/cpdatakit/reporting.py)：12、21、125–126、141、149、410、492–496、502–503、507–509、581。
  - [src/cpdatakit/inspection.py](../../../src/cpdatakit/inspection.py)：15、180、201、294、324、425、694、764。
  - [src/cpdatakit/schema.py](../../../src/cpdatakit/schema.py)：16–17、350–353。
  - [tests/test_review_atomic_text.py](../../../tests/test_review_atomic_text.py)：1–153。

- 新增测试：
  - `test_interrupted_text_write_preserves_complete_target`：三种 writer 在部分内容写出后抛异常时，目标不存在或保留完整旧内容，并清理暂存。
  - `test_concurrent_text_target_is_preserved`：序列化期间出现的并发目标保持原样，写入返回已存在错误。
  - `test_text_writer_preserves_mode_and_force_contract`：默认保护目标，force 发布新内容并保持 mode。
  - `test_new_text_file_uses_normal_create_permissions`：新文件的权限与普通 create 一致。
  - `test_schema_writer_preserves_platform_newlines`：schema 输出字节采用原平台换行。
  - `test_permissions_are_preserved_before_content_write`：三种 writer 在写暂存内容前及发布后保持原权限；Windows 使用真实 icacls，覆盖继承与保护两种 ACL。
  - `test_permission_copy_failure_preserves_existing_output`：权限复制失败保留完整旧文件并清理暂存。

- 未做 / 存疑：Windows mode/DACL 行为已实际运行；POSIX owner/group/ACL 路径完成代码审查，本轮环境未执行该平台测试。HTML 继续使用内联样式，现有报告解析与自包含测试通过。

### P2-1 取消期间异常诊断

- 问题：取消标志置位后的真实异常曾被记为 CANCELLED 且 error=None。

- 实现：正常 JobCancelled 保留 CANCELLED 和空 error；真实异常仍为 CANCELLED，但提供可区分的错误摘要，并以 job ID 在本地记录完整异常。

- 修复前证据：`.venv\Scripts\python -m pytest -q tests/test_review_cancellation.py` → **2 failed, 1 passed in 0.50s**。[P2-1-red.txt](P2-1-red.txt)。

- 修复后证据：同一命令与测试文件 → **3 passed in 0.31s**。[P2-1-final-green.txt](P2-1-final-green.txt)。完整覆盖率由上面的全量命令产生。

- 改动文件（修复验收时行号）：
  - [src/cpdatakit/jobs/manager.py](../../../src/cpdatakit/jobs/manager.py)：176–181、188。
  - [tests/test_review_cancellation.py](../../../tests/test_review_cancellation.py)：1–68。

- 新增测试：
  - `test_cancelled_job_retains_failure_diagnostic_and_logs`：真实线程在取消后抛 ValueError 或 DataReadError，状态为 CANCELLED、error 非空且日志保留异常对象。
  - `test_checkpoint_cancellation_keeps_normal_cancelled_result`：正常检查点取消保持 error=None，日志中没有错误堆栈。

- 未做 / 存疑：沿用现有对外取消状态，诊断使用已有 error 字段和本地日志。

### P2-2 四处小修

- 问题：存在永假白名单判断、DAMASK 打开错误被吞、Host 文档与实现不符，以及四个纯成功调用测试。

- 实现：保留固定 7 字段投影并删除重复判断；DAMASK 打开错误改为带原 cause 的 DataReadError；文档准确说明 hostname 解析；补强六个相关测试并验证其检错能力。

- 修复前证据：`.venv\Scripts\python -m pytest -q tests/test_review_small_fixes.py` → **2 failed, 2 passed in 0.52s**。[P2-2-red.txt](P2-2-red.txt)。

- 修复后证据：同一命令与测试文件 → **4 passed in 0.35s**。[P2-2-final-green.txt](P2-2-final-green.txt)。完整覆盖率由上面的全量命令产生。

- 改动文件（修复验收时行号）：
  - [src/cpdatakit/inspection.py](../../../src/cpdatakit/inspection.py)：15、180、201、294、324、425、694、764。
  - [src/cpdatakit/adapters/damask_dadf5.py](../../../src/cpdatakit/adapters/damask_dadf5.py)：15、88–89。
  - [docs/local-ui-security.md](../../../docs/local-ui-security.md)：17–18、22、39–40、51–52、59–61。
  - [tests/test_review_small_fixes.py](../../../tests/test_review_small_fixes.py)：1–62。
  - [tests/test_v06_dependency_matrix.py](../../../tests/test_v06_dependency_matrix.py)：99、101–102、160–164、174–177、206–212。
  - [tests/test_surfalex_public_reference_case.py](../../../tests/test_surfalex_public_reference_case.py)：162–170、178、187–188。

- 新增测试：
  - `test_damask_detection_preserves_corrupt_file_cause`：真实损坏 HDF5 的检测返回 DataReadError，并保留原 OSError 原因。
  - `test_damask_detection_preserves_open_permission_error`：注入打开权限错误后，异常 cause 和原始原因保留。
  - `test_damask_detection_distinguishes_a_readable_file_without_markers`：可读且缺 marker 的 HDF5、其他后缀仍返回 False。
  - `test_portable_provenance_keeps_only_documented_fields`：任意扩展字段与敏感字段被过滤，保留固定合法字段及可移植文件名。

- 未做 / 存疑：此项的死代码删除和文档对齐没有行为修复前失败用例；采用 AST/文件回读和行为保留测试，具体证据如下。测试审计实际发现四个纯 smoke，用另外两个相关验证测试补齐六项强化，未虚报原始数量。

### P2-2 四项独立证据

1. **永假判断。** 对 `git show 6122189:src/cpdatakit/inspection.py` 与当前源码执行 AST 比较，旧 allowed 集合与 for 常量元组完全相同，条件为真的输入数为 0；当前投影字段与旧版一致。[p2-2-static-evidence.json](p2-2-static-evidence.json)。行为测试在修改前后均通过，未伪造 RED。

2. **DAMASK 检测。** 修复前两个 opens-error 用例都出现 `Failed: DID NOT RAISE DataReadError`；修复后 4 项测试通过。可读文件缺 marker 与文件打开失败得到不同结果。

3. **Host 文档。** 旧文档写 bound host and configured port，实际 `_host_name` 去掉端口；现文档说明比较解析后的 hostname。[p2-2-host-documentation.txt](p2-2-host-documentation.txt) 保存前文、后文与原实现。`web/app.py` 本轮无改动，端口校验未新增。

4. **六项断言。** 更新以下现有测试，每项同时检验成功路径或错误内容及可操作失败条件：

   - `test_matrix_rejects_silent_installed_version_drift`：版本漂移错误包含期望 pin，规范化名称成功。
   - `test_probe_completeness_uses_frozen_candidate_list`：当前候选成功，移除必需项失败。
   - `test_installed_module_accepts_normalized_environment_path`：规范化路径成功，环境外路径失败。
   - `test_installed_module_accepts_symlink_alias`：真实目录别名双向识别，外部路径失败。
   - `test_fetch_verifier_checks_md5_and_sha256`：真实内容正确摘要成功，正确 MD5 配错误 SHA-256 失败，输入保持原值。
   - `test_fetch_verifier_rejects_wrong_digest`：错误 MD5 点名文件，输入保持原值。

```powershell
.venv\Scripts\python -X utf8 docs/verification/2026-09-27-review-fixes/probe_assertions.py --historical --mutate
.venv\Scripts\python -X utf8 docs/verification/2026-09-27-review-fixes/probe_assertions.py --mutate
.venv\Scripts\python -X utf8 docs/verification/2026-09-27-review-fixes/probe_assertions.py
```

临时 no-op 校验器实验：旧版 **2 failed, 4 passed**（四项漏检）；强化后 **6 failed**（六项全部识别破坏）；实际实现 **6 passed**。脚本仅在测试进程内替换加载的校验函数，源码保持原样。证据：[p2-2-original-mutation.txt](p2-2-original-mutation.txt)、[p2-2-strengthened-mutation.txt](p2-2-strengthened-mutation.txt)、[p2-2-assertions-green.txt](p2-2-assertions-green.txt)。

## 审查追加修复与过程记录

独立审查补出并已修正：Zarr None 默认扫描、首变量为标量时漏过记录上限、非法单位来源写读不一致、string false 分支建议、权限复制时机及 Windows DACL。[review-read-units-red.txt](review-read-units-red.txt) 为前两组真实失败；[review-acl-red.txt](review-acl-red.txt) 中三个 writer 的 SDDL 断言失败，[review-acl-green.txt](review-acl-green.txt) 为对应通过结果。

初次 ACL 探针按带 BOM 的 UTF-16 读取 icacls 文件，遇到测试夹具解码错误；已修为 UTF-16LE，再在关闭 ACL 复制的旧行为上实际复现 SDDL 差异并重新启用修复。该解码错误未计为权限缺陷的 RED。记录见 [review-permissions-string-first-run.txt](review-permissions-string-first-run.txt)、[review-boundaries-fixture-error.txt](review-boundaries-fixture-error.txt)。

第一次全量运行是 1389 passed、1 failed，失败来自保留依赖发布事实的文档字符串断言；恢复对应事实措辞后最终全量通过。[initial-full.txt](initial-full.txt) 保留该过程；最新审查定向为 117 passed, 1 warning in 2.85s。

Windows 权限复制使用标准库 ctypes 调用微软公开 API；DACL 获取与设置的接口依据为 [GetNamedSecurityInfoW](https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-getnamedsecurityinfow) 和 [SetNamedSecurityInfoW](https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-setnamedsecurityinfow)。

两路审查最终均为 **0 项可操作发现**，独立报告原文见 [review.md](review.md)。

## 全项目文案清理

已检查中英文 README、指南、示例、历史设计/计划、发布说明、验证说明及界面/报告输出。49 份 Markdown 调整包括本轮功能说明和防御性文案清理；改为陈述校验内容、输入格式、快照恢复、显式映射等已有能力，并清除历史 non-goals 段落。

界面与报告相关文件：`web/static/app.js`、`reporting.py`、`model.py`、`statistics.py`、`comparison.py` 和切片说明。JSON 的 scope_note 键继续保留，值改为正面的检查内容。完整文档清单和逐行变动见 [copy-cleanup-files.json](copy-cleanup-files.json)、[changed-files.json](changed-files.json)。

## 总表

| 项目 | 结果 | 最终定向证据 |
| --- | --- | --- |
| P0-1 allow_missing / string | 通过 | 12 passed in 0.85s |
| P0-2 单位来源 | 通过 | 12 passed in 0.70s |
| P1-1 加载路径 ReadLimits | 通过 | 28 passed, 1 warning in 0.88s |
| P1-2 catalog 错误契约与并发 | 通过 | 28 passed in 0.74s |
| P1-3 三处文本原子发布 | 通过 | 25 passed in 0.72s |
| P2-1 取消期间异常诊断 | 通过 | 3 passed in 0.31s |
| P2-2 四处小修 | 通过 | 4 passed in 0.35s |


覆盖率：终端 **90% → 90%**；精确 **89.7876% → 90.0592%**。通过用例数 **1297 → 1409**，新增 **112**，跳过数量 **1 → 1**。

发布授权前的修复验收记录：schema 1.0/2.0 结构、依赖 extras、约束版本组合、公开既有参数与软件版本保持原样；未 commit、push、打标签或发布。本轮验证环境为 Windows / Python 3.12；跨平台 CI、远端发布和完整真实浏览器验收未执行。本轮产品逻辑由完整 pytest、Node 前端逻辑测试及本地构建验证。

本地结果为当前工作区改动和证据文件，分组日志、失败复现及最终覆盖率均可从本报告目录读取。

随后用户授权发布，v0.9.2 的版本和发行信息见 [发行说明](../../../.github/release-notes/v0.9.2.md)。
