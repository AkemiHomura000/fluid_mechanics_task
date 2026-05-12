# Rear Wing CFD Optimization README

## 1. Project Overview

本项目用于 FSAE 赛车尾翼准二维气动优化。目标是在固定弦长、固定来流速度、固定 CFD 求解设置的条件下，通过两个基础参数寻找最大下压力构型。

- 优化对象：Rear Wing
- 基础翼型：NACA23012
- 弦长：c = 300 mm
- 来流速度：V = 250 km/h = 69.44 m/s
- 优化目标：最大化下压力，即最大化 `-CL`
- 优化变量：`alpha_deg` 攻角，`t_over_c` 厚度比
- 推荐方法：LHS 初始采样 + Kriging 代理模型 + EI 期望改进函数
- 推荐执行方式：半自动。Python 负责参数、坐标、代理模型和推荐下一点；SpaceClaim、Fluent Meshing 和 Fluent 求解由人工完成。

整体流程：

```text
LHS 生成初始样本
↓
Python 修改翼型坐标
↓
SpaceClaim 生成几何
↓
Fluent Meshing 划分网格
↓
Fluent 求解得到 CL、CD
↓
Kriging 拟合 target = -CL
↓
EI 推荐下一组参数
↓
重复 CFD → 更新模型 → EI 选点
↓
最终构型加密网格或延长迭代验证
```

---

## 2. Design Variables

本项目只优化两个基础参数。

| 变量 | 名称 | 推荐范围 | 说明 |
|---|---|---:|---|
| `alpha_deg` | 攻角 | 0° ~ 20° | 正值定义为产生下压力方向 |
| `t_over_c` | 厚度比 | 0.10 ~ 0.16 | 基础 NACA23012 为 0.12 |

建议配置：

```yaml
design_variables:
  alpha_deg:
    min: 0
    max: 20
  t_over_c:
    min: 0.10
    max: 0.16
```

如果大攻角工况不收敛，可以缩小为：

```yaml
alpha_deg:
  min: 4
  max: 18
```

---

## 3. Sign Convention

### 3.1 Fluent 输出约定

Fluent 中通常：

```text
CL > 0：向上升力
CL < 0：向下作用力，即下压力
```

因此目标函数定义为：

```text
target = -CL
```

例如：

```text
CL = -2.10
target = -CL = 2.10
```

target 越大，说明下压力越大。

### 3.2 攻角符号约定

程序中规定：

```text
alpha_deg > 0 表示增加尾翼下压力的安装角方向
```

由于原始 NACA 翼型一般是航空升力方向，建议在几何处理中先反装尾翼：

```text
y = -y
```

然后绕 1/4 弦长点旋转。

推荐在代码中保留：

```python
rotation_sign = -1
theta_math = rotation_sign * alpha_deg * pi / 180
```

如果前几个 CFD 结果显示攻角增大后 `CL` 变为正值，说明旋转方向反了，需要把 `rotation_sign` 改为 `+1`。最终以 Fluent 结果为准。

---

## 4. Geometry Processing

每一个优化样本都需要生成新的翼型坐标。

### 4.1 输入文件

基础翼型坐标文件：

```text
data/base_airfoil/NACA23012.dat
```

要求：

```text
x, y 为单位弦长坐标
x 范围约为 0 ~ 1
前缘在 x = 0 附近
尾缘在 x = 1 附近
```

### 4.2 坐标处理步骤

对于每个工况，输入：

```text
alpha_deg
t_over_c
```

处理：

```text
1. 读取 NACA23012 原始坐标
2. 分离上表面和下表面
3. 将上下表面插值到相同 x 网格
4. 计算中弧线 yc 和半厚度 yt
5. 根据目标厚度比缩放 yt
6. 重新生成上下表面坐标
7. 将翼型反装
8. 缩放到 c = 300 mm
9. 绕 1/4 弦长点旋转 alpha_deg
10. 输出 upper_surface.txt 和 lower_surface.txt
```

---

## 5. Thickness Modification

基础翼型 NACA23012 的厚度比为：

```text
t_base = 0.12
```

目标厚度比为：

```text
t_new = t_over_c
```

厚度缩放系数：

```text
scale_t = t_new / t_base
```

若同一 x 位置上的上下表面为：

```text
yu(x)
yl(x)
```

则：

