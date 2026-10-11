# 玉山 AI CUP：8 小時 MVP 實作 Checklist

對應設計：`design1001.md` v0.3、`AGENTS.md` v1.0｜日期：2026-10-11

**本清單按實際驗收記錄，未勾選項目仍未完成。** 2026-10-11 已完成第 01 批：標準庫共用資料合約、含既有持股的離線 demo、CLI 示例及 30 項合約測試。真實行情、因子、投資模型、配置、D-Plan、SQLite 帳務與回測仍待逐批實作；詳見 `development_notes.md`、`diary.md`。

第 01 批證據：`src/etf_agent/contracts.py`、`agent/base.py`、`cli.py`、`specs/internal/agent_draft.schema.json`、`tests/fixtures/contracts_demo.json`、`tests/test_contracts.py`、`docs/data_contracts.md`。PowerShell 先設定 `$env:PYTHONPATH = (Resolve-Path 'src').Path`；`python -B -m etf_agent.cli contracts-demo --fixture tests/fixtures/contracts_demo.json` 成功，25 檔持股市值 90,000,000.00 元＋現金 10,000,000.00 元＝NAV 100,000,000.00 元；`python -B -m unittest discover -s tests -p test_contracts.py` 為 30 tests、OK。全部為人工測試資料，`submission_ready=false`。

每完成一項才把 `[ ]` 改成 `[x]`，並在旁邊留下測試結果／檔案路徑。若卡住，寫問題與採用的替代路徑，不直接勾選。`P0` 是這 8 小時必要；`P1` 延到會議後；`LIVE` 是正式參賽前必做，不以 demo 通過取代。

## 0. 每批都要遵守的合作方式

合作規則已提供於 `AGENTS.md`，下列項目用來檢查開發過程是否遵守，不代表本次已經建立 Python 專案。三份 Markdown 放在專案根目錄，九份來源依設計 §2.1 放在 `specs/official/`；再貼 `design1001.md` §20.1 的新 prompt，取代舊版直接開工要求。

- [x] **COOP-01** 第一回合僅讀設計、來源與必要專案指示，先解釋流程與第一批方案；不改檔、不安裝、不執行專案程式或付費呼叫。證據：2026-10-11 首輪九份來源盤點；`diary.md`。
- [ ] **COOP-02** 每批約10～30分鐘，只處理一個可展示結果的小任務；討論與驗收算進8小時。
- [ ] **COOP-03** 事前講清目的、輸入輸出、修改檔案、指令、連網／模型用量與驗收方式。
- [ ] **COOP-04** 用具體例子與1～2個關鍵問題確認理解；回答疑問後等待明確同意，不把沉默或詢問當授權。
- [ ] **COOP-05** 同意只涵蓋列出的本批實作／驗證；同範圍修正可繼續，擴大範圍、加依賴、改合約／參數或付費服務則重新討論。
- [ ] **COOP-06** 完成後展示輸出、實際測試、如何重跑與未完成項目，再討論下一批；不一次做完全部清單。
- [x] **COOP-07** 確認已讀取根目錄提供的AGENTS.md；在同意的首批範圍內建立簡短development_notes.md，之後保存已同意決定、授權範圍與完成證據。第 01 批已建立 `development_notes.md`、使用者另要求的 `diary.md`；後續仍逐批更新。
- [ ] **COOP-08** 先確認共用資料格式與模組介面，再寫各adapter；官方規則、自訂參數與假設分開。
- [ ] **COOP-09** 驗證擴充方式：加法人因子沿用orders／ledger、換Claude沿用風控、加UI沿用核心流程。
- [ ] **COOP-10** 區分開發助手與每日投資決策模型；教學／批准對話不放進AgentDraft或D-Plan。

## 1. 8 小時完成的定義

