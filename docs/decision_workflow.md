# 決策資料包與 Agent 分工

文件版本：1.5｜更新：2026-10-11｜權重草稿：WeightedAgentDraft 2.0

`prepare-decision` 將截至指定日的既有排名、完整帳戶與來源，整理成主 ETF Agent 決策的固定輸入。四個角色共用一次執行的資料索引；`compile-plan` 接收權重草稿，以程式計算股數、檢查完整組合及編譯 D-Plan。第 23 批以真實 Codex 完成全部續抱的 demo。本次另用綜合排名末 25 檔建構弱期初，重新凍結輸入並讓模型自主決策，增加角色與主決策 CSV 供檢視；新實跑證據另記，成交帳務仍待實作。

## 簡單分工與資料流

所有角色留在同一 Python 專案，以函式傳入／回傳資料，不增加常駐服務或模型編排框架。

| 角色／模組 | 本批責任 | 交付資料 |
|---|---|---|
| `data_agent/` | 只讀已保存的行情與排名，計算視窗、因子、排名，整理候選與限制。 | 純市場資料報告；不讀帳戶、不抓行情 |
| `test_agent/` | 負責行情下載與整理；首日回顧仍為 `prior_run_missing`，封存後另有隔離收益／最佳化入口。 | 官方原始資料／日表、`review_report.json`及隔離評估 |
| `account_agent/` | 匯入完整快照，以共用截止日收盤估值，檢查日期／身分／NAV／持股完整性。 | `account_report.json`；目前不改帳、不扣款 |
| 主 ETF Agent | 真實 Codex 只讀凍結輸入，提出市場姿態、目標權重及全部原持股檢視，拒絕工具使用。 | WeightedAgentDraft／實際 CLI 模型 ID、用量與原始回覆 |
| `evidence` 組合模組 | 合併三份角色報告，建立來源／事實引用、決策提示與版本，保存共用索引。 | 證據包、`workspace.json`、提示、schema 與 manifest |
| `decision/` 配置／D-Plan／驗證模組 | 按官方公式計算股數、費用估算及完整組合，編譯 D-Plan 並做結構／語意檢查。 | 組合、計畫JSON／可讀MD、驗證與版本 |

`test_agent` 的首日回顧仍只回報缺件，單元測試另用於驗證各模組。封存後的獨立入口已可模擬收益與搜尋事後配置；將昨日行情／原計畫帳戶／檢討接到下一日的流程尚待串接，見 [每日流程](daily_workflow.md)。

共用 [prices.py](../src/etf_agent/prices.py) 只讀指定截止日行情，提供相同上下文給 data_agent 與 account_agent。為保持 packet 1.0 相容，`evidence` 組裝報告時才將 account_agent 的帳戶／估值與持股欄位接到既有 `data_report` 結構；data_agent 本身的輸出不含帳戶。

```text
既有 9/30 排名＋來源     → data_agent 報告 ───┐
前日封存／成交尚缺       → test_agent 報告 ───┼→ 共用 workspace／證據包／提示／schema
完整帳戶＋歷史估值       → account_agent 報告 ┘                 ↓
                                                   主 ETF Agent（Codex 決策入口）
                                                             ↓
                                                    股數／風控 → D-Plan／驗證
```

## 本批資料範圍

演示設定為 **2025-10-01 決策日，2025-09-30 資料截止**。使用 [25 檔、10 億元弱期初 demo 帳戶](account.md)，原持股改為同日綜合排名末 25 檔，人工股數仍按每股 3,600 萬元取整張，剩餘現金精確核對。這是測試情境，不指定模型必須換股。因子配比仍為 40%／25%／35%。`prepare-decision` 重用既有排名，`refresh-decision` 則依新取得的九月行情重算同一套視窗、因子與排名；兩個入口都不改策略參數。

`prepare-decision` 的行情來源只讀排名 metadata、所引用的 manifest 與 **9/30 唯一日表**，另載入帳戶與 F05 名單核對身分。`refresh-decision` 重抓九月、重建 9/30 以前的價格視窗，不實作每日增量合併、不補四檔缺失、不新增流動性門檻。`data_report` 保留原持股與既有缺件／未核實狀態，排名可比較不等於正式可交易。

`demo_candidate` 只表示具備白名單、既有原價因子與截止日有效收盤。原持股即使不在 demo 候選內仍保留；新買候選與完整持股分開傳入後續 Agent。

`known_at`、公司行動、流動性與正式資格尚未核實；資料包維持 `formal_eligible=false`、`submission_ready=false`，不將歷史資料包冒充正式 MarketSnapshot。帳戶仍是人工 demo，估值相符不會讓它成為官方已確認庫存。

