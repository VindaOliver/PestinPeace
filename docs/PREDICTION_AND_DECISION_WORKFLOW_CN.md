# 当前系统的虫情预测与喷药决策说明

本文档面向项目组成员，目的是用尽量容易理解的方式，说明我们当前系统到底是如何进行虫情预测和喷药决策的。

这份说明重点回答 5 个问题：

1. 我们现在的系统由哪几部分组成
2. 数据是从哪里来的，存到哪里去
3. 现在的“预测”到底是怎么做的
4. 现在的“决策”到底是怎么做的
5. 当前方案的边界和局限在哪里

---

## 1. 先用一句话理解当前系统

我们现在的系统不是“一个模型做完所有事情”，而是分成了几层：

1. 图像识别层：负责数虫子
2. 环境采集层：负责记录温度、湿度、气压等
3. 趋势预测层：负责判断接下来虫压是上升、稳定还是下降
4. 喷药决策层：负责给出喷不喷、喷多大范围、喷多少液量

也就是说：

- `/predict` 负责“看见了多少虫”
- `/telemetry` 负责“环境现在怎么样”
- `/forecast/weekly` 或 `/forecast/auto` 负责“接下来虫情会怎样”
- `/decision/weekly` 负责“基于当前周状态，喷药建议是什么”

这几层是串联关系，但目前还没有形成真正的自动闭环控制。

---

## 2. 当前系统的数据流

### 2.1 图像数据怎么进系统

用户或设备把图片发到：

```text
POST /predict
```

服务端会做 YOLO 检测，得到：

- 图片里有多少只蚜虫
- 每个检测框的位置和置信度

除了返回识别结果以外，服务端还会把这次识别出来的虫量写进 Azure Table 的虫量表：

```text
aphidcounts
```

这里存的核心字段包括：

- `device_id`
- `ts`
- `count`
- `request_id`
- `filename`

所以，`/predict` 不只是“识别图片”，还会顺手把虫量历史沉淀下来，供后面的预测使用。

---

### 2.2 环境数据怎么进系统

树莓派或其他设备把环境传感器数据发到：

```text
POST /telemetry
```

服务端把它写入 Azure Table 的环境表：

```text
iottelemetry
```

这里通常记录：

- `device_id`
- `ts`
- `temperature`
- `humidity`
- `pressure_hpa`
- `light`

所以，环境数据和虫量数据是分开存储的，不在同一张表里。

---

### 2.3 为什么 `device_id` 很重要

当前系统里，预测时是按 `device_id` 去查历史数据的。

这意味着以下几条链路最好保持同一个 `device_id`：

1. `/telemetry`
2. `/predict`
3. `/forecast/auto`

只有这样，系统才能把：

- 这个监测点的环境历史
- 这个监测点的虫量历史

正确对应起来。

如果 `device_id` 不统一，就会出现预测时拿不到对应历史数据的问题。

---

## 3. 当前“预测”是怎么做的

我们现在的预测层主要有两个入口：

1. `POST /forecast/weekly`
2. `GET /forecast/auto`

它们的区别不是预测逻辑不同，而是“输入是你手动给，还是系统自动去找”。

---

### 3.1 手动预测：`/forecast/weekly`

这个接口适合测试和调试。

你需要自己传入一组数据，例如：

- 当前窗口内虫量 `aphid_count`
- 当前窗口对应的 `exposure_days`
- 上一个窗口的虫量速率 `prev_catch_rate`
- 当前平均温度 `t_mean`
- 当前平均湿度 `rh_mean`
- 当前平均气压 `pressure_mean`
- 未来预测温度 `t_forecast`
- 未来预测湿度 `rh_forecast`
- 未来预测气压 `pressure_forecast`

服务端收到这些数据后，会把它们转换成模型需要的特征，再送进预测模型。

---

### 3.2 自动预测：`/forecast/auto`

这个接口更接近真实运行场景。

调用方式类似：

```text
GET /forecast/auto?device_id=trap-001&days=7
```

它会自动做下面几件事。

#### 第一步：取最近一段时间的环境数据

系统会去 `iottelemetry` 表里读取指定 `device_id` 最近 `days` 天的数据。

然后计算：

- `t_mean`：当前窗口温度均值
- `rh_mean`：当前窗口湿度均值
- `pressure_mean`：当前窗口气压均值

