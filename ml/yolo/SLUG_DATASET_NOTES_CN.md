# Slug 数据集说明

这份说明用于答辩和后续维护，解释为什么系统现在支持 `aphid + slug` 双类检测，以及 slug 类别目前的限制。

## 当前类别

`ml/yolo/data.yaml` 当前类别是：

```yaml
names:
  0: aphid
  1: slug
```

业务逻辑上：

- `aphid_count` 是趋势预测和喷药决策主输入。
- `slug_count` 是新增监测类别，先用于展示和记录。
- `total_count = aphid_count + slug_count` 只用于展示双类总量。

## 数据量差异

当前合并训练集大致规模：

- train: 2532 张
- valid: 235 张
- test: 116 张
- aphid 标注框: 19818
- slug 标注框: 1026

这意味着 slug 的样本量明显少于 aphid。模型能识别 slug，但 slug 指标通常会低于 aphid，这是合理现象，不代表系统接入失败。

## 为什么 slug 表现可能低一些

主要原因：

- slug 标注框数量比 aphid 少很多。
- slug 在图像中的姿态、大小、背景变化可能更大。
- aphid 是主线任务，之前已有更多训练和验证积累。
- 如果 slug 图片来自不同来源，光照、拍摄距离、背景分布可能和 aphid 数据不完全一致。

## 当前工程取舍

为了不破坏已有系统，当前做法是：

- 不把 slug 混进 aphid 决策阈值。
- 不让 `total_count` 直接驱动喷药建议。
- 在 API、Azure Table、Dashboard、Grafana 中保留 slug 作为可见的监测信号。

这适合课程项目和答辩，因为它既展示了模型扩展能力，又避免了“新增类别改变喷药决策口径”的风险。

## 后续提升方向

如果后续要让 slug 也参与决策，可以按这个顺序做：

1. 增加 slug 样本，尤其是当前设备视角下的真实图片。
2. 单独评估 slug 的 precision、recall、mAP。
3. 给 slug 建立独立阈值，不直接复用 aphid 阈值。
4. 在 `decisionhistory` 中区分 aphid-driven 和 slug-driven decision。
5. 更新 Grafana 和 API 文档，明确两类害虫的不同业务意义。

