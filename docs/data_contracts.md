# 共用資料合約與功能導覽

文件版本：1.17｜更新：2026-10-11｜內部合約版本：1.0｜歷史閱讀 CSV 格式版本：4.0｜對應設計：[design1001.md v0.3](../design1001.md)

本文件說明各模組吃什麼資料、交出什麼結果，以及目前程式實際能做什麼。**資料合約**是模組共用的欄位、單位與檢查規則；定義合約不等於已完成抓取、計算或交易功能。六種核心合約集中在 [contracts.py](../src/etf_agent/contracts.py)，金額使用 `Decimal`，以 Python 標準庫的 `dataclass` 定義資料。HTTP、模型 SDK、檔案與資料庫操作留在各自模組。

以下功能區塊各自列出「目的與資料」「已實作檢查」「待完成」「程式位置」。日期與數值若標為 fixture，都是人工測試資料；下載的官方歷史行情另行保存，不會讓假帳變成官方帳。

## 目錄

- [流程與共通格式](#流程與共通格式)
- [官方股票白名單](#官方股票白名單)
- [每日行情覆蓋與缺件報告](#每日行情覆蓋與缺件報告)
- [行情與清洗](#行情與清洗)
- [F05 全股票歷史月報](#f05-全股票歷史月報)
- [官方排程日曆與價格視窗](#官方排程日曆與價格視窗)
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

## 官方股票白名單

### 目的與資料

白名單回答「本競賽允許哪些股票」，供後續抓取行情、形成候選池與驗證選股共用。[F05 官方 PDF](../specs/official/05_stock_universe_150_v1.pdf) 是來源，衍生檔為 [data/universe.csv](../data/universe.csv)，包含 150 檔：100 檔上市 `TWSE`、50 檔上櫃 `TPEX`。這份資料包含股票身分，沒有價格、持股或買賣建議；列入白名單也不代表當日有完整行情或可立即交易。

CSV 只有三欄，按官方內容保存；代號保留字串，不轉整數：

| 欄位 | 含義 | 例子 |
|---|---|---|
| `ticker` | 四位 ASCII 數字字串 | `"2330"`、`"5274"` |
| `name` | 官方股票名稱 | `台積電`、`信驊` |
| `market` | 市場，限 `TWSE`／`TPEX` | 2330 為 `TWSE`，5274 為 `TPEX` |

設計 §6.1 的 `industry`／`theme_tag` 是待討論的擴充欄位；本批不以名稱猜產業，也不把自訂主題標籤當成官方資料。

[data/universe.manifest.json](../data/universe.manifest.json) 保存來源檔位置、來源版本、PDF 與 CSV 的 SHA-256 雜湊及股票數；`extraction` 另記錄各頁市場檔數及每檔來源頁碼。雜湊用來辨識這次整理所依據的內容，版本為 `F05-v1-<CSV 雜湊前 12 碼>`。官方原檔保留不改；CSV 與 manifest 是可重新核查的衍生產物。F05 的適用起始日期未確認，`official_source.effective_from_trade_date` 留空，不能以生成日期代填。

### 載入與已實作檢查

`load_universe(csv_path, *, manifest_path=None)` 讀取白名單並回傳 `Universe`；未另指定 manifest 時，使用同目錄、同名主體的 `.manifest.json`。例如 `data/universe.csv` 對應 `data/universe.manifest.json`。manifest 內的 CSV 與 PDF 路徑以 manifest 所在目錄為基準。使用現有 Python 標準庫，載入與檢查均不連網。

載入時檢查 CSV 標頭恰好是 `ticker,name,market`、代號為四位 ASCII 數字、名稱非空、市場合法，並拒絕重複代號，即使它被分別列在兩個市場也會阻擋。另要求 150 檔與 100／50 市場分布，核對 CSV、來源 PDF 的雜湊及 manifest 版本；缺檔或資料不符時回報錯誤，不自動改寫來源或名單。

`Universe` 提供下列重用入口：

| 入口 | 用途與例子 |
|---|---|
| `stocks` | 全部 `Stock`，每筆只有 `ticker`、`name`、`market` |
| `allowed_tickers` | 合法代號集合，供後續候選池／驗證共用 |
| `lookup(ticker, *, market=None)` | `lookup("2330", market="TWSE")` 回傳台積電；代號未知或市場不符時阻擋 |
| `select_market(market)` | `select_market("TPEX")` 取得 50 檔上櫃股票 |
| `universe_version` | 本份名單的可重現版本 |
| `source_path`／`source_sha256`／`csv_sha256` | 對回來源與衍生檔內容，供產物紀錄引用 |

在專案根目錄設定 `PYTHONPATH` 後，可直接使用：

```python
from etf_agent.universe import load_universe

universe = load_universe("data/universe.csv")
stock = universe.lookup("5274", market="TPEX")
# stock.name 為「信驊」；universe.allowed_tickers 可供後續模組使用。
```

### 重跑與待完成

白名單 CLI 檢查命令可重跑，不安裝套件、不抓行情、不呼叫模型：

```powershell
$env:PYTHONPATH = (Resolve-Path 'src').Path
python -B -m etf_agent.cli universe-check --universe data/universe.csv
python -B -m etf_agent.cli universe-check --universe data/universe.csv --manifest data/universe.manifest.json --json
python -B -m unittest discover -s tests -p test_universe.py -v
```

檢查成功回傳 exit code 0，顯示總數、市場分布、來源版本與抽查股票；`--json` 輸出機器可讀摘要。缺檔、CSV／manifest 或雜湊錯誤回傳 exit code 2。實際驗收結果統一記於 [development_notes.md](../development_notes.md)。

白名單已接入下方的離線每日行情覆蓋檢查、`history-universe` 全股票月報下載，以及沿用價格視窗報告的原價因子分析，尚未串接 Agent 或風控。`history-sample` 仍只下載 2330／5274，`contracts-demo` 的候選池仍來自人工 fixture 行情。後續應由組合流程明確傳入這份白名單；不會只因存在 `allowed_tickers` 就自動完成全流程限制。

F05 是競賽 v1 股票池，不是已核實各歷史日期的可投資股票池。長期回測若固定沿用這份名單，仍須評估存續偏差、股票上市時間與當時適用名單；每日最新行情更新、交易日曆、停牌／公司行動與歷史公開時刻也另待實作。

**程式位置：** [universe.py](../src/etf_agent/universe.py) 的 `Stock`、`Universe`、`load_universe()`；[cli.py](../src/etf_agent/cli.py) 的 `universe-check` 命令；相關行為測試見 [test_universe.py](../tests/test_universe.py)。

## 每日行情覆蓋與缺件報告

### 目的與輸入

覆蓋率回答「指定日期的日表包含 F05 的幾檔股票，還缺哪些」，並將股票身分、有效價格與原有可交易旗標分開統計。它供後續補資料及檢查資料範圍使用，不計算因子、不改寫行情或帳戶，也不產生正式 `MarketSnapshot`。

`check_daily_prices(csv_path, *, trade_date, universe)` 接收一份 CSV 4.0 日表、明確指定的資料日期及已核對來源的 `Universe`，回傳覆蓋報告字典。只讀每日表，不再合併同資料的個股月表或 `source_csv`。日期由 `trade_date` 指定，程式不根據檔名猜日期，也不推定它是合法交易日。

例如 `2025-09-01` 日表只有 2330／TWSE、5274／TPEX 兩列，且身分與格式均正確時，報告應為 `present_count=2`、`expected_count=150`、`missing_count=148`、`coverage_percent="1.3333"`。其中上市缺 99 檔、上櫃缺 49 檔；兩列都有有效收盤時 `valid_price_count=2`，原有 `tradable=false` 則使 `tradable_flag_count=0`。這是對競賽 v1 名單的歷史資料範圍比較，不表示 F05 在 2025-09-01 已生效。

### 如何計數與核對

- **已取得 `present_count`**：同指定日期、代號在白名單、所屬市場正確且沒有同日重複的股票列。價格空白或 `price_valid=false` 仍可算已取得；其他數值／狀態錯誤會另列 `errors`，所以已取得數不能代替輸入檢查。
- **有效價格 `valid_price_count`**：已取得列中，`price_valid=true`、原始收盤為正且價格一致性檢查通過者。它不要求 TPEx 月報提供精確成交量／金額，也沒有查證停牌或公司行動。
- **原有可交易旗標 `tradable_flag_count`**：僅數已取得列原本的 `tradable=true`，程式不重新判定正式可交易資格。
- **缺件 `missing_count`**：白名單中未計入已取得的股票數。錯日期、錯市場、白名單外列都排除；同日同股票即使兩列完全相同，也整組排除，不挑一列採用。這是本檢查器的保守政策，與未來完整清洗器的去重設計分開。

檢查器要求 CSV 標頭恰為格式 4.0 的 22 欄、順序相同，列欄位數正確；數值使用 `Decimal`，拒絕 NaN／Infinity、非正價格與負量值。另核對 OHLC 高低範圍、三個 true／false 旗標、來源與版本欄、調整狀態、時間的 `+08:00` 時區，以及有效價格／可交易旗標的基本一致性。零成交量搭配正成交金額也列為錯誤。這些是本機格式與一致性檢查，沒有比對官方原始行情。

TPEx 的精確 `volume_lots`、`amount_ktwd`、`avg_price_ktwd_per_lot` 空白是合法缺值，仍保留 `reported_*` 及 `exact_volume_amount=false`；不以報表估算填入精確欄。`known_at` 空白、`adjustment_status=unresolved`、`tradable=false`、未核實量值精度及缺收盤等限制記為 `warnings`。程式不補值、不編造公開時間，也不因 warning 把上櫃股票移出白名單。

### 如何解讀報告

| 報告欄位 | 解讀 |
|---|---|
| `trade_date`／`row_count` | 要檢查的資料日期／實際讀到的非空資料列數，列錯誤也保留在列數中 |
| `expected_count`／`present_count`／`missing_count` | 白名單檔數／符合身分與唯一性條件的已取得數／仍缺股票數 |
| `coverage_percent` | `present_count ÷ expected_count × 100`，百分比保存為十進位字串，顯示 4 位小數；此取整只供報告顯示 |
| `valid_price_count`／`tradable_flag_count` | 有效價格數／原列可交易旗標數；兩者不能直接當成正式可選股數 |
| `by_market` | `TWSE`／`TPEX` 各自的白名單、已取得、有效價格及缺件數 |
| `present_tickers`／`missing_tickers`／`missing_stocks` | 已取得代號、缺件代號與缺件股票的代號／名稱／市場 |
| `duplicate_tickers`／`unexpected_tickers` | 同日重複代號／白名單外或代號格式錯誤的值；錯市場另見 `errors` |
| `input_valid`／`errors`／`warnings` | 無列錯誤時為 true；errors 保存列號、代號與原因，warnings 保存尚未核實的限制及相關代號 |
| `coverage_complete` | 沒有缺股票且沒有列錯誤時為 true；有完整覆蓋仍可能含缺價格與 warnings |
| `input_csv`／`input_csv_sha256` | 此次日表的完整路徑與內容雜湊，供辨識受檢版本 |
| `universe_version`／`universe_csv_sha256`／`universe_source_sha256` | 對應 F05 白名單版本、衍生 CSV 與官方 PDF 的雜湊 |
| `checks_not_performed`／`submission_ready` | 列出未檢查項目；此報告的 `submission_ready` 始終為 false |

本批沒有沿 `source_key`／`data_version` 回查歷史下載 manifest 或 raw 行情，因此日表雜湊只辨識輸入內容，不能證明行情原始來源或正確性。交易日曆、盤前截止、歷史公開時間證據、公司行動、21 日因子視窗、歷史時點股票池及帳戶／正式交易驗證仍待實作；完整覆蓋不能代替這些檢查。

### 保存、重跑與失敗行為

`write_coverage_report(report, output_dir)` 為每次檢查建立 `output_dir/<資料日期>/<時間_隨機識別碼>/`，回傳 `run_dir`、`report_json`、`report_md`、`missing_csv` 四個路徑。目錄內有三檔：

| 檔案 | 用途 |
|---|---|
| `coverage.json` | 完整欄位、錯誤、限制、輸入／白名單版本，以及本次 `created_at`／`run_id`；報告格式版本為 1.0 |
| `coverage.md` | 可直接閱讀的總數與市場摘要；完整錯誤見 JSON，Markdown 至多展示前 20 筆列錯誤 |
| `missing_stocks.csv` | 缺件股票，只有 `ticker,name,market` 三欄，按代號排序；沒有缺件時仍保留標頭 |

預設輸出在 `data/cache/coverage/`，和下載 run 分開；每次是新版本，不覆寫輸入日表、既有報告或歷史 manifest。本機快取不由 Git 追蹤。使用現有 Python 標準庫，不安裝套件、不連網、不呼叫模型：

```powershell
$env:PYTHONPATH = (Resolve-Path 'src').Path
python -B -m etf_agent.cli prices-check --prices data/cache/history_universe/2025-09/20261011T145716_6e56c903/daily/2025-09/2025-09-01_prices.csv --date 2025-09-01 --output data/cache/coverage
python -B -m unittest discover -s tests -p test_coverage.py -v
```

`--prices` 與 `--date` 必填；`--universe` 預設 `data/universe.csv`，可用 `--universe-manifest` 指定白名單來源紀錄；`--output` 預設 `data/cache/coverage`。加 `--json` 可輸出機器可讀結果及報告路徑。

日表格式無列錯誤時，CLI 回傳 exit code 0，即使只有 2／150 檔也會保存報告並顯示 `coverage_complete=false`。有錯日期／市場／重複或數值等列錯誤時，仍保存診斷報告，回傳 2。缺檔、標頭不符、CSV 無法解析或白名單載入失敗時，直接回傳 2，不製造看似有效的覆蓋報告。成功讀取與完整覆蓋分開判斷，日後選股不能只看 CLI exit code。

第 09 批接續驗收已實際執行全套 119 項測試並通過，其中覆蓋檢查為 28 項。當時真實歷史樣本日表的 CLI 實測另存 2025-09-01 閱讀報告（本機路徑 `data/cache/coverage/2025-09-01/20261011T144802_4463a889/coverage.md`）、完整 JSON（本機路徑 `data/cache/coverage/2025-09-01/20261011T144802_4463a889/coverage.json`） 與 148 檔缺件 CSV（本機路徑 `data/cache/coverage/2025-09-01/20261011T144802_4463a889/missing_stocks.csv`）。結果為取得 2／150、有效價格 2、原列 tradable=true 為 0，並保留四類限制及 submission_ready=false。當時全部 21 個日表、42 列也已離線核對相同覆蓋結果；沒有下載新行情，測試中的 150 檔完整列仍是人工 fixture。

舊報告與原輸入路徑保留為當時證據，原樣本目錄已清理。要重跑 2／150 的樣本覆蓋結果，可將上述 `--prices` 改為 `data/cache/history_universe/2025-09/20261011T145716_6e56c903/provenance/history_sample/input/2025-09-01_prices.csv`；這份 保存的兩檔輸入（本機路徑 `data/cache/history_universe/2025-09/20261011T145716_6e56c903/provenance/history_sample/input/2025-09-01_prices.csv`） 保留原文與 hash。日常分析用全股票日表，上述目前指令會核對 146／150。

**程式位置：** [coverage.py](../src/etf_agent/coverage.py) 的 `check_daily_prices()`、`write_coverage_report()`；[cli.py](../src/etf_agent/cli.py) 的 `prices-check` 命令；相關行為測試見 [test_coverage.py](../tests/test_coverage.py)。授權、實測與下一步記於 [development_notes.md](../development_notes.md) 第 09 批。

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

現有合約已檢查部分數字與時間規則；月報 adapter 可供兩檔樣本與 F05 全股票下載共用，官方排程及價格視窗另有檢查，但尚未完成決策快照、臨時休市／個股停牌／公司行動查證及完整資料品質驗證。歷史下載的來源／格式檢查與逐日覆蓋，不等於已核實實際交易日期完整或可直接回測。

官方歷史查詢入口：[TWSE 個股日成交資訊](https://www.twse.com.tw/zh/trading/historical/stock-day.html)、[TPEx 個股日成交資訊](https://www.tpex.org.tw/zh-tw/mainboard/trading/info/stock-pricing.html)。這兩個是供人查閱的官方網頁；程式實際請求 URL 必須跟原始回應一起保存，不能把最新行情入口當成已驗證的歷史 API。

### 兩檔歷史樣本實測

自動請求 2025 年 9 月的上市 2330、上櫃 5274 個股月報，兩者均取得 HTTP 200 且各有 21 筆歷史交易日資料。請求與回應日期已核對，沒有把最新行情存成指定歷史月份。這些 OHLC 價格是真實官方歷史資料，與前述 fixture 假價格分開。

兩來源的量值不能直接視為相同口徑：

| 來源 | 原始數量／金額欄位 | 精度與成交範圍 |
|---|---|---|
| TWSE 月報 | 成交股數／成交金額 | 單位為股／元；報表註記包含一般、零股、盤後定價與鉅額交易 |
| TPEx 月報 | 成交張數／成交仟元 | 以整數張／仟元縮位；報表註記不含鉅額交易，換算值不能當成精確股數／元 |

因此 TPEx 樣本的 `PriceBar.volume_shares`／`amount_twd` 留空，另保存來源原始張／仟元與換算後的 reported 值及精度說明。這樣不會讓月報近似值被誤用為精確成交均價或帳務結算依據；後續需要另找精度與成交範圍符合用途的官方資料。

目前樣本保留 `known_at=null`、`return_close=null`、`tradable=false`、`adjustment_status=unresolved`：無法證明歷史公開時刻，不冒稱已完成調整價格或可交易狀態核實。它可供閱讀與下載測試，沒有放入過去的正式 MarketSnapshot、結算或完整回測。

取得方式使用 Windows 內建 `curl` 與系統 Schannel 憑證驗證。Python 3.14 的 urllib 在本機遇到 TLS `Missing Subject Key Identifier`，改用系統工具重試，沒有關閉憑證驗證或安裝套件。CLI 的 `--transport auto` 優先用既有 curl，沒有 curl 時才用標準庫 urllib；亦可明確指定工具。每個請求有 10 秒 timeout，沒有自動重試；已保存的月報可用下述 `history-export` 完全離線重輸出。

首次真實下載批次為 `20261011T122548_f1b87c04`，後續使用該批原始 JSON 離線重輸出成閱讀 CSV 2.0，再依使用者選定的千元／張單位整理為 3.0；第 06 批由同一資料重排成每日／個股月 CSV 4.0。早期目錄已依使用者要求清理；兩份原始 JSON、原欄位 CSV 與行情已包含於全股票目錄，樣本 manifest 原文和格式／驗收紀錄另行保存。查看及重跑入口以下方現存全股票目錄為準。

### 如何解讀 prices.csv

CSV 使用 UTF-8 BOM，方便 Excel 顯示中文；空欄代表 `null`。新版每日表與個股月表使用相同 22 欄，原報表欄位 CSV 則保持來源單位與原值。

原樣本根目錄 `prices.csv` 月合表已移除；現在以 `daily/<YYYY-MM>/<YYYY-MM-DD>_prices.csv` 保存當天所有已取得股票的價量長表，另有 `monthly/<YYYY-MM>/<market>_<ticker>_<YYYY-MM>.csv` 個股月表。2025-09 現存資料取自 F05 全 150 檔查詢，147 檔有行情；2330／5274 每股 21 列的早期樣本已包含在內。`TWSE` 表示上市，`TPEX` 表示上櫃。兩種表共用格式與清洗結果，月表仍是整月每日行情集合，不是月 K 線；日／月表不能同時合併計算。這些是歷史資料閱讀表，尚未完成可交易狀態、公司行動或歷史公開時間核實。

`ktwd` 表示新臺幣千元，`lot` 表示張。第 06 批曾完全離線將兩檔樣本整理為 21 份日表及兩份月表，保留 42 列；第 10 批全股票下載核對並復用這兩份原始來源，現存資料統一於 `data/cache/history_universe/2025-09/20261011T145716_6e56c903/`：

- 2025-09-01 每日價量 CSV（146 列、張／千元）（本機路徑 `data/cache/history_universe/2025-09/20261011T145716_6e56c903/daily/2025-09/2025-09-01_prices.csv`）。全批 21 個來源回傳日，共 3,075 列；缺件另見下節，未填造休市或無行情日期。
- TWSE 2330 月表（21 列）（本機路徑 `data/cache/history_universe/2025-09/20261011T145716_6e56c903/monthly/2025-09/TWSE_2330_2025-09.csv`）、TPEx 5274 月表（21 列）（本機路徑 `data/cache/history_universe/2025-09/20261011T145716_6e56c903/monthly/2025-09/TPEX_5274_2025-09.csv`）。兩股原價量、原抓取時間與版本保留；來源代號依全股票批次配置。月表供個股歷史查閱，不與日表重複合併。
- TWSE 原報表欄位 CSV（本機路徑 `data/cache/history_universe/2025-09/20261011T145716_6e56c903/source_csv/2025-09/TWSE_2330_2025-09_source.csv`）、TPEx 原報表欄位 CSV（本機路徑 `data/cache/history_universe/2025-09/20261011T145716_6e56c903/source_csv/2025-09/TPEX_5274_2025-09_source.csv`）。依月份分目錄、檔名加 `_source`，保留原欄位、字串及單位，與原樣本檔逐位元相同。
- TWSE 原始 JSON（本機路徑 `data/cache/history_universe/2025-09/20261011T145716_6e56c903/raw/TWSE_2330_2025-09.json`）、TPEx 原始 JSON（本機路徑 `data/cache/history_universe/2025-09/20261011T145716_6e56c903/raw/TPEX_5274_2025-09.json`）。原內容及 hash 保留，不重新下載這兩股。
- 全股票 manifest（本機路徑 `data/cache/history_universe/2025-09/20261011T145716_6e56c903/manifest.json`） 與 品質報告（本機路徑 `data/cache/history_universe/2025-09/20261011T145716_6e56c903/data_quality.json`） 是現行索引，保存網址、HTTP 狀態、原抓取時間、hash、版本、單位及日／月路徑。
- 樣本 manifest 原文（本機路徑 `data/cache/history_universe/2025-09/20261011T145716_6e56c903/sample_manifest.json`）、樣本品質報告（本機路徑 `data/cache/history_universe/2025-09/20261011T145716_6e56c903/provenance/history_sample/data_quality.json`） 與 首次下載 manifest 原文（本機路徑 `data/cache/history_universe/2025-09/20261011T145716_6e56c903/provenance/history_sample/original_manifest.json`） 另行保存，內容與 hash 不變。樣本 manifest 的舊 run ID、輸入目錄、日表列數與格式整理路徑是歷史紀錄，不能當作現行全股票索引；`history-export` 仍可從它與同目錄兩份 raw 完全離線重建兩股 CSV。

原 `data/cache/history_sample/` 經重複資料核對後已清理。樣本格式變遷證據另存 `provenance/history_sample/`，包含 `csv_v2_manifest.json`、`source_layout_manifest.json`、`daily_monthly_manifest.json` 及 第 09 批兩股日表輸入（本機路徑 `data/cache/history_universe/2025-09/20261011T145716_6e56c903/provenance/history_sample/input/2025-09-01_prices.csv`）；上述樣本 manifest 與品質／原始 manifest 合計保存七份證據。另有 清理及保存 hash 索引（本機路徑 `data/cache/history_universe/2025-09/20261011T145716_6e56c903/provenance/history_sample/cleanup.json`），記錄原路徑、保存路徑及刪除範圍。第 09 批覆蓋報告保留原始輸入路徑，不回改歷史。

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

**本批評估後保留此欄位。** 它記錄來源量值精度，不是選股因子，也不是官方 D-Plan schema 的必填欄位。目前解析器依來源格式設定它，匯出 CSV／manifest 並顯示於 CLI；下方三因子只使用收盤原價，不依此旗標選股。配置與結算尚未實作，不能宣稱程式已依此旗標完成投資決策或正式驗證。

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

`history-export` 從兩檔樣本的 manifest 與保存的 raw JSON 重建新版 CSV，先核對 SHA-256，再使用相同市場 adapter 解析；不用網路，也不把重輸出時刻當成新的抓取時刻。新 run 的 manifest 標記 `purpose=offline_cached_export`、`network_requests=0`，並以 `reexport_of` 記錄原批次。此命令只支援 2330／5274；F05 全股票快取使用下方 `history-universe --cache-manifest`。一般重跑不覆寫輸入目錄，核心合約與 fixture 不修改。

先前 CSV 3.0 依使用者要求直接替換三份閱讀 CSV，當時 manifest 標記 `purpose=offline_cached_csv_rebuild`、`network_requests=0`；保留原 `run_id`、`created_at`，另記 `csv_rebuilt_at`。`csv_rebuild_of` 記錄替換前 manifest 的雜湊及存檔位置 `provenance/csv_v2_manifest.json`，原 `reexport_of` 仍代表首次下載的來源關係。原始 JSON／原欄位 CSV 與 `provenance/original_manifest.json` 維持原文。

後續依使用者要求，原報表 CSV 移到 `source_csv/2025-09/`、檔名加 `_source`，內容不變。來源路徑以現在的 `manifest.sources[].source_csv` 為準，當次整理前 manifest 保存於 `provenance/source_layout_manifest.json`；該次只調整位置，CSV 仍為 3.0。一般離線匯出仍從 raw JSON 重建來源表，不把 source_csv 當因子輸入或信任已手動修改的來源表。

第 06 批曾以 CSV 4.0 就地整理日／月視圖，樣本 manifest 標記 `purpose=offline_cached_price_view_rebuild`、`network_requests=0`，另記 `price_views_rebuilt_at`；`price_views_rebuild_of` 保存前版 CSV 格式、manifest 雜湊及當時存檔位置 `provenance/daily_monthly_manifest.json`。當時不改原始 JSON、原報表 CSV、原下載時間、原批次 ID 或建立時間；樣本品質報告記錄 21 份日檔、兩份月檔。這些樣本 manifest／provenance 現已另存，舊路徑是當時版本紀錄；查閱目前行情依全股票 `manifest.json`，兩股離線重輸出使用 `sample_manifest.json` 與 raw。

### 資料使用入口與每日／每月檔案

目前實作兩檔樣本及 F05 全股票月報的來源保存、每日表與個股月表匯出，另有沿用完整價格視窗、只讀每日表收盤原價的三因子分析。正式快照／因子合約串接、預測、每日最新行情更新／排程及下列額外資料入口尚未實作；核心因子函式不解析原報表的中文欄位、不抓 API。

| 資料 | 預計用途 | 目前狀態 |
|---|---|---|
| 清洗後的歷史價量 | 動能、均線、波動、成交金額篩選；20 日動能要同股 21 個有效交易日 | 有全股票月報下載、21 筆價格視窗檢查及三種原價因子；實際休市／公司行動與歷史可知時間仍待核實 |
| [data/universe.csv](../data/universe.csv) | 限定 F05 白名單、標示股票與市場 | 已有 150 檔、來源版本及 loader／CLI，已接入月報下載、日表覆蓋及視窗分析；交易流程尚待串接 |
| 交易日曆 | 找市場排程交易日、檢查指定日以前的價格視窗 | 已有兩市場官方年度排程的月份日曆，臨時全市場休市未全面核實 |
| 公司行動／個股停牌 | 核對價格調整與當日可交易資格 | 尚未接入 |
| 大盤行情 | 市場研判與市場因子 | 尚未接入 |
| 法人、營收等資料表 | 新增這些因子時才加入，依公告與版本時間取用 | 未實作 |
| `FeatureTable`／排名產物 | 模型接收計算後的因子、排名與證據；研究模型另需標籤與時間切分 | 原價三因子另有歷史分析產物，尚未接入此合約或排名；正式來源／觀察證據鏈及訓練待完成 |
| `AccountSnapshot`／帳戶 JSON | 策略、配置及風控需知道完整持股與現金 | 僅有人工 demo／合約，尚無正式帳務 |

先前已同意將**每日表作後續核心讀取入口**，每股每月表作歷史查閱視圖，並完成兩種視圖的匯出。同一批 raw 經同一清洗結果產生兩種表，不重複抓取；後續讀取器只用一種入口，不把兩種表同時合併，避免同股同日重複。日表方便每日更新及橫斷面排名，但 20 日動能仍須讀同股 21 個有效交易日，不能只讀單日日檔。

目前全股票目錄內的路徑：

```text
monthly/2025-09/TWSE_2330_2025-09.csv          # 同股一個月每天的清洗資料，月表共147檔
monthly/2025-09/TPEX_5274_2025-09.csv
daily/2025-09/2025-09-01_prices.csv           # 同一天已取得的股票，本日146檔
daily/2025-09/...                            # 共 21 個實際有資料的日期
source_csv/2025-09/*_source.csv              # 原報表字串與單位，供來源核對
```

第 06 批樣本曾從既有 42 列離線重排，得到兩份個股月表與 21 份日表，每日只有 2330／5274 兩列；原目錄現已清理，原始來源、價量與必要驗收紀錄在全股票目錄保留。全股票逐股取得狀態與逐日覆蓋見下節，後續官方排程與價格視窗另存獨立報告。真實每日最新更新、臨時休市及截止驗證仍待補齊，沒有建立每日抓取排程。缺行情或尚未核實者保留狀態／品質紀錄，不因資料不完整而默默從股票池消失。

盤前時間保留兩種不同意義：`trade_date` 是行情日，`known_at` 是有證據的公開可知時刻。若採「今日資料下一交易日使用」，可另增 `usable_from_trade_date` 作**自訂保守使用政策**；不能把 known_at 改成下一天或下一開盤時刻。使用日要依交易日曆、已完成資料及決策截止推導，遇休市或延遲公告須延後，不能固定日期加一。現在歷史 known_at 未核實，新增政策日期仍不能使資料通過正式快照驗證；此欄位與計算尚未實作。

每次重跑產生新的時間／隨機 ID 目錄，保留舊回應。失敗回應與原因記在 manifest；HTTP 錯誤或 HTML 不轉成行情。單一市場失敗時仍保留另一市場資料，但整次 `success=false`、CLI exit code 2，不能把部分成功當完整下載通過。

上述快取由 `.gitignore` 排除，連結是本機產物導覽；新 clone 沒有這些檔案，需先取得對應原始資料才能重輸出。它不是已建好的帳務資料庫或研究資料集。

**下載、匯出與解析程式：** [history.py](../src/etf_agent/history.py) 的 `download_history_sample()` 負責兩檔樣本，`download_history_universe()` 負責 F05 全股票與快取核對，`_export_month()` 共用來源保存及日／月匯出，`export_history_sample()` 負責已存樣本的離線重輸出，`_write_prices()` 負責閱讀 CSV 單位轉換；[providers/http.py](../src/etf_agent/providers/http.py) 負責 HTTPS；[providers/twse.py](../src/etf_agent/providers/twse.py)、[providers/tpex.py](../src/etf_agent/providers/tpex.py) 各自建立官方歷史 URL 與讀取報表；[providers/monthly.py](../src/etf_agent/providers/monthly.py) 做日期、逗號、空值、單位及重複／價格檢查。這些來源原始欄位不進六種核心合約。

**程式位置：** [contracts.py](../src/etf_agent/contracts.py) 的 `PriceBar`（第 160 行）、`MarketSnapshot`（第 199 行）。

## F05 全股票歷史月報

### 目的、輸入與產物

`download_history_universe(month, output, *, universe, cache_manifest=None, ...)` 取得 F05 全 150 檔的一個已完成月份，沿用兩檔樣本的官方月報 adapter 與 CSV 4.0／22 欄。`universe` 必須是已核對的 150 檔、100 TWSE／50 TPEX 白名單。此批先處理 2025-09；不下載當月尚未完成或未來月報，不建立每日最新更新或投資決策流程。

每次另建 `data/cache/history_universe/<月份>/<時間_隨機識別碼>/`，保留既有樣本和舊批次。完成批次包含以下資料：

```text
raw/TWSE_2330_2025-09.json                   # 官方原始回應；失敗回應若已取得也保存
source_csv/2025-09/TWSE_2330_2025-09_source.csv # 成功來源的原報表欄位、字串與單位
monthly/2025-09/TWSE_2330_2025-09.csv         # 該股整個月的每日清洗行情，不是月 K 線
daily/2025-09/2025-09-01_prices.csv          # 當天實際取得的上市／上櫃股票合併表
manifest.json                              # 逐股狀態、網址／hash／時間與日／月索引
data_quality.json                          # 解析檢查、取得數與尚未核實項目
coverage.json                              # 失敗股票、來源回傳各日的覆蓋及缺件
```

日表與月表由同一清洗結果產生，數值與唯一鍵應一致。後續分析採每日表作核心入口；單股查閱可看月表，不能將日／月視圖疊加成兩倍資料。CSV 使用 UTF-8 BOM，可用 Excel 開啟；欄位、張／千元單位、均價精度與上櫃 `reported_*` 政策見前節。

### 取得、快取與中斷續接

全股票下載為單線請求，每兩次 HTTP 請求間隔至少 1 秒，每次 timeout 10 秒，不自動重試；使用現有標準庫及系統 curl，不新增依賴或呼叫投資模型。`network_requests` 記錄此次真正呼叫下載器的次數，`cache_hits` 記錄成功復用的來源數；每股均在 CLI 顯示進度。

`--cache-manifest` 可指定既有兩檔樣本、完整全股票批次或中斷／部分失敗批次。程式先檢查 manifest 格式與請求月份、來源股票／市場及重複，再針對成功來源核對原始 JSON SHA-256、目錄內路徑、官方請求 URL、HTTP 200、HTTPS 主機、JSON 類型及真實 `+08:00` 的 `fetched_at`，最後用 adapter 重驗月份／股票。壞快取直接阻擋，不以重新下載掩蓋；未成功來源不作快取使用。

確認快取後，把原始內容複製至新 run，再從 raw 重建 `source_csv`、月表及日表；不信任舊清洗 CSV，也不改原 `fetched_at`。新 manifest 的 `cache_reuse` 記錄來源 manifest 的路徑、hash 與 run ID。若已具備 150 個成功來源，仍使用 `history-universe --cache-manifest` 另建一版 CSV，實際 HTTP 為 0；`history-export` 仍僅支援兩檔樣本。

每股處理後以暫存檔替換 manifest，保存 `status=in_progress`、已完成來源、HTTP／快取計數及 `success=false`。串流中斷可用此 manifest 的成功 raw 續接，另建新目錄；原批次保留。全部走訪完成後 `status=completed`，`sources` 恰有 150 個逐股成功／失敗狀態，按代號排序配置 `source_key=H1`～`H150`。這些 H 代號是該批資料引用，不代表已建好官方 D-Plan 證據鏈。

來源失敗時保留理由與已取得原始回應，不產生該來源的清洗月表；其餘股票仍繼續。沒有回傳的日期／股票不補造行。最終任一來源失敗則整批 `success=false`、CLI exit code 2；沒有股票查詢／下載／解析失敗時 exit code 0。

### 如何判斷取得成功與完整性

| 欄位／結果 | 意義與限制 |
|---|---|
| `manifest.success`／逐股 `status=success` | 股票月報取得且日期／身分／欄位解析成功；不保證該股有整月每個交易日 |
| `manifest.daily_prices` | 來源實際回傳日期聯集的日檔索引、每檔列數；不是官方交易日曆 |
| `coverage.successful_stock_count`／`failed_stocks` | 150 檔之中成功來源數，以及失敗股票名稱／市場／原因 |
| `coverage.daily_reports` | 對每個已產生日檔呼叫日表覆蓋檢查，保留已取得／有效價格／缺件／errors／warnings |
| `data_quality.checks.all_150_symbols_covered` | 每個來源回傳日期的日表均通過 150 檔身分覆蓋；整月缺一個所有來源都未回傳的日期仍無法辨識 |
| `calendar_completeness_verified`／`historical_universe_verified` | 原下載報告維持 false；後續官方排程與價格視窗另存報告，歷史各日股票池未完整核實 |
| `submission_ready` | 固定為 false，不產生正式 D-Plan 或已核對帳戶 |

因此取得 150／150 與每日日表 150／150 須分別查看，且仍不能宣稱完整回測或正式決策資格。TPEx 精確量值／均價仍空白、`reported_*` 保留整數張／仟元報表換算；兩市場成交統計範圍未統一。歷史 `known_at` 與 `return_close` 留空、`adjustment_status=unresolved`、`tradable=false`；公司行動及當時可知版本未驗證。原下載報告不包含後續官方排程與價格視窗核對，後續結果另見下節。

### 2025-09 實際產物與缺件

第 10 批真實下載輸出於 `data/cache/history_universe/2025-09/20261011T145716_6e56c903/`。150 個來源全部走訪，147 檔有行情，其中 146 檔各 21 列，7750 為 9 列；共 3,075 個唯一股票日資料，產生 21 份日表與 147 份每股月表。實際 HTTP 148 次，2330／5274 原始快取命中 2 次；147 檔成功不等於 150 檔完整覆蓋。

| 股票／日期範圍 | 官方取得結果及日表影響 |
|---|---|
| 3718／TPEX、7769／TWSE、7828／TPEX | 官方回應查無 2025-09 行情，下載原紀錄為失敗來源；後續已核對三股上市／上櫃日期均晚於該月，原因見下方核實報告 |
| 7750／TWSE | 月報僅回傳 2025-09-17～09-30 的 9 筆；後續核對 TWSE 上市日為 2025-09-17，不補掛牌前日期，仍待核實完整交易日曆 |
| 來源回傳的 2025-09-01～09-16 | 12 份日表，每份 146／150、缺 4；缺上述三檔與 7750 |
| 來源回傳的 2025-09-17～09-30 | 9 份日表，每份 147／150、缺 3；缺上述三檔 |

已完成走訪但整批 `success=false`、CLI exit code 2；全部日表 `coverage_complete=false`，`submission_ready=false`。原下載報告中的 21 日只是來源回傳日期聯集，當時尚未用官方日曆驗證；後續排程與價格視窗核對另外保存。

資料入口：

- 每日表目錄（本機路徑 `data/cache/history_universe/2025-09/20261011T145716_6e56c903/daily/2025-09/`）及 2025-09-01 日表（本機路徑 `data/cache/history_universe/2025-09/20261011T145716_6e56c903/daily/2025-09/2025-09-01_prices.csv`）。
- 每股月表目錄（本機路徑 `data/cache/history_universe/2025-09/20261011T145716_6e56c903/monthly/2025-09/`）、2330 月表（本機路徑 `data/cache/history_universe/2025-09/20261011T145716_6e56c903/monthly/2025-09/TWSE_2330_2025-09.csv`）、7750 月表（9 筆）（本機路徑 `data/cache/history_universe/2025-09/20261011T145716_6e56c903/monthly/2025-09/TWSE_7750_2025-09.csv`）。
- 來源及逐股狀態 manifest（本機路徑 `data/cache/history_universe/2025-09/20261011T145716_6e56c903/manifest.json`）、逐日覆蓋與缺件 coverage（本機路徑 `data/cache/history_universe/2025-09/20261011T145716_6e56c903/coverage.json`）、品質報告（本機路徑 `data/cache/history_universe/2025-09/20261011T145716_6e56c903/data_quality.json`）。

第 10 批全套 132 項測試通過（13.821 秒）。這是程式檢查證據；三檔真實來源無行情與 7750 部分日期仍如實保留，不因測試通過而變成完整歷史資料集。第 09 批覆蓋報告保留不改，樣本來源與必要驗收紀錄已另存；以上連結為 Git 忽略的本機快取，新 clone 不會附帶。

後續三檔無行情原因已依官方上市／上櫃資料核對，詳見 [2025-09 歷史行情可取得範圍](history_availability_2025-09.md)。核實結果另外保存，不更改原 manifest／coverage 的下載狀態，不將股票移出 F05，也不使用前身代號或興櫃價量補入本批；缺件仍保持缺值。原兩檔樣本目錄已清理，所需來源與七份追溯／驗收證據已併入全股票目錄，第 09 批覆蓋報告保持原文。

清理後全套 132 項測試再次通過（13.556 秒）；保存的 `sample_manifest.json` 已實際零 HTTP 匯出 42 列、21 個兩股日檔，首日檔內容與保存輸入逐位元相同，保存輸入也重跑出 2／150 覆蓋。原全股票 468 份檔案、九份官方來源與兩份白名單檔案 hash 維持；上述七份保存證據保留原 hash。暫存驗證輸出已清理，沒有增加分析資料的第二份常駐副本。

### 重跑方式

從目前全股票批次復用 147 檔成功來源，再查詢三檔無行情來源（會連網，仍有 3 次 HTTP）：

```powershell
$env:PYTHONPATH = (Resolve-Path 'src').Path
python -B -m etf_agent.cli history-universe --month 2025-09 --universe data/universe.csv --cache-manifest data/cache/history_universe/2025-09/20261011T145716_6e56c903/manifest.json --output data/cache/history_universe
```

`--month` 必填；`--universe` 預設 `data/universe.csv`，可用 `--universe-manifest` 指定白名單來源紀錄。未提供 `--cache-manifest` 時請求全部 150 檔；部分成功快取只減少已成功來源，完整成功快取才可零 HTTP 重輸出。`--output` 預設 `data/cache/history_universe`，`--transport` 支援 auto／curl／urllib 且保留憑證驗證。

**程式位置：** [history.py](../src/etf_agent/history.py) 的 `download_history_universe()`、`_read_cached_month()`、`_export_month()`；[cli.py](../src/etf_agent/cli.py) 的 `history-universe` 命令；逐日核對重用 [coverage.py](../src/etf_agent/coverage.py)。實際執行與驗收證據統一記於 [development_notes.md](../development_notes.md)。

## 官方排程日曆與價格視窗

### 輸入、方法與產物

`calendar-download` 取得 TWSE／TPEx 官方年度開休市表，按例行週一至週五及官方排程事件產生指定月份日曆。每批另存 `data/cache/calendar/<月份>/<版本>/calendar.json`、可用 Excel 開啟的 `calendar.csv` 與兩份原始回應；來源紀錄保存請求／回應 URL、抓取時間及 SHA-256。兩市場各自解析並核對回應年份，錯年或缺一市場不產生成功日曆；離線載入再核對 raw hash 與重建結果。

已實測 [TWSE 2025 年表](https://www.twse.com.tw/rwd/zh/holidaySchedule/holidaySchedule?response=json&date=20250101) 與 [TPEx 2025 年表](https://www.tpex.org.tw/www/zh-tw/bulletin/tradingDate?date=2025&response=json)。TWSE 必須用 `date=20250101`；直接傳 `queryYear=2025` 曾回傳 2026，解析器會拒絕錯年。TPEx 從 JSON 的 `data.html` 年度表解析，核對民國年標題，排除債券專屬事件；股票封關後的非交易期間仍保留。

`calendar_basis=official_schedule`、各市場 `schedule_verified=true` 只表示官方年度排程已核對。天然災害等臨時全市場休市公告尚未全面核實，因此 `actual_sessions_verified=false`；日曆也不是個股停牌表，不證明歷史公開可知時間。

`history-window-check` 接收全股票 manifest、保存的日曆與 `--as-of`，按每個市場取截止日以前最近 21 個排程交易日，核對相應日表中的每檔有效價格。例如 `--as-of 2025-09-30` 表示已完成歷史行情的資料截止日，不是 2025-09-30 盤前決策；不讀之後日期，也不把月表疊加進來。

日期依日曆指定，缺整個日檔列入 `missing_day_files`，缺股票或無效價格分別保存日期清單；不能因總列數有 21 筆就跳過中間缺日。若當月截至指定日不足 21 個排程交易日，記錄 `calendar_window_shortfall`，不猜更早月份日期。本版只接受同月日曆／行情；跨月視窗的讀取仍待擴充，必須取得更早月日曆與價格。

每次另建 `data/cache/history_windows/<截止日>/<版本>/`，不改原下載 manifest、行情或日曆：

| 檔案／欄位 | 用途 |
|---|---|
| `window_coverage.csv` | UTF-8 BOM、13 欄，150 檔各一列：市場、有效價格筆數、缺失／無效價格的日期、日曆不足及狀態；不逐股重複 `expected_dates` |
| `window_report.json`／`.md` | 完整逐日診斷／閱讀摘要，保留資料及日曆版本、來源與未核實事項 |
| `window_complete` | 依已提供官方排程，所需 21 個日期都有有效價格；不表示正式可交易或因子已計算 |
| `input_valid` | 日表讀取與列格式診斷；和缺日期、視窗完整分開判斷 |

CSV 完整股票的 `missing_dates`／`invalid_price_dates` 留空；有缺失時以分號列出實際缺哪幾天。完整預期日期仍在 JSON 的分市場索引及日曆保存，閱讀表只呈現日期缺口。現有四檔不足的原因已核實為掛牌期間／新股視窗不足，依使用者指示先停止缺失查核，後續跨月視窗、意外漏資料、停牌／公司行動等工作列於 checklist 的 DATA-22。

窗口檢查沿用每日 coverage 的價格口徑，尚未逐份驗歷史行情 raw、公司行動、`return_close`、`known_at`、帳戶或正式截止規則。CLI 成功保存無列錯誤報告可回傳 exit 0，即使某些股票視窗不足；manifest／日曆無法載入或日表列／讀檔錯誤回傳 2，缺日期則另外記錄。所有新產物仍為 `submission_ready=false`；原下載報告的未核實旗標保持當時內容。

### 重跑與本批結果

下載日曆會連網；價格視窗檢查完全離線。第二條示範使用本機已保存版本，新下載請改用 CLI 顯示的日曆路徑：

```powershell
python -B -m etf_agent.cli calendar-download --month 2025-09 --output data/cache/calendar --transport curl
python -B -m etf_agent.cli history-window-check --manifest data/cache/history_universe/2025-09/20261011T145716_6e56c903/manifest.json --calendar data/cache/calendar/2025-09/20261011T154421_1306c9a4/calendar.json --as-of 2025-09-30 --output data/cache/history_windows
```

實際日曆下載為兩次 HTTP、exit 0；TWSE／TPEx 各 21 個排程交易日，9/29 排程休市。日曆 CSV（本機路徑 `data/cache/calendar/2025-09/20261011T154421_1306c9a4/calendar.csv`） 供閱讀，日曆 JSON（本機路徑 `data/cache/calendar/2025-09/20261011T154421_1306c9a4/calendar.json`） 保存日期及官方來源索引，`actual_sessions_verified=false`。

截至 2025-09-30，146 檔各有完整 21 筆有效價格，7750 有 9 筆、3718／7769／7828 各 0 筆；`missing_day_files=[]`、`input_valid=true`、CLI exit 0。150 檔視窗 CSV（本機路徑 `data/cache/history_windows/2025-09-30/20261011T154440_9842e79e/window_coverage.csv`）、完整 JSON（本機路徑 `data/cache/history_windows/2025-09-30/20261011T154440_9842e79e/window_report.json`） 與 閱讀摘要（本機路徑 `data/cache/history_windows/2025-09-30/20261011T154440_9842e79e/window_report.md`） 另存，沒有改原行情或下載 manifest。

第 13 批實際通過一項日曆年度測試與三項價格視窗測試，未重跑全套。後續原價因子分析見下方「因子與排名」；視窗完整不能替代公司行動、歷史可知時間或正式快照核實。

**程式位置：** [calendar.py](../src/etf_agent/calendar.py) 的 `download_calendar()`／`load_calendar()`；[history_windows.py](../src/etf_agent/history_windows.py) 的 `check_history_windows()`／`write_window_report()`；命令由 [cli.py](../src/etf_agent/cli.py) 組合。

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

### 原價歷史三因子分析

選擇理由、指標意義、公式、閱讀例子、執行與失敗處理集中在 [三因子分析說明](factor_analysis.md)。本節保留與其他模組接合時需要的輸入、欄位、單位及來源界線。

`history-features` 沿用 `window_report.json` 的資料截止日、分市場共同日期與 `window_complete=true` 股票名單。只讀報告引用的 daily 收盤 `close_raw_ktwd_per_lot`，不讀月表或截止日之後；每股 21 筆原價得 20 個日簡單報酬。輸入價格為新臺幣千元／張，因子使用比例，單位在相除時抵消。`as_of` 為歷史資料截止日，並非決策日盤前時間。

| 產物／欄位 | 合約與單位 |
|---|---|
| `features.csv` | 六欄：`ticker`、`name`、`market`、`mom20_pct`、`trend20_pct`、`vol20_annual_pct`；三因子為百分數，`10.000000` 代表 10%。UTF-8 BOM、六位小數、`ROUND_HALF_UP`。 |
| `metadata.json` 的 `rows[].values` | `mom20`、`trend20`、`vol20` 以 Decimal 十進位字串保存比率；`0.10` 代表 10%。計算用 34 位精度、`ROUND_HALF_EVEN`。不能直接以 CSV 百分數替換核心 `FeatureRow.values`。 |
| 每股來源 | `price_count=21`、`return_count=20`、`source_metadata`；保留來源 key、資料版本、取得時間及未核實時間／調整狀態。 |
| 共同 metadata | `as_of`、`expected_dates_by_market`、`formulas`、`annualization_trading_days=252`、`units`、`input_window_report`、`input_manifest`、`daily_inputs`、`universe_version`、`calendar_version`／依據、`feature_version`、`price_basis`、`limitations`。輸入路徑與 hash 保留供追溯。 |
| 排除紀錄／正式狀態 | `excluded_stocks` 沿用原視窗不足紀錄；`submission_ready=false`，原價分析不自動證明可交易或可提交。 |

每次另建 `data/cache/features/<as_of>/<執行版本>/`，保存 features.csv、metadata.json 及 analysis.md。`feature_version` 按固定公式與輸入內容辨識，相同輸入可重算相同版本，執行時間與目錄另行保存。現有版本截至 2025-09-30 分析 146 檔、排除既有四檔；實際產物入口與重跑方式見 [專屬說明](factor_analysis.md#先看哪個檔案)。

核心純計算為 [features.py](../src/etf_agent/features.py) 的 `calculate_price_features()`；`analyze_history_features()` 核對既有輸入並讀日表，`write_feature_analysis()` 保存產物。這份歷史分析尚未接入正式 `MarketSnapshot`／`FeatureTable`、完整 source→observation 證據鏈、加權排名或投資模型。公司行動、歷史 `known_at` 與臨時休市未全面核實，原行情的 `return_close` 留空、`adjustment_status=unresolved` 與 `tradable=false` 維持原狀；缺失處理另列 checklist DATA-22。

### 待完成

現有 `contracts-demo` 的因子與排名仍是人工假值，`origin=fixture`，上述真實歷史原價分析不會自動替換 fixture。調整價／公司行動、正式快照與因子合約串接、流動性篩選、因子標準化及加權排名尚未完成。O1～O25 只是 fixture 內部引用，還不是官方完整 source→observation 證據鏈。

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

`AgentDraft.validate_context()` 要由呼叫端傳入 `allowed_tickers`、`held_tickers`、`observation_ids`，再檢查候選池合法、完整且精確覆蓋原持股、觀察引用確實存在。`Universe.allowed_tickers` 已提供 F05 合法代號集合；目前 `contracts-demo` 仍使用 fixture 的行情代碼作示例候選池，尚未串接白名單載入模組。

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

日表對 F05 的股票覆蓋率已有獨立檢查；它沒有檢查長期歷史期間或因子視窗。真正交易日 gap、標籤終點、排除跨界標籤（purge）、研究資料完整度、測試集存取限制、滾動回測與訓練流程尚未實作。`final_test_locked=true` 目前只是配置檢查，沒有禁止程式讀取測試期的功能。

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

小量歷史樣本下載指令保留供兩檔來源測試（會連網）；日常分析以全股票目錄為入口：

```powershell
$env:PYTHONPATH = (Resolve-Path 'src').Path
python -B -m etf_agent.cli history-sample --month 2025-09 --output data/cache/history_export
```

`--month` 只接受已完成月份；`history-sample` 固定下載 2330／5274，全 150 檔另用 [history-universe](#f05-全股票歷史月報)。成功回傳 exit code 0；任一來源失敗或輸入錯誤回傳 2。輸出顯示每日／月表目錄、日檔數、第一個日檔及 manifest 路徑。程序使用真實歷史行情，但不呼叫投資模型、不計算因子或更新帳戶。

已保存的樣本 manifest 原文與同目錄兩份 raw 可完全離線重輸出為張／千元 CSV，包含當日均價（不連網）：

```powershell
python -B -m etf_agent.cli history-export --manifest data/cache/history_universe/2025-09/20261011T145716_6e56c903/sample_manifest.json --output data/cache/history_export
```

此指令從目前保留的新版目錄讀取來源資料，再建立新批次並印出每日／月表目錄、日檔數、第一個日檔及 manifest 路徑，不需要已刪除的舊目錄。缺少 manifest／raw 檔、SHA-256 不符、錯月／錯股票或來源失敗時，不視為成功；實際錯誤原因保存或顯示供核對。它是對已取得真實資料的離線重輸出，不是本次又抓到最新資料。

離線檢查指令不連網，fixture 明示合成值；包含來源格式、錯月／股票、單位／精度、空值、衝突、價格錯誤、下載失敗、版本保存，以及閱讀 CSV 張／千元換算、均價與離線來源核對：

```powershell
python -B -m unittest discover -s tests -p 'test_*.py' -v
```

相關程式在 [test_history.py](../tests/test_history.py)、[test_universe.py](../tests/test_universe.py) 與 [test_coverage.py](../tests/test_coverage.py)，各批實際測試數與結果記錄在開發紀錄。`universe-check` 的重跑方式與檢查範圍見 [官方股票白名單](#官方股票白名單)；`prices-check` 見 [每日行情覆蓋與缺件報告](#每日行情覆蓋與缺件報告)。

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
