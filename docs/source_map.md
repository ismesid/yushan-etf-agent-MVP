# 程式與文件索引

這份索引說明倉庫內各檔案的內容、責任及使用入口。整體架構與閱讀順序見 [README](../README.md)，環境及命令參數見 [基本使用](quickstart.md)，執行後的 JSON／CSV 與版本索引見 [產物導覽](artifacts.md)。本頁不列本機快取路徑。

目前使用單一 Python 專案，由 CLI 組合函式。`sub_agents` 是分工模組；真實投資模型呼叫集中在 `decision/providers/codex_cli.py`。尚未建立每日常駐排程、通用增量資料合併、正式交割帳務或自動提交。已有隔離收益評估與事後最佳化，但其結果不回寫原決策，也不等同正式 D-Plan。

本次整合及真實決策入口限定 `as_of=2025-09-30`、`trade_date=2025-10-01`。因子／排名使用截至 9/30 的價格視窗，帳戶與配置使用 9/30 前收；封存後才由隔離評估讀取 10/1 單日行情，按當日均價模擬交易、按當日收盤估值。主決策輸入與後驗評估資料各自保存。

## 先找到對應文件

| 文件 | 存什麼 | 什麼時候看 |
|---|---|---|
| [quickstart.md](quickstart.md) | Python 環境、CLI 使用、必要測試與版本管理。 | 第一次設定環境，或尋找可重跑命令。 |
| [data_contracts.md](data_contracts.md) | 共用資料型別、日期／金額／來源單位、已實作檢查及限制。 | 串接新模組、讀取 JSON 或新增欄位之前。 |
| [history_data.md](history_data.md) | 官方月行情下載、快取重用、離線匯出與覆蓋檢查。 | 使用 `history-*` 下載／匯出入口或 `prices-check`。 |
| [history_availability_2025-09.md](history_availability_2025-09.md) | 2025-09 四檔缺件的既有核實紀錄與原因。 | 解讀缺件；保留既有原因，不重新查核或補值。 |
| [calendar_windows.md](calendar_windows.md) | 官方開休市排程、交易日與 21 筆價格視窗。 | 使用 `calendar-download`、`history-window-check`。 |
| [factor_analysis.md](factor_analysis.md) | 三因子公式、數值解讀、權重研究與資料限制。 | 使用 `history-features`，或討論因子依據。 |
| [ranking.md](ranking.md) | 排名方向、百分位、分數貢獻與排名設定。 | 使用 `history-rankings`，或比較候選分數。 |
| [account.md](account.md) | 帳戶 JSON、歷史市值／NAV 核對、弱期初及帳戶角色報告。 | 使用 `account-check`、`build-demo-account`。 |
| [decision_workflow.md](decision_workflow.md) | 角色分工、凍結證據包、真實模型入口、配置／編譯／驗證。 | 使用 `prepare-decision`、`refresh-decision`、`decide-plan`、`compile-plan`。 |
| [daily_workflow.md](daily_workflow.md) | 每日角色順序、前日行情／原計畫帳戶／檢討的日期邊界、D-Plan Markdown與待串接批次。 | 理解整理後架構與下一日循環設計。 |
| [evaluation.md](evaluation.md) | 封存後單日行情、模擬收益、事後最佳化及隔離限制。 | 理解既有 `evaluate-plan` 入口與評估結果。 |
| [artifacts.md](artifacts.md) | 各階段產物的內容、讀取方式及版本／hash 關係。 | 檢查一次執行的 JSON、CSV、workspace 或 manifest。 |
| [source_map.md](source_map.md) | 本頁：實際程式、配置、規格、測試及文件逐檔索引。 | 從命令或功能找實作位置。 |
| [assets/architecture.svg](assets/architecture.svg) | README 嵌入的架構與資料流圖，呈現共用模組、主決策及隔離評估邊界。 | 點開看完整圖；修改此 SVG 即更新 README 引用的同一張圖。 |

## 核心流程模組

三個 agent 各自擁有一個資料夾；只由單一角色使用的程式跟著角色放，共用合約、行情讀取、日曆、檢查與輸出放在外層。CLI與主流程負責組合角色，角色不自行呼叫投資模型。表中的命令參數見對應操作文件。