本批提示澄清：正式資格待核實這項限制，單獨不會禁止本地歷史 demo 的買賣；它仍阻擋正式提交。續抱理由應引用提供的價格因子，並與其他候選比較。是否續抱、調整或退出由模型判斷，不設最低交易數、不指定應買股票，也不為展示換股修改結果。

**在主 ETF Agent 決策與 D-Plan 生成並封存前，不下載或讀入 10/1 行情。** 本批不計算 10/1 實際報酬、成交或實際費用；編譯器只以前收估算。取得當日行情與效益驗證需要後續明確授權。

最後整合由 data_agent 調用既有下載程式，重新取得九月資料並共用新索引。`refresh-decision` 不自行刪快取，舊下載目錄的刪除依使用者本批授權另行處理。重新取得的資料仍須截至 9/30，不能以「最新資料」為由取得 10/1 行情；第三批的實際刷新結果見下方紀錄。

第 21 批於 2026-10-11 的固定離線實跑為 exit 0，當時保存六個產物，結果如下；下方新增 account_agent 與共用索引不回填這份歷史版本：

| 項目 | 實跑結果 |
|---|---|
| 資料截止／決策日 | 2025-09-30／2025-10-01 |
| 既有排名／demo 候選 | 146／146 檔 |
| 原持股／沿用排除 | 完整保留 25 檔／4 檔 |
| 來源系列／內部 observations | 2 組／147 筆（146 檔與 1 筆廣度摘要） |
| 帳戶 NAV／估值差額 | 1,000,000,000.00 元／0.00 元 |
| 前日檢視 | `prior_run_missing`；建議空陣列、績效 null |
| 準備／正式旗標 | `demo_decision_ready=true`；`formal_eligible=false`、`submission_ready=false` |
| 真實模型／D-Plan | 本批均未執行或產生 |

當次本機路徑：`data/cache/decision_packets/2025-10-01/20261011T174640_396092d6/`。目錄中的 10/1 是預定決策日，全部行情仍截至 9/30；147 筆 observations 是內部決策輸入，由後續編譯步驟按實際引用裁剪。

## 來源與事實怎麼整理

來源先按實際已訪問的資料系列整理為兩組：TWSE 月報 endpoint 與 TPEx 月報 endpoint。各組保留逐股查詢 URL、原始內容 hash 與來源版本，並非只保留網站首頁。它是此次內部證據包的整理方式；主辦方是否接受用系列表示多檔查詢，尚未確認，不能宣稱正式來源引用已驗收。

事實保留全 146 檔排名／因子，以及以這 146 檔為統計範圍的廣度摘要，讓主 ETF Agent 能比較候選與原持股。這份內部包尚未按正式 D-Plan 的實際引用裁剪；[F04 v4.2](../specs/official/04_D-Plan.schema_v4.2.json) 的 observations 最多 100 筆，因此本包不宣稱符合官方 observations 上限。編譯器只留下決策實際引用的來源與事實，再驗證 S→O→I→D→order 鏈、ID 連續與官方數量限制。

內部資料的 hash 用於回查內容版本。來源保存 `content_as_of_trade_date` 描述內容日期；編譯器以當日末 `23:59:59+08:00` 填寫 demo 的 `content_as_of`，只是截至當日內容的描述政策，不是已核實公開時刻。`known_at` 是公開可知時間，`fetched_at` 是實際取得時間；三者不能互相代填。正式截止資格仍須有相應證據。

## 主 ETF Agent 的權重草稿

新增 [weighted_agent_draft.schema.json](../specs/internal/weighted_agent_draft.schema.json) 與 `WeightedAgentDraft`，`contract_version="2.0"`；舊 AgentDraft 與舊合約 fixture 保持原格式。AccountSnapshot 仍為 1.0。

新草稿包含市場提案、20～30 檔正目標權重選股與全部原持股 review。`target_weight` 用 Decimal／JSON 十進位字串，例 `"0.035235"` 表示 3.5235%；總目標權重加現金目標須精確等於 1。2330 權重上限 25%、其他個股 10%，並檢查候選與事實引用存在、原持股完整覆蓋。續抱股應仍有正目標權重，退出股不在正目標選股內。

主 ETF Agent 提出選股、姿態、權重與理由，程式依帳戶、收盤價及官方公式推導最終股數。第 21 批先保存草稿格式與提示，第 22 批加入計算與編譯；第三批加入真實模型入口，實際決策結果另記於驗收紀錄。人工帳戶配比不會被指定成模型的投資目標。

## account_agent 與共用索引

`account_agent` 使用既有 AccountSnapshot 1.0 與估值報告，回傳 `cash_twd`、`nav_twd`、`current_positions` 的每股原持股股數／價格／市值／權重，以及資料問題。`account_valid` 必須同時滿足估值通過、基本組合限制通過、截止日及完整帳戶身分相同、現金與 NAV 核對、全部持股股數相符且沒有 BLOCK。原持股缺行情仍留在報告，不能刪股或假設市值為零。

