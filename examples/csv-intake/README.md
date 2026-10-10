# 第一次 CSV 导入与转换

这个三行文件是合成示例，采用仪器常见的分号导出格式；它没有实验或材料验证含义。
CSV 确认导入和“使用此结果继续处理”从 v0.10.0 开始提供；v0.9.3 不含这两个功能。

## 安装软件包或源码

要求 Python 3.12 或更高版本。可用 `python -m pip install "cpdatakit==0.10.2"` 安装软件包，
或在包含 `pyproject.toml` 的源码目录执行下面的独立环境安装。
使用独立环境和完整解释器路径即可，不必修改 PowerShell 的脚本执行策略：

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install .
.venv\Scripts\cpdatakit.exe ui --workspace ./csv-demo-workspace
```

macOS / Linux：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/cpdatakit ui --workspace ./csv-demo-workspace
```

浏览器资源随包提供；使用工作台无需安装 Node.js。首次安装需要获取 Python 依赖，
之后工作台使用本机回环地址。若已有 `.venv` 或 `csv-demo-workspace`，请选择新的环境和工作区名称。

## 用工作台完成一次转换

1. 创建一个新项目，在“添加数据”中选择“导入 CSV”，选择同目录的 `instrument.csv`。
2. 点击“解析设置”，分隔符选“分号”，表头行填 `1`，单位行填 `0`，小数符号选“.”，编码选“UTF-8 / UTF-8 BOM”。点击“预览”，应显示 **3 条记录、6 列**。
3. 逐行点击“编辑”，按下表填写后点击“应用”，类型均选“小数”。第四列取消“保留”，原始字节继续保存。

| 来源列 | 输出字段名 | 来源单位 | 输出单位 | 用途 |
|---|---|---|---|---|
| 1 `(sec)` | `time` | `s` | `s` | 时间 |
| 2 `(mm)` | `extension` | `mm` | `mm` | 测量值 |
| 3 `(N)` | `force` | `N` | `kN` | 测量值 |
| 4 无列名 | 取消保留 | — | — | — |
| 5 `(MPa)` | `reported_stress` | `MPa` | `MPa` | 测量值 |
| 6 `(mm/mm)` | `reported_strain` | `mm/mm` | `dimensionless` | 测量值 |

4. 来源说明填写：“合成示例，单位由示例表头定义；第四列排除但保留原文件；不推断工程/真实应力应变。”勾选“已核对字段及来源”，再点击“确认导入”。
5. 当前数据和规则自动选中。点击“生成报告”，检查 3 条记录、零错误、零警告。
6. 点击“转换并保存”，使用新的项目内路径，例如 `results/csv-demo.h5`。
7. 转换完成后点击“使用此结果继续处理”。输入切换到转换快照及它的原规则；再次点击复用同一条记录。改用新报告路径，再生成报告。

最终字段顺序为 `time, extension, force, reported_stress, reported_strain`；力为
`0.1, 0.25, 0.375 kN`。新 HDF5 保存创建顺序；需要按位置读取时仍可用显式 `fields=[...]`。
报告检查声明的数据合同。来源单位未知时须核对来源，不能把未知量填写成无量纲。

## 运行可复现示例

同目录的 `settings.json` 保存上述声明。安装软件包后，在源码根目录运行：

```powershell
.venv\Scripts\python.exe examples/csv-intake/run_example.py --output csv-demo-output
```

macOS / Linux 使用 `.venv/bin/python`。输出目录必须是新目录；脚本拒绝替换已有成果。
输出包括原字节 `source.csv`、`schema.json`、`manifest.json`、`data.h5`、`report.json`
和 `report.html`。浏览器导入也保留原字节、规则和清单，另由工作台目录保存任务、报告和转换快照。

## 遇到错误

- 预览只有一列：检查分隔符，重新预览；改动文件或解析设置会使旧预览失效。
- `CSV row ... has ... columns`：按提示行号核对引号和分隔符。异常行不会被丢弃。
- `Column ... requires explicit input/output unit`：填写保留的数字列的来源和输出单位；文字列不填数字单位。
- 换算后的整数出现小数：改为“小数”类型。大整数应使用“整数”，无法保证精度的转换会停止。
- 原始字节变更、输出同名或快照变更：重新预览、选择新输出路径或重新转换。已登记结果不会因这次操作被覆盖。

默认上限为 64 MiB、100,000 条记录，支持逗号、分号、Tab，UTF-8/BOM 和 GB18030。
无表头用 `0`，独立单位行按包含空行的原文件行号填写。原样保留字节的下载名为
`source.csv`，原文件名、编码、小数符号和排除列均记在清单中。

## 真实 IN718 验收

真实实验源文件独立保存在上游缓存，不加入本示例。来源为
[Mendeley DOI 10.17632/nx55jj48rx.2](https://doi.org/10.17632/nx55jj48rx.2)，
作者 Simon Malej、Matjaž Godec，许可为 CC BY 4.0；来源与许可可由 DOI 的 DataCite 元数据核对。
维护者可用 `scripts/verify_csv_intake_case.py --source-zip ... --output ...` 复核原始压缩包。
脚本检查固定来源哈希、12 个 CSV、24,073 行、原字节、单位、数值和列序。
`in718-source.json` 是两个真实验收脚本共用的来源指纹；错误 ZIP 在创建证据或启动服务前被拒绝。
应力应变定义仍以原实验说明为准。