这里的“当前窗口”一般就是最近 7 天或你指定的窗口长度。

---

#### 第二步：取最近一段时间的虫量数据

系统会去 `aphidcounts` 表里读取同一个 `device_id` 的虫量记录。

然后把数据分成两个窗口：

1. 当前窗口
2. 前一个对比窗口

例如当 `days=7` 时：

- 当前窗口：最近 7 天
- 前一个窗口：再往前 7 天

系统会计算：

- `aphid_count`：当前窗口总虫量
- `exposure_days`：当前窗口里实际有虫量记录的天数
- `prev_catch_rate`：前一个窗口的平均虫量速率

这一步非常重要，因为当前系统的“趋势”并不是只看现在虫多不多，而是通过当前窗口和前一个窗口做比较。

---

### 3.3 当前系统里的“虫压趋势”怎么理解

在当前实现里，一个很关键的量叫：

```text
catch_rate = aphid_count / exposure_days
```

可以把它理解为：

“当前窗口内，平均每天观察到多少只虫”

然后系统再计算：

```text
catch_trend = catch_rate - prev_catch_rate
```

它表示：

- 如果大于 0，说明当前窗口比前一个窗口更高
- 如果小于 0，说明当前窗口比前一个窗口更低
- 如果接近 0，说明变化不明显

所以你现在的系统里，“虫压趋势”本质上不是复杂物理模型，而是：

“当前虫量速率与前一窗口虫量速率之间的变化”

---

### 3.4 预测模型到底用了哪些特征

当前 forecast 模型使用的主要特征包括：

- `log_catch`
- `catch_trend`
- `T_mean`
- `RH_mean`
- `pressure_mean`
- `VPD_mean`
- `T_forecast`
- `RH_forecast`
- `pressure_forecast`
- `VPD_forecast`
- `temp_delta`
- `rh_delta`
- `pressure_delta`
- `doy_sin`
- `doy_cos`
- `in_tepp_window`

这些特征可以分成 4 类来理解。

#### 1. 当前虫量相关

- `catch_rate`
- `log_catch`
- `catch_trend`

它们描述当前虫量水平，以及最近是不是在上升。

#### 2. 当前环境相关

- `T_mean`
- `RH_mean`
- `pressure_mean`
- `VPD_mean`

它们描述最近这段时间的环境条件。

#### 3. 未来天气相关

- `T_forecast`
- `RH_forecast`
- `pressure_forecast`
- `VPD_forecast`
- `temp_delta`
- `rh_delta`
- `pressure_delta`

它们描述未来天气，以及未来天气相对现在的变化方向。

#### 4. 季节相关

- `doy_sin`
- `doy_cos`
- `in_tepp_window`

这些特征是为了告诉模型：

- 现在大概处于一年中的什么时间
- 是否处于施药窗口附近

也就是说，当前模型不是只看虫量，也会看天气和季节信息。

---

### 3.5 预测模型输出什么

当前的 forecast 层实际有两个输出任务：

#### 1. 趋势分类

预测结果会落在 3 类之一：

- `down`
- `stable`
- `up`

代码里对应：

- `-1 = down`
- `0 = stable`
- `1 = up`

#### 2. 下一个窗口的虫量估计

模型还会估计一个：

```text
next_catch_rate_estimate
```

再进一步换算成：

```text
next_count_estimate
```

你可以把它理解为：

“如果未来条件按当前 forecast 走，下一周可能会达到的大致虫量水平”

注意，这只是统计预测，不是未来真实值。

---

### 3.6 如果预测模型不可用，会发生什么

系统里还有一套兜底逻辑。

如果 forecast 模型加载失败，或者分类器/回归器不可用，就会走一个启发式公式。

这套兜底规则会综合：

- `catch_trend`
- `temp_delta`
- `rh_delta`
- `pressure_mean - pressure_forecast`
- `log_catch`
- `in_tepp_window`

先算一个分数，再推一个 `next_catch_rate`，最后根据阈值判断是：

- `up`
- `stable`
- `down`

所以即使模型没有成功加载，接口仍然能给出一个趋势判断，但这个结果更像规则推断，不是严格意义上的机器学习推断。

---

### 3.7 训练数据目前的现实情况