- [ ] **P0-01** 至少一個完整 run：資料→清洗→三因子→真實 Codex 決策→配置→官方股數公式→D-Plan 4.2→本地驗證→版本存檔。
- [ ] **P0-02** 報告有實際 20～30 檔持股、前收估算現金、全部持股權重、費用、交易股數與引用鏈。
- [ ] **P0-03** 有一個無交易日或第二日案例，證明每檔原持股都有處理。
- [ ] **P0-04** 有一個錯誤案例被擋下，例如 I9 斷引用或超賣。
- [ ] **P0-05** 有收盤結算模擬、核對差異及重複入帳保護；測試核對資料需標明 fixture。
- [ ] **P0-06** 儲存輸入、模型輸出、程式／參數／prompt 版本；離線 replay 的股數與費用相同。
- [ ] **P0-07** 完成 `meeting_report.md`，清楚列出真實資料、demo 資料、已實作、未實作及正式上線 blockers。

驗收路徑：`runs/<交易日>/<RUN_ID>/meeting_report.md`；實際 RUN_ID：________。

**只有 fixture／規則結果，沒有一次真實 Codex 決策，就只算資料與交易引擎原型，AI Agent MVP 仍未完成。** 若官方資料暫時不可取得，先展示明確標示的測試流程；正式可用性另外評估。

## 2. 時間分配與停止點

T+0 從你真正開始合作實作時計，不是收到這份檔案的時間；討論、確認與測試都算入8小時。以下是時間預算，不是授權Codex連續執行全部階段。四人可按第 3 節分工，仍以同一套介面整合。

| 時段 | 工作 | 必須留下的結果 | 超時處理 |
|---|---|---|---|
| T+0:00～0:30 | 範圍、目錄、官方檔、設定、合約 | 專案可啟動、正式與 demo 分開 | 先用最小 CLI，不加 UI |
| T+0:30～2:00 | 白名單、資料與帳戶匯入、清洗 | 價量快照、品質報告、150 檔名單 | 抓取卡住改官方 CSV／快取；fixture 明示 |
| T+2:00～3:00 | 特徵、排名、證據包 | features、rankings、packet | 維持三因子；不加基本面／新聞 |
| T+3:00～4:00 | AgentDraft、真實 Codex、Claude 預留 | 一次真實模型 JSON＋logs | CLI 卡住用互動 Codex 讀同一包 |
| T+4:00～5:00 | 配置、整張與風控 | 20～30 檔可行方案、股數與現金 | 配置器太慢先等權；完整標明方法 |
| T+5:00～6:00 | D-Plan 編譯、結構及語意驗證 | 一份可讀 JSON、一份驗證報告 | 不放寬硬限；減少交易／補足引用 |
| T+6:00～7:00 | 帳本、結算、核對、版本 | 庫存三狀態、重跑不重複扣款 | 優先完成最小真實公式與 fixture 核對 |
| T+7:00～8:00 | 端到端、錯誤案例、replay、開會稿 | 一次完整展示與已知缺項 | 停止加功能；修最重要失敗 |

- [ ] **GATE-01／T+0:30** 合約與路徑固定，各模組能用相同 fixture 溝通。
- [ ] **GATE-02／T+2:00** 至少有可演示的資料快照；如果資料不夠，已清楚轉成 demo，其他模組繼續。
- [ ] **GATE-03／T+4:00** 真實 Codex 輸出已儲存；還沒有就優先處理，不開始訓練模型。
- [ ] **GATE-04／T+6:00** 一份 D-Plan 經結構及本地語意檢查；未通過則把剩餘時間留給整合。
- [ ] **GATE-05／T+8:00** 報告能說明目前能跑什麼、哪些正式條件還沒核實。

## 3. 四人團隊可用分工

若今天四人都能開工，可依下表分工；只有你一人時，照第 2 節順序做即可。

