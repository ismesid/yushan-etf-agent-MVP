# 玉山 AI CUP：AI Agent 主動型 ETF MVP

GitHub：[ismesid/yushan-etf-agent-MVP](https://github.com/ismesid/yushan-etf-agent-MVP)（私有倉庫），主要分支為 `main`。名稱中的 `MVP` 表示目前是測試版。

目標是在約 8 小時內完成可供開會檢查的 ETF 決策流程，並方便增加資料源、因子、模型與 UI。目前有共用資料合約、離線示例及兩檔官方歷史下載樣本，完整投資流程仍在開發。

## 目前功能

- 六種核心合約：`MarketSnapshot`、`AccountSnapshot`、`FeatureTable`、`AgentDraft`、`PortfolioProposal`、`ValidationReport`。
- `AgentProvider` 共同介面與 `AgentResult`，保留實際模型資訊及用量欄位。
- `DatasetSplitPlan`：按時間保留訓練、驗證、測試期間，檢查日期順序與不重疊。
- 含 25 檔既有持股的人工測試帳，以及離線 CLI 合約展示。
- 官方歷史月報樣本：2330／5274，各 21 筆 2025-09 資料，保存原始資料與品質紀錄。
- CSV 4.0：21 份每日股票表、2 份個股月表，支援從本機快取離線重新匯出；目前仍只有兩檔樣本。
- 標準庫 `unittest` 檢查共用合約及歷史解析，實際驗收結果見 [開發紀錄](development_notes.md)。

**contracts-demo 的行情、因子、帳戶與 Agent 草稿都是人工測試資料。** history-sample 另行下載真實歷史行情，沒有取代 fixture 或呼叫投資模型；兩者都不是正式可提交的 D-Plan。

## 執行方式

需要 Python 3.11 以上。目前執行示例與測試只使用標準庫，不需安裝第三方套件。

專案使用 `src` 目錄配置。從專案根目錄開啟 PowerShell，設定 Python 模組路徑後執行：

```powershell
$env:PYTHONPATH = (Resolve-Path 'src').Path
python -B -m etf_agent.cli --help
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

要試下載兩檔歷史 CSV，可在上述 Python 路徑設定後執行（此指令會連網）：

```powershell
python -B -m etf_agent.cli history-sample --month 2025-09 --output data/cache/history_sample
```

下載使用標準庫與系統既有 curl，沒有新增 Python 依賴。產物存於本機 `data/cache/`，每次新建版本目錄，Git 不追蹤。

已有原始資料時，可完全離線重新匯出 CSV：

```powershell
python -B -m etf_agent.cli history-export --manifest data/cache/history_sample/2025-09/20261011T125021_603f0054/manifest.json --output data/cache/history_sample
```

資料欄位、單位、清洗方式、上櫃空值與報表精度，請看 [資料說明](docs/data_contracts.md)；README 只提供專案概況與執行入口。

現有樣本可查看 [2025-09-01 日表](data/cache/history_sample/2025-09/20261011T125021_603f0054/daily/2025-09/2025-09-01_prices.csv)、[2330 月表](data/cache/history_sample/2025-09/20261011T125021_603f0054/monthly/2025-09/TWSE_2330_2025-09.csv)、[5274 月表](data/cache/history_sample/2025-09/20261011T125021_603f0054/monthly/2025-09/TPEX_5274_2025-09.csv)。這些是本機快取連結，新 clone 需先下載；離線重新匯出也會建立另一版本目錄。

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
| [src/etf_agent/cli.py](src/etf_agent/cli.py) | 離線合約展示、歷史樣本下載與快取離線匯出命令 |
| [src/etf_agent/history.py](src/etf_agent/history.py) | 兩檔歷史樣本下載、每日／個股月 CSV 與快取離線匯出 |
| [tests/fixtures/contracts_demo.json](tests/fixtures/contracts_demo.json) | 人工測試行情、帳戶、草稿與研究設定 |
| [tests/test_contracts.py](tests/test_contracts.py) | 合約測試 |
| [specs/internal/agent_draft.schema.json](specs/internal/agent_draft.schema.json) | 內部 AgentDraft 格式，與官方 D-Plan 分開 |
| [specs/official/](specs/official/) | F01～F09 官方參賽參考來源 |

## 歷史資料與後續功能

合約已預留資料日、公開可知時間、實際抓取時間、原始內容雜湊及資料版本，讓日後回測能追查當時使用的資料。訓練、驗證、測試按時間切分，較新的測試期間預先保留。

fixture 的切分是說明用設定：2020～2023 訓練、2024 驗證、2025～2026-09 測試，並沒有對應的長期歷史資料。真正的交易日隔離、標籤跨界檢查、公司行動處理、回測與訓練尚未實作。

其他尚未完成：F05 白名單讀取、150 檔行情取得與完整清洗、精確且一致成交口徑、因子計算、真實 Codex／Claude 決策、配置與風控、官方股數與費用計算、D-Plan 結構／語意驗證、SQLite 帳務、成交與官方庫存核對。後續依合作規則逐批討論和驗收。

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
