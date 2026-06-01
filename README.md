# 红利双雄 ETF 盯盘

基于 AkShare 日线数据和原有布林带策略参数的双 ETF 盯盘工具，覆盖：

- `510880` 红利 ETF - 进攻端
- `512890` 红利低波 - 防守端

## 功能

- 双 ETF 最新盯盘状态：最新价、布林带上下轨、中轨、通道位置、目标仓位。
- 操作触发提示：跌破下轨提示买入/加仓，突破上轨提示卖出/减仓，通道内展示距离触发价。
- 信号流水：展示布林带规则生成的仓位变化，支持筛选和导出。
- K线图表：保留 K 线、成交量、布林带和买卖信号标记。
- 参数优化：保留原项目的布林带 Window x StdDev 网格搜索热力图。

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

## 项目结构

```text
红利 V2/
├── app.py                  # Streamlit 盯盘入口
├── components/             # 页面组件
│   ├── tab_monitor.py      # 双 ETF 盯盘总览
│   ├── tab_kline.py        # K线与布林带
│   ├── tab_signals.py      # 信号流水
│   └── tab_optimize.py     # 参数优化
├── src/
│   ├── data_loader.py      # AkShare 数据加载与缓存
│   ├── monitoring.py       # 盯盘状态计算
│   ├── strategies.py       # 布林带策略
│   └── optimize.py         # 参数优化逻辑
└── data/                   # 本地行情缓存（运行时自动生成）
```

策略信号仅供参考，投资需谨慎。