| 人員／角色 | 責任 | 交付介面 | 避免衝突 |
|---|---|---|---|
| A：資料 | 白名單、TWSE／TPEx、calendar、clean | prices、universe、品質報告、provenance | 不改 AgentDraft／訂單合約 |
| B：因子與 Agent | features、rankings、evidence、Codex | evidence_packet、agent_draft、真實 logs | 不自行寫最終 orders |
| C：配置與驗證 | allocator、Decimal 公式、D-Plan、validator | allocation、orders、validation | 不修改官方 schema |
| D：整合與帳務 | CLI、ledger、版本、測試、報告 | 全流程指令、replay、meeting_report | 一人維護 shared config／合約 |

- [ ] **TEAM-01** 指定同一位整合者與正式提交者：________。
- [ ] **TEAM-02** T+0:30 前凍結內部合約；共同確認單位為元／股、日期為臺北交易日。
- [ ] **TEAM-03** 每人只改自己的模組；改公共合約先同步，保留 git commit 或版本包。
- [ ] **TEAM-04** T+2、T+4、T+6 小時各跑一次短整合，不等全部做完才接線。

## 4. T+0:00～0:30：啟動與必要配置

- [x] **SETUP-01／P0** 將 `design1001.md`、本清單與九份官方檔放到專案；來源原樣保留到 `specs/official/`。首輪盤點確認已存在，本批未修改官方來源。
- [x] **SETUP-02／P0** 讀 F04／F07／F05；確認 ETF 清單 F03 只是參考，不可拿來交易。九份來源已讀；F05 文字盤點 150 個不重複代碼，100 TWSE／50 TPEX。
- [ ] **SETUP-03／P0** 建 Python 虛擬環境、pyproject 與 `etf_agent` package；核心依賴按設計 §16。第 01 批已建 `pyproject.toml`／package；虛擬環境與第三方依賴尚未建立。
- [ ] **SETUP-04／P0** 初始化 git 或版本包；不要把 key、登入資料、大量原始快取放進 git。
- [x] **SETUP-05／P0** 建 CLI 命令骨架與 exit code；`python -m etf_agent.cli --help` 可執行。第 01 批在 `PYTHONPATH=src` 下 help／contracts-demo exit 0，缺 fixture 回可讀錯誤及 exit 2；其他設計命令未實作。
- [ ] **SETUP-06／P0** 設 mode=demo、Asia/Taipei、`official_rules_confirmed=false`；未知官方截止、rounding 留 null。
- [ ] **SETUP-07／P0** TEAM 編號正式必填；demo 可用 DEMO_TEAM，不能照抄附件 TEAM_042。
- [x] **SETUP-08／P0** 建 `AgentDraft` schema／Provider 合約與所有輸入輸出型別；額外欄位不放行。第 01 批完成六種核心合約、`AgentResult`／`AgentProvider`、`DatasetSplitPlan`；30 項測試涵蓋未知欄位與草稿 `shares` 拒絕。內部 schema 已建立，JSON Schema 套件驗證尚未執行。
- [ ] **SETUP-09／P0** 建含合法白名單股票、完整價量、現金與持股的 fixtures；假資料／假庫存明確標示。第 01 批已有 25 檔假帳與 26 列兩日行情；未有完整 21 日價量及真正因子，維持未完成。
- [ ] **SETUP-10／P0** 驗證配置錯誤會回明確訊息；不把正式必要空值默默補成假官方規則。

完成證據：第 01 批上述程式／fixture／30 項合約測試；只完成已勾選項。全流程、正式模式與未勾選項不能據此視為完成。

## 5. T+0:30～2:00：資料與清洗

