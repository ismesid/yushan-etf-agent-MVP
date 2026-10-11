# 環境與基本使用

這份文件說明環境設定、基本命令、必要測試與版本管理；四角色資料重抓及真實模型入口另列於下方。整體架構見 [README](../README.md)。

## 環境設定

需要 Python 3.11 以上；行情、因子及帳戶核心使用標準庫，D-Plan 結構驗證另需 `jsonschema>=4.0,<5`。本次已建立 `.venv` 並安裝 jsonschema 4.26.0；新 clone 可從專案根目錄開啟 PowerShell 重建：

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
$env:PYTHONPATH = (Resolve-Path 'src').Path
.\.venv\Scripts\python.exe -B -m etf_agent.cli --help
```

`PYTHONPATH` 讓 Python 找到 `src/etf_agent`，設定只影響目前 PowerShell 工作階段；另開終端時重新設定。`-B` 避免執行時產生 Python 位元碼快取。

依賴安裝需要連網；執行離線決策準備或計畫編譯不另下載行情。CLI 共用的驗證入口需要 jsonschema，因此本頁 CLI 指令統一使用 `.\.venv\Scripts\python.exe -B`；純核心模組仍以標準庫為主。`.venv` 屬本機環境，不提交到 Git。`decide-plan` 另使用已安裝的 Codex CLI 與明確本機模型 ID，會呼叫真實模型並保存其實報用量。

各命令的個別參數可用 `--help` 查看，例如：

```powershell
.\.venv\Scripts\python.exe -B -m etf_agent.cli history-universe --help
.\.venv\Scripts\python.exe -B -m etf_agent.cli history-features --help
.\.venv\Scripts\python.exe -B -m etf_agent.cli history-rankings --help
.\.venv\Scripts\python.exe -B -m etf_agent.cli prepare-decision --help
.\.venv\Scripts\python.exe -B -m etf_agent.cli compile-plan --help
.\.venv\Scripts\python.exe -B -m etf_agent.cli build-demo-account --help
.\.venv\Scripts\python.exe -B -m etf_agent.cli refresh-decision --help
.\.venv\Scripts\python.exe -B -m etf_agent.cli decide-plan --help
```

下載命令的 `--transport auto` 優先使用系統既有 curl，否則使用 Python `urllib`；也可明確選 `curl` 或 `urllib`。都保留 HTTPS 憑證驗證，行情下載本身不依賴第三方 HTTP 套件。

## 合約示例

新 clone 可直接執行此命令，不需行情快取、不連網、不呼叫模型：

```powershell
.\.venv\Scripts\python.exe -B -m etf_agent.cli contracts-demo --fixture tests/fixtures/contracts_demo.json
```

示例載入六種核心合約（MarketSnapshot、AccountSnapshot、FeatureTable、AgentDraft、PortfolioProposal、ValidationReport），以及 DatasetSplitPlan 與 AgentResult。它展示 JSON 往返、帳戶市值／現金核對與資料格式，全部為人工測試資料。

預期重點：

```text
JSON 往返：PASS
持股：25 檔
現金：10,000,000 元
股票市值：90,000,000 元
NAV：100,000,000 元
現金＋股票市值核對：PASS
submission_ready：false
```

加入 `--json` 可輸出機器可讀摘要。fixture 中的因子與選股是假值，模型版本及用量為 null；這個命令沒有產生正式 D-Plan。

fixture 示範 2020～2023 訓練、2024 驗證、2025～2026-09 測試的時間切分設定，並沒有對應的長期歷史資料或已完成回測。詳見 [資料合約](data_contracts.md)。

## 白名單核對

```powershell
.\.venv\Scripts\python.exe -B -m etf_agent.cli universe-check --universe data/universe.csv
```

預期核對格式、檔數與來源雜湊 PASS：150 檔、TWSE 100／TPEX 50，代號無重複。來源是官方 F05 v1；[universe.csv](../data/universe.csv) 保存股票，配套 [manifest](../data/universe.manifest.json) 保存來源版本。

預設使用白名單同名 `.manifest.json`；`--manifest` 可指定其他來源紀錄，`--json` 可輸出摘要。競賽白名單不等於每個歷史日期的可投資股票池；歷史掛牌範圍仍需另外判斷。

## 必要測試

日常修改優先執行受影響的測試。從根目錄、已設定 `PYTHONPATH` 的 PowerShell 執行，例如：

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -p test_contracts.py -v
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -p test_features.py -v
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -p test_ranking.py -v
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -p 'test_*.py' -k CalendarTests -k HistoryWindowTests -v
```

