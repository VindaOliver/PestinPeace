# 答辩资料包说明

这个文件夹是我帮你整理好的答辩资料包。
目标是让你在当前部署项目目录里，直接拿到架构图、YOLO 训练结果和部署信息，不用再来回切换两个仓库。

## 文件夹结构

- `architecture/`
  - 当前 Azure 架构图
  - 可编辑版本
- `yolo_training/`
  - YOLO 训练结果图
  - 准确率与 mAP 数据
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

你这次训练最关键的指标是：

- 最佳轮次：`Epoch 88`
- `Precision = 0.88549`
- `Recall = 0.89288`
- `mAP50 = 0.93117`
- `mAP50-95 = 0.48830`

### 3. 当前部署摘要

看这份：

- [deployment/CURRENT_DEPLOYMENT_SUMMARY_CN.md](C:/Users/Amour/Desktop/UCL%20IoT/design%20sensor%20system/Website/archive%20(2)/defense_assets/deployment/CURRENT_DEPLOYMENT_SUMMARY_CN.md)

## 这些文件是从哪里来的

这个资料包里的内容来自两个地方：

1. 当前部署仓库  
   `Website/archive (2)`
2. 之前的 YOLO 训练目录  
   `archive (2)/runs/train/yolo26_aphids_tf_env_gpu_full`

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
