# 红利双雄 ETF 盯盘

基于 AkShare 日线数据和原有布林带策略参数的双 ETF 盯盘工具，覆盖：

- `510880` 红利 ETF - 进攻端
- `512890` 红利低波 - 防守端

## 功能

- 双 ETF 最新盯盘状态：最新价、布林带上下轨、中轨、通道位置、目标仓位。
- 操作触发提示：跌破下轨提示买入/加仓，突破上轨提示卖出/减仓，通道内展示距离触发价。
- Dashboard：把盯盘重点直接整合到 K 线图中，并集中展示当前持仓和投资记录。
- 策略工具：合并信号流水和参数优化，支持筛选、导出和布林带网格搜索。
- 投资记录：记录买入/卖出流水，成交价默认带出所选日期收盘价，也可手工修改；按 FIFO 自动计算已实现收益、浮动收益、当前持仓和历史收益。
- K线图表：保留 K 线、成交量、布林带和买卖信号标记。

## 保留项

- 数据源保留为 AkShare `fund_etf_hist_em`，本地缓存运行时保存在 `data/`，不会提交到公开仓库。
- 默认布林带参数保留：
  - `510880`: Window `40`，StdDev `2.1`，首批仓位 `90%`
  - `512890`: Window `50`，StdDev `2.1`，首批仓位 `100%`
- 参数优化能力保留在页面的“参数优化”标签页。

## 快速开始

```bash
pip install -r requirements.txt
python3 -m streamlit run app.py
```

如果仓库内 `.venv/bin/streamlit` 指向旧路径，可以直接使用上面的 `python3 -m streamlit` 启动方式。

## GitHub Actions 信号推送

仓库已包含 `.github/workflows/check-signals.yml`，会每小时运行一次 `scripts/check_signals.py`：

1. 拉取 `510880`、`512890` 前复权日线行情。
2. 按保留的布林带参数计算目标仓位变化。
3. 最新交易日出现买入/加仓或卖出/减仓信号时，调用 PushPlus 推送。
4. 通过 `.cache/check-signals/pushplus_sent.json` 缓存已推送信号，避免每小时重复提醒。
5. 默认只使用近一年日线，并优先用仓库内 `data/seed/` 初始化行情缓存，避免每次从 2020 年全量拉取。

需要在 GitHub 仓库的 `Settings -> Secrets and variables -> Actions` 添加：

- `PUSHPLUS_TOKEN`: 必填，PushPlus 用户令牌或消息令牌。
- `PUSHPLUS_TOPIC`: 可选，PushPlus 群组编码。
- `PUSHPLUS_TO`: 可选，好友令牌。不要和 `PUSHPLUS_TOPIC` 同时使用。
- `PUSHPLUS_CHANNEL`: 可选，指定推送渠道。

本地测试可运行：

```bash
SIGNAL_DRY_RUN=1 SIGNAL_FORCE_UPDATE=0 python3 scripts/check_signals.py
```

仓库还包含 `.github/workflows/push-band-status.yml`，会在交易日北京时间 `10:00` 和 `14:00`
固定推送一次两只 ETF 的布林带状态。内容包括实时价格、布林带上/中/下轨，以及价格在通道内的位置
（`0%` 为下轨，`50%` 为中轨，`100%` 为上轨）。状态推送默认只拉近一年日线，并在 GitHub Actions
缓存 `data/`，减少行情接口短暂断连导致的漏推。本地预览可运行：

```bash
SIGNAL_DRY_RUN=1 SIGNAL_FORCE_UPDATE=0 python3 scripts/check_signals.py --mode status
```

## 项目结构

```text
红利 V2/
├── app.py                  # Streamlit 盯盘入口
├── components/             # 页面组件
│   ├── tab_dashboard.py    # 盯盘/K线/投资记录 Dashboard
│   ├── tab_monitor.py      # 双 ETF 盯盘组件
│   ├── tab_kline.py        # K线与布林带
│   ├── tab_signals.py      # 信号流水
│   ├── tab_investments.py  # 投资记录与收益统计
│   ├── tab_strategy_tools.py # 信号流水 + 参数优化
│   └── tab_optimize.py     # 参数优化
├── src/
│   ├── data_loader.py      # AkShare 数据加载与缓存
│   ├── investment_records.py # 本地投资流水与收益计算
│   ├── monitoring.py       # 盯盘状态计算
│   ├── strategies.py       # 布林带策略
│   └── optimize.py         # 参数优化逻辑
└── data/                   # 本地行情缓存（运行时自动生成）
```

策略信号仅供参考，投资需谨慎。
