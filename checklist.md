# 玉山 AI CUP：8 小時 MVP 實作 Checklist

對應設計：`design1001.md` v0.3、`AGENTS.md` v1.0｜日期：2026-10-11

**本清單按實際驗收記錄，未勾選項目仍未完成。** 2026-10-11 已完成第 01～09 批合約、歷史樣本、CSV 格式、白名單及覆蓋檢查，以及第 10 批 F05 全股票月報下載功能。白名單共 150 檔（100 TWSE／50 TPEX）；2025-09 實際取得 147 檔、3,075 列，產生 21 個日檔及 147 個股月檔。3718／7769／7828 官方端點未回傳該月行情，後續已核實上市／上櫃日期均晚於該月；7750 僅回傳 2025-09-17～09-30 共 9 筆。前 12 個日檔 146／150、後 9 個日檔 147／150，缺件如實記錄，未宣稱完整覆蓋。第 10 批全套 132 項測試（30 核心合約＋36 歷史資料＋25 白名單＋28 覆蓋＋13 全股票下載）通過。CSV 4.0／22 欄及千元／張、張、千元等單位維持，核心合約仍用股與元。重複的 `history_sample` 目錄已清理，兩檔原始來源、行情及必要追溯／驗收證據併入全股票目錄，舊覆蓋報告保持原文；完整資料時間核實、公司行動、每日更新、因子、投資模型、配置、D-Plan、SQLite 帳務與回測仍待逐批實作。進度與授權統一記錄於 `development_notes.md`。

第 15 批已完成 2025-09-30 的 146 檔歷史原價三因子分析 CSV、metadata JSON 與閱讀摘要，3 項重點測試通過，未重跑全套。第 16 批補齊指標理由／意義並整理 README 的架構與九命令入口、專屬操作文件，受影響匯出測試通過。第 13 批官方排程日曆及視窗為兩市場各 21 日，另外四檔不足沿用既有紀錄；第 14 批閱讀 CSV 已移除重複預期日期，缺失後續工作列 DATA-22。臨時休市、公司行動／return_close 與歷史可知時間仍待核實，正式資格仍 false；正式 FeatureTable／快照、排名及模型尚未串接。第 08～12 批累積修改已推送 `72a885b`，第 13～16 批納入本次 COMMIT PUSH 範圍，Git 操作與授權見 development_notes 的對應 Git 紀錄。

第 01 批證據：`src/etf_agent/contracts.py`、`agent/base.py`、`cli.py`、`specs/internal/agent_draft.schema.json`、`tests/fixtures/contracts_demo.json`、`tests/test_contracts.py`、`docs/data_contracts.md`。PowerShell 先設定 `$env:PYTHONPATH = (Resolve-Path 'src').Path`；`python -B -m etf_agent.cli contracts-demo --fixture tests/fixtures/contracts_demo.json` 成功，25 檔持股市值 90,000,000.00 元＋現金 10,000,000.00 元＝NAV 100,000,000.00 元；`python -B -m unittest discover -s tests -p test_contracts.py` 為 30 tests、OK。全部為人工測試資料，`submission_ready=false`。

每完成一項才把 `[ ]` 改成 `[x]`，並在旁邊留下測試結果／檔案路徑。若卡住，寫問題與採用的替代路徑，不直接勾選。`P0` 是這 8 小時必要；`P1` 延到會議後；`LIVE` 是正式參賽前必做，不以 demo 通過取代。

## 0. 每批都要遵守的合作方式

合作規則已提供於 `AGENTS.md`，下列項目用來檢查開發過程是否遵守，不代表本次已經建立 Python 專案。三份 Markdown 放在專案根目錄，九份來源依設計 §2.1 放在 `specs/official/`；再貼 `design1001.md` §20.1 的新 prompt，取代舊版直接開工要求。