上列分別驗核心合約、因子、排名、日曆與價格視窗；依當批修改選擇。只有跨模組或共用規則變更等需要整體確認時，才擴大執行：

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -p 'test_*.py' -v
```

這些是可重跑的指令，不表示每批都已跑過全套；實際結果與未執行範圍記在 [development_notes.md](../development_notes.md)。

## 產物與版本管理

程式、官方參考來源及白名單放在倉庫，解釋與操作文件集中在 `docs/`；行情與分析各次執行另建 `data/cache/<功能>/<月份或截止日>/<執行版本>/`，保存 CSV／JSON 結果。新產物不覆寫舊版本，下一個命令應使用剛產生的 manifest／報告 JSON 路徑。

新 `compile-plan`／`decide-plan` 的計畫階段另自動保存同名 Markdown，含市場理由、原／目標股數、委託、現金與驗證表格；路徑見輸出的 `plan_markdown` 或 `workspace.files.plan_markdown`。[可讀決策說明](daily_workflow.md#d-plan-markdown-怎麼閱讀)／[每日角色與待串接流程](daily_workflow.md)。

[.gitignore](../.gitignore) 忽略 `data/cache/`、真實帳戶 `data/account/`、執行產物、資料庫、日誌、金鑰與本機設定。文件所列快取路徑供本機查閱，GitHub 的可點擊入口連到倉庫內的說明；需要重建時依序使用 [歷史資料](history_data.md)、[日曆／視窗](calendar_windows.md)、[三因子分析](factor_analysis.md)、[加權排名](ranking.md)。

每次提交前先檢查差異，明確加入本批檔案；以下只是合約與文件修改的示例：

```powershell
git status
git diff
git add src/etf_agent/contracts.py docs/data_contracts.md development_notes.md checklist.md
git commit -m "Update contracts and development notes"
git push
```

`git push` 需已設定 GitHub 遠端與分支追蹤關係。金鑰、真實帳戶及大量行情快取保留在忽略的位置。

CLI 的一般退碼為 0 成功、2 輸入或執行失敗；`compile-plan` 在可編譯但驗證 BLOCK 時為 exit 4，保存候選及診斷。下載及覆蓋命令對缺資料的解讀不同，詳見 [歷史資料](history_data.md) 與 [價格視窗](calendar_windows.md)。

## 四角色決策準備與編譯

已有本次九月排名及完整歷史來源時，先用 `prepare-decision` 整理 data_agent、test_agent、account_agent 的回報、共用 `workspace.json` 及主 ETF Agent 證據包。已有模型或 fixture 草稿後，再用 `compile-plan` 計算股數與驗證 D-Plan，參數及產物詳見 [決策流程](decision_workflow.md)。兩個命令都不讀 10/1 行情，也不更新原帳戶。

沒有真實模型執行 metadata 時只產生可診斷的候選計畫，不能補假模型名稱／版本以通過 schema；真實決策使用下方 `decide-plan`。正式資料資格仍未核實，即使 demo 結構／語意驗證通過也不代表可提交。

`refresh-decision` 重新取得九月資料並建立新的共享 run，命令本身不刪除快取；刪除依本批明確授權另行處理。D-Plan 及真實決策封存之前仍禁止下載或讀入 10/1 行情。

第 22 批已用人工權重草稿與真實 9/30 前收完成離線編譯：組合檢查通過、缺真實模型 metadata 而 schema BLOCK，CLI exit 4，候選與診斷均保存。共 30 項相關測試通過，未跑全套；固定 run、金額及可重跑命令見 [本批實跑與驗收](decision_workflow.md#第-22-批實跑與驗收)。

## 重新取得九月資料並呼叫真實模型

這是完整重建九月資料的入口，會連網取得 147 檔九月行情，但沒有模型呼叫。第 23 批已完成重抓，新弱期初批次重用保留的行情與排名，不需再次下載；既有三檔無九月行情保留原因、不重新請求，7750 的九月資料正常下載：

```powershell
$env:PYTHONPATH = (Resolve-Path -LiteralPath 'src').Path
.\.venv\Scripts\python.exe -B -m etf_agent.cli refresh-decision --month 2025-09 --as-of 2025-09-30 --trade-date 2025-10-01 --account tests/fixtures/account_demo_2025-09-30.json --calendar data/cache/calendar/2025-09/20261011T154421_1306c9a4/calendar.json --output data/cache/integrated_runs
```

使用命令實際顯示的 `run_root` 與新 `evidence_packet.json` 路徑，讓下一步計畫留在同一 shared run。下列變數是待替換的路徑示例，不能直接指向舊資料包：

```powershell
$sharedRun = 'data/cache/integrated_runs/2025-10-01/<本次run>'
$packetPath = '<refresh-decision顯示的新evidence_packet.json路徑>'
.\.venv\Scripts\python.exe -B -m etf_agent.cli decide-plan --packet $packetPath --output "$sharedRun/plans" --team-id DEMO --model gpt-5.6-sol --max-attempts 2
```

`decide-plan` 使用凍結資料、提示與 schema，真實呼叫 Codex；本批呼叫合計最多兩次，保存實際模型 ID、用量、原始回覆及驗證結果。未知資訊不補值，使用工具或改動固定輸入的結果會被拒絕。本地配置／結構／語意通過才保存 demo D-Plan，正式資格始終為 false。詳細資料索引與失敗診斷見 [整合操作](decision_workflow.md#重新取得九月資料與真實決策)。

第 23 批歷史刷新為 147 次請求、0 cache hits、146 檔排名，前版本 25 檔帳戶與 10 億元 NAV 的差額為 0。第一次模型請求因服務端不支援設定模型而 HTTP 400，未取得投資決策；唯讀核對可用模型後，第二次以 `--model gpt-5.6-sol --max-attempts 1` 使用剩餘額度，成功回覆 25 檔全部續抱。模型實報 input 145,146／output 3,976 tokens，reasoning 232／cached 0。

首次自動編譯遇到 Windows 深層目錄長度限制，沿同一份真實原始回覆改短輸出路徑離線重編，沒有再次呼叫模型。當時封存計畫為 `data/cache/integrated_runs/2025-10-01/20261011T181709_8585216a/final/2025-10-01/20261011T182555_b8b2869e/D-Plan_DEMO_2025-10-01.json`：結構／語意／本地驗證均通過，25 檔不交易、0 筆委託，現金 109,109,400 元、NAV 10 億元。本批清理舊決策後，該路徑只是歷史紀錄，不能用作新弱期初的結果。正式與提交旗標仍為 false。

`--model` 只覆寫本次 CLI，不改全域設定；上方 `max-attempts 2` 是一般入口範例，不能當成本批已有兩次額度之外再呼叫的授權。實際紀錄與用量見 [第 23 批紀錄](decision_workflow.md#第-23-批刷新實跑與模型狀態)。D-Plan 已封存，後續 10/1 行情、成交／效益驗證與帳務更新仍需下一批明確授權。

## 弱期初與 CSV 檢視

新批次用保留的 9/30 綜合排名末 25 檔建立人工弱期初。NAV 仍為 10 億元，每股預算 3,600 萬元、按 9/30 前收取整張，現金是精確餘額；不改因子權重、不把模型換股當成必要結果：

```powershell
$rankingMetadata = 'data/cache/integrated_runs/2025-10-01/20261011T181709_8585216a/rankings/2025-09-30/20261011T182031_a7d53013/metadata.json'
.\.venv\Scripts\python.exe -B -m etf_agent.cli build-demo-account --ranking-metadata $rankingMetadata --as-of 2025-09-30 --output data/cache/demo_accounts --account-output tests/fixtures/account_demo_2025-09-30.json
```

`--account-output` 本批明確覆寫這份 demo fixture，snapshot 身分含 `WEAK`；詳見 [帳戶建構](account.md#建立弱期初帳戶)。清理限舊決策包／草稿／原始回覆／計畫，新九月 `market`、視窗、因子、排名、日曆及官方來源保留。共享 run 的帳戶副本與 workspace 更新，新證據包按新 snapshot 重新凍結；再將實際新包路徑交給 `decide-plan`。

提示澄清：正式資格待核實仍阻擋提交，單獨不禁止本地歷史 demo 交易。續抱或換股以給定因子、候選比較及完整帳戶為依據，沒有強制換股名單或最低委託數。新模型實跑已完成：一次gpt-5.6-sol回覆、15退出／10新買／10續抱、25筆委託與目標20檔，結構／本地語意通過；詳見 [第24批驗收](decision_workflow.md#第-24-批弱期初重新決策實跑)。

角色結果附 `data_candidates.csv`、`data_issues.csv`、`account_positions.csv`、`account_summary.csv`、`review_status.csv`、`review_recommendations.csv`；主決策與計畫附 `agent_decisions.csv`、`orders.csv`、`portfolio_positions.csv`、`portfolio_summary.csv`、`validation_checks.csv`。CSV 使用 UTF-8 BOM，股數為股、金額為元、比率為 0～1，null 留空，沒有建議或委託時只有欄名。JSON 合約與版本仍保存，檔案用途見 [CSV 說明](decision_workflow.md#csv-檢視各角色結果)。

重用本次九月資料準備新帳戶輸入（不連網或呼叫模型）：

```powershell
$taskSharedRun = 'data/cache/integrated_runs/2025-10-01/20261011T181709_8585216a'
.\.venv\Scripts\python.exe -B -m etf_agent.cli prepare-decision --account tests/fixtures/account_demo_2025-09-30.json --ranking-metadata "$taskSharedRun/rankings/2025-09-30/20261011T182031_a7d53013/metadata.json" --as-of 2025-09-30 --trade-date 2025-10-01 --workspace-root $taskSharedRun
```

`--workspace-root` 更新帳戶副本、四角色報告／六CSV及共享索引，模型輸入全部重新凍結。它不自行刪除舊決策；本批實際清理按使用者明確指示執行。新的 `workspace.json` 提供 evidence_packet 路徑，傳給上方 `decide-plan` 會產生新的模型呼叫，勿將它當成離線重播。

## 封存後的隔離評估

第25批已授權test_agent取得10/1單日行情，只存隔離區，核算原計畫／不交易收益及146候選事後配置。首次需已授權的SciPy額外依賴；重播用明確隔離 `market_manifest.json`，不新下載或呼叫模型。指令、單位、無成交保留、8份CSV與限制集中在 [隔離評估](evaluation.md)，不要用 `prepare-decision` 改寫已封存的首日输入。