```text
yc(x) = [yu(x) + yl(x)] / 2
yt(x) = [yu(x) - yl(x)] / 2
yt_new(x) = yt(x) * scale_t
yu_new(x) = yc(x) + yt_new(x)
yl_new(x) = yc(x) - yt_new(x)
```

注意事项：

- 不建议直接改 x 坐标。
- 尾缘不要变成尖尾缘。
- 尾缘建议保留至少 `0.2%c` 的厚度。
- 对于 c = 300 mm，尾缘厚度建议不小于 `0.002 * 300 = 0.6 mm`。

---

## 6. Coordinate Rotation

坐标缩放到实际尺寸后，绕 1/4 弦长点旋转。

旋转中心：

```text
x0 = 0.25c = 75 mm
y0 = 0
```

旋转公式：

```text
xr = x - x0
yr = y - y0

x_new = x0 + xr*cos(theta) - yr*sin(theta)
y_new = y0 + xr*sin(theta) + yr*cos(theta)
```

其中：

```text
theta = rotation_sign * alpha_deg * pi / 180
```

---

## 7. Rear Wing Ground Height

尾翼不研究地面效应，离地高度固定。

建议：

```text
h_mm = 1000 mm
```

在调用课程提供的 MATLAB 几何脚本时，尾翼离地高度输入：

```text
1000
```

`h_mm` 不作为优化变量。

---

## 8. Case Folder Structure

每个工况输出到独立文件夹：

```text
cases/case_001/
├─ input_params.json
├─ upper_surface.txt
├─ lower_surface.txt
├─ Airfoil.txt
├─ Airfoil.py
├─ RearWing.scdoc
├─ RearWing.msh
├─ fluent_result.csv
└─ notes.txt
```

### 8.1 input_params.json 示例

```json
{
  "case_id": 1,
  "airfoil": "NACA23012",
  "chord_mm": 300,
  "alpha_deg": 8.5,
  "t_over_c": 0.135,
  "h_mm": 1000,
  "rotation_center": "quarter_chord",
  "rotation_sign": -1
}
```

### 8.2 上下表面坐标文件格式

`upper_surface.txt` 和 `lower_surface.txt` 格式：

```text
x_mm    y_mm
```

要求：

```text
1. 单位为 mm
2. 上下表面分别保存
3. 坐标顺序为：前缘 → 尾缘
4. 第一列为 x，第二列为 y
```

---

## 9. CFD Workflow

每个工况需要完成一次完整 CFD。

### 9.1 几何生成

```text
1. Python 生成 upper_surface.txt 和 lower_surface.txt
2. 将两个文件输入 MATLAB 程序
3. MATLAB 程序生成 Airfoil.txt 和 Airfoil.py
4. SpaceClaim 中导入 Airfoil.txt
5. 运行 Airfoil.py
6. 检查几何和边界
7. 保存为 RearWing.scdoc
```

### 9.2 SpaceClaim 检查项

脚本运行成功后，应检查：

```text
实体：
Air
LE_BOI
TE_BOI1
TE_BOI2
Airfoil_BOI

边界：
Inlet
Outlet
Farfield
MovingWall
Airfoil_Top
Airfoil_Bottom
Airfoil_TE
Sym1
Sym2
```

尾翼虽然不研究地面效应，但可以保持教程默认几何和边界结构。

### 9.3 Fluent Meshing

```text
1. 启动 Fluent
2. 选择 3D
3. 选择 Double Precision
4. 进入 Meshing 模式
5. 加载 RearWing.wtf
6. Import Geometry
7. Update Local Sizing
8. Generate Surface Mesh
9. Describe Geometry
10. Update Boundaries
11. Update Regions
12. Add Boundary Layers
13. Generate Volume Mesh
14. File → Write → Mesh
```

网格质量建议：

```text
minimum Orthogonal Quality > 0.02
```

若低于 0.02，建议检查几何、边界层或局部加密区。

### 9.4 Fluent Solver

```text
1. 启动 Fluent Solution
2. 选择 3D
3. 选择 Double Precision
4. 读取 RearWing_imCompressible.cas.h5
5. File → Read → Mesh
6. 选择 Replace Mesh
7. 检查网格尺寸
8. 初始化
9. 运行计算
10. 监视 residual、fx、fy、CL、CD
11. 判断收敛
12. 导出结果
```

