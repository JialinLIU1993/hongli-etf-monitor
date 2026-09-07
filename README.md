# 红利双雄 ETF 盯盘

支持 AkShare 与同花顺 Financial API 的双 ETF 盯盘工具，沿用原有布林带策略参数，覆盖：

- `510880` 红利 ETF - 进攻端
- `512890` 红利低波 - 防守端

## 功能

- 双 ETF 最新盯盘状态：最新价、布林带上下轨、中轨、通道位置、目标仓位。
- 操作触发提示：跌破下轨提示买入/加仓，突破上轨提示卖出/减仓，通道内展示距离触发价。
- 行情总览：单标的报价、全宽 K 线/收盘线、布林通道与决策参考；选择历史区间时，图表与决策参考区都使用区间末日。
- 信号复盘：按 ETF 和调仓方向筛选，查看次数统计并导出所选信号。
- 参数研究：复用当前行情进行布林带网格搜索；切换优化目标复用结果，行情、来源或参数变化时提示重新运行。
- 投资记录：记录买入/卖出流水，成交价默认带出所选日期收盘价，也可手工修改；按 FIFO 自动计算已实现收益、浮动收益、当前持仓和历史收益。
- K线图表：保留 K 线、成交量、布林带和买卖信号标记。

## 保留项

- 默认使用 AkShare `fund_etf_hist_em` 前复权行情，可切换到同花顺 Financial API。不同来源分别保存在 `data/`，不会混合或提交到公开仓库。
- 默认布林带参数保留：
  - `510880`: Window `40`，StdDev `2.1`，首批仓位 `90%`
  - `512890`: Window `50`，StdDev `2.1`，首批仓位 `100%`
- 参数搜索从顶部“参数研究”直接进入。

## 快速开始

