# multi_timeframe 数据层引用规范（防前视铁律）

> 版本：v1.0（2026-10-22）｜适用：所有读取 `export_package/data/multi_timeframe/{period}/{code}.csv` 的代码
> 依据：freqtrade / backtesting.py / LEAN / vn.py / StockSharp 五处官方文档互证（方案 V1.2 第 2.4 节 §25-31）；本规范配套 `scripts/lookahead_check.py` 实证（2026-10-22 报告：直引 100% 命中前视、平移 0 命中）

## 1. 数据层事实

| 周期目录 | 来源 | label 语义 | 周期时长 delta | 闭合时间 |
|---|---|---|---|---|
| daily_year | 日线 YE 重采样 | bin 左端点（前一年 12-31） | 1 年（365/366 天，数据自推导） | label + 1 年 |
| daily_quarter | 日线 QE 重采样 | bin 左端点 | ~3 个月（数据自推导） | label + delta |
| daily_month | 日线 ME 重采样 | bin 左端点（月初） | ~1 个月（数据自推导） | label + delta |
| daily_week | 日线 W 重采样 | bin 左端点（周一） | 7 天 | label + 7 天 |
| min60 / min30 / min15 | 5min 重采样 | 聚合窗口起点 | 60/30/15 分钟 | label + delta |

**关键语义**：`time` 列是**周期起点标签**（label="left"），该 bar 的 OHLCV 是**整个周期**的聚合结果，闭合于 `label + period_delta`。CSV 中记录的未闭合 bar 值是"截至数据末端的最终值"——**在盘中按标签直引它，会看到未来数据**。

## 2. 三条铁律（硬约束）

### 铁律 1：引用必须平移（date_merge 写法）
合并大周期列到小周期/决策行时，**必须**执行：

```python
# freqtrade 官方写法（方案 §27）：
#   平移大周期 bar 的标签，使其"可见时间"= 闭合时间，再 left join
inf["date_merge"] = inf["time"] + inf_period_delta      # 平移一个周期
df = df.merge(inf, left_on="t", right_on="date_merge", how="left")
df = df.ffill()                                          # 前向填充使大周期值逐行可见
```

禁止：`df.merge(inf, left_on="t", right_on="time")`（按原标签直引 = 前视）。

### 铁律 2：公转层只读已闭合 bar（未闭合硬闸门）
任何"当前周期"判断（如"本周/本月/本季/本年状态"）必须用**上一根已闭合 bar**（`label + delta <= asof`），禁止用当前未闭合 bar：

```python
def closed_bar(series, asof, delta):
    mask = series["label"] + delta <= asof      # 只取已闭合
    return series[mask].iloc[-1]                # 或请求 close[1]（TradingView 语义）
```

代码层每个周期处理器带闸门：`if not bar_closed: return`（StockSharp/LEAN/vn.py 同构，方案 §25-28）。

### 铁律 3：构建后必须自检
每次 `build_multi_timeframe.py` 重生成后，**必须**运行：

```bash
python scripts/lookahead_check.py
```

验收标准：报告"平移命中 = 0"全绿；"直引命中 > 0"仅作风险提示（证明直引禁令的必要性），不作为失败项。报告落盘 `results/lookahead_report_YYYYMMDD.txt`。

## 3. 与现有系统的关系

- **现有盘后全量 + DecisionEngine.evaluate() T-1 冻结口径本身无前视**（regime/S0/R0/Q_pos 只用 asof 之前日线），不受本规范影响。
- 本规范针对 **multi_timeframe 新消费场景**（公转自转体系 P1 起的增效器/共振评分读取该数据层）。
- `core/multi_timeframe_pipeline.py`（特种兵策略旧对齐管道，依赖 AKShare+模拟降级）与本数据层**不是同一事物**；改造该管道时应套用本规范三条铁律。

## 4. 修改维度与空间（可调项）

- 周期时长：脚本从数据自推导（相邻标签差中位数），新增周期目录无需改硬编码。
- 截断点数 N_CUTOFFS（默认 10）、抽样文件数：可在 `lookahead_check.py` 顶部调整。
- 未来扩展：盘中实时轮询落盘时，未闭合 bar 需显式标记（如 `is_closed=0` 列），本规范铁律 2 升级为按标记过滤——留作 P 级后续项。
- 本规范版本随方案迭代（V1.2 → V1.3+）同步更新。

## 5. 验收闭环

P0 验收：lookahead_check.py 已运行（2026-10-22 报告全量 7 周期 603 文件）→ 平移 0 命中全绿 → 引用规范 v1.0 落库 → 后续所有读取 multi_timeframe 的代码强制遵守本规范。
