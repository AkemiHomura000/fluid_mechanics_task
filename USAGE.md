# 程序使用说明

本文档说明如何运行 LHS 初始采样程序并准备输入。

## 1. 环境准备

- python3 3.8+
- requirements.txt 中的依赖

安装依赖：

```
pip install -r requirements.txt
```

## 2. 准备基础翼型数据

将基础翼型文件放在：

```
data/base_airfoil/NACA23012.dat
```

文件格式：两列（x y），单位弦长，不需要表头。

如果使用其他文件名，请修改 config.yaml：

```
paths:
  base_airfoil_path: data/base_airfoil/NACA23012.dat
```

## 3. 配置项目参数

编辑 config.yaml 可调整：

- 设计变量范围（alpha_deg, t_over_c）
- LHS 样本数量（optimization.n_initial_lhs）
- 弦长与旋转方向

## 4. 运行 LHS 采样

使用默认样本数：

```
python3 -m src.generate_lhs
```

指定样本数：

```
python3 -m src.generate_lhs --n-samples 12
```

覆盖 samples.csv（从 case_001 开始）：

```
python3 -m src.generate_lhs --overwrite
```

## 5. 输出内容

每个工况会生成：

```
cases/case_###/
  input_params.json
  Airfoil.txt
  upper_surface.txt
  lower_surface.txt
```

样本表保存在：

```
data/samples.csv
```

默认会追加新行，除非使用 --overwrite。

## 6. 下一步

- 按工况使用 SpaceClaim 和 Fluent 进行仿真。
- 将 CL/CD 回填到 data/samples.csv。
- 增加 Kriging + EI 脚本推荐下一组工况。

## 7. Kriging + EI 批量选点

在完成一批工况并得到 CL 后：

1. 在 data/samples.csv 中将对应行更新为：
  - `CL` 填入 Fluent 输出
  - `target = -CL`
  - `converged = yes`
  - `status = success`
2. 运行 EI 批量推荐：

```
python3 -m src.suggest_next_ei
```

可选参数（批量大小、候选点数、最小距离、分维度最小距离）：

```
python3 -m src.suggest_next_ei --batch-size 4 --n-candidates 20000 --min-distance 0.12

分维度距离约束示例（强制攻角至少相差 0.5 度）：

```
python3 -m src.suggest_next_ei --batch-size 4 --min-distance-alpha 0.5
```
```

输出内容：

- 生成一组 `cases/case_###/` 几何文件
- 写入 `data/next_case.csv`（包含多行）
- 追加多行 `pending` 到 `data/samples.csv`

## 8. 上下表面可视化

按工况目录绘制：

```
python3 -m src.plot_surfaces --case-dir cases/case_001
```

指定文件绘制：

```
python3 -m src.plot_surfaces --upper cases/case_001/upper_surface.txt --lower cases/case_001/lower_surface.txt
```

保存图片：

```
python3 -m src.plot_surfaces --case-dir cases/case_001 --out figures/surfaces_case_001.png
```

批量生成所有工况图片（输出到 figures）：

```
python3 -m src.plot_surfaces --all-cases --cases-dir cases --out-dir figures
```

默认命名格式为：

```
figures/surfaces_case_001.png
```
