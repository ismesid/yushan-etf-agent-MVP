# 歷史行情下載、重建與覆蓋

這份文件說明如何產生官方歷史行情 CSV、復用快取及檢查每日股票覆蓋。先依 [環境與基本使用](quickstart.md) 設定 `PYTHONPATH`；資料欄位與精度見 [資料合約](data_contracts.md)。

## 全股票下載

`history-universe` 依 F05 白名單走訪全部 150 檔，下載一個已完成月份的 TWSE／TPEx 官方月報。從頭下載：

```powershell
python -B -m etf_agent.cli history-universe --month 2025-09 --universe data/universe.csv --output data/cache/history_universe --transport curl
```

月份格式為 `YYYY-MM`，目前不下載當月尚未完成的月報。`--transport` 可用 auto／urllib／curl；`--universe-manifest` 可指定白名單來源紀錄。全股票下載採單線，每兩次 HTTP 請求間隔至少 1 秒、每次 timeout 10 秒，不自動重試。

每次另建 `data/cache/history_universe/<月份>/<執行版本>/`，命令列逐股顯示進度，最後顯示成功／失敗、實際 HTTP 次數、快取命中數與輸出路徑。不要只看退碼：逐股取得成功、逐日覆蓋完整及正式交易資格是不同狀態。

## 復用快取與中斷續接

串流中斷或部分股票失敗時，使用該次目錄的 manifest 再執行。既有 2025-09 資料可用：

```powershell
python -B -m etf_agent.cli history-universe --month 2025-09 --universe data/universe.csv --cache-manifest data/cache/history_universe/2025-09/20261011T145716_6e56c903/manifest.json --output data/cache/history_universe
```

成功快取先核對原始內容 hash、股票／月份、官方 HTTPS 與取得時間，再複製到新執行目錄；壞快取會阻擋。只對未成功股票發出新請求。現有資料有 147 檔成功來源，因此上述命令仍會查詢三檔無行情來源、發出 3 次 HTTP 請求；不是完全離線重建。

若一份快取的全部 150 檔皆成功，相同命令可零次 HTTP 另產一版 CSV。快取命中不更新原始 `fetched_at`；它代表原資料取得時間。

## 產物結構與讀取方式

```text
history_universe/<月份>/<執行版本>/
├─ raw/                 # 官方回應原文，包含失敗回應
├─ source_csv/<月份>/   # 成功來源的原始報表 CSV
├─ daily/<月份>/        # 一日一檔，合併當日已取得股票
├─ monthly/<月份>/      # 一股一檔，該股整月每日行情
├─ manifest.json        # 來源網址、時間、hash、逐股狀態與檔案索引
├─ coverage.json        # 逐日覆蓋、缺件與失敗股票
└─ data_quality.json    # 原價、空值、單位與未核實限制
```

日表與月表都是 CSV 4.0／22 欄，來自同一清洗結果。月表是整月每日行情，並非月 K 線；分析入口使用 daily，monthly 供個股查閱，不同時合併兩種視圖。

閱讀 CSV 以千元／張表示價格，以張表示成交量、千元表示金額。空欄代表未知，不可當成 0；TPEx 精確成交量／金額尚無法從月報確認，保留報表口徑，精確值留空。來源單位、清洗計算、顯示精度與內部合約的元／股轉換，統一見 [資料合約](data_contracts.md)。

## 目前 2025-09 結果

已走訪 150 檔，其中 147 檔有行情：共 3,075 列、21 份日表、147 份每股月表。前 12 個日表為 146 檔，後 9 個為 147 檔。

| 股票 | 2025-09 資料 | 已核對原因 |
|---|---|---|
| 3718、7769、7828 | 各 0 筆 | 上市／上櫃日在該月之後 |
| 7750 | 9/17～9/30，共 9 筆 | 該月 9/17 上市 |

官方日期與來源見 [歷史行情可取得範圍](history_availability_2025-09.md)。維持原 150 檔名單，不補零、不用其他代號或興櫃行情替代。後續擴期間的缺失處理留在 checklist DATA-22，目前沿既有紀錄進行分析。