- [x] **COOP-01** 第一回合僅讀設計、來源與必要專案指示，先解釋流程與第一批方案；不改檔、不安裝、不執行專案程式或付費呼叫。證據：2026-10-11 首輪九份來源盤點；`development_notes.md`。
- [ ] **COOP-02** 每批約10～30分鐘，只處理一個可展示結果的小任務；討論與驗收算進8小時。
- [ ] **COOP-03** 事前講清目的、輸入輸出、修改檔案、指令、連網／模型用量與驗收方式。
- [ ] **COOP-04** 用具體例子與1～2個關鍵問題確認理解；回答疑問後等待明確同意，不把沉默或詢問當授權。
- [ ] **COOP-05** 同意只涵蓋列出的本批實作／驗證；同範圍修正可繼續，擴大範圍、加依賴、改合約／參數或付費服務則重新討論。
- [ ] **COOP-06** 完成後展示輸出、實際測試、如何重跑與未完成項目，再討論下一批；不一次做完全部清單。
- [x] **COOP-07** 確認已讀取根目錄提供的AGENTS.md；在同意的首批範圍內建立簡短development_notes.md，之後保存已同意決定、授權範圍與完成證據。第 01 批已建立 `development_notes.md`；原另建日記，依使用者最新指示已整併，後續只更新 `development_notes.md`。
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
- [x] **SETUP-04／P0** 初始化 git 或版本包；不要把 key、登入資料、大量原始快取放進 git。Git-01 已初始化 `main`，初始提交 `d6cd05f` 已推送；目前私有倉庫為 [ismesid/yushan-etf-agent-MVP](https://github.com/ismesid/yushan-etf-agent-MVP)。已建立 `.gitignore`／`.gitattributes`／README；九份官方來源逐位元比對 PASS，金鑰與私人資料路徑已排除。
- [x] **SETUP-05／P0** 建 CLI 命令骨架與 exit code；`python -m etf_agent.cli --help` 可執行。第 01 批在 `PYTHONPATH=src` 下 help／contracts-demo exit 0，缺 fixture 回可讀錯誤及 exit 2；其他設計命令未實作。
- [ ] **SETUP-06／P0** 設 mode=demo、Asia/Taipei、`official_rules_confirmed=false`；未知官方截止、rounding 留 null。
- [ ] **SETUP-07／P0** TEAM 編號正式必填；demo 可用 DEMO_TEAM，不能照抄附件 TEAM_042。
- [x] **SETUP-08／P0** 建 `AgentDraft` schema／Provider 合約與所有輸入輸出型別；額外欄位不放行。第 01 批完成六種核心合約、`AgentResult`／`AgentProvider`、`DatasetSplitPlan`；30 項測試涵蓋未知欄位與草稿 `shares` 拒絕。內部 schema 已建立，JSON Schema 套件驗證尚未執行。
- [ ] **SETUP-09／P0** 建含合法白名單股票、完整價量、現金與持股的 fixtures；假資料／假庫存明確標示。第 01 批已有 25 檔假帳與 26 列兩日行情；未有完整 21 日價量及真正因子，維持未完成。
- [ ] **SETUP-10／P0** 驗證配置錯誤會回明確訊息；不把正式必要空值默默補成假官方規則。

完成證據：第 01 批上述程式／fixture／30 項合約測試；只完成已勾選項。全流程、正式模式與未勾選項不能據此視為完成。

## 5. T+0:30～2:00：資料與清洗

- [x] **DATA-01／P0** 從 F05 擷取 `universe.csv`：四位字串代碼、名稱、TWSE／TPEX。第 08 批已產生 `data/universe.csv`／`universe.manifest.json`；純標準庫解碼三頁 PDF 文字，名稱沿用官方原文，保存來源／CSV hash、版本及每檔來源頁碼。
- [x] **DATA-02／P0** 逐頁對照並測試 150 檔、100 上市、50 上櫃、無重複；抽查上市 2330／上櫃 5274。第 08 批核對頁 1 TWSE 60、頁 2 TWSE 40＋TPEX 16、頁 3 TPEX 34；`universe-check` exit 0，2330 台積電／TWSE、5274 信驊／TPEX。25 項白名單測試涵蓋上述檔數、未知代號／錯市場、重複、格式、缺檔與來源完整性；全套 91 tests、OK。
- [ ] **DATA-03／P0** 取得官方交易日曆；前一交易日不以日期減 1 算，週末／休市也不造新資料。第 13 批已取得兩市場官方年度排程，2025-09 各 21 個排程交易日、9/29 休市；臨時全市場休市仍未全面核實，actual_sessions_verified=false，完整實際日曆維持未勾選。
- [x] **DATA-04／P0** TWSE 至少下載一個真實回應／CSV，檢查欄位、日期、量值單位、錯誤頁。第 02 批 `history-sample --month 2025-09` 實際 HTTP 200，2330 共 21 筆；JSON／原表 CSV／統一格式 CSV 已保存，股／元欄位及原始 SHA-256 核對通過；HTML 與 HTTP 拒絕的離線測試通過。
- [ ] **DATA-05／P0** TPEx 同樣實測；若 API 不可用則取官方 CSV／快取，不漏 50 檔上櫃。第 10 批依 F05 處理全部 50 檔上櫃，2025-09 取得 48 檔、3718／7828 回傳空月；先前 5274 樣本已核對重用。月報為整數張／仟元且不含鉅額，核心精確股數／金額留空，reported 欄位僅換算；完整覆蓋及正式精確量值／成交口徑仍待核實，本項維持未勾選。
- [ ] **DATA-06／P0** 核對 OpenAPI 是否真的支援歷史日期；不能把 latest 回應存成請求的歷史日。第 02 批確認兩市場個股月報查詢回傳指定 2025-09 並拒絕錯月；latest OpenAPI 加日期的能力未測試，不宣稱可查歷史。
- [ ] **DATA-07／P0** 每檔核心因子用至少 21 個連續有效市場交易日；建議初次查 90 個日曆日。第 13 批依官方排程核對截至 2025-09-30 的 21 個日期，146 檔價格視窗完整、7750 僅 9 筆、3 檔為 0 筆；缺日不縮窗或補值。臨時休市、公司行動／return_close 與歷史可知時間尚未核實，尚無因子計算，維持未勾選。
- [ ] **DATA-08／P0** 每個 provider 加 timeout／限速／最多 2 次重試及快取；儲存所有原始資料、實際 URL、抓取時刻與 hash。既有每請求 10 秒 timeout、獨立版本目錄、TLS 驗證與 raw 保存保持；第 10 批新增全股票下載單線、每兩個實際 HTTP 請求至少間隔 1 秒，核對快取 hash／月份／股票／來源後保留原 fetched_at 重用。150 個來源實跑 148 HTTP＋2 快取，逐股 manifest 原子保存可供續接。尚無自動重試或 HTTP 快取過期管理，本項維持未勾選。
- [ ] **DATA-09／P0** 清理逗號／空白、ROC 日期；null 不填 0；所有量轉股、金額轉新臺幣元。月報樣本已實作上述內部轉換，單位／精度不符會停止；第 03 批閱讀 CSV 另用張顯示，不影響內部股數。上櫃核心量值暫留空，不把張／仟元縮位值當精確資料。全市場清洗仍未完成。
- [ ] **DATA-10／P0** 檢查 OHLC、日期、交易金額／股數、重複與價格異常；衝突不任選一列。月報樣本已檢查日期／股票／OHLC／非負與零成交量值／重複衝突；完整成交均價口徑與異常政策仍未完成。
- [ ] **DATA-11／P0** 儲存停牌／無成交／公司行動狀態；無調整資料的事件區間股票不新建倉。
- [ ] **DATA-12／P0** 取得 TAIEX 歷史；市場級判斷有實際大盤資料，不能只靠單股平均。
- [ ] **DATA-13／P0** 把資料日／known_at／fetched_at 分開；盤前 packet 不含 T 日結算量值。第 02 批保留真實 fetched_at、trade_date、hash，無證據的 known_at 留空；未建真實盤前 packet 或核實歷史發布版本。
- [ ] **DATA-14／P0** 建 `account_snapshot` 匯入：cash、NAV、ticker／shares、結算日、origin、reconciled。
- [ ] **DATA-15／P0** 區分測試全現金帳、simulated、official_confirmed；測試 10 億本金不冒充實際官方期初帳。
- [ ] **DATA-16／P0** 產 `data_quality.json`，列可選股數、缺資料、單位確認、資料日期、demo旗標與阻擋原因。第 02 批已有兩檔下載範圍的品質報告與限制；第 09 批已驗收獨立日表對 F05 的覆蓋率、有效價格與缺件報告。全股票池正式可選股數、交易日曆／截止／來源核實及正式阻擋檢查仍未完成，因此本項維持未勾選。
- [ ] **DATA-17／P0** 不足20檔或缺NAV／庫存，回可讀失敗；不要硬補數字繼續。
- [ ] **DATA-18／P0** 如果改用 fixture，記錄切換原因；資料流程與報告中明確顯示 demo。
- [ ] **DATA-19／P0** 取得官方產業分類，讓40%產業上限可驗；全缺失時不能拿UNKNOWN繞過限制。僅demo明示關閉則報告列「產業分散未實作」。
- [x] **DATA-20／資料輔助** 依 F05 全 150 檔取得一個已完成月份，保存每檔成功／失敗、原始來源及每日／每股月 CSV；日／月內容一致，缺日缺股不補造。第 10 批 2025-09 實跑、132 項測試及下方產物核對通過。此項完成的是下載功能與取得範圍核對，不等於 150／150 完整行情或正式資料合格。
- [x] **DATA-21／資料輔助** 保存兩市場官方月份排程，依資料截止日離線檢查 150 檔的 21 筆價格視窗，另存逐股 CSV／JSON／閱讀摘要。第 13 批兩個 CLI 實跑 exit 0，4 項重點測試通過；完成的是排程及價格缺件診斷，正式資格仍 false。
- [ ] **DATA-22／後續資料工作** 使用者已接受 2025-09 的四檔不足原因，下一批優先討論因子分析，不再查缺失。後續需區分掛牌前本來無該市場行情、新股尚未累積 21 筆、停牌／無成交、API／檔案意外遺漏；跨月視窗讀取與必要下載另列批次。掛牌前不補造行情，新股累積足夠有效價格再納入；意外遺漏才評估續抓。臨時休市、公司行動／調整價與歷史可知時間依 DATA-03／11／13 後續補齊，正式用途前再驗收。第 14 批僅記錄待辦，未實作上述政策。

第 14 批閱讀表調整：依使用者要求，`window_coverage.csv` 移除逐股重複的 expected_dates，改為 13 欄；missing_dates／invalid_price_dates 有缺失才列日期。程式匯出與目前開啟的 150 列 CSV 已同步，其他欄位值保持一致；JSON／日曆仍保存完整預期日期。DATA-22 是後續待辦，不宣稱缺失政策已完成，因子功能仍待新批次同意。

第 13 批證據：[官方排程 CSV](data/cache/calendar/2025-09/20261011T154421_1306c9a4/calendar.csv)、[排程來源及版本](data/cache/calendar/2025-09/20261011T154421_1306c9a4/calendar.json)、[150 檔價格視窗 CSV](data/cache/history_windows/2025-09-30/20261011T154440_9842e79e/window_coverage.csv)、[閱讀摘要](data/cache/history_windows/2025-09-30/20261011T154440_9842e79e/window_report.md)。新增 `calendar.py`／`history_windows.py` 及兩個 CLI；日曆下載本身 2 次官方 HTTPS，視窗完全離線，沒有缺整日日表、input_valid=true。僅執行本批 4 項測試（0.195s）：完整視窗、週末／休市且不讀未來日、缺整日日表／新股不足，以及實際遇到的回應錯年防護；未重跑全套，前批 132 項通過證據仍是歷史紀錄。原下載 manifest／行情不改，actual_sessions_verified／submission_ready 均 false。重跑方式與授權見 `development_notes.md` 第 13 批。

第 10 批全股票月報證據：[資料 manifest](data/cache/history_universe/2025-09/20261011T145716_6e56c903/manifest.json)、[逐日覆蓋／缺件](data/cache/history_universe/2025-09/20261011T145716_6e56c903/coverage.json)、[2025-09-01 日表](data/cache/history_universe/2025-09/20261011T145716_6e56c903/daily/2025-09/2025-09-01_prices.csv)、[2330 月表](data/cache/history_universe/2025-09/20261011T145716_6e56c903/monthly/2025-09/TWSE_2330_2025-09.csv)。150 個來源均有狀態與 raw，147 個月表／來源 CSV、21 個日檔共 3,075 列；150 raw hash 全部相符，日／月每欄值完全一致、3,075 個日期×股票唯一鍵，報告缺件集合一致。原兩檔快取保留 hash／fetched_at／版本，其餘 148 次真實官方 HTTPS。`history-universe` 已接 CLI，全套 132 tests、OK（13.821s）；錯月份 CLI 原生 exit 2 且未建輸出。下載有 3 檔缺件，coverage_complete／submission_ready 均 false；其他正式／完整資料項目維持未勾選。

後續缺件核實及資料清理：[2025-09 行情可取得範圍](docs/history_availability_2025-09.md) 保存官方上市／上櫃日期及來源。3718／7769／7828 在該月尚未上市／上櫃，不填零、不補前身代號或興櫃行情、不改 F05 的 150 檔及原下載 manifest／coverage。全股票目錄為現行分析入口；原 `data/cache/history_sample/` 經重複資料核對後已清理。[樣本 manifest 原文](data/cache/history_universe/2025-09/20261011T145716_6e56c903/sample_manifest.json) 與 `provenance/history_sample/` 共保留七份追溯／驗收證據；兩份 raw／原表 CSV 與原價量已在全股票目錄。兩股離線匯出使用 `history-export --manifest data/cache/history_universe/2025-09/20261011T145716_6e56c903/sample_manifest.json --output data/cache/history_export`；重跑第 09 批 2／150 可用 [保存的樣本日表](data/cache/history_universe/2025-09/20261011T145716_6e56c903/provenance/history_sample/input/2025-09-01_prices.csv)。不勾選日曆／公司行動或正式品質項目。

清理驗收：[cleanup.json](data/cache/history_universe/2025-09/20261011T145716_6e56c903/provenance/history_sample/cleanup.json) 記錄刪除 33 檔、68,275 bytes 及七份證據保存位置／hash。清理後全套 132 tests、OK（13.556s），樣本 manifest 已實測零 HTTP 重建 42 列／21 日檔，首日檔與保存的原輸入逐位元相同；原輸入也重跑 2／150 覆蓋。原全股票 468 檔、九份官方來源與兩份白名單檔案 hash 全不變，暫存驗證輸出已清理；本批沒有更動程式或正式資料合格條件。

第 12 批清理：依使用者指示刪除 `data/cache/history_probe/`；其中兩份探測 JSON 已在全股票資料保存，無程式／文件／快取引用。只做必要的目標、依賴與刪除結果確認，未跑全套測試。後續驗證優先關鍵行為與常見案例，依改動影響選擇範圍，合作偏好見 `development_notes.md` 第 12 批。

第 08 批白名單證據：`src/etf_agent/universe.py`／`tests/test_universe.py`、`data/universe.csv`／`universe.manifest.json`。版本 `F05-v1-c12c57571f22`，PDF 與 CSV 完整 SHA-256 記在 manifest；載入器核對雙 hash、150／100／50 與三欄格式。PowerShell 設定 `PYTHONPATH=src` 後執行 `python -B -m etf_agent.cli universe-check --universe data/universe.csv` 或 `python -B -m unittest discover -s tests -p test_universe.py`。當時白名單尚未串接行情下載；第 10 批已接入月報下載，目前仍未串接因子／Agent，不能因此勾選全市場完整行情、正式候選池或交易驗證；F05 也不是已核實的歷史時點股票池。

第 09 批覆蓋驗收證據：沿用中斷前已存在的 `src/etf_agent/coverage.py`／`tests/test_coverage.py` 與 CLI `prices-check`，本批沒有重建白名單或修改程式。全套 119 tests、OK（1.736s）；28 項覆蓋測試包含錯日期／市場／重複、缺件、價格與 CLI exit 2 診斷。真實歷史日表實測 exit 0，另存 [覆蓋報告](data/cache/coverage/2025-09-01/20261011T144802_4463a889/coverage.md)，取得 2／150、缺 148（TWSE 99／TPEX 49）、有效價格 2、原列 tradable=true 為 0、submission_ready=false；缺件 CSV 148 個唯一代號與白名單差集一致。當時另核對全部 21 個日表、42 列均符合相同覆蓋結果，禁止 HTTP／外部程序的核對中沒有網路呼叫。當時輸入、官方來源、白名單與舊報告保持不變；後續樣本目錄清理將重跑所需輸入原文另存，舊報告仍保留原輸入路徑與 hash。本機快取由 Git 忽略。當時使用者選擇下一批完整行情先做 2025-09、沿用 CSV，待第 10 批同意後才下載。

第 02 批樣本證據：首次下載的舊目錄依使用者要求刪除後，兩份原始 JSON／原表 CSV 及下載 manifest 原文曾保存於第 03 批樣本目錄。該樣本目錄現也已清理，raw／原表 CSV 保留於全股票目錄，首次 manifest 原文保存於 [provenance/history_sample/original_manifest.json](data/cache/history_universe/2025-09/20261011T145716_6e56c903/provenance/history_sample/original_manifest.json)。檔案由 Git 忽略。`src/etf_agent/history.py`／`providers/`／CLI 已能重跑；當時 `tests/test_history.py` 25 項及原 30 項合約測試合計 55 tests、OK。功能與現存產物連結見 `docs/data_contracts.md`；這不代表本節其他未勾選項已完成。

第 03 批格式驗收：`data/cache/history_sample/2025-09/20261011T125021_603f0054/` 的合併／個股 CSV 顯示 `volume_lots`／`reported_volume_lots`，不放 source_url；網址、精度及來源版本仍在 manifest。離線 `history-export` exit 0，42 列保留原價量、時間與 hash，股張換算可回復；TWSE 23,022,319 股＝23,022.319 張，TPEx 報表 356 張但精確值仍空。manifest 為 network_requests=0、CSV 2.0，核心合約1.0；59 tests（30＋29）OK，舊版與原始證據不覆寫。此批沒有勾選任何新的全市場資料／交易功能。

後續清理：使用者要求直接刪除舊樣本，已移除 `20261011T122548_f1b87c04` 資料夾；刪除前確認新版原始檔與舊版相同、保留舊 manifest 原文及 hash，刪除後確認新版 42 列仍完整。README／功能文件及重跑指令改指向現存新版；程式仍按原方式每次建立新匯出目錄，此次清理沒有修改程式。

第 04 批格式驗收：依使用者選擇，當時 `20261011T125021_603f0054/` 三份閱讀 CSV 就地替換為 3.0，仍 42 列。價格欄 `_ktwd_per_lot` 表示千元／張，成交金額 `_ktwd` 表示千元；移除 CSV raw_sha256，保留 manifest 完整 hash／data_version 與核心合約。新增精確量值推算與 reported 估算均價，TPEx 精確均價空；均價顯示 8 位小數僅供閱讀，零量／缺值不補。63 tests（30 合約＋33 歷史）OK，逐列換算／時間／版本與原始檔 hash 核對通過，新版 manifest CLI 離線重輸出成功且零 HTTP。CSV 2.0 manifest 原文當時保存在 `provenance/csv_v2_manifest.json`，現另存全股票目錄 `provenance/history_sample/csv_v2_manifest.json`；原始 JSON／原欄位 CSV 不變。正式結算、公司行動及防洩漏缺項未完成，因此未勾選新的交易／回測功能。

第 05 批來源檔整理：兩份原欄位 CSV 已移到同 run 的 `source_csv/2025-09/`，檔名改為 `TWSE_2330_2025-09_source.csv`／`TPEX_5274_2025-09_source.csv`，移動前後 SHA-256 相同、舊同名來源檔不存在；產生器與 manifest 路徑同步。新增一項行為測試，歷史 34 tests、OK；既有離線重輸出測試亦確認不依賴手動改動的 source_csv。三份閱讀 CSV 仍為格式 3.0。每日／每股月視圖、可使用交易日及移除閱讀表原單位欄僅討論，尚未實作，不勾選日曆或防洩漏功能。

第 06 批視圖驗收：使用者同意日／月結構及移除閱讀表原單位欄。現存 run 的 `daily/2025-09/` 已有 21 個日期 CSV、每檔 2 列；`monthly/2025-09/` 有 2330／5274 各 21 列。CSV 4.0 共 22 欄，日／月來源相同；來源單位只在 manifest／source_csv。逐列比對舊 42 列，除刪除兩個來源單位欄之外所有值、時間與版本相同，42 個日期×股票唯一鍵，日／月資料一致；原始 JSON／source_csv／既有 provenance 共 7 檔 hash 不變。舊根目錄合表及兩個股閱讀 CSV 已刪除，前 manifest 保存為 `provenance/daily_monthly_manifest.json`。36 tests 歷史驗收 OK，新版 manifest CLI 離線重新匯出成功且零 HTTP。每日檔案是歷史資料視圖，不是每日抓取排程或 150 檔覆蓋；known_at／usable_from 日期規則仍未實作，不勾選正式快照／回測功能。

第 07 批文件補充：data_contracts 1.7 解釋 TPEx 精確欄空值與 reported 報表量值的差別，評估後保留 exact_volume_amount（品質資訊，非打分或選股開關）；README 移除詳細清洗說明，連至資料說明。CSV 4.0／程式及既有測試證據不變，本批只驗文件與本機連結；未實作因子／流動性估算政策或正式結算，不勾選新資料功能。

## 6. T+2:00～3:00：特徵、排名與證據包

- [x] **FACTOR-01／P0** 實作 mom20=`P_t/P_(t-20)-1`，收益率以小數。第 15 批 `features.py` 純函式與原價分析已驗收；內部 Decimal 小數、JSON 保存文字，閱讀 CSV 才顯示百分數；正式調整價格／候選資格另待核實。
- [x] **FACTOR-02／P0** 實作 trend20=`P_t/SMA20-1`，SMA只用最近20交易日。第 15 批明確使用 21 筆中的最後 20 筆平均，手算及實際兩股獨立核對通過；不把 21 筆全平均當 SMA20。
- [ ] **FACTOR-03／P0** 實作 vol20=`std(20 daily returns,ddof=1)*sqrt(252)`；檢查0波動不是填值或停牌。第 15 批已完成樣本波動公式（分母 19）及年化、固定價格回傳 0；停牌／零波動的正式資格政策仍未實作，完整本項維持未勾選。
- [ ] **FACTOR-04／P0** 實作 adv20、lot_nav_pct、current_weight、breadth與TAIEX特徵；流動性作 eligibility，不額外偷偷加分。
- [ ] **FACTOR-05／P0** 分位排名公式、平手平均、全相同0.5；低波動只反向一次。
- [ ] **FACTOR-06／P0** 使用固定 profile：mom20=.40、trend20=.25、lowvol=.35；不逐股更換權重。
- [ ] **FACTOR-07／P0** 儲存 features、每因子貢獻、score、排名、排除原因；平手以ticker固定順序。
- [ ] **FACTOR-08／P0** 做一筆手算小例：價格增長／下降／恆定，確認因子方向、觀測數及區間。第 15 批手算首筆 100、後 20 筆 110（動能 10%、均線偏離 0%、年化波動 35.496479%）與固定價格三值 0 通過；專門下降手算尚未補測，維持未勾選。
- [ ] **FACTOR-09／P0** 候選池＝前30＋全部原持股＋最多5分散候選；不得漏掉資料缺失的原持股。
- [x] **FACTOR-10／分析輔助** 依已驗收完整視窗，離線產生三因子原價分析表、共用來源／公式 metadata 與分布閱讀摘要；截止日、期間與百分數單位明確，排除股票沿用既有缺失紀錄。第 15 批 146 檔／6 欄／21 日輸入及 3 項測試通過；不等於正式候選池、回測或模型決策。
- [ ] **EVIDENCE-01／P0** Python 建 sources／observations；S/O連號、authority與市場一致、values只有數值。
- [ ] **EVIDENCE-02／P0** 每個因子數字能對回原始列、區間與程式版本；計算值標明公式，不當作交易所直接公佈的欄位。
- [ ] **EVIDENCE-03／P0** 明確決定歷史 source 分組方式；正式 sources≤50、observations≤100，不能刪必要證據湊數。
- [ ] **EVIDENCE-04／P0** Evidence packet 含 cutoff、rules、account、rankings、原持股、baseline、O/S、allowed_tickers與品質報告。
- [ ] **EVIDENCE-05／P0** 凍結packet與hash；不要讓Agent接資料時自行改清洗結果。

第 15 批完成證據：`src/etf_agent/features.py`、CLI `history-features`、`tests/test_features.py`、[146 檔分析 CSV](data/cache/features/2025-09-30/20261011T160349_3b42fa16/features.csv)、[來源／公式 metadata](data/cache/features/2025-09-30/20261011T160349_3b42fa16/metadata.json)、[閱讀摘要](data/cache/features/2025-09-30/20261011T160349_3b42fa16/analysis.md)。特徵版本 `price-features-v1-c9e2191b62ec`；3 tests、OK（1.505s），CLI exit 0，CSV BOM／146 唯一代號／6 欄與 JSON 一致，2330／5274 另用標準庫獨立公式核對 PASS；同輸入重算與不覆寫、日表改動阻擋已由測試驗收。全套、排名／權重、官方 S/O 引用及正式 FeatureTable／MarketSnapshot 尚未完成，本批不擴張勾選。

第 16 批說明與導覽：[analysis.md](data/cache/features/2025-09-30/20261011T160349_3b42fa16/analysis.md) 及其產生器已補三指標的選用理由、含義、公式與未來用途，數值 CSV／metadata 不變。專屬 [因子分析](docs/factor_analysis.md)、[快速開始](docs/quickstart.md)、[歷史資料](docs/history_data.md)、[日曆／視窗](docs/calendar_windows.md) 說明由精簡 README 的架構／九命令入口連入；原價、正式串接及待實作狀態保持明確。受影響匯出測試 1 test、OK（0.130s），本批入口連結與命令對照通過，未新增測試或重跑全套；排名／風控及正式資格仍未完成。

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
