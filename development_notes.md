# 開發紀錄

更新：2026-10-11。此檔統一保存簡明的討論、決定、授權、驗收與下一步，不保存逐字對話。

## 合作方式與依據

- 目標：約 8 小時完成可開會討論的 ETF MVP，模組保留資料、因子、模型與 UI 的擴充邊界。
- 每批約 10～30 分鐘，先說明與討論，使用者明確同意後實作；每批完成展示結果，再討論下一批。第一批同意不授權後續階段。
- 文件維護：依使用者第 16 批要求，README 作快速理解專案架構、現況與執行的入口；完整參數、輸入輸出、續接與失敗處理連到各功能專屬文件。各批更新 README 的功能狀態與入口，測試流水帳留本檔／checklist，避免持續堆進 README。
- GitHub 導覽：README 與操作文件的倉庫內連結必須指向 Git 已追蹤的檔案或目錄，並核對章節標題；不能只驗本機檔案存在。被忽略的快取成果顯示為明確本機路徑，入口連至可閱讀的說明與重建方式。
- 解說集中：依第 18 批要求，通用解釋與閱讀範例維護在 docs；覆蓋、價格視窗與三因子執行保留 CSV／JSON，CLI 顯示當次數據摘要與專屬文件位置，避免產生重複本機 Markdown。
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

## 18｜解說集中 docs，清理重複本機 Markdown（2026-10-11）

- 授權：使用者肯定解釋文件集中 docs，要求確認原本僅本機可看的解釋文件與 docs 重複很多時可刪。先比對四份現有快取 Markdown 與相應 docs、CSV／JSON，再清理並同步產生器、CLI、引用及必要測試；不擴至策略、排名或新資料取得。
- 比對：三因子 `analysis.md` 的選用理由、意義、公式、用途及限制均已在 `docs/factor_analysis.md`；獨有分布與前五股閱讀範例先完整移入該頁，標記 2025-09-30、146 檔及既有版本。視窗結果與限制已有 `docs/calendar_windows.md`；兩份內容相同的早期覆蓋摘要已有 `docs/history_data.md`，各自 JSON 保存原輸入、雜湊、市場統計、警告與缺失，CSV 保存完整清單。
- 清理範圍：移除 `features/2025-09-30/20261011T160349_3b42fa16/analysis.md`、`history_windows/2025-09-30/20261011T154440_9842e79e/window_report.md` 及 `coverage/2025-09-01/` 下 `20261011T143543_bb32db7e`／`20261011T144802_4463a889` 的 `coverage.md`（以上均在 `data/cache/`）。現有 metadata 的 artifacts 僅去掉已刪 Markdown 項目，其餘資料保持原值。
- 程式與文件：移除 features／history_windows／coverage 三個 writer 的 Markdown 呈現，三種執行各保存 CSV／JSON，不再回傳 analysis_md／report_md；CLI 改顯示 docs 專屬說明。README、操作文件、資料合約及 checklist 同步，因子／資料合約說明升 1.18。核心資料合約、CSV 格式、因子公式、特徵版本及官方來源未改；歷史 notes 保留當時建立 Markdown 的紀錄，本節說明其後續清理。
- 例子：既有三因子仍是 146／150 檔、4 檔排除；2330 的動能／均線偏離／年化波動仍為 12.017167%／4.337398%／23.192445%。之後先讀 docs，再開當次 `features.csv`；日期、排除、公式與來源在 `metadata.json`。全部仍是歷史原價分析、submission_ready=false，沒有帳戶或投資模型參與。
- 必要測試：只更新既有匯出案例並跑 4 tests、全部 OK；因子匯出／來源／重算一致 1 項（0.133s），視窗 CSV／JSON 1 項（0.086s），覆蓋版本不覆寫及 CLI 錯誤時診斷保存 2 項（0.051s）。測試確認各次輸出只含原 CSV／JSON，未新增測試或重跑全套；程式數值邏輯未更動。
- 實際清理驗收：四個絕對目標均核對位於本專案 `data/cache/` 且為 Markdown 檔，再逐檔刪除；目前快取沒有 Markdown。既有 7 份 CSV／JSON hash 與清理前相同，metadata JSON 除去 artifacts.analysis_md 後與原值完整相同；分布及前五股共 8 列數值在 docs 與原 MD 逐列一致。README／docs 的 143 個相對導航連結均指向 Git 追蹤檔／目錄且章節存在，47 行既有命令未改，git diff --check 通過；未查外部 HTTP 或掃其他行情快取。
- 重跑與後續：三個 CLI 的命令參數維持不變，按 `docs/history_data.md`、`docs/calendar_windows.md`、`docs/factor_analysis.md` 執行。無安裝、連網、模型呼叫或正式交易；本批尚未 commit／push。排名／權重仍待另批討論。

```powershell
$env:PYTHONPATH = (Resolve-Path -LiteralPath 'src').Path
python -B -m unittest discover -s tests -p test_features.py -k test_complete_stock_only_daily_inputs_percent_csv_and_repeatable_new_runs -v
python -B -m unittest discover -s tests -p test_history_windows.py -k test_complete_21_price_window_reports_each_stock_and_writes_readable_bom_csv -v
python -B -m unittest discover -s tests -p test_coverage.py -k test_report_outputs_are_readable_and_each_run_is_separate -k test_cli_invalid_row_returns_two_and_preserves_diagnostics -v
```

## 19｜權重研究備註與歷史因子排名（2026-10-11）

