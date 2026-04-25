# Aphid + Slug 双类模型接入报告

## 实施状态

这份文档最初是接入方案，现在作为实施报告和决策记录保留。

当前状态：

- Phase 1 后端双类字段已经落地。
- Phase 2 页面与 Grafana 文档已经切到双类口径。
- `/predict` 会返回 `aphid_count`、`slug_count`、`total_count`、`class_breakdown`。
- `count = aphid_count` 继续保留，用来兼容旧接口、旧图表和旧测试。
- forecast / trend / decision 仍然只使用 `aphid_count`，不会把 slug 混入喷药决策。
- 当前单次请求按单张图片记录：`images_in_round = 1`，`aggregation_mode = single_image`。

下面保留原方案内容，作为为什么这样接入的背景说明。

这份文档回答一个很实际的问题：

**我们现在训练出的 `aphid + slug` 双类 YOLO 模型，怎样才能安全地接到当前线上系统里？**

先给结论：

- **如果只是为了演示识别框**，可以直接替换模型文件。
- **如果要让整套系统继续正确记录历史、做趋势预测、做喷药决策**，不能直接无改动替换。
- 我更推荐的方案是：
  **保留现有 aphid 业务主线不变，把 slug 作为新增观测类别接入。**

这样做的好处是：

- 改动最小
- 不会把现在的 `forecast / decision / trend` 逻辑弄乱
- 适合课程项目、答辩演示和后续逐步扩展

---

## 1. 当前现状

当前系统的核心假设还是：

- `/predict` 识别到的所有框，都会被当成 `aphid` 数量
- 表 `aphidcounts` 记录的也是蚜虫数量
- `/predict/trend`
- `/forecast/weekly`
- `/forecast/auto`
- `/decision/weekly`

这些接口默认都建立在“输入是 aphid count”这个前提上。

而双类模型的输出会变成：

- `aphid`
- `slug`

如果我们直接把双类模型换进去，但不改代码，系统会把：

**aphid + slug 的总框数**

当成：

**aphid 数量**

这会让：

- 趋势图失真
- 虫量历史失真
- forecast 失真
- decision 失真

所以“模型可加载”不等于“系统可正确使用”。

---

## 2. 代码里已经具备的有利条件

这次对照现有代码后，有几个好消息：

1. `/predict` 已经返回每个框的：

- `class_id`
- `class_name`
- `confidence`
- `bbox_xyxy`

也就是说，接双类模型后，系统本来就会拿到类别信息，不需要从零重写推理输出。

2. 模型类别名不是写死的，而是运行时从模型读取：

- `names = r0.names`

这说明：

- 只要替换成双类 `best.pt`
- 响应里的 `class_name` 就会自动出现 `slug`

3. 当前真正缺的不是“识别双类”，而是：

- **聚合层没有按类别分开统计**
- **写表层没有按类别保存**
- **趋势/预测/决策层仍然假设只有 aphid**

所以这次改造重点应该放在：

- 聚合逻辑
- 存储字段
- 兼容策略

而不是重新设计整套推理流程。

---

## 3. 推荐目标

推荐把系统升级成下面这个语义：

- `aphid_count`: 继续作为预测和决策主线输入
- `slug_count`: 作为新增类别单独记录和展示
- `total_count`: 只做展示，不参与 aphid forecast / decision

也就是说：

- **喷药建议仍然只跟 aphid 有关**
- **slug 先作为监测和展示能力**

这很适合当前项目阶段，因为你现有的周预测和决策模型都是 aphid 逻辑，不需要被 slug 重新定义。

---

## 4. 我建议的实施方案

### Phase 1：最小风险接入

这一阶段的目标是：

**先让双类模型能安全替换，不破坏现有系统主线。**

#### 4.1 修改 `/predict` 的聚合逻辑

当前问题：

- 现在 `count = len(detections)`
- 所有检测框都被当成 aphid

推荐做法：

1. 保留现有 `detections` 输出不变
2. 在 `/predict` 内部新增一次按 `class_name` 的聚合
3. 生成：

- `aphid_count`
- `slug_count`
- `total_count`
- `class_breakdown`

推荐响应示例：