- [ ] **DATA-01／P0** 從 F05 擷取 `universe.csv`：四位字串代碼、名稱、TWSE／TPEX。
- [ ] **DATA-02／P0** 逐頁對照並測試 150 檔、100 上市、50 上櫃、無重複；抽查上市 2330／上櫃 5274。
- [ ] **DATA-03／P0** 取得官方交易日曆；前一交易日不以日期減 1 算，週末／休市也不造新資料。
- [ ] **DATA-04／P0** TWSE 至少下載一個真實回應／CSV，檢查欄位、日期、量值單位、錯誤頁。
- [ ] **DATA-05／P0** TPEx 同樣實測；若 API 不可用則取官方 CSV／快取，不漏 50 檔上櫃。
- [ ] **DATA-06／P0** 核對 OpenAPI 是否真的支援歷史日期；不能把 latest 回應存成請求的歷史日。
- [ ] **DATA-07／P0** 每檔核心因子用至少 21 個連續有效市場交易日；建議初次查 90 個日曆日。
- [ ] **DATA-08／P0** 每個 provider 加 timeout／限速／最多 2 次重試及快取；儲存所有原始資料、實際 URL、抓取時刻與 hash。
- [ ] **DATA-09／P0** 清理逗號／空白、ROC 日期；null 不填 0；所有量轉股、金額轉新臺幣元。
- [ ] **DATA-10／P0** 檢查 OHLC、日期、交易金額／股數、重複與價格異常；衝突不任選一列。
- [ ] **DATA-11／P0** 儲存停牌／無成交／公司行動狀態；無調整資料的事件區間股票不新建倉。
- [ ] **DATA-12／P0** 取得 TAIEX 歷史；市場級判斷有實際大盤資料，不能只靠單股平均。
- [ ] **DATA-13／P0** 把資料日／known_at／fetched_at 分開；盤前 packet 不含 T 日結算量值。
- [ ] **DATA-14／P0** 建 `account_snapshot` 匯入：cash、NAV、ticker／shares、結算日、origin、reconciled。
- [ ] **DATA-15／P0** 區分測試全現金帳、simulated、official_confirmed；測試 10 億本金不冒充實際官方期初帳。
- [ ] **DATA-16／P0** 產 `data_quality.json`，列可選股數、缺資料、單位確認、資料日期、demo旗標與阻擋原因。
- [ ] **DATA-17／P0** 不足20檔或缺NAV／庫存，回可讀失敗；不要硬補數字繼續。
- [ ] **DATA-18／P0** 如果改用 fixture，記錄切換原因；資料流程與報告中明確顯示 demo。
- [ ] **DATA-19／P0** 取得官方產業分類，讓40%產業上限可驗；全缺失時不能拿UNKNOWN繞過限制。僅demo明示關閉則報告列「產業分散未實作」。

完成證據／資料來源狀態：________。

## 6. T+2:00～3:00：特徵、排名與證據包

- [ ] **FACTOR-01／P0** 實作 mom20=`P_t/P_(t-20)-1`，收益率以小數。
- [ ] **FACTOR-02／P0** 實作 trend20=`P_t/SMA20-1`，SMA只用最近20交易日。
- [ ] **FACTOR-03／P0** 實作 vol20=`std(20 daily returns,ddof=1)*sqrt(252)`；檢查0波動不是填值或停牌。
- [ ] **FACTOR-04／P0** 實作 adv20、lot_nav_pct、current_weight、breadth與TAIEX特徵；流動性作 eligibility，不額外偷偷加分。
- [ ] **FACTOR-05／P0** 分位排名公式、平手平均、全相同0.5；低波動只反向一次。
- [ ] **FACTOR-06／P0** 使用固定 profile：mom20=.40、trend20=.25、lowvol=.35；不逐股更換權重。
- [ ] **FACTOR-07／P0** 儲存 features、每因子貢獻、score、排名、排除原因；平手以ticker固定順序。
- [ ] **FACTOR-08／P0** 做一筆手算小例：價格增長／下降／恆定，確認因子方向、觀測數及區間。
- [ ] **FACTOR-09／P0** 候選池＝前30＋全部原持股＋最多5分散候選；不得漏掉資料缺失的原持股。
- [ ] **EVIDENCE-01／P0** Python 建 sources／observations；S/O連號、authority與市場一致、values只有數值。
- [ ] **EVIDENCE-02／P0** 每個因子數字能對回原始列、區間與程式版本；計算值標明公式，不當作交易所直接公佈的欄位。
- [ ] **EVIDENCE-03／P0** 明確決定歷史 source 分組方式；正式 sources≤50、observations≤100，不能刪必要證據湊數。
- [ ] **EVIDENCE-04／P0** Evidence packet 含 cutoff、rules、account、rankings、原持股、baseline、O/S、allowed_tickers與品質報告。
- [ ] **EVIDENCE-05／P0** 凍結packet與hash；不要讓Agent接資料時自行改清洗結果。

