# 官方排程與 21 筆價格視窗

這份文件說明日曆取得、歷史價格視窗檢查及缺失日期的閱讀方式。先依 [環境與基本使用](quickstart.md) 設定 `PYTHONPATH`，並準備 [全股票歷史日表](history_data.md)。

## 取得官方排程

```powershell
python -B -m etf_agent.cli calendar-download --month 2025-09 --output data/cache/calendar --transport curl
```

命令對 TWSE 與 TPEx 各發出一次官方 HTTPS 請求，取得該年度開休市表，再產生指定已完成月份的日曆。`--transport` 可用 auto／urllib／curl。

每次另建 `data/cache/calendar/<月份>/<執行版本>/`：

```text
├─ raw/TWSE_2025.json
├─ raw/TPEX_2025.json
├─ calendar.json        # 官方來源、取得時間、hash、版本及分市場日期
└─ calendar.csv         # 一列一市場一日期，包含開休市與原因
```

來源為 TWSE `holidaySchedule` 與 TPEx `bulletin/tradingDate`。程式核對回應年度：TWSE 以 `date=YYYY0101` 查詢；TPEx 依 HTML 民國年度標題辨識，排除債券專屬列。若收到錯年資料會停止；失敗回應保留以供檢查。

日曆以例行週一至週五及官方排程事件建立。`calendar_basis=official_schedule`、`schedule_verified=true`；天然災害等臨時全市場休市尚未全面核實，`actual_sessions_verified=false`。它是排程核對基礎，不能宣稱已確認所有實際交易日。

現有 2025-09 日曆兩市場各 21 個排程交易日，9/29 排程休市。可查看 calendar.csv（本機路徑 `data/cache/calendar/2025-09/20261011T154421_1306c9a4/calendar.csv`） 與 calendar.json（本機路徑 `data/cache/calendar/2025-09/20261011T154421_1306c9a4/calendar.json`）。

## 價格視窗檢查

21 筆收盤價可形成 20 個相鄰日報酬期間。視窗命令按各股票所屬市場，核對截至指定資料日最近 21 個排程日期是否有有效價格：

```powershell
python -B -m etf_agent.cli history-window-check --manifest data/cache/history_universe/2025-09/20261011T145716_6e56c903/manifest.json --calendar data/cache/calendar/2025-09/20261011T154421_1306c9a4/calendar.json --as-of 2025-09-30 --output data/cache/history_windows
```

這個命令完全離線，讀本機 raw 日曆、全股票 manifest 與所需 daily CSV。若剛下載了新資料／日曆，換用 CLI 顯示的新 `manifest.json`／`calendar.json` 路徑。預設股票池是 `data/universe.csv`，亦可設 `--universe`／`--universe-manifest`。

`--as-of` 是**包含當日在內的已完成歷史資料截止日**，不是該日盤前決策日。例如 `2025-09-30` 允許讀 9/30 收盤資料，但不能把它拿來模擬 9/30 盤前已知資訊。命令不讀截止日之後的日表，也不讀 monthly 重複視圖。

目前只支援同月份：當月截止日前不足 21 個排程日，列出 `calendar_window_shortfall`，尚不回讀前一月份。缺股票、無效價格或缺整日日表均保留原預期日期，不縮短視窗、不補零。

## 輸出與閱讀

每次另建 `data/cache/history_windows/<截止日>/<執行版本>/`：

| 檔案 | 用途 |
|---|---|
| `window_coverage.csv` | 150 檔逐股價格筆數、狀態、缺失／無效日期 |
| `window_report.json` | 共用預期日期、來源版本、讀取日表、完整錯誤及逐股狀態 |

解釋集中在本頁，每次執行只產生 CSV／JSON。閱讀 CSV 已移除各股重複的 `expected_dates`；共同日期保存在 JSON／日曆。`missing_dates` 與 `invalid_price_dates` 只在有缺失或無效價格時填寫，以分號分隔日期。`window_complete=true` 表示該股票在目前排程下有全部需要的有效價格。

現有截至 2025-09-30 的結果：

| 範圍 | 有效價格 | 視窗狀態 |
|---|---:|---|
| 146 檔 | 各 21 筆 | 完整 |
| 7750 | 9 筆 | 缺 9/17 掛牌前的 12 個排程日 |
| 3718、7769、7828 | 各 0 筆 | 各缺 21 個排程日，該月尚未在指定市場掛牌 |

沒有缺整日日表，`input_valid=true`。可查看 150 檔 CSV（本機路徑 `data/cache/history_windows/2025-09-30/20261011T154440_9842e79e/window_coverage.csv`）與完整 JSON（本機路徑 `data/cache/history_windows/2025-09-30/20261011T154440_9842e79e/window_report.json`）。掛牌原因見 [歷史行情可取得範圍](history_availability_2025-09.md)。

## 退碼與限制

`calendar-download` 的退碼 0 表示排程取得／解析成功，2 表示輸入、來源或執行失敗。它不因成功就把臨時休市核實旗標改成 true。

`history-window-check` 的退碼 0 表示 `input_valid=true`，即使部分股票價格不足；2 表示資料格式、日曆／白名單載入或執行錯誤。應分別看 `input_valid`、`window_complete` 及缺失紀錄。

價格完整仍未證明公司行動、調整價、歷史 `known_at`、個股停牌、正式截止或帳戶已核實，`submission_ready=false`。四檔已知不足沿原紀錄保存，後續缺失處理在 [checklist DATA-22](../checklist.md)；目前先使用 146 檔完整視窗做 [三因子分析](factor_analysis.md)。

日曆／視窗的必要測試指令見 [環境與基本使用](quickstart.md#必要測試)；實際批次驗收見 [開發紀錄](../development_notes.md)。