```json
{
  "device_id": "demo-trap-001",
  "aphid_count": 12,
  "slug_count": 2,
  "total_count": 14,
  "count": 12,
  "count_mean": 12,
  "class_breakdown": {
    "aphid": 12,
    "slug": 2
  }
}
```

这里最关键的一点是：

- **不要再让 `count` 代表所有检测框**
- **让 `count` 临时兼容为 `aphid_count`**

这样现有下游逻辑才不会被污染。

#### 4.2 修改写表逻辑

当前 `aphidcounts` 表不应该再只写一个模糊的 `count`。

推荐新增字段：

- `aphid_count`
- `slug_count`
- `total_count`
- `class_breakdown_json`

为了兼容当前系统：

- `count = aphid_count`
- `count_mean = aphid_count`

这一步是本方案的核心兼容策略。

注意：

- Azure Table Storage 没有原生 JSON 类型
- 所以 `class_breakdown_json` 应该是 **string 列**
- 建议写法：

```python
json.dumps({"aphid": 12, "slug": 2})
```

读取时再：

```python
json.loads(...)
```

#### 4.3 旧历史数据兼容

这一步非常重要，不能漏。

因为当前 `aphidcounts` 表里已经存在很多旧行，它们只有：

- `count`

没有：

- `aphid_count`
- `slug_count`
- `total_count`

所以读取层必须先做兼容：

```python
aphid_count = row.get("aphid_count", row.get("count", 0))
slug_count = row.get("slug_count", 0)
total_count = row.get("total_count", aphid_count + slug_count)
```

这样可以保证：

- 老数据还能用
- 新数据又能支持双类

#### 4.4 修改 `/grafana/aphidcounts`

当前这个接口名字虽然叫 `aphidcounts`，但可以继续保留。

推荐改成返回：

- `aphid_count`
- `slug_count`
- `total_count`
- `count`
- `count_mean`
- `class_breakdown`

这样 Grafana 可以同时画：

- aphid trend
- slug trend
- total detections

#### 4.5 修改 `/predict/trend`

当前趋势逻辑应该显式只使用：

- `aphid_count`

而不是 `count` 的旧模糊语义。

读取时建议直接复用 §4.3 的 fallback 逻辑，也就是：

- 先读 `aphid_count`
- 如果旧行没有这个字段，再退回读 `count`

目标是确保：

- aphid 趋势仍然只反映蚜虫
- slug 不会污染 aphid 的趋势分析

#### 4.6 保持 forecast / decision 暂时只看 aphid

这一阶段不建议把 slug 直接并入：

- `/forecast/weekly`
- `/forecast/auto`
- `/decision/weekly`

原因很简单：

- 这些接口目前都是真正的 aphid 业务逻辑
- 如果硬把 slug 混进去，系统含义会变得不清楚

当前最稳的做法是：

- `aphid_count` 继续驱动预测与决策
- `slug_count` 只做监测与展示

#### 4.7 同步更新训练配置文件

当前系统仓库里的 `ml/yolo/data.yaml` 已经同步为双类配置，并会和训练脚本一起进入 repo。

如果以后要在当前系统仓库里做：

- 重训
- 评估
- 数据集说明

这个 `data.yaml` 需要继续保持双类配置：

- `0: aphid`
- `1: slug`

**这一步不会影响线上 API 立刻推理，只是为了让后续训练、评估和仓库配置保持一致。**

---

## 5. Phase 2：前端与展示升级

这一阶段的目标是：

**让系统在页面和 Grafana 上真正展示“双类能力”。**

#### 5.1 修改识别页面

在 `/predict/dashboard` 或本地识别页上新增：

- `Aphid count`
- `Slug count`
- `Total detections`

不要只显示一个总数。

#### 5.2 修改 Grafana

建议增加 3 类图：

- aphid 每日数量
- slug 每日数量
- aphid vs slug 对比图

#### 5.3 修改历史页

历史页面里如果展示每次记录，建议也加：

- `aphid_count`
- `slug_count`

这样答辩时能更直观证明系统已经从单类升级成双类。

#### 5.4 修改 Raspberry Pi 客户端提示语

这一条容易被忽略，但很值得顺手修。

目前树莓派客户端里有类似：