这一点需要明确告诉组员。

当前线上 forecast 模型的元数据里写的是：

- `source = real_plus_synthetic`
- `rows_real = 2`
- `rows_synthetic = 34`

这说明目前这套预测模型虽然已经跑起来了，但真实周级数据还非常少，训练仍然高度依赖合成样本。

所以当前它更适合：

- 展示流程
- 验证接口
- 做早期演示

而不适合直接被当成高置信度的自动控制依据。

---

## 4. 当前“决策”是怎么做的

当前喷药决策的主入口是：

```text
POST /decision/weekly
```

它和 forecast 不是一个接口，也不是同一个模型。

forecast 回答的是：

```text
未来虫情可能怎么变化
```

decision 回答的是：

```text
本周应该喷不喷，喷多大范围，喷多少液量
```

---

### 4.1 决策接口的输入有哪些

当前决策接口主要使用这些输入：

- `aphid_count`
- `field_area_ha`
- `exposure_days`
- `prev_catch_rate` 或 `catch_trend`
- `t_mean`
- `rh_mean`
- `vpd_mean`
- `week_start`
- `in_tepp_window`
- `apps_so_far`
- `respect_compliance_gate`

其中最关键的是：

- 当前周虫量水平
- 相对上一周的变化
- 当前环境条件
- 当前季节位置
- 本季已经施药多少次

---

### 4.2 决策特征是怎么构造的

当前决策层构造的特征包括：

- `catch_rate`
- `log_catch`
- `catch_trend`
- `T_mean`
- `RH_mean`
- `VPD_mean`
- `doy_sin`
- `doy_cos`
- `in_tepp_window`
- `apps_so_far`

注意，这里和 forecast 最大的不同是：

当前决策模型不使用未来天气 forecast，也不直接使用 `next_count_estimate`。

也就是说，当前决策层更多是根据“当前周状态”做判断，而不是根据“未来预测结果”做判断。

---

### 4.3 决策模型输出什么

当前决策模型输出的是 `scope_class`，一共有 3 类：

- `0 = no_spray`
- `1 = boundary_band`
- `2 = full_field`

可以理解成：

1. 不喷
2. 只喷边界带
3. 全田喷施

然后系统再根据这个等级，换算出：

- `treated_fraction`
- `water_l_ha`
- `product_kg`
- `spray_l`

---

### 4.4 决策模型如果不可用，会怎么退化

如果 `tepp_demo_scope_model.pkl` 加载失败，就会退回一套 teacher rule。

这套规则的核心逻辑是：

#### 第一步：根据 `catch_rate` 做初始分级

- 如果 `catch_rate >= q85`，则判为 `2`
- 否则如果 `catch_rate >= q50`，则判为 `1`
- 否则判为 `0`

当前元数据中的阈值大致是：

- `q50 = 1.3571`
- `q85 = 2.1143`

#### 第二步：做升级判断

如果原本是 `scope_class = 1`，但同时满足：

- `catch_trend > 0.8`
- `T_mean > 14`

那就升级成：

- `scope_class = 2`

也就是说，当前 fallback 规则本质上是：

“先看当前虫量水平，再看是否正在快速上升，而且环境温度适合虫害发展”

---

### 4.5 合规闸门比模型优先级更高

这一点很关键。

无论模型还是规则先给出了什么结果，只要开启了：

```text
respect_compliance_gate = true
```

系统还会再检查两件事：

1. 当前是否在 Teppeki 施药窗口内
2. 本季是否已经施药过 1 次以上

如果不满足，就会强制改成：

```text
scope_class = 0
```

所以当前决策不是“模型说喷就喷”，而是：

```text
模型先给建议
再由合规规则最后把关
```

---

### 4.6 剂量和喷液量是怎么计算的

当前元数据里预设了：

- `scope 0 -> treated_fraction = 0.0`
- `scope 1 -> treated_fraction = 0.3`
- `scope 2 -> treated_fraction = 1.0`

以及：

- `scope 0 -> water_l_ha = 0`
- `scope 1 -> water_l_ha = 350`
- `scope 2 -> water_l_ha = 500`

药剂有效成分速率目前是：

```text
tepp_rate_kg_ha = 0.14
```

所以：

