# 玉山 AI CUP：AI Agent 主動型 ETF MVP

[GitHub 倉庫](https://github.com/ismesid/yushan-etf-agent-MVP)（私有，主要分支 `main`）。這個 Python 專案要把官方行情、因子分析、模型選股與程式風控串成可追溯的 ETF 決策流程，最後產生競賽 D-Plan；目前完成到歷史資料與三因子分析。

## 目前可以做什麼

- 核對 F05 的 150 檔股票（100 上市／50 上櫃），下載官方月報，輸出每日合併 CSV 與每股月 CSV。
- 使用官方開休市排程，檢查截至資料日的 21 筆收盤價，再產生動能、均線偏離、年化波動分析。
- 2025-09 已取得 147 檔行情、3,075 列；截至 9/30 有 146 檔完整視窗。7750 有 9 筆，其餘三檔尚未在指定市場掛牌，原因見 [行情可取得範圍](docs/history_availability_2025-09.md)。
- 用人工 fixture 展示資料合約與 25 檔持股帳戶核對。

三因子使用未調整原價；臨時休市、公司行動及歷史公開時間仍待核實。排名、真實模型、配置與風控、D-Plan、帳務尚未串接；目前產物都是歷史分析或測試示例，`submission_ready=false`。

## 專案架構

```text
F05 股票池 → 官方月報 → 每日日表 → 21 筆價格視窗 → 三因子分析
                                                       ↓ 後續
                     排名 → 模型提案 → 配置／風控 → D-Plan → 帳務核對
```

| 責任 | 程式位置 | 實作狀態 |
|---|---|---|
| 共用資料與帳戶合約 | [contracts.py](src/etf_agent/contracts.py) | 六種核心合約與離線示例；正式快照／FeatureTable 串接待實作 |
| 股票池、行情取得與覆蓋 | [universe.py](src/etf_agent/universe.py)、[providers/](src/etf_agent/providers/)、[history.py](src/etf_agent/history.py)、[coverage.py](src/etf_agent/coverage.py) | 官方歷史月報、快取、CSV、覆蓋報告 |
| 日曆與價格視窗 | [calendar.py](src/etf_agent/calendar.py)、[history_windows.py](src/etf_agent/history_windows.py) | 官方排程與同月份 21 筆視窗 |
| 因子 | [features.py](src/etf_agent/features.py) | 三因子計算與閱讀報告；排名待實作 |
| 模型介面 | [agent/base.py](src/etf_agent/agent/base.py) | Protocol 與結果合約已預留，真實 Codex／Claude 決策待實作 |
| 執行入口 | [cli.py](src/etf_agent/cli.py) | 組合上述模組的九個命令 |
| 配置、D-Plan、帳務 | [設計草案](design1001.md) | 待實作；草案指令不代表可執行功能 |

欄位、單位、來源時間及模組介面集中在 [資料合約](docs/data_contracts.md)。行情分析只讀 daily，monthly 是同一資料的查閱視圖，兩者不要合併。

## 快速開始

需要 **Python 3.11 以上**，目前只使用標準庫。從專案根目錄開啟 PowerShell：

```powershell
$env:PYTHONPATH = (Resolve-Path 'src').Path
python -B -m etf_agent.cli --help
python -B -m etf_agent.cli contracts-demo --fixture tests/fixtures/contracts_demo.json
```

示例應顯示 JSON 往返與帳戶核對 PASS：25 檔測試持股，股票市值 90,000,000 元＋現金 10,000,000 元＝NAV 100,000,000 元。沒有真實模型呼叫。環境、白名單檢查與必要測試見 [環境與基本使用](docs/quickstart.md)。

下載與分析產物放在 Git 忽略的 `data/cache/`，新 clone 不會自帶。若要從頭產生真實歷史分析，依序閱讀下表的歷史資料、日曆／視窗、因子分析操作；每步使用命令顯示的新產物路徑。

## 依用途執行

| 要做的事 | CLI 命令 | 專屬說明 |
|---|---|---|
| 看共用資料與測試帳 | `contracts-demo` | [環境與基本使用](docs/quickstart.md#合約示例) |
| 核對 150 檔股票池 | `universe-check` | [白名單核對](docs/quickstart.md#白名單核對) |
| 下載全股票月資料、續接快取 | `history-universe` | [歷史資料取得](docs/history_data.md#全股票下載) |
| 小量下載、離線重建樣本 | `history-sample`、`history-export` | [兩檔樣本](docs/history_data.md#兩檔樣本與離線匯出) |
| 檢查單日日表 | `prices-check` | [每日覆蓋檢查](docs/history_data.md#每日覆蓋檢查) |
| 取得官方排程 | `calendar-download` | [日曆下載](docs/calendar_windows.md#取得官方排程) |
| 檢查 21 筆價格 | `history-window-check` | [價格視窗](docs/calendar_windows.md#價格視窗檢查) |
| 產生與閱讀三因子 | `history-features` | [因子意義、公式與用法](docs/factor_analysis.md) |

## 查看目前成果

| 內容 | 本機成果 |
|---|---|
| 每日／每股月行情 | [daily 目錄](data/cache/history_universe/2025-09/20261011T145716_6e56c903/daily/2025-09/)／[monthly 目錄](data/cache/history_universe/2025-09/20261011T145716_6e56c903/monthly/2025-09/) |
| 150 檔價格視窗與缺失日期 | [window_coverage.csv](data/cache/history_windows/2025-09-30/20261011T154440_9842e79e/window_coverage.csv)／[閱讀報告](data/cache/history_windows/2025-09-30/20261011T154440_9842e79e/window_report.md) |
| 146 檔三因子與解讀 | [features.csv](data/cache/features/2025-09-30/20261011T160349_3b42fa16/features.csv)／[analysis.md](data/cache/features/2025-09-30/20261011T160349_3b42fa16/analysis.md) |

## 設計、規則與進度

- [design1001.md](design1001.md)：整體架構與策略草案；[checklist.md](checklist.md)：完成證據與後續待辦。
- [development_notes.md](development_notes.md)：各批授權、決定、實際驗收與限制；[AGENTS.md](AGENTS.md)：開發合作方式。
- [specs/official/](specs/official/)：F01～F09 官方來源；[specs/internal/](specs/internal/)：內部合約 schema；[tests/](tests/)：測試與人工 fixture。

官方附件保留作參賽參考，不因納入倉庫而宣稱具有開源授權；本專案目前未指定開源授權。