對 demo 帳戶，`estimated_available_cash_twd` 為現金扣除明示的零保留額，只是演示估算。本批 `reservations_twd="0"`、`reservation_status="not_implemented"`；尚未有委託保留、交割、帳務資料庫或主辦方額度核對，因此 `available_cash_twd=null`。正式帳戶的 demo 估算欄位也為 null。估值正確不會改成 `reconciled=true`，主 Agent 不可直接改帳。

每次新執行的 `workspace.json` 列出四個角色 `data_agent`、`test_agent`、`account_agent`、`etf_agent`，以及該 run 內的資料報告、檢討報告、帳戶報告、證據包、提示、草稿 schema 與 manifest 的相對檔名。路徑相對於這份索引所在目錄解析，不查「最近修改」的快取；尚未生成的 `agent_result`、`dplan` 為 null。整合入口沿用此索引與共享目錄，完整每日排程與成交帳務仍待實作。

## 執行與產物

已有此次歷史排名及其來源快取時，在專案根目錄執行：

```powershell
$env:PYTHONPATH = (Resolve-Path -LiteralPath 'src').Path
.\.venv\Scripts\python.exe -B -m etf_agent.cli prepare-decision --account tests/fixtures/account_demo_2025-09-30.json --ranking-metadata data/cache/integrated_runs/2025-10-01/20261011T181709_8585216a/rankings/2025-09-30/20261011T182031_a7d53013/metadata.json --as-of 2025-09-30 --trade-date 2025-10-01 --output data/cache/decision_packets
```

`--account`、`--ranking-metadata`、`--as-of`、`--trade-date` 必填；`--output` 預設 `data/cache/decision_packets`。`--universe` 預設 `data/universe.csv`，可用 `--universe-manifest` 指定來源紀錄；`--json` 輸出完整 `{ "packet": ..., "outputs": ... }`。

日期需明確指定，不能把帳戶／排名日期換成決策日。程式檢查決策日晚於資料截止日，尚未驗證是否相鄰的正式交易日。每次在 `data/cache/decision_packets/<trade_date>/<執行版本>/` 下建立新執行版本，不覆寫既有產物；`data/cache/` 被 Git 忽略，新 clone 需自行取得前置資料。本頁提供 GitHub 導航，本機路徑以純文字表示。

| 檔案 | 用途 |
|---|---|
| `data_report.json` | 資料角色整理的排名、帳戶、來源與限制。 |
| `review_report.json` | 前日檢視角色的缺資料狀態，不含假績效或假建議。 |
| `account_report.json` | 帳戶角色回報的完整現金、NAV、股數、估值與問題；不更新庫存。 |
| `workspace.json` | 四角色共用的 run 內檔案索引，未執行的模型及 D-Plan 路徑為 null。 |
| `evidence_packet.json` | 主 ETF Agent 的固定證據輸入，保留日期、引用與 demo 狀態。 |
| `manifest.json` | 產物與輸入版本／hash，供回查及後續封存引用。 |
| `decision.md` | 當次決策提示；供模型作決策使用，操作說明仍集中於本頁。 |
| `weighted_agent_draft.schema.json` | 當次凍結的權重草稿格式，避免下一批呼叫時格式漂移。 |

JSON 與提示／schema 保存完整合約與來源，另附下方六份角色 CSV；manifest 保存其他產物的 SHA-256，不含自己避免循環引用。上方第 21／22 批的八份產物是當時版本的紀錄，不能當作新增 CSV 後的檔案總數。本命令完全離線，不呼叫模型、不生成 D-Plan、不更動帳戶或策略參數，也不 commit／push；D-Plan 結構驗證另需環境中的 `jsonschema`，設定見 [環境與基本使用](quickstart.md)。

`demo_decision_ready=true` 表示帳戶估值與基本期初條件通過，並至少有 20 檔 demo 候選，可供下一批模型演示；CLI 此時 exit 0。輸入或提示／schema 缺檔、來源日期／hash 等不符，或 demo 準備條件未通過，exit 2。這個旗標與 `formal_eligible`、`submission_ready` 分開，沒有替代正式候選／D-Plan 驗證。

## 模組介面與驗收