```text
product_kg = tepp_rate_kg_ha * field_area_ha * treated_fraction
spray_l = water_l_ha * field_area_ha * treated_fraction
```

这个计算不是预测出来的，而是模型先决定“喷到什么等级”，然后再按固定规则换算成剂量和喷液量。

当前演示喷头按 Hunter MP1000 Rotator Nozzle 换算：默认 `90° arc + 40 PSI + 0.21 GPM`，约 `13.25 ml/s`。所以后端还会返回 `nozzle.runtime_sec`，表示为了喷完 `spray_ml` 需要打开喷头多久。这个值只负责硬件动作换算，不会改变喷药决策本身。

---

## 5. 树莓派本地版到底做了什么

除了云端接口以外，仓库里还有一个树莓派本地版本：

```text
clients/raspberry_pi_decision/pi_weekly_decision.py
```

这个脚本的定位不是 forecast，而是：

“在树莓派本地把一周的样本聚合后，直接做喷药推荐”

它的工作流程是这样的。

### 5.1 本地采样

每次记录一个样本时，会保存：

- 时间戳
- 温度
- 湿度
- 虫量

到本地状态文件中。

### 5.2 本地周聚合

运行 `recommend` 时，脚本会把：

- 当前周样本
- 上一周样本

分别聚合成周级统计。

当前周会得到：

- `aphid_count`
- `t_mean`
- `rh_mean`

上一周会用于计算：

- `prev_catch_rate`

### 5.3 本地推荐

聚合完后，本地脚本再加载本地模型或 fallback 规则，跑出：

- `scope_class`
- `scope_name`
- `product_kg`
- `spray_l`

它的逻辑和云端 `/decision/weekly` 基本一致，只是它完全在本地计算，不依赖云端 forecast。

---

## 6. 当前系统最重要的事实

这是最值得向组员讲清楚的部分。

### 6.1 现在的“预测”和“决策”不是同一个模型

当前系统里：

- forecast 模型负责预测未来趋势
- decision 模型负责做喷药建议

它们是两层，不是一个统一模型。

---

### 6.2 决策层目前没有真正使用 forecast 输出

虽然系统已经有：

- `trend_label`
- `trend_confidence`
- `next_count_estimate`

但当前 `/decision/weekly` 并不会直接把这些 forecast 输出当作输入。

换句话说，现在系统并不是：

```text
先预测未来虫压
再根据预测结果定剂量
```

而更像是：

```text
一条链路做未来趋势预测
另一条链路按当前周状态给喷药建议
```

---

### 6.3 当前系统更像“演示版可运行流程”

目前系统已经具备：

- 数据上传
- 历史存储
- 自动读取历史
- 自动做趋势预测
- 自动做喷药建议

所以从工程流程上说，它已经是一个完整原型。

但是从模型可靠性上说，目前仍然有明显限制：

1. forecast 真实训练数据非常少
2. decision 元数据也明确写着 `Synthetic demo only`
3. 预测层和决策层还没有形成真正闭环
4. 目前还没有做长期平滑、双阈值、喷后反馈修正等慢控制逻辑

---

## 7. 给组员汇报时可以怎么讲

如果你要在组会上快速解释当前系统，可以直接用下面这段逻辑：

### 7.1 简短版

我们现在已经把系统拆成了两层：

1. 一层负责做虫情趋势预测
2. 一层负责做喷药决策

虫情预测会结合最近几天的虫量历史、环境历史和未来天气，预测下一周虫压是升、稳还是降，并估计下一周虫量。

喷药决策则主要根据当前周虫量、相对上一周的变化、环境条件、季节窗口和施药次数，输出不喷、边界带喷施或者全田喷施，并进一步换算成喷液量和药剂量。

---

### 7.2 更准确一点的说法

我们现在已经完成了“数据采集 -> 历史存储 -> 趋势预测 -> 决策输出”的基本流程，但还没有把 forecast 和 decision 融合成一个真正的慢闭环控制系统。

也就是说，当前系统更适合用来展示完整流程和验证架构，而不是直接用于高风险的全自动施药闭环。

---

## 8. 相关文件位置

如果组员想看源码，可以重点看这几个文件：

- `apps/api/container/server.py`
  主服务，包含 `/predict`、`/telemetry`、`/forecast/weekly`、`/forecast/auto`、`/decision/weekly`

