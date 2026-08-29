# CPDataKit

CPDataKit 是一个与求解器无关的 Python 工具包，用来在晶体塑性模拟数据进入分析脚本或交给
其他工具前，检查字段、单位和形状，并完成标准化、统计和绘图。

> 当前为 alpha 版本。验证通过表示记录符合所选 schema，科学解释仍需结合研究者的领域判断。
> 仓库示例由固定随机种子生成，公开参考数据保留在其上游记录中。

## 什么时候用

数据交接时，字段名和单位很容易分叉。比如导出器给出 `eps` 和 `sigma_pa`，分析脚本却需要
`strain` 和 `stress`。CPDataKit 把这些约定写进 schema 和 mapping 文件，并把验证结果保存
到输出 HDF5。

它适合放在分析脚本前、文件交接时，或者需要追溯字段改名原因的地方。CPDataKit 将数据契约、
来源、验证和单位转换集中在数据边界，并提供 CPDataKit HDF5、选定 DAMASK DADF5 数据和
Surfalex 公开参考流程的文档化路径。

v0.2.0 提供 `curve`、`point` 和 `field2d` 三种 profile，读取 UTF-8 CSV、JSON records 和
CPDataKit 自有 HDF5。schema 显式声明字段、类型、shape、物理角色、单位、缺失值、索引、
范围与科学约定。应力/应变量、张量顺序、取向表达、单位和 ID 含义都通过 schema 或 mapping
显式提供。已有的
DAMASK DADF5 只读适配器也能在文件只有一个明确选择时完成检查和报告。
当前 writer 还会把完整的 canonical schema 和 SHA-256 写入 HDF5。提供 schema URI 时，
CPDataKit 会记录它，URI 的访问由调用方负责。

## 安装与快速开始

当前 `v0.2.0` 已发布到 PyPI，使用以下命令安装：

```powershell
python -m pip install cpdatakit
```

如果需要固定 GitHub Release wheel，可使用：

```powershell
python -m pip install "https://github.com/17636365690/cpdatakit/releases/download/v0.2.0/cpdatakit-0.2.0-py3-none-any.whl"
```

然后按照[五分钟快速教程](https://github.com/17636365690/cpdatakit/blob/main/docs/quickstart.md)
验证、统计、转换并绘制固定种子生成的示例。

## 仓库里的工作流

示例和测试覆盖以下路径：

- 在分析或交换前，按显式 schema 验证 curve、point 和二维 field 数据；
- 使用 JSON mapping 文件处理不同导出器的字段名和单位。声明过的向量、矩阵和张量字段会
  按元素转换单位，并保持原有 shape；
- 以声明的 shape 和 component order 保存向量/张量数据；
- 转换为包含单位、映射、来源和验证摘要的可审计 HDF5；
- 在 CI、文档和实验脚本中生成固定种子的合成测试数据。
- 复现公开 Surfalex HF（AA6016A）Workflow 7A 的转换，查看显式张量 mapping、来源 hash
  和 schema provenance。第三方原始文件只在用户请求时下载。

## 项目与集成链接

- [PyPI 软件包](https://pypi.org/project/cpdatakit/)
- [v0.2.0 GitHub Release](https://github.com/17636365690/cpdatakit/releases/tag/v0.2.0)
- [五分钟快速教程](https://github.com/17636365690/cpdatakit/blob/main/docs/quickstart.md)
- [Schema authoring 与 mapping 指南](https://github.com/17636365690/cpdatakit/blob/main/docs/schema-authoring.md)
- [示例目录](https://github.com/17636365690/cpdatakit/tree/main/examples)
- [公共参考案例 #1：Surfalex HF](https://github.com/17636365690/cpdatakit/tree/main/examples/public-datasets/surfalex-aa6016a)
- [路线图与 Issue](https://github.com/17636365690/cpdatakit/issues)
如果需要新的数据契约或输入格式，请在 Issue 中附一个小型合成样例和字段规则，后续改动就有
具体的测试对象。

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python examples/generate_sample_data.py --output sample_data
cpdatakit validate sample_data/synthetic_curve.csv --schema curve --json-output validation.json
cpdatakit summary sample_data/synthetic_curve.csv --schema curve --json-output summary.json
cpdatakit convert sample_data/synthetic_curve.csv --schema curve --output curve.h5
cpdatakit plot curve.h5 --schema curve --kind stress-strain --output curve.png
cpdatakit plot curve.h5 --schema curve --kind stress-strain --output curve.svg
cpdatakit inspect curve.h5 --format json --output inspect.json
cpdatakit report curve.h5 --schema curve --output report.html
```

对于字段名或单位不同的导出数据，可显式提供 mapping 文件：

```powershell
cpdatakit convert raw.csv --schema curve --mapping mapping.json --output curve.h5
```

详见[schema authoring 与 mapping 指南](https://github.com/17636365690/cpdatakit/blob/main/docs/schema-authoring.md)。

`inspect` 的 schema 参数可选。它会显示文件类型、格式版本、字段 dtype/shape/单位、缺失值、
HDF5 chunk、provenance、adapter 和结构风险。`report` 要求显式 schema，默认生成可离线打开的
HTML，也支持 `--format markdown` 和 `--format json`。报告只保留统计和验证结果，原始记录留在
输入数据中。输出已存在时要显式传入 `--force` 才会替换。验证或检查发现数据问题时退出码为 `1`，
参数、schema、读取和输出错误为 `2`。验证结果描述声明的结构检查，物理或科学判断结合领域方法完成。使用 `cpdatakit --help`
查看完整帮助。

## Python API

```python
from cpdatakit import (
    build_report,
    inspect_dataset,
    load_dataset,
    load_hdf5,
    validate_dataset,
    normalize_dataset,
    summarize_dataset,
)
from cpdatakit.adapters import DamaskDADF5Adapter

dataset = load_dataset("sample_data/synthetic_curve.csv")
result = validate_dataset(dataset, "curve")
summary = summarize_dataset(dataset, "curve", validation=result)
print(result.valid, summary)
print(inspect_dataset("curve.h5", schema="curve")["record_count"])
print(build_report("curve.h5", "curve")["validation"]["valid"])

dadf5 = DamaskDADF5Adapter(
    kind="homogenization", label="Taylor", field="mechanical", datasets=["F", "P"]
).load("result.hdf5")
window = load_hdf5("curve.h5", fields=["step", "stress"], start=10, stop=20)
```

字段映射与单位转换必须通过 `FieldMapping` 显式提供；未参与标准化的原始字段默认保留。
绘图函数返回 Matplotlib `Figure/Axes`，支持 PNG 和 SVG，并适用于 CI 无显示环境。

## 文档、限制与贡献

详细格式见[数据格式文档](https://github.com/17636365690/cpdatakit/blob/main/docs/data-format.md)，
架构、适配器、维护和路线图见仓库 `docs/`。
当前提供一个范围受限的 DAMASK DADF5 只读选择适配器，适配器贡献按格式证据、许可、可复现
夹具和科学约定清单审核。贡献前请阅读
[CONTRIBUTING.md](https://github.com/17636365690/cpdatakit/blob/main/CONTRIBUTING.md)。项目采用
Apache-2.0，依赖许可核查见
[NOTICE](https://github.com/17636365690/cpdatakit/blob/main/NOTICE)，引用信息见
[CITATION.cff](https://github.com/17636365690/cpdatakit/blob/main/CITATION.cff)。