完成證據：________。

## 7. T+3:00～4:00：真正的 Agent 決策與 API 預留

- [ ] **AGENT-01／P0** 本機執行 `codex --version`、`codex exec --help`，確認帳號登入與可用性。
- [ ] **AGENT-02／P0** 建 `prompts/decision.md`：只用packet、不造URL／數值、選股／held_reviews完整、反方證據與O引用。
- [ ] **AGENT-03／P0** `CodexProvider` 包裝CLI，shell=False、180秒timeout；events／stderr／最後draft各自儲存。
- [ ] **AGENT-04／P0** 用內部schema限制草稿；ticker只限allowed_tickers、conviction只准.8／1／1.2。
- [ ] **AGENT-05／P0** 真實呼叫一次：市場regime／stance／cash、最終選股、每檔原持股review與理由。
- [ ] **AGENT-06／P0** 無指令碼呼叫時，用互動Codex讀同packet／schema寫JSON，再接finalize；儲存實際執行記錄。
- [ ] **AGENT-07／P0** 比較baseline與Agent提案，記錄本次實際選擇；不強迫為展示而改答案。
- [ ] **AGENT-08／P0** 草稿引用斷裂／不合格式最多1次修正；超時／用量不足明確報錯。
- [ ] **AGENT-09／P0** 儲存真實model_version、起訖、CLI版本；沒有token資料就省略，不填假的0。
- [ ] **AGENT-10／P0** FixtureProvider僅供測試，標demo；不能當AGENT-05完成證據。
- [ ] **API-01／P0** config保留claude.enabled=false、base_url、api_key_env、model、max_tokens、timeout、預算／呼叫上限欄位。
- [ ] **API-02／P0** `ClaudeProvider` 同合約；尚未實作要明確NotImplementedError，不回空成功。
- [ ] **API-03／P0** 保證key不入config／prompt／log／git；provider切換共用同一配置與validator。

真實模型／run證據：________。

## 8. T+4:00～5:00：配置、整張化與風控

- [ ] **ALLOC-01／P0** 實作full portfolio targets，含所有原持股／退出股，不只算新增股票。
- [ ] **ALLOC-02／P0** 使用分數＋conviction／波動下限的配置；封頂後重分剩餘股票預算。
- [ ] **ALLOC-03／P0** 如果改等權fallback，報告與manifest記 allocation_method=equal_weight；不冒稱inverse-vol已完成。
- [ ] **ALLOC-04／P0** 25檔目標與現金目標；一般8%、2330 20%、產業40%為自訂；官方10%／25%另外驗。
- [ ] **ALLOC-05／P0** 加無交易帶、正常最多2組換股、gross turnover20%；初始化demo例外明列。
- [ ] **ORDER-01／P0** 用Decimal官方floor公式推目標shares與delta，不能用模型shares。
- [ ] **ORDER-02／P0** 測BUY／ADD／TRIM／SELL_ALL、剛好整張邊界、零delta歸no_trade。
- [ ] **ORDER-03／P0** JSON寫出後重讀重算股數，避免target_weight序列化改變floor結果。
- [ ] **ORDER-04／P0** 0張／count不足／現金超限時，修改target_weight或選股並重推；不直接手調訂單股數。
- [ ] **ORDER-05／P0** 非整張官方庫存先BLOCK並待確認，不自行抹除零股。
- [ ] **RISK-01／P0** 計fee後cash、NAV、每股權重、檔數；續抱股同樣算進去。
- [ ] **RISK-02／P0** 對帳戶snapshot版本檢查；生成期間庫存改變就重新推單。
- [ ] **RISK-03／P0** 壓力情境：買價上升／賣價下降、單股相對上漲、未成交導致count／cash變化。
- [ ] **RISK-04／P0** 違規方案回Agent限次修訂，記錄financial revisions；超過次數就停止。
- [ ] **RISK-05／P0** 最終選股／現金／意圖變動由Agent確認，不能風控默默改完仍留舊理由。