- `ml/forecast/train_aphid_forecast_model.py`
  虫情 forecast 模型的训练脚本

- `apps/api/container/model/aphid_forecast_meta.json`
  当前 forecast 模型元数据

- `apps/api/container/model/tepp_demo_meta.json`
  当前 decision demo 模型元数据

- `clients/raspberry_pi_decision/pi_weekly_decision.py`
  树莓派本地周级决策脚本

---

## 9. 一句话结论

当前系统已经能做到：

```text
识别虫量 + 记录环境 + 自动预测趋势 + 输出喷药建议
```

但它目前还是：

```text
“预测层”和“决策层”并存的原型系统
而不是一个已经完全打通的自动闭环控制系统
```

如果后续要继续升级，最自然的方向就是：

把云端 forecast 的结果真正接入 decision 层，再配合趋势平滑、双阈值、日级执行窗口和喷后反馈，形成更稳健的慢控制闭环。

---

## 10. 当前 PAYG 部署环境

从 2026-04-20 开始，这个项目的线上运行环境已经切到新的 Azure Pay-As-You-Go 订阅，不再依赖之前的学生订阅。

当前线上环境如下：

- Subscription: `Azure subscription 1`
- Subscription ID: `2685e946-e7eb-4d8a-ac8c-e899199ab4b3`
- Resource Group: `rg-aphid-yolo-payg`
- ACR: `acraphidyolo9547`
- Storage Account: `staphidpayg9547`
- Container App: `aca-aphid-yolo`
- App URL: `https://aca-aphid-yolo.salmonforest-9615860e.swedencentral.azurecontainerapps.io`

当前 PAYG 存储里已经有这两张业务表：

- `iottelemetry`
- `aphidcounts`

要注意一件事：

- 旧学生订阅里的历史数据没有一起迁过来
- 迁过来的是应用、配置、部署链路和表结构
- 所以现在系统功能是延续的，但历史数据不是完全继承的

---

## 11. 当前完整部署流程

如果用最通俗的话来讲，现在这套部署流程就是：

```text
本地改代码
-> push 到 GitHub main
-> GitHub Actions 自动构建镜像
-> 自动推到 Azure Container Registry
-> 自动更新 Azure Container App
-> 自动做健康检查和 smoke test
```

### 11.1 GitHub 自动更新

当前仓库是：

```text
https://github.com/VindaOliver/PestinPeace
```

部署工作流文件是：

```text
.github/workflows/deploy_containerapp.yml
```

它的触发方式是：

- push 到 `main`
- 手动 `workflow_dispatch`

也就是说，只要我们把改动 push 到 `main`，GitHub Actions 就会自动开始部署。

---

### 11.2 GitHub Actions 现在依赖的关键变量

仓库里现在已经配置好的 Actions Variables 是：

- `ACR_NAME = acraphidyolo9547`
- `RESOURCE_GROUP = rg-aphid-yolo-payg`
- `CONTAINER_APP_NAME = aca-aphid-yolo`
- `IMAGE_REPO = aphid-yolo26`
- `AZURE_SUBSCRIPTION_ID = 2685e946-e7eb-4d8a-ac8c-e899199ab4b3`
- `AZURE_TENANT_ID = 1faf88fe-a998-4c5b-93c9-210a11d9a5c2`
- `AZURE_CLIENT_ID = 411ad807-be68-4d9c-bbe2-d99cfc655c4d`

这些值现在已经全部改成 PAYG 的配置。

---

### 11.3 Azure 自动部署现在是怎么完成的

GitHub Actions 现在通过 OIDC 登录 Azure，不是用传统的 client secret。

对应的 GitHub OIDC 服务主体已经在 PAYG 订阅里配置好了权限：

- 对资源组 `rg-aphid-yolo-payg` 有 `Contributor`
- 对 ACR `acraphidyolo9547` 有 `AcrPush`

这意味着 GitHub Actions 现在可以自动做两件事：

1. 把新镜像推到 ACR
2. 把 Container App 更新到新镜像

所以现在“GitHub 自动更新 + Azure 自动部署”这两件事都已经具备，而且已经验证成功。

---

### 11.4 一次完整部署时 GitHub Actions 会做什么

当前 workflow 的主要步骤是：

