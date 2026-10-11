# 玉山 AI CUP：AI Agent 主動型 ETF MVP

GitHub：[ismesid/yushan-etf-agent-MVP](https://github.com/ismesid/yushan-etf-agent-MVP)（私有倉庫），主要分支為 `main`。名稱中的 `MVP` 表示目前是測試版。

目標是在約 8 小時內完成可供開會檢查的 ETF 決策流程，並方便增加資料源、因子、模型與 UI。目前有共用資料合約、離線示例、官方歷史樣本及 F05 全股票月報下載功能，完整投資流程仍在開發。

## 目前功能

- 六種核心合約：`MarketSnapshot`、`AccountSnapshot`、`FeatureTable`、`AgentDraft`、`PortfolioProposal`、`ValidationReport`。
- `AgentProvider` 共同介面與 `AgentResult`，保留實際模型資訊及用量欄位。
- `DatasetSplitPlan`：按時間保留訓練、驗證、測試期間，檢查日期順序與不重疊。
- 含 25 檔既有持股的人工測試帳，以及離線 CLI 合約展示。
- F05 官方股票白名單：150 檔（100 TWSE／50 TPEX），提供 CSV、來源版本及獨立載入／檢查命令。
- 官方歷史月報：2025-09 已走訪全部 150 檔，147 檔有資料，另保存缺件與部分日期狀態；2330／5274 的早期樣本來源及驗收紀錄已併入同一資料目錄。
- F05 全股票月報下載：依白名單逐股取得已完成月份，單線限速、核對並復用原始快取、保存逐股成功／失敗及逐日覆蓋報告。
- CSV 4.0：每日股票表與每股月表共用 22 欄；月表是該股整月的每日行情，不是月 K 線。兩種視圖由相同清洗結果生成，分析時只讀一種，避免重複計算。
- 每日行情覆蓋檢查：日表對照 F05 白名單，分別列出已取得、有效價格與缺件股票，保存獨立報告版本。
- 標準庫 `unittest` 檢查共用合約、白名單、歷史解析及日表覆蓋，實際驗收結果見 [開發紀錄](development_notes.md)。

**contracts-demo 的行情、因子、帳戶與 Agent 草稿都是人工測試資料。** history-sample／history-universe 另行取得真實官方歷史行情，沒有取代 fixture 或呼叫投資模型；這些功能都不產生正式可提交的 D-Plan。

## 執行方式

需要 Python 3.11 以上。目前執行示例與測試只使用標準庫，不需安裝第三方套件。

專案使用 `src` 目錄配置。從專案根目錄開啟 PowerShell，設定 Python 模組路徑後執行：

```powershell
$env:PYTHONPATH = (Resolve-Path 'src').Path
python -B -m etf_agent.cli --help
python -B -m etf_agent.cli universe-check --universe data/universe.csv
python -B -m etf_agent.cli contracts-demo --fixture tests/fixtures/contracts_demo.json
python -B -m unittest discover -s tests -p 'test_*.py' -v
```

設定只影響目前的 PowerShell 工作階段。示例預期顯示：

```text
JSON 往返：PASS
持股：25 檔
現金：10,000,000 元
股票市值：90,000,000 元
NAV：100,000,000 元
現金＋股票市值核對：PASS
submission_ready：false
```

下載使用標準庫與系統既有 curl，沒有新增 Python 依賴。產物存於本機 `data/cache/`，每次新建版本目錄，Git 不追蹤。

要重新建立 2025-09 全股票日／月 CSV，可復用目前 147 檔成功來源，再查詢三檔無行情來源（仍會有 3 次 HTTP 請求）：

```powershell
python -B -m etf_agent.cli history-universe --month 2025-09 --universe data/universe.csv --cache-manifest data/cache/history_universe/2025-09/20261011T145716_6e56c903/manifest.json --output data/cache/history_universe
```

全股票命令每兩次 HTTP 請求間隔至少 1 秒、每次 timeout 10 秒，不自動重試。每次另建 `data/cache/history_universe/<月份>/<版本>/`；`daily/<月份>/` 是當日已取得股票的合併表，`monthly/<月份>/` 是每股整月每日行情，原始資料和逐股狀態留在同批目錄。`coverage.json` 列出各日覆蓋、缺件及失敗股票；只採來源實際回傳日期，沒有補造日曆、缺日或缺股。

串流中斷或部分下載失敗時，可把 `--cache-manifest` 換成該次全股票目錄的 manifest 再執行；已成功來源先核對原始檔 hash、月份／股票、HTTPS 與抓取時間再復用，只請求其餘股票。壞快取會阻擋；完整 150 檔成功快取可用同一命令零次 HTTP 另產一版 CSV。命令顯示實際 HTTP 次數與快取命中數，成功代表各股取得／解析成功，仍需分別查看逐日覆蓋與資料限制。

保留 `history-sample` 供兩檔的小量下載測試；需要再產生 2330／5274 測試用 CSV 時，使用已保存的樣本 manifest 完全離線匯出至另一目錄：

```powershell
python -B -m etf_agent.cli history-export --manifest data/cache/history_universe/2025-09/20261011T145716_6e56c903/sample_manifest.json --output data/cache/history_export
```

`history-export` 保持只支援 2330／5274 樣本；全股票快取請使用上述 `history-universe --cache-manifest`。

要檢查本機日表的股票覆蓋，可離線執行：

```powershell
python -B -m etf_agent.cli prices-check --prices data/cache/history_universe/2025-09/20261011T145716_6e56c903/daily/2025-09/2025-09-01_prices.csv --date 2025-09-01 --output data/cache/coverage
```

每次在 `data/cache/coverage/<日期>/<新版本>/` 保存 `coverage.json`、`coverage.md`、`missing_stocks.csv`。覆蓋率只說明取得哪些股票的資料，完整覆蓋也不代表正式可交易或可提交。

第 09 批當時完成離線驗收：全套 119 項測試通過，當時 21 個樣本日表皆取得 2／150、缺 148 檔。[當時覆蓋報告](data/cache/coverage/2025-09-01/20261011T144802_4463a889/coverage.md) 與 [缺件股票 CSV](data/cache/coverage/2025-09-01/20261011T144802_4463a889/missing_stocks.csv) 保留不改，報告中的原輸入路徑是歷史紀錄；原樣本目錄已清理，需重跑當時結果可使用 [保存的兩檔日表](data/cache/history_universe/2025-09/20261011T145716_6e56c903/provenance/history_sample/input/2025-09-01_prices.csv)。日常分析使用下方全股票資料。

白名單來源／載入、覆蓋報告、資料欄位、單位、清洗方式、上櫃空值與報表精度，請看 [資料說明](docs/data_contracts.md)；README 只提供專案概況與執行入口。

第 10 批已走訪全部 150 檔的 2025-09 官方月報，147 檔有資料：共 3,075 列、21 份日表、147 份每股月表，實際 HTTP 148 次、復用兩檔快取。3718／7769／7828 的官方回應查無行情；7750 只回傳 2025-09-17 起的 9 筆，因此前 12 個日表為 146／150，後 9 個為 147／150。未補造缺件，整批 `success=false`、覆蓋未完整、`submission_ready=false`；132 項測試通過。

三檔缺件原因已核對官方上市／上櫃日期，均晚於 2025-09；日期、來源與市場沿革見 [歷史行情可取得範圍](docs/history_availability_2025-09.md)。維持 F05 原 150 檔名單，不補零值，也不以其他代號或興櫃行情代替缺件。

本批資料可直接查看：

- [每日 CSV 目錄](data/cache/history_universe/2025-09/20261011T145716_6e56c903/daily/2025-09/)／[2025-09-01 日表（146 檔）](data/cache/history_universe/2025-09/20261011T145716_6e56c903/daily/2025-09/2025-09-01_prices.csv)。
- [每股月 CSV 目錄](data/cache/history_universe/2025-09/20261011T145716_6e56c903/monthly/2025-09/)／[2330 月表](data/cache/history_universe/2025-09/20261011T145716_6e56c903/monthly/2025-09/TWSE_2330_2025-09.csv)。
- [逐股來源與狀態](data/cache/history_universe/2025-09/20261011T145716_6e56c903/manifest.json)／[逐日覆蓋與缺件](data/cache/history_universe/2025-09/20261011T145716_6e56c903/coverage.json)／[品質與限制](data/cache/history_universe/2025-09/20261011T145716_6e56c903/data_quality.json)。

原 `history_sample` 已清理，兩檔 raw、原報表 CSV 與保留原價量／抓取時間的清洗月表都已包含於上述全股票資料；樣本 [manifest 原文](data/cache/history_universe/2025-09/20261011T145716_6e56c903/sample_manifest.json)、[早期驗收證據](data/cache/history_universe/2025-09/20261011T145716_6e56c903/provenance/history_sample/) 與 [清理／hash 索引](data/cache/history_universe/2025-09/20261011T145716_6e56c903/provenance/history_sample/cleanup.json) 另行保存。清理後 132 項測試通過，樣本離線匯出仍可零 HTTP 重建 42 列。以上行情連結皆為本機快取，新 clone 不會自帶；重新匯出另建版本目錄。

## 文件與程式導覽

| 路徑 | 內容 |
|---|---|
| [AGENTS.md](AGENTS.md) | 分批討論、實作與驗收的合作規則 |
| [design1001.md](design1001.md) | 架構與策略草案；其中待建立的命令不代表已實作 |
| [checklist.md](checklist.md) | 待辦、完成證據與正式輸出阻擋條件 |
| [development_notes.md](development_notes.md) | 簡明記錄討論、決定及原因，並保存各批授權、實際修改、驗收與下一步 |
| [docs/data_contracts.md](docs/data_contracts.md) | 資料欄位、清洗與精度說明，以及各模組合約與程式位置 |
| [src/etf_agent/contracts.py](src/etf_agent/contracts.py) | 核心合約及輸入檢查 |
| [src/etf_agent/agent/base.py](src/etf_agent/agent/base.py) | 模型 provider 介面與結果格式 |
| [data/universe.csv](data/universe.csv)／[universe.manifest.json](data/universe.manifest.json) | F05 的 150 檔股票及來源版本紀錄 |
| [src/etf_agent/universe.py](src/etf_agent/universe.py) | 白名單載入、來源完整性、代號／市場查詢 |
| [src/etf_agent/coverage.py](src/etf_agent/coverage.py) | 日表對照白名單、基本格式檢查與覆蓋／缺件報告 |
| [src/etf_agent/cli.py](src/etf_agent/cli.py) | 白名單／日表檢查、離線合約展示、歷史樣本／全股票下載與快取匯出命令 |
| [src/etf_agent/history.py](src/etf_agent/history.py) | 歷史樣本／全股票下載、原始快取核對、每日／每股月 CSV 與覆蓋保存 |
| [tests/fixtures/contracts_demo.json](tests/fixtures/contracts_demo.json) | 人工測試行情、帳戶、草稿與研究設定 |
| [tests/test_contracts.py](tests/test_contracts.py) | 合約測試 |
| [specs/internal/agent_draft.schema.json](specs/internal/agent_draft.schema.json) | 內部 AgentDraft 格式，與官方 D-Plan 分開 |
| [specs/official/](specs/official/) | F01～F09 官方參賽參考來源 |

## 歷史資料與後續功能

合約已預留資料日、公開可知時間、實際抓取時間、原始內容雜湊及資料版本，讓日後回測能追查當時使用的資料。訓練、驗證、測試按時間切分，較新的測試期間預先保留。

fixture 的切分是說明用設定：2020～2023 訓練、2024 驗證、2025～2026-09 測試，並沒有對應的長期歷史資料。真正的交易日隔離、標籤跨界檢查、公司行動處理、回測與訓練尚未實作。

白名單已接入離線日表覆蓋檢查與 `history-universe` 月報下載，尚未接入因子、Agent 或交易流程；`history-sample` 仍固定下載兩檔，`contracts-demo` 仍使用 fixture 候選池。F05 是競賽股票池，不能直接視為各歷史日期的可投資股票池。

其他尚未完成：每日最新行情更新、交易日曆／公司行動與歷史可知時間、完整快照與清洗、精確且一致成交口徑、因子計算、真實 Codex／Claude 決策、配置與風控、官方股數與費用計算、D-Plan 結構／語意驗證、SQLite 帳務、成交與官方庫存核對。後續依合作規則逐批討論和驗收。

## 日常版本管理

每次完成一批，先查看差異，再加入本批指定檔案。以下用合約和文件修改作例子：

```powershell
git status
git diff
git add src/etf_agent/contracts.py docs/data_contracts.md development_notes.md checklist.md
git commit -m "Update contracts and development notes"
git push
```

`git push` 需已設定 GitHub 遠端與目前分支的追蹤關係。金鑰、本機設定、真實帳戶與大量行情快取應保留在未追蹤位置；提交前檢查 `git status` 和差異內容。

`specs/official/` 附件保留為本專案參賽參考來源，不因納入版本管理而宣稱具有開源授權。本專案目前未指定開源授權。