### 9.5 收敛判断

不能只看残差，还要检查：

```text
1. Residual 是否下降并稳定
2. CL 是否基本稳定
3. CD 是否基本稳定
4. fx/fy 是否进入平台或小幅振荡
5. 流场是否出现大范围非物理分离
```

---

## 10. Data Table

所有工况记录在：

```text
data/samples.csv
```

字段：

```csv
case_id,source,alpha_deg,t_over_c,CL,CD,target,converged,status,note
```

字段说明：

| 字段 | 含义 |
|---|---|
| `case_id` | 工况编号 |
| `source` | 样本来源：LHS / EI / Final |
| `alpha_deg` | 攻角 |
| `t_over_c` | 厚度比 |
| `CL` | Fluent 输出升力系数 |
| `CD` | Fluent 输出阻力系数 |
| `target` | 优化目标，`target = -CL` |
| `converged` | yes / no |
| `status` | success / failed / pending |
| `note` | 备注 |

示例：

```csv
case_id,source,alpha_deg,t_over_c,CL,CD,target,converged,status,note
1,LHS,3.2,0.112,-0.85,0.11,0.85,yes,success,
2,LHS,8.6,0.145,-1.76,0.24,1.76,yes,success,
3,LHS,15.1,0.128,-2.20,0.49,2.20,yes,success,
```

---

## 11. Optimization Algorithm

本项目采用：

```text
LHS + Kriging + EI
```

### 11.1 推荐样本数量

由于只有两个优化变量，建议：

```text
初始 LHS 样本数：8 ~ 10 个
EI 新增样本数：6 ~ 10 个
最终验证样本：1 个
总 CFD 工况数：15 ~ 21 个
```

推荐配置：

```text
n_initial = 10
n_infill = 8
n_final_validation = 1
```

### 11.2 LHS 采样范围

```text
alpha_deg ∈ [0, 20]
t_over_c ∈ [0.10, 0.16]
```

### 11.3 Kriging 拟合对象

Kriging 拟合的是：

```text
target = -CL = f(alpha_deg, t_over_c)
```

输入：

```text
X = [alpha_deg, t_over_c]
```

输出：

```text
y = -CL
```

### 11.4 EI 选点流程

每次已有 CFD 结果后：

```text
1. 读取 samples.csv
2. 过滤 failed / not converged 工况
3. 用成功样本训练 Kriging
4. 在设计空间中搜索 EI 最大的点
5. 输出下一组 alpha_deg 和 t_over_c
6. 人工进行 CFD
7. 填回 CL、CD
8. 重复
```

---

## 12. Suggested Python Project Structure

推荐目录：

```text
rear_wing_optimization/
├─ README.md
├─ config.yaml
├─ data/
│  ├─ base_airfoil/
│  │  └─ NACA23012.dat
│  ├─ samples.csv
│  └─ next_case.csv
├─ cases/
│  ├─ case_001/
│  ├─ case_002/
│  └─ ...
├─ src/
│  ├─ generate_lhs.py
│  ├─ airfoil_geometry.py
│  ├─ suggest_next_ei.py
│  ├─ update_results.py
│  ├─ plot_results.py
│  └─ utils.py
└─ figures/
   ├─ optimization_history.png
   ├─ sample_distribution.png
   └─ alpha_thickness_response.png
```

---

## 13. config.yaml

```yaml
project:
  name: rear_wing_optimization
  airfoil: NACA23012

geometry:
  chord_mm: 300
  base_t_over_c: 0.12
  h_mm: 1000
  invert_y: true
  rotation_center: quarter_chord
  rotation_sign: -1
  n_points_per_surface: 200
  min_te_thickness_ratio: 0.002

design_variables:
  alpha_deg:
    min: 0
    max: 20
  t_over_c:
    min: 0.10
    max: 0.16

optimization:
  objective: negative_CL
  n_initial_lhs: 10
  n_infill_ei: 8
  random_seed: 1

cfd:
  velocity_mps: 69.44
  solver: Fluent
  meshing_workflow: RearWing.wtf
  case_file: RearWing_imCompressible.cas.h5
```

---

## 14. Core Functions

### 14.1 airfoil_geometry.py

需要实现以下函数：

```python
def read_airfoil_dat(path):
    """Read base airfoil coordinate file. Return array with columns [x, y]."""
```