1. Checkout 仓库代码
2. 解析部署变量
3. 把网页文件同步进 Docker context
4. 检查模型文件和容器内必须文件是否齐全
5. 使用 Azure OIDC 登录
6. 构建 Docker 镜像
7. 推送镜像到 ACR
8. 更新 Azure Container App
9. 调用 `/health`
10. 调用 `/decision/weekly`
11. 调用 `/forecast/weekly`

也就是说，它不是只“发上去”，还会自动做一轮最基本的可用性验证。

---

### 11.5 最近一次成功部署记录

我已经在 PAYG 环境上实际 push 并跑通了一次完整自动部署。

最近一次成功的 workflow run 是：

- Workflow: `Build Push Deploy (Container App)`
- Commit: `dbea9a7`
- Run ID: `24674063406`
- 结果：`success`

这一条成功记录说明：

- GitHub 仓库配置是对的
- GitHub Actions 能正常触发
- Azure 登录是通的
- ACR 推镜像是通的
- Container App 更新是通的
- 三个 smoke test 是通的

---

## 12. 当前线上接口和网页是否已经指向 PAYG

这部分我已经实际检查过，可以直接给组员一个结论：

### 12.1 API 接口

下面这些接口现在在线都能正常返回：

- `GET /health`
- `POST /decision/weekly`
- `POST /forecast/weekly`

实际检查结果是：

- `/health` 返回 `200`
- `/decision/weekly` 返回 `200`
- `/forecast/weekly` 返回 `200`

并且 `/health` 里已经明确显示：

- `telemetry_table = iottelemetry`
- `aphid_count_table = aphidcounts`

这说明线上 API 现在确实已经在用 PAYG 的表。

---

### 12.2 网页入口

这里有一个很容易误解的点：

线上网页不是通过下面这种静态路径访问的：

- `/local_web_client.html`
- `/history_records.html`
- `/decision_dashboard.html`
- `/forecast_dashboard.html`
- `/telemetry_dashboard.html`

这些路径在线会返回 `404`。

真正可用的线上网页入口是下面这些 API 风格的 dashboard 路由：

- `/predict/dashboard`
- `/history/dashboard`
- `/decision/dashboard`
- `/forecast/dashboard`
- `/telemetry/dashboard`

这些路径我已经实际检查过，结果是：

- 全部返回 `200`
- 页面内部默认 API 地址都已经是 PAYG 的线上地址

所以现在更准确的说法不是“网页没部署”，而是：

```text
网页已经部署了
只是线上访问路径是 /xxx/dashboard
不是 *.html
```

---

### 12.3 给 teammate 最简单的使用说法

如果你要跟 teammate 说“现在怎么访问线上系统”，最简单可以直接说：

#### API 基础地址

```text
https://aca-aphid-yolo.salmonforest-9615860e.swedencentral.azurecontainerapps.io
```

#### 常用在线页面

- Predict Dashboard  
  `https://aca-aphid-yolo.salmonforest-9615860e.swedencentral.azurecontainerapps.io/predict/dashboard`

- History Dashboard  
  `https://aca-aphid-yolo.salmonforest-9615860e.swedencentral.azurecontainerapps.io/history/dashboard`

- Decision Dashboard  
  `https://aca-aphid-yolo.salmonforest-9615860e.swedencentral.azurecontainerapps.io/decision/dashboard`

- Forecast Dashboard  
  `https://aca-aphid-yolo.salmonforest-9615860e.swedencentral.azurecontainerapps.io/forecast/dashboard`

- Telemetry Dashboard  
  `https://aca-aphid-yolo.salmonforest-9615860e.swedencentral.azurecontainerapps.io/telemetry/dashboard`

---

## 13. 现在可以怎么理解整个状态

截至目前，最准确的总结是：

1. 系统功能还和之前基本一样
2. 运行环境已经切到 PAYG
3. 旧历史数据没有迁移过来
4. GitHub 自动部署已经恢复并验证成功
5. Grafana 接入能力已经补上
6. 线上 API 和 dashboard 现在都已经指向 PAYG 版本

如果后面有人再问“项目现在到底是在旧学生订阅里，还是在新 PAYG 里”，可以直接回答：

```text
现在正式运行的是 PAYG 环境
旧学生订阅只保留为历史背景，不再作为当前部署目标
```
