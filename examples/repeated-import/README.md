# 同类 CSV 的第二次导入与下游交接

本案例使用 v0.11.0 的 CSV 设置复用功能。安装软件包或当前源码后运行
`cpdatakit ui --workspace ./repeat-import-workspace`。完整界面步骤见
[中文工作台指南](../../docs/workbench-guide.md#第二份同类文件复用已确认导入设置)。

只复用解析选项和已经确认的列声明。每份文件仍需独立保存身份、来源、许可、
哈希和实验说明。设置不包含这些事实，不会自动匹配样品表或解释领域元数据。

本目录提供公开配置与手工导入步骤，可下载
[echemdb 曲线设置](echemdb-settings.json)和[PyIRoGlass 光谱设置](pyiroglass-spectrum-settings.json)，
在工作台“导入 CSV”的“解析设置 › 复用已确认导入设置”中选择对应文件，再选择原始 CSV 并预览。
载入前请核对下述固定来源、列定义和单位；设置不会填写实验身份或来源说明，
这些事实仍须按当前文件独立确认。完整原生对照脚本与机器收据属于本机验收证据，
未随本仓库分发；验收报告中的检查数目不代表此目录提供了可直接运行的自动化对照案例。

## 案例一：echemdb 两条循环伏安曲线

固定来源为 [echemdb/electrochemistry-data 的提交 04ceb256](https://github.com/echemdb/electrochemistry-data/tree/04ceb25622008e5b823a665759fcbce9bc3f4f7f/literature/source_data/schonig_2023_entropic_5948)。
取 `schonig_2023_entropic_5948_f1_purple.csv`、`schonig_2023_entropic_5948_f1_brown.csv`
及各自同名 YAML。数据采用该仓库 `literature/LICENSE.md` 提供的 CC BY 4.0 许可选项；
作者为 Marco Schönig 与 Rolf Schuster，论文 DOI 为
[10.1039/D2CP04680F](https://doi.org/10.1039/D2CP04680F)。上游 GPL 源码不纳入本产品。

两文件均使用逗号、表头第 1 行、无独立单位行、小数点、UTF-8。

| 来源列 | 输出字段 | 类型 | 来源单位 | 输出单位 | 用途 |
| --- | --- | --- | --- | --- | --- |
| t | t | 小数 | s | s | 时间 |
| E | E | 小数 | V | V | 测量值 |
| I | I | 小数 | A | A | 测量值 |

先导入 purple 并保存设置，再载入设置处理 brown。预期分别为 3,501 和 5,001 行，
原始行序及 t、E、I 列序保留。同结构第二份应自动填入 6 个单位单元格和 3 个用途，
但仍需核对、填写 brown 的新来源说明并确认。

purple 的电解液是 KI，brown 是 KBr；两份 YAML 分开保留。E 的数值标度为 SCE，
实际参比电极类型为 Pt-Pseudo，这两层声明不能混为一谈。purple 的来源记录描述了
到 SCE 的偏移，brown 没有相同的描述，不能抄入 brown。不得额外移位或把 I 归一化为电流密度。

交接给 unitpackage 时仍需提供每份 YAML 及将字段/元数据构造成 Entry 的领域衔接代码。
该成熟原生流程本来已有元数据，因此本功能减少的是 CPDataKit 工作台内部的重复输入，
并未证明比原生流程整体更省事。数值验收要求原 CSV、HDF5 及 Entry 重开结果逐值精确相等。

## 案例二：PyIRoGlass 光谱与成分、厚度表

固定来源为 [PyIRoGlass v0.6.3](https://github.com/sarahshi/PyIRoGlass/tree/5ccb6358053a9c5cfb22ca4a65327901e9d790db/Inputs/COLAB_BINDER)，
并对照 [Zenodo 12735203 归档](https://doi.org/10.5281/zenodo.12735203) 的 CC BY 4.0 记录。
取成分/厚度表 `Colab_Binder_ChemThick.csv` 和 `TransmissionSpectra/` 中
`AC4_OL49_021920_30x30_H2O_a.CSV`、`AC4_OL49_021920_30x30_H2O_b.CSV`。
原始代码的 GPL 许可与归档数据的许可记录分别保存。

光谱使用逗号、**表头行 0**、无单位行、小数点、UTF-8；两条光谱各 3,942 行。

| 来源位置 | 输出字段 | 类型 | 来源单位 | 输出单位 | 用途 |
| --- | --- | --- | --- | --- | --- |
| 第 1 列 | Wavenumber | 小数 | 1/cm | 1/cm | coordinate（坐标） |
| 第 2 列 | Absorbance | 小数 | dimensionless | dimensionless | 测量值 |

先导入第一条并保存设置，再预览第二条。第二条可复用 2 个输出字段名、4 个单位单元格
和 2 个用途。API 配置的 `coordinate` 用途在载入后按原值保留并显示为已保存用途；
首次纯界面填写时可选择“其他”并在说明中声明坐标含义。无表头文件的两列都为小数，列交换可能呈现同样的结构；必须对照上游说明
核对列位置和实际样本值，不能把“结构一致”当作科学含义确认。

成分/厚度表是独立的 9 行样品表，按 `Sample` 与不含扩展名的光谱文件名精确关联。
化学成分是质量百分数，厚度及其标准差使用 µm；不要按表格行序连接。只选择有精确
ID 对应的谱，不要求这次两条光谱覆盖整张表。

CPDataKit 的 NumPy >=2 与 PyIRoGlass 0.6.3 的 NumPy <2 要求不兼容，采用独立环境和文件
交接。Windows 上完整 PyIRoGlass 安装还遇到 mc3 扩展编译限制。本轮原生对照执行固定
源码中未改写的 `SampleDataLoader` 读取器，验证读取和交接，不声称完整包或 MCMC 可用。

## 失败示例与判定

在副本上构造失败例，保留原件：

- 有表头曲线交换 E、I，或改名、改可见单位：设置预览应列出差异，旧声明不自动填入。
- 使用旧文件哈希提交新文件：原有导入接口应拒绝。
- 设置缺少原始列记录：解析选项可以载入，列声明须重新核对。
- 光谱样品表缺少一个 ID：案例交接检查应拒绝；通用 CSV 导入不自动完成跨文件关联。
- 样品 ID 重复：在正式 schema 中为 `Sample` 同时声明 `index: true`、`unique: true`，
  并在交接前拒绝歧义匹配；CSV 用途选择“标识”本身不会自动添加唯一性约束。

工程验收要分别核对数值、单位、列/行顺序、样品关联、来源哈希和实验说明。
CPDataKit CSV/HDF5 往返采用精确比较；原生光谱读取器的浮点解析及默认裁剪区间应
另行声明容差和比较范围。测试通过不等于仪器校准、光谱拟合或实验科学结论成立。