```python
def split_upper_lower(coords):
    """Split original airfoil coordinates into upper and lower surfaces."""
```

```python
def resample_surfaces(upper, lower, n_points=200):
    """Interpolate upper and lower surfaces onto the same x grid."""
```

```python
def modify_thickness(upper, lower, t_new, t_base=0.12):
    """Keep camber line unchanged and scale half-thickness."""
```

```python
def invert_airfoil_y(upper, lower):
    """Flip airfoil vertically for rear wing installation."""
```

```python
def scale_to_chord(upper, lower, chord_mm=300):
    """Convert unit chord coordinates to millimeter coordinates."""
```

```python
def rotate_airfoil(upper, lower, alpha_deg, chord_mm=300, rotation_sign=-1):
    """Rotate airfoil around quarter chord."""
```

```python
def write_surface_txt(surface, path):
    """Write x_mm, y_mm coordinates."""
```

```python
def generate_case_geometry(case_id, alpha_deg, t_over_c, config):
    """Input design variables and output upper_surface.txt/lower_surface.txt."""
```

---

## 15. LHS Script

文件：

```text
src/generate_lhs.py
```

功能：

```python
def generate_lhs_samples(config):
    """
    Generate initial LHS samples for alpha_deg and t_over_c.
    Save to data/samples.csv.
    For each sample, generate case folder and airfoil geometry files.
    """
```

伪代码：

```text
read config.yaml

bounds = [
    [alpha_min, alpha_max],
    [t_min, t_max]
]

generate LHS samples with n_initial_lhs

for each sample:
    create case_id
    write sample row to samples.csv
    generate upper_surface.txt
    generate lower_surface.txt
    write input_params.json
```

---

## 16. Kriging + EI Script

文件：

```text
src/suggest_next_ei.py
```

功能：

```python
def suggest_next_case(config):
    """
    Read finished CFD samples.
    Train Gaussian Process / Kriging model.
    Calculate EI.
    Output next_case.csv and create geometry files.
    """
```

伪代码：

```text
read samples.csv
filter rows where status == success and converged == yes

X = samples[["alpha_deg", "t_over_c"]]
y = -samples["CL"]

train Kriging model

define EI(x)

search EI maximum in design space

create new case_id
write next_case.csv
append pending row to samples.csv
generate geometry files for next case
```

---

## 17. Kriging Implementation

使用 `scikit-learn` 的 `GaussianProcessRegressor`。

推荐核函数：

```python
ConstantKernel * RBF
```

示例：

```python
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, RBF

kernel = ConstantKernel(1.0) * RBF(length_scale=[1.0, 0.02])

model = GaussianProcessRegressor(
    kernel=kernel,
    normalize_y=True,
    n_restarts_optimizer=10,
    random_state=1
)

model.fit(X, y)
```

预测候选点：

```python
mu, sigma = model.predict(x_candidate, return_std=True)
```

---

## 18. EI Formula

最大化问题：

```text
y_best = max(y)
improvement = μ(x) - y_best
z = improvement / σ(x)
EI(x) = improvement * Φ(z) + σ(x) * φ(z)
```

其中：

```text
Φ(z) = standard normal CDF
φ(z) = standard normal PDF
```

如果：

```text
σ(x) < 1e-9
```

则：

```text
EI(x) = 0
```

---

## 19. EI Search Method

因为只有两个变量，EI 搜索可以很简单。

推荐方法 1：随机候选点搜索。

```text
generate 10000 random candidate points
calculate EI for each point
choose candidate with max EI
```

推荐方法 2：`scipy.optimize.differential_evolution`。

课程作业中，方法 1 足够且更容易调试。

---

## 20. Manual CFD Result Update

Fluent 计算完成后，人工更新 `samples.csv`。

CFD 前：

```csv
case_id,source,alpha_deg,t_over_c,CL,CD,target,converged,status,note
11,EI,13.6,0.145,,,,,pending,
```

CFD 后：

```csv
case_id,source,alpha_deg,t_over_c,CL,CD,target,converged,status,note
11,EI,13.6,0.145,-2.38,0.42,2.38,yes,success,force stable
```

---

## 21. Stopping Criteria

满足以下任一条件可停止优化：

```text
1. Total CFD cases >= 18 ~ 20
2. Best target improvement < 1% for 3 consecutive EI cases
3. EI recommended points concentrate around the same region
4. CFD becomes unstable in high-alpha region
5. Current best design is physically reasonable and flow field is stable
```

