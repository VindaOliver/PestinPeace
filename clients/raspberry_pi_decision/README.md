# Raspberry Pi 本地周度决策版

这个目录是给树莓派使用的本地版本，复用了项目里现有的温度、湿度、虫子数量周度决策模型。

它适合下面这种流程：

1. 树莓派每天或每次巡检时记录一次样本。
2. 样本里至少包含 `aphid_count`、`temperature`、`humidity`。
3. 到需要做判断的时候，脚本会自动把本周数据聚合成：
   - `aphid_count` 周累计
   - `t_mean` 周均温
   - `rh_mean` 周均湿
   - `prev_catch_rate` 上周虫量速率
4. 然后在树莓派本地直接运行模型，输出 `scope_class`、`product_kg`、`spray_l`。

## 目录内容

- `pi_weekly_decision.py`
  树莓派本地运行脚本。
- `requirements.txt`
  本地 Python 依赖。
- `config.example.json`
  配置模板。
- `model/`
  本地模型文件目录。
- `data/`
  默认状态文件目录，第一次运行会自动生成 `weekly_state.json`。

## 安装

```bash
cd clients/raspberry_pi_decision
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config.example.json config.json
```

如果你没有接 DHT11/DHT22，只要在运行命令时手动传 `--temperature` 和 `--humidity` 即可。

## 常用命令

### 1. 记录一个样本

手动输入温湿度：

```bash
python3 pi_weekly_decision.py --config config.json add-sample \
  --aphid-count 3 \
  --temperature 19.6 \
  --humidity 72.4
```

从 DHT22 读取：

```bash
python3 pi_weekly_decision.py --config config.json add-sample \
  --aphid-count 3 \
  --sensor dht22 \
  --pin 4
```

### 2. 查看当前状态

```bash
python3 pi_weekly_decision.py --config config.json show-state
```

### 3. 生成本周建议

```bash
python3 pi_weekly_decision.py --config config.json recommend
```

如果你想边记录本次样本边出建议：

```bash
python3 pi_weekly_decision.py --config config.json recommend \
  --record-current \
  --aphid-count 4 \
  --temperature 20.1 \
  --humidity 70.5
```

### 4. 记录已经施药一次

```bash
python3 pi_weekly_decision.py --config config.json mark-applied
```

### 5. 新季节开始时重置计数

```bash
python3 pi_weekly_decision.py --config config.json reset-season
```

## 输出说明

- `scope_class`
  - `0`: 不喷
  - `1`: 边界带喷施
  - `2`: 全田喷施
- `product_kg`
  推荐药剂量。
- `spray_l`
  推荐喷液量。
- `weekly_summary`
  本周与上周聚合后的中间结果，方便你核对模型输入。

## 注意

- 这个目录复用的是当前仓库里的 demo 模型，不是新的训练模型。
- 默认会遵守合规门控：
  - 不在施药窗口内时强制输出 `scope_class = 0`
  - `apps_so_far >= 1` 时强制输出 `scope_class = 0`
- `aphid_count` 现在默认按本周样本求和。如果你未来有更精确的诱捕板或图像计数流程，可以继续替换样本来源，但不需要改模型输入结构。