- [sub_agents/data_agent/agent.py](../src/etf_agent/sub_agents/data_agent/agent.py)：`prepare_data(ranking_metadata_path, *, as_of, universe, price_context=None)`，只整理市場／因子／排名；未提供上下文時使用共用prices讀價。
- [sub_agents/test_agent/agent.py](../src/etf_agent/sub_agents/test_agent/agent.py)：`refresh_history()` 只重抓已授權九月來源；`review_previous_day()` 仍只接受首日missing；`evaluate_trade_day()` 為封存後隔離評估。
- [sub_agents/account_agent/agent.py](../src/etf_agent/sub_agents/account_agent/agent.py)：`prepare_account(account_path, price_context, *, as_of)` 匯入／估值，再用 `report_account()` 完整核對與回報；無網路、模型或帳務寫入。
- [evidence.py](../src/etf_agent/evidence.py)：`prepare_decision()` 組合角色報告，`write_decision_packet()` 保存一次執行。
- [pipeline.py](../src/etf_agent/pipeline.py)：`refresh_prepare()` 建立新共享 run，重抓行情並重算現有分析。
- [agent/codex_cli.py](../src/etf_agent/decision/providers/codex_cli.py)：`CodexProvider.generate()` 單次真實決策；[decision_runner.py](../src/etf_agent/decision/runner.py) 的 `decide_plan()` 控制最多兩次並串接計畫驗證。
- [contracts.py](../src/etf_agent/contracts.py)：`WeightedAgentDraft` 與 `WeightedSelection`；[cli.py](../src/etf_agent/cli.py) 組合模組。

本批必要驗收聚焦日期與 hash 來源一致、排名／持股完整、未讀決策日行情、前日缺資料與假績效拒絕、新權重草稿的總和／個股上限／完整 review，以及新版本產物不覆寫。實際測試與離線演示證據記於 [development_notes.md](../development_notes.md)，完成狀態記於 [checklist.md](../checklist.md)；缺資料角色介面不勾選為已完成績效功能。

第 21 批實際通過 **16 項新增測試**：證據準備 5 項、前日檢視 4 項、權重草稿 7 項；另通過舊 fixture 的 3 項聚焦相容檢查。第 22 批新增 account_agent 四項測試通過，涵蓋 10 億正常帳戶、缺價保留持股、日期／身分／股數／NAV 不符及正式額度限制。未反覆執行全套或掃所有快取。可依修改範圍選擇重跑：

```powershell
$env:PYTHONPATH = (Resolve-Path -LiteralPath 'src').Path
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -p test_evidence.py -v
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -p test_review_agent.py -v
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -p test_weighted_draft.py -v
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -p test_account_agent.py -v
```

舊 fixture 的相容檢查與當次完整執行證據見開發紀錄；測試用帳戶／價格是合成值，上方固定資料包則重用 9/30 真實歷史收盤與人工 demo 帳戶。

## 股數／風控與 D-Plan 編譯

`compile-plan` 接收凍結 `evidence_packet.json` 與 WeightedAgentDraft 2.0 草稿。配置模組只使用包內帳戶、前收及引用，不抓行情、不呼叫模型、不改寫現金或股數。

依 [F07 v4.2 §⑥ orders](../specs/official/07_D-Plan_guide_v4.2.md)，目標股數與委託機械推導如下：

```text
目標股數 = floor(目標權重 × 前日 NAV ÷ 前日收盤價 ÷ 1000) × 1000
委託股數 = 目標股數 − 原持股股數
```

例如只示範算式：2330 權重 4%、NAV 10 億元、9/30 收盤 1,305 元，推導目標 30,000 股；原持 27,000 股，故推導 BUY 3,000 股。這不是模型的實際投資決策。`keep` 要求推導股數與原股數一致，退出股不留正目標權重；不以手改 shares 解決草稿與意圖矛盾。

檢查涵蓋全部原持股與選股、漏 review、前收缺件、整張、超賣、零股數選股、雙向委託、正持股 20～30 檔、個股上限、費用後現金與宣告區間，以及淨買賣姿態。F07 列買賣手續費各 0.1425%、賣出稅 0.3%；本批以前收假設委託全成，Decimal 全精度估算，不假稱 10/1 成交。正式費用取整、當日成交與結算口徑仍待核實。

編譯器保留實際引用的事實並重排 ID，檢查官方 schema 及來源→事實→解讀→決策→委託的引用。真實執行資訊需另供 `--agent-metadata`；沒有資訊就留缺件，不照抄 F08／F09 的模型名稱、版本、時間或 token。`--decision-source fixture` 明示人工草稿，不能因此填出真實模型紀錄。

先建立環境，並把下列兩個路徑換成本次凍結包與實際草稿：

```powershell
$env:PYTHONPATH = (Resolve-Path -LiteralPath 'src').Path
$packetPath = 'data/cache/decision_packets/2025-10-01/<本次run>/evidence_packet.json'
$draftPath = '<本次草稿路徑>/agent_draft.json'
.\.venv\Scripts\python.exe -B -m etf_agent.cli compile-plan --packet $packetPath --draft $draftPath --decision-source fixture --team-id DEMO --output data/cache/plans
```

