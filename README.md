# 玉山 AI CUP：AI Agent 主動型 ETF MVP

目標是在約 8 小時內完成可供開會檢查的 ETF 決策流程，並方便增加資料源、因子、模型與 UI。目前完成第一批：共用資料合約與離線示例，完整投資流程仍在開發。

## 目前功能

- 六種核心合約：`MarketSnapshot`、`AccountSnapshot`、`FeatureTable`、`AgentDraft`、`PortfolioProposal`、`ValidationReport`。
- `AgentProvider` 共同介面與 `AgentResult`，保留實際模型資訊及用量欄位。
- `DatasetSplitPlan`：按時間保留訓練、驗證、測試期間，檢查日期順序與不重疊。
- 含 25 檔既有持股的人工測試帳，以及離線 CLI 合約展示。
- 30 項 `unittest`；第一批驗收結果為全部通過，證據見 [開發紀錄](development_notes.md)。

**示例的行情、因子、帳戶與 Agent 草稿都是人工測試資料。** 沒有真實行情下載或投資模型呼叫；示例固定為 `submission_ready=false`，未知模型版本與用量為 `null`。

## 執行方式

需要 Python 3.11 以上。目前執行示例與測試只使用標準庫，不需安裝第三方套件。

專案使用 `src` 目錄配置。從專案根目錄開啟 PowerShell，設定 Python 模組路徑後執行：

```powershell
$env:PYTHONPATH = (Resolve-Path 'src').Path
python -B -m etf_agent.cli --help
python -B -m etf_agent.cli contracts-demo --fixture tests/fixtures/contracts_demo.json
python -B -m unittest discover -s tests -p test_contracts.py -v
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

## 文件與程式導覽

| 路徑 | 內容 |
|---|---|
| [AGENTS.md](AGENTS.md) | 分批討論、實作與驗收的合作規則 |
| [design1001.md](design1001.md) | 架構與策略草案；其中待建立的命令不代表已實作 |
| [checklist.md](checklist.md) | 待辦、完成證據與正式輸出阻擋條件 |
| [diary.md](diary.md) | 簡明的討論、決定及原因 |
| [development_notes.md](development_notes.md) | 各批授權、實際修改、驗收與下一步 |
| [docs/data_contracts.md](docs/data_contracts.md) | 共用欄位、單位、時間、研究切分與示例說明 |
| [src/etf_agent/contracts.py](src/etf_agent/contracts.py) | 核心合約及輸入檢查 |
| [src/etf_agent/agent/base.py](src/etf_agent/agent/base.py) | 模型 provider 介面與結果格式 |
| [src/etf_agent/cli.py](src/etf_agent/cli.py) | 已實作的離線合約展示命令 |
| [tests/fixtures/contracts_demo.json](tests/fixtures/contracts_demo.json) | 人工測試行情、帳戶、草稿與研究設定 |
| [tests/test_contracts.py](tests/test_contracts.py) | 合約測試 |
| [specs/internal/agent_draft.schema.json](specs/internal/agent_draft.schema.json) | 內部 AgentDraft 格式，與官方 D-Plan 分開 |
| [specs/official/](specs/official/) | F01～F09 官方參賽參考來源 |

## 歷史資料與後續功能

合約已預留資料日、公開可知時間、實際抓取時間、原始內容雜湊及資料版本，讓日後回測能追查當時使用的資料。訓練、驗證、測試按時間切分，較新的測試期間預先保留。

fixture 的切分是說明用設定：2020～2023 訓練、2024 驗證、2025～2026-09 測試，並沒有對應的長期歷史資料。真正的交易日隔離、標籤跨界檢查、公司行動處理、回測與訓練尚未實作。

其他尚未完成：F05 白名單讀取、TWSE／TPEx 行情抓取與清洗、因子計算、真實 Codex／Claude 決策、配置與風控、官方股數與費用計算、D-Plan 結構／語意驗證、SQLite 帳務、成交與官方庫存核對。後續依合作規則逐批討論和驗收。

## 日常版本管理

每次完成一批，先查看差異，再加入本批指定檔案。以下用合約和文件修改作例子：

```powershell
git status
git diff
git add src/etf_agent/contracts.py docs/data_contracts.md diary.md development_notes.md checklist.md
git commit -m "Update contracts and development notes"
git push
```

`git push` 需已設定 GitHub 遠端與目前分支的追蹤關係。金鑰、本機設定、真實帳戶與大量行情快取應保留在未追蹤位置；提交前檢查 `git status` 和差異內容。

`specs/official/` 附件保留為本專案參賽參考來源，不因納入版本管理而宣稱具有開源授權。本專案目前未指定開源授權。