- `Detected aphids: ...`

这样的硬编码提示语。

如果换成双类模型，但不改这里，日志会“说谎”。

推荐改成：

- `Detected aphids: X`
- `Detected slugs: Y`
- `Total detections: Z`

或者至少改成更中性的：

- `Detections: ...`

---

## 6. Phase 3：业务逻辑扩展（可选）

这一阶段不是当前必须做的。

只有在你以后真想把 slug 也纳入决策系统时，才建议继续做。

例如：

- 新建 `slug trend`
- 新建 `slug forecast`
- 新建 slug 专属阈值或治理建议

但这已经不是“安全替换模型”的范围了，而是“扩展业务规则”的新项目。

对于当前课程项目，我不建议现在就做太大。

---

## 7. 推荐的数据口径

为了避免系统内部再次混乱，我建议统一成下面这个口径：

- `aphid_count`: 蚜虫数量
- `slug_count`: 蛞蝓数量
- `total_count`: 所有检测框之和
- `count`: 兼容字段，等于 `aphid_count`
- `count_mean`: 兼容字段，等于 `aphid_count`
- `class_breakdown_json`: 字符串列，存 JSON 文本

一句话说：

**旧系统里所有依赖 `count` 的地方，暂时都把它视为 `aphid_count`。**

这是当前最低成本、最不容易出错的做法。

---

## 8. 当前双类模型结果说明

当前双类 baseline 结果来源于训练目录：

`C:\Users\Amour\Desktop\UCL IoT\trip\6e723\aphid-slug-yolo26\runs\train\yolo26_aphid_slug_baseline_960`

最终 `best.pt` 的 standalone validation 大致是：

- overall `mAP50-95 = 0.440`
- aphid `mAP50-95 = 0.497`
- slug `mAP50-95 = 0.383`

这说明：

- 作为课程项目和答辩展示，已经够用
- aphid 表现明显比 slug 更好
- slug 还可以继续通过重采样或二阶段训练提升

要注意：

- 这些数字来自双类训练项目目录
- 当前 `defense_assets/yolo_training/` 已经同步为这批双类训练结果

所以如果后面要给队友或老师看，最好明确说明指标来源，避免和旧单类结果混淆。

---

## 9. 我认为最合理的落地顺序

推荐按这个顺序做：

1. 修改 `/predict` 的类别聚合逻辑
2. 修改 `aphidcounts` 写表字段
3. 修改读取层，对旧历史行加兼容 fallback
4. 修改 `/grafana/aphidcounts`
5. 修改 `/predict/trend` 只读 `aphid_count`
6. 确认 `ml/yolo/data.yaml` 保持双类配置
7. 增加一条 mixed-class smoke test
8. 运行 smoke test，完成本地接口验证
9. 替换 `best.pt`
10. 最后修改前端和树莓派显示

这个顺序的好处是：

- 每一步都能测
- 业务语义不会中途乱掉
- 如果中间发现问题，也容易回滚

---

## 10. 验收标准

我建议把“接入成功”定义成下面这些条件都满足：

1. `/predict` 返回：

- `aphid_count`
- `slug_count`
- `total_count`

2. `aphidcounts` 表每条新记录都包含：

- `aphid_count`
- `slug_count`
- `total_count`

3. 老历史记录在没有 `aphid_count` 字段时，也能被正确读取

4. `/predict/trend` 的趋势和 aphid 数量一致，不受 slug 干扰

5. `/forecast/weekly` 和 `/decision/weekly` 的输入语义仍然清晰，仍然只使用 aphid count

6. 页面能看到：

- aphid 数
- slug 数
- 总数

7. Grafana 能单独画出 aphid 与 slug 的曲线

8. 至少有一条 smoke test 覆盖 mixed-class 响应

9. Raspberry Pi 客户端日志或终端输出能区分：

- `aphid_count`
- `slug_count`
- `total_count`

---

## 11. 一句话结论

**我不建议把双类模型直接无改动塞进当前系统。**

**我建议先做一层最小兼容改造：把 aphid 和 slug 分开计数，保留 aphid 作为预测与决策主线，然后再替换模型。**

这是当前风险最低、逻辑最清楚、也最适合课程项目的做法。
