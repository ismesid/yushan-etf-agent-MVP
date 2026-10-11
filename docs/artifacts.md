# 輸出檔案：內容、用途與閱讀順序

從 [README 的執行流程](../README.md#執行流程) 找到要執行的步驟，再用本頁查該步產生的檔案。程式、配置及測試原始碼另見 [程式檔案索引](source_map.md)。

## 先找到本次執行

`run` 是一次執行版本，同名檔案放在不同run／階段時，可能代表不同日期與用途。請先看所屬目錄和JSON的 `scope`／日期，再讀CSV。

| 要找的內容 | 先開哪個檔案 | 接著看什麼 |
|---|---|---|
| 整個九月→10/1決策流程 | shared run 根目錄 `workspace.json` | `files` 中的明確相對路徑；`stage`與驗收狀態 |
| 各角色給模型什麼 | `decision_input/.../evidence_packet.json` | 原始三份角色報告與六份CSV |
| 模型做了什麼決定 | `plans/.../decision_run.json` | 接受的 `attempt_<n>/agent_result.json`、`raw_response.json` |
| 最終買賣股票與股數 | compiled run 的 `orders.csv` | 同run的D-Plan／`portfolio.json`／`validation.json` |
| 10/1交易後收益 | 隔離run的 `performance.csv` | `fills.csv`、`end_positions.csv`、`review_report.json` |
| 事後最佳買賣與目標 | 隔離run的 `hindsight_orders.csv` | `hindsight_positions.csv`、`hindsight_optimization.json` |
| 確認檔案未變動 | 該階段 `manifest.json`；日曆用 `calendar.json` | 對應SHA-256與凍結輸入；日曆來源hash在sources；評估另有 `freeze_gate.json` |

`data/cache/` 由Git忽略，新clone沒有這些產物；本頁用檔名與目錄模式說明，GitHub連結只指向可閱讀的說明文件。要在本機查看結果，使用CLI輸出的路徑或workspace索引，不按資料夾名稱猜最新有效計畫。

## 目錄怎麼分

完整整合由 `refresh-decision` 建立shared run；個別命令也能各自輸出到独立cache，格式的用途相同，實際路徑以CLI為準。

```text
data/cache/
├─ calendar/<月份>/<run>/                 官方交易日排程
├─ integrated_runs/<交易日>/<run>/        同一次決策的共用資料
│  ├─ workspace.json                     全流程路徑與狀態入口
│  ├─ run_summary.json                   本次另存的整體摘要（非CLI固定產物）
│  ├─ model_availability.json            本次另存的模型核對（非CLI固定產物）
│  ├─ inputs/                           帳戶與排名設定副本
│  ├─ market/                           官方月報raw、日表、月表、品質報告
│  ├─ windows/                          21筆視窗核對
│  ├─ features/                         三因子與精確metadata
│  ├─ rankings/                         綜合排名與精確metadata
│  ├─ initial_account/                  人工弱期初建構證據（本次另建）
│  ├─ decision_input/                   三角色報告、證據包與凍結提示
│  └─ plans/
│     ├─ <交易日>/decision_<run>/        真實模型嘗試與執行紀錄
│     └─ compiled/<交易日>/<run>/        股數、D-Plan、驗證、程式封存
└─ evaluation_quarantine/<交易日>/<run>/  封存後的隔離行情／收益／事後配置
```

單獨執行時還可能使用 `history_universe/`、`history_windows/`、`features/`、`rankings/`、`account_checks/`、`account_demo/`、`decision_packets/`、`plans/`；它們是CLI輸出位置，不能把同名檔跨run混用。曾清理的舊決策包與計畫路徑是開發歷史，不是目前有效入口。

`run_summary.json`、`model_availability.json` 是本次開發演示額外保存的紀錄，現有CLI不保證每次產生；`initial_account/` 也是本次明確指定的建構位置。自動結果導航以 `workspace.json` 及各CLI實際顯示的路徑為準。

## 行情、日曆、視窗與排名

| 檔案／模式 | 存什麼 | 怎麼使用／完整說明 |
|---|---|---|
| 月行情 `raw/<market>_<ticker>_<月份>.json` | 每股官方月報回應原文，含失敗回應 | 出現價格／單位問題時回查；[歷史資料](history_data.md#產物結構與讀取方式) |
| `source_csv/<月份>/*_source.csv` | 官方報表原欄位的查阅CSV | 人工核對原單位；分析讀日表，見 [行情合約](data_contracts.md#行情與清洗) |
| `daily/<月份>/<日期>_prices.csv` | 當日全部已取得股票的統一價量 | 視窗與帳戶估價入口；[欄位與單位](data_contracts.md#如何解讀-pricescsv) |
| `monthly/<月份>/<market>_<ticker>_<月份>.csv` | 一股整月的每日行情，與日表同源 | 個股查閱用；不要與daily重複合併，[歷史資料](history_data.md#產物結構與讀取方式) |
| 月行情 `manifest.json` | 來源URL、取得時間、raw與CSV hash、逐股狀態、單位、版本 | 下游驗證與續接快取；[快取操作](history_data.md#復用快取與中斷續接) |
| 月行情 `coverage.json` | 逐日股票覆蓋、缺件與失敗清單 | 區分成功下載與完整150檔；[覆蓋檢查](history_data.md#每日覆蓋檢查) |
| 月行情 `data_quality.json` | 原價／近似量值／空值與未核實限制 | 確認可用範圍；[價格與時間](data_contracts.md#return_closeknown_at-與當日均價的用途) |
| 單日覆蓋 `coverage.json`／`missing_stocks.csv` | 單日日表的檢查及缺股明細 | `prices-check`的結果；實際檔名以CLI顯示為準，[覆蓋報告](data_contracts.md#保存重跑與失敗行為) |
| 日曆 `raw/TWSE_<年>.json`／`raw/TPEX_<年>.json` | TWSE／TPEx官方開休市回應 | 以 `calendar.json` 的來源hash回查原排程；[日曆下載](calendar_windows.md#取得官方排程) |
| 日曆 `calendar.json`／`calendar.csv` | 共用交易日、非交易日及來源／限制 | `history-window-check --calendar`讀JSON；CSV查閱，[日曆](calendar_windows.md) |
| 日曆 `failure.json`（失敗時） | 官方排程下載／解析失敗與已保存來源 | 只表示失敗證據，不能作已驗收日曆 |
| `window_report.json` | 預期21個日期、逐股有效價格、讀取日表hash與錯誤 | `history-features --window-report`的輸入；[價格視窗](calendar_windows.md#價格視窗檢查) |
| `window_coverage.csv` | 各股價格筆數、完整狀態、缺失／無效日期 | 人工查看排除原因；[視窗輸出](calendar_windows.md#輸出與閱讀) |
| `features.csv` | 動能、均線偏離、年化波動，每股一列 | Excel解讀原始因子；[因子欄位](factor_analysis.md#先看哪個檔案) |
| features的 `metadata.json` | 精確因子比率、21筆價格／公式／單位／來源與排除紀錄 | `history-rankings --feature-metadata`的輸入；[因子操作](factor_analysis.md#執行與重算) |
| `rankings.csv` | 名次、原始因子、因子得分、加權貢獻及總分 | 看完整146檔比較；[排名欄位](ranking.md#先看哪個檔案) |
| rankings的 `metadata.json` | 精確排名值、完整配比、feature版本、來源hash及限制 | demo建構／帳戶核對／決策準備的 `--ranking-metadata`；[排名操作](ranking.md#執行與重算) |

月行情閱讀CSV用張、千元、千元／張；features的 `_pct` 用百分數；排名的 `score_pct` 是0～100分。這些顯示欄位不能直接當元／股價格或0～1比率回寫計算。完整轉換見 [資料合約](data_contracts.md)。

## 帳戶與弱期初

| 檔案 | 存什麼 | 怎麼使用／完整說明 |
|---|---|---|
| `inputs/account_snapshot.json` | 本次決策用的完整期初cash、NAV、持股股數、日期與身分 | account_agent／股數計算的凍結輸入；[輸入格式](account.md#帳戶輸入格式) |
| `inputs/ranking.json` | 本次排名設定的副本 | 對回三因子40／25／35與來源hash；[設定責任](ranking.md#設定與模組責任) |
| 建構／核對run的 `account_snapshot.json` | 同一次建構或核對的帳戶快照 | 下游明確選用其版本；不把人工demo當官方帳，[帳戶](account.md) |
| `initial_positions.csv` | 弱期初各股股數、前收、市值、排名／因子 | 檢查「弱」以9/30排名選取；[demo建構](account.md#建立弱期初帳戶) |
| `construction.json` | 人工建構方法、預算、來源版本、基本限制與產物hash | 核對如何湊出10億NAV；[demo建構](account.md#建立弱期初帳戶) |
| 帳戶核對的 `positions.csv` | 全部原持股股數、指定日收盤、市值、估值狀態 | 缺行情也保留原股；[估值結果](account.md#輸出與資料問題) |
| `valuation.json` | 現金、已知／完整股票市值、輸入／計算NAV、差額與問題 | 看NAV是否一致與日期是否匹配；[核對結果](account.md#輸出與資料問題) |

## 決策前：三份角色報告與證據包

以下位於同一 `decision_input/<交易日>/<run>/`（或獨立 `decision_packets`）內。[準備指令](decision_workflow.md#執行與產物)整理既有資料，不呼叫投資模型。

| 檔案 | 存什麼 | 怎麼使用／完整說明 |
|---|---|---|
| `data_report.json` | data_agent的排名、候選、完整帳戶估值、來源與限制 | 主模型的資料背景；[資料分工](decision_workflow.md#簡單分工與資料流) |
| `data_candidates.csv` | 候選因子、排名、股數與資格狀態 | 人工檢查模型可比較哪些股；[角色CSV](decision_workflow.md#csv-檢視各角色結果) |
| `data_issues.csv` | 4檔歷史視窗不足的原因與來源版本 | 原紀錄查閱，不補零；[已知缺件](history_availability_2025-09.md) |
| `account_report.json` | account_agent的完整cash／NAV／股數、可用資金估計與檢查 | 給主模型資金與原持股背景；[account_agent](account.md#account_agent-帳戶回報) |
| `account_positions.csv` | 全部原持股的股數、前收、市值與權重 | 與期初帳核對；[角色CSV](decision_workflow.md#csv-檢視各角色結果) |
| `account_summary.csv` | 現金、NAV、差額、可用資金與帳戶狀態 | 快速看帳戶是否可作demo決策；[帳戶回報](account.md#account_agent-帳戶回報) |
| 決策前 `review_report.json` | `previous_trade_review`；首日是prior_run_missing | 明示前績效未知；不是本次隔離評估，[報告邊界](data_contracts.md#agent-草稿與模型介面) |
| `review_status.csv` | 首日前日檢視狀態、截止日及績效空值 | 不把null當0收益；[角色CSV](decision_workflow.md#csv-檢視各角色結果) |
| 決策前 `review_recommendations.csv` | 有依據的前日建議；首日只有欄名 | 本次不會自動回填10/1事後建議；[隔離邊界](evaluation.md#日期與隔離) |
| `evidence_packet.json` | 三角色報告、sources／observations、帳戶、截止日、候選與限制 | `decide-plan --packet`的固定輸入；[證據整理](decision_workflow.md#來源與事實怎麼整理) |
| `decision.md` | 當次凍結投資決策提示 | 模型使用；來源為 `prompts/decision.md`，[權重草稿](decision_workflow.md#主-etf-agent-的權重草稿) |
| `weighted_agent_draft.schema.json` | 當次凍結WeightedAgentDraft 2.0格式 | 限制模型輸出；[共用合約](data_contracts.md#agent-草稿與模型介面) |
| 此階段 `workspace.json` | 此資料包內的檔案索引與準備狀態 | 不是shared root最終總索引；[共用索引](decision_workflow.md#account_agent-與共用索引) |
| 此階段 `manifest.json` | packet／提示／schema／角色CSV與JSON的hash | 模型呼叫前檢查凍結輸入；[操作](decision_workflow.md#執行與產物) |

## 模型呼叫：原始回覆與執行證據

`decide-plan` 使用凍結輸入呼叫真實Codex，這些檔案不是人工fixture。[執行方式](decision_workflow.md#重新取得九月資料與真實決策)列出呼叫上限與限制。

| 檔案／位置 | 存什麼 | 怎麼使用 |
|---|---|---|
| `decision_run.json` | 本次尝試清單、接受／拒絕狀態、輸入位置、產物索引 | 先找被接受的attempt，而不是只開最新raw |
| `code_before/`、`attempt_<n>/code_after/` | 呼叫前後程式內容副本及版本對照 | 核對呼叫期間程式是否變動 |
| `attempt_<n>/provider_packet.json` | 實際傳入模型的證據資料 | 對回原packet／snapshot cutoff |
| `provider_schema.json`／`provider_output_schema.json` | 內部草稿格式與CLI結構輸出格式 | 檢查實際要求模型遵守哪個版本 |
| `decision.md`／`provider_stdin.txt` | 當次提示與實際標準輸入 | 查看模型看過什麼；修正回合含實際錯誤回饋 |
| `raw_response.json` | 模型原始JSON草稿 | 原文查閱；不手改後冒稱原決策 |
| `agent_result.json` | 解析草稿、實際provider／模型、起訖、usage、檔案引用 | 編譯採用的正式內部模型結果；未知資訊留null |
| `events.jsonl` | Codex CLI逐行事件與實報usage | 查工具使用、完成／失敗、用量來源 |
| `stderr.txt` | CLI標準錯誤文字 | 呼叫失敗診斷 |
| `codex_execution.json` | CLI命令／版本、輸入前後hash、模型與成功／失敗紀錄 | 區分真實呼叫、CLI失敗與被拒結果 |
| `repair_context.json`（若有） | 上一回合實際驗證錯誤 | 只有修正回合出現，不代表模型已通過 |

更完整的責任與安全界線見 [模型介面](data_contracts.md#模型介面與待完成)；這些紀錄不含金鑰。

## 計畫編譯：股數、驗證與封存

以下位於compiled run，數值取9/30前收作決策時的預估。[編譯指令](decision_workflow.md#股數風控與-d-plan-編譯)與後驗日均價模擬分開。

| 檔案 | 存什麼 | 怎麼使用 |
|---|---|---|
| `D-Plan_DEMO_<交易日>.json` | 通過本地檢查的D-Plan 4.2、來源／引用／決策／委託／模型紀錄 | 查看封存原計畫；本地通過仍不代表正式可提交 |
| `dplan_candidate.json`（未接受為真實demo計畫時） | 被驗證擋下或來源為fixture的編譯候選 | 即使fixture通過本地財務檢查也只是candidate，不能當已驗收真實模型D-Plan |
| `D-Plan_DEMO_<交易日>.md`／`dplan_candidate.md` | 同份計畫的可讀表格：市場理由、原／目標股數、委託、費稅／現金、原理由／反證與驗證 | 新 compiled run 自動生成，workspace.files.plan_markdown與manifest索引；[閱讀方式](daily_workflow.md#d-plan-markdown-怎麼閱讀) |
| `agent_draft.json` | 本次編譯用的目標權重與原持股review | 對回真實模型回覆或明示fixture來源 |
| `agent_decisions.csv` | 原／新股聯集的模型理由、反證、權重與引用 | 人工看為何續抱、退出、買入 |
| `portfolio.json` | 程式算出的目標／委託股數、完整組合、前收費稅與檢查 | 官方股數公式與完整財務核算入口 |
| `orders.csv` | 買賣方向、整張股數、決策引用與前收估算費稅 | 人工檢查原委託；不是當日實際成交 |
| `portfolio_positions.csv` | 原股數、目標股數、前收估價、投影權重 | 退出股仍以0目標留在聯集 |
| `portfolio_summary.csv` | 前收買賣金額、費用、稅、現金與NAV預估 | 與portfolio JSON核對 |
| `validation.json` | schema／語意／正式資格／提交旗標與問題 | 確認有沒有BLOCK；schema通過不等於正式通過 |
| `validation_checks.csv` | 每項PASS／BLOCK／檢查訊息 | 人工逐項驗收 |
| `compilation.json` | 編譯結果的範圍、日期、身分、來源與限制 | 分辨候選、真模型demo與fixture |
| `evidence_packet.json`及三角色報告 | 這次編譯使用的完整輸入副本 | 對回期初、來源、模型metadata |
| `workspace.json` | 此compiled run的檔案索引／輸出狀態 | 不是shared root总workspace；保留所屬階段 |
| `manifest.json`／`code/` | 本次產物hash、程式／配置／提示／schema內容版本及副本 | 離線重編與原版本查核 |

[五份計畫CSV的解讀](decision_workflow.md#csv-檢視各角色結果)與 [驗證邊界](data_contracts.md#驗證與-d-plan)有更完整說明。

## 隔離評估：當日行情、收益與事後配置

這些只在原D-Plan封存後產生，存到獨立 `evaluation_quarantine`。`decision_as_of=2025-09-30`，評估日期 `2025-10-01`，`decision_input_allowed=false`。[操作與重播](evaluation.md#執行與離線重播)不會改原決策或期初帳。

| 檔案 | 存什麼 | 怎麼使用／說明 |
|---|---|---|
| `freeze_gate.json` | 下載前原決策已封存的閘門、原hash、評估程式版本 | 驗證何時才允許取得T日資訊；[日期與隔離](evaluation.md#日期與隔離) |
| `raw/TWSE.json`／`raw/TPEX.json` | T日官方單日全市場回應原文 | 回查精確成交量值、零成交與日期，不用次日參考價 |
| `TWSE_source.json`／`TPEX_source.json` | 單次HTTP來源、取得時間／或明示未知、rawhash | 解析失敗也保留来源證據 |
| `market_manifest.json` | 指定日的兩來源索引、rawhash、單位與覆蓋狀態 | `evaluate-plan --market-manifest`的離線重播輸入 |
| `market_quotes.json`／`market_quotes.csv` | 146候選的收盤、精確量值、VWAP、trading_status與來源 | CSV檢查當日價量；沒有成交不補價格 |
| 隔離 `review_report.json` | `isolated_post_decision_evaluation`的情境收益、假設、問題與建議 | 與決策前review同名但scope／日期不同，不能回填原packet |
| `no_trade_simulation.json` | 保留原股不交易的完整股數、市值與NAV | 交易決策的比較基準 |
| `frozen_dplan_simulation.json` | 原委託固定股數的VWAP模擬、費稅、現金、檢查與NAV | 核對原計畫在T日的價格收益 |
| `performance.csv` | 不交易／原計畫／事後最佳三個情境 | 先看收益；比率為0～1，金額元 |
| `fills.csv` | 原委託逐筆模擬成交、費稅、現金與相對取消的貢獻 | 分析哪一筆交易有利／不利；不是實際主辦方成交 |
| `end_positions.csv` | 原計畫模擬後的原／新股聯集、股數、市值 | 退出0股保留，缺估價留空 |
| `hindsight_ranking.json`／`hindsight_ranking.csv` | 全候選後驗報酬排行，零成交保留 | 已看到T日結果的排行，不是原三因子排名 |
| `hindsight_optimization.json` | 146個目標股數、最佳委託、限制、solver狀態／上界／gap與Decimal驗收 | 先確認是否證明最佳；[最佳範圍](evaluation.md#最佳的範圍) |
| `hindsight_orders.csv` | 事後最佳配置買賣方向與股數 | 查最佳交易清單，不替代原D-Plan |
| `hindsight_positions.csv` | 事後配置期末股數、市值與退出0股 | 與best JSON核對；不是正式帳戶 |
| 隔離 `review_recommendations.csv` | 原單後驗貢獻、最佳目標與檢討提示 | 有T日後驗資料；與決策前同名首日空建議分開 |
| `simulated_account.json` | 原計畫的獨立期末AccountSnapshot | `status=simulated`、未正式核對；未回寫canonical期初 |
| `hindsight_account.json` | 事後配置的獨立期末AccountSnapshot | 只供比較，不能當原計畫實際持股 |
| `manifest.json`／`code/` | 評估產物與程式hash、原決策未變動、實際資料／模擬成交標記 | 核對與重播；[本次結果](evaluation.md#第25批實跑) |
| `failure.json`（失敗時） | 無法下載／解析／核算／驗收的錯誤 | 不把只有raw或部分結果的run當完整成功 |

## 共通閱讀原則

- **JSON是完整資料與精確計算依據，CSV供人工查阅。** 決策／帳戶／評估CSV用股、元／股、元、0～1比率；行情閱讀與因子顯示使用各自明示單位。
- **相同檔名要對所屬目錄。** `manifest.json`各自描述market、packet、compiled或evaluation，不是每份都有scope；日曆來源另存calendar JSON。`metadata.json`要分features／rankings；workspace須看目錄、files與stage（prepared／compiled可同為shared_agent_run）；兩種review須看scope及日期。
- **投影、模擬、官方帳戶分開。** 前收配置不是已成交；日均價模擬不是主辦方結算；demo／simulated快照不等於official_confirmed。
- **先看問題再看總數。** 缺价時總NAV可能null，只有已知市值小計；不要把空欄填0，或把缺行情原股刪除。
