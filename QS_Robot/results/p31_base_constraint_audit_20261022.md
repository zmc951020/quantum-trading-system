# P3.1 逐策略底座约束审计清单（19 策略）

- 生成时间：2026-10-22 21:24:12
- 审计维度：底座继承/导入、止损、止盈、仓位上限、冷却、趋势/市况闸门、参数持久化、update_price 在线接口、买卖点信号函数（13 章买卖点审计前置）
- 口径：用户 2026-10-22 —— 魔法策略目前没加底座约束；其它 18 个应有底座约束，没有的要添加

| # | 策略 | 文件 | 行数 | 底座 | 止损 | 止盈 | 仓位上限 | 冷却 | 趋势闸门 | 持久化 | update_price | 买点函数 | 卖点函数 | 缺口 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | downtrend_optimized | downtrend_optimized.py | 28150 | 0/0 | 31 | 21 | 29 | 0 | 0 | 0 | 1 | 0 | 0 | 无底座继承；无冷却；无市况闸门 |
| 2 | multi_factor_resonance | multi_factor_resonance.py | 16419 | 0/0 | 27 | 0 | 0 | 0 | 10 | 0 | 1 | 2 | 3 | 无底座继承；无止盈；无仓位上限；无冷却 |
| 3 | gyro_minute_strategy_v6_optimized | gyro_minute_strategy_v6_optimized.py | 28891 | 0/0 | 29 | 19 | 0 | 0 | 1 | 2 | 1 | 0 | 0 | 无底座继承；无仓位上限；无冷却 |
| 4 | gyro_precession_strategy | gyro_precession_strategy.py | 37429 | 1/3 | 16 | 9 | 0 | 0 | 2 | 0 | 1 | 0 | 0 | 无仓位上限；无冷却 |
| 5 | fund_allocation | fund_allocation.py | 46498 | 0/0 | 9 | 2 | 6 | 5 | 4 | 1 | 3 | 0 | 0 | 无底座继承 |
| 6 | golden_bowl_ice_break | golden_bowl_ice_break.py | 49004 | 0/0 | 2 | 32 | 8 | 22 | 0 | 0 | 1 | 6 | 1 | 无底座继承；无市况闸门 |
| 7 | final_optimized_strategy | final_optimized_strategy.py | 22233 | 0/0 | 16 | 0 | 0 | 0 | 28 | 0 | 1 | 0 | 0 | 无底座继承；无止盈；无仓位上限；无冷却 |
| 8 | adaptive_ml_strategy | adaptive_ml_strategy.py | 16284 | 0/0 | 1 | 0 | 0 | 0 | 14 | 2 | 1 | 1 | 1 | 无底座继承；无止盈；无仓位上限；无冷却 |
| 9 | newton_momentum_enhanced | newton_momentum_enhanced.py | 20615 | 0/0 | 17 | 15 | 14 | 8 | 16 | 0 | 1 | 1 | 1 | 无底座继承 |
| 10 | thermodynamic_entropy_enhanced | thermodynamic_entropy_enhanced.py | 20551 | 0/0 | 19 | 17 | 16 | 0 | 12 | 0 | 1 | 1 | 1 | 无底座继承；无冷却 |
| 11 | fractal_chaos_strategy | fractal_chaos_strategy.py | 15272 | 0/0 | 15 | 11 | 6 | 8 | 1 | 0 | 1 | 3 | 3 | 无底座继承 |
| 12 | fluid_dynamics_strategy | fluid_dynamics_strategy.py | 7529 | 0/0 | 11 | 11 | 0 | 8 | 1 | 0 | 1 | 1 | 1 | 无底座继承；无仓位上限 |
| 13 | rl_adaptive_param_strategy | rl_adaptive_param_strategy.py | 13591 | 0/0 | 17 | 9 | 0 | 0 | 9 | 2 | 1 | 1 | 1 | 无底座继承；无仓位上限；无冷却 |
| 14 | bernoulli_coanda_strategy | bernoulli_coanda_strategy.py | 44589 | 0/0 | 20 | 12 | 10 | 7 | 31 | 3 | 2 | 0 | 2 | 无底座继承 |
| 15 | minervini_sepa_strategy | minervini_sepa_strategy.py | 44464 | 1/3 | 35 | 1 | 2 | 0 | 3 | 0 | 1 | 2 | 1 | 无冷却 |
| 16 | adaptive_range_grid | adaptive_range_grid.py | 31597 | 0/0 | 18 | 15 | 16 | 0 | 18 | 0 | 1 | 0 | 0 | 无底座继承；无冷却 |
| 17 | high_return_grid | high_return_grid.py | 48683 | 0/0 | 28 | 32 | 57 | 0 | 20 | 4 | 1 | 1 | 0 | 无底座继承；无冷却 |
| 18 | final_market_adaptive | final_market_adaptive.py | 68223 | 0/0 | 16 | 25 | 63 | 0 | 69 | 8 | 1 | 2 | 0 | 无底座继承；无冷却 |