`--packet`、`--draft` 指定本次輸入；`--agent-metadata` 可選，`--decision-source` 為 `fixture` 或 `real`。`--output` 預設 `data/cache/plans`，`--team-id` 預設 `DEMO`。`real` 必須反映實際模型呼叫；第三批的 `decide-plan` 會由模型執行紀錄組合這些資訊。

缺少真實模型 metadata 的本機演示保留 `dplan_candidate.json` 及 schema BLOCK，不能宣稱已通過官方結構。真正有模型紀錄、配置及驗證通過時才保存 `D-Plan_<TEAM>_<DATE>.json`。兩種情況都保存 `portfolio.json`、`validation.json`、輸入 `evidence_packet.json`、`agent_draft.json`、完整 `compilation.json`、三份角色報告、`workspace.json`、`manifest.json` 及程式版本歸檔，另附下方主決策／計畫 CSV。manifest 保存其他產物的 hash；共用索引列出該次帳戶、資料、檢討、草稿、投影、驗證及候選／計畫，全部使用 run 相對路徑。成功本地驗證 exit 0；可編譯但被驗證阻擋為 exit 4，仍保存診斷；讀檔／合約／草稿 schema 等無法編譯為 exit 2。即使 demo 驗證通過，正式資格仍為 false，也不代表已核對官方庫存或可以提交。

此入口尚未處理 SQLite、實際成交、資金保留及新帳戶版本；account_agent 回報仍是原快照。各項實際驗收與輸出名稱記在開發紀錄。

## 重新取得九月資料與真實決策

`refresh-decision` 從明確的九月日曆、9/30 demo 帳戶及既有排名設定開始，由 data_agent 調用原下載器，重新取得官方九月月報。禁止讀取舊行情快取，`cache_manifest=None`；已核實九月不存在行情的 3718／7769／7828 只保留 failed／缺件紀錄，不發出請求，不造 raw、取得時間或 HTTP 結果。7750 的九月月報正常下載，既有視窗不足原因不重新調查。

本次實際發出 147 次請求、cache hits 為 0，147 檔成功且沒有額外失敗。來源清單仍有 150 檔，下載器 `success=false` 可反映這三個已知缺件；整合流程將既有缺件與額外下載失敗分開判斷。下載失敗或新資料與帳戶／日期不符時保存診斷，不以補值或改帳強行通過。

命令本身不刪任何舊資料、沒有模型呼叫；本批舊下載快取的刪除由外部依已授權範圍處理。每次新建 `data/cache/integrated_runs/<trade_date>/<執行版本>/`，將新行情、視窗、特徵、排名、帳戶副本與角色報告存於同一 shared run：

```powershell
$env:PYTHONPATH = (Resolve-Path -LiteralPath 'src').Path
.\.venv\Scripts\python.exe -B -m etf_agent.cli refresh-decision --month 2025-09 --as-of 2025-09-30 --trade-date 2025-10-01 --account tests/fixtures/account_demo_2025-09-30.json --calendar data/cache/calendar/2025-09/20261011T154421_1306c9a4/calendar.json --output data/cache/integrated_runs
```

CLI 顯示新的 `run_root`、`workspace.json` 與 `evidence_packet.json`；下一步明確傳入這份新凍結包，計畫輸出指定為同一 run 下的 `plans`。下列路徑變數需替換為實際結果：

```powershell
$sharedRun = 'data/cache/integrated_runs/2025-10-01/<本次run>'
$packetPath = '<refresh-decision顯示的新evidence_packet.json路徑>'
.\.venv\Scripts\python.exe -B -m etf_agent.cli decide-plan --packet $packetPath --output "$sharedRun/plans" --team-id DEMO --model gpt-5.6-sol --max-attempts 2
```

`decide-plan` 才呼叫真實 Codex。使用已安裝 CLI 與本機明確設定的 OpenAI 模型 ID，保存實際 CLI 版本、指定模型 ID、開始／結束、CLI 實報 usage、事件及原始回覆；確切模型 snapshot 若 CLI 未提供則保持 null，不猜版本或 token。本批真實呼叫合計最多兩次，provider 本身不自動重試；若需要第二次修正，仍計入這個上限。

`--packet` 與 `--output` 必填；`--max-attempts` 只允許 1 或 2，預設 2，`--team-id` 預設 `DEMO`。`--model` 可指定本次模型 ID，覆寫 CLI 參數但不改全域設定；本次 `gpt-5.6-sol` 依唯讀可用模型清單選定。每次嘗試各有 `attempt_<n>/`，保存凍結 provider 輸入、原始回覆、CLI 事件、執行紀錄與驗證回饋；整體結果另保存決策報告。共用 workspace 會指向模型紀錄與實際候選／計畫，通過時標記 `compiled_demo_frozen`，未通過標記 `decision_blocked`。