---

## 22. Final Validation

优化结束后，选择：

```text
best_case = argmax(target)
```

然后进行最终验证：

```text
1. 重新生成 best_case 几何
2. 如有时间，稍微加密网格
3. 延长 Fluent 迭代
4. 检查 residual 和 force stability
5. 导出最终 CL、CD
6. 导出 pressure contour、velocity contour、streamline、Cp distribution
```

最终报告中的最优结果以验证 CFD 为准，不以 Kriging 预测值为准。

---

## 23. Required Plots

程序建议生成以下图：

### 23.1 Optimization History

```text
x-axis: CFD case number
y-axis: current best -CL
```

文件：

```text
figures/optimization_history.png
```

### 23.2 Sample Distribution

```text
x-axis: alpha_deg
y-axis: t_over_c
color: target = -CL
```

文件：

```text
figures/sample_distribution.png
```

### 23.3 Response Surface

可选：

```text
x-axis: alpha_deg
y-axis: t_over_c
contour: predicted -CL
```

文件：

```text
figures/kriging_response_surface.png
```

---

## 24. Final Report Outputs

最终报告应包含：

```text
1. 优化变量和范围
2. LHS + Kriging + EI 方法说明
3. CFD 设置说明
4. 所有工况 CL、CD 表格
5. 优化历史曲线
6. 最优参数组合
7. 基准构型 vs 最优构型对比
8. 压力云图
9. 速度云图
10. 流线图
11. 分离情况分析
12. 结论
```

推荐结果表：

| Case | alpha_deg | t_over_c | CL | CD | -CL | Note |
|---:|---:|---:|---:|---:|---:|---|
| baseline | 0 | 0.12 | | | | 原始构型 |
| best | | | | | | 最优构型 |

---

## 25. Baseline Case

必须先做基准工况：

```text
alpha_deg = 0
t_over_c = 0.12
```

如果 `alpha_deg = 0` 下下压力很小，可以增加工程基准：

```text
alpha_deg = 8
t_over_c = 0.12
```

最终报告可以同时比较：

```text
原始翼型基准
优化前安装角基准
优化后最优构型
```

---

## 26. Recommended Case Plan

建议执行顺序：

```text
Stage 0:
baseline case
alpha_deg = 0
t_over_c = 0.12

Stage 1:
10 LHS initial cases

Stage 2:
8 EI infill cases

Stage 3:
best case validation
```

总工况：

```text
1 + 10 + 8 + 1 = 20 cases
```

---

## 27. Important Notes for AI Programmer

1. 不要让程序直接自动调用 Fluent，除非额外要求。
2. 本 README 默认半自动流程。
3. 程序只需要生成坐标、管理样本表、训练代理模型、推荐下一点。
4. 每次 CFD 结果由用户手动填入 `samples.csv`。
5. 所有几何文件必须按 `case_id` 单独保存。
6. 攻角符号需要通过前几个 CFD 结果验证。
7. 如果攻角增大导致 `CL` 变正，说明几何旋转方向错误。
8. 如果某工况不收敛，不要用于训练 Kriging。
9. 最终结果必须用 Fluent 验证，不使用代理模型预测值作为最终值。
10. 输出图表必须使用英文标签，方便报告整理。

---

## 28. Summary

本项目完整逻辑如下：

```text
1. 固定尾翼基础翼型 NACA23012 和弦长 c = 300 mm
2. 选择两个优化变量：alpha_deg 和 t_over_c
3. 通过 LHS 生成初始样本
4. 对每个样本修改翼型坐标并生成 CFD 几何
5. 使用 SpaceClaim、Fluent Meshing、Fluent 完成仿真
6. 记录 CL、CD，并计算 target = -CL
7. 使用 Kriging 拟合 target = f(alpha_deg, t_over_c)
8. 使用 EI 推荐下一组最有潜力的参数
9. 重复 CFD → 更新模型 → EI 选点
10. 选出最大 -CL 的构型
11. 对最终构型进行加密网格或延长迭代验证
```

最终目标：

```text
在较少 CFD 工况数量下，获得尾翼最大下压力参数组合：
alpha_deg = ?
t_over_c = ?
CL = ?
CD = ?
-CL = ?
```
