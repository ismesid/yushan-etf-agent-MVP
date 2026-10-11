# 開發紀錄

更新：2026-10-11。此檔統一保存簡明的討論、決定、授權、驗收與下一步，不保存逐字對話。

## 合作方式與依據

- 目標：約 8 小時完成可開會討論的 ETF MVP，模組保留資料、因子、模型與 UI 的擴充邊界。
- 每批約 10～30 分鐘，先說明與討論，使用者明確同意後實作；每批完成展示結果，再討論下一批。第一批同意不授權後續階段。
- 文件維護：依使用者第 16 批要求，README 作快速理解專案架構、現況與執行的入口；完整參數、輸入輸出、續接與失敗處理連到各功能專屬文件。各批更新 README 的功能狀態與入口，測試流水帳留本檔／checklist，避免持續堆進 README。
- GitHub 導覽：README 與操作文件的倉庫內連結必須指向 Git 已追蹤的檔案或目錄，並核對章節標題；不能只驗本機檔案存在。被忽略的快取成果顯示為明確本機路徑，入口連至可閱讀的說明與重建方式。
- 已讀根目錄 `AGENTS.md` v1.0、`design1001.md` v0.3、`checklist.md`（2026-10-11），首輪已閱讀 F01～F09 九份官方來源，來源內容未修改。
- 官方要求以對應原文為準；策略權重、風控閾值仍待討論。下列 demo 數值與時間切分是專案示例，不能當成官方規則。

## 已討論的決定

| 討論 | 決定與理由 | 狀態 |
|---|---|---|
| 模組如何共用資料 | 六種核心合約集中定義；金額使用 Decimal，股數用整數，HTTP／SDK 不進核心 | 已實作合約 |
| 模型如何參與 | AgentDraft 只提出選股與理由，不接受 shares／orders；最終股數由程式計算 | 已實作合約與 provider 介面，未接模型 |
| 含既有持股的 demo 是什麼 | 模擬帳已持有 25 檔股票，股票市值 9,000 萬＋現金 1,000 萬＝NAV 1 億；可展示續抱與加減碼 | 已建人工測試帳，不是正式期初帳 |
| 帳務與行情如何保存 | 規劃 SQLite 保存帳務／索引，JSON／CSV 保存原始資料、清洗行情、因子與執行產物；方便本機檢查與備份 | 第 02 批已保存歷史樣本；SQLite／完整存檔流程尚未完成 |
| 股市資料如何取得 | TWSE／TPEx 各自的官方月報 adapter 記錄來源、單位、資料日與取得時間；不能把 latest 當成指定歷史日 | 第 10 批已處理 150 檔，2025-09 有行情 147 檔；第 13 批另保存官方排程及價格視窗診斷 |
| 官方股票範圍如何共用 | F05 衍生 CSV 只保存 ticker／name／market，讀取時核對來源與內容；後續模組共用 allowed_tickers | 已接入全股票月報、覆蓋、價格視窗及原價分析，排名／投資流程未實作 |
| 分析如何呈現 | 每個截止日另存六欄因子 CSV、共同日期／公式／來源 JSON 與閱讀摘要；內部比率小數，CSV 用百分數 | 第 15 批已實作歷史原價三因子分析，正式快照／FeatureTable 尚未串接 |
| 未來如何回測 | 保留原價／因子價格、資料日、known_at、fetched_at、hash 與版本；按時間切成 train／validation／test，留出較新測試期 | 已預留格式與切分檢查，未訓練或回測 |
| 討論紀錄如何維護 | 依使用者最新指示只保留本檔，合併原日記必要決定，避免重複維護 | 本次整併 |
| 上市／上櫃表格如何整理 | 原始來源分開，整理後以 market 區分的長表合併，便於因子分組與日期切片 | 第 03 批已同意並完成樣本匯出 |
| CSV 如何顯示單位與來源 | 成交量用張並保留小數，閱讀價格／均價用千元／張、金額用千元；網址與完整 hash 集中在 manifest；內部仍股與元 | 第 06 批 CSV 4.0；核心合約仍 1.0 |

時間切分示例：2020～2023 訓練、2024 驗證、2025～2026-09 測試，標籤與 gap 暫用 5 個交易日。這些不是已取得的歷史資料或已定案的研究期間。真正的交易日 gap、標籤跨界檢查與測試集存取限制尚未實作；21 日因子行情也不足以替代長期回測資料。8 小時 MVP 暫不訓練預測模型。

## 01｜共用合約與離線示例（2026-10-11）

- 授權：標準庫 dataclass／Decimal、六種合約、AgentProvider 介面、含既有持股的 demo、CLI 與必要 unittest。使用者追加回測預留，因此增加 DatasetSplitPlan；本批不安裝依賴、不抓資料、不呼叫投資模型。
- 檔案：`pyproject.toml`、`src/etf_agent/contracts.py`、`src/etf_agent/cli.py`、package 初始化檔、`src/etf_agent/agent/base.py`、`specs/internal/agent_draft.schema.json`、`tests/fixtures/contracts_demo.json`、`tests/test_contracts.py`、`docs/data_contracts.md`、本檔與 checklist。
- 完成六種核心合約：MarketSnapshot、AccountSnapshot、FeatureTable、AgentDraft、PortfolioProposal、ValidationReport；另有 AgentResult／AgentProvider、DatasetSplitPlan。
- demo 例子：2891 有 60,000 股×假價格 50 元＝300 萬；其餘 24 檔各 58,000 股×假價格 62.50 元，合計 8,700 萬；全部股票 9,000 萬。26 列假行情只涵蓋兩個資料日，不是完整歷史行情。

實際驗收：

| 指令／檢查 | 結果 |
|---|---|
| `python -B -m etf_agent.cli --help` | exit code 0 |
| `python -B -m etf_agent.cli contracts-demo --fixture tests/fixtures/contracts_demo.json` | exit code 0；八種合約 JSON 往返 PASS；25 檔持股、25 selections／25 reviews |
| demo 資產核對 | `90000000.00`＋`10000000.00`＝`100000000.00`，PASS |
| `python -B -m unittest discover -s tests -p test_contracts.py -v` | 30 tests，0.542s，OK |
| CLI 缺檔輸入 | exit code 2 與清楚錯誤 |

PowerShell 重跑先設定 `$env:PYTHONPATH = (Resolve-Path 'src').Path`，再執行上表命令。完整說明見 `docs/data_contracts.md`。

fixture 的價量、帳戶、因子與草稿皆為人工測試值；實際模型版本及用量為 null，`submission_ready=false`。內部 schema 僅做 JSON 可讀及結構檢查，未安裝 jsonschema，也未完成官方 F04 結構／語意驗證。

## Git｜建立與改名（2026-10-11）