### 主 ETF 決策與組合流程

| 檔案 | 責任／內容 | 怎麼用／由誰呼叫 |
|---|---|---|
| [cli.py](../src/etf_agent/cli.py) | 命令參數、模組呼叫、摘要與退碼。 | `python -m etf_agent.cli <命令>`；[基本使用](quickstart.md)。 |
| [pipeline.py](../src/etf_agent/pipeline.py) | 九月下載、分析與角色報告整合；另可重用指定shared run並替換帳戶。 | `refresh-decision`／`prepare-decision --workspace-root`；[決策流程](decision_workflow.md)。每日增量尚待串接。 |
| [evidence.py](../src/etf_agent/evidence.py) | 組合三角色報告、持股上下文、S／O引用、提示、schema、workspace與CSV。 | `prepare-decision`；[決策準備](decision_workflow.md)。 |
| [decision/runner.py](../src/etf_agent/decision/runner.py) | 核對凍結輸入，呼叫provider，有限次必要修正，接續編譯與封存。 | `decide-plan`；[真實模型](decision_workflow.md)。會呼叫真實模型，依當批授權。 |
| [decision/providers/base.py](../src/etf_agent/decision/providers/base.py) | AgentProvider Protocol／AgentResult，實際模型、用量、時間、回覆引用與兩版草稿相容。 | provider與合約展示；[模型介面](data_contracts.md#agent-草稿與模型介面)。 |
| [decision/providers/codex_cli.py](../src/etf_agent/decision/providers/codex_cli.py) | 真實Codex CLI、固定stdin、禁工具、核對hash與回覆、保存實報用量。 | runner使用CodexProvider；[真實決策](decision_workflow.md)。Claude尚未實作。 |
| [decision/portfolio.py](../src/etf_agent/decision/portfolio.py) | 按前收／NAV／權重算整張股數，核對完整組合、費稅、現金、上限與姿態。 | dplan使用build_portfolio；[股數與風控](decision_workflow.md#股數風控與-d-plan-編譯)。純計算。 |
| [decision/dplan.py](../src/etf_agent/decision/dplan.py) | 編譯官方4.2、整理S／O／I／D、保存計畫／MD／CSV／驗證／程式封存。 | `compile-plan`或runner；[編譯](decision_workflow.md)。 |
| [decision/validation.py](../src/etf_agent/decision/validation.py) | 官方schema與本地日期、引用、庫存、股數公式及財務語意驗證。 | dplan使用validate_dplan；[驗證](data_contracts.md#驗證與-d-plan)。本地通過不等於正式資格。 |
| [decision/markdown.py](../src/etf_agent/decision/markdown.py) | 同份計畫的可讀表格，原股數→目標、理由／反證、引用、財務與BLOCK。 | writer使用render_plan_markdown；[Markdown](daily_workflow.md#d-plan-markdown-怎麼閱讀)。無模型／IO／股數重算。 |

### data_agent：只讀歷史與計算指標

| 檔案 | 責任／內容 | 怎麼用／由誰呼叫 |
|---|---|---|
| [data_agent/agent.py](../src/etf_agent/sub_agents/data_agent/agent.py) | 核對排名、前收、來源與缺件，整理候選／市場廣度；不讀帳戶、不抓資料。 | evidence使用prepare_data；[角色](decision_workflow.md)。 |
| [data_agent/history_windows.py](../src/etf_agent/sub_agents/data_agent/history_windows.py) | 依日曆及行情manifest核對截至指定日的21筆價格與不足原因。 | `history-window-check`、pipeline；[視窗](calendar_windows.md)。 |
| [data_agent/features.py](../src/etf_agent/sub_agents/data_agent/features.py) | 動能、均線偏離、年化波動，核對封存視窗／行情hash。 | `history-features`；[三因子](factor_analysis.md)。calculate_price_features為純計算。 |
| [data_agent/ranking.py](../src/etf_agent/sub_agents/data_agent/ranking.py) | 載入設定、方向與同分百分位、加權分數與各因子貢獻。 | `history-rankings`；[排名](ranking.md)。排名分數不等於配置權重。 |

### account_agent：完整帳戶與估值

| 檔案 | 責任／內容 | 怎麼用／由誰呼叫 |
|---|---|---|
| [account_agent/agent.py](../src/etf_agent/sub_agents/account_agent/agent.py) | prepare_account匯入與估值；report_account核對身份／日期／NAV／全部股數，回報可用資金估算。 | evidence；[帳戶](account.md#account_agent-帳戶回報)。跨日成交入帳／交割待實作。 |
| [account_agent/account.py](../src/etf_agent/sub_agents/account_agent/account.py) | 匯入AccountSnapshot、純估值、NAV差額與缺價保股；另建立25弱股／10億元demo。 | `account-check`、`build-demo-account`；[帳戶操作](account.md)。共用行情讀取由外層prices提供。 |

### test_agent：行情下載與事後檢討

| 檔案 | 責任／內容 | 怎麼用／由誰呼叫 |
|---|---|---|
| [test_agent/agent.py](../src/etf_agent/sub_agents/test_agent/agent.py) | 受限九月刷新、首日missing回顧、封存後評估委派。 | pipeline.refresh_prepare、evidence、`evaluate-plan`；[決策](decision_workflow.md)／[評估](evaluation.md)。每日合併與次日回饋待接。 |
| [test_agent/history.py](../src/etf_agent/sub_agents/test_agent/history.py) | 官方個股月報下載、原始來源與日／月CSV；離線匯出。 | `history-sample`、`history-universe`、`history-export`；[歷史資料](history_data.md)。 |
| [test_agent/evaluation.py](../src/etf_agent/sub_agents/test_agent/evaluation.py) | 封存hash閘門、固定委託VWAP模擬、現金／費稅／收盤NAV及事後排名。 | evaluation_runner／hindsight；[隔離評估](evaluation.md)。不更新正式帳。跨日帳務接入時再抽共用交易數學。 |
| [test_agent/hindsight.py](../src/etf_agent/sub_agents/test_agent/hindsight.py) | SciPy／HiGHS整數配置最大化費後收盤NAV、Decimal重驗。 | evaluation_runner；[最佳的範圍](evaluation.md#最佳的範圍)。需要evaluation額外依賴。 |
| [test_agent/evaluation_runner.py](../src/etf_agent/sub_agents/test_agent/evaluation_runner.py) | 封存閘門後單日下載／隔離重播、原計畫／不交易／最佳化、獨立報告與8CSV。 | test_agent.evaluate_trade_day／`evaluate-plan`；[操作](evaluation.md)。不回流當日決策。 |
| [test_agent/providers/monthly.py](../src/etf_agent/sub_agents/test_agent/providers/monthly.py) | 月報共用ParsedMonth與日期、OHLC、量值、單位、缺值／重碼檢查。 | TWSE／TPEx adapters；[行情合約](data_contracts.md#行情與清洗)。 |
| [test_agent/providers/twse.py](../src/etf_agent/sub_agents/test_agent/providers/twse.py) | TWSE STOCK_DAY URL／月報解析，保留原價、股／元。 | history按市場選用；[歷史資料](history_data.md)。 |
| [test_agent/providers/tpex.py](../src/etf_agent/sub_agents/test_agent/providers/tpex.py) | TPEx月報URL／解析，區分reported張／千元與精確原量值。 | history按市場選用；[上櫃單位](data_contracts.md#上櫃空值與-reported-報表量值)。 |
| [test_agent/providers/daily.py](../src/etf_agent/sub_agents/test_agent/providers/daily.py) | 指定單日URL與純解析、日期／單位／rawhash、精確VWAP與traded／no_trade／unknown。 | evaluation_runner下載後解析；[單日資料](evaluation.md)。目前尚未輸出open／high／low。 |

### 外層：跨角色共用

| 檔案 | 責任／內容 | 怎麼用／由誰呼叫 |
|---|---|---|
| [contracts.py](../src/etf_agent/contracts.py) | 市場／帳戶／特徵／草稿／配置／驗證與時間切分合約，JSON與Decimal單位檢查。 | 全流程；`contracts-demo`；[資料合約](data_contracts.md)。 |
| [universe.py](../src/etf_agent/universe.py) | F05白名單、市場、原PDF／CSVhash及版本。 | `universe-check`，下載／帳戶／資料共用；[白名單](data_contracts.md#官方股票白名單)。 |
| [prices.py](../src/etf_agent/prices.py) | 核對排名／manifest／截止日唯一CSV與hash，提供共用行情上下文。 | evidence、data／account角色；[日期邊界](decision_workflow.md)。不下載、不計算NAV。 |
| [coverage.py](../src/etf_agent/coverage.py) | CSV4.0日期、市場、白名單、重碼、價格／量值及缺件檢查。 | `prices-check`，視窗／讀價共用；[覆蓋合約](data_contracts.md#每日行情覆蓋與缺件報告)。 |
| [calendar.py](../src/etf_agent/calendar.py) | TWSE／TPEx年度開休市表、月份交易日排程及讀取。 | `calendar-download`與價格視窗；[日曆](calendar_windows.md)。 |
| [providers/http.py](../src/etf_agent/providers/http.py) | 共用HTTPS、狀態／body／來源時間；curl或urllib、保留憑證驗證。 | test_agent下載與calendar；[下載](history_data.md)。 |
| [reports.py](../src/etf_agent/reports.py) | UTF-8 BOM CSV視圖、Decimal字串、未知空欄、集合確定性JSON與hash。 | evidence／dplan／evaluation_runner；[產物](artifacts.md)。 |
| [paths.py](../src/etf_agent/paths.py) | 與角色資料夾深度無關的專案根目錄。 | 官方schema、模型prompt與程式封存；不沿用搬檔前parents深度。 |

套件入口檔只標識責任或匯出公開介面：[etf_agent/__init__.py](../src/etf_agent/__init__.py)、[sub_agents/__init__.py](../src/etf_agent/sub_agents/__init__.py)、[data_agent/__init__.py](../src/etf_agent/sub_agents/data_agent/__init__.py)、[account_agent/__init__.py](../src/etf_agent/sub_agents/account_agent/__init__.py)、[test_agent/__init__.py](../src/etf_agent/sub_agents/test_agent/__init__.py)、[test_agent/providers/__init__.py](../src/etf_agent/sub_agents/test_agent/providers/__init__.py)、[decision/__init__.py](../src/etf_agent/decision/__init__.py)、[decision/providers/__init__.py](../src/etf_agent/decision/providers/__init__.py)、[providers/__init__.py](../src/etf_agent/providers/__init__.py)。

## 配置、提示、內部合約與固定資料

| 檔案 | 存什麼 | 怎麼用 |
|---|---|---|
| [config/ranking.json](../config/ranking.json) | 因子設定 `price_only_v1`；動能 0.40、均線偏離 0.25、低波動 0.35，皆為十進位字串。 | `ranking.load_ranking_profile` 載入；見 [排名](ranking.md)與[權重研究](factor_analysis.md)。是初始設定，尚無最佳值或業界標準證據。 |
| [prompts/decision.md](../prompts/decision.md) | 主投資模型的凍結輸入、引用、完整持股與權重草稿輸出要求。 | `evidence` 複製進資料包，Codex provider 納入固定輸入；見 [決策流程](decision_workflow.md)。與開發合作用 AGENTS.md 分開。 |
| [specs/internal/agent_draft.schema.json](../specs/internal/agent_draft.schema.json) | 舊版 `AgentDraft 1.0`：conviction 選股、市場提案、原持股檢視及嚴格欄位。 | 舊合約／fixture 相容；見 [Agent 合約](data_contracts.md#agent-草稿與模型介面)。 |
| [specs/internal/weighted_agent_draft.schema.json](../specs/internal/weighted_agent_draft.schema.json) | `WeightedAgentDraft 2.0`：十進位字串目標權重、觀察引用及完整持股檢視；禁止最終股數。 | 決策包與 provider 使用；跨股票合計／上下文另由 Python 合約核對；見 [權重草稿](decision_workflow.md#主-etf-agent-的權重草稿)。 |
| [data/universe.csv](../data/universe.csv) | 150 檔固定 F05 白名單：`ticker`、`name`、`market`。 | `universe.load_universe` 載入，供下載、覆蓋與候選檢查使用。 |
| [data/universe.manifest.json](../data/universe.manifest.json) | F05 原 PDF／CSV hash、版本、欄位、150 檔及 TWSE／TPEx 數量、來源頁次。 | 與 CSV 配對核對；見 [白名單合約](data_contracts.md#官方股票白名單)。 |
| [tests/fixtures/contracts_demo.json](../tests/fixtures/contracts_demo.json) | 2026-10-14 人工價格／帳戶與舊草稿等合約示例。 | `contracts-demo` 與合約測試使用；與 2025-09-30 歷史情境日期不同；見 [基本使用](quickstart.md#合約示例)。 |
| [tests/fixtures/account_demo_2025-09-30.json](../tests/fixtures/account_demo_2025-09-30.json) | 2025-09-30、NAV 10 億元的 25 檔人工弱期初 `AccountSnapshot`；含現金及整股股數。 | 歷史帳戶核對與決策準備使用；見 [弱期初](account.md#建立弱期初帳戶)。不是官方已確認庫存。 |

## 九份官方來源

版本與內容以原檔為準；程式／測試只使用需要的來源，不把範例價格、TEAM 或模型資訊當作真實資料。策略模板與參考 PDF 可以直接開啟閱讀；JSON／Markdown 可在 GitHub 或編輯器檢視。

| ID／檔案 | 內容／版本 | 在專案怎麼用 |
|---|---|---|
| F01：[01_etf_strategy_template_v1.docx](../specs/official/01_etf_strategy_template_v1.docx) | ETF 策略繳交模板 v1。 | 規劃策略文件內容與提交格式；設計背景見 [design1001.md](../design1001.md)。 |
| F02：[02_etf_strategy_example_v1.pdf](../specs/official/02_etf_strategy_example_v1.pdf) | ETF 策略範例 v1。 | 理解策略主題／寫作格式，範例不作實際策略驗證證據。 |
| F03：[03_active_etf_list_v1.pdf](../specs/official/03_active_etf_list_v1.pdf) | 主動型 ETF 參考列表 v1。 | 研究背景與策略討論，不是本程式的可交易白名單。 |
| F04：[04_D-Plan.schema_v4.2.json](../specs/official/04_D-Plan.schema_v4.2.json) | 官方 D-Plan JSON schema 4.2。 | `validation.validate_structure`、D-Plan 編譯與測試的結構依據；見 [決策流程](decision_workflow.md)。 |
| F05：[05_stock_universe_150_v1.pdf](../specs/official/05_stock_universe_150_v1.pdf) | 官方 150 檔股票白名單 v1。 | `data/universe.csv` 的原來源；`universe` 核對來源 hash；見 [資料合約](data_contracts.md#官方股票白名單)。 |
| F06：[06_google_token_credit_guide_v1.pdf](../specs/official/06_google_token_credit_guide_v1.pdf) | Google Token Credit 取得說明 v1。 | 外部服務與費用規劃參考；目前 Codex provider 不使用此文件申請額度。 |
| F07：[07_D-Plan_guide_v4.2.md](../specs/official/07_D-Plan_guide_v4.2.md) | 股數計算、證據鏈、庫存、費稅及版本指引 4.2。 | `portfolio`／`dplan`／`validation` 與隔離模擬的規則依據；正式未確認事項另見 [資料合約](data_contracts.md#官方要求與未確認事項)。 |
| F08：[08_D-Plan_positive_example_v4.2.json](../specs/official/08_D-Plan_positive_example_v4.2.json) | 官方 D-Plan 正例 4.2。 | 結構與引用示例、`test_validation.py` 驗收；不是完整期初帳戶或真實模型執行。 |
| F09：[09_D-Plan_negative_example_v4.2.json](../specs/official/09_D-Plan_negative_example_v4.2.json) | 官方 D-Plan 反例 4.2。 | 語意錯誤驗收，含不存在／不一致引用等；不能只以 schema 結果判斷有效計畫。 |

## 測試索引

下列為目前全部 22 個 `test_*.py`，依功能排列。行情、provider 與交易案例主要使用人工 fixture／替身，不把測試當成新下載或真實模型呼叫。白名單與官方例子測試會讀倉庫內的固定來源；相關驗收紀錄見 [development_notes.md](../development_notes.md)。

已設定環境後，只執行受影響的檔案，例如：

```powershell
$env:PYTHONPATH = (Resolve-Path -LiteralPath 'src').Path
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -p test_portfolio.py -v
```

這是重跑方式，不表示本次文件批次執行了測試。環境、套件與整體測試使用方式見 [基本使用](quickstart.md#必要測試)。`test_evaluation.py` 的最佳化案例需要 SciPy 額外依賴。

| 測試檔 | 主要驗什麼 | 對應實作／說明 |
|---|---|---|
| [test_contracts.py](../tests/test_contracts.py) | JSON 往返、Decimal 單位、未知欄位、截止時間、demo 身分、持股／引用與時間切分。 | `contracts`、`decision/providers/base`；[資料合約](data_contracts.md)。 |
| [test_weighted_draft.py](../tests/test_weighted_draft.py) | 第二版權重字串、合計、檔數、上限、持股意圖、引用、禁止最終 shares 及舊版相容。 | `WeightedAgentDraft` 與內部 schema；[權重草稿](decision_workflow.md)。 |
| [test_universe.py](../tests/test_universe.py) | 官方 150 檔、市場數量、代號／名稱、CSV／來源 hash、manifest 與 CLI 失敗。 | `universe`；[白名單](data_contracts.md#官方股票白名單)。 |
| [test_history.py](../tests/test_history.py) | 月報欄位／單位／日期／OHLC／缺值、HTTP 替身、日／月匯出與原始 hash 重播。 | `history`、月報 adapters／HTTP；[歷史資料](history_data.md)。 |
| [test_history_universe.py](../tests/test_history_universe.py) | 全白名單下載替身、已知缺件不請求、cache hash、失敗保存、速率及輸出一致性。 | `history`、`data_agent.refresh_history`；[全股下載](history_data.md)。 |
| [test_coverage.py](../tests/test_coverage.py) | CSV 4.0 覆蓋、錯日期／市場／重碼、價格與量值、空表、診斷及 CLI 退碼。 | `coverage`；[覆蓋合約](data_contracts.md#每日行情覆蓋與缺件報告)。 |
| [test_calendar.py](../tests/test_calendar.py) | 官方排程回應年份必須等於請求年份。 | `calendar`；[日曆](calendar_windows.md)。 |
| [test_history_windows.py](../tests/test_history_windows.py) | 21 筆視窗、週末／休市、不能讀未來行情、缺中間日及不足視窗。 | `history_windows`；[視窗](calendar_windows.md)。 |
| [test_features.py](../tests/test_features.py) | 手算三因子、常數價格、完整輸入選擇、單位／版本及被改動的日表阻擋。 | `features`；[因子](factor_analysis.md)。 |
| [test_ranking.py](../tests/test_ranking.py) | 同分百分位、低波動方向、配置／數值錯誤、缺件與版本保留。 | `ranking`；[排名](ranking.md)。 |
| [test_account.py](../tests/test_account.py) | 股／元估值、日期與 NAV 差異、缺價保留、單日讀價與 hash、零 NAV 診斷、弱期初及輸出。 | `account`；[帳戶](account.md)。 |
| [test_account_agent.py](../tests/test_account_agent.py) | 完整持股回報，日期／身分／股數／NAV 錯誤，正式可用資金保持未知。 | `sub_agents/account_agent`；[帳戶角色](account.md)。 |
| [test_review_agent.py](../tests/test_review_agent.py) | 首日前日缺件、截止日、空績效／建議及拒絕未支援的回顧狀態。 | `sub_agents/test_agent` 的前日檢視；[決策準備](decision_workflow.md)。 |
| [test_evidence.py](../tests/test_evidence.py) | 同日期凍結輸入、來源／因子一致性、缺價完整持股、六 CSV 單位／hash 與空建議。 | `evidence`、`data_agent`、`reports`；[決策資料包](decision_workflow.md)。 |
| [test_pipeline.py](../tests/test_pipeline.py) | 共享 run 的新輸入串接、日期／來源失敗及重用排名時不讀舊決策或抓資料。 | `pipeline`；[整合流程](decision_workflow.md)。 |
| [test_codex_provider.py](../tests/test_codex_provider.py) | 假 subprocess 成功／超時／錯 JSON、模型配置缺失、工具事件拒絕及用量保存。 | `agent/codex_cli`；[真實模型介面](decision_workflow.md)。不實際呼叫模型。 |
| [test_decision_runner.py](../tests/test_decision_runner.py) | 假 provider 的次數限制、必要修正、輸入／程式 hash 與封存失敗。 | `decision_runner`；[決策流程](decision_workflow.md)。 |
| [test_portfolio.py](../tests/test_portfolio.py) | 官方整張 floor、買進／加碼／減碼／退出／續抱、超賣、費稅、現金姿態、零股與證據引用。 | `portfolio`；[股數與風控](decision_workflow.md)。 |
| [test_dplan.py](../tests/test_dplan.py) | 引用裁剪、完整持股、未知模型阻擋、JSON 數字轉換 floor、封存及五 CSV 財務／理由一致。 | `dplan`；[編譯與產物](decision_workflow.md)。 |
| [test_plan_markdown.py](../tests/test_plan_markdown.py) | 原理由與引用、KEEP／退出股數、未知／BLOCK、表格特殊字元，輸入不變。 | decision/markdown；[可讀說明](daily_workflow.md#d-plan-markdown-怎麼閱讀)。 |
| [test_validation.py](../tests/test_validation.py) | 官方正／反例、結構、引用序號、凍結事實、日期、官方公式、篡改委託與資金語意。 | `validation`；[驗證合約](data_contracts.md#驗證與-d-plan)。 |
| [test_daily_quotes.py](../tests/test_daily_quotes.py) | 單日 URL、西元／民國日期、元／股與精確均價、空表、重碼、零成交／未知區別。 | `providers/daily`；[隔離行情](evaluation.md)。 |
| [test_evaluation.py](../tests/test_evaluation.py) | VWAP 費稅／NAV／不交易基準、缺價、封存與隔離、CSV 一致、整數最佳化／限時狀態。 | `evaluation`、`evaluation_runner`、`hindsight`；[隔離評估](evaluation.md)。 |

## 根目錄檔案

| 檔案 | 存什麼 | 怎麼用 |
|---|---|---|
| [README.md](../README.md) | 專案目的、目前狀態、架構圖與操作導航。 | 專案閱讀起點，細節沿 docs 連結。 |
| [AGENTS.md](../AGENTS.md) | 開發合作、分批共識、授權、驗收及正式／demo 邊界。 | 開發助手續接時先讀；不整份貼入投資決策提示。 |
| [design1001.md](../design1001.md) | 架構、資料、因子、演算法、風控、D-Plan、帳務與版本設計草案。 | 判斷擴充責任及待完成設計；實際完成狀態以驗收紀錄為準。 |
| [checklist.md](../checklist.md) | 任務狀態、優先級、驗收與停止點。 | 每批對照範圍，驗收後更新完成證據。 |
| [development_notes.md](../development_notes.md) | 各批授權、決定、修改、實際驗收、問題及下一步的摘要。 | 續接工作與核對歷史批次，不當成每日投資模型輸入。 |
| [pyproject.toml](../pyproject.toml) | Python 版本、專案資訊、`etf-agent` CLI 入口、jsonschema 與 SciPy 選用依賴。 | 安裝與工具設定；見 [環境設定](quickstart.md#環境設定)。 |
| [.gitignore](../.gitignore) | 排除本機環境、私密帳戶／設定、快取及執行產物。 | Git 版本管理；本機產物導覽見 [artifacts.md](artifacts.md)。 |
| [.gitattributes](../.gitattributes) | 專案文字換行規則，PDF／DOCX 與官方來源保留原始位元組。 | Git 讀寫與來源 hash 保存，不自行改寫官方原檔。 |
