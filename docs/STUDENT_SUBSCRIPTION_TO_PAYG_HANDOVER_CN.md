# 从旧学生订阅切到当前 PAYG 的交接说明

这份文档是专门写给之前一直在用旧 `Azure for Students` 订阅的人看的。

目的只有一个：

```text
让你不用重新理解整个项目，
也能知道现在该连哪里、看哪里、改哪里。
```

---

## 1. 先说结论

现在这个项目已经不再以旧学生订阅作为正式运行环境。

当前正式使用的是新的 Azure Pay-As-You-Go 环境。

也就是说：

- 线上服务已经切到 PAYG
- GitHub 自动部署已经切到 PAYG
- Azure 资源已经切到 PAYG
- 旧学生订阅现在只算历史背景，不再是当前部署目标

---

## 2. 什么东西变了

最重要的变化有 4 个：

### 2.1 订阅变了

旧的：

- `Azure for Students`

现在新的：

- `Azure subscription 1`
- Subscription ID: `2685e946-e7eb-4d8a-ac8c-e899199ab4b3`

---

### 2.2 Azure 资源名字变了

现在应该认这套资源：

- Resource Group: `rg-aphid-yolo-payg`
- ACR: `acraphidyolo9547`
- Storage Account: `staphidpayg9547`
- Container App: `aca-aphid-yolo`

如果你看到旧的这些名字：

- `rg-aphid-yolo-se`
- `acraphidyolo2498`
- `staphid25021201`

那就是旧学生订阅时代的资源，不是当前正式环境。

---

### 2.3 线上地址要用新的

当前正式的 Base URL 是：

```text
https://aca-aphid-yolo.salmonforest-9615860e.swedencentral.azurecontainerapps.io
```

以后给别人接口地址、测试地址、网页地址，都应该以这个为准。

---

### 2.4 GitHub 自动部署现在也跟着新环境走

现在仓库的 GitHub Actions 已经改成指向 PAYG 资源。

也就是说：

```text
git push 到 main
-> GitHub Actions 自动跑
-> 镜像推到新的 ACR
-> 部署到新的 Container App
```

这条链路已经实际验证成功了。

---

## 3. 什么东西没变

从“系统功能”角度看，很多东西其实没变：

- `/predict` 还是做虫子识别
- `/telemetry` 还是收温湿度等传感器数据
- `/forecast/weekly` 和 `/forecast/auto` 还是做虫情趋势预测
- `/decision/weekly` 还是做喷药建议

也就是说：

```text
项目功能基本延续了之前那套，
只是运行底座换成了 PAYG。
```

---

## 4. 有一个重要区别：旧历史数据没有一起迁移

这点一定要讲清楚。

迁过来的主要是：

- 应用服务
- 部署配置
- GitHub Actions
- Azure 资源结构
- 表结构
- 文档和网页默认地址

没有完整迁过来的，是旧学生订阅里的历史数据。

所以现在更准确的说法是：

```text
应用和环境迁过来了，
旧历史数据没有完整继承。
```

---

## 5. 现在还能用哪些表

PAYG 存储里当前已经有这两张业务表：

- `iottelemetry`
- `aphidcounts`

这说明现在：

- 传感器数据还是写这两张表
- 虫量记录还是写这两张表
- `/health` 也已经能返回它们

所以“表还在不在”这个问题，可以直接回答：

```text
在，而且已经在新的 PAYG 订阅里。
```

---

## 6. 现在在线页面该怎么进

这里非常容易踩坑。

线上不是访问这些：

- `/local_web_client.html`
- `/history_records.html`
- `/decision_dashboard.html`
- `/forecast_dashboard.html`
- `/telemetry_dashboard.html`

这些静态路径在线会返回 `404`。

真正应该访问的是下面这些路由：

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

一句话记忆：

```text
线上走 /xxx/dashboard
不是走 *.html
```

---

## 7. 现在怎么判断自己是不是还在用旧环境

如果你不确定自己连的是旧环境还是新环境，可以看这几件事：

### 看 Base URL

如果不是：

```text
https://aca-aphid-yolo.salmonforest-9615860e.swedencentral.azurecontainerapps.io
```

那你大概率不是在用当前正式环境。

### 看资源组

如果不是：

```text
rg-aphid-yolo-payg
```

那也不是当前正式环境。

### 看 GitHub Actions 变量

如果你看到的不是下面这些值：

- `ACR_NAME = acraphidyolo9547`
- `RESOURCE_GROUP = rg-aphid-yolo-payg`
- `CONTAINER_APP_NAME = aca-aphid-yolo`
- `AZURE_SUBSCRIPTION_ID = 2685e946-e7eb-4d8a-ac8c-e899199ab4b3`

那说明你看到的仍然不是现在这套 PAYG 配置。

---

## 8. 你现在应该看哪几份文档

如果你之前一直在用旧学生订阅，我建议你现在直接看这几份：

1. `docs/STUDENT_SUBSCRIPTION_TO_PAYG_HANDOVER_CN.md`
   - 先看这份，解决“现在到底换到哪里了”

2. `docs/PREDICTION_AND_DECISION_WORKFLOW_CN.md`
   - 解决“当前系统整体怎么工作”

3. `docs/GITHUB_ACTIONS_SETUP.md`
   - 解决“现在怎么部署”

4. `docs/GRAFANA_PAYG_QUICKSTART_BILINGUAL.md`
   - 解决“现在怎么接 Grafana”

---

## 9. 最短交接话术

如果你要把这件事一句话告诉 teammate，可以直接这么说：

```text
项目现在已经从旧学生订阅切到新的 PAYG 订阅。
API、网页入口、GitHub 自动部署和 Azure 资源都已经切过去了。
功能基本和以前一样，但旧历史数据没有完整迁移。
以后统一使用新的 PAYG Base URL 和新的 Azure 资源名。
```
