# 真实 CSV 工作流实现与验证

本轮在 `f2cd9e5648f272287065f3fe20e2391b49bd5ca6`（v0.9.3）基础上完成本地开发。
代码位于分支 `codex/csv-workflow-20260929`。没有提交、推送或发布；安装包仅用于隔离验证。

## 已完成的使用路径

- 原始 CSV/TSV/文本表格可显式设置分隔符、表头、单位行、小数符号和编码，先看列数与原始样本。
- 在表格中确认保留列、输出名、类型、来源/输出单位和用途，无需手工编辑规则 JSON。
- 原始字节、规则、导入清单与已确认 HDF5 保存在新的独立目录。数据与规则的目录记录一起提交。
- 新 HDF5 1.0 保留原始数据列顺序，包括扩展列。
- 转换快照可直接成为下一步输入，绑定生成它时使用的规则。重复操作复用同一数据记录。
- 切换数据和规则会清除过期草稿、映射和预览；旧请求不能把内容回填到新的选择中。

## 自动验证

Windows / CPython 3.12.13：

| 检查 | 结果 |
|---|---|
| 改动前基线 | 1421 passed, 1 skipped, 40 warnings |
| 完整测试 | **1546 passed, 1 skipped, 40 warnings** |
| 行覆盖率 | **90.172048%**，7652/8486 行 |
| Ruff 检查、格式检查 | 通过，302 个文件格式检查完成 |
| JavaScript 语法 | app.js、authoring.js、csv-intake.js 通过 |
| git diff --check | 通过 |
| wheel 构建、twine check | 通过 |
| 独立 wheel 环境依赖检查 | 通过，47 个运行依赖包；无 httpx 开发依赖 |

跳过项是原有 `tests/test_batch_recovery.py:76`，原因是此 Windows 环境无法创建所需符号链接。
新的快照链接测试使用可用的 Windows junction 对照，已运行通过。

红绿证据保存在 `.artifacts/csv-workflow/`，包括 `order-red/green.txt`、
`intake-red/green.txt`、`intake-field-name-red/green.txt`、
`intake-preservation-red/green.txt`、`artifact-red.txt`、`artifact-race-red/green.txt`、
`web-red.txt`、`web-race-red/green.txt`、`ui-state-red/green.txt`。
最终全量记录为 `final-pytest.txt`，覆盖率明细为 `coverage.json`。

独立审查补充并修复：引号空单元格不得当作空行丢弃；HDF5 目标字段不得包含层级分隔符；
大整数和单位换算不能静默损失精度；解析达到行数上限后立即停止；确认产物在登记过程中
被修改时不能返回成功；异步作者工具不得把上一份数据的规则或映射写入当前选择。

## 真实 IN718 文件验证

输入是本机既有的 Mendeley 公开拉伸数据缓存，来源 DOI `10.17632/nx55jj48rx.2`，
作者 Simon Malej、Matjaž Godec，CC BY 4.0。源压缩包未改动，原始数据没有加入源码仓库。
脚本 `scripts/verify_csv_intake_case.py` 接收本地源压缩包和新的输出目录，便于重复核查。

- 12 个原始分号 CSV，共 **24,073 行**。
- 每份正确识别 6 列，显式选取 5 个具有单位依据的字段；第 4 列无名称和单位，明确排除，原字节保留。
- 力从 N 转为 kN，其余量按原始导出定义保存，不推断工程/真实应力应变。
- 所有文件的输出列序为 `time, extension, force, reported_stress, reported_strain`。
- 与独立分号读取并计算换算的结果比较，最大绝对差 **0.0**；行数、单位和原始文件哈希一致。
- 原压缩包 SHA-256：`8bd49396f5f78f255dadf41fb1ec1061cfe0b5d27cb3d7027c3ea61bc0a235db`。
- 汇总：`.artifacts/csv-workflow/real-acceptance/acceptance.json`。

## 实际安装包的浏览器验证

使用干净环境安装本轮 wheel，包路径确认来自该环境的 site-packages，再启动独立本地工作区。

1. 上传原始拉伸 CSV。默认逗号预览显示一列，并提示检查分隔符；选择分号后旧预览失效。
2. 重新预览显示 1,865 行、6 列。通过表格命名、选择用途、声明单位并排除未知列。
3. 数字字段改成文字时，数字单位会清空并禁用；改回数字后须重新填写单位。
4. 确认导入，直接生成报告。零错误、零警告。
5. 转换输出，主动切换到其他规则，再点击“使用此结果继续处理”；页面恢复生成结果时的规则。
6. 重复点击仍只有 2 个数据记录（原确认数据和转换结果），没有重复上传或重复登记。
7. 对转换结果生成第二份报告，再刷新页面。输入名称、记录 ID 和绑定规则仍正确。

独立回读同时确认 1,865 行的原始来源字节、五列数值、单位和列序正确，3 个任务完成、2 份报告有效。
证据：`wheel-browser-readback.json`、`browser-checks.json`、`csv-confirmation.png`、`converted-report.png`。

本地验证 wheel SHA-256：`fff090bbffcfdadd97f8b896499bbc5676b459105510e4ddc1ae24fb5d35db19`。
此包仍沿用开发基线版本号 0.9.3，不能与 PyPI 已发布的 0.9.3 内容混同。

## 使用范围

默认 CSV 上限为 64 MiB、100,000 条数据；只执行显式声明的字段/单位转换，来源未知时停止确认。
旧 HDF5 文件没有记录创建顺序时，无法自动恢复原始列序。按位置读取特征数组前应显式指定字段顺序。
文件哈希在复用和消费时复核；不声称能用这些检查原子阻止外部进程持续并发改写文件。

NetCDF3 与日期坐标兼容是后续独立里程碑，本轮没有扩展。未运行远程 CI 或其他操作系统；
以上是本地工程及数据保真证据，不是材料或模型的物理验证。