- 授權：使用者要求將本輪權重資料查詢記錄於 `docs/factor_analysis.md`，附連結供開會，並明確要求「先按照預定的 % 執行排名」。本批沿原提案，動能 40%、均線偏離 25%、低波動 35%；未改因子期間或新增資料／模型，尚未授權 Git 提交推送。
- 決定：40／25／35 是專案初始分析設定，不是公開資料證明的業界標準或最佳配比。研究資料記錄 MSCI 的中期風險調整動能、S&P 四因子等權合成與低波動配置、均線作者頁及 French 動能定義；版本及與本專案的差異一併保存。多期含成本驗證與相關性列會議待討論，本批按已同意配比執行。
- 方法及界線：讀現有 features metadata 的精確十進位字串，三因子各算平均平手分位，低波動僅反向一次；總分降序、精確平手按 ticker 升序。146 檔完整視窗只是歷史分析母體；保留原四檔排除紀錄，formal_eligible／submission_ready 均 false，不建立正式 FeatureTable／MarketSnapshot 或候選交易池。
- 保存：新增 `src/etf_agent/ranking.py`、`config/ranking.json`、`tests/test_ranking.py` 與離線 `history-rankings` CLI，另建 `data/cache/rankings/<截止日>/<執行版本>/` 的 CSV／JSON。計算、metadata 讀取、產物保存分開；精確 Fraction 排序後將比率保存為 34 位 Decimal 字串、ROUND_HALF_EVEN，避免 1/3／1/145 等非終止小數造成假平手。CSV 為 UTF-8 BOM、16 欄，三個原始因子欄為百分數，分位／貢獻／總分欄乘 100 顯示相對分數，六位 ROUND_HALF_UP。方向固定為動能／均線正向、波動僅反向一次；無完整因子、重複代號、非有限值或不合法權重則停止，不逐股重新配重。
- 實際執行：CLI exit 0，本機產物 `data/cache/rankings/2025-09-30/20261011T165509_b1899354/`，版本 `price-rankings-v1-3f25120fa996`；146 檔、4 檔排除、16 欄，只有 rankings.csv／metadata.json，沒有本機說明 MD。各股保留原 source_metadata，JSON 保存特徵／白名單／日曆版本、完整 profile、輸入 metadata 與設定檔路徑及 hash、排名公式、排除理由及限制。
- 歷史結果例子：第 1 名 3231 緯創 78.482759 分；動能／均線偏離／低波動貢獻顯示為 36.965517／24.137931／17.379310 分，各欄獨立四捨五入，顯示相加可與總分差最後一位。第 2～5 名依序 2382 廣達 78.206897、2303 聯電 76.758621、2887 台新新光金 76.275862、3227 原相 75.586207；2330 第 7 名 73.655172，5274 第 98 名 43.103448。這些是同截止日歷史分析的相對分數，不是報酬率、買賣或配置指令，沒有帳戶參與。
- 必要驗收：3 tests、OK（0.108s），涵蓋手算／平均平手／全同／單股／低波動反向與非終止小數精確平手、常見不完整因子與配置錯誤、僅讀 metadata／設定及來源／排除保存、重算一致與新 run 不覆寫。真實 CLI 整合後，另以獨立 less／equal 計數推導平均名次及 Fraction 公式核對 146 全排序、貢獻、分數與 ticker 決勝通過；CSV BOM／16 欄／146 列及 JSON 分數一致，輸入 metadata hash 保持 `5cf1b5270d726ef98befa70df9ecd6b45c7aa10e69c0767b11b29b782333304b`。缺檔 CLI 回可讀錯誤、native exit 2；PowerShell 外層原回 1，明確傳回 `$LASTEXITCODE` 後核實原生退出碼，未修改程式。未重跑全套或掃行情／raw hash。
- 文件：`docs/factor_analysis.md` 記錄五份來源與開會問題，新增 `docs/ranking.md` 說明計算、欄位、範例及操作；README 更新架構／已完成排名／十個命令入口，quickstart 與資料合約同步。因子／資料合約文件升 1.19，排名說明 1.0。FACTOR-05～07 按歷史分析範圍勾選，其餘正式資料／資格／流動性及模型項目不擴張勾選。
- 文件驗收：研究來源用原文網址與指定版本記錄，未把作者資料頁或不同指數方法當成同一配比的證明；本批不重做外部 HTTP。新增導航目標可對應已追蹤或本批新增待提交檔案及章節，沒有指向 Git 忽略快取的導航；固定歷史範例對照實際 CSV，git diff --check 通過。缺檔驗收沒有另建結果版本，目前真實排名目錄只有上述一次成功執行。
- 下一步與保存：可另批討論正式資格、流動性及證據包／帳戶接合，再形成模型決策池；本批不做相關性、等權比較或回測。18～19 批仍未 commit／push；沒有新增依賴、抓行情、模型／付費服務或正式交易。實際命令如下，重跑會另建版本，相同輸入及 profile 的值與 ranking_version 相同。

```powershell
$env:PYTHONPATH = (Resolve-Path -LiteralPath 'src').Path
python -B -m etf_agent.cli history-rankings --feature-metadata data/cache/features/2025-09-30/20261011T160349_3b42fa16/metadata.json --profile config/ranking.json --output data/cache/rankings
python -B -m unittest discover -s tests -p test_ranking.py -v
```

## Git｜文件清理、權重研究與歷史排名提交（2026-10-11）

- 授權：使用者明確要求「commit push」，保存第 18～19 批已完成且驗收的修改；兩批先前「未 commit／push」是當時狀態，本節記錄後續 Git 授權。
- 範圍：19 檔，涵蓋 CSV／JSON 產物保存調整、排名模組與 CLI、40／25／35 設定、相關測試、README、docs 及開發紀錄。本機行情與排名快取仍由原忽略規則管理。
- 提交前檢查：修改及未追蹤名單均屬上述範圍，`git diff --check` 通過；沿用第 18 批 4 項受影響測試、第 19 批 3 項排名測試及真實產物核對結果，本次沒有再跑測試或抓行情。
- 保存目標：本機 `main` → `origin/main`，GitHub `ismesid/yushan-etf-agent-MVP`，一般 commit／push。暫存後檢查範圍與空白錯誤，推送後核對本機與遠端追蹤版本及工作目錄；最終 commit ID 與實際結果在本次回覆提供，亦可用 `git log -1`、`git status` 查閱。

## 20｜含原持股的歷史帳戶匯入與市值核對（2026-10-11）

