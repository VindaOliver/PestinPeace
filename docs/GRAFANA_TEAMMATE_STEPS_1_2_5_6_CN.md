# Grafana 同伴操作说明（步骤 1、2、5、6）

这份文档是给负责 Grafana 侧操作的 teammate 写的。

它默认以下事情已经由别人完成：

- 第 3 步：Azure 里的 Service Principal 已经创建好
- 第 4 步：`Monitoring Reader` 权限已经配好

你这边主要负责：

- 第 1 步：进入真正的 Grafana UI
- 第 2 步：添加 Azure Monitor 数据源
- 第 5 步：把 Azure 信息填进去并 `Save & Test`
- 第 6 步：做第一轮查询验证

---

## 1. 先说结论

你现在不用再去 Azure 里创建新的账号或权限。

你要做的事情很简单：

1. 打开 Grafana 实例
2. 添加 `Azure Monitor` 数据源
3. 选择 `Service Principal`
4. 填入当前 PAYG 环境的 Azure 信息
5. 点 `Save & Test`
6. 用 Log Analytics 表跑一两条简单查询确认成功

---

## 2. 当前项目使用的是哪套 Azure 环境

当前正式环境不是旧学生订阅，而是新的 PAYG。

当前有效环境：

- Subscription Name: `Azure subscription 1`
- Subscription ID: `2685e946-e7eb-4d8a-ac8c-e899199ab4b3`
- Tenant ID: `1faf88fe-a998-4c5b-93c9-210a11d9a5c2`
- Resource Group: `rg-aphid-yolo-payg`
- Container App: `aca-aphid-yolo`
- Log Analytics Workspace: `workspace-rgaphidyolopaygK1ST`

---

## 3. 第 1 步：进入真正的 Grafana UI

你现在不要停留在 Grafana Cloud Portal 管理页。

正确做法是：

1. 登录 Grafana Cloud
2. 在左侧找到你们的 stack
3. 点击 `Open Grafana`
4. 进入类似下面这种页面：

```text
https://xxx.grafana.net
```

只有进到这个页面以后，后面的数据源配置才是有效的。

---

## 4. 第 2 步：添加 Azure Monitor 数据源

进入 Grafana UI 后，按下面路径操作：

1. 左侧菜单
2. `Connections` 或 `Data sources`
3. 点击 `Add data source`
4. 搜索 `Azure Monitor`
5. 点击进入

到这里为止，你就进入了数据源配置页。

---

## 5. 第 5 步：要填什么

在 Azure Monitor 数据源配置页，核心字段这样填：

- Authentication: `Service Principal`
- Tenant ID: `1faf88fe-a998-4c5b-93c9-210a11d9a5c2`
- Client ID: `49e3878a-aff7-4afe-9e84-0ed9ea46273f`
- Subscription ID: `2685e946-e7eb-4d8a-ac8c-e899199ab4b3`

`Client Secret` 不写进仓库文档里。

如果你在实际配置时需要它，请直接向项目负责人索取当前有效的 secret。

一句话记忆就是：

```text
Tenant / Client / Subscription 可以写在文档里，
Client Secret 不放进仓库。
```

---

## 6. Save & Test 成功后说明什么

如果你点了 `Save & Test` 并且成功，说明这些事情已经打通了：

1. Grafana 已经能用 Service Principal 登录 Azure
2. Grafana 已经能读当前 PAYG 订阅下的 Azure Monitor 数据
3. 你后面可以开始做 Logs / Metrics 面板了

这一步成功以后，说明第 5 步已经完成。

---

## 7. 第 6 步：第一次应该怎么测

建议你先不要一上来做复杂 dashboard。

先做两类最简单的验证。

### 7.1 先测 Logs

优先试这几个表：

- `ContainerAppConsoleLogs_CL`
- `ContainerAppSystemLogs_CL`
- `AppRequests`
- `AppTraces`

这些是当前 PAYG 环境里已经可以查到的 Azure Monitor / Log Analytics 数据。

你可以先做很简单的查询，比如：

```kusto
ContainerAppConsoleLogs_CL
| take 20
```

或者：

```kusto
AppRequests
| take 20
```

如果能正常返回数据，就说明 Grafana 到 Azure Monitor Logs 这条链路已经通了。

---

### 7.2 再测 Metrics

如果你想确认资源指标也能查，可以在 Azure Monitor 数据源里尝试：

- Container App 相关指标
- 资源组里的基础指标

这一步主要是确认：

```text
Grafana 不只是能读日志，
也能读 Azure Monitor 的指标数据。
```

---

## 8. 现在不能直接查什么

这个点非常重要，别踩坑。

现在虽然 Grafana 已经可以连 Azure Monitor，但它还**不能直接查**下面这两张 Azure Table：

- `iottelemetry`
- `aphidcounts`

原因不是权限没配，而是因为这两张表现在还在 Azure Table Storage 里，不在 Log Analytics 里。

所以当前状态是：

- 能直接查：Azure Monitor / Log Analytics 里的日志和指标
- 不能直接查：Azure Table 里的业务表数据

如果你要问一句最简单的话：

```text
Grafana 现在能直接看云平台日志，
但还不能直接看业务表本身。
```

---

## 9. 如果 Save & Test 失败，先查什么

建议按这个顺序排查：

1. 先确认你是不是在真正的 `https://xxx.grafana.net` 页面
2. 确认 Authentication 选的是 `Service Principal`
3. 确认 Tenant ID / Client ID / Subscription ID 没填错
4. 确认拿到的 `Client Secret` 是当前有效版本
5. 确认不是把旧学生订阅的值拿来填了

当前有效的订阅一定是：

```text
2685e946-e7eb-4d8a-ac8c-e899199ab4b3
```

不是旧学生订阅。

---

## 10. 给 teammate 最短操作版

如果你只想看最短版，就按这个来：

1. 打开 `https://xxx.grafana.net`
2. `Connections -> Add data source -> Azure Monitor`
3. Authentication 选 `Service Principal`
4. 填：
   - Tenant ID: `1faf88fe-a998-4c5b-93c9-210a11d9a5c2`
   - Client ID: `49e3878a-aff7-4afe-9e84-0ed9ea46273f`
   - Subscription ID: `2685e946-e7eb-4d8a-ac8c-e899199ab4b3`
   - Client Secret: 向负责人索取
5. 点 `Save & Test`
6. 先查：
   - `ContainerAppConsoleLogs_CL`
   - `AppRequests`

---

## 11. 进一步阅读

如果你想看更完整的当前状态，可以继续看：

- `docs/GRAFANA_PAYG_QUICKSTART_BILINGUAL.md`
- `docs/PREDICTION_AND_DECISION_WORKFLOW_CN.md`
- `docs/STUDENT_SUBSCRIPTION_TO_PAYG_HANDOVER_CN.md`