完成證據：________。

## 9. T+5:00～6:00：D-Plan 編譯與驗證

- [ ] **DPLAN-01／P0** 正式JSON只用F04允許欄位；內部風險指標、manifest與報告另存。
- [ ] **DPLAN-02／P0** 每個order引用decision→inference→observation→source；ID連續、唯一、無跳號／前導零。
- [ ] **DPLAN-03／P0** 原持股完整覆蓋，decisions與no_trade互斥；每檔續抱有相關證據與理由。
- [ ] **DPLAN-04／P0** 動作按起訖股數分類；orders ticker／方向／股數／decision_ref完全吻合。
- [ ] **DPLAN-05／P0** net_flow與increase／reduce／hold一致；現金宣告區間包含前收估算，不能事後隨便改姿態。
- [ ] **DPLAN-06／P0** funding_for只指同日BUY／ADD；刪掉全部調度賣出後才真有現金缺口。
- [ ] **DPLAN-07／P0** sources≤50、O≤100、I≤60、D≤30、orders≤30；每層refs數量／字數符合schema。
- [ ] **DPLAN-08／P0** 正確檔名 `D-Plan_<真實team_id或demo編號>_<trade_date>.json`；內容一致、時間+08:00。
- [ ] **VALID-01／P0** Draft202012Validator＋FormatChecker；另parse日曆與timestamp，不只比regex。
- [ ] **VALID-02／P0** F08與F09的結構驗證；F09 I9由語意層抓到，F08不作缺完整庫存的端到端金標準。
- [ ] **VALID-03／P0** 設計§13 L01～L15逐項輸出機器可讀結果；LLM寫risk_check不算通過。
- [ ] **VALID-04／P0** 超賣、非2330超10%、白名單外、cash／posture矛盾全部BLOCK。
- [ ] **VALID-05／P0** demo／未知必要官方規則／未核對庫存，使submission_ready=false；不能進正式輸出目錄。
- [ ] **VALID-06／P0** 本地較嚴檢查即使通過，也不宣稱完整官方server驗證通過。

完成證據：________。

## 10. T+6:00～7:00：庫存、結算、核對與版本

- [ ] **LEDGER-01／P0** SQLite最小表；股數整數、Decimal以字串儲存、transaction一次完成。
- [ ] **LEDGER-02／P0** projected／simulated／official_confirmed三狀態分開；提交成功不直接加股數。
- [ ] **LEDGER-03／P0** 使用T日官方amount／volume算成交均價；買賣0.1425%手續費、賣另0.3%稅。
- [ ] **LEDGER-04／P0** 只有實際filled才變cash與shares；無成交價not_filled，資訊不足unknown。
- [ ] **LEDGER-05／P0** 期末NAV按期末持股×官方收盤＋cash；rounding未確認時標demo假設。
- [ ] **LEDGER-06／P0** 相同plan_hash重複settle不再次扣款；同日v1／v2不能都當成交。
- [ ] **LEDGER-07／P0** reconcile逐股、cash、NAV；金額容差依確認規則，不任意放大。
- [ ] **LEDGER-08／P0** 有差異儲存並阻擋隔日正式賣出；官方權威snapshot取代下單依據但不刪模擬證據。
- [ ] **VERSION-01／P0** 每run獨立目錄；儲存raw／cleaned／features／packet／prompt／draft／orders／validation／report。
- [ ] **VERSION-02／P0** 儲存source／account／outputs hash；schema與config／prompt修改也換code_version。
- [ ] **VERSION-03／P0** git乾淨用commit；有dirty變更用已儲存的版本包hash，不能只記舊commit。
- [ ] **VERSION-04／P0** metadata真實、不打包key；申報起訖不能晚於實際收件時刻。
- [ ] **VERSION-05／P0** 內部日run_id與最終官方檔名分開；重繳保留兩版及最後有效plan／receipt對應。