- 授權：使用者要求建立 GitHub repository 做版本管理，後續要求名稱加上 MVP；這兩批不授權新的 ETF 功能。
- 已初始化 `main`，新增 README、`.gitignore`、`.gitattributes`；金鑰、本機設定、真實帳戶、下載快取、runs／exports、SQLite 與日誌不追蹤。九份官方來源與 Git blob 的 SHA-256 比對全部相同。
- 初建私有倉庫 `ismesid/yushan-etf-agent`，後改名為 [ismesid/yushan-etf-agent-MVP](https://github.com/ismesid/yushan-etf-agent-MVP)。API 核對 repository ID 相同、仍為私有、主要分支仍為 `main`；Python package 名稱沿用 `yushan-etf-agent`。
- 本機 `origin=https://github.com/ismesid/yushan-etf-agent-MVP.git`，`main` 追蹤 `origin/main`。已推送：`d6cd05f`（初始專案）、`7a49f49`（建立倉庫紀錄）、`4c72e04`（改名）。
- 使用既有 Git Credential Manager 與 Python 標準庫，未安裝套件，憑證只在記憶體中使用。經工具批准，Git safe.directory 只新增本專案絕對路徑。
- 實際檢查：忽略規則命中金鑰與本機資料路徑、文字檔金鑰模式無匹配、文件差異檢查通過。功能程式未改，不重跑合約測試。

## 文件整理（2026-10-11）

- 授權：使用者要求只保留開發 note，並解釋已完成與下一步。
- 結果：必要討論與決定已合併至本檔，刪除 `diary.md`，更新 README 與 checklist 的連結、指令示例及紀錄說明；沒有新增 ETF 功能或勾選未完成項目。
- 驗收：`Test-Path diary.md` 為 False；搜尋確認 README／checklist 無日記連結或指令引用；`git diff --check` 通過，差異僅四份文件。本批不重跑先前 30 項程式測試，變更尚未提交或推送。

## 第 01 批後的未完成與提案（歷史紀錄）

- 尚未實作：150 檔可載入白名單、完整行情與交易日曆、全市場清洗、精確且一致的成交量值口徑、因子計算／排名、真實投資模型、配置／風控、股數與費用、D-Plan 編譯及驗證、SQLite 帳務與核對、完整執行版本保存、訓練／回測與 UI。
- 正式流程仍需確認：期初帳／本金、截止時刻與資訊區間、費用取整、公司行動、無成交與現金比例口徑、官方驗證器及完整 AI 資格要求。缺必要規則時正式產物停止，demo 明示限制。
- 回測資料批次還需決定：歷史範圍、獨立測試期、預測標籤與交易日 gap，並確認修正資料的當時可知版本、公司行動及存續偏差。
- 下一批建議約 20～30 分鐘：將 F05 轉成 150 檔 `data/universe.csv`，保存來源／版本，加入載入與檢查；驗收恰好 150 檔、100 TWSE／50 TPEX、無重複，抽查 2330／5274。不安裝套件、不抓外部行情、不呼叫模型。
- 待使用者明確同意下一批後實作；之後再討論歷史資料取得與保存，不自動連續執行。

## 02｜官方歷史下載樣本與功能文件（2026-10-11）

- 授權：使用者明確要求先試自動取得歷史資料、提供可查看 CSV，並擴充 data_contracts 文件解釋、附程式連結及按功能區塊更新。範圍選 2330／5274 各一份 2025-09 已完成月報，不擴大成 150 檔資料集、不安裝套件或呼叫投資模型。
- 修改：新增 `src/etf_agent/history.py`、`providers/__init__.py`／`http.py`／`monthly.py`／`twse.py`／`tpex.py`、`tests/test_history.py`；CLI 增加 `history-sample`。文件擴成各功能的用途、欄位、檢查、待完成及相對程式連結；同步更新 README／checklist／本檔。
- 真實執行：TWSE／TPEx 官方月報均 HTTP 200，各 21 筆，日期為 2025-09-01～2025-09-30；CSV 共 42 列。程式保存原始 JSON、原欄位 CSV、統一格式 CSV、品質報告及 manifest；兩份原始 SHA-256 再核對相同。
- 當時產物：`data/cache/history_sample/2025-09/20261011T122548_f1b87c04/`；此舊目錄後依使用者要求刪除，原始資料及下載紀錄已完整保存在第 03 批新版目錄。可查看連結集中於 `docs/data_contracts.md` 的「本批歷史下載實測」。快取留本機、Git 忽略；程式每次重跑仍新建目錄。
- 關鍵發現：TWSE 月報是股／元、包含一般／零股／盤後定價／鉅額；TPEx 是整數張／仟元且不含鉅額。TPEx ×1000 的 reported 欄位只保留報表換算，核心精確 volume_shares／amount_twd 留空，不能拿來正式結算均價。
- 時間與狀態：取得時間為真實本次時間，歷史 known_at 沒證據就留空；return_close 留空、adjustment_status=unresolved、tradable=false。樣本沒有取代人工帳戶／草稿，不是正式快照、因子或回測結果。
- 環境：首次沙盒連線遭 WinError 10013；工具批准後 urllib 遇 TLS Missing Subject Key Identifier。改用既有 Windows curl／Schannel 成功，保持 HTTPS 憑證驗證，沒有關閉驗證或安裝依賴。每請求 timeout 10 秒，沒有自動重試；HTTP 拒絕或 HTML 記失敗，不繞封鎖。
- 驗收：全部 55 tests（原 30＋新 25）通過，0.883s；涵蓋錯年月／股票、空值、單位／精度、OHLC、衝突、HTML／403、部分下載失敗、重跑證據不覆蓋及 urllib 錯誤頁保留。既有 contracts-demo／CLI help exit 0，無效月份確認 Python exit 2。文件本機連結均存在，git diff --check 通過。
- 重跑（PowerShell，專案根目錄）：先 `$env:PYTHONPATH = (Resolve-Path 'src').Path`，再 `python -B -m etf_agent.cli history-sample --month 2025-09 --output data/cache/history_sample`（兩次官方 HTTPS 請求）；離線測試為 `python -B -m unittest discover -s tests -p 'test_*.py'`。
- 下一步：先討論 F05 150 檔白名單，再處理 TPEx 精確每日量值、交易日曆與更長歷史；不要直接把兩檔月報擴稱全流程完成。此批不提交或推送 GitHub，亦不授權後續階段。

## CSV 結構與單位討論（2026-10-11，後續於第 03 批同意實作）

- 使用者提問：上市／上櫃行情應合併或分開；希望 CSV 不放 source_url，數量用張，並確認最小交易單位。
- 官方確認：F04 的 orders.shares 最少 1000 且為 1000 倍數，F07 公式以股推導，因此本競賽委託是整張。實際上市／上櫃一般股票交易為 1000 股一單位，但另有 1 股一單位的零股制度；參考 [TWSE 說明](https://shl.twse.com.tw/page/library/trade/1.html)、[TPEx 交易制度](https://www.tpex.org.tw/zh-tw/mainboard/trading/rules/system.html)。
- 建議：原始來源分開保存，清洗後以一張長表、market 欄位區分；因子按股票分組，排名／回測依日期取資料。兩市場量值口徑與精度差異仍保留，不因合表而視為相同。
- source_url：CSV 每列 URL 與 manifest 重複，可移除 CSV 欄位；由 market／ticker／raw_sha256 對回 manifest 的來源網址及原始檔。網址證據仍保留。
- 單位提案：讀者 CSV 成交量用張且保留小數；價格仍元／股、金額仍元。內部 PriceBar.volume_shares／Position.shares 建議保留整數股數，官方 D-Plan shares 必須用股。TWSE 23,022,319 股可精確顯示 23,022.319 張；TPEx 報表 356 張仍只有報表精度，不能當成精確股數。
- 當時提案：修改 CSV 輸出與測試、文件／checklist／本紀錄，移除重複網址、改成交張數欄位；從已保存原始 JSON 重新輸出新版本，驗收 42 列、精度／空值／追溯與換算，不連網或安裝，不修改六種核心合約。討論當下未改程式及 CSV；使用者後續同意，完成證據見下一節。

## 03｜CSV 張數顯示與離線重輸出（2026-10-11）

- 授權：使用者同意合併表、移除 CSV source_url、成交量以張顯示但內部計算仍用股，並要求更新開發紀錄及文字說明。此批僅格式與離線重輸出，不抓新行情、不安裝套件、不呼叫模型或開始白名單批次。
- 修改：`history.py` 的 CSV 寫出改用 Decimal／1000，`volume_shares`／`reported_volume_shares` 在 CSV 改為 `volume_lots`／`reported_volume_lots`；新增 `export_history_sample()` 與 CLI `history-export`；更新 `tests/test_history.py`、README、功能說明、設計 §6.1、checklist 與本紀錄。六種核心合約、官方 schema 及原始來源未修改。
- 決定：CSV 顯示版本為 2.0；核心合約與 manifest 結構版本仍 1.0。股數不取整，價格元／股、金額元，缺值不補零；TPEx 精確成交量／金額仍空，報表量保留原揭示精度。網址由 CSV 的 market／ticker／raw_sha256 對回 manifest。
- 真實產物：以第 02 批保存的官方 JSON 完全離線重輸出，新目錄 `data/cache/history_sample/2025-09/20261011T125021_603f0054/`，仍為 42 列。舊 `20261011T122548_f1b87c04` 不覆寫；新 run 的原始 JSON／原欄位 CSV 與舊 run 逐位元相同。
- 可讀例子：2025-09-01，2330 的 23,022,319 股顯示為精確 23,022.319 張；5274 的 volume_lots 留空、reported_volume_lots=356、exact_volume_amount=false。這些是已下載的真實歷史月報，沒有更新人工測試帳戶或草稿。
- 追溯：新 manifest 記錄 csv_format_version=2.0、csv_units、purpose=offline_cached_export、network_requests=0，以及 reexport_of 的原 manifest 路徑／SHA-256／run_id。fetched_at 保留原下載時刻，created_at／reexported_at 記此次匯出時刻；先驗原始 hash、來源身分及格式，再建立新目錄。
- 實際驗收：全部 59 tests（30 合約＋29 歷史）通過，0.987s；新增 4 項離線匯出測試覆蓋舊 CSV 相容、零 HTTP、舊版不覆寫、雜湊／欄位錯誤阻擋。CLI 離線匯出及原 contracts-demo exit 0。逐列確認 42 列價格、金額、來源 hash、原下載時間不變，張數乘 1000 可精確回復；新版 CSV 無 source_url 或股數欄。文件連結及 git diff --check 通過。
- 重跑：專案根目錄先設定 `$env:PYTHONPATH = (Resolve-Path 'src').Path`；執行 `python -B -m etf_agent.cli history-export --manifest data/cache/history_sample/2025-09/20261011T125021_603f0054/manifest.json --output data/cache/history_sample`。重跑會另建一份匯出目錄；測試為 `python -B -m unittest discover -s tests -p 'test_*.py'`。
- 限制與下一步：樣本仍缺 TPEx 精確量值口徑、交易日曆、公司行動與歷史 known_at，不能正式結算或宣稱完整回測。下一批可討論 F05 白名單；此批未提交或推送 GitHub，不授權後續階段。

## 舊樣本清理（2026-10-11）

- 授權：使用者要求指出新版位置並直接刪除舊版；僅清理第 02 批樣本目錄及同步文字說明，不開始下一批功能。
- 結果：已刪除 `data/cache/history_sample/2025-09/20261011T122548_f1b87c04/`；目前查看 `data/cache/history_sample/2025-09/20261011T125021_603f0054/prices.csv`。
- 保存證據：刪除前逐位元核對新版兩份 raw JSON／原欄位 CSV 與舊版相同，來源 hash 及 fetched_at 相同；原 manifest 原文保存為新版 `provenance/original_manifest.json`，SHA-256 與 reexport_of 記錄相符。新版 manifest 增列 archived_manifest_path；原路徑與 run_id 僅作歷史識別，離線重輸出使用新版自己的 raw。
- 驗收：新版仍為 42 列、CSV 2.0、成交量用張、無 source_url／volume_shares；舊目錄不存在。同步更新 README／功能文件的查看連結及重跑指令、checklist 的現存證據位置。此項僅本機清理，沒有連網、模型呼叫、安裝或重跑專案測試。

## 04｜閱讀 CSV 千元／張與當日均價（2026-10-11）

- 授權：使用者要求逐欄解讀 CSV、解釋 return_close／known_at、移除對分析無用的 raw_sha256、價格改千元單位且數量用張、增加均價，並允許刪除原 CSV 重新整理。價格基準經提問確認採「每張價格，單位千元」，成交金額也統一千元；此批只修改匯出、文件與必要測試，不開始其他功能。
- 決定：閱讀格式升 CSV 3.0。價格欄明示 `_ktwd_per_lot`；1165 元／股＝1165 千元／張，所以價格數字不變。金額欄改 `amount_ktwd`／`reported_amount_ktwd`，原元值除 1000；成交量維持張並保留零股形成的小數。核心 PriceBar、持股與官方 D-Plan 仍依既有元／股、股數合約。
- 欄位用途：return_close 是報酬計算用價格，不是報酬率或成交均價；尚未核實公司行動所以留空。known_at 是有證據可確認公開可知的時刻，用來防回測資訊洩漏，未知留空；fetched_at 保留原下載時刻。
- 來源追溯：CSV 移除 raw_sha256；manifest／核心合約與離線防竄改驗證保留完整 hash。manifest 每份來源補 data_version，同批 CSV 依 market＋ticker＋data_version 找回來源；短版本碼不單獨作跨批唯一身分。
- 均價：依 F07 以成交金額÷成交股數推導，閱讀等價公式為千元金額÷成交張數。`avg_price_ktwd_per_lot` 用精確量值；`reported_avg_price_ktwd_per_lot` 用報表量值，TPEx 僅估算、精確均價仍空。缺量值或零成交量時均價空，不用 OHLC 平均替代；Decimal 獨立精度 50，均價閱讀顯示 8 位小數、ROUND_HALF_UP，這不是官方結算取整規則。T 日均價收盤後才取得，不進 T 盤前因子；正式結算須用確認口徑的原始量值重算。
- 修改：`src/etf_agent/history.py`、`src/etf_agent/cli.py`、`tests/test_history.py`、README、功能文件、設計 §6.1、checklist 與本檔。原路徑 `data/cache/history_sample/2025-09/20261011T125021_603f0054/` 三份閱讀 CSV 就地替換，沒有另外留下舊閱讀 CSV 或新樣本目錄。
- 保存與實測：新版仍 42 列；兩份 raw JSON、兩份原欄位 CSV、原下載 manifest 共 5 檔 hash 不變。CSV 2.0 manifest 原文另存 `provenance/csv_v2_manifest.json`；更新 manifest 標記 CSV 3.0、csv_rebuilt_at、csv_rebuild_of、purpose=offline_cached_csv_rebuild、network_requests=0，原 run_id／created_at 不變。
- 真實歷史例子（2025-09-01）：2330 收盤 1165.00 千元／張、成交 23022.319 張、金額 26647241.918 千元、精確量值推算均價 1157.45255367 千元／張；5274 收盤 5015.00，報表成交 356 張／1785269 千元、估算均價 5014.80056180，精確量值／均價留空。未修改人工 demo 帳戶或草稿。
- 驗收：33 項歷史離線測試通過（0.369s），30 項核心合約測試通過（0.525s），共 63 項。新增必要行為涵蓋千元／張估值、均價來自量值且區分報表精度、零量／缺值、8 位 HALF_UP 邊界、外部 Decimal 精度不影響匯出且核心列不變。另逐列確認 42 列身分／價格／時間／版本不變，金額乘 1000 可回復、均價符合公式；重建後 CLI `history-export` 讀新版 manifest 成功，輸出於已清理的暫存目錄，mock 確認零 HTTP。三份閱讀 CSV 欄位相同、24 欄均有文件解釋，59 個本機連結與 git diff --check 通過。
- 自行檢查：專案根目錄先 `$env:PYTHONPATH = (Resolve-Path 'src').Path`，執行 `python -B -m unittest discover -s tests -p 'test_*.py'`。離線另產一份 CSV 可執行 `python -B -m etf_agent.cli history-export --manifest data/cache/history_sample/2025-09/20261011T125021_603f0054/manifest.json --output data/cache/history_sample`；一般指令仍另建版本目錄，此次就地替換依使用者明確要求執行。
- 限制及下一步：TPEx 精確成交量值、兩市場成交口徑、歷史 known_at／公司行動仍待處理；有均價欄不代表能正式結算或回測。本批沒有抓新資料、安裝套件、呼叫投資模型或推送 GitHub；下一批仍先討論 F05 白名單，等待新的批次授權。

## 05｜來源表按月整理與每日資料討論（2026-10-11）

- 授權：使用者明確要求 source_csv 按月份放資料夾、避免與整理後 CSV 同名；同時詢問因子資料入口、每日全股票表、盤前可用日期及截圖中的來源單位。本批實作僅來源檔整理與同範圍程式／測試／文件同步，其餘先討論。
- 修改與產物：`history.py`、`tests/test_history.py`、README、功能文件、設計 §6.1、checklist 與本檔。原 run 兩份來源表改為 `source_csv/2025-09/TWSE_2330_2025-09_source.csv`／`TPEX_5274_2025-09_source.csv`；manifest.sources 路徑同步，整理前 manifest 保存 `provenance/source_layout_manifest.json`，另記 source_csv_reorganized_at 與來源 archive/hash。CSV 3.0 欄位及三份閱讀 CSV 不變，原表仍維持官方字串／單位。
- 驗收：移動前後兩份來源檔 SHA-256 完全相同、舊同名檔已移除。34 項歷史離線測試通過（0.625s），新增來源按月／不同名稱與原始欄位保留測試；離線匯出測試亦刻意改壞來源 CSV，確認程式仍只讀 raw JSON 重建、零 HTTP。另以現存新版 manifest 實測離線重輸出，42 列、兩份來源 CSV 內容相同，暫存輸出已清理；來源 hash、存檔 manifest hash、63 個本機連結與 git diff --check 通過。核心合約不變，沿用第 04 批 30 項通過證據，總測試數 64；本批未重跑核心合約測試。
- 資料入口討論：P0 因子主要讀歷史價量，還需 F05 白名單、交易日曆、公司行動與大盤；策略另讀完整帳戶，法人／營收因子才增加其資料表。模型接收 FeatureTable／排名及證據，預測訓練另需標籤與時序切分，目前均未實作。
- 路徑提議（尚未同意／實作）：`monthly/2025-09/TWSE_2330_2025-09.csv` 為每股月表，`daily/2025-09/2025-09-01_prices.csv` 為每日全股票表；從同一清洗結果產生兩種視圖、日表作核心入口，不把日／月表同時合併。現有樣本只能產生 21 個交易日日表、每天 2 檔，不能冒稱 150 檔完整資料。真實每日增補另列批次。
- 時間提議（尚未同意／實作）：known_at 保留有證據的公開時刻，不改成隔天；可另設 usable_from_trade_date 表示「今日資料下一交易日使用」的自訂保守政策，依日曆／決策截止／延遲公告推導。日曆與歷史公開時間目前未核實，不能固定加一天或靠政策日期讓正式驗證通過。
- 單位說明：截圖股／元與張／仟元是 source_volume_unit／source_amount_unit 的原報表描述，數值欄已轉張／千元。建議下一版閱讀 CSV 移除這兩個原單位欄、仍留 manifest 與精度旗標；目前尚未改 CSV 欄位。
- 自行重跑：先 `$env:PYTHONPATH = (Resolve-Path 'src').Path`，再 `python -B -m unittest discover -s tests -p test_history.py`；既有 `history-export --manifest data/cache/history_sample/2025-09/20261011T125021_603f0054/manifest.json --output data/cache/history_sample` 仍完全離線、另建匯出目錄。
- 下一批建議約 20～30 分鐘：先確認日／月清洗視圖及閱讀欄位，再從既有 42 列重排並驗收總筆數／唯一鍵／零 HTTP／欄位單位一致；不連網、不新增資料源、不自行填 known_at 或使用日期。暫未執行此提議，也未安裝、呼叫模型或推送 GitHub。

## 06｜每日全股票表與每股月表（2026-10-11）

- 授權：使用者對上一批明列的「每日／每股月結構＋移除閱讀 CSV 兩個原單位欄」回覆「可以」。此批用已保存的 42 列重排、必要驗證與文件紀錄；不新增資料源、日曆、known_at／usable_from 計算、因子、模型或帳務。
- 修改：`src/etf_agent/history.py`、`src/etf_agent/cli.py`、`tests/test_history.py`、README、功能文件、設計 §6.1／§14.2、checklist 與本檔。CSV 升為 4.0、22 欄，移除 source_volume_unit／source_amount_unit，來源單位仍在 manifest.sources[].units；量、金額、價格、8 位閱讀均價及精度旗標維持。
- 輸出：原 run 的 `monthly/2025-09/TWSE_2330_2025-09.csv`／`TPEX_5274_2025-09.csv` 各 21 列；`daily/2025-09/2025-09-01_prices.csv` 等共 21 個日檔、每檔 2 列。兩種視圖由同一清洗列生成，日表為規劃的核心資料入口、月表供查閱；尚未建立因子 reader，不能將兩種視圖同時合併而重複計算。
- 索引與相容：manifest 結構格式仍 1.0、CSV 4.0；頂層移除舊 prices_csv 月合表索引，改 daily_prices（日期／路徑／列數），每份來源的 prices_csv 指 monthly 路徑。回傳結果及 CLI 改顯示日／月目錄、日檔數與首日檔；舊 manifest 可由 raw JSON 完全離線重輸出，不依賴舊清洗 CSV。
- 保存與清理：先產生暫存視圖並驗收，再寫入原 run 的 daily／monthly，最後刪除根目錄 prices.csv／TWSE_2330_2025-09.csv／TPEX_5274_2025-09.csv。保留原 run_id／created_at，manifest 記 purpose=offline_cached_price_view_rebuild、price_views_rebuilt_at、price_views_rebuild_of；整理前 manifest 原文與 hash 保存在 provenance/daily_monthly_manifest.json。raw／source_csv／既有 provenance 共 7 檔 hash 不變，暫存輸出已清理。
- 真實歷史例子：2025-09-01 日檔有 2330、5274。2330 收盤 1165 千元／張、成交 23022.319 張、金額 26647241.918 千元、均價 1157.45255367；5274 精確量值／均價空，報表 356 張／1785269 千元、估算均價 5014.80056180。與整理前數值相同，沒有新下載或改 demo 帳戶。
- 實際驗收：36 項歷史離線測試通過（0.909s），新增日／月相等、日期排序／唯一性與缺日缺股不補造行為；原精度、缺值、量值、hash、403、部分失敗及 legacy raw-only 重輸出仍通過。另核對日／月兩視圖均等於原 42 列去掉兩個單位欄、所有值保持、42 個唯一鍵；新版 manifest CLI 離線重輸出 exit 0、mock 確認零 HTTP。23 份閱讀 CSV 與文件 22 欄一致，65 個本機連結、來源／歷史 manifest hash 及 git diff --check 通過。核心合約未變，沿用第 04 批 30 項通過證據，總數 66；不重跑無關測試。
- 自行重跑：先 `$env:PYTHONPATH = (Resolve-Path 'src').Path`，執行 `python -B -m unittest discover -s tests -p test_history.py`。另外產生日／月視圖可用 `python -B -m etf_agent.cli history-export --manifest data/cache/history_sample/2025-09/20261011T125021_603f0054/manifest.json --output data/cache/history_sample`，會建立另一版本目錄，不連網。
- 限制與下一步：此批只重排兩檔一個月歷史樣本，未完成 150 檔覆蓋、每日最新行情增補、日曆／公司行動、正式公開時間或因子計算。下一批建議先載入 F05 白名單，再討論真實每日行情及因子歷史視窗；本批不安裝、呼叫投資模型或推送 GitHub，完成後等待下一批共識。

## 07｜上櫃空值、報表精度與 README 導覽（2026-10-11）

- 授權：使用者要求解釋上櫃前三個量值欄為空、reported 三欄差別、評估 exact_volume_amount，並將說明補進資料合約文件；README 精簡清洗細節，保留導向資料說明的連結。
- 決定：本批保留 CSV／manifest 的精度旗標及兩組量值欄。旗標不直接參與價格因子打分，但成交金額流動性篩選、均價成交模擬、回測與帳務需要判斷精度；false 不等於排除上櫃。現有程式尚無真實因子／策略／正式驗證器使用旗標，不把未實作用途說成既有功能。
- 解釋：目前 TPEx 月報只提供整數張／仟元，本專案保守政策將不能核實的精確量值／均價留空；reported 保存同一份報表、同一天的揭示值，空不表示零成交或轉換失敗。TWSE 提供股／元，所以兩組數字相同。未知取整規則與交易範圍仍需確認，不因換算或均價顯示小數而宣稱變精確。
- 真實歷史例子：5274 的 2025-09-01 原表為 356 張／1785269 仟元，閱讀表 reported 保留 356 張／1785269 千元，估算均價 5014.80056180 千元／張；前面三個精確欄仍空。原始來源與解析／匯出邏輯已唯讀對照。
- 修改：`docs/data_contracts.md` 升文件 1.7，新增上櫃空值／兩組欄位對照、精度旗標對各用途的影響、原始政策與官方規則界線及程式連結；README 保留概況、執行與樣本導覽，詳細欄位／清洗集中導向資料說明。同步更新 checklist 與本檔。程式、CSV 4.0／22 欄、原始資料與 manifest 未變更。
- 驗收：63 個本機文件連結及 `git diff --check` 通過；5274 實例與原來源 CSV／整理後日表及量值比一致，22 欄均有文件解讀，README 已導向資料文件且移除欄位／清洗細節。本批僅文件修改，未重跑專案測試或新增測試。此前 36 項歷史測試及 30 項核心合約的通過證據保留，沒有宣稱本次重跑。
- 後續：reported 是否允許進成交量／金額因子與門檻判斷，須於因子批次討論；正式結算仍需精確資料及符合用途的成交範圍。下一個功能批次仍待使用者同意，未連網、安裝、呼叫投資模型或推送 GitHub。

## Git｜歷史資料與文件版本提交（2026-10-11）

- 授權：使用者要求「先 commit push 後，說明下一步」。範圍為第 02～07 批累積、已驗收的程式與文件，以及已同意的 diary 刪除；此指令不授權下一個功能批次。
- 提交範圍：歷史 TWSE／TPEx adapter、HTTPS／快取重輸出、CSV 4.0 每日／個股月視圖、CLI、歷史測試、README／資料說明／設計／checklist／開發紀錄，以及 diary 刪除。官方來源、核心合約與依賴設定保持原樣。
- 保存位置：本機 `main`，目標遠端 `origin/main`、私有 `ismesid/yushan-etf-agent-MVP`。真實行情快取、帳戶、runs／exports 仍由 Git 忽略；提交只包含已核對的程式與文字檔案。
- 本次驗收：`python -B -m unittest discover -s tests -p 'test_*.py'` 全 66 項通過（1.242s）；既有 contracts-demo exit 0、NAV／JSON 往返 PASS、fixture 狀態及 submission_ready=false 正確。`git diff --check` 通過，沒有官方來源／核心合約／依賴設定差異；快取忽略規則及提交候選敏感內容已檢查。
- Git 操作：本批提交並以一般 `git push origin main` 推送；執行結果、commit ID 與遠端同步確認於本次開發回覆提供，不使用強制推送。
- 下一批提案：約 20～30 分鐘，從 F05 產生 `data/universe.csv`（ticker／name／market）與來源版本紀錄，新增 `src/etf_agent/universe.py` 載入／檢查及必要測試，CLI 展示白名單。驗收 150 檔、100 TWSE／50 TPEX、無重複、來源 hash 可核查並抽查 2330／5274；不抓外部行情、不安裝套件、不呼叫模型。這項功能尚未實作，仍待新的批次同意。

## 08｜官方股票白名單（2026-10-11）

- 授權：使用者對上一輪 20～30 分鐘的 F05 白名單提案回覆「好，請執行」。範圍為衍生名單、來源版本、載入／檢查、CLI、必要測試與文字紀錄；此批完全離線。
- 來源與決定：唯讀解碼 F05 全三頁，核對頁 1 上市 60、頁 2 上市 40＋上櫃 16、頁 3 上櫃 34。代號維持四位字串，名稱依官方文字；合併 `-KY` 等文字區塊及 3718 的「中光電投控」，不以目前公司名取代來源。沒有產業／主題來源，因此採已同意的三欄，不填設計草案中的 industry／theme_tag。
- 產物：`data/universe.csv` 150 檔、ticker 排序、UTF-8／LF；`data/universe.manifest.json` 保存 PDF 與 CSV SHA-256、頁碼索引、生成時間及版本 `F05-v1-c12c57571f22`。F05 未提供已確認適用起始日，effective_from_trade_date 留空；不能把這份競賽名單當成歷史各日股票池。
- 程式：新增 `src/etf_agent/universe.py` 的 `Stock`／`Universe`／`load_universe()`，驗三欄、ASCII 代號、名稱、市場、重複、150／100／50、檔案與 manifest 版本。`allowed_tickers`、`lookup()`、`select_market()` 可供後續模組共用；CLI 新增 `universe-check` 及 JSON 摘要，成功 exit 0、失敗 exit 2。
- 修改與界線：新增上述資料／模組及 `tests/test_universe.py`；修改 CLI、README、資料說明（1.8）、checklist 與本檔。官方來源、六種核心合約、依賴設定、既有歷史 CSV／manifest 與人工 demo 未改；history-sample 仍兩檔，contracts-demo 仍使用 fixture 候選池。
- 實際驗收：全套 91 tests、OK（1.517s），其中本批 25 項覆蓋檔數／查詢、跨市場重複、錯格式、缺檔、CSV／來源 hash、版本與 CLI 成功／失敗。CLI universe-check、help 及既有 contracts-demo 均 exit 0；原人工帳 NAV 核對仍 PASS、submission_ready=false。生成 CSV 的完整 hash 與獨立唯讀抽取結果一致；九份官方來源逐位元核對 Git 版本不變，73 個本機文件連結有效，`git diff --check` 通過。
- 抽取環境：本機沒有 PDF 第三方套件，採 Python 標準庫讀取既有 PDF。首次透過 PowerShell 管線送入含中文的抽取碼時編碼失敗，改用直接命令參數後成功；未安裝工具或呼叫外部服務。
- 重跑：專案根目錄先 `$env:PYTHONPATH = (Resolve-Path 'src').Path`，再 `python -B -m etf_agent.cli universe-check --universe data/universe.csv`；加 `--json` 得摘要。測試用 `python -B -m unittest discover -s tests -p 'test_*.py'`。
- 限制與下一步提案：行情仍只有兩檔，未完成 150 檔覆蓋、日曆／公司行動、資料截止、因子與正式交易驗證。下一批可先將每日 CSV 接上白名單，產生覆蓋／缺件報告，例如樣本 2／150、其餘 148 檔缺行情；實作仍待新批次共識。本批沒有安裝、連網、投資模型呼叫或 Git 提交／推送。

## 09｜接續覆蓋檢查驗收與紀錄收尾（2026-10-11）

- 授權：新會話先依使用者要求唯讀盤點，提出約 20～30 分鐘的覆蓋檢查離線驗收與收尾；使用者回覆「好」，並詢問完整 150 檔日／月資料。本批沿用既有程式、執行必要測試與 CLI、另存報告及同步文件；150 檔新下載另列批次，沒有以本批同意擴張授權。
- 中斷核對：先前工作目錄已存在 coverage.py、28 項對應測試與 prices-check 接線，README／資料說明也已介紹功能；另有 20261011T143543_bb32db7e 報告，但 notes／checklist 只記至 08 批。此次保留它們、接續驗收，不補造上次授權或測試成功紀錄，不重建白名單／覆蓋模組。
- 實際修改：README、docs/data_contracts.md（文件 1.10）、checklist 與本檔，補齊覆蓋實測與用途界線；程式、測試、官方來源、白名單、CSV 4.0／22 欄及歷史下載 manifest 保持原樣。
- 本次測試：`python -B -m unittest discover -s tests -p 'test_*.py'` 實際為 119 tests、OK（1.736s）：30 合約、36 歷史、25 白名單、28 覆蓋。覆蓋測試包含同日重複全組排除、錯日期／市場／名單外、格式與數值、缺價格、版本保存、部分覆蓋 exit 0 與列錯誤診斷 exit 2。
- 真實歷史輸入／輸出：2025-09-01 日表的 prices-check exit 0；新報告位於 `data/cache/coverage/2025-09-01/20261011T144802_4463a889/`，含 coverage.json／coverage.md／missing_stocks.csv。結果 2／150（1.3333%）、缺 148（TWSE 99／TPEX 49）、有效價格 2、原列 tradable=true 為 0、errors=[]、四類 warnings、submission_ready=false。沒有使用或修改帳戶，也沒有真實投資模型決策。
- 產物核對：缺件 CSV 恰 148 個唯一代號，與白名單扣除 2330／5274 的差集一致；輸入與白名單 hash 相符，新舊報告除 created_at／run_id 外全部欄位一致。另以禁止 HTTP 與外部程序的方式核對 21 個真實歷史日表、42 列，均為相同 2／150 覆蓋，零網路呼叫。
- 保存及文件檢查：歷史樣本、舊覆蓋報告、九份官方來源及白名單共 47 檔，操作前後 SHA-256 全部相同；85 個本機文件連結有效，`git diff --check` 通過。
- 執行說明：一次以 PowerShell 單引號傳 Python `-c` 參數的 hash 盤點因引號解析失敗，改以標準輸入送入相同唯讀碼後成功；沒有修改資料或安裝工具。
- 重跑：先 `$env:PYTHONPATH = (Resolve-Path 'src').Path`；測試執行上述 unittest 指令，或只跑 `python -B -m unittest discover -s tests -p test_coverage.py`。展示用 `python -B -m etf_agent.cli prices-check --prices data/cache/history_sample/2025-09/20261011T125021_603f0054/daily/2025-09/2025-09-01_prices.csv --date 2025-09-01 --output data/cache/coverage`，每次另建報告目錄。
- 限制：覆蓋率及有效價格數不能當正式可選股數；行情 raw／公開時間、日曆／公司行動、21 日因子視窗、歷史股票池及帳戶尚未完整核實。DATA-16 等完整品質／正式條件維持未勾選。本批沒有安裝、連網、投資模型呼叫或 Git 提交／推送。
- 下一批需求已討論：使用者選擇先完成 150 檔的 2025-09 資料，CSV 即可，沿用目前每日全股票表及每股月表。月表仍是該股每日行情的整月集合，不是月 K 線。完整下載的來源、請求範圍、失敗處理、修改及驗收會另行提案，待該批明確同意後執行。

## 10｜F05 全股票 2025-09 日／月 CSV（2026-10-11）

- 授權：使用者先選擇 2025-09、一個月、CSV 沿用目前格式；在說明 150 檔官方月報、最多 150 次單線 HTTPS、優先快取、修改及驗收方式後，回覆「好」。本批涵蓋下載／快取、日／月輸出、逐股及逐日缺件、必要測試與文件；沒有擴大成其他月份、模型、帳務、依賴安裝或 Git 提交／推送。
- 方法與程式：`history.py` 把共用產生器整理為 `_export_month()`，原兩股 sample／export 入口保持；新增 `download_history_universe()` 與原始快取核對，CLI 新增 `history-universe`。150 檔依 ticker 排序、每份來源 H1～H150；共用既有 TWSE／TPEx adapter，不改核心合約或來源文件。每兩個實際 HTTP 請求至少間隔 1 秒、10 秒 timeout、沒有自動重試，維持 TLS 驗證。
- 快取與寫入：下載前先驗全部成功 raw 的 hash、月份／股票、市場、請求網址、HTTPS 原主機、內容類型及 +08:00 fetched_at，再重新解析；壞快取於新 run 建立前阻擋，不用連網補抓掩蓋。新 run 複製原始 bytes、保留原取得時間與 data_version，來源 key 依新批重編。每股後以同目錄暫存檔原子更新進度 manifest，串流中斷可由成功 raw 續接；單股 CSV 寫入失敗清除該新 run 的不完整月表／來源表，保留 raw。
- 實際資料：`data/cache/history_universe/2025-09/20261011T145716_6e56c903/`，147 檔有月報、21 個日檔、147 個股月檔及來源 CSV，共 3,075 列。150 份來源皆有 status 與原始回應；HTTP 148 次、快取命中 2 次（2330／5274）。raw、source_csv、monthly、daily、manifest、data_quality 與 coverage 分開保存，新資料由 Git 忽略；原樣本不覆寫。
- 缺件：3718／7828 的 TPEx 回傳空月；7769 的 TWSE 回覆「很抱歉，沒有符合條件的資料!」。本批只能確認端點未提供該月行情，不推定掛牌日期或自行改市場／代號。7750 月報自 2025-09-17 至 09-30 共 9 筆；另外 146 個成功月報各 21 筆。前 12 個日表 146／150，缺 3718／7750／7769／7828；後 9 個日表 147／150，缺 3718／7769／7828。缺件原因及每一天的代號清單保存在 coverage.json，沒有造空行情或補 0。
- 可讀例子：2025-09-01 日表有 146 檔；2330 收盤 1165 千元／張、成交 23022.319 張、金額 26647241.918 千元、均價 1157.45255367，與原快取相同。7750 在 2025-09-17 的收盤 919 千元／張，只從來源回傳的首日開始出現。全部均為真實歷史行情；沒有使用或修改帳戶、因子或投資模型草稿。
- 實際驗收：全套 132 tests、OK（13.821s）：30 合約、36 歷史、25 白名單、28 覆蓋、13 全股票下載。新測試覆蓋 150 source／日月一致、2 cache→148 requests、快取污染阻擋、403／HTML／錯股／下載錯誤、缺日期、限速與進度、非法月份／間隔、0 HTTP 完整快取重播、重跑不覆寫，以及來源 CSV／JSON 寫入故障。首輪 129 tests 有 1 項間隔測試用 0.25 秒，與至少 1 秒政策不符；改為 1.25 秒並增非法間隔測試後，130 項通過，再補兩項 I/O 故障測試形成上述 132 項。
- 真實產物核對：150 raw SHA-256 全部符合 manifest；147 原來源 CSV 與 raw 原欄／原列一致。日／月全部 22 欄，3,075 個唯一日期×股票，逐欄內容完全相等；H1～H150 引用市場／代號／版本一致。每日 input_valid=true、errors=[]，覆蓋與缺件集合符合實際 CSV；2 cache 的原始 bytes、fetched_at、hash、版本及 URL 不變。另有獨立唯讀核對得到相同結果。
- 保存及文件核對：操作前後比對舊樣本、既有覆蓋報告、九份官方來源及白名單，共 50 檔 SHA-256 全部相同；108 個本機文件連結有效，`git diff --check` 通過。沒有刪除舊資料或提交 Git。
- 執行與連線：沙盒 curl 探測無法連線，按工具權限流程重跑沙盒外後 HTTP 200；150 股下載命令亦經工具批准在沙盒外連線。下載本身 148 次 HTTPS；另有 1 次成功的 TWSE 1101 連線探測，總 149 次成功送出的官方查詢，未安裝或呼叫模型。完整下載有資料缺件，外層工具回報 exit 1；CLI 以資料失敗狀態結束，未當作完整通過。錯月份命令另實測原生 exit 2，未建輸出目錄。
- 實際修改：`src/etf_agent/history.py`、`src/etf_agent/cli.py`、新增 `tests/test_history_universe.py`，以及 README、docs/data_contracts.md（1.11）、checklist 與本檔。九份官方來源、白名單、六種核心合約、依賴、CSV 4.0／22 欄及原樣本保持。
- 重跑：專案根目錄先 `$env:PYTHONPATH = (Resolve-Path 'src').Path`。本次下載命令為 `python -B -m etf_agent.cli history-universe --month 2025-09 --universe data/universe.csv --cache-manifest data/cache/history_sample/2025-09/20261011T125021_603f0054/manifest.json --output data/cache/history_universe --transport curl`。若改用本批 manifest 作 cache，會重用 147 個成功來源，仍對 3 個 failed 來源發出新請求；不是完全離線命令。全套測試沿用 unittest discover，單批可用 `python -B -m unittest discover -s tests -p test_history_universe.py`。
- 限制與下一步：已完成全白名單下載功能、日／月 CSV 與缺件核對，但該月未完整覆蓋 150 檔；交易日曆、公司行動、歷史公開時刻、精確 TPEx 量值與歷史時點股票池仍待核實，coverage_complete／submission_ready=false。後續可先討論資料缺件／可用期間及日曆／公司行動，再建立因子讀取與視窗；本批結束後等待下一批共識。

## 11｜無行情原因核實與舊樣本快取清理（2026-10-11）

- 授權：使用者直接要求確認 3718／7769／7828 整月沒有資料的原因，並指示 `history_sample` 若後續不用就刪除。本批限於官方來源查核、重複資料／依賴盤點、保存必要紀錄後清理快取、相關文件及必要離線驗證。前一輪提出的官方交易日曆與 21 筆價格視窗功能尚未取得實作同意，沒有開始。
- 官方核實：3718 上櫃日期 2026-09-03、7828 上櫃日期 2026-04-22，直接讀取櫃買中心 `mopsfin_t187ap03_O` 的 `DateOfListing`（本次資料日期 `1151010`）；7769 的 TWSE「股票上市買賣日期」為 2025-11-27。7828 的興櫃公告另確認開始日 2025-05-08，故 2025-09 當時屬興櫃，不能宣稱所有市場均無行情。日期與月份比較解釋現有空月報，不把空值當零成交；來源、欄位與限制見 [核實報告](docs/history_availability_2025-09.md)。同一份 TWSE 資料所列 7750 上市日 2025-09-17，也與現有九列起始日相符。
- 來源方式：透過網頁工具查閱官方基本資料、掛牌表與公告；新增的是有官方連結的核實摘要，不宣稱已保存本次網頁原始 HTTP bytes／雜湊。原三份空行情回應、150 檔 F05 及全股票 manifest／coverage 原文均保留；沒有加入興櫃資料源、代號銜接或自動略過規則。
- 清理前核對：唯一舊樣本 run 共 33 檔／68,275 bytes。2330／5274 的 raw、來源 CSV 已在全股票 run 逐位元保存，原 fetched_at、SHA-256、版本與網址一致；兩份月表 42 列只改 source_key 為 H24／H108，其餘值相同。現有測試自行建立 fixture／暫存資料，不依賴本機舊樣本。
- 實際清理：刪除 `data/cache/history_sample/`。後續分析使用 `data/cache/history_universe/2025-09/20261011T145716_6e56c903/`。刪除前已保存七份必要紀錄：全股票 run 根層 `sample_manifest.json`；`provenance/history_sample/` 下的 data_quality、四份舊 manifest，以及 `input/2025-09-01_prices.csv`。完整索引與 hash 在同處 `cleanup.json`；兩份舊 coverage 報告引用的首日兩列 CSV SHA-256 均與保存輸入一致。舊報告保留當時的路徑／2／150 結果，不改成全股票日表。
- 程式界線：保留 `history-sample`／`history-export` 小量下載與匯出功能及測試；本批沒有更動程式、CLI 預設、CSV 4.0／核心合約或資料版本字串。保存的根層 sample manifest 原文可直接復用完整 run 的兩份 raw，仍支援離線重建，不需另留重複行情目錄。
- 實際驗收：刪後全套 132 tests、OK（13.556s）。以禁止 HTTP 的方式從保存 manifest 離線重建兩檔 42 列／21 日檔，network_requests=0，首日日表逐位元等同保存輸入；保存輸入重跑覆蓋為 2／150、缺 148、submission_ready=false。暫存驗證輸出已清理，沒有重建 `history_sample`。
- 保存檢查：全股票原有 468 檔的路徑／SHA-256 摘要清理前後一致；九份官方來源及兩份白名單資料共 11 檔亦一致，七份保存紀錄逐檔 hash 核對通過。一次性腳本遇到 Windows 缺時區資料庫與日檔索引欄位誤讀，分別改用既有 +08:00 表示及正確 prices_csv 欄位後完成；未安裝依賴。
- 文件：新增核實報告，README／資料說明／checklist 改用現存全股票入口及保存證據；舊 notes 中的樣本路徑屬歷史紀錄，從本批起使用新入口。本批沒有投資模型、帳戶／交易、Git 提交或推送。
- 重跑：先 `$env:PYTHONPATH = (Resolve-Path 'src').Path`，測試為 `python -B -m unittest discover -s tests -p 'test_*.py'`。離線重建指令為 `python -B -m etf_agent.cli history-export --manifest data/cache/history_universe/2025-09/20261011T145716_6e56c903/sample_manifest.json --output data/cache/history_export`，另建新版本；舊 2／150 覆蓋重跑改讀保存 input CSV。日常分析及 prices-check 請讀完整 run 的 daily，不合併每日與月表。
- 下一步：掛牌日期已可解釋三檔的指定市場缺件，但尚非完整歷史股票池或正式資料資格；交易日曆、公司行動、known_at、因子與模型仍待逐批討論。先前日曆／價格視窗提案維持待確認。

## 12｜清理探測快取與調整驗證方式（2026-10-11）

- 授權：使用者要求解釋交易日曆與 21 筆價格視窗、直接刪除 `history_probe`，並調整驗證方式，優先重要行為與常見案例。本批只清理該探測目錄及記錄合作偏好；日曆／視窗功能仍待討論同意。
- 清理：`data/cache/history_probe/` 僅含 2330／5274 的兩份原始 JSON，共 5,689 bytes；與完整 run 既存 raw 完全相同，程式、測試、文件與其他快取沒有引用，無唯一行情或紀錄。確認目標位於專案內後刪除，刪後資料夾已不存在；目前分析入口維持 `history_universe`。
- 驗證偏好（後續批次沿用）：事前依改動影響選擇必要驗證，優先關鍵數值／單位／時間、常見成功與失敗案例；不為每次修改固定跑全套、重複掃所有資料或增加大量邊緣案例。資料夾清理只確認位置、引用／獨有資料與刪除結果；一般模組改動跑受影響測試；共用合約、數值／帳務規則或跨模組改動再擴大檢查。遇到失敗或新問題才補測、重跑。既有測試保留，無須為縮減驗證刪除測試。
- 此批驗收：完成上述必要唯讀依賴與重複資料檢查、刪除目標／結果確認；沒有改程式、行情、官方來源或交易規則，因此未跑 Python 全套測試、未建立額外雜湊報告或新測試，沒有外部請求。
- 說明例子：交易日曆列市場實際開市日期，用來找前一交易日與分辨休市／漏資料。21 筆價格視窗取同股、截至指定日期連續 21 個市場交易日的有效收盤價，得到 20 段漲跌；假設首筆 100 元、末筆 110 元，20 日動能為 110／100－1＝10%，這是說明用數字。
- 若後續同意日曆／視窗功能，先驗收三組案例：完整 21 筆；跨週末／休市；缺一天或新掛牌只有 9 筆。既有格式、重複、價格合理性檢查沿用既有測試，不另建重複驗證。日曆、公司行動與歷史公開時間仍未核實，不因這份說明標記完成。

## 13｜先提交推送，再實作官方排程與價格視窗（2026-10-11）

- 授權：使用者要求「commit push後 執行你下一步工作」，接續前述 2025-09 官方交易日曆與 21 筆價格視窗提案。範圍為先保存累積修改，再實作日曆來源、離線逐股視窗、CSV／JSON／閱讀報告、CLI、必要測試及文件；沿用第 12 批縮減驗證的偏好。
- Git 結果：先將第 08～12 批累積的 14 個程式／資料／文件檔案提交為 `72a885b`（`Add universe history downloads and coverage reports`），一般 `git push origin main` 成功，遠端由 `9fd1127` 更新至 `72a885b`。提交前 diff 檢查及唯讀範圍檢視通過，原始快取仍由 Git 忽略，未重跑前批全套。本批接著新增的日曆／視窗功能尚未提交或推送。
- 修改：新增 `src/etf_agent/calendar.py`、`history_windows.py`、`tests/test_calendar.py`、`test_history_windows.py`；CLI 加 `calendar-download`／`history-window-check`。README、資料合約文件 1.13、checklist 與本檔同步實測；沒有新增依賴或更改六種核心合約、CSV 4.0／22 欄、F01～F09 或既有行情／下載報告。
- 日曆來源與方法：保存 TWSE／TPEx 官方年度開休市排程，核對回應年份，按例行週一至週五及官方事件建立月份日曆。TWSE 用 `date=20250101`；探查時僅傳 `queryYear=2025` 實際回傳 2026，故加入錯年拒絕。TPEx 依網頁表單找到 `bulletin/tradingDate?date=2025&response=json`，解析 `data.html` 的民國 114 年標題，排除債券專屬列並保留股票封關後休市；`endDate=20260101` 是可查範圍，不拿它當回應年份。
- 實際排程：下載命令 exit 0，本次下載本身 2 次 HTTPS；另有來源探索請求，不宣稱整輪只有 2 次。產物為 `data/cache/calendar/2025-09/20261011T154421_1306c9a4/` 的 calendar.json、UTF-8 BOM calendar.csv 及兩份 raw JSON，保存 URL、實際取得時間、SHA-256 和排程版本。兩市場各 21 個排程交易日，9/29 休市；`calendar_basis=official_schedule`、`schedule_verified=true`，臨時全市場休市未全面查核，`actual_sessions_verified=false`。
- 視窗介面：`--as-of` 是已完成歷史行情的資料截止日，並非該日盤前決策。依各市場截至該日最近 21 個排程日期只讀 daily，不讀未來日或疊加 monthly；缺整日日表、缺股票及無效價格各自記錄，不縮窗、不補零。本版只支援同月份，當月不足 21 日列 calendar_window_shortfall，跨月讀取仍待擴充。
- 真實歷史例子與結果：截至 2025-09-30，150 檔中 146 檔都有所需 21 筆有效價格；7750 自 9/17 起只有 9 筆，缺前 12 日；3718／7769／7828 各 0 筆、缺 21 日。沒有缺整日日表，input_valid=true，CLI exit 0。輸出在 `data/cache/history_windows/2025-09-30/20261011T154440_9842e79e/`：14 欄、150 列的 UTF-8 BOM window_coverage.csv，以及 window_report.json／.md；逐檔缺日期可直接查閱。
- 實際驗收：本批 4 項重點測試通過（0.195s），涵蓋完整 21 筆、跨週末／休市且拒讀未來日、缺整日日表／新掛牌 9 筆不補值、官方回應年份核對。兩個 CLI 實跑成功，產物必要核對確認 150 個唯一代號、146／4 與 JSON 一致、兩市場 21 日、9/29 排除、CSV BOM、缺日表 0、正式旗標 false。另作短程式檢視，未發現影響日期或筆數的重要問題；未重跑全套、全快取 hash 或全文件連結掃描。前批 132 項通過仍屬先前證據。
- 限制：window_complete 僅表示提供排程下價格齊全，不證明公司行動、return_close、歷史 known_at、個股停牌、歷史股票池、正式截止或帳戶已核實。所有新報告 submission_ready=false；原行情與下載 manifest 的未核實旗標維持原文。沒有呼叫投資模型、付費服務、變動庫存或實際交易。
- 重跑：在專案根目錄執行下列 PowerShell；第一條下載會連網，第二條使用本批保存日曆完全離線、另建版本，新下載日曆則換用 CLI 顯示的 calendar.json 路徑。

```powershell
$env:PYTHONPATH = (Resolve-Path -LiteralPath 'src').Path
python -B -m etf_agent.cli calendar-download --month 2025-09 --output data/cache/calendar --transport curl
python -B -m etf_agent.cli history-window-check --manifest data/cache/history_universe/2025-09/20261011T145716_6e56c903/manifest.json --calendar data/cache/calendar/2025-09/20261011T154421_1306c9a4/calendar.json --as-of 2025-09-30 --output data/cache/history_windows
python -B -m unittest discover -s tests -p 'test_*.py' -k CalendarTests -k HistoryWindowTests -v
```

- 下一批建議：約 20～30 分鐘，先討論以既有 146 檔完整原價視窗產生動能、均線與波動的歷史分析示範 CSV；公式、單位及未調整價格限制先達成共識，正式資格保持阻擋。驗收重點為可手算的動能例子、不足視窗排除與不讀未來日；公司行動／return_close 核實另列批次。因子尚未實作，本批收尾後等待下一批共識。

## 14｜精簡視窗 CSV，暫緩缺失處理（2026-10-11）

- 授權與方向：使用者要求移除大家重複的 expected_dates，日期只寫有缺失的；目前缺失原因合理，先記錄後續處理，下一步先討論。本批只調整閱讀匯出、目前 CSV 與文件／待辦，沒有開始因子或新增資料查核。
- 修改：`history_windows.py` 的 CSV 欄位移除 expected_dates，更新既有匯出測試的欄位預期；目前 `data/cache/history_windows/2025-09-30/20261011T154440_9842e79e/window_coverage.csv` 同步改為 13 欄、150 列。完整股票的 missing_dates／invalid_price_dates 留空，有缺才列日期；JSON 與日曆保留共同預期日期。README、資料說明 1.14、checklist 同步，既有行情、JSON／MD 報告及六種核心合約保持原樣。
- 歷史例子與驗收：7750 仍有 9 筆，missing_dates 列前 12 個交易日；3718／7769／7828 各列 21 個缺失日期，其餘 146 檔沒有價格日期缺口。重寫時逐列確認只刪該欄、其餘值完全相同及 BOM／150 列。僅跑受影響的既有 CSV 匯出測試，1 test、OK（0.114s）；未新增測試、重跑全套或掃全快取，沒有連網、模型或 Git 操作。
- 後續缺失工作：checklist DATA-22 維持未勾選，待日後擴期間／正式用途再處理掛牌前與新股不足政策、跨月視窗、停牌／無成交、意外資料遺漏及必要續抓；臨時休市、公司行動／報酬用調整價與歷史公開時間沿原待辦保留。對現有四檔不再查核、不補零、不尋找其他市場資料來填當期缺口。
- 下一批提案（尚未授權）：約 20～30 分鐘，用截至 2025-09-30 的現有 146 檔完整原價視窗，產生三因子分析 CSV 及共用 metadata JSON。沿 design1001.md §7.1：mom20＝最後／最早收盤−1；trend20＝最後收盤／最後 20 筆平均−1；vol20＝20 個日簡單報酬的樣本標準差（分母 19）×√252。內部比率用小數，閱讀欄 mom20_pct／trend20_pct／vol20_annual_pct 用百分數（10 表示 10%）；252 為設計的年化約定。
- 提案範圍：新增 `features.py` 的純因子計算與離線資料組合，CLI、少量重要測試、文件；保留截止日／資料版本／公式／原價標記，共同日期集中 metadata。產物為歷史原價分析示範，未核實公司行動與 known_at，正式資格保持 false；不假造正式 MarketSnapshot 或 observation 引用。三因子表完成後再討論排名與模型輸入。
- 提案驗收：用可手算及固定價格例子驗三個公式；實際輸出 146 檔、四檔不足沿用既有紀錄；相同輸入重算一致、只用截止日以前 daily 且來源可追溯。說明用例子為首筆 100、後 20 筆 110，mom20=10%、trend20=0%、年化 vol20 約 35.4965%。待使用者確認原價分析方向後才實作。
- 本批重跑：先 `$env:PYTHONPATH = (Resolve-Path -LiteralPath 'src').Path`，執行 `python -B -m unittest discover -s tests -p test_history_windows.py -k test_complete_21_price_window_reports_each_stock_and_writes_readable_bom_csv -v`。一般重新匯出仍用第 13 批的 history-window-check 命令，之後新 CSV 都不再輸出 expected_dates。

## 15｜146 檔歷史原價三因子分析（2026-10-11）

- 授權：使用者先詢問分析的保存、呈現與運用，在明列 `data/cache/features/<截止日>/<執行版本>/` 的 features.csv、metadata.json、analysis.md 與後續排名／模型流程後回覆「好」。本批完成原價因子分析、離線 CLI、重要驗收與文件；缺失工作繼續留在 DATA-22，排名／權重另列下一批。
- 修改：新增 `src/etf_agent/features.py`、`tests/test_features.py`；CLI 加 `history-features --window-report --output`。README、資料文件 1.15、checklist 與本檔同步。計算函式、讀檔組合與產物保存分開，後續排名可重用同一計算；六種核心合約、官方來源、白名單及既有行情／視窗報告未變更。
- 公式與單位：21 筆原價得 mom20＝末／首−1；trend20＝末／最後 20 筆平均−1；vol20＝20 個相鄰日簡單報酬的樣本標準差（分母 19）×√252。固定 34 位 Decimal、內部 ROUND_HALF_EVEN；JSON 將比率保存為十進位文字，CSV mom20_pct／trend20_pct／vol20_annual_pct 用百分數、6 位小數 ROUND_HALF_UP。252 是設計年化約定；原閱讀價格的千元／張在比率中抵消。
- 輸入與界線：沿用第 13 批 window_report.json 的完整股票及分市場日期，直接讀需要的 daily；不重讀月表、不讀截止日之後、不重新查核四檔缺失。對本來就要讀的 manifest／21 個日表核對既有驗收 hash，防止用到已修改資料，未掃描 raw 或其他快取。每股保留來源 key／資料版本／取得時間，共同日期與來源集中 metadata；未建立正式 MarketSnapshot、FeatureTable 或 S/O 引用。
- 實際執行：離線 CLI exit 0；產物在 `data/cache/features/2025-09-30/20261011T160349_3b42fa16/`，features.csv 為 6 欄 UTF-8 BOM、146 檔；metadata.json 保存內部數值／公式／來源／四檔排除紀錄；analysis.md 顯示各因子最小／中位／最大值與依代號排列的前五檔閱讀例子。特徵版本 `price-features-v1-c9e2191b62ec`，所有 146 檔都用 21 價格／20 日報酬；3718／7750／7769／7828 沿用既有不足紀錄。
- 真實歷史例子：2330 原價首 1165、末 1305（千元／張），mom20=12.017167%、trend20=4.337398%、vol20=23.192445%；5274 首 5015、末 5050，三值依序 0.697906%、0.934393%、37.658959%。這是從已保存官方行情計算的原價分析，不是測試假值，也沒有帳戶或投資模型參與。
- 實際驗收：3 tests、OK（1.505s）。案例為可手算與固定價格、完整視窗／離線日表／百分數與來源／重算一致及新版本不覆寫、日表被修改後 hash 不一致阻擋。實際產物只做必要核對：146 唯一股票與原報告完整集合相同、6 欄／BOM、4 排除、21 日不超截止、CSV 全值與 JSON 六位百分數一致；另用獨立標準庫公式核對 2330／5274 通過。未重跑全套或全文件連結／raw hash。
- 限制與下一步：原價未調整除權息，公司行動、known_at、臨時休市與正式候選資格仍未核實，submission_ready=false。下一批可討論百分位排名、低波動反向及綜合權重；設計草案 40%／25%／35% 僅是提案，不因本批變成已同意設定。沒有安裝依賴、連網、付費或投資模型呼叫、帳務交易、Git commit／push。
- 自行重跑：在專案根目錄執行下列 PowerShell，會另建執行版本，沿用相同輸入時數值與特徵版本一致。

```powershell
$env:PYTHONPATH = (Resolve-Path -LiteralPath 'src').Path
python -B -m etf_agent.cli history-features --window-report data/cache/history_windows/2025-09-30/20261011T154440_9842e79e/window_report.json --output data/cache/features
python -B -m unittest discover -s tests -p test_features.py -v
```

## 16｜補齊指標意義，整理 README 與專屬操作文件（2026-10-11）

- 授權：使用者要求 analysis.md 說明為何使用三種指標及代表什麼，並明確要求更新 README，讓它能快速理解整個專案架構與使用方式、各項執行細節連專屬文件。本批限於解說、文件導覽與摘要產生器的同範圍同步，沒有開始排名或改策略參數。
- 原說明位置：design1001.md §3／§7.1 已有主題、公式、用途與兩種價格面向；資料合約文件有公式／單位，但當時 analysis.md 只列計算方式，未完整說明選用理由。此次將理由、數值意義與後續運用補進現有摘要。
- 摘要修改：`features.py` 把 Markdown 呈現分成 `_render_feature_analysis()`，未變動因子計算；之後每次匯出自帶「為什麼先使用」「各指標代表什麼」「計算方式」「後續如何運用」。由現存 metadata 重建 `20261011T160349_3b42fa16/analysis.md`，沒有重新讀行情或重新算因子。現有 features.csv 與 metadata.json 已逐位元確認不變。
- 解說例子：動能 10% 表示窗口原價上漲 10%；均線偏離 3% 表示末價高於最近 20 筆平均 3%；年化波動反映近期日報酬起伏換到年尺度。三指標用現有價格、約一月視窗及可追溯公式作 MVP 起點，動能／均線偏離相關，主要是趨勢與波動兩面向；未宣稱官方指定、回測最佳或保證未來表現。
- 必要驗收：受影響的既有匯出／重算測試 1 test、OK（0.130s），無新增測試，未重跑全套、行情下載或數值全套驗收；現有摘要已人工閱讀確認理由／含義／未來用途與原分布數值存在，數值 CSV／JSON 保持原版。
- 文件整理：README 精簡為 75 行，集中目標／現況、架構與完成邊界、最短執行、九個 CLI 的用途入口及成果連結。新增 `docs/quickstart.md`（環境／合約／白名單／必要測試）、`history_data.md`（下載／快取續接／匯出／覆蓋）、`calendar_windows.md`（排程／截止日／視窗）、`factor_analysis.md`（指標理由／意義／用途／分析操作）；`data_contracts.md` 升 1.16，保留因子欄位與單位合約，詳細操作轉連專屬文件。
- 文件驗收：只核對 README 與本批四份新操作文件的 84 個本機連結目標均存在、九個 CLI 均有操作入口，並人工對照各入口章節名稱與已實作參數。沒有掃全專案連結或外部網址；git diff --check 通過。本批不連網、安裝、呼叫模型、改帳戶、commit 或 push；排名／權重仍待下一批共識。
- 重跑：一般 `history-features` 命令維持不變，會在新版本摘要自帶解說，完整用法見 `docs/factor_analysis.md#執行與重算`。本批只更新當前 MD 解說，沒有產生另一份數值分析；必要匯出測試為 `python -B -m unittest discover -s tests -p test_features.py -k test_complete_stock_only_daily_inputs_percent_csv_and_repeatable_new_runs -v`，先按 quickstart 設定 PYTHONPATH。

## Git｜日曆、價格視窗、三因子與文件提交（2026-10-11）

- 授權：使用者明確要求「COMMIT PUSH」，提交第 13～16 批已完成修改並推送目前倉庫。此操作沒有授權新的排名／策略功能。
- 範圍：15 檔，包括 calendar／history_windows／features 三個模組、三份對應測試、CLI、README、資料合約、四份專屬操作文件、checklist 與本檔；行情快取與生成分析保留本機，提交摘要產生器及重算說明。
- 提交前檢查：git diff --check 通過，變更名單與 CLI 所需模組一致；.gitignore 已排除 cache、帳戶、金鑰及本機設定，沒有額外未授權檔案。沿用第 13～16 批的必要測試與實際產物驗收證據，不重跑全套或抓行情。
- 保存目標：本機 main → origin/main，GitHub `ismesid/yushan-etf-agent-MVP`；以一般 git commit／git push 保存。最終 commit ID 與推送／同步結果在本次回覆提供，也可用 git log -1 與 git status 查看。

## 17｜修正 GitHub 文件的快取成果連結（2026-10-11）

- 授權：使用者回報 README 連結在 GitHub 顯示 404，後續要求「繼續」。延續已授權文件修正與 COMMIT PUSH，修正導航、更新紀錄並推送；未開始排名、策略或資料下載。
- 原因：第 16 批僅檢查本機存在，漏了 Git 追蹤範圍；README 的 6 個成果連結指向被 `.gitignore` 排除的 `data/cache/`，GitHub 沒有這些檔案。第 13～16 批先前已由 `3848134` 推送 main，本批修正該版本的文件入口。
- 修改：README 的成果入口連至已提交的歷史資料、日曆／視窗與因子分析說明；5 份相關文件的 49 個快取超連結改為標明本機的程式碼路徑，quickstart 同步說明 GitHub 閱讀與本機重建。資料合約及因子文件升 1.17。歷史 checklist 的驗收連結保留當時紀錄，本批不將快取加入 Git。
- 閱讀例子：在 GitHub 點 README「因子說明、範例與重算」可進入 `docs/factor_analysis.md`，閱讀三個指標與 2330 範例；依命令重建後，再用 IDE／Excel 開啟本機 `features.csv`、`analysis.md`、`metadata.json`。既有數值、行情、計算程式、帳戶與正式資格均未修改。
- 實際驗收：README 32 個及 docs 109 個本地 Markdown 導航連結，全部能對應 Git 追蹤檔案／目錄，所用標題 anchor 均吻合；快取已不再作這兩個範圍的導航連結。文字替換的 UTF-8 標記問題已在提交前修正；命令範例與原版一致，git diff --check 通過。僅文件修改，未跑 Python 測試、掃行情 hash 或查外部網址／HTTP 狀態。
- 保存與後續：本批 9 份文件以一般 commit／push 保存 main → origin/main，最終 ID 與同步結果在回覆提供。排名／權重仍需另外討論；本機行情與分析維持原保存方式。
