# 開發紀錄

更新：2026-10-11。此檔統一保存簡明的討論、決定、授權、驗收與下一步，不保存逐字對話。

## 合作方式與依據

- 目標：約 8 小時完成可開會討論的 ETF MVP，模組保留資料、因子、模型與 UI 的擴充邊界。
- 每批約 10～30 分鐘，先說明與討論，使用者明確同意後實作；每批完成展示結果，再討論下一批。第一批同意不授權後續階段。
- 已讀根目錄 `AGENTS.md` v1.0、`design1001.md` v0.3、`checklist.md`（2026-10-11），首輪已閱讀 F01～F09 九份官方來源，來源內容未修改。
- 官方要求以對應原文為準；策略權重、風控閾值仍待討論。下列 demo 數值與時間切分是專案示例，不能當成官方規則。

## 已討論的決定

| 討論 | 決定與理由 | 狀態 |
|---|---|---|
| 模組如何共用資料 | 六種核心合約集中定義；金額使用 Decimal，股數用整數，HTTP／SDK 不進核心 | 已實作合約 |
| 模型如何參與 | AgentDraft 只提出選股與理由，不接受 shares／orders；最終股數由程式計算 | 已實作合約與 provider 介面，未接模型 |
| 含既有持股的 demo 是什麼 | 模擬帳已持有 25 檔股票，股票市值 9,000 萬＋現金 1,000 萬＝NAV 1 億；可展示續抱與加減碼 | 已建人工測試帳，不是正式期初帳 |
| 帳務與行情如何保存 | 規劃 SQLite 保存帳務／索引，JSON／CSV 保存原始資料、清洗行情、因子與執行產物；方便本機檢查與備份 | 第 02 批已保存歷史樣本；SQLite／完整存檔流程尚未完成 |
| 股市資料如何取得 | TWSE／TPEx 各自的官方月報 adapter 記錄來源、單位、資料日與取得時間；不能把 latest 當成指定歷史日 | 第 02 批兩檔已連網實測成功，150 檔取得尚未完成 |
| 未來如何回測 | 保留原價／因子價格、資料日、known_at、fetched_at、hash 與版本；按時間切成 train／validation／test，留出較新測試期 | 已預留格式與切分檢查，未訓練或回測 |
| 討論紀錄如何維護 | 依使用者最新指示只保留本檔，合併原日記必要決定，避免重複維護 | 本次整併 |
| 上市／上櫃表格如何整理 | 原始來源分開，整理後以 market 區分的長表合併，便於因子分組與日期切片 | 第 03 批已同意並完成樣本匯出 |
| CSV 如何顯示單位與來源 | 成交量用張並保留小數，網址集中在 manifest；內部股數／官方 shares 用股，價格元／股、金額元 | 第 03 批 CSV 2.0；核心合約仍 1.0 |

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

## 未完成與下一批提案

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
