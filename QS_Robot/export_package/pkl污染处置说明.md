# optimized_params.pkl 污染事件处置说明

日期：2026-10-21
状态：待用户拍板（删除属破坏性操作）

## 事件经过（已验证）

- 5 分钟口径复核（backtest_grid_audit_5min.py）运行期间发现：策略 `final_market_adaptive`
  的 `update_price()` 每 100 根 K 线自动调用 `_save_optimized_params()`，把在线探索到的
  "更优参数" 写入生产参数文件。
- 默认保存路径 `persist_dir='strategy_params'`（相对 CWD）→ 生产文件
  `D:\Gupiao\升级vscode\QS_Robot\export_package\strategy_params\optimized_params.pkl`。
- 复核首跑（全量 70 只，task eba97762 中断）期间，生产 pkl 被改写，save_time 为
  2026-10-21T17:04:51.322322。
- 已修复：复核脚本每策略实例化后重定向 persist_dir → `strategy_params_audit_tmp`，
  批次B 输出已确认参数全部写到 audit_tmp 目录（隔离生效）。

## 当前事实（已核验）

1. 全盘搜索：export_package 下唯一 .pkl 即被污染的 optimized_params.pkl（704 字节，
   save_time 2026-10-21T17:04:51），无任何历史备份。
2. git 未跟踪该文件（git ls-files 为空），无法用 git 恢复。
3. 文件内容 = final_market_adaptive 在 600016 单股上的在线探索结果：
   - best_params: grid_spacing=0.0005, 仓位=0.8, 最大回撤=0.05, 0.05
   - market_state_params: 对应 600016 行情
4. 代码内置默认（final_market_adaptive.py L207 附近 self.best_params 初始值）：
   grid_spacing=0.0040 / 0.8 / 0.2 / 0.025 / 0.008 / 0.08 + 初装 market_state_params。
5. 训练历史 training_history.json（100 条上限）已被 2026-10-21 15:52 起的在线探索记录占满，
   复核前无快照。

## 影响

- 若不处理：生产环境 final_market_adaptive 将使用 600016 单股的探索参数（grid_spacing
  0.0005 属极密网格，可能高频过度交易），且 market_state_params 与任意新股票行情不匹配。
- 周五 17:30 C 路线定时训练会重写该 pkl，但在此之前生产行为不确定。

## 处置选项

| 方案 | 动作 | 后果 | 可回滚性 |
|---|---|---|---|
| A（推荐） | 删除 pkl → 策略回落代码内置默认参数 | 生产行为确定、可预期；周五训练后自动更新 | 可回滚（周五训练重写；或随时重新训练） |
| B | 保留现状 | 用 600016 单股参数运行，行为不可预期 | 需人工重写才能恢复 |

## 后续加固建议（待确认后实施）

1. 给 final_market_adaptive 加 `--no-persist` / 环境变量开关，审计/回测场景禁止写生产参数。
2. 生产 pkl 纳入 git 跟踪（或建立每日快照），避免再次"无备份可恢复"。
3. 复核脚本 audit 隔离已内置，后续批次复用。