- 授權：使用者明確表示不要全現金，要讓 Agent 考慮賣出；以九月份資料產出 2025-10-01 買賣與配置，最後才做效益驗證程式。重新規劃後，使用者回覆「你可以執行第一部分 記得總金額要符合比賽規則」。本批限於截至 9/30 的獨立 demo 帳戶、歷史估值、CLI、相關測試與文件，不涵蓋模型、配置合約、D-Plan、效益驗證或 commit／push。
- 防止未來資料進入：Agent 交易決策與 D-Plan 生成、驗證及封存前，不下載或讀入 2025-10-01 行情；後續取得新授權後才接入驗證資料。此限制須沿用到候選／證據包與模型批次。此次只開啟既有 9/30 日表；測試中的 10/1 為不存在的人工 sentinel 路徑，不是真實行情。
- 本金修正：上一輪 1 億元提案改為 **1,000,000,000.00 元（10 億）**。本輪回查 [W06 清大代轉公告](https://dsa.site.nthu.edu.tw/p/406-1266-314652,r6890.php?Lang=zh-tw)，正文載明 10 億虛擬本金；競賽官網仍 403，附件連結本次導回首頁，未讀到完整辦法。10 億作 demo 建構金額，正式期初流程與後台帳戶仍待核實。本輪網路查核僅查本金依據，沒有下載新行情。
- 帳戶：新增 `tests/fixtures/account_demo_2025-09-30.json`，沿用舊 fixture 的 25 個代號，股數全部重建；舊 `contracts_demo.json` 的 2026-10-14、假價、1 億 NAV 保持原樣。人工期初建構為每股預算 `10億×90%÷25=36,000,000` 元，依 9/30 原始收盤 floor 到整張，再以 NAV 減全部市值得到現金；這不是模型選股或已定案配置參數，不計算不存在的建倉成交／費用。
- 介面：新增 `src/etf_agent/account.py` 的 `load_account_json()`、`load_history_closes()`、`value_account()`、`analyze_account()`、`write_account_report()`。核心估值不讀檔／抓 API、不依賴模型 SDK；AccountSnapshot 1.0 合約保持不變。CLI 增加 `account-check --account --ranking-metadata --as-of`，可用 `--universe`／`--universe-manifest`／`--output`／`--json`。
- 行情輸入：排名 metadata 截止日須等於明確 `--as-of`，日期先於 manifest／行情讀取檢查；再核對 F05 版本、manifest hash 與唯一日表路徑／hash，只讀指定日 CSV 4.0，不讀其他日、monthly 或 raw。重用 coverage 檢查日期、市場、重複與價格，對回 source_key／data_version／fetched_at／原始 hash 記錄；來源 hash 是沿 manifest 保存，未重新掃描原始檔。原持股無需出現在完整排名母體。
- 計算與問題：價格轉元／股時數字與千元／張相同，持股用股，金額用元；Decimal 50 位／ROUND_HALF_EVEN，NAV 差額為「計算 NAV－輸入 NAV」。demo 身分式用零容差，不是正式結算 rounding／容差。缺行情保留原股數、價格／市值 null，完整股票合計／NAV／差額 null，已估值小計另列；日期／NAV 不符不改帳。基本期初只驗白名單、20～30 檔、2330≤25%／其他≤10%、cash 0～25%；現金比例以本地計算 NAV 為分母，正式 server 口徑未確認。此為資料輔助，不取代配置／完整 D-Plan 驗證。
- 實際輸出：`data/cache/account_checks/2025-09-30/20261011T172216_f175f6cb/`，只有 account_snapshot.json／positions.csv／valuation.json。25 檔股票市值 **890,890,600.00** 元，現金 **109,109,400.00** 元，計算與輸入 NAV 均 **1,000,000,000.00** 元，差額 **0.00**，現金比例 **10.91094%**。白名單、檔數、個股上限及現金檢查皆通過；75 WARN 為 25 股各自的 known_at、公司行動與正式交易資格未核實，沒有 BLOCK。仍為 demo=true、reconciled=false、submission_ready=false。
- 可讀歷史例子：2330 人工原持 **27,000 股×真實前收 1,305.00 元＝35,235,000.00 元**；5274 **7,000 股×5,050.00 元＝35,350,000.00 元**；2891 **839,000 股×42.90 元＝35,993,100.00 元**。這些是待模型檢視的期初部位，沒有產生 10/1 訂單。
- 實際驗收：初測 **6 tests、OK（0.534s）**；短檢視發現錯日列可能覆寫診斷價格及零計算 NAV 除零，已修正指定日列篩選、沿用完整價格有效性欄位及正 NAV 才計現金比。補 1 個針對兩項問題的回歸案例後，最終 `test_account.py` **7 tests、OK（0.412s）**。涵蓋純估值／股元單位與 demo 保留、日期與 NAV -0.01 差額、缺行情／無效價仍保留原持股、日期／版本／hash／來源阻擋且讀檔限於 metadata／manifest／9/30、25 檔三產物保存與不覆寫、CLI 成功 0／NAV 失配 2 保存診斷／缺帳戶 2 不建產物。正常歷史 CLI 實跑 exit 0；另以不匯入估值模組的標準庫程式核對 25 股原日表收盤×股數、CSV 值、精確 10 億合計、三檔產物、UTF-8 BOM、輸入與 demo 身分及 artifact hash，全通過；最大單股權重 3.600%。沒有跑全套、掃所有快取或重新查核四檔缺件。
- 文件與完成範圍：新增 `docs/account.md`、相關測試與歷史 fixture，修改 CLI、README、資料合約（1.20）、checklist 與本檔。README 連至 docs；快取純文字標本機路徑。DATA-14 與帳戶輔助 DATA-23 按本批驗收勾選，正式庫存／模擬結算 DATA-15 等項目仍未勾選；沒有新增依賴、改三因子配比、模型呼叫、實際交易、commit／push。
- 收尾檢查：`git diff --check` 通過；只核對本批帳戶文件與新增入口的 11 個本機導航目標，全部存在且不被 Git 忽略，沒有掃所有快取或全專案連結。
- 下一批：討論九月份候選資格／流動性與完整原持股的資料狀態；再做 10/1 決策、9/30 截止的凍結證據包。讓 Agent 提出每股目標權重涉及 AgentDraft 合約調整，另批同意後實作；由程式推最終股數、風控與 D-Plan。效益程式與 10/1 行情嚴格排在計畫封存後。

重跑（PowerShell，專案根目錄；完全離線，另建結果版本）：

```powershell
$env:PYTHONPATH = (Resolve-Path -LiteralPath 'src').Path
python -B -m etf_agent.cli account-check --account tests/fixtures/account_demo_2025-09-30.json --ranking-metadata data/cache/rankings/2025-09-30/20261011T165509_b1899354/metadata.json --as-of 2025-09-30 --output data/cache/account_checks
python -B -m unittest discover -s tests -p test_account.py -v
```

## 21｜sub_agents 分工介面與凍結歷史決策輸入（2026-10-11）

- 授權：使用者希望 18:30 前先打通「10/1 歷史決策→股數／風控→可驗證 D-Plan」，三個 agent 用簡單介面串接，架構重整與檔案整理留在之後；對第一批「資料／檢討介面與凍結 packet、主 Agent 提目標權重、程式推股數」回覆「可以」。本批只實作第一批，沒有授權模型呼叫、股數、D-Plan、10/1 行情、commit／push。
- 分工：新增 `sub_agents/data_agent.py`，重用排名與指定日收盤，組成完整帳戶／來源／因子資料；目前只支援歷史 replay，未實作最新下載、增量合併、流動性閾值或新因子。新增 `test_agent.py`，目前無前日已封存 D-Plan／成交，因此嚴格回傳 prior_run_missing、空建議、performance=null；實際績效與最佳化尚未完成。事後檢討只能影響下一日，不回改已封存決策。
- 合約：新增 WeightedSelection／WeightedAgentDraft 2.0、strict schema；權重 Decimal 字串、每股上限、精確合計加現金等於1、完整原持股 review 與引用存在。keep／rebalance 必須選入，未選入只能明示 exit，避免調整意圖被默默全賣。AgentResult 支援兩版，PortfolioProposal 1.0 增列 agent_target_weights 方法識別；舊草稿與 fixture 不變，未實作該配置器或 shares。
- 凍結：新增 `evidence.py`、`prompts/decision.md` 與 CLI `prepare-decision --account --ranking-metadata --as-of --trade-date`。決策日先驗晚於截止日，排名日期／scope／原價基礎／版本先驗再讀指定日行情；沿用 account 的 manifest／日表 hash 與來源核對。只讀帳戶、排名 metadata、manifest 與 9/30 日表，不重新掃快取；上游特徵引用沿排名保存，未重新讀取／驗收全部特徵來源。
- 證據：依 TWSE／TPEx 相同 endpoint 月報系列建 S1／S2，保留 147 個實際 URL、資料版本、來源 hash 與取得時刻；獨立核對為 TWSE 99 個 `/rwd/zh/afterTrading/STOCK_DAY`、TPEx 48 個 `/www/zh-tw/afterTrading/tradingStock`。程式拒絕混合 endpoint；正式系列接受未知。內容只有描述日期、不填造 known_at／官方 timestamp。市場 O1 是分析股票池的正動能／均線廣度，不是 TAIEX／櫃買指數；個股 O 保留數值、來源及人工帳戶上下文。
- 實際結果：`data/cache/decision_packets/2025-10-01/20261011T174640_396092d6/`，CLI exit 0；146 排名／146 demo 候選、25 全持股、4 原排除、2 S、147 內部 O，NAV 1,000,000,000.00、差額 0.00。demo_decision_ready=true 僅表示歷史 demo 輸入可用；real_agent_decision／formal_eligible／submission_ready=false。6 檔為 data_report.json、review_report.json、evidence_packet.json、manifest.json 及必要可執行 prompt/schema，沒有產物說明 Markdown。
- 驗收：weighted 7 項通過（最終 0.230s），review 4 項通過（0.000s），packet 5 項通過（最終 1.154s；新增同 endpoint 反例後只重跑受影響檔）；舊 fixture 聚焦 3 項通過（0.137s）。合計 16 項新增與 3 項相容檢查。涵蓋權重、型別、完整 review、缺價不刪持股、日期先驗、來源／數值不一致、無假績效、允許讀檔邊界、hash、穩定輸入版本、不覆寫及 CLI 退碼。正常歷史 CLI exit 0；另以不匯入模組的標準庫核對 6 產物／5 hashes、完整帳戶、資料截止、所有 O→S 引用及 flags 全通過。不跑全套、不下載或讀入 10/1 行情、不呼叫投資模型、不改 40／25／35 或重查四檔缺件。
- 文件：README 加第 12 個命令與簡單角色導航；新增 `docs/decision_workflow.md`，資料合約升 1.21；更新 checklist／本檔。EVIDENCE-05、演示輔助 EVIDENCE-06 與 AGENT-02 按本批證據勾選；官方證據、真實 provider／模型、股數／風控、D-Plan、帳務仍未勾選。
- 收尾：`git diff --check` 通過；只核對新增工作流／提示與本批入口的 12 個本機導航目標，全存在且不被 Git 忽略。以標準庫查到本機 `jsonschema_available=False`，沒有安裝；下一批結構驗證須明確包含此依賴。既有第 20 批修改保留，工作樹尚未 commit／push。
- 下一批：只討論並實作官方公式股數、完整組合／現金／姿態檢查與 D-Plan 編譯、結構及語意驗證；再以新授權接真實模型。147 內部 O 須依實際引用裁剪與重編，數值轉官方 JSON 型別；不得把此 packet 說成已符合 D-Plan。正式截止／公開時間、交易日相鄰、公司行動、費用取整及實際期初核對仍未確認，輸出限 demo；10/1 行情仍嚴格排在計畫生成、驗證與封存後。

重跑（離線，專案根目錄；另建版本）：

```powershell
$env:PYTHONPATH = (Resolve-Path -LiteralPath 'src').Path
python -B -m etf_agent.cli prepare-decision --account tests/fixtures/account_demo_2025-09-30.json --ranking-metadata data/cache/rankings/2025-09-30/20261011T165509_b1899354/metadata.json --as-of 2025-09-30 --trade-date 2025-10-01 --output data/cache/decision_packets
python -B -m unittest discover -s tests -p test_evidence.py -v
```

## 22｜account_agent、官方股數與前收風控、D-Plan 編譯／驗證（2026-10-11）

- 授權：使用者對第二批與 jsonschema 安裝回覆「可以」，另要求新增 account_agent 每日回報現金／可用資金／完整股數，並在最後整合測試先刪已下載資料，由 agent 調用既有程式重抓，放在共用位置。後者排在最終測試，本批未刪／未抓；10/1 行情仍禁止在決策、驗證及封存前取得。真實模型呼叫仍待下一批同意，未 commit／push。
- 依賴：pyproject 增 jsonschema>=4.0,<5；建立專案 `.venv`。首次 pip 被 sandbox WinError10013 擋連線，依已同意用途提出提升安裝後成功，實裝 jsonschema4.26.0。全域 Python 沒此套件；編譯／驗證使用 `.venv\Scripts\python.exe`。
- 帳戶角色：新增 `sub_agents/account_agent.py`／4tests，純 AccountSnapshot＋估值核對，回報原現金、NAV、25全持股、來源hash、缺件／身份／日期／股數問題。demo估算可用現金等於cash，明示 reserve=0／not_implemented；正式 available_cash_twd=null，不假造可用額度，不扣款或更新股數。prepare-decision 增account_report與workspace索引，共8產物／7hashes。
- 計算：新增 portfolio.py，WeightedAgentDraft目標由精確 Fraction／Decimal floor 成整張，再按原庫存產 BUY／ADD／TRIM／SELL_ALL、零delta續抱。完整組合費後NAV、現金／每股權重／檔數、千股／超賣、前收淨流向與宣告現金区間皆重算；費率用 F07，Decimal完整demo估算不取整。自訂產業／換手／壓力與實际成交未完成，未改三因子配比。
- 編譯：新增 dplan.py／compile-plan，裁實際引用O／S並重編S/O/I/D，理由用原草稿不代寫；values轉官方JSON數字後重新檢查floor。歷史source content_as_of採日期末23:59:59描述截至當日，是明示demo政策，非公開known_at。模型metadata缺失就保存schema BLOCK，不塞範例模型。保存候選、完整投影、驗證、三角色報告／workspace、packet／draft、manifest及所有實跑src/config/prompt/schema／pyproject/F04/F07內容版本；dirty workspace不冒用舊HEAD。
- 驗證：新增 validation.py，Draft202012Validator／FormatChecker及真實日期、時區、起訖；ID引用、完整持股、action/order/官方floor、數字序列化、超賣、費後組合／姿態及funding缺口。按當前plan獨立重算，portfolio BLOCK另保留，不能被KEEP/no_trade掩蓋。有完整凍結facts時，source URL／authority及O文字／數字／來源組合逐一比對；F08/F09只作schema／語意樣本，F09 I9確實BLOCK。正式server、台股相鄰日與全部設計L01～L15仍未完整實作。
- 實跑：最新四角色packet `data/cache/decision_packets/2025-10-01/20261011T180724_e49e57e2/` exit0。另人工流程草稿（明標fixture，不是投資模型）25股各0.0364、cash0.09／rebalance，接真9/30價格，產 `data/cache/plans/2025-10-01/20261011T180729_491b495e/`：17買單／8續抱，買8,698,350元、fee12,395.14875000元、tax0、前收預估cash100,398,654.85125000、NAV999,987,604.85125000，portfolio_ok=true；缺全部真實模型metadata故schema BLOCK／exit4，只存dplan_candidate.json，未產有效D-Plan。帳戶不入帳、submission_ready=false。
- 驗收：portfolio7（0.209s）、account_agent4（0.027s）、validation8（0.794s）、compiler6（最終0.920s），新增25；受影響packet5（最終0.813s），共30相關檢查，未全套。初次人工草稿命令漏PYTHONPATH，補上後正常。短review修正KEEP配置BLOCK串到validator gate；補數字序列化整張邊界及凍結O／來源篡改反例。對早期同値產物以不匯入模組的標準庫獨立核對四角色索引、7輸入hash／6初版編譯hash、程式版本包、所有股數／費用／現金與真實metadata缺失BLOCK全通過；最新計畫多3角色報告與workspace，10個artifact hashes。
- 文件：README／account／decision_workflow／quickstart補四角色、共用位置、.venv與compile-plan；資料合約升1.22，更新checklist／本檔。真正完成的股數、前收風控／引用／驗證按證據勾選；真模型、有效DPlan、成交／帳務、壓力、正式資格與完整來源仍未完成。
- 下一步：取得真實決策批次同意後接provider，先核對本機CLI／可用帳號／真實模型資訊；最後整合測試再安全清除指定九月下載快取、由data_agent重抓九月並重建同截止因子／排名，交四角色共享索引；不清除官方來源或帳戶輸入。重抓耗時與模型可用性需留緩衝，不因18:30目標填假metadata或使用10/1行情。

重跑（人工草稿只驗流程，預期缺模型exit4；新run不覆寫）：

```powershell
$env:PYTHONPATH = (Resolve-Path -LiteralPath 'src').Path
.\.venv\Scripts\python.exe -B -m etf_agent.cli compile-plan --packet data/cache/decision_packets/2025-10-01/20261011T180724_e49e57e2/evidence_packet.json --draft data/cache/plan_examples/weighted_draft_fixture_2025-10-01.json --decision-source fixture --output data/cache/plans
```

## 23｜九月資料冷啟動、四角色共享與真實決策接線（2026-10-11）

- 授權：使用者回覆「可以」，執行已討論的真實Codex決策初次及最多一次必要修正、最後清除指定九月下載快取後連動測試。只抓2025-09，截止9/30、決策10/1；10/1行情仍禁止。未授權commit／push、真正交易或提交。
- 清除：先核對絕對路徑在本專案內，以PowerShell原生Remove-Item清除 `data/cache/history_universe/2025-09/`（舊run `20261011T145716_6e56c903`）。官方原文、帳戶、日曆及先前分析／決策封存保留；舊分析引用該raw目錄的重跑需改用本批新run，不能宣稱其raw還存在。
- 接線：新增pipeline.refresh_prepare與refresh-decision入口，現有下載器→日表／月表→21筆視窗→三因子→同40/25/35排名→資料／前日檢討／帳戶回報→凍結證據包。各階段都在新的shared run，頂層workspace列四角色與相對路徑；帳戶與排名設定複製凍結。test_agent仍prior_run_missing，實際前日成果／最佳化建議未完成；account_agent仍快照回報，無成交入帳。
- 已知缺件：3718／7769／7828依既有紀錄略過請求，不填raw／fetched_at／HTTP資料；7750正常重抓但仍無完整視窗，原四檔排除保留。額外下載失敗或視窗input_invalid阻擋model。
- 實跑下載：沙箱內curl連線失敗，停止首個失敗run，不把它當正常下載；依環境權限提升重跑成功，shared root `data/cache/integrated_runs/2025-10-01/20261011T181709_8585216a/`。147請求、0cachehit、147成功、3已知略過、0新增失敗；coverage_complete=false／history.success=false如實保留。146排名、25持股、cash109109400.00、NAV1000000000.00、差額0.00；demo_decision_ready=true、formal／submission仍false。原失敗run保留诊斷，沒有恢復舊raw來假裝冷啟動。
- Provider：依openai-docs技能與官方非互動／Structured Outputs文件及本機help核對，codex-cli0.145.0，node＋codex.js argv／shellFalse／STDIN、獨立cwd、忽略使用者MCP／開發文件與規則、關閉web／shell／apps／plugins等工具，發現工具或未知事件整次拒絕。220秒timeout殺自身程序樹；保存原始回覆、events／stderr、真實起訖／用量及完整輸入hash。原schema保留，本地完整驗證；遠端投影去未採用的uniqueItems／字串長度限制、const轉enum，仍獨立保存並hash，不放寬本地合約。
- Runner：新增decision_runner／decide-plan，最多兩次；只有已完成但格式／合約或財務不符可修正，服務／工具／逾時錯誤停止。凍結全部7個輸入hash、模型前後程式內容版本核對；可信metadata加入deepcopy執行context，原packet不改。只通過者封存demo D-Plan，失敗候選／回覆保留且不入帳。
- 本機模型設定不相容：首請求explicit gpt-6.1-sol被ChatGPT服務端400拒絕（unsupported），無草稿／用量，不算真實投資決策完成；失敗run `plans/2025-10-01/decision_20261011T182135_e508b83c/` 保留。只讀app-server model/list核對該登入實際預設gpt-5.6-sol，保存model_availability.json。用本次--model覆寫、不改全域設定；剩餘一次命令max-attempts=1完成如下，累計2個模型請求、1份成功決策，沒有第三次。
- 聚焦驗收：history人工2新增＋2既有PASS（5.490s），pipeline3mock PASS（0.106s），provider6mock PASS（最後0.154s），runner5mock PASS（0.484s）。共18項相關檢查，沒有全套或掃舊快取。另獨立核對當次7輸入hash、147請求／0命中、150來源及四檔排除；行情日期全部在九月。讀取診斷腳本首次誤用manifest.month，改用requested_month後核對通過，未改行情或核心。
- 真實結果：gpt-5.6-sol於18:23:14.797549～18:24:34.655385+08:00完成，input145146／output3976／reasoning232／cached0，服務端snapshot未知null，模型身份依据explicit CLI ID。25selections與25held_reviews全部keep、neutral／neutral／hold、cash_target0.1091094、區間0.105～0.115；模型自然選續抱，不強迫換股。1303理由為維持期初股數、首日未核實資料不貿然換股，反方指出動能轉負／排名118、續抱依據偏弱；保存原文供會議評估。
- 封存修正：自動流程將compiled再嵌套日期／run，Windows長路徑使code archive失敗；模型草稿／events／AgentResult均已保存。沒有重叫模型，沿同raw_response＋真實metadata用既有compile-plan，短output `shared_root/final` 離線恢復成功。之後修runner compiled固定在output_dir/compiled，不再嵌套decision run；OSError保存archive_or_io_failed且不重試。新增必要IO失敗／布局回歸，runner最終6tests PASS（0.589s），本批共19項相關檢查。原自動失敗report先備份，再記離線恢復與0新增modelcalls；原始模型資料不改。
- 最終計畫：`final/2025-10-01/20261011T182555_b8b2869e/D-Plan_DEMO_2025-10-01.json`，F04 schema／semantic／local全部true、issues空；2S／26O／25I、0decisions／0orders／25no_trade，cash109109400.00、NAV1000000000.00、fee／tax0。real_agent_decision=true／accepted_demo_plan=true，但formal_eligible=false／submission_ready=false，不是成交或正式資格通過。封存版本sha256:455d78cf0f69；其後runner路径修正不回寫已封存版本包。
- 最終獨立核對：10產物hash、36程式／配置／schema封存檔hash、metadata與真實AgentResult／log／用量／起訖相等、provider全部輸入hash前後相同、全部原持股覆蓋／0委託通過。離線重編plan與portfolio完全一致，validation仍PASS；沒有新行情或模型。頂層workspace更新模型原始回覆／結果／驗證／D-Plan位置，run_summary.json保存可讀驗收摘要。文件與checklist同步，未跑全套、未commit／push。
- 文件收尾：README／quickstart／工作流記錄真實結果與重跑方式；資料合約升1.23，更新實際provider與共享工作流，核心1.0／草稿2.0不變。git diff --check通過，README與新工作流未連到被忽略的快取；本機產物路徑以程式碼文字供IDE定位。
- 下一批：先整理架構／檔案與會議展示；如需驗證10/1效益、實際成交與逐日帳務，另取得下載範圍授權後才能抓10/1，再實作settlement及test_agent成果回顧。正式候選／流動性、point-in-time、實際庫存／費用取整仍未完成。

重跑入口（會重新呼叫模型，須留意本批額度已用完；不要當離線重播）：

```powershell
$env:PYTHONPATH = (Resolve-Path -LiteralPath 'src').Path
.\.venv\Scripts\python.exe -B -m etf_agent.cli decide-plan --packet data/cache/integrated_runs/2025-10-01/20261011T181709_8585216a/decision_input/2025-10-01/20261011T182031_5135f5cb/evidence_packet.json --output data/cache/integrated_runs/2025-10-01/20261011T181709_8585216a/plans --model gpt-5.6-sol --max-attempts 1
```

## 24｜弱期初持股、CSV檢查視圖與重新決策（2026-10-11）

- 授權：使用者直接要求將初始持股改成較弱股票，明確撤回「保留既有決策」，刪除舊決策後让程式自主產生新決策，並要求sub_agent結果輸出CSV供人工檢查；後續「繼續」延續本批。包含同範圍必要真實決策初次／至多一次修正，不強迫交易。仍不下載或讀10/1行情，不改40/25/35、不commit／push。
- 清理：先把7個絕對目標核對在專案data/cache內，以PowerShell原生Remove-Item刪 `decision_packets/2025-10-01`、`plans/2025-10-01`、`plan_examples/weighted_draft_fixture_2025-10-01.json`，以及cold shared root `20261011T181709_8585216a` 下的plans／final／decision_input／run_summary.json。沒有備份或保留舊模型回覆／D-Plan；九月market/windows/features/rankings、日曆、官方F08/F09與舊合約fixture保留。前面第21～23批是開發歷史，所列舊決策路徑現已不存在。
- 弱期初：新增account.build_weak_demo_account／write_weak_demo_account及CLI build-demo-account。弱僅指9/30三因子綜合排名末25（第122～146），不用10/1表現挑股；每股人工預算3600萬元、整張floor、cash=10億減全部前收股票市值。不更換缺價股票或補值；完整白名單／檔數／單股／現金及NAV核對失敗即阻擋。人工建構90%股票預算只服務demo，不是投資策略／官方配置要求。
- 實際新帳戶：覆寫同名 `tests/fixtures/account_demo_2025-09-30.json`，snapshot `DEMO_WEAK_20250930_NAV1B_03a1b24f856c`、日期9/30／demo／未reconciled。25股24檔動能負、22檔低於均線；股票892932500.00＋cash107067500.00＝NAV1000000000.00。建構、估值與初始CSV保存在sharedroot/initial_account/2025-09-30/20261011T183759_84fc3293/，初始CSV亦保留排名、三因子、價格、整張與來源版本。
- CSV：新reports.write_csv_view統一UTF8BOM、Decimal字串、bool小寫、未知None空欄、JSON陣列／字典可重現。data_agent候選data_candidates.csv／原缺件data_issues.csv；account_agent完整account_positions.csv／一行account_summary.csv；test_agent review_status.csv／review_recommendations.csv。無前績效時status=prior_run_missing、績效未知、建議只有表頭。JSON仍是主資料；CSV不回寫權重、股數、帳戶或策略。
- 主決策檢查：dplan writer另產agent_decisions.csv／orders.csv／portfolio_positions.csv／portfolio_summary.csv／validation_checks.csv，原持股與新股完整聯集、退出股target0保留、模型理由／反證／O引用、前收估金額／fee／sell tax及每項PASS/BLOCK可讀。無單亦產orders表頭，不造交易；5CSV納入最終15artifact hashes，JSON欄位合約不變。
- 共用流程：pipeline.prepare_cached與prepare-decision --workspace-root重用明確shared root，不HTTP或重算因子，換新account copy並清理舊模型／計畫索引。新輸入 `decision_input/2025-10-01/20261011T184109_4a9529e8/`，14檔／13hash；六CSV實際列數146／4／25／1／1／0，全部BOM與13hash獨立核對。rootworkspace保留九月資料，指向新四角色報告與CSV；新demo ready、NAV差0。
- 提示：原真實回覆把未核實正式資格當續抱的重要理由。明確澄清formal false阻擋正式提交，不單獨禁止demo買賣；每股需按价格因子與可替代候選比較，續抱須說明相對優勢／成本／反證，不指定一定換股或數量。禁止事後行情與工具的限制不變。
- 相關測試：account9 PASS（0.469s）、packet8 PASS（1.622s）、compiler既有6 PASS（修CSV摘要兼容後1.246s）＋新增2CSV PASS（0.422s）、cached pipeline新增2 PASS（根代理實跑0.278s），合計27。首次CSV writer假設held_tickers使舊人工packet出錯，改以核心account_snapshot.positions計數，原6再驗通過；未全套或掃全部cache。CSV驗收包含跨行／逗號理由、費用精確一致、退出保留與無單表頭。
- 執行：重新決策指定已核對可用gpt-5.6-sol、最多2次，只有新凍結資料／沒有舊決策輸入；初次即通過，沒有第二次。開發分工agent兩個在結束階段遭用量限制，由根代理接手完成測試／文件；開發工具狀態與投資provider實際回覆分開記錄。
- 真實結果：`plans/2025-10-01/decision_20261011T184244_64a7bd3d/`，gpt-5.6-sol實報input145401／output4204／reasoning703／cached0；模型前後輸入／程式hash相同。25檔held_reviews=15exit＋10keep，selections20=10keep＋10新買。自主risk_on／neutral／hold、cash_target0.12、區間0.115～0.125；25orders=15SELL_ALL／10BUY，10no_trade。例：6919退出194000股、2330新買76000股，沒有人工指定交易名單或手改股數。
- 封存：`plans/compiled/2025-10-01/20261011T184409_51450818/D-Plan_DEMO_2025-10-01.json`，版本sha256:61938e20777f，2S／36O／35I／25D／10no_trade／25orders。schema／semantic／local全部true、issues空，real_agent_decision／accepted_demo_plan=true，formal／submission=false。沒有再遇長路徑或離線人工恢復，沒有實際成交／入帳。
- 前收demo估算：sell534806700.00／buy520423650.00、fees1503703.24875000、tax1604420.10000，cash_after118342426.65125000、projected_NAV996891876.65125000、cash比11.8711396314%。初始25→目標20；NAV下降為前收假設下交易費稅，不是已驗證10/1報酬。
- 獨立核對：13輸入／15輸出／37程式封存檔hash、metadata對實際AgentResult／CLI log起訖與用量、11CSV的全部委託shares／價格／金額／逐筆費稅／現金、所有shared workspace路径存在、舊決策目標不存在全部通過。35列聯集包含15退出股target0，正持股20，首日建議header only；離線重編plan與portfolio完全一致。新run_summary.json與workspace更新初始持股CSV、模型、11CSV與新計畫，舊root摘要已替換。
- 收尾：README／account／quickstart／workflow補新實跑與離線準備入口，資料合約升1.24（核心1.0／draft2.0不變），checklist更新當前證據。仍未抓或讀10/1行情、未全套、未commit／push。下一步待使用者指示架構整理或封存後成交／效益驗證，不自行下載10/1。

## 25｜封存後test_agent隔離收益與全候選事後最佳化（2026-10-11）

- 授權：使用者直接要求test_agent取得10/1資料、先放隔離區、計算收益與最佳決策；日期指2025-10-01。澄清後明選完整146候選重選股票／股數，接受較長實作，並另同意新增SciPy。只供封存後評估，不修改原D-Plan／40-25-35／期初帳、不新呼叫投資模型、不commit／push。前批不取得T日限制直到本批才針對隔離評估解鎖。
- 閘門：核對rootworkspace real／accepted、兩manifest13＋15產物hash、37決策程式封存hash、模型／帳戶／workspace／兩manifest，合計73原檔；D-Plan與portfolio orders一致、日期相符、9/30股數×前收＋cash精確等於10億。原D-Plan仍為20261011T184409_51450818，不因事後結果回改。
- 修改：providers/daily.py單日TWSE MI_INDEX／TPEx dailyQuotes adapter與嚴格日期／欄位／單位、兩市场不混、精確元／股量值、50位VWAP、rawhash；evaluation.py純模擬與封存閘門；hindsight.py整數配置；evaluation_runner.py隔離下載／重播／版本與8CSV；test_agent.evaluate_trade_day與CLI evaluate-plan。不改核心1.0／draft2.0或首日previous_trade_review，新增獨立isolated_post_decision_evaluation報告1.0。
- 依賴：pyproject新增optional evaluation=[scipy>=1.13,<2]，本機經授權安装SciPy1.18.1／NumPy2.5.4。MILP文件以SciPy官方說明核對整數、time_limit、gap、求解狀態；不把先四捨五入線性解當作整數最優。
- 下載：封存閘門後默認沙盒curl7無法連官方；按工具权限流程重跑需提升權限命令，成功取得TWSE1308列、TPEx12000列，保存兩份raw於隔離 `20261011T190144_d44c411d`，實際成功HTTP2次。第一次TPEx主table.date為ROC114/10/01、空管理table無date，parser原只接受YYYYMMDD而拒絕；新增ROC嚴格轉換與非空缺日阻擋，沒有重新HTTP。恢復raw manifest時fetched_at／content_type／effective_url未知留null、source_metadata_recovered=true，HTTP200由解析前程式閘門確認；之後請求即时保存source sidecar避免資訊丟失。
- 可得資料：按原146候選篩选為98上市／48上櫃。3260官方T日收盤---／量0／金額0，不是一般missing；trading_status區分traded／no_trade／unknown，缺價均價仍null。完整候選146保留，3260原未持有所以MIP目標固定0、145可交易；不補价、不重查3718／7750／7769／7828。
- 模擬：固定原25orders，以官方精確amount／shares算VWAP，買賣fee0.001425、sell tax0.003，50位Decimal未取整，T收估NAV。缺成交不執行、不扣款且保留原股；缺持股期末估價總NAV／profit=null，known stock value另列。canonical fixture及原account_agent回報不改；另存AccountSnapshot1.0 status=simulated/demo=true/reconciled=false。
- 最佳化：全146 q/b/s整張整数与持有／買單／卖单binary，目標費後T收NAV；限制20–30正持股、≤30orders、同股不能双向、卖出≤初持、現金0–25%、233025%其餘10%。前收費後與T收費後兩種cash/caps均檢，前收目標股市值75–100%期初NAV、股數可由前收權重公式達成。最佳方案自选現金比例，不繼承原12%目標，沒有改策略；不含正式資格／流動性／證據鏈／投資主題的官方完成保證。HiGHS time_limit120、mip_rel_gap1e-8，status0且精確重驗才optimal_to_solver_tolerance，限時可行另標，其他solver失敗與Decimal違規拒絕。
- 實跑：先 `20261011T190347_89d2e89b` 得原收益但3260當一般缺價使全池best阻擋，補zero-trade狀態後 `20261011T190528_028cf8c1` 首次完整成功。補齊評估程式封存後最終 `data/cache/evaluation_quarantine/2025-10-01/20261011T190922_e164811e/` 離線重播，network_requests0/new_model_calls0；兩種simulation與best JSON同首成功完全一致。不掃其他快取、沒有重下載。
- 收益：不交易cash107067500、stock895395350、NAV1002462850、profit2462850、return0.00246285。原25筆全部有VWAP，20持股、cash118610864.463443753743596947、stock878986850、NAV997597714.463443753743596947、profit−2402285.536556246256403053、return−0.002402285536556246；fee1517797.867621913556、tax1619703.264310868547。相對不交易差−4865135.536556246256元；所有本批原plan財務檢查通過。
- Best：HiGHS status0/gap0/1node，146候選145可交易、30orders／20holdings；cash20337.947368109472、stock1017574650、NAV1017594987.947368109472、profit17594987.947368109472、return0.017594987947368109，solver上界1017594987.9473682、Decimal微差屬float表示。前收fee後cash比約2.636897%、implied cash target3.07359%，T收現金約0.00199863%。部分原股只留1張满足20檔，為事後數學解，不是可預測建議；無替代D-Plan。與原計畫NAV差19997273.483924355729元。
- CSV：8份UTF8BOM，market_quotes146／performance3／fills25／end_positions35／hindsight_ranking146／hindsight_orders30／hindsight_positions33／review_recommendations25。原退出及最佳退出0股仍在聯集；146 targetshares含3260=0保留best JSON。欄位為元／股／元金額與股，與舊行情閱讀CSV張／千元分開。
- 驗收：daily11 PASS（0.011s）＋evaluation12 PASS（2.347s）＋舊review4 PASS（0.001s），27相關檢查。正常VWAPfee/tax/NAV與逐單skip貢獻、缺交易仍保股／缺估值NAVnull、未封存/坏hash、跨日期／超賣／同股雙向拒絕、隔離目錄禁決策root、全池最佳／平價不交易／未知不縮池／no_trade保持0、求解限時不冒稱最優及8CSV／JSON／hash一致。獨立子代理核對首完整run所有量值與fee/tax、雙取價caps/cash、股數；根代理核對最終63產物hash含41評估程式／配置封存檔及原73hash、8CSV列數、財務JSON重播一致。版本sha256:86f79658b6b5，git diff --check PASS，未全套。
- 文件：新增docs/evaluation.md含實際收益、公式、8CSV、來源精度／恢復限制與offline重跑；README／quickstart／workflow改為封存後隔離現況，data_contracts1.25，checklist本批EVAL勾完成、正式LEDGER保持待辦。下一批可討論把10/1獨立simulated帳與檢討接到10/2決策，或按使用者需求架構整理；需另達成共識，不自動下載下一日、不回流改原決策。SQLite／重複入帳／官方核對、公司行動與正式取整仍未完成，formal／submission始終false。

## 26｜README架構、流程與逐檔閱讀入口（2026-10-11）

- 授權：使用者要求「這個先停在這」，改為整理README，須看見整體架構圖、連到說明文件的執行流程、每個檔案存什麼及怎麼用。本批只文件與必要本機預覽／導航核對，沒有繼續收益／交易功能、修改原始碼／參數／資料、搬移檔案、下載行情、投資模型呼叫或commit／push。
- README改為目的與狀態→架構圖／四角色→7步流程與輸入輸出→常用結果導航→專案目录與設定→環境→完成／待辦。過去第22～25批詳細故事從README移除，既有docs及development_notes仍保留原驗收紀錄。例：9/30排名／帳戶→凍結packet→真Codex權重→程式股數／D-Plan→封存後10/1隔離收益；沒有回流舊決策。
- 新docs/assets/architecture.svg提供可直接嵌入、放大與會議使用的圖；決策區與隔離評估區分開，標明日期、模型／程式責任、驗收hash閘門及待串接的下一日。sub_agents目前是函式分工，不冒稱各自真LLM；前日review首日仍missing，封存後evaluation另入口。
- 新docs/source_map.md逐檔說明94個實際檔案，包括34src Python、22tests、2fixtures、9官方、2internal schema、設定／提示／白名單、根目錄文件與docs／SVG；每檔有內容、CLI或呼叫者、對應說明。新docs/artifacts.md按市場／日曆／視窗／因子／排名／帳戶／packet／model／compiled／evaluation分列所有產物模式與用途，拆清相同metadata／workspace／manifest／review名稱及單位。
- 核對修正：日曆來源hash在calendar.json.sources，不造manifest；行情raw／monthly stem含月份；run_summary.json與model_availability.json是本次另存，不承諾CLI固定生成；fixture即使本地驗證通過亦只保存candidate；workspace scope可相同，需要stage／目錄判別。所有GitHub導航只連專案文件或原始碼，cache只示範目錄／檔名。
- 驗收：README／source_map／artifacts共278個本地連結與章節anchor無錯、94檔coverage無遺漏、無ignored cache導航；SVG XML有效、36文字節點、無script。以無畫面Edge將本機SVG轉暫存PNG檢查字體／箭頭，初次沙盒啟動失敗，依工具權限流程在沙盒外預覽成功，修正閘門文字上方箭頭線穿越。沒有安裝繪圖依賴或使用外部圖資；沒有新增無效測試或跑程式測試。
- 收尾：checklist DOC-26僅勾文件導覽，原功能待辦保留。使用者可用IDE Markdown預覽開README、點完整SVG放大、沿source_map／artifacts看逐檔說明；git diff --check核對後收尾。後续功能或實體目錄重整另待使用者指示。

## 27｜三角色資料夾、責任分離與 D-Plan Markdown（2026-10-11）

- 授權：使用者同意上一輪「先搬清楚歸屬模組／更新import／保持CLI與計算結果」整理批次，另指定test_agent負責新行情與昨日檢討、data_agent只算指標、account_agent估值，要求D-Plan除JSON亦有可讀MD。本批完成角色整理、離線介面分離與MD；每日增量庫／跨日入帳／次日回饋另列待辦，沒有新增外部依賴、行情下載、投資模型呼叫、策略／風控參數或commit／push。
- 歸屬：22既有Python檔搬到三角色與decision。data_agent/含agent、history_windows、features、ranking；account_agent/含agent與account；test_agent/含agent、history、evaluation／runner、hindsight、月／日官方providers。decision/含主模型providers、runner、portfolio、dplan、validation及新markdown。外層保留contracts／universe／coverage／calendar／reports／HTTP與主pipeline／evidence，新prices共用截止日讀價、paths統一專案根目錄；移除舊agent目錄三個生成pyc，沒有清理任何行情或封存快取。
- 介面：data.prepare_data(rankingpath,as_of,universe,price_context=None)不讀帳戶、不估NAV、不下載；account.prepare_account(accountpath,price_context,as_of)獨佔匯入／value_account／report_account。evidence讀同份行情上下文後組合，才補回packet1.0既有account_snapshot／account_valuation／held_positions與排名held／shares／weight欄位。九月重抓wrapper移到test_agent，pipeline及日期限制同步更新；官方schema／provider prompt／評估封存改用paths.project_root，避免搬檔後parents深度錯誤。
- MD：render_plan_markdown(result,packet,draft)為純閱讀視圖，原JSON金額／股數／權重直接渲染，含市場原理由／反證、完整持股／EXIT／KEEP、官方及原O引用、日期／demo／fixture／BLOCK與資料問題。writer保存同JSON基名.md，新增manifest.plan_markdown_file與workspace.files.plan_markdown，hash與CSV／JSON同列；renderer沒有新模型、IO或股份重算。新compiled共17檔／16產物hash；舊decision.md仍是模型提示。獨立子代理審查發現MD被套上_csv後綴的假索引，已改成只對.csv生成CSV索引並補斷言。
- 實際例：用明確指定的既有9/30排名／25原股／10億帳戶，比對整理前後packet逐欄完全相同，packet版本decision-packet-v1-c871b82cf0cf。固定舊模型草稿在記憶體離線重編，plan／portfolio／validation三份JSON與原值全相同；未產生新模型決策或回寫舊run。既有15退出／10新買／10續抱的10/1原計畫另產生 `data/cache/refactor_checks/batch27/D-Plan_DEMO_2025-10-01.md` 閱讀副本，25orders／35原新股票聯集；同目錄markdown_view_manifest記錄原來源hash、view_only=true、0網路／0新模型。原73凍結hash最後仍一致。
- 驗收：首次15個受影響測試模組111項PASS（31.847s）；搬價格視窗及新增shared MD聯動後，6個聚焦模組31項中30PASS，新增1項因測試用假code_version與writer真實封存版本不同而被metadata檢查阻擋。改為實際程式封存／仍用假provider後，僅重跑該項PASS（0.630s）；合計115項不同重點檢查皆通過，未重跑全套。41個模組匯入與CLI17命令help PASS；65份Python AST有效。正常估值、日期／NAV、缺行情保股與未知NAV、來源／hash、角色不讀帳戶、股數／風控、MD原理由／未知／BLOCK／escaping／hash／workspace皆有證據。沒有使用真模型替測試。
- 文件：README角色／目錄與SVG同步，source_map重整為主流程／每角色／共用表，104個实际倉庫檔案全有索引（42src／23tests）；新docs/daily_workflow有每日Mermaid、VWAP成交與收盤NAV、事後解只供檢討、共享資料與分批待辦。README／source_map／artifacts／daily_workflow共299個本地連結與anchor有效，無ignored cache導航；SVG XML有效／36文字節點／無script。更新account／workflow1.5／data_contracts1.26／quickstart與相關程式連結，官方來源不改。
- 下一批建議：離線使用既有10/1隔離行情併入共用歷史庫，並由account_agent承接原10/1計畫的simulated帳戶；建議SQLite（標準庫）＋JSON／CSV檢查視圖，合約與持久化另先確認。尚缺open／high／low輸出、跨月份視窗、去重／重複入帳防護、ready前日回顧與10/2固定輸入；不自動下載10/2、不把最佳化帳戶當原帳、不另呼叫模型。正式帳務／資格／提交仍false。

## 28｜README會議講解與版本提交（2026-10-11）

- 授權：使用者要求先把README整理成可看著講解設計，並明確要求commit／push、確認README最新。本批提交自3637d9f後累積且已授權的帳戶／真實決策／隔離評估／角色整理／文件與測試；不續作每日合併或跨日帳務，不新下載行情或呼叫投資模型。
- README：最前加入每日設計Mermaid圖、四步講解顺序（昨日檢討→更新指標與帳戶→主Agent決策→JSON／Markdown／CSV檢查）、10/2只能讀截至10/1的時間界線，以及目前9月資料→10/1真模型→25委託的實際展示。目標設計與已完成範圍分別標明，既有架構SVG／docs／檔案索引／使用方式保留。
- 驗收與提交：沿用第27批115項已通過的重要檢查、固定草稿plan／portfolio／validation完全相同與原73封存hash不變；本批不重跑策略或全套測試，只核對最新README、導航、diff與提交範圍。data/cache、.venv、金鑰與本機設定保持忽略，不納入提交。Git提交／推送結果以本批收尾的實際commit與遠端main核對回報為準。
