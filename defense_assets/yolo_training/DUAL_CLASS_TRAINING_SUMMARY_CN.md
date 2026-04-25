# Aphid + Slug 双类 YOLO 训练摘要

这份摘要用于答辩展示，指标来自：

`C:\Users\Amour\Desktop\UCL IoT\trip\6e723\aphid-slug-yolo26\runs\train\yolo26_aphid_slug_baseline_960`

## 数据集规模

- `train`: 2532 张图片
- `valid`: 235 张图片
- `test`: 116 张图片
- aphid 标注框：19818
- slug 标注框：1026
- 总标注框：20844

## 最佳模型指标

- 最佳轮次：`Epoch 53`
- 目标训练轮次：`100`
- 实际记录轮次：`83`
- 提前停止：`true`
- Overall Precision：`0.83412`
- Overall Recall：`0.78233`
- Overall mAP50：`0.83499`
- Overall mAP50-95：`0.43960`

## 按类别拆分

| Class | Instances | Precision | Recall | F1 | mAP50 | mAP50-95 |
|---|---:|---:|---:|---:|---:|---:|
| aphid | 1867 | 0.84408 | 0.92180 | 0.88123 | 0.93171 | 0.49672 |
| slug | 67 | 0.82434 | 0.64179 | 0.72170 | 0.73620 | 0.38304 |

## 答辩时怎么解释

这个模型已经从单类 aphid 升级到 aphid + slug 双类识别。aphid 的数据量明显更多，所以 aphid 指标更稳定；slug 样本较少，因此 mAP50-95 较低，但已经能支持“是否出现 slug”和基础数量统计。

