# 答辩资料包说明

这个文件夹是我帮你整理好的答辩资料包。
目标是让你在当前部署项目目录里，直接拿到架构图、YOLO 训练结果和部署信息，不用再来回切换两个仓库。

## 文件夹结构

- `architecture/`
  - 当前 Azure 架构图
  - 可编辑版本
- `yolo_training/`
  - YOLO 双类训练结果图
  - aphid / slug 准确率与 mAP 数据
  - 混淆矩阵和 PR/F1 曲线
- `deployment/`
  - 当前 Azure PAYG 部署摘要

## 你答辩时最建议先用的内容

### 1. 架构图

先看：

- [architecture/azure_architecture_defense.png](C:/Users/Amour/Desktop/UCL%20IoT/design%20sensor%20system/Website/archive%20(2)/defense_assets/architecture/azure_architecture_defense.png)

如果你想自己调位置或改字：

- [architecture/azure_architecture_defense_editable.svg](C:/Users/Amour/Desktop/UCL%20IoT/design%20sensor%20system/Website/archive%20(2)/defense_assets/architecture/azure_architecture_defense_editable.svg)
- [architecture/azure_architecture_defense_editable.mmd](C:/Users/Amour/Desktop/UCL%20IoT/design%20sensor%20system/Website/archive%20(2)/defense_assets/architecture/azure_architecture_defense_editable.mmd)

### 2. YOLO 训练结果

最重要的是这几份：

- [yolo_training/training_dashboard.png](C:/Users/Amour/Desktop/UCL%20IoT/design%20sensor%20system/Website/archive%20(2)/defense_assets/yolo_training/training_dashboard.png)
- [yolo_training/results.png](C:/Users/Amour/Desktop/UCL%20IoT/design%20sensor%20system/Website/archive%20(2)/defense_assets/yolo_training/results.png)
- [yolo_training/confusion_matrix.png](C:/Users/Amour/Desktop/UCL%20IoT/design%20sensor%20system/Website/archive%20(2)/defense_assets/yolo_training/confusion_matrix.png)
- [yolo_training/results_summary.json](C:/Users/Amour/Desktop/UCL%20IoT/design%20sensor%20system/Website/archive%20(2)/defense_assets/yolo_training/results_summary.json)
- [yolo_training/DUAL_CLASS_TRAINING_SUMMARY_CN.md](C:/Users/Amour/Desktop/UCL%20IoT/design%20sensor%20system/Website/archive%20(2)/defense_assets/yolo_training/DUAL_CLASS_TRAINING_SUMMARY_CN.md)

这次答辩统一使用 aphid + slug 双类模型结果。最关键的整体指标是：

- 最佳轮次：`Epoch 53`
- 提前停止：`true`
- `Precision = 0.83412`
- `Recall = 0.78233`
- `mAP50 = 0.83499`
- `mAP50-95 = 0.43960`

按类别拆开看：

- `aphid`: `mAP50 = 0.93171`, `mAP50-95 = 0.49672`
- `slug`: `mAP50 = 0.73620`, `mAP50-95 = 0.38304`

数据量：

- `train`: 2532 张
- `valid`: 235 张
- `test`: 116 张
- aphid 标注框：19818
- slug 标注框：1026

### 3. 当前部署摘要

看这份：

- [deployment/CURRENT_DEPLOYMENT_SUMMARY_CN.md](C:/Users/Amour/Desktop/UCL%20IoT/design%20sensor%20system/Website/archive%20(2)/defense_assets/deployment/CURRENT_DEPLOYMENT_SUMMARY_CN.md)

## 这些文件是从哪里来的

这个资料包里的内容来自两个地方：

1. 当前部署仓库  
   `Website/archive (2)`
2. 最新 aphid + slug 双类 YOLO 训练目录  
   `C:\Users\Amour\Desktop\UCL IoT\trip\6e723\aphid-slug-yolo26\runs\train\yolo26_aphid_slug_baseline_960`

我已经把答辩最常用的图片和数据复制到了这里，所以你后面直接从这个文件夹拿就行。

## 最实用的答辩顺序

如果你临近答辩，只按这个顺序看：

1. 架构图  
2. `training_dashboard.png`
3. `results.png`
4. `confusion_matrix.png`
5. 当前部署摘要

## 一句话版

这个文件夹就是你现在的答辩素材总入口。