支持 Python 3.10 / 3.11，建议使用项目独立环境：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m streamlit run app.py
```

已有环境可跳过第一步。macOS 也可双击 `start.command` 启动。使用 `python -m streamlit` 可避免虚拟环境迁移后启动器指向旧路径。

## 工作台使用

采用全宽白色工作区，顶部导航切换四个工作空间，设置按需打开。

- **行情总览**：先选择 ETF，再查看该标的的报价与全宽图表。图表下方提供当前位置、价格边界和最近调仓；历史区间的决策参考与图表末日同步。
- **持仓记录**：管理实际成交，在当前持仓、收益记录和交易流水之间切换。
- **信号复盘 / 参数研究**：独立工作空间，使用同一份行情上下文，切换页面保留选择并复用有效缓存。
- **行情连接 / 数据范围 / 策略参数**：从顶部面板打开，不占用图表区域。刷新按钮重新获取行情。
- **窄屏布局**：顶部操作自动换行，报价重排为两列，决策参考纵向排列。

### 前端架构

- `app.py`：应用入口与页面路由。
- `components/workspace_controls.py`：统一导航、行情连接、日期和策略设置。
- `components/workspace_context.py`：行情缓存、快照、策略计算与统一数据上下文；不向业务页面传递 API Key。
- 各业务页面：只消费数据上下文。行情页负责当前标的，图表组件返回可见区间的状态，决策区据此展示。

## 同花顺 Financial API

已接入[官方 Financial-API](https://github.com/HiThink-Tech/Financial-API) 的 ETF 日线与行情快照，使用标准库 HTTP 客户端，无需安装额外 SDK。

### 页面使用

1. 在[官方管理页](https://fuyao.aicubes.cn/admin/)申请 API Key。
2. 启动项目，打开顶部“行情连接”，在“行情来源”选择“同花顺 Financial API”。
3. 展开“同花顺 API 设置”，在密码框填写 Key。该输入仅用于当前页面会话，不会写入项目文件。
4. 点击“刷新行情数据”。选择截至今天的区间时，会同时获取行情快照；布林带、收益估值和参数优化仍使用日线。

需要在重启后自动读取 Key，可在本机把 `.streamlit/secrets.toml.example` 复制为 `.streamlit/secrets.toml`，填入自己的 Key。真实配置文件已被 Git 忽略，不要提交或公开分享。也支持通过环境变量 `HITHINK_FINANCE_API_KEY` 注入；优先级为页面输入、环境变量、Streamlit 私密配置。

`ETF_DATA_PROVIDER=hithink` 可设为页面和命令行的默认来源；省略时继续使用 `akshare`。无 Key 时仍可选择 AkShare；明确选择同花顺后，失败只回落到同花顺自己的缓存，不会悄悄切换来源。

### 价格与时间口径

- 同花顺 ETF 历史接口没有 `adjust` 参数，返回的是“接口原始口径”，不将其标为前复权。分红附近的布林带和回测结果可能与 AkShare 前复权行情不同。[基金接口契约](https://github.com/HiThink-Tech/Financial-API/blob/main/docs/api/endpoints-fund.md)
- 同花顺历史缓存命名为 `data/<代码>_hithink_original.csv`，AkShare 前复权缓存仍为 `data/<代码>_qfq.csv`。
- 日期按北京时间转换为毫秒时间戳，超过 5 年的历史请求自动拆分为不重叠窗口；先检索并核对 ETF 完整代码，再请求行情。
- 快照标注接口返回时间，缺时间时明确提示，不填成当前时间。快照缓存 30 秒、日线缓存 5 分钟，均在页面交互时检查，不自动后台轮询。
- 基金契约未注明成交量的份/手单位，保留接口原值；缺失值保持为空。行情来源及价格口径随图表、信号和优化结果导出、通知显示。
- 请求只发送到官方 HTTPS 地址；包含超时、有界重试、业务错误检查和安全错误提示。鉴权失败不会盲目重试，密钥不会放入 URL 或日志。

### 命令行与定时推送

命令行使用环境变量 `HITHINK_FINANCE_API_KEY`，不会读取页面密码框或 `.streamlit/secrets.toml`。配置好环境变量后，可只预览通知内容：

```bash
.venv/bin/python scripts/check_signals.py --provider hithink --dry-run
.venv/bin/python scripts/check_signals.py --provider hithink --mode status --dry-run
```

GitHub Actions 中增加仓库变量 `ETF_DATA_PROVIDER=hithink` 和 Secret `HITHINK_FINANCE_API_KEY` 即可切换定时任务来源。原有 PushPlus Secrets 仍用于发送通知。两种来源的通知去重记录相互隔离；`--dry-run` 不发送消息或更新通知状态。

接口契约依据：[通用认证与错误码](https://github.com/HiThink-Tech/Financial-API/blob/main/docs/api/README.md)、[ETF 行情](https://github.com/HiThink-Tech/Financial-API/blob/main/docs/api/endpoints-fund.md)、[标的检索](https://github.com/HiThink-Tech/Financial-API/blob/main/docs/api/endpoints-meta.md)。当前接入以模拟响应完成测试，真实账户的权限与可用行情需在配置 Key 后验证。

## 数据刷新与记录保护

- 页面行情缓存 5 分钟，后续操作触发重新检查；点击“刷新行情数据”可立即重取。页面静置时不自动轮询。
- 网络失败或接口空响应时保留已有缓存，并展示降级提示和行情日期。单只 ETF 无行情时，其他行情及记账功能仍可使用。
- 刷新保留已缓存的完整日期区间；检测到历史复权价格变化时重取历史，避免混用不同复权价格。
- 投资记录存放在项目内 `data/investment_records.csv`。保存使用原子替换和版本检查，阻止多个页面相互覆盖；覆盖前保留上次完整版本为同目录 `.csv.bak` 文件。
- 损坏记录不会静默清空；读取失败时页面显示错误，可检查原文件与备份。CSV、备份、锁文件及写入临时文件均已加入 Git 忽略规则。
- 成交价默认取所选来源的参考收盘价，并标注价格口径，需核对实际成交价。市值按所选区间末日行情估值；缺少行情时不把未计算收益当成零。

## 开发与验证

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

默认仅收集 `tests/` 下测试；行情与推送接口均使用模拟，界面测试的记录读写隔离到临时目录。
`test_akshare.py` 是手动联网检查，只有直接运行才会请求外部数据。
仓库包含 Python 3.10 / 3.11 自动测试工作流，提交或拉取请求会运行回归验证。

## GitHub Actions 信号推送

仓库已包含 `.github/workflows/check-signals.yml`，会每小时运行一次 `scripts/check_signals.py`：

1. 按配置来源拉取 `510880`、`512890` 日线行情；默认 AkShare 前复权，选择同花顺时使用接口原始口径。
2. 按保留的布林带参数计算目标仓位变化。
3. 最新交易日出现买入/加仓或卖出/减仓信号时，调用 PushPlus 推送。
4. 通过 `.cache/check-signals/pushplus_sent.json` 缓存已推送信号，避免每小时重复提醒。
5. 默认只使用近一年日线；AkShare 来源优先用仓库内 `data/seed/` 初始化行情缓存，同花顺使用独立缓存。

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
│   ├── workspace_controls.py # 顶部导航与设置面板
│   ├── workspace_context.py # 共享行情与策略上下文
│   ├── tab_dashboard.py    # 当前 ETF、全宽图表与决策参考
│   ├── tab_monitor.py      # 双 ETF 盯盘组件
│   ├── tab_kline.py        # K线与布林带
│   ├── tab_signals.py      # 信号流水
│   ├── tab_investments.py  # 独立持仓记录工作台
│   └── tab_optimize.py     # 参数优化
├── src/
│   ├── data_loader.py      # 多来源行情加载与隔离缓存
│   ├── data_sources.py     # 来源选择与凭据读取
│   ├── hithink_api.py      # 同花顺 ETF REST 客户端
│   ├── investment_records.py # 本地投资流水与收益计算
│   ├── monitoring.py       # 盯盘状态计算
│   ├── strategies.py       # 布林带策略
│   └── optimize.py         # 参数优化逻辑
└── data/                   # 本地行情缓存（运行时自动生成）
```

策略信号仅供参考，投资需谨慎。

## GitHub Pages 网页版

访问 https://jialinliu1993.github.io/hongli-etf-monitor/ 。白色工作台提供行情图表、信号筛选、参数网格结果及浏览器本地持仓记录。

- 页面只发布行情与策略计算结果，不读取或上传个人投资记录。网页新访客从空记录开始，录入仅保存于当前浏览器，可导出 CSV；清理浏览器存储会失去这些记录。
- 默认采用 AkShare 前复权日线。工作日北京时间 16:30 由 GitHub Actions 尝试更新，实际执行时间可能延迟；页面展示真实行情日期。点击“检查更新”读取最近发布版本，不会实时请求行情。
- 自定义策略参数重算继续使用本地 Streamlit。网页版展示构建时计算的参数网格，历史回测不代表未来收益。
- 如需同花顺数据，在仓库 Actions Secrets 设置 `HITHINK_FINANCE_API_KEY`，在 Actions Variables 设置 `ETF_DATA_PROVIDER=hithink`，手动运行 `Deploy GitHub Pages`。密钥只用于后台构建，永不写入网页。
- 推送主分支发布随代码维护的公开行情快照；定时或手动运行会获取行情。获取失败时保留已经上线的版本。

本地构建：`python scripts/build_pages.py`，产物仅在 `output/pages`；`--refresh` 获取最新行情。GitHub Pages 使用 Actions 部署，不运行 Python 服务。
