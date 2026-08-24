# CPDataKit

CPDataKit（Crystal Plasticity Data Quality Toolkit）是一个与求解器无关的 Python 工具包，
用于验证、标准化、统计和可视化晶体塑性模拟数据。

> 当前为 alpha 版本。验证通过只表示数据符合显式 schema，不能证明模拟、材料模型或
> 物理解释正确。仓库内数据均由固定随机种子生成，仅用于演示和测试。

## 项目边界

CPDataKit 面向材料计算研究人员、模拟工程师和数据维护者。它不是有限元求解器、DAMASK
后处理器、Abaqus 插件、UMAT 执行器或 ODB 读取器；项目与 DAMASK、Abaqus 及 Dassault
Systèmes 没有官方隶属关系。

MVP 提供 `curve`、`point` 和 `field2d` 三种 profile，读取 UTF-8 CSV、JSON records 和
CPDataKit 自有 HDF5。schema 显式声明字段、类型、shape、物理角色、单位、缺失值、索引、
范围与科学约定。工具不会猜测应力/应变量、张量顺序、取向表达、单位或 ID 含义。

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

## 支持的实际工作流

当前仓库已经提供并验证了以下具体工作流：

- 在分析或交换前，按显式 schema 验证 curve、point 和二维 field 数据；
- 使用 JSON mapping 文件处理不同导出器的字段名和单位；
- 以声明的 shape 和 component order 保存向量/张量数据；
- 转换为包含单位、映射、来源和验证摘要的可审计 HDF5；
- 在 CI、文档和实验脚本中生成固定种子的合成测试数据。

## 项目与集成链接

- [PyPI 软件包](https://pypi.org/project/cpdatakit/)
- [v0.2.0 GitHub Release](https://github.com/17636365690/cpdatakit/releases/tag/v0.2.0)
- [五分钟快速教程](https://github.com/17636365690/cpdatakit/blob/main/docs/quickstart.md)
- [Schema authoring 与 mapping 指南](https://github.com/17636365690/cpdatakit/blob/main/docs/schema-authoring.md)
- [示例目录](https://github.com/17636365690/cpdatakit/tree/main/examples)
- [路线图与 Issue](https://github.com/17636365690/cpdatakit/issues)
如果 CPDataKit 对你的工作有帮助，欢迎 Star 仓库，并通过 Issue 告诉我们你需要的数据契约
或与求解器无关的工作流。

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
```

对于字段名或单位不同的导出数据，可显式提供 mapping 文件：

```powershell
cpdatakit convert raw.csv --schema curve --mapping mapping.json --output curve.h5
```

详见[schema authoring 与 mapping 指南](https://github.com/17636365690/cpdatakit/blob/main/docs/schema-authoring.md)。

输出已存在时默认拒绝覆盖；显式传入 `--force` 才会替换。验证/统计发现不合规数据时退出码
为 `1`，参数、读取和输出错误为 `2`。使用 `cpdatakit --help` 查看完整帮助。

## Python API

```python
from cpdatakit import load_dataset, validate_dataset, normalize_dataset, summarize_dataset

dataset = load_dataset("sample_data/synthetic_curve.csv")
result = validate_dataset(dataset, "curve")
summary = summarize_dataset(dataset, "curve", validation=result)
print(result.valid, summary)
```

字段映射与单位转换必须通过 `FieldMapping` 显式提供；未参与标准化的原始字段默认保留。
绘图函数返回 Matplotlib `Figure/Axes`，支持 PNG 和 SVG，并适用于 CI 无显示环境。

## 文档、限制与贡献

详细格式见[数据格式文档](https://github.com/17636365690/cpdatakit/blob/main/docs/data-format.md)，
架构、适配器、维护和路线图见仓库 `docs/`。
首版不实现求解器、本构积分、ODB/DADF5 直接读取、科学正确性认证、GUI、3D 交互或分布式
处理。贡献前请阅读
[CONTRIBUTING.md](https://github.com/17636365690/cpdatakit/blob/main/CONTRIBUTING.md)。项目采用
Apache-2.0，依赖许可核查见
[NOTICE](https://github.com/17636365690/cpdatakit/blob/main/NOTICE)，引用信息见
[CITATION.cff](https://github.com/17636365690/cpdatakit/blob/main/CITATION.cff)。