模型只能讀凍結證據、提示與 WeightedAgentDraft schema；不抓市場資料，不使用工具，不修改輸入，也不決定最終 shares。事件包含工具操作或呼叫期間輸入 hash 改動時拒絕該結果。每次呼叫與失敗診斷都保存，用量與模型資訊依實際紀錄填寫。

模型回覆須通過草稿、完整配置、F04 結構與語意驗證，才保存 `D-Plan_DEMO_2025-10-01.json`；被拒絕時保留原回覆、候選或錯誤診斷，不手改草稿湊通過。本地通過仍為 demo，`formal_eligible=false`、`submission_ready=false`，也不更新帳戶。

## CSV 檢視各角色結果

每次新產物提供 UTF-8 BOM CSV，方便直接用 Excel 開啟；JSON 合約、來源與版本仍保存。股數是股、金額是新臺幣元、價格是元／股，權重和現金比為 0～1 比率；null 為空欄。建議或委託為空時只保留欄名，不能把空資料寫成假建議、假交易或零績效。

| 角色 CSV | 檢視內容 |
|---|---|
| `data_candidates.csv` | 全部可比較候選的因子、排名與資格狀態。 |
| `data_issues.csv` | 未進完整排名的股票、視窗狀態、有效價格筆數、缺失／無效日期與來源版本。 |
| `account_positions.csv` | 全部原持股的股數、前收、市值、權重及來源狀態。 |
| `account_summary.csv` | 現金、NAV、估值差額與帳戶檢查。 |
| `review_status.csv` | 前日檢視狀態與截止日；目前仍為 `prior_run_missing`、績效空值。 |
| `review_recommendations.csv` | 有依據的前日改善建議；目前沒有前日封存與成交，只留欄名。 |

主 ETF Agent 回覆、程式配置與驗證另提供以下五份 CSV：

| 主決策／計畫 CSV | 檢視內容 |
|---|---|
| `agent_decisions.csv` | 模型選股、目標權重及原持股檢視理由。 |
| `orders.csv` | 程式推導的買賣方向、整張委託股數與決策引用。 |
| `portfolio_positions.csv` | 原股數與目標股數、前收及完整持股投影。 |
| `portfolio_summary.csv` | 前收估算的買賣金額、費用、稅、現金與 NAV。 |
| `validation_checks.csv` | 結構／語意／完整組合的檢查結果與問題。 |

CSV 不會讓 `prior_run_missing` 成為已完成績效功能，也不會讓投影股數成為已成交庫存；模型理由不改寫正式行情或帳戶。

## 弱期初重新決策與舊產物邊界

使用者本批授權清除舊決策包、舊草稿、模型回覆與舊計畫，保留新九月行情及其視窗、因子、排名、日曆與官方來源。本頁第 21～23 批的 run 與數字是歷史證據；清理後不要再用那些舊決策／計畫路徑執行下一步。

共享 run `data/cache/integrated_runs/2025-10-01/20261011T181709_8585216a/` 的 `market/`、`windows/`、`features/`、`rankings/` 保留。新弱 snapshot 寫入 `inputs/account_snapshot.json`，重新建立 `decision_input/` 與 workspace，不沿用舊帳戶的凍結包。命令不自行清除整個 shared run；清理只針對本批列明的決策產物。

