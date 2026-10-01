# CSV 发布候选验收：2026-09-30 至 2026-10-01

本地 CSV 候选、真实案例和安装后使用路径已经通过本轮验证。候选未提交、推送或发布。
公开仓库最后核查仍为 `f2cd9e5648f272287065f3fe20e2391b49bd5ca6` / v0.9.3；候选远程 CI 未运行。

## 接手与保留

接手目录为 `cpdatakit-csv-workflow`，实际分支和 HEAD 与给定历史值一致，存在 25 个未提交文件。
项目及其父目录未找到 AGENTS.md；已读取 CONTRIBUTING、README、近期提交、相关 skills、原始差异及验证记录。
启动时未发现该目录正在执行测试或服务。接手文件、字节哈希及差异保存在
`.artifacts/csv-release-20260930/intake-state.json`、`intake-snapshot/` 和 `intake.diff`。

本轮使用独立本地分支 `codex/csv-release-readiness-20260930`，HEAD 保持原值，保留接手改动及同级工作树。
原始数据没有写入、重命名或删除；测试服务仅使用新建的本机回环工作区，验收后均已停止。
Git origin 仍为原账号地址；只通过当前公开仓库名称读取 GitHub 状态，没有改动 remote 配置。

## CI 诊断及实际修复

[最新依赖矩阵](https://github.com/koocmitwho/cpdatakit/actions/runs/36406667152) 的 12 个单元中，
Windows / Python 3.12 / latest 失败，其余 11 个成功。
同一提交的[常规 CI](https://github.com/koocmitwho/cpdatakit/actions/runs/36328269811)全部通过。
原始日志、sdist、依赖报告和 JUnit 已下载到本轮 `ci/` 证据目录。

失败单元的前六个场景 `historical, selection, load-more, slice, coalesce, stale-page` 连续发生
15 秒子进程超时；第七项耗时 7.616 秒，后续恢复到 0.056–0.421 秒。
Windows / Python 3.13 / latest 的 57 个非 pip/CPDataKit 依赖版本与失败单元一致，却通过全部场景。
镜像清单列出 Node 22.23.2；原任务未输出实际 Node 版本，不能把镜像声明当作运行时日志。

公开 sdist 和接手候选在 Node 22.23.2 / 24.18.0 下进行了 120 次带阶段标记的运行，全部通过，
单进程耗时 0.0506–0.8146 秒。标记覆盖脚本进入、VM 创建、资源加载、断言完成及自然退出；
没有观察到持续轮询/计时器泄漏。原宿主 CPU、磁盘或安全扫描状态没有日志，不能确定具体资源机制。
现有证据更符合运行环境短时变慢；没有本地证据支持把六次超时定性为产品逻辑缺陷。

前端测试改为一次 Node 启动，30 个场景逐项使用独立 VM，等待真实计时器和轮询收尾。
所有已有断言保留，**15 秒进程限额没有增加**；未知场景、缺少完整通过记录、延迟错误及超时均失败。
超时保留最后阶段输出，CI 增加 Node/platform 身份日志。新的批次在两个 Node 版本各运行五遍，
每批全部 30 项通过，耗时 0.6384–0.7425 秒。这项改动减少重复启动及其放大效应；候选远程结果仍待验证。

## 修改清单

| 范围 | 接手成果及本轮处理 |
|---|---|
| CSV 核心及 Web 登记 | 保留已有解析、逐列确认、原字节/清单/规则/HDF5 保存与原子登记实现；复跑其回归与真实案例 |
| HDF5 与转换复用 | 保留新文件列序、同项目快照校验、原规则恢复和重复登记复用；回读及浏览器验证 |
| 前端状态 | 修复普通上传程序切换输入后遗留旧映射/草稿；后台刷新仍保留当前编辑 |
| CSV 错误提示 | 显示真实 API 的 `error.action` 修正提示，同时保留原行/列诊断；模拟字段错误已由实际浏览器发现并纠正 |
| 前端测试/CI | 单进程多场景、后台收尾、未知/延迟错误回归、运行时身份日志、安装包 CSV 浏览器检查 |
| 来源验收 | 空 ZIP 曾能产生“成功”收据，已修复；两个真实验收脚本共用 `in718-source.json` 的固定来源指纹，错误 ZIP 在创建证据及服务前拒绝 |
| 首次使用 | 新增三行合成文件、设置、运行器、实际字段表和错误处理说明；校正安装后的命令行启动入口，补开发测试的 Node 前提 |
| 交付文档 | README 双语入口、quickstart、工作台指南、CHANGELOG、版本建议/发布说明草稿及独立 NetCDF 问题记录 |

代码、示例及文档位置分别见 `src/cpdatakit/application/csv_intake.py`、`src/cpdatakit/web/csv_workflow.py`、
`src/cpdatakit/web/artifact_inputs.py`、`src/cpdatakit/web/static/`、`tests/test_csv*`、`tests/test_frontend*`、
`examples/csv-intake/` 和两个验收脚本。
独立 Standards / Spec 审查发现的 Node 前提、普通上传状态和 ZIP 来源三项已处理；原文及闭环记录在
`.artifacts/csv-release-20260930/independent-review.md`。

## 本轮结果与历史结果

| 检查 | 状态 | 结果/证据 |
|---|---|---|
| 最终 Windows 完整测试 | 本轮通过 | **1558 passed, 1 skipped, 40 warnings**；222.68 秒；`final-pytest-v2.txt`、`final-tests-v2.xml` |
| Python 行覆盖率 | 本轮通过 | **90.172048%**，7652/8486；阈值 85%；`final-coverage-v2.json` |
| 失败 CI 依赖版本环境 | 本轮通过 | 57 个非 pip/CPDataKit 版本一致，Node 22.23.2，**156 passed**；本机 Python 3.12.13 / Windows 11，与原 3.12.10 / Server 2025 有差别 |
| ZIP 来源防误验收 | 本轮通过 | 原脚本空 ZIP 成功已先复现；固定来源校验回归通过；浏览器脚本错误 ZIP 也在输出创建前拒绝 |
| IN718 全档验收 | 本轮通过 | **12 CSV / 24,073 行**；原字节、单位、五列顺序和逐值复核通过；最大绝对差 **0.0** |
| 三行例子安装后运行 | 本轮通过 | 干净 wheel 环境运行示例，保留原文件及生成 HDF5、JSON/HTML 报告 |
| 安装包 Chromium CSV | 本轮通过 | 合成 3 行及真实 1,865 行；两份报告均有效且零警告；原规则复用、重复登记、刷新、普通上传清理通过 |
| 原常规浏览器/CLI | 本轮通过 | 原上传/校验/转换/报告/下载路径通过；文档中的 `cpdatakit ui` 实际启动、健康页通过，测试后停止 |
| Ruff、格式、JS、差异检查 | 本轮通过 | 最终检查记录与打包记录同目录 |
| wheel/sdist/metadata | 本轮通过 | 同源两次构建逐字节相同，twine 与基线版本一致性检查通过；最终交付包在 `final-dist/`，校验清单单独保存 |
| 接手完整测试 1546/1/40 | 历史通过 | 仅保留为 2026-09-29 的历史证据，未计入本轮结果 |
| 公开依赖矩阵 | 远程失败 | 原 v0.9.3 的 Windows 3.12/latest 单元仍为失败，不冒充已修复 |
| 候选远程矩阵及 macOS/Linux | 未验证 | 未获准提交/推送，因此没有触发候选远程 CI |
| NetCDF3 / 日期坐标 | 历史失败；本轮未验证 | 单独记录在 `docs/known-issues/netcdf3-datetime.md`，未扩展实现 |

唯一跳过为既有 `test_batch_lock_preserves_aliases_of_mapping_inputs[symlink]`：本机不能创建所需符号链接。
新修复没有通过新增跳过、删断言或加长超时取得通过。40 条 warnings 保留在完整日志中。
表中的所有本轮路径均有独立运行记录；三次完整测试及中间红/绿证据分别保存，没有去重拼接通过数。

最后完整测试完成后，验收脚本的来源指纹改为共用收据；相应拒绝错误来源回归、12 文件验收及真实浏览器
再次通过。包内应用代码没有随后修改；最终 wheel 与实际已安装/已测试 wheel 的哈希相同。

## 来源与数值检查

来源为 [Mendeley DOI 10.17632/nx55jj48rx.2](https://doi.org/10.17632/nx55jj48rx.2)，
作者 Simon Malej、Matjaž Godec。已实时读取[DataCite 元数据](https://api.datacite.org/dois/10.17632/nx55jj48rx.2)，
核对 CC BY 4.0 与来源页；原压缩包 SHA-256 为
`8bd49396f5f78f255dadf41fb1ec1061cfe0b5d27cb3d7027c3ea61bc0a235db`。
当前 12 份清单与历史来源 receipt 的成员名、行数、字节哈希逐项一致。

按原表头确认五个量，第四无名列显式排除且保留在原字节。输出顺序为
`time, extension, force, reported_stress, reported_strain`，力由 N 换为 kN。
原应力/应变定义未推断为工程或真实量；本轮证据是软件工作流和数据保真。

全档 API 验收以独立 pandas 分号读取、力乘 `0.001` 对照，最大差为 0.0。
浏览器回读以标准库 CSV 读取、力除 `1000` 对照：力列最大差为 `8.881784197001252e-16 kN`，
其余四列为 0；符合事先保留的 `rtol=1e-15, atol=1e-12` 检查，没有删除断言。
两种浮点计算顺序的结果分别记录，不将浏览器差值写成精确零。

## 安装及发布边界

实际安装包来自新虚拟环境的 site-packages，运行依赖检查通过，不含 httpx 开发依赖。
包内关键 JS/模板逐字节核对当前源码。Chromium 153.0.8010.12 / Playwright 1.63.0 的源码、
控制台、截图、下载回读、trace 和服务日志保留在 `browser-synthetic-v2/`、`browser-in718-final/` 与 `browser-legacy/`。
所有浏览器服务正常关闭；实际 CLI 的本地测试服务通过健康检查后经 Ctrl+C 停止，没有保留后台服务。

本地验收 wheel 仍使用开发基线版本 0.9.3，内容与 PyPI 已发布的 0.9.3 不同：
SHA-256 `16ef6f1fc07d8822d741341a55c57bf5fe02fee26c92930a00b0e1b5b44b1270`。
源码包/最终分发的哈希、安装环境及保留检查见 `.artifacts/csv-release-20260930/delivery-manifest.json`。
历史 wheel 的哈希与结果没有替代这份记录。

建议版本 **v0.10.0**，因为 CSV 确认导入与结果复用属于功能增加。
[发布说明草稿](../../.github/release-notes/v0.10.0-draft.md)已准备。
发布前仍需确认版本、同步版本元数据/安装入口、重建发布包，并在获准提交/推送后核查候选远程 CI。
CI 宿主具体资源原因未证实，NetCDF3/日期坐标仍是独立事项。当前停止在本地候选供审阅。
