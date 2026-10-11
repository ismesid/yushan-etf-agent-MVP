# 帳戶匯入與歷史市值核對

文件版本：1.2｜更新：2026-10-11｜AccountSnapshot 合約版本：1.0

`account-check` 匯入一份獨立帳戶 JSON，用指定資料日的既有歷史收盤價核對全部原持股、現金與 NAV（帳戶淨資產）。帳戶與排名共用日期，原持股即使缺行情或未參與排名也必須保留。`prepare-decision` 的 account_agent 再將核對結果整理成主 Agent 的完整帳戶回報；這兩個入口都不成交、不扣款、不更新帳務。

## demo 的日期與資金

本次 [account_demo_2025-09-30.json](../tests/fixtures/account_demo_2025-09-30.json) 為 **2025-09-30、10 億元 NAV 的人工弱期初 demo 帳戶**。新批次將此檔改為同日三因子綜合排名末 25 檔，snapshot 身分明示 `WEAK`，讓主 ETF Agent 面對價格因子較弱的既有持股，自行比較續抱、調整與退出。價格來自已重新取得的官方九月月報，持股與現金由程式人工建構，沒有取得官方期初庫存。

10 億元金額依本次查到的 [清華大學轉載競賽公告](https://dsa.site.nthu.edu.tw/p/406-1266-314652,r6890.php?Lang=zh-tw)。競賽官網本次回傳 403，金額依轉載內容採用，不能因此宣稱帳戶已由主辦方確認。[F07 v4.2 指南](../specs/official/07_D-Plan_guide_v4.2.md) 的 decisions／orders 另列持股數、個股權重、現金比及整張限制。

這份 demo 的建構算式是：

```text
每股預算 = 1,000,000,000 元 × 90% ÷ 25 = 36,000,000 元
人工持股 = floor(36,000,000 ÷ 9/30 收盤價 ÷ 1000) × 1000 股
現金 = 1,000,000,000 元 − 所有人工持股的 9/30 收盤市值
```

綜合末 25 名、90% 與每股同預算只用來建構這份演示壓力情境，不是投資配置或預先指定模型的選股。三因子權重仍是原本 40%／25%／35%。模型不參與期初股數建構，後續自主決定續抱、調整或換股，程式才依目標權重換算最終股數。弱排名並不保證下一日報酬差，也不代表模型必須交易。

## 建立弱期初帳戶

`build-demo-account` 讀取明確的 9/30 排名 metadata，取完整排名末 25 檔，再核對每檔的同日有效前收，按上方整張算式建構 AccountSnapshot 1.0。選定股票缺價、預算不足一張或資料不符時阻擋，不另選其他股票或補值。它保存建構與估值結果，並將指定 fixture 寫成新 snapshot；只使用九月排名與收盤，不取 10/1 行情、不呼叫模型：

```powershell
$env:PYTHONPATH = (Resolve-Path -LiteralPath 'src').Path
$rankingMetadata = 'data/cache/integrated_runs/2025-10-01/20261011T181709_8585216a/rankings/2025-09-30/20261011T182031_a7d53013/metadata.json'
.\.venv\Scripts\python.exe -B -m etf_agent.cli build-demo-account --ranking-metadata $rankingMetadata --as-of 2025-09-30 --output data/cache/demo_accounts --account-output tests/fixtures/account_demo_2025-09-30.json
```

此命令的 `--account-output` 明確指定寫入檔案，本批已授權以新弱期初覆寫該 demo fixture。舊 `contracts_demo.json` 保留原合約示例。新帳戶已實跑：第122～146名、25檔，其中24檔動能負、22檔低於均線；股票892,932,500元＋現金107,067,500元＝NAV1,000,000,000元，差額0，基本期初檢查通過。

本機建構證據在 `data/cache/integrated_runs/2025-10-01/20261011T181709_8585216a/initial_account/2025-09-30/20261011T183759_84fc3293/`。例如末名6919持有194,000股、9/30前收185.50元、市值35,987,000元；CSV保留原因子與排名，可人工核對弱股選法。後續真模型自主退出15檔、新買10檔、續抱10檔，詳見 [最新決策](decision_workflow.md#第-24-批弱期初重新決策實跑)；本帳戶fixture仍是期初，沒有入帳成目標20檔。

`--output` 預設 `data/cache/account_demo`，另建 `<as_of>/<run>/`，保留四份產物：

| 檔案 | 用途 |
|---|---|
| `account_snapshot.json` | 新人工期初的完整帳戶 JSON。 |
| `initial_positions.csv` | 末 25 名的因子、排名、預算、整張股數、前收、市值與來源；UTF-8 BOM。 |
| `construction.json` | 選取方法、算式、輸入與產物 hash、版本及 demo 限制。 |
| `valuation.json` | 完整市值／NAV 核對與基本期初檢查。 |

只有完整估值與基本條件皆通過才輸出成功 demo。建構限 2025-09-30，缺行情、排名不連續或身分／hash 等不符回傳 exit 2，不用人工調股數通過驗收。

## 前版本期初的歷史對照

新弱期初之前，2026-10-11 的前版本沿用舊 fixture 的 25 個代號，`account-check` 曾完成估值、exit 0。以下是那份歷史對照，並非目前弱期初的估值：

| 項目 | 實跑結果 |
|---|---:|
| 股票總市值 | 890,890,600.00 元 |
| 現金 | 109,109,400.00 元 |
| 輸入／計算 NAV | 1,000,000,000.00 元 |
| 計算 NAV－輸入 NAV | 0.00 元 |
| 現金占計算 NAV | 10.91094% |
| 基本期初條件 | 通過；25 檔、白名單、個股上限及現金範圍相符 |
| 資料問題 | 0 BLOCK、75 WARN |

逐股摘錄，股數均為這份人工 demo 的輸入：

| 股票 | 股數 | 9/30 收盤（元／股） | 市值（元） |
|---|---:|---:|---:|
| 2330 台積電 | 27,000 | 1,305.00 | 35,235,000.00 |
| 5274 信驊 | 7,000 | 5,050.00 | 35,350,000.00 |
| 2891 中信金 | 839,000 | 42.90 | 35,993,100.00 |

前版本的 2330 市值占輸入 NAV 為 3.5235%。25 檔人工股數均已核對為整張；75 個 WARN 是每檔各自的歷史公開時間、公司行動及正式可交易資格未核實，算式及基本條件通過仍保留這些限制。當次本機產物路徑是 `data/cache/account_checks/2025-09-30/20261011T172216_f175f6cb/`，沒有作 GitHub 導航連結；目前 fixture 已改用弱期初時，重跑會得到新帳戶結果。

舊 [contracts_demo.json](../tests/fixtures/contracts_demo.json) 保持 **2026-10-14、假價、1 億元 NAV**，供共用合約展示。不能將舊日期／股數／NAV 直接接到此次 9/30 排名與歷史收盤。

## 帳戶輸入格式

輸入 JSON 直接包含一份 AccountSnapshot，不需外層 `account_snapshot`、其他合約或行情。完整可執行例子使用上方新 fixture；必要欄位如下：

| 欄位 | 格式與用途 |
|---|---|
| `contract_version` | `"1.0"`，沿用既有合約。 |
| `snapshot_id` | 非空字串，辨識這份完整帳戶。 |
| `as_of_trade_date` | `"2025-09-30"`；須與 `--as-of`、排名與日表日期一致。 |
| `status`、`demo`、`reconciled` | 本次為 `"demo"`、`true`、`false`；估值相符後仍保持原標記。 |
| `cash_twd`、`nav_twd` | 新臺幣元、十進位字串；例如 NAV `"1000000000.00"`。 |
| `positions` | 完整原持股陣列；每列只有 `ticker` 四位字串與 `shares` 正整數，股數單位為股。零持股省略。 |
| `origin`、`origin_ref` | 人工來源說明及可選引用；demo 的引用不能充作官方核對證據。 |

載入拒絕未知欄位、缺必要欄位、重複股票、布林值冒充股數、非整數股數、NaN／Infinity 或不合法日期。現金須非負且不大於 NAV，NAV 須大於零。合約也有 projected、simulated、official_confirmed 狀態，詳見 [資料合約](data_contracts.md#帳戶與庫存)；匯入器只核對欄位，不登入主辦方系統查證。

## 收盤來源與估值方式

命令讀指定 `ranking-metadata`，核對其所引用的歷史 manifest 與當日日表。只載入 `--as-of` 對應的一份日表，不合併 monthly、不掃所有快取、不讀下一交易日資料，也不要求每檔原持股都在排名內。

來源檢查涵蓋日期與輸入 hash、F05 白名單及市場、日表重複、`price_valid`、正收盤價，以及 `source_key`／`data_version` 與 manifest 的對應；資料不符列入診斷。來源網址與版本仍沿 manifest 回查。

閱讀日表的 `close_raw_ktwd_per_lot` 是千元／張，核心估值用元／股。因 1 張＝1000 股、1 千元＝1000 元，兩種價格的數值相同；市值以 **元／股 × 股數** 計算，不另乘 1000。例如 9/30 的 2330 收盤為 1305.00，若以說明用 1000 股估值，就是 1,305,000.00 元；這個 1000 股例子不是整份 demo 的持股。

全部原持股均有可用收盤時：

```text
逐股市值 = 原持股股數 × 指定日原始收盤（元／股）
全股票市值 = 所有逐股市值之和
計算 NAV = 帳戶現金 + 全股票市值
NAV 差額 = 計算 NAV − 輸入 NAV
```

Decimal 以 50 位計算精度、`ROUND_HALF_EVEN` 計算市值與比率，不用浮點數比對金額，也不從 CSV 顯示值反算 NAV。股權重以輸入 NAV 作分母，現金比以計算 NAV 作分母。`nav_tolerance_twd="0"` 表示本次 demo 算術核對要求差額為零，是本地核對設定，不是正式結算容差；差額正值表示重算值高於輸入 NAV。估值等式相符不等於實際成交結果或官方帳務核對。

歷史原價可供這次 demo 估值；`known_at` 尚未核實、公司行動及正式可交易資格仍待確認。這些限制保留於報告，不填造公開時間或生成正式 MarketSnapshot。基本期初檢查包含白名單、持股 20～30 檔、2330 權重≤25%、其餘個股≤10%、現金比 0～25%。原持股的正整數股數可含零股，匯入與估值保留原數量；整張是本次 demo 的建構選擇，委託整張限制留到交易批次檢查。檢查通過只表示本次估值與這些基本條件相符，沒有完成委託、費用、證據鏈、正式資格或 D-Plan 驗證。

## 執行方式

已有 9/30 排名與其來源快取時，從專案根目錄執行：

```powershell
$env:PYTHONPATH = (Resolve-Path -LiteralPath 'src').Path
.\.venv\Scripts\python.exe -B -m etf_agent.cli account-check --account tests/fixtures/account_demo_2025-09-30.json --ranking-metadata data/cache/integrated_runs/2025-10-01/20261011T181709_8585216a/rankings/2025-09-30/20261011T182031_a7d53013/metadata.json --as-of 2025-09-30 --output data/cache/account_checks
```

`--account`、`--ranking-metadata`、`--as-of` 必填；`--output` 預設 `data/cache/account_checks`。`--universe` 預設 `data/universe.csv`，可用 `--universe-manifest` 指定其來源紀錄；`--json` 輸出 `{ "report": ..., "outputs": ... }`，包含完整報告與產物路徑。替換排名路徑時應使用同日期的實際產物。需要本機既有歷史快取，新 clone 不自帶 `data/cache/`；資料重建入口見 [歷史資料](history_data.md) 與 [排名](ranking.md)。

命令完全離線，帳戶核心使用 Python 標準庫；CLI 共用入口另需已安裝的 jsonschema，環境見 [基本使用](quickstart.md)。本命令不安裝依賴、不下載行情、不呼叫模型、不修改輸入帳戶／策略參數，也不 commit／push。

## 輸出與資料問題

每次另建 `data/cache/account_checks/<as_of>/<執行版本>/`，CLI 顯示本次路徑，僅保存 CSV／JSON：

| 檔案 | 用途 |
|---|---|
| `account_snapshot.json` | 保存本次輸入的完整帳戶與原有 demo／核對狀態，供下游引用。 |
| `positions.csv` | 每股代號、股數、收盤與市值，以及來源／估值狀態；缺行情的原持股仍在。 |
| `valuation.json` | 現金、已估值小計、全股票市值、輸入／計算 NAV、差額、基本檢查、資料問題與輸入版本。 |

`valuation.json` 的主要金額欄位為 `cash_twd`、`known_stock_value_twd`（已估值小計）、`stock_value_twd`（完整股票市值）、`input_nav_twd`、`calculated_nav_twd`、`nav_difference_twd`。`valuation_ok` 是算術與資料核對結果，`initial_constraints.passed` 是基本期初條件；兩者分開保存，CLI 必須兩者通過才回傳 0。逐股 `weight_of_input_nav` 是市值占輸入 NAV 的比率，`cash_ratio` 是現金占計算 NAV 的比率。

缺原持股行情時，該股價格與市值為 JSON `null`、CSV 空欄；已估值小計保留，完整全股票市值、計算 NAV、NAV 差額為 `null`，並列 BLOCK。不能將缺價視為零、刪掉持股，或將部分小計當成完整 NAV。

帳戶日期／NAV 不符保存診斷並回傳 exit 2；正常完整估值、NAV 相符且基本期初檢查通過，回傳 exit 0。可解析的日表列錯誤轉成 BLOCK，隨估值診斷保存。輸入檔缺失、AccountSnapshot 無法載入，或 ranking／manifest 的 scope、日期、hash、來源身分不符時，讀取器回報 AccountError，CLI exit 2 且不建立估值報告；不能將來源未核對的行情交給下游。

成功的 demo 仍維持 `demo=true`、`reconciled=false`、`submission_ready=false`。本機 CSV／JSON 是可檢查的產物，GitHub 說明以本頁為入口，不連到被忽略的快取檔案。

## 必要驗收與後續

本批 [test_account.py](../tests/test_account.py) 七項測試已實際通過，涵蓋：

- 正常元／股與股數估值，保留 demo 身分，分開顯示算術核對與基本持股檔數條件。
- 帳戶日期或 NAV 不符，保存診斷並保持輸入原值。
- 行情不存在、收盤空值或價格旗標無效，原持股與股數仍在，完整 NAV 留空。
- 限制行情讀取為排名 metadata、manifest、9/30 唯一日表，攔下 scope／日期／白名單版本、hash 與來源身分不符。
- 25 檔報告新建版本、保存三個產物，不覆寫輸入與舊執行。
- CLI 成功、NAV 差額及缺輸入檔，顯示真實診斷並回傳正確退碼。
- 錯日期列不能覆寫指定日收盤；零計算 NAV 保留差額診斷，現金比留空，避免除零。

通用未知欄位／股數等合約檢查，以及日表重複／市場等檢查，重用既有 contracts／coverage 實作；本批沒有重新執行所有既有測試。可重跑本批相關測試：

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -p test_account.py -v
```

本批七項測試通過（0.412s）；真實歷史收盤 demo 核對 exit 0，固定數值見上方表格。執行證據另記於 [development_notes.md](../development_notes.md)，完成證據記在 [checklist.md](../checklist.md)。

後續按下列資料流銜接：

1. 完整帳戶與歷史估值，保留全部原持股。
2. 候選資格／流動性，再將排名、資料截止與可回查來源整理成證據包。
3. 以 **2025-10-01 決策日、2025-09-30 資料截止** 呼叫真實 Agent，檢視續抱／換股並提出目標權重；WeightedAgentDraft 2.0、真實 Codex 入口已串接，弱期初的新結果另記。
4. 程式按官方方法換算股數、檢查完整配置／風控、驗證並封存 D-Plan 與輸入版本；模型不直接修改 shares 或帳戶。
5. 取得新授權後才下載或讀入 10/1 行情，實作效益／成交帳務驗證。

在第 4 步封存完成前，不下載或讀入 10/1 行情。帳戶模組只匯入與估值，不抓 API、不替模型決策，也不將 demo 變成官方已確認帳戶。

核心入口在 [account.py](../src/etf_agent/sub_agents/account_agent/account.py)：`load_account_json()`、`load_history_closes()`、`value_account()`、`analyze_account()`、`write_account_report()`；人工弱期初另用 `build_weak_demo_account()` 與 `write_weak_demo_account()`。CLI 只組合這些模組，後續 UI／排程可重用相同函式。

## account_agent 帳戶回報

入口位於 [account_agent/agent.py](../src/etf_agent/sub_agents/account_agent/agent.py)。`prepare_account(account_path, price_context, *, as_of)` 負責匯入完整帳戶、使用共用截止日行情計算估值，接續純函式 `report_account(account_snapshot, valuation, *, as_of)` 核對並回報。它沿用 AccountSnapshot 1.0，不從網路取價，也不呼叫模型；由 [決策資料包](decision_workflow.md) 的 `prepare-decision` 保存為 `account_report.json`。data_agent 已不再計算帳戶估值，跨日原計畫入帳見 [每日串接計畫](daily_workflow.md)。

回報保留輸入的 `snapshot_id`、日期、`status`、`demo`、`reconciled`、`origin`／`origin_ref`，並提供現金、NAV、`current_positions` 的全部代號、股數、價格、市值、權重與來源。`account_valid` 要求估值、基本期初限制、日期／完整快照身分、現金／NAV 及完整股數均相符且沒有 BLOCK。日期或來源帳戶不符時，不挪用另一份估值；缺價仍保留持股與股數，價格及市值為 null。

以前版本人工帳戶為例，回報 `cash_twd="109109400.00"`、`nav_twd="1000000000.00"`，完整 25 檔持股仍在。弱期初回報應使用新 snapshot 的實際現金與股數。`estimated_available_cash_twd` 是 demo 現金減去明示零保留額的估算，不是主辦方的可用額度：

| 欄位 | 目前含義 |
|---|---|
| `estimated_available_cash_twd` | demo 帳戶等於輸入現金；非 demo 為 null。 |
| `available_cash_twd` | null，尚未核對正式額度。 |
| `reservations_twd` | `"0"`，只是此次演示估算假設。 |
| `reservation_status` | `"not_implemented"`，委託資金保留尚未實作。 |

此角色目前是快照／回報介面，不能稱為已完成每日帳務控管。成交均價、費用入帳、委託保留、交割、帳務資料庫及新一日帳戶快照仍待後續批次；編譯器的前收交易估算也不會改寫這份帳戶。主 ETF Agent 只能提出決策，不可直接修改現金或股數。

決策資料包另提供 `account_positions.csv` 與 `account_summary.csv`，方便在 Excel 檢視全部原持股和現金／NAV。CSV 使用 UTF-8 BOM；股數單位為股、金額為新臺幣元、價格為元／股，權重與現金比為 0～1 比率，null 顯示空欄。JSON 仍保存完整帳戶合約、來源、檢查與版本；CSV 不改變股數或帳務狀態。其餘角色與主決策 CSV 見 [決策流程](decision_workflow.md#csv-檢視各角色結果)。

[test_account_agent.py](../tests/test_account_agent.py) 四項測試通過：10 億元完整回報、缺價保留股數、日期／身分／股數／NAV 不符阻擋，以及不能將估算冒充正式可用資金。測試使用人工價格，不讀決策日行情。

2026-10-11 第 22 批重新準備決策資料，run 為 `data/cache/decision_packets/2025-10-01/20261011T180724_e49e57e2/`。當次 `account_report.json` 回報現金／demo 估算可用資金各 109,109,400 元、NAV 10 億元、25 檔完整持股，`account_valid=true`，並保存帳戶來源 hash。計畫編譯另有交易後投影，但原帳戶現金與股數不變；詳細編譯驗收見 [第 22 批實跑](decision_workflow.md#第-22-批實跑與驗收)。