可查看既有 [manifest](../data/cache/history_universe/2025-09/20261011T145716_6e56c903/manifest.json)、[逐日覆蓋](../data/cache/history_universe/2025-09/20261011T145716_6e56c903/coverage.json)、[品質限制](../data/cache/history_universe/2025-09/20261011T145716_6e56c903/data_quality.json)、[9/1 日表](../data/cache/history_universe/2025-09/20261011T145716_6e56c903/daily/2025-09/2025-09-01_prices.csv) 與 [2330 月表](../data/cache/history_universe/2025-09/20261011T145716_6e56c903/monthly/2025-09/TWSE_2330_2025-09.csv)。

三檔指定市場缺件使這次下載 `success=false`，但成功資料與失敗回應均保存。原價、調整價與歷史公開時間的限制仍有效，`submission_ready=false`。

## 兩檔樣本與離線匯出

`history-sample` 固定取得 2330／5274，供小量下載測試；再次執行會建立新樣本目錄：

```powershell
python -B -m etf_agent.cli history-sample --month 2025-09 --output data/cache/history_sample --transport curl
```

`history-export` 只支援這兩檔樣本，讀已保存的官方 raw JSON，完全離線另建 CSV：

```powershell
python -B -m etf_agent.cli history-export --manifest data/cache/history_universe/2025-09/20261011T145716_6e56c903/sample_manifest.json --output data/cache/history_export
```

以上 manifest 與兩檔 raw 已保存在全股票目錄，原 `history_sample` 重複快取已清理；仍可離線重建 42 列／21 個日表。早期驗收與原報告保存在 [provenance/history_sample](../data/cache/history_universe/2025-09/20261011T145716_6e56c903/provenance/history_sample/)，對應索引見 [cleanup.json](../data/cache/history_universe/2025-09/20261011T145716_6e56c903/provenance/history_sample/cleanup.json)。全股票重建使用前述 `history-universe --cache-manifest`，不要將全股票 manifest 交給 `history-export`。

## 每日覆蓋檢查

`prices-check` 離線核對日表格式、基本價格有效性及 F05 股票覆蓋：

```powershell
python -B -m etf_agent.cli prices-check --prices data/cache/history_universe/2025-09/20261011T145716_6e56c903/daily/2025-09/2025-09-01_prices.csv --date 2025-09-01 --output data/cache/coverage
```

`--date` 是預期資料日，並非決策日；預設使用 `data/universe.csv`，可另設 `--universe`／`--universe-manifest`。加入 `--json` 輸出完整報告與產物路徑。

每次另建 `data/cache/coverage/<資料日>/<版本>/`，保存 `coverage.json`、`coverage.md`、`missing_stocks.csv`。已取得股票、有效價格及原輸入 `tradable=true` 分開統計；覆蓋完整不代表正式可交易。

早期兩檔示例的 [舊覆蓋報告](../data/cache/coverage/2025-09-01/20261011T144802_4463a889/coverage.md) 保存當時 2／150 結果及原路徑。若要重現，改讀 [保存的兩檔日表](../data/cache/history_universe/2025-09/20261011T145716_6e56c903/provenance/history_sample/input/2025-09-01_prices.csv)；日常分析使用全股票 daily。

## 退碼與後續步驟

| 命令 | 退碼 0 | 退碼 2 |
|---|---|---|
| `history-universe`、`history-sample`、`history-export` | 各指定來源取得／解析或匯出成功 | 有來源失敗、錯誤快取或輸入／執行錯誤；先查看保存報告 |
| `prices-check` | `input_valid=true`，即使股票覆蓋不完整 | 日表輸入格式無效或載入／執行錯誤 |

行情完成後，使用 [官方排程與價格視窗](calendar_windows.md) 找到可分析股票，再用 [三因子分析](factor_analysis.md) 產生 CSV 與閱讀摘要。沒有資料下載命令會自行呼叫投資模型或產生正式 D-Plan。