> 数字 = 关键词命中次数（0 表示缺失/极可能缺失，需人工复核）。闸门口径=趋势/市况关键词命中。

## 结论（复核后填写）

**审计口径确认**：用户"底座等约束条件"按课题主线解读 = **公转自转护佑底座约束**
（V3d 决策引擎网关 + 统一风控约束），P4 接入时统一添加；本审计盘点各策略**现有自带约束**缺口。

**逐策略缺口清单（需添加/补齐项）**：

| 类别 | 策略 | 缺口 | 处理 |
|---|---|---|---|
| 魔法 | minervini_sepa_strategy | **无冷却**（其余齐全） | 已有 StrategyBase 继承+完整风控；补冷却 → P3.2 处理 |
| 完整 | multi_factor_resonance | 无止盈、无仓位上限、无冷却 | P4 统一护佑底座补齐 |
| 完整 | final_optimized_strategy | 无止盈、无仓位上限、无冷却 | 同上（假完整已补接口，风控仍缺） |
| 完整 | adaptive_ml_strategy | 无止盈、无仓位上限、无冷却 | 同上（风控外置，需内化） |
| 完整 | fluid_dynamics_strategy | 无仓位上限 | 同上 |
| 完整 | rl_adaptive_param_strategy | 无仓位上限、无冷却 | 同上 |
| 完整 | gyro_minute_strategy_v6_optimized | 无仓位上限、无冷却 | 同上 |
| 完整 | gyro_precession_strategy | 无仓位上限、无冷却 | 同上 |
| 完整 | thermodynamic_entropy_enhanced | 无冷却 | 同上 |
| 完整 | downtrend_optimized | 无冷却、无市况闸门 | 同上 |
| 完整 | golden_bowl_ice_break | 无市况闸门（10-18：无固定止损） | 同上 |
| 网格 | adaptive_range_grid / high_return_grid / final_market_adaptive | 均无冷却（风控/闸门齐全） | 同上 |

**魔法策略底座现状（P3.2 深读确认，A 级）**：
- **实际已继承 StrategyBase（class MinerviniSepaStrategy(StrategyBase)，L45）+ 从 .strategy_base 导入**
  ——"魔法策略目前没加底座等约束条件"与实际不符（可能是旧版本认知，或指公转自转护佑底座
  尚未接入）；缺口仅**无冷却**一项。
- 自带风控完整：止损 35 命中（7.5%/5.5% 双档+10% 硬线）、仓位 2（max_positions 6/exposure 0.8）、
  大盘过滤（000300 MA200）、3R 保本、分批建仓——**书页精华参数已全参数化**（详见 P3.2）。

**添加方式建议**：不逐策略手改（避免破坏原生信号，符合 10-18"壳永不拥有改方向权力"铁律）——
统一由 P4 增效器网关（V3d 决策引擎）提供公转自转护佑底座约束：L1 公转闸门（只拦买不拦卖）+
L2 自转确认 + L3 ABC 加权（只缩放不改方向）；策略自身缺失的止盈/仓位/冷却在 P4 接入时
由网关外层兜底（硬止损/跟踪止盈/最大仓位/冷却为统一风控外层）。