完成證據：________。

## 11. T+7:00～8:00：整合與開會材料

- [ ] **TEST-01／P0** 完整demo：真實Codex→配置→D-Plan→驗證→報告。
- [ ] **TEST-02／P0** 無交易日全部持股覆蓋，orders=[]／decisions=[]仍合法。
- [ ] **TEST-03／P0** 一筆錯誤引用（I9）確實被BLOCK。
- [ ] **TEST-04／P0** 超賣／現金負／單股超限／非千股三類以上財務錯誤被BLOCK。
- [ ] **TEST-05／P0** T日結算資訊誤入盤前輸入會被BLOCK。
- [ ] **TEST-06／P0** funding_for缺口不存在與宣告reduce但淨買，兩者被BLOCK。
- [ ] **TEST-07／P0** 結算無成交不加庫存；重跑不重複扣款；官方fixture差異能顯示。
- [ ] **TEST-08／P0** 儲存draft離線replay，orders／費用／財務結果相同；不要求再次詢問LLM字句一致。
- [ ] **TEST-09／P0** 全部核心測試 `python -m pytest -q` 通過；記錄真實結果及失敗項，不寫預期當結果。
- [ ] **MEETING-01／P0** 報告列資料日期、來源、active因子、每因子意義與排名、資料品質與缺項。
- [ ] **MEETING-02／P0** 展示Agent選股／不交易理由、市場姿態、反方證據及baseline差異。
- [ ] **MEETING-03／P0** 展示實際張數、cash、fee、全組合權重／產業、風險與壓力測試結果。
- [ ] **MEETING-04／P0** 展示D-Plan引用鏈與驗證結果，不只展示JSON長相。
- [ ] **MEETING-05／P0** 展示提交≠成交、三種庫存狀態、第二日可賣依據與版本重播。
- [ ] **MEETING-06／P0** 最終報告標「demo／可提交性」，列正式尚未確認項目。
- [ ] **MEETING-07／P0** 儲存可交給隊友的程式版本、啟動方式、demo RUN_ID與報告；準備約10分鐘演示。

完成證據／測試結果：________。

## 12. 會議後再做：不佔這8小時

- [ ] **P1-01** 接法人買賣超與月營收，並確認point-in-time公告／單位／coverage。
- [ ] **P1-02** 接60日動能、估值／品質；因子profile全run一致，不逐股改權重。
- [ ] **P1-03** 確認原價／還原價／除權息與分割策略；回測／官方NAV不同口徑分別處理。
- [ ] **P1-04** 用時間序列驗證比較多因子baseline、線性模型／LightGBM；扣實際費用、禁止隨機切分。第 01 批按使用者要求預留歷史時間／版本與 `DatasetSplitPlan`，拒絕 train／validation／test 重疊或未鎖定測試期；實際長期資料、交易日 gap／標籤隔離、回測與訓練未實作。
- [ ] **P1-05** 真實Claude API adapter，確認可用模型、結構化輸出支援、真實費用記錄／預算控制。
- [ ] **P1-06** 接官方驗證器（主辦方有釋出才接）；記錄版本與本地驗證差異。
- [ ] **P1-07** 有需要才做排程、通知、UI、海外行情／新聞；新來源仍須儲存可核實證據。