先依 [帳戶說明](account.md#建立弱期初帳戶) 執行 `build-demo-account`，再用 `prepare-decision --workspace-root <shared_run>`，以新帳戶及保留的同日排名產生新凍結包／六CSV。呼叫 `decide-plan` 時傳入這份新包，不能使用舊rawresponse或舊D-Plan；全程保持9/30截止。新實跑見 [第24批](#第-24-批弱期初重新決策實跑)。

本批刷新與真實決策已完成，D-Plan 本地通過並封存；紀錄區分刷新成功、首次模型請求被拒絕、第二次真實回覆成功與同一回覆的離線重編。四角色共享歷史資料與完整帳戶，test_agent 的前日績效仍是 null，實際成交／效益及官方帳務尚未實作。後續取得 10/1 行情與帳務／效益驗證另需明確授權。

## 第 23 批刷新實跑與模型狀態

此節為歷史驗收紀錄。第24批依使用者明確指示刪除本節的舊決策包、模型回覆與D-Plan，下面的舊決策路徑現已不存在；九月行情／排名保留，新結果見第24批。

共享 run 為 `data/cache/integrated_runs/2025-10-01/20261011T181709_8585216a/`；新凍結包相對路徑為 `decision_input/2025-10-01/20261011T182031_5135f5cb/evidence_packet.json`。四角色共用這份新索引，沒有從舊行情快取重建：

| 項目 | 實際結果 |
|---|---|
| 真實 HTTP 請求／cache hits | 147／0 |
| 成功／已知略過／額外失敗 | 147／3／0 檔 |
| 排名／完整原持股 | 146／25 檔 |
| 帳戶 NAV／市值核對差額 | 1,000,000,000 元／0 元 |
| 行情截止／決策日 | 2025-09-30／2025-10-01 |

第一次模型請求被 ChatGPT 服務端以 HTTP 400「unsupported model」拒絕，沒有取得投資決策。唯讀核對 app-server 可用模型清單後，剩餘一次以 `--model gpt-5.6-sol --max-attempts 1` 執行成功；未更改全域模型設定。本批合計兩次請求、一次取得決策，上方一般 `max-attempts 2` 範例不授權超出本批額度的再次呼叫。

| 真實模型紀錄 | 實際結果 |
|---|---|
| 模型 ID | `gpt-5.6-sol`；未知確切 snapshot 保持 null |
| 呼叫起訖（+08:00） | 2026-10-11 18:23:14.797549～18:24:34.655385 |
| Input／output tokens | 145,146／3,976 |
| Reasoning／cached tokens | 232／0（CLI 實報） |
| 選股／原持股檢視 | 25／25 檔，全為 keep |
| 市場／策略姿態 | neutral／neutral，intended_action 為 hold |
| 現金目標／宣告範圍 | 0.1091094／0.105～0.115 |

模型自然判斷全部續抱，沒有為展示換股而修改它的選擇。首次自動版本歸檔因 Windows 深層目錄超過路徑長度限制而失敗；保留同一份原始回覆，以 `compile-plan` 改短輸出至 shared run 下的 `final` 離線重編，沒有第三次模型請求。

有效 demo 計畫相對路徑為 `final/2025-10-01/20261011T182555_b8b2869e/D-Plan_DEMO_2025-10-01.json`，完整本機路徑為 `data/cache/integrated_runs/2025-10-01/20261011T181709_8585216a/final/2025-10-01/20261011T182555_b8b2869e/D-Plan_DEMO_2025-10-01.json`。封存的程式版本為 `455d78cf0f69`，後續程式修正不回寫這份已通過版本：

| 計畫與完整組合 | 實跑結果 |
|---|---|
| 官方 schema／語意／本地驗證 | 全部 true；issues 為空陣列 |
| 變動決策／委託／不交易持股 | 0／0／25 |
| 手續費／賣出稅估算 | 0／0 元 |
| 現金／NAV | 109,109,400／1,000,000,000 元 |
| 決策來源／提交資格 | `real_decision=true`；`submission_ready=false` |

這份計畫當時保存了真實模型紀錄與凍結資料，後於第24批明確清除。兩批都只產人工帳戶demo，正式資格與提交維持false，未取得10/1行情。實際成交／費用、隔日帳戶與test_agent成效檢視仍待後續授權。

## 第 22 批實跑與驗收

2026-10-11 18:07 的最新資料準備 run 為 `data/cache/decision_packets/2025-10-01/20261011T180724_e49e57e2/`，產生八份檔案／七份產物 hash。account_agent 保留帳戶輸入 hash，回報現金與 demo 估算可用資金各 109,109,400 元、NAV 10 億元、25 檔完整股數，`account_valid=true`。原帳戶仍為 demo、未正式核對。

人工草稿位於 `data/cache/plan_examples/weighted_draft_fixture_2025-10-01.json`：25 檔各目標權重 0.0364、現金目標 0.09，原持股全為 rebalance。這些是專供編譯驗收的人工選擇，不是真實模型決策，也沒有修改既有因子權重。

計畫 run 為 `data/cache/plans/2025-10-01/20261011T180729_491b495e/`。人工草稿配合真實 9/30 前收得到以下結果，金額均為元：

| 項目 | 實跑結果 |
|---|---:|
| 買進委託／不交易持股 | 17 筆／8 檔 |
| 買進／賣出估算金額 | 8,698,350／0 |
| 手續費／賣出稅估算 | 12,395.14875／0 |
| 費用後現金估算 | 100,398,654.85125 |
| 費用後 NAV 估算 | 999,987,604.85125 |
| 完整組合檢查 | `portfolio_ok=true` |
| 官方 schema／CLI | 缺真實模型 metadata 而 BLOCK／exit 4（預期） |

當次保存 11 份 JSON 與程式版本歸檔，manifest 記錄 10 份產物 hash。沒有有效 D-Plan、真實模型呼叫、實際成交或新帳戶入帳；`dplan_candidate.json` 是可回查的診斷候選，不能當成已完成真實投資決策。

當時離線演示保留 BLOCK 並回傳 exit 4。舊草稿及決策產物列入本批清理，這段只保留歷史驗收說明，不提供已清理路徑作為重跑入口；新的人工測試應另建 fixture，不能代替本批真實模型。

本批共 **30 項相關測試通過**：account_agent 4、portfolio 7、validation 8、compiler 6，另複驗受影響 evidence 5。驗收涵蓋官方 F08／F09 結構皆通過而 F09 的 I9 語意被阻擋、keep 股數與權重矛盾必須傳到驗證、JSON 浮點序列化造成整張邊界差異、引用或事實數字遭篡改、完整帳戶與來源不符。測試只驗重要行為，未跑全套或掃所有快取；測試中模型 metadata 為人工值，不能充作真實模型執行紀錄。

第 22 批收尾時未刪除舊快取、重新下載九月行情或取得／讀入 10/1 行情；真實模型與重新取得資料的整合由第 23 批處理。每日成交帳務仍留待後續授權。

## 第 24 批弱期初重新決策實跑

本批依使用者指示清除舊決策包、fixture權重草稿、模型回覆與D-Plan，沒有保留或備份它們；保留九月官方行情、視窗、因子、排名與日曆。人工期初改為綜合第122～146名25股：24檔動能負、22檔低於均線，股票892,932,500元＋cash107,067,500元＝NAV10億元。三因子40／25／35不變，不用10/1表現挑弱股。

同一shared root `data/cache/integrated_runs/2025-10-01/20261011T181709_8585216a/` 的本次位置：

| 產物 | 相對路徑 |
|---|---|
| 初始持股／建構核對 | `initial_account/2025-09-30/20261011T183759_84fc3293/` |
| 四角色輸入／六CSV | `decision_input/2025-10-01/20261011T184109_4a9529e8/` |
| 真實模型回覆／用量 | `plans/2025-10-01/decision_20261011T184244_64a7bd3d/attempt_1/` |
| D-Plan／五CSV／驗證 | `plans/compiled/2025-10-01/20261011T184409_51450818/` |
| 全流程導航／摘要 | `workspace.json`／`run_summary.json` |

真實gpt-5.6-sol初次回覆即通過，不需第二次修正：input145,401／output4,204／reasoning703，服務端snapshot未知保持null。模型自主判斷15原股退出、10原股續抱、新買10股，目標正持股20檔；例如退出6919的194,000股、買入2330的76,000股，股數由程式依前收與目標權重推導，模型沒有直接指定最終shares。

| 前收demo投影 | 金額／結果 |
|---|---:|
| 賣出／买進金額 | 534,806,700／520,423,650元 |
| 買賣手續費／賣出稅 | 1,503,703.24875／1,604,420.10元 |
| 費後現金 | 118,342,426.65125元 |
| 費後NAV | 996,891,876.65125元 |
| 現金比 | 約11.87114% |
| 委託／續抱／正持股 | 25筆（15SELL／10BUY）／10檔／20檔 |
| F04結構／本地語意 | 全部通過，issues空 |

`D-Plan_DEMO_2025-10-01.json` 有2S／36O／35I／25D／10no_trade／25orders，版本 `sha256:61938e20777f`。未更新期初帳戶；上述是9/30前收、費用不取整的demo估計，不是10/1成交或績效。formal_eligible／submission_ready均false，沒有取得或讀入10/1行情。

六角色CSV列數依序146候選、4缺件、25原持股、1帳戶摘要、1檢討狀態、0建議；五主決策CSV為35股完整聯集、25委託、35股投影、1財務摘要、247驗證檢查。35股聯集包含15檔目標0的退出股，不會在表格消失；target_shares>0只有20檔。首日無前績效，建議CSV只有表頭。

27項相關測試通過，未跑全套。當次13輸入／15輸出hash、37程式封存檔hash、模型metadata／原始用量、所有CSV委託／逐筆金額／費用及現金獨立核對通過；真實草稿離線重編plan與portfolio完全一致。本批沒有新行情請求，模型只呼叫一次；下次重新呼叫仍屬新決策，不能當離線重播。

## 第25批封存後隔離收益

使用者下一批授權test_agent取得10/1行情，並選擇完整146候選股票／股數最佳化，另明確同意SciPy。原workspace／packet／D-Plan未改；新 `evaluate-plan` 在 sibling `evaluation_quarantine` 保存當日官方量值、8CSV、收益、最佳化與simulated帳。

10億元期初：不交易＋2,462,850元（＋0.246285%）；原25委託按官方日均價模擬、扣費稅後−2,402,285.54元（−0.240229%）；全候選事後最佳＋17,594,987.95元（＋1.759499%），30單／20股、solver gap0、前收與T收雙財務重验通過。3260當日零成交保留候選但禁建倉，未補價；事後配置不替換D-Plan，也不回流首日review。

結果、日期／單位、求解范围、來源時間未知、CSV解讀及不連網的重跑指令見 [隔離收益評估](evaluation.md#第25批實跑)。正式帳務、官方核對及下一日的建議／帳戶匯入仍未串接。第24批「未取得10/1」描述當時狀態，本批才於封存後取得。
