# 共用資料合約與功能導覽

文件版本：1.7｜更新：2026-10-11｜內部合約版本：1.0｜歷史閱讀 CSV 格式版本：4.0｜對應設計：[design1001.md v0.3](../design1001.md)

本文件說明各模組吃什麼資料、交出什麼結果，以及目前程式實際能做什麼。**資料合約**是模組共用的欄位、單位與檢查規則；定義合約不等於已完成抓取、計算或交易功能。六種核心合約集中在 [contracts.py](../src/etf_agent/contracts.py)，金額使用 `Decimal`，以 Python 標準庫的 `dataclass` 定義資料。HTTP、模型 SDK、檔案與資料庫操作留在各自模組。

以下功能區塊各自列出「目的與資料」「已實作檢查」「待完成」「程式位置」。日期與數值若標為 fixture，都是人工測試資料；下載的官方歷史行情另行保存，不會讓假帳變成官方帳。

## 目錄

- [流程與共通格式](#流程與共通格式)
- [行情與清洗](#行情與清洗)
- [如何解讀 prices.csv](#如何解讀-pricescsv)
- [帳戶與庫存](#帳戶與庫存)
- [因子與排名](#因子與排名)
- [Agent 草稿與模型介面](#agent-草稿與模型介面)
- [配置與風控](#配置與風控)
- [驗證與 D-Plan](#驗證與-d-plan)
- [研究切分與資料版本](#研究切分與資料版本)
- [CLI 與示例](#cli-與示例)
- [官方要求與未確認事項](#官方要求與未確認事項)
- [後續更新方式](#後續更新方式)

## 流程與共通格式

完整設計流程是：

```text
官方名單與行情 → adapter／清洗 → MarketSnapshot
                                      ↓
                           因子計算 → FeatureTable
                                      ↓
完整 AccountSnapshot ─────────────→ AgentDraft
          ↓                           ↓
          └──────────────→ 配置／風控 → PortfolioProposal
                                      ↓
                         股數／費用／D-Plan 編譯
                                      ↓
                              ValidationReport
                                      ↓
                             庫存核對與版本保存
```

圖中是模組責任與資料流，沒有表示整條流程已經實作。現有離線示例讀取人工準備的六種合約，不會自動完成中間的業務計算。

| 資料 | 格式與單位 | 例子 |
|---|---|---|
| 股票代碼 | 四位字串，不能先轉整數 | `"2891"` |
| 核心合約股數 | 整數，單位為股；持股列必須大於零 | `60000` 股＝60 張 |
| 閱讀 CSV 成交量 | 單位為張，1 張＝1000 股；用 `Decimal` 換算，保留小數，不取整 | `23022319` 股→`23022.319` 張 |
| 核心合約價格 | Python `Decimal`；JSON 保存十進位字串，單位為新臺幣元／股 | `"50.00"` 元／股 |
| 閱讀 CSV 價格 | 新臺幣千元／張；1 張＝1000 股，所以換算後數字恰與元／股相同 | `1165` 千元／張＝1,165,000 元／張 |
| 核心現金、NAV、成交金額 | Python `Decimal`；JSON 保存十進位字串，單位為新臺幣元 | `"10000000.00"` 元 |
| 閱讀 CSV 成交金額 | 新臺幣千元，原元值除以 1000 | `26647241918` 元→`26647241.918` 千元 |
| 比例、報酬、權重 | `0.04` 表示 4%；PortfolioProposal 權重為 Decimal／JSON 字串；AgentDraft 比例與因子值為 JSON 數字 | `"0.04"`、`0.04` |
| 資料日 | ISO 日期 | `"2026-10-14"`，fixture 假設日期 |
| 時間 | 帶臺北時區的 ISO 時間；目前合約要求 `+08:00` | `"2026-10-15T08:00:00+08:00"`，自訂測試截止 |
| 未知或缺失值 | 允許空值的欄位用 `null`，不編造 0、發布時刻或模型版本 | `"usage": null` |

**已實作檢查：** `Contract.from_dict()` 載入時拒絕未知欄位與缺少必要欄位；`.to_dict()` 將合約轉回可寫入 JSON 的資料。NaN／Infinity、布林值冒充整數、非整數股數、非法日期、無時區時間會被拒絕。額外欄位檢查也會攔下 AgentDraft 夾帶的 `shares`、`orders`，但不能替代白名單或官方交易驗證。

**程式位置：** [contracts.py](../src/etf_agent/contracts.py) 的 `_decode()`（第 22 行）、`_encode()`（第 95 行）、`Contract`（第 109 行）、`ContractError`（第 18 行）。核心合約包含 `contract_version="1.0"`；AgentDraft 的 schema 版本另存。

## 行情與清洗

### 目的與資料

`MarketSnapshot` 是**本次決策可以使用的行情包**。它保存決策日、前一交易日、資料截止時間、來源類型、資料版本，以及由多筆 `PriceBar` 組成的價量長表。同一股票可以有多個歷史交易日；同一快照的「日期×股票」不能重複。

例如 fixture 中的 2891 在 2026-10-14 的 `close_raw="50.00"`，只是人工測試價格。當假設決策日是 2026-10-15 時，這筆資料日期早於決策日；合約仍會檢查是否超過截止時間與是否有重複列。

重要欄位：

- `MarketSnapshot`：`snapshot_id`、`trade_date`、`previous_trade_date`、`snapshot_cutoff`、`data_origin`、`dataset_version`、`prices`。
- `PriceBar` 價量：`ticker`、`market`、`trade_date`、`open/high/low`、`close_raw`、`return_close`、`volume_shares`、`amount_twd`。
- `PriceBar` 來源與狀態：`source_key`、`known_at`、`fetched_at`、`raw_sha256`、`data_version`、`adjustment_status`、`price_valid`、`tradable`。

`close_raw` 保存未調整收盤價；`return_close` 預留計算報酬的價格，不是報酬率，詳見下方 CSV 欄位說明。`adjustment_status` 表示 `raw`、`adjusted` 或 `unresolved`，不能只因填了價格就宣稱已處理除權息、分割等公司行動。

### 合併表與單位邊界

**來源擷取與解析分開，清洗後的價量使用統一長表格式。** TWSE、TPEx 各自處理 API 欄位、日期與原始單位；標準結果以 `market` 保留市場，每列是一檔股票的一個交易日。匯出時依交易日合併上市／上櫃成每日表，另按股票產生每股月表，兩種視圖來自同一清洗結果。之後算動能／波動時按股票分組，做橫斷面排名或取回測某日資料時按日期選取；需要單看上市或上櫃時，再篩選 `market`。

合併不會消除來源口徑差異：TPEx 月報縮位且不含鉅額，TWSE 月報提供股／元並含鉅額。表中保留精度與來源引用，原始 JSON／原欄位 CSV 各自保存；不同統計範圍不能直接拿來作同一種精確成交均價。

閱讀 CSV 的成交量顯示張、價格顯示千元／張、成交金額顯示千元；核心 `PriceBar.volume_shares`、`Position.shares` 仍保存股，核心價格為元／股、金額為元。[F04 官方委託格式](../specs/official/04_D-Plan.schema_v4.2.json) 的 `shares` 最少 1000，且須為 1000 的倍數；它限制的是本競賽委託。成交行情可含零股，所以 CSV 成交張數必須保留小數，不能因委託整張而裁掉行情小數。

目前是**閱讀 CSV 格式 4.0，共 22 欄**，記錄在 manifest 的 `csv_format_version`；六種核心合約與 manifest 本身的 `format_version` 仍為 **1.0**。格式 2.0 已把股轉成張；3.0 明列 `*_ktwd_per_lot` 價格、`*_ktwd` 金額與均價，移除逐列原始雜湊；4.0 改為每日表與個股月表，並移除閱讀 CSV 的兩個原來源單位欄。讀舊 CSV 的程式須辨識版本、欄位與單位，不能直接把閱讀 CSV 當作 `PriceBar` JSON。

### 已實作檢查

- 價格必須大於零或為 `null`；成交股數／金額不能為負。
- 同時有最高與最低價時，最高不能低於最低，開盤／收盤須在範圍內。
- `price_valid=true` 必須有原始收盤價；`tradable=true` 必須有有效價格。這只是資料的一致性檢查，沒有查證官方停牌狀態。
- `MarketSnapshot` 不接受 T 日或未來行情；已填的 `known_at` 不可超過 `snapshot_cutoff`。
- 非 fixture 快照還要求每列有 `known_at` 與合法原始資料 hash。這不代表程式已核實其來源證據，呼叫端仍要提供真實可核查的資訊。

### 清洗原則與待完成

完整清洗設計在 [design1001.md §6.2](../design1001.md)。原則先固定，來源欄位與單位須用真實樣本驗證：

1. 股票代碼保留字串，TWSE／TPEX 由各自 adapter 解析後合表並保留 `market`；白名單外列不進候選池。
2. 民國日期轉 ISO 日期；清掉千分位逗號與空白；`--`、空字串轉 `null`，不轉成零。
3. 依來源確認單位，核心數量用股、金額用新臺幣元；閱讀 CSV 將量轉張、金額轉千元、價格轉千元／張，不裁掉張數小數。單位不明就停止，不猜；報表縮位不因換算而變精確。
4. 相同重複可以去重；同股同日衝突值保留原始證據並阻擋，不任選其中一筆。
5. 使用真實交易日曆，不把週末、休市或停牌填成假成交；不拿補值製造低波動。
6. 缺有效行情者不新買；既有持股仍保留在完整帳戶與風控中。公司行動未處理時，不把價格斷點當成選股訊號。

現有合約已檢查部分數字與時間規則，但尚未完成全市場清洗器、交易日曆、停牌／公司行動查證及完整資料品質報告。歷史下載樣本用來先驗證兩個市場的來源、欄位及日期；少量樣本成功不等於已覆蓋 150 檔或可直接回測。

官方歷史查詢入口：[TWSE 個股日成交資訊](https://www.twse.com.tw/zh/trading/historical/stock-day.html)、[TPEx 個股日成交資訊](https://www.tpex.org.tw/zh-tw/mainboard/trading/info/stock-pricing.html)。這兩個是供人查閱的官方網頁；程式實際請求 URL 必須跟原始回應一起保存，不能把最新行情入口當成已驗證的歷史 API。

### 本批歷史下載實測

自動請求 2025 年 9 月的上市 2330、上櫃 5274 個股月報，兩者均取得 HTTP 200 且各有 21 筆歷史交易日資料。請求與回應日期已核對，沒有把最新行情存成指定歷史月份。這些 OHLC 價格是真實官方歷史資料，與前述 fixture 假價格分開。

兩來源的量值不能直接視為相同口徑：

| 來源 | 原始數量／金額欄位 | 精度與成交範圍 |
|---|---|---|
| TWSE 月報 | 成交股數／成交金額 | 單位為股／元；報表註記包含一般、零股、盤後定價與鉅額交易 |
| TPEx 月報 | 成交張數／成交仟元 | 以整數張／仟元縮位；報表註記不含鉅額交易，換算值不能當成精確股數／元 |

因此 TPEx 樣本的 `PriceBar.volume_shares`／`amount_twd` 留空，另保存來源原始張／仟元與換算後的 reported 值及精度說明。這樣不會讓月報近似值被誤用為精確成交均價或帳務結算依據；後續需要另找精度與成交範圍符合用途的官方資料。

目前樣本保留 `known_at=null`、`return_close=null`、`tradable=false`、`adjustment_status=unresolved`：無法證明歷史公開時刻，不冒稱已完成調整價格或可交易狀態核實。它可供閱讀與下載測試，沒有放入過去的正式 MarketSnapshot、結算或完整回測。

取得方式使用 Windows 內建 `curl` 與系統 Schannel 憑證驗證。Python 3.14 的 urllib 在本機遇到 TLS `Missing Subject Key Identifier`，改用系統工具重試，沒有關閉憑證驗證或安裝套件。CLI 的 `--transport auto` 優先用既有 curl，沒有 curl 時才用標準庫 urllib；亦可明確指定工具。每個請求有 10 秒 timeout，沒有自動重試；已保存的月報可用下述 `history-export` 完全離線重輸出。

首次真實下載批次為 `20261011T122548_f1b87c04`，後續使用該批原始 JSON 離線重輸出成閱讀 CSV 2.0，再依使用者選定的千元／張單位整理為 3.0；本批由同一資料重排成每日／個股月 CSV 4.0。舊目錄已依使用者要求刪除；原始 JSON、原欄位 CSV 與來源紀錄完整保存在下方新版目錄，查看及重跑均使用新版。

### 如何解讀 prices.csv

CSV 使用 UTF-8 BOM，方便 Excel 顯示中文；空欄代表 `null`。新版每日表與個股月表使用相同 22 欄，原報表欄位 CSV 則保持來源單位與原值。

原根目錄 `prices.csv` 月合表已移除；現在以 `daily/<YYYY-MM>/<YYYY-MM-DD>_prices.csv` 保存當天所有已取得樣本股票的價量長表，另有 `monthly/<YYYY-MM>/<market>_<ticker>_<YYYY-MM>.csv` 個股月表。2025 年 9 月目前只有 2330、5274，每股 21 列；`TWSE` 表示上市，`TPEX` 表示上櫃。這些是歷史資料閱讀表，尚未完成可交易狀態、公司行動或歷史公開時間核實，也不是 150 檔完整資料。

`ktwd` 表示新臺幣千元，`lot` 表示張。這次完全離線整理，同一目錄改為 21 份日表與兩份個股月表，驗收後移除根目錄原本三份閱讀 CSV；實際產物在 `data/cache/history_sample/2025-09/20261011T125021_603f0054/`：

- [2025-09-01 每日價量 CSV（2 列、張／千元）](../data/cache/history_sample/2025-09/20261011T125021_603f0054/daily/2025-09/2025-09-01_prices.csv)。日表涵蓋此次樣本實際有行情的 21 日，各 2 列，合計 42 列；沒有填造休市或無行情日期。
- [TWSE 2330 月表（21 列）](../data/cache/history_sample/2025-09/20261011T125021_603f0054/monthly/2025-09/TWSE_2330_2025-09.csv)、[TPEx 5274 月表（21 列）](../data/cache/history_sample/2025-09/20261011T125021_603f0054/monthly/2025-09/TPEX_5274_2025-09.csv)。月表供個股歷史查閱，與日表是同一批 42 列的不同視圖，不能再合併算成 84 列。
- [TWSE 原報表欄位 CSV](../data/cache/history_sample/2025-09/20261011T125021_603f0054/source_csv/2025-09/TWSE_2330_2025-09_source.csv)、[TPEx 原報表欄位 CSV](../data/cache/history_sample/2025-09/20261011T125021_603f0054/source_csv/2025-09/TPEX_5274_2025-09_source.csv)。依月份分目錄、檔名加 `_source`，與清洗後的個股月表區分；由首次下載的 JSON 轉出，保留原欄位、字串及單位。
- [TWSE 原始 JSON](../data/cache/history_sample/2025-09/20261011T125021_603f0054/raw/TWSE_2330_2025-09.json)、[TPEx 原始 JSON](../data/cache/history_sample/2025-09/20261011T125021_603f0054/raw/TPEX_5274_2025-09.json) 與來源雜湊核對相同。
- [來源 manifest](../data/cache/history_sample/2025-09/20261011T125021_603f0054/manifest.json) 與[品質報告](../data/cache/history_sample/2025-09/20261011T125021_603f0054/data_quality.json)。manifest 保存來源網址、HTTP 狀態、原抓取時間、SHA-256、`data_version`、原始／整理後單位及成交範圍，標記 CSV 格式 4.0、零次網路請求。`daily_prices` 列出每個日檔、交易日與列數；`sources[].prices_csv` 指向各股月表。舊頂層 `prices_csv` 月合表索引已移除。`reexport_of` 的原 run ID／路徑是歷史紀錄，離線重輸出只需新版目錄內的 manifest 與 raw 檔案。
- [首次下載 manifest 原文](../data/cache/history_sample/2025-09/20261011T125021_603f0054/provenance/original_manifest.json) 保留原批次的完整來源紀錄。

新版目錄內的原始 JSON／原欄位 CSV 與首次下載逐位元相同，原抓取時間不變，可獨立使用。這是同一批歷史資料的新版閱讀格式，不是又一次真實下載。

| 閱讀 CSV 欄位 | 單位與用途 | 精度／例子 |
|---|---|---|
| `trade_date` | 行情所屬交易日 | `2025-09-01`，不是下載日期 |
| `ticker` | 四位股票代碼，當作字串讀取 | `2330`、`5274` |
| `market` | 來源市場 | `TWSE`＝上市、`TPEX`＝上櫃 |
| `open_ktwd_per_lot` | 開盤價，千元／張 | 2330 當日 `1150`＝每張 1,150,000 元 |
| `high_ktwd_per_lot` | 最高價，千元／張 | 2330 當日 `1165` |
| `low_ktwd_per_lot` | 最低價，千元／張 | 2330 當日 `1145` |
| `close_raw_ktwd_per_lot` | 未調整收盤價，千元／張 | 2330 當日 `1165`；不是 `1.165` |
| `return_close_ktwd_per_lot` | 預留計算報酬用價格，千元／張；不是報酬率 | 尚未核實除權息／分割等公司行動，樣本留空 |
| `volume_lots` | 已取得精確股數才換算成張 | TWSE 23,022,319 股→23,022.319 張；TPEx 月報留空 |
| `reported_volume_lots` | 報表揭示的成交量，換成張供閱讀 | TPEx 356 張→356，精度仍是原報表的整數張 |
| `amount_ktwd` | 精確成交金額，千元 | TWSE 26,647,241,918 元→26,647,241.918 千元；TPEx 月報留空 |
| `reported_amount_ktwd` | 報表金額換成千元供閱讀 | TPEx 1,785,269 仟元→1,785,269 千元，仍為縮位資料 |
| `avg_price_ktwd_per_lot` | 精確量值計算的當日成交均價，千元／張 | `amount_ktwd ÷ volume_lots`；TPEx 月報留空 |
| `reported_avg_price_ktwd_per_lot` | 報表量值相除的均價，千元／張 | TPEx `1785269 ÷ 356 = 5014.80056180`，只代表縮位報表近似值 |
| `exact_volume_amount` | 來源量值是否精確到股／元；為品質旗標，不是模型分數或可交易資格 | TWSE 月報 `true`；目前 TPEx 月報 `false`，用途見下節 |
| `source_key` | 原始資料來源代號 | 表示使用哪個官方來源，完整網址見 manifest |
| `known_at` | 有證據顯示這筆資料已公開可知的時間 | 未核實就留空；不能以下載時刻代填歷史發布時間 |
| `fetched_at` | 第一次取得這份原始回應的實際時間，含 `+08:00` | 本次重整理不改原抓取時間 |
| `data_version` | 此列原始來源的版本索引 | 同批 `market`＋`ticker`＋`data_version` 對回 manifest 的來源紀錄 |
| `adjustment_status` | 公司行動調整狀態 | `raw`＝原價、`adjusted`＝已調整、`unresolved`＝尚未核實；目前為 `unresolved` |
| `price_valid` | 價格欄位通過已實作的一致性檢查 | 不等於證明可交易或已處理公司行動 |
| `tradable` | 可交易狀態標記 | 目前未核實，維持 `false`，不是宣稱 2025-09 當時股票停牌 |

截圖中的 `source_volume_unit`／`source_amount_unit` 原本描述**原報表單位**，所以曾顯示「股／元」或「張／仟元」。CSV 4.0 已移除這兩欄，原單位統一放在 `manifest.sources[].units.source_volume`／`source_amount`，`source_csv` 則保持官方原欄位與單位；整理後表格只有張、千元／張及千元的數值欄。`exact_volume_amount` 的 true／false 仍保留，表示原量值精度，不能因改單位就把 TPEx 縮位數值當成精確資料。

例如 2330 在 2025-09-01 的收盤價為 `1165` 千元／張、成交量為 `23022.319` 張、成交金額為 `26647241.918` 千元。每張收盤價格與張數相乘，就是按收盤價估計的千元市值；當日成交均價則為 `26647241.918 ÷ 23022.319 = 1157.45255367` 千元／張，兩者用途不同。價格轉換公式為「元／股×1000 股／張÷1000 元／千元」，所以數字不變，欄名明確標示新單位。

TPEx 5274 同日收盤價為 `5015` 千元／張；報表揭示量 `356` 張、金額 `1785269` 千元。其 `reported_avg_price_ktwd_per_lot=5014.80056180` 是縮位報表的近似均價；精確 `volume_lots`、`amount_ktwd`、`avg_price_ktwd_per_lot` 仍留空，不能把近似值改寫成已核實的正式成交均價。

### 上櫃空值與 reported 報表量值

`reported` 表示「來源報表揭示的數值」，是本專案加入的欄名前綴。前面三欄與後面的 `reported_*` 來自**同一份官方月報、同一交易日與相同成交範圍**；分開保存的原因是能否確認量值精度。兩組用途如下：

| 精確量值欄位 | 報表量值欄位 | 差別 |
|---|---|---|
| `volume_lots` | `reported_volume_lots` | 前者由可核實的成交股數除以 1000；後者保存報表量換算成張，保留原揭示精度 |
| `amount_ktwd` | `reported_amount_ktwd` | 前者由精確元金額除以 1000；後者保存報表金額換成千元，換單位不恢復已省略的小數 |
| `avg_price_ktwd_per_lot` | `reported_avg_price_ktwd_per_lot` | 前者由精確量值相除；後者由報表量值相除，來源縮位時只代表估算均價 |

目前 TWSE 月報提供股／元量值，因此兩組數字相同。TPEx 月報只提供整數張／仟元，沒有足夠資料核實底層的逐股、逐元數值；[monthly.py](../src/etf_agent/providers/monthly.py) 的 `parse_table()` 因而採**本專案的保守精度政策**，將核心精確股數／元金額留空，精確均價也隨之留空。[history.py](../src/etf_agent/history.py) 仍把報表量值輸出至 `reported_*`，沒有丟掉成交資訊。這是目前 TPEx 月報來源的限制，不是所有上櫃資料都不精確。

以 5274 的 2025-09-01 原表為例：`成交張數=356`、`成交仟元=1785269`。閱讀 CSV 保存 `reported_volume_lots=356`、`reported_amount_ktwd=1785269`，估算均價為 `1785269 ÷ 356 = 5014.80056180` 千元／張。前三個精確欄位空白表示「此來源不足以提供精確值」，**不代表零成交、股票不能交易或 CSV 換算失敗**。也不要把空欄填 0，或直接複製 reported 值至精確欄。

已保存的 TPEx 回應沒有交代張／仟元的截斷或四捨五入方法，不能自行宣稱誤差小於一張／一千元；均價顯示 8 位小數也不會增加原始精度。TPEx 月報不含鉅額、TWSE 月報包含鉅額的統計範圍差異仍需另外核對，不能只看單位或精度。

### exact_volume_amount 對決策的作用

**本批評估後保留此欄位。** 它記錄來源量值精度，不是選股因子，也不是官方 D-Plan schema 的必填欄位。目前解析器依來源格式設定它，匯出 CSV／manifest 並顯示於 CLI；真實因子、配置與結算尚未實作，不能宣稱程式已依此旗標完成投資決策或正式驗證。

| 使用情境 | 是否受量值精度影響 | 建議使用方式 |
|---|---|---|
| `mom20`、`trend20`、`vol20` 等價格因子 | 不直接依賴此旗標或成交量值 | 用已核實的價格序列，不因 `false` 自動扣分或排除上櫃股票 |
| 成交量／金額因子與 `adv20` 流動性篩選 | 會；縮位與成交範圍可能影響接近門檻的判斷 | 是否接受報表估算、如何處理邊界需先決定；不能默默混用精確欄與 reported 欄 |
| 均價成交模擬、回測費用、現金／NAV 帳務 | 會；均價差異會傳入費用、現金與後續配置 | demo 可明示使用估算；正式結算須取得精確量值並核對官方統計口徑 |

上述流動性規則是設計草案中的自訂條件，不是官方要求此旗標。是否允許 reported 量值參與因子／篩選仍是後續批次要決定的使用政策，尚未實作。保留旗標能讓資料使用者判斷適用用途；若未來簡化閱讀表，可把它移至 manifest，但讀取器仍須帶回這份品質資訊。

`false` 不表示不能選上櫃，`true` 也不證明這一列量值非空、有成交、完整覆蓋白名單、符合時間截止或正式可提交。零量、缺值、公司行動、來源範圍與 `known_at` 仍需各自檢查；精度旗標不能取代資料驗證。

### return_close、known_at 與當日均價的用途

`return_close` 是核心合約中預留的「報酬計算用價格」，閱讀 CSV 對應 `return_close_ktwd_per_lot`。未來要用它計算動能或報酬時，需有已核實且不洩漏未來資訊的價格調整方法。報酬率本身才是兩期價格相除減一，例如 `P_t / P_(t-1) - 1`；此欄不是已算好的百分比。目前公司行動未核實，留空比直接複製收盤價可靠。

`known_at` 用於判定當時能否知道這筆資訊；`fetched_at` 是程式實際拿到資料的時間。2026 年下載 2025 年月報，不能直接證明 2025 年哪個時刻已公開相同版本。未來盤前決策要檢查 `known_at ≤ snapshot_cutoff`，回測也須尊重當時可知版本；目前未知留空，因此這份閱讀 CSV 尚不能直接作已驗證的歷史決策快照。

[F07 官方指南「orders」](../specs/official/07_D-Plan_guide_v4.2.md) 指出競賽以「當日成交金額÷成交股數」作成交均價，後續模擬成交與帳務會用到。這是按成交量加權的當日均價，不是開高低收四個價格的算術平均。T 日均價收盤後才能得知，不能用於 T 日盤前選股；取得資料仍須符合結算所需的交易範圍及精度，目前 TPEx 月報不能當成精確結算來源，TWSE 月報範圍也須與正式口徑核對。

CSV 的兩個均價欄位使用 `Decimal`、50 位計算精度，再以 `ROUND_HALF_UP` 顯示固定 8 位小數；量為零或缺量／金額時均價留空。這是本地閱讀格式決定，不是官方帳務取整規定。未來正式費用／結算須從原始精確量值重算，不應用已四捨五入的 CSV 均價代替。

### 來源追溯與離線重輸出

**閱讀 CSV 不逐列放 `source_url` 或 `raw_sha256`。** 雜湊不是選股因子，也不必放在分析表內；它用於核對原始回應未遭改動及辨識版本，因此仍保存在 manifest 與核心合約。來源網址、完整 SHA-256、原始 JSON 與原報表 CSV，可由同批 `market`＋`ticker`＋`data_version` 對回 `manifest.sources`。不要只搬走 CSV 而丟掉同批 manifest 與 raw 檔案。

`history-export` 從指定目錄的 manifest 與保存的 raw JSON 重建新版 CSV，先核對 SHA-256，再使用相同市場 adapter 解析；不用網路，也不把重輸出時刻當成新的抓取時刻。新 run 的 manifest 標記 `purpose=offline_cached_export`、`network_requests=0`，並以 `reexport_of` 記錄原批次。一般重跑不覆寫輸入目錄，核心合約與 fixture 不修改。

先前 CSV 3.0 依使用者要求直接替換三份閱讀 CSV，當時 manifest 標記 `purpose=offline_cached_csv_rebuild`、`network_requests=0`；保留原 `run_id`、`created_at`，另記 `csv_rebuilt_at`。`csv_rebuild_of` 記錄替換前 manifest 的雜湊及存檔位置 `provenance/csv_v2_manifest.json`，原 `reexport_of` 仍代表首次下載的來源關係。原始 JSON／原欄位 CSV 與 `provenance/original_manifest.json` 維持原文。

後續依使用者要求，原報表 CSV 移到 `source_csv/2025-09/`、檔名加 `_source`，內容不變。來源路徑以現在的 `manifest.sources[].source_csv` 為準，當次整理前 manifest 保存於 `provenance/source_layout_manifest.json`；該次只調整位置，CSV 仍為 3.0。一般離線匯出仍從 raw JSON 重建來源表，不把 source_csv 當因子輸入或信任已手動修改的來源表。

本批 CSV 4.0 就地整理日／月視圖，manifest 標記 `purpose=offline_cached_price_view_rebuild`、`network_requests=0`，另記 `price_views_rebuilt_at`；`price_views_rebuild_of` 保存前版 CSV 格式、manifest 雜湊及存檔位置 `provenance/daily_monthly_manifest.json`。不改原始 JSON、原報表 CSV、原下載時間、原批次 ID 或建立時間。品質報告記錄 21 份日檔、兩份月檔；舊路徑在 provenance 內是當時的版本紀錄，查閱目前產物應依現有 manifest 的新索引。

### 資料使用入口與每日／每月檔案

目前實作兩檔月報的來源保存、每日表與個股月表匯出；因子讀取器、計算、預測、每日抓取排程及下列額外資料入口尚未實作。因子／模型將透過共用合約讀資料，不直接解析原報表的中文欄位與單位。

| 資料 | 預計用途 | 目前狀態 |
|---|---|---|
| 清洗後的歷史價量 | 動能、均線、波動、成交金額篩選；20 日動能要同股 21 個有效交易日 | 目前只有兩檔各 21 列樣本，日曆／公司行動未核實 |
| `universe.csv` | 限定 F05 白名單、標示股票與市場 | 尚未產生；官方來源仍為 F05 |
| 交易日曆／公司行動資料 | 找前一交易日、檢查連續有效日期及調整價格 | 尚未接入，檔案格式待討論 |
| 大盤行情 | 市場研判與市場因子 | 尚未接入 |
| 法人、營收等資料表 | 新增這些因子時才加入，依公告與版本時間取用 | 未實作 |
| `FeatureTable`／排名產物 | 模型接收計算後的因子、排名與證據；研究模型另需標籤與時間切分 | 僅有共用合約／fixture，沒有真實計算或訓練 |
| `AccountSnapshot`／帳戶 JSON | 策略、配置及風控需知道完整持股與現金 | 僅有人工 demo／合約，尚無正式帳務 |

本批已同意將**每日表作後續核心讀取入口**，每股每月表作歷史查閱視圖，並完成兩種視圖的匯出。同一批 raw 經同一清洗結果產生兩種表，不重複抓取；後續讀取器只用一種入口，不把兩種表同時合併，避免同股同日重複。日表方便每日更新及橫斷面排名，但 20 日動能仍須讀同股 21 個有效交易日，不能只讀單日日檔。

目前樣本目錄內的路徑：

```text
monthly/2025-09/TWSE_2330_2025-09.csv          # 同股一個月每天的清洗資料
monthly/2025-09/TPEX_5274_2025-09.csv
daily/2025-09/2025-09-01_prices.csv           # 同一天此次已取得的樣本股票，目前只有兩檔
daily/2025-09/...                            # 共 21 個實際有資料的日期
source_csv/2025-09/*_source.csv              # 原報表字串與單位，供來源核對
```

本批從既有 42 列離線重排，得到兩份個股月表與 21 份日表，每日只有 2330／5274 兩列；不代表 150 檔完整可交易股票資料，也沒有建立真實每日抓取排程。真實每日更新、150 檔覆蓋、日曆與截止驗證另列批次。未來擴到白名單時，缺行情、停牌或尚未核實者需保留狀態／品質紀錄，不因資料不完整而默默從股票池消失。

盤前時間保留兩種不同意義：`trade_date` 是行情日，`known_at` 是有證據的公開可知時刻。若採「今日資料下一交易日使用」，可另增 `usable_from_trade_date` 作**自訂保守使用政策**；不能把 known_at 改成下一天或下一開盤時刻。使用日要依交易日曆、已完成資料及決策截止推導，遇休市或延遲公告須延後，不能固定日期加一。現在歷史 known_at 未核實，新增政策日期仍不能使資料通過正式快照驗證；此欄位與計算尚未實作。

每次重跑產生新的時間／隨機 ID 目錄，保留舊回應。失敗回應與原因記在 manifest；HTTP 錯誤或 HTML 不轉成行情。單一市場失敗時仍保留另一市場資料，但整次 `success=false`、CLI exit code 2，不能把部分成功當完整下載通過。

上述快取由 `.gitignore` 排除，連結是本機產物導覽；新 clone 沒有這些檔案，需先下載樣本才能離線重輸出。它不是已建好的帳務資料庫或研究資料集。

**下載、匯出與解析程式：** [history.py](../src/etf_agent/history.py) 的 `download_history_sample()` 負責兩檔樣本與產物保存，`export_history_sample()` 負責已存樣本的離線重輸出，`_write_prices()` 負責閱讀 CSV 單位轉換；[providers/http.py](../src/etf_agent/providers/http.py) 負責 HTTPS；[providers/twse.py](../src/etf_agent/providers/twse.py)、[providers/tpex.py](../src/etf_agent/providers/tpex.py) 各自建立官方歷史 URL 與讀取報表；[providers/monthly.py](../src/etf_agent/providers/monthly.py) 做日期、逗號、空值、單位及重複／價格檢查。這些來源原始欄位不進六種核心合約。

**程式位置：** [contracts.py](../src/etf_agent/contracts.py) 的 `PriceBar`（第 160 行）、`MarketSnapshot`（第 199 行）。

## 帳戶與庫存

### 目的與資料

`AccountSnapshot` 是**決策前完整帳戶**，包含現金、NAV（帳戶淨資產）、全部持股與核對狀態。每筆 `Position` 只有 `ticker` 和整數 `shares`。即使某檔股票缺行情或因子，也不能從帳戶裡消失。

重要欄位是 `snapshot_id`、`as_of_trade_date`、`cash_twd`、`nav_twd`、`positions`、`status`、`origin`、`origin_ref`、`reconciled`、`demo`。

帳戶狀態分成：

| 狀態 | 含義 |
|---|---|
| `demo` | 人工測試帳，不是官方期初帳 |
| `projected` | 依委託推估的成交後帳戶，尚未結算 |
| `simulated` | 依模擬成交得到的帳戶 |
| `official_confirmed` | 有實際核對來源、已核對的官方帳戶 |

### 已實作檢查

現金不得為負或大於 NAV，NAV 必須大於零；持股代碼不得重複，持股股數必須為正整數。`demo` 必須標記 `demo=true`、`reconciled=false`；`official_confirmed` 必須是非 demo、已核對且附 `origin_ref`。程式只檢查欄位一致性，沒有登入官方後台或確認該引用的真實性。

### 已有 demo 與待完成

現有 fixture 是 25 檔人工測試帳：2891 為 60,000 股×假價格 50 元＝300 萬元；其餘 24 檔各 58,000 股×假價格 62.50 元，合計 8,700 萬元。股票 9,000 萬＋現金 1,000 萬＝NAV 1 億元。

CLI 會使用 fixture 的前收重新核對這個等式，但 `AccountSnapshot` 本身沒有行情，因此不會自己重算 NAV。正式帳戶匯入、SQLite 帳本、成交／費用入帳、庫存更新、每日核對與重複入帳保護均尚待實作。SQLite 保存帳務／必要索引、JSON／CSV 保存行情與執行產物，是目前的儲存方向，還不是已建立的資料庫。

**程式位置：** [contracts.py](../src/etf_agent/contracts.py) 的 `Position`（第 224 行）、`AccountSnapshot`（第 234 行）；[cli.py](../src/etf_agent/cli.py) 的 `load_demo()` 負責跨合約檢查及 demo NAV 核對。

## 因子與排名

### 目的與資料

`FeatureTable` 是**股票因子與排名表**；`FeatureRow` 是一檔股票的計算結果。因子回答「這檔股票最近的數值特徵如何」，排名回答「和其他股票相比排在哪裡」，兩個步驟分開，因子函式不抓 API、不修改帳戶。

例如一列可保存 `ticker="2891"`、`values={"mom20": 0.04}`，表示 20 日動能為 4%；若無法計算，保存 `null`，並在 `missing_reasons` 填原因。這只是欄位解讀，不是本批已算出的真實因子。

- 表的版本欄位：`snapshot_id`、`dataset_version`、`feature_version`、`factor_profile`、`origin`。
- 列的內容：`ticker`、`window_start/end`、`values`、`missing_reasons`、`source_refs`、`observation_ids`、`eligible`、`rank`。

### 已實作檢查

同表股票不能重複；計算期間起訖不能顛倒；因子須有來源引用。缺失因子須有對應原因，排名須為正整數或空值，觀察 ID 須符合 O1～O999 格式。CLI 另檢查因子視窗不能延伸至決策日或未來。

### 待完成

現有 fixture 的因子與排名都是人工假值，`origin=fixture`。20 日動能、均線偏離、低波動、流動性篩選及加權排名還沒計算；需要至少 21 個符合條件的價格資料點與已核實市場交易日。O1～O25 只是 fixture 內部引用，還不是官方完整 source→observation 證據鏈。

新增法人或營收時，在資料 adapter 與因子計算處擴充，沿用 FeatureTable、配置、股數計算與帳務。因子啟用與權重應集中配置，不能逐股偷偷換權重。

**程式位置：** [contracts.py](../src/etf_agent/contracts.py) 的 `FeatureRow`（第 259 行）、`FeatureTable`（第 281 行）。

## Agent 草稿與模型介面

### 目的與資料

`AgentDraft` 是**投資決策模型提出的想法**，包含市場姿態、選股與每檔原持股的處理理由。它不包含最終股數或委託，也不能改帳戶。

| 草稿部分 | 主要內容 | 例子含義 |
|---|---|---|
| `market_proposal` | `regime`、`stance`、現金目標／區間、淨流向、依據與理由 | `cash_target=0.09` 是提議保留 9% 現金 |
| `selections` | 股票、`conviction`、觀察引用、理由／反證 | 選股信心 `1.2` 是內部配置提示，不是 120% 持股權重 |
| `held_reviews` | 每檔原持股的 `keep/rebalance/exit` 意圖、引用與理由 | 2891 `rebalance` 代表需要重新配置，不等於已下單 |

### 已實作檢查

草稿提案 20～30 檔，選股與原持股 review 各自不能重複；`conviction` 限 0.8／1.0／1.2；理由不能為空。現金目標須在 0～25%，區間須合法並包含目標。這些是內部草稿限制；正式持股數仍要按成交後正股數驗證。

`AgentDraft.validate_context()` 要由呼叫端傳入 `allowed_tickers`、`held_tickers`、`observation_ids`，再檢查候選池合法、完整且精確覆蓋原持股、觀察引用確實存在。現有 CLI 使用 fixture 的行情代碼作示例候選池，尚未自動載入完整 F05 白名單。

### 模型介面與待完成

`AgentProvider` 是共同呼叫介面（Protocol），目前只有宣告：

```python
generate(packet, draft_schema, run_dir) -> AgentResult
```

`packet` 是凍結的輸入資料包，`draft_schema` 是內部草稿格式，`run_dir` 是這次執行的紀錄目錄。`AgentResult` 保存草稿、`provider`、實際模型版本、起訖時間、用量，以及原始回應／日誌路徑。未知資訊留 `null`；fixture 不可冒稱真實模型版本或用量。

尚無實際 Codex／Claude provider、模型呼叫、完整決策 prompt 或凍結證據包。未來接 Claude 時實作新的 provider，維持 AgentDraft 輸出與相同下游風控；不把模型 SDK 放入配置或帳務。

**程式位置：** [contracts.py](../src/etf_agent/contracts.py) 的 `MarketProposal`（第 296 行）、`Selection`（第 316 行）、`HeldReview`（第 331 行）、`AgentDraft`（第 345 行）；[agent/base.py](../src/etf_agent/agent/base.py) 的 `AgentResult`（第 12 行）與 `AgentProvider`（第 31 行）。

**JSON 格式位置：** [agent_draft.schema.json](../specs/internal/agent_draft.schema.json) 只描述上述草稿，不是六種合約合集，也不是官方 D-Plan。已檢查 JSON 可讀與結構內容；目前示例執行 Python 合約檢查，未安裝／執行 JSON Schema 驗證套件。

## 配置與風控

### 目的與資料

`PortfolioProposal` 是**程式整理出的完整目標配置**，接收 AgentDraft 與完整 AccountSnapshot 後產生。它包含快照 ID、配置方法、現金目標及每檔股票的 `TargetWeight`。退出股票也要列出，權重為零，才能保留完整處理路徑。

例如 fixture 中 2891 的 `target_weight="0.04"` 是「目標占總 NAV 的 4%」；原先持有 3% 時，代表配置增加。它不是 4% 的買單，也不是模型直接指定的股數。

### 已實作檢查

各股內部權重在 0～1 且代碼不重複，股票權重加現金須**精確等於 1**。`validate_context()` 要求配置股票集合恰好等於「全部原持股∪本次選股」，退出股亦不可漏列。

`allocation_method` 可記錄 `fixture`、`equal_weight`、`capped_score_inverse_vol`；列有方法名稱不代表計算器已完成。目前示例固定是 `fixture`。

### 待完成

真正的等權／受限制配置、單股／產業／換手風控、最終持股數、費用、賣出可用股數、官方股數公式與委託生成都尚未實作。內部權重 0～1 的檢查不能替代官方個股上限。最終股數須由程式依前收、NAV、目標權重與實際庫存計算，模型不得覆寫。

以 demo NAV 1 億、假前收 50 元、目標 4% 手算，2891 目標為 80,000 股，比原先 60,000 股多 20,000 股；這只是解讀例子，現有示例不執行該股數推導、費用或成交。

**程式位置：** [contracts.py](../src/etf_agent/contracts.py) 的 `TargetWeight`（第 367 行）、`PortfolioProposal`（第 379 行）。

## 驗證與 D-Plan

### 目的與資料

`ValidationReport` 是**檢查結果單**，不是交易計畫本身。每筆 `ValidationCheck` 保存檢查 ID、`PASS/WARN/BLOCK`、是否通過、說明及相關資料 ID。報告另外保存檢查範圍、demo／formal 模式、官方規則確認、帳戶核對、真實 Agent 決策與 `submission_ready`。

`scope=contract_only` 表示只檢查內部合約；`dplan_local` 預留本地 D-Plan 檢查；`official` 預留官方檢查結果。後兩個名稱只是格式可接受的值，尚未有相應驗證器。

### 已實作檢查

檢查 ID 不可重複。若設 `submission_ready=true`，合約要求正式模式、非 contract_only、規則已確認、帳戶已核對、有真實決策、有檢查結果，且沒有失敗的 BLOCK。欄位保護不能替代實際驗證器，也不等於主辦方接受提交。現有 fixture 固定 `submission_ready=false`。

### 待完成

D-Plan 編譯器、[F04 官方 schema](../specs/official/04_D-Plan.schema_v4.2.json) 的套件驗證，以及完整引用鏈、股數、超賣、資金調度、現金／姿態、全組合限制等語意檢查尚未完成。實作依據是 [F07 D-Plan 指南](../specs/official/07_D-Plan_guide_v4.2.md)；內部合約不能任意加進官方 JSON 的欄位。

**程式位置：** [contracts.py](../src/etf_agent/contracts.py) 的 `ValidationCheck`（第 397 行）、`ValidationReport`（第 406 行）。

## 研究切分與資料版本

### 目的與資料

`DatasetSplitPlan` 保存日後回測／訓練的時間切分計畫。`train` 用來學習參數；`validation` 用來比較方法或調參；`test` 是預先保留、最後評估的較新資料。較新的期間不能全部訓練或反覆調參後仍聲稱是獨立測試。

主要欄位為 `dataset_version`、`train_start/end`、`validation_start/end`、`test_start/end`、`label_horizon_trading_days`、`gap_trading_days`、`final_test_locked`。

### 已實作檢查

三個期間須依時間排序、起訖合法且不重疊；標籤期間須為正整數，gap 設定至少等於標籤期間，最終測試期須標為鎖定。

fixture 的示例計畫如下：

| 期間 | 起訖日期 |
|---|---|
| 訓練 | 2020-01-01～2023-12-29 |
| 驗證 | 2024-01-15～2024-12-31 |
| 保留測試 | 2025-01-15～2026-09-30 |

示例標籤與 gap 均為 5 個交易日，這是合約解說用假設，並非已取得的歷史範圍或已定案研究設定。端點也還沒核對真實交易日。21 筆價格／約 90 天初次補抓是盤前因子需求，不足以替代長期訓練或回測資料。

### 當時可知資訊與待完成

行情採長表。官方修正同一天資料時，保留原始來源與新版本；不同 `snapshot_id`／`dataset_version` 可選不同已確認版本，同一快照不得混放同股同日的兩種值。

| 追溯欄位 | 含義 |
|---|---|
| `trade_date`／資料期間 | 內容描述哪一天或哪個期間 |
| `known_at` | 有證據顯示何時已公開可知；無法核實則空值 |
| `fetched_at` | 程式本次取得時刻，不能倒填成歷史時刻 |
| `raw_sha256` | 原始回應內容的雜湊，用來辨識版本；保存在核心合約／manifest，閱讀 CSV 不逐列顯示 |
| `data_version` | 每筆行情用哪一版本；搭配資料集、清洗、因子版本保存 |

今天下載某個歷史月報，只能證明今天拿到該回應，**不能直接證明當時已知內容或當時價格版本**。某月營收屬於 9 月，也不等於 9 月底已公告。歷史樣本的 `known_at` 若無證據應留空，現有非 fixture MarketSnapshot 會因此阻擋，不能為了通過合約而編造發布時間。

真正交易日 gap、標籤終點、排除跨界標籤（purge）、資料覆蓋率、測試集存取限制、滾動回測與訓練流程尚未實作。`final_test_locked=true` 目前只是配置檢查，沒有禁止程式讀取測試期的功能。

後續切分不隨機打散股票日資料；同一天股票用相同時間邊界。標準化或缺值處理參數只從訓練資料擬合。實際期間須依來源涵蓋範圍、標籤及獨立測試長度共同決定；目前 F05 名單也不保證可作無偏差的長期歷史股票池，須評估存續偏差與當時可投資範圍。

**程式位置：** [contracts.py](../src/etf_agent/contracts.py) 的 `DatasetSplitPlan`（第 425 行），以及前述 `PriceBar` 的時間／版本欄位。完整資料版本存檔流程仍待後續批次。

## CLI 與示例

### 現有示例如何運作

`contracts-demo` 讀取 [contracts_demo.json](../tests/fixtures/contracts_demo.json)，載入六種核心合約、DatasetSplitPlan、AgentResult 共八種資料，執行 JSON 往返與跨合約檢查，再印出摘要。

它會檢查行情／帳戶／因子的日期與快照 ID、資料版本、完整持股 review、配置覆蓋，以及「現金＋持股前收市值＝NAV」。這是共用格式的離線串接，不是因子→真實模型→D-Plan 的完整投資流程。

fixture 假設決策日為 2026-10-15、前日為 2026-10-14，截止時間是自訂測試值，尚未核對真實市場日曆。26 列行情是 25 檔前收，加上 2891 的 2026-10-13 一列，用來展示多日格式；沒有完整 21 日序列。帳戶、因子、草稿都是人工測試值；模型版本與用量為 `null`，沒有真實投資模型呼叫。下載的歷史 CSV 不會自動取代此 fixture。

### 重跑與驗收

在專案根目錄開 PowerShell，使用現有 Python，不需第三方套件：

```powershell
$env:PYTHONPATH = (Resolve-Path 'src').Path
python -B -m etf_agent.cli --help
python -B -m etf_agent.cli contracts-demo --fixture tests/fixtures/contracts_demo.json
python -B -m unittest discover -s tests -p test_contracts.py -v
```

第 01 批實測：help／demo exit code 0；八種資料 JSON 往返 PASS；25 檔股票市值 90,000,000.00 元＋現金 10,000,000.00 元＝NAV 100,000,000.00 元，PASS；30 項單元測試通過；缺 fixture 檔時 exit code 2 並輸出可讀錯誤。文件擴充本身不代表重跑以上測試，新的執行證據記錄在 [development_notes.md](../development_notes.md)。

歷史樣本下載指令（會連網）：

```powershell
$env:PYTHONPATH = (Resolve-Path 'src').Path
python -B -m etf_agent.cli history-sample --month 2025-09 --output data/cache/history_sample
```

`--month` 只接受已完成月份；目前固定下載 2330／5274，沒有批次下載 150 檔。成功回傳 exit code 0；任一來源失敗或輸入錯誤回傳 2。輸出顯示每日／月表目錄、日檔數、第一個日檔及 manifest 路徑。程序使用真實歷史行情，但不呼叫投資模型、不計算因子或更新帳戶。

已下載的歷史樣本可完全離線重輸出為新版張／千元 CSV，包含當日均價（不連網）：

```powershell
python -B -m etf_agent.cli history-export --manifest data/cache/history_sample/2025-09/20261011T125021_603f0054/manifest.json --output data/cache/history_sample
```

此指令從目前保留的新版目錄讀取來源資料，再建立新批次並印出每日／月表目錄、日檔數、第一個日檔及 manifest 路徑，不需要已刪除的舊目錄。缺少 manifest／raw 檔、SHA-256 不符、錯月／錯股票或來源失敗時，不視為成功；實際錯誤原因保存或顯示供核對。它是對已取得真實資料的離線重輸出，不是本次又抓到最新資料。

離線檢查指令不連網，fixture 明示合成值；包含來源格式、錯月／股票、單位／精度、空值、衝突、價格錯誤、下載失敗、版本保存，以及閱讀 CSV 張／千元換算、均價與離線來源核對：

```powershell
python -B -m unittest discover -s tests -p 'test_*.py' -v
```

相關程式在 [test_history.py](../tests/test_history.py)，本批實際測試數與結果記錄在開發紀錄。

**程式位置：** [cli.py](../src/etf_agent/cli.py) 的 `load_demo()`、`demo_summary()`、`main()`；相關測試在 [test_contracts.py](../tests/test_contracts.py)。未來 UI／排程應呼叫核心模組，而不是複製業務邏輯到畫面。

## 官方要求與未確認事項

官方內容保留 [specs/official/](../specs/official/) 中 F01～F09 原檔。六種內部格式、資料切分、demo 數值與儲存方式是專案實作決定，不是官方規定。因子權重、產業上限、換手限制等設計參數仍須按批次討論，不能因出現在設計文件就當成已同意或已驗收。

正式期初帳戶、截止時刻、合法資訊區間、費用取整、公司行動、無成交與現金比例口徑等仍待確認。缺必要規則、真實模型決策或官方庫存核對證據時，不能宣稱正式可提交；schema 通過也不等於語意或正式資格通過。

## 後續更新方式

每次更新直接整理相應功能區塊，避免把所有新內容堆到文末：

1. 先更新「目的與資料」及具體例子；有合約變更時明列版本與相容性影響。
2. 「已實作檢查」只寫可對照程式的行為；介面宣告、fixture、快取 replay、真實執行分別標明。
3. 完成實作後移除對應的待完成描述，補來源、產物連結、必要驗收及可重跑指令；尚未完成的項目保留。
4. 每個區塊維持相對程式連結與類別／函式名；程式改動後更新旁註行號。這裡的行號是本版導覽，名稱是查找依據。
5. 說明文件寫當前行為，討論／授權／驗收歷史統一放 [development_notes.md](../development_notes.md)，完成證據更新 [checklist.md](../checklist.md)，不重複維護日記。