## 13. 正式參賽前：LIVE 阻擋條件

不要求這8小時內取得主辦方所有答案，但必須在報告列為未確認，正式模式不能跳過。

- [ ] **LIVE-01** 核對最新完整競賽辦法與schema／指南版本；儲存檔案與hash。
- [ ] **LIVE-02** 核對正式初始本金、期初持股／建倉流程與實際帳號NAV，不使用範例1.02億元。
- [ ] **LIVE-03** 填入每日收件截止、伺服器時戳／延遲規則、允許資料時間區間；確認可否用T日試撮。
- [ ] **LIVE-04** 核對費用rounding、均價量值口徑、NAV／cash ratio分母、權重取價與容差。
- [ ] **LIVE-05** 核對無成交／停牌、除權息／股利／分割、零股庫存與未成交後修正程式。
- [ ] **LIVE-06** 核對官方AI實際參與／模型紀錄／資格審查與重跑要求；每日真實決策與code_version證據完整。
- [ ] **LIVE-07** 匯入實際主辦方結算，精確核對庫存、cash、NAV；未核對不能正式賣出。
- [ ] **LIVE-08** 150檔、價格、資料時間、sources與引用可核實；無測試／示意行情或網址冒充真實。
- [ ] **LIVE-09** 按F01正式寫ETF說明書：名稱「主動」開頭20字內、主題50字內、理念100～300字，與實際因子一致。
- [ ] **LIVE-10** 檢查上傳檔案寫的公開說明書區間2026-10-21～10-26，並與最新公告核對。
- [ ] **LIVE-11** 指定唯一提交者；驗證通過後提交、儲存官方接收／驗證／最終採用plan證據。
- [ ] **LIVE-12** 收盤後核對實際結算，第二日原持股全覆蓋；未解決差異不能繼續賣。
- [ ] **LIVE-13** 若使用Google Credit：F06要求任一隊員完成指定課程，以報名email提交截圖；附件時段2026-09-20～10-19，預估約3工作日核驗。這是隊員行政工作，不由程式自行寄信。
- [ ] **LIVE-14** 實際核實Token Credit抵免金額／計價／序號及兌換期限；9／200是課程積分，附件兌換11/30前、餘額12/31後失效。
- [ ] **LIVE-15** 確認本地Codex／Claude可用額度與備用處理；超時或沒額度不能編造AI結果。

## 14. 會議要決定的事

- [ ] 是否採用跨產業動能與風險控制主題，或換成需要產業分類證據的AI／半導體主題。
- [ ] P0三個價格因子作baseline是否合理；下一步優先補法人、營收還是更長歷史。
- [ ] 是否接受目前現金／換股／產業限制；任何調整先改config、版本與驗證，不當場手改orders。
- [ ] 由誰處理官方規則未確認項，誰負責任每日庫存核對與提交。
- [ ] MVP缺項的優先順序：先解決正式規則／資料／庫存，再評估預測模型與UI。

會議結論／下一版任務：________。

## 15. 最短執行方式

先將 `AGENTS.md`、`design1001.md`、本清單放在專案根目錄，九份來源依設計 §2.1 的標準檔名放在 `specs/official/`。從專案根目錄開啟本地Codex，貼上 `design1001.md` §20.1 的新合作prompt。第一回合先讀文件與討論，達成共識後才實作第一批；每批完成後更新清單與開發紀錄並附證據，再討論下一批。

程式建好後，以實際交易日／RUN_ID取代佔位符：

```bash
python -m etf_agent.cli run --trade-date YYYY-MM-DD --mode demo --provider codex_cli --data-mode cached
python -m etf_agent.cli report --run-id RUN_ID
python -m pytest -q
```

這些是待實作的命令合約，目前不能據此宣稱專案已可以執行。
