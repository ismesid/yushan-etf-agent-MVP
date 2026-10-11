# 封存後的隔離收益與事後最佳化

`evaluate-plan` 由 `sub_agents/test_agent.evaluate_trade_day` 組合執行。先核對真實模型決策已封存、本地驗證通過、輸入／產物／決策程式 hash 一致，才下載指定交易日行情。這個流程沒有新模型呼叫，也不改寫原 D-Plan、九月資料、策略設定或期初帳戶。

## 日期與隔離

此次決策只使用截至 **2025-09-30** 的資料，交易日為 **2025-10-01**。獨立的 `data/cache/evaluation_quarantine/2025-10-01/<run>/` 保存後驗行情與評估；原 shared run 的 workspace、決策資料包與模型輸入保持不變。所有評估 manifest 與報告均標 `decision_input_allowed=false`。評估目錄放進原決策目錄會被拒絕，完成後再次核對原凍結檔案。

行情從 [TWSE 單日全市場報表](https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date=20251001&type=ALLBUT0999&response=json) 及 [TPEx 單日全市場報表](https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes?date=2025%2F10%2F01&response=json) 各取得一次，保存原始 JSON、URL、單位及 SHA-256。只保留當日候選與原持股；不查十月月報、不使用回應中的次日參考價。日期、欄位、量值單位及重碼不符會停止。

`trading_status` 區分 `traded`、官方量值皆零的 `no_trade`、資料不足的 `unknown`。3260 的10/1原報表為收盤 `---`、成交股數0、成交金額0，保留候選列但不可交易，價格與均價留空；它不是先前3718／7750／7769／7828的歷史視窗問題。本次沒有重新查核或補那些缺件。

## 收益怎麼計算

三個情境使用相同9/30人工期初帳戶，NAV **1,000,000,000元**、25檔持股、現金107,067,500元：

1. 原持股不交易：現金不變，持股以10/1收盤估值。
2. 凍結 D-Plan：固定原25筆委託股數，按10/1官方日均價模擬成交，不以事後行情重新計算原股數。
3. 全候選事後配置：重新搜尋股票與整張股數，以費後10/1收盤NAV為目標。

[F07 v4.2 §⑥](../specs/official/07_D-Plan_guide_v4.2.md) 定義日均價為當日成交金額÷成交股數，買賣各收0.1425%費用、賣出另收0.3%稅。程式以50位 `Decimal` 計算，股數用股、金額用元、價格用元／股，比率用0～1；未知為null／CSV空欄。

`期末NAV = 期末現金 + Σ(期末持股 × 10/1收盤價)`；`收益 = 期末NAV − 9/30期初NAV`。逐筆的 `benefit_vs_skip_twd = 股數增減 × (收盤 − 日均價) − 費稅`，衡量該筆交易相對不交易的貢獻；個別負貢獻不代表可以把所有負貢獻單一起取消而仍滿足組合限制。

缺成交均價的委託為 `unfilled_missing_vwap`，不增減該股或扣款；原持股仍保留。缺期末估值時，已知市值另列，但總NAV／收益為null，不把未知補零。模擬結果另輸出 `AccountSnapshot 1.0`、`status=simulated`、`demo=true`、`reconciled=false`，不更新 canonical fixture、正式帳務或 account_agent 的當日決策輸入。

這是價格收益模擬，採同日現金淨額結算，沒有撮合容量、滑價或主辦方結算紀錄；股利、公司行動、費用取整及正式權重取價仍待核對。`real_market_data=true`、`real_fills=false`，正式／提交資格始終false。

## 「最佳」的範圍

使用 [SciPy `milp`／HiGHS](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.milp.html) 搜尋完整146檔候選的整張目標／買進／賣出股數，最大化當日費後NAV。3260保留在池內，因確定零成交且原未持有而目標固定0；其餘145檔可成交。一般缺資料會阻擋完整最佳主張，不自行縮小池。

限制來自F04／F07的整張、不超賣、不放空、不做同股雙向交易、20～30檔持股、最多30筆委託、現金0～25%、2330上限25%／其他股10%。另外同時檢查前收預估費後與10/1收盤費後的現金、單股權重，並限制前收目標市值75～100%期初NAV，使目標股數可由官方前收權重公式達成。這是明列的財務搜尋範圍，不等於完成正式來源、流動性、投資主題、模型理由或官方D-Plan驗證。

最佳化重新選擇現金比例，不沿用原模型的12%現金目標；40／25／35因子權重及原策略設定不變。純數學配置可能保留部分原股各1張，以滿足最低持股檔數；不能把這種後驗配置當成可預測的投資建議。

求解器上限預設120秒，`mip_rel_gap=1e-8`；回報 status、上界、差距、節點與版本。只有 status0且整數／Decimal財務重验通過才標 `optimal_to_solver_tolerance=true`；超時可行解標 `feasible_limit_reached`，未證明最佳。浮點候選未通過精確重算時拒絕，不放寬財務門檻。此次gap為0，求解上界與Decimal NAV微小差別屬浮點表示。

## 執行與離線重播

從專案根目錄安裝一次已授權的評估額外依賴：

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[evaluation]"
$env:PYTHONPATH = (Resolve-Path -LiteralPath 'src').Path
```

首次執行會向兩個官方單日入口下載；本次已執行，不必再下載：

```powershell
$taskDecisionWorkspace = 'data/cache/integrated_runs/2025-10-01/20261011T181709_8585216a/workspace.json'
.\.venv\Scripts\python.exe -B -m etf_agent.cli evaluate-plan --workspace $taskDecisionWorkspace --time-limit 120 --json
```

使用本機現存隔離行情離線重算，沒有HTTP或模型呼叫；`--market-manifest` 明確指向本次評估輸出的檔案：

```powershell
$taskEvaluationMarket = 'data/cache/evaluation_quarantine/2025-10-01/20261011T190922_e164811e/market_manifest.json'
.\.venv\Scripts\python.exe -B -m etf_agent.cli evaluate-plan --workspace $taskDecisionWorkspace --market-manifest $taskEvaluationMarket --time-limit 120 --json
```

會新增獨立評估run，重新核對原hash與隔離raw，不再扣同一帳的款。這是從同一期初帳重演，不是有重複入帳保護的正式ledger；SQLite、plan版本採用與主辦方逐股核對留待後續。

## 人工檢查的檔案

| 檔案 | 用途 |
|---|---|
| `market_quotes.csv`／JSON | 146候選當日量值、收盤、均價、無成交狀態、來源與hash |
| `performance.csv` | 不交易、凍結計畫、事後配置的現金／股票市值／NAV／收益／費稅 |
| `fills.csv` | 原25筆委託、模擬股數、日均價、費稅、現金與逐筆貢獻 |
| `end_positions.csv` | 原持股與買入股聯集，退出股保留0股 |
| `hindsight_ranking.csv` | 146候選的前收→收盤、日均價買進→收盤費後報酬排行，無成交保留空欄 |
| `hindsight_orders.csv`／`hindsight_positions.csv` | 事後配置的委託／期末股數與市值 |
| `review_recommendations.csv` | 原委託後驗貢獻、最佳目標股數與檢討提示 |
| `review_report.json`／`hindsight_optimization.json` | 情境、假設、問題、求解上界與精確驗收；不是投資模型回覆 |
| `simulated_account.json`／`hindsight_account.json` | 分開的模擬帳，未正式核對，未回寫期初帳 |
| `freeze_gate.json`／`manifest.json`／`code/` | 原封存hash、評估程式版本、CSV／JSON／raw hashes與隔離證據 |

8份CSV使用UTF-8 BOM，與同份JSON核對；主資料仍是JSON。這批只在隔離區完成收益與事後檢討，沒有自動回流建議。接到下一日決策前，須另批決定可用日期、模擬／正式帳戶來源與檢討報告合約，避免把事後最佳當作已知訊號。

## 第25批實跑

完成run為 `data/cache/evaluation_quarantine/2025-10-01/20261011T190922_e164811e/`。期初NAV10億元、25檔；金額以下四捨五入至小數2位供閱讀，JSON／CSV保留完整Decimal：

| 情境 | 期末NAV（元） | 收益（元） | 報酬率 |
|---|---:|---:|---:|
| 原持股不交易 | 1,002,462,850.00 | +2,462,850.00 | +0.246285% |
| 凍結D-Plan | 997,597,714.46 | −2,402,285.54 | −0.240229% |
| 全候選事後配置 | 1,017,594,987.95 | +17,594,987.95 | +1.759499% |

原計畫25筆全部有均價、模擬20檔持股；手續費1,517,797.87元、稅1,619,703.26元、費後現金118,610,864.46元，全部本批財務檢查通過。相對不交易少4,865,135.54元，這一日結果不能證明策略長期優劣。

最佳化保留146候選、3260零成交固定0、145可成交，HiGHS status0／gap0／1節點；30筆委託、20檔正持股、現金20,337.95元。與原計畫NAV差19,997,273.48元，只是事後機會差距。146 target_shares保留於最佳化JSON，33列最佳持股聯集包含退出0股；它不產生替換原D-Plan。

本批實際成功下載2次，初次沙盒網路被阻擋後依工具權限流程執行。TPEx民國表格日期解析首次失敗，隔離raw保留；修正後重用兩份已下載原文，不再HTTP。第一次未保存的fetched_at／effective_url／content_type維持null、`source_metadata_recovered=true`，不拿檔案時間編造取得時刻。之後單次請求立即保存source metadata sidecar，即使解析失敗也能回查。

最終離線重播與首次完整成功run的兩種模擬及最佳化JSON完全一致。8CSV列數146／3／25／35／146／30／33／25，63產物hash（含41個評估程式／設定封存檔）及原73凍結檔hash全通過，評估內容版本 `sha256:86f79658b6b5`。獨立分工再次核對量值、逐筆費稅、兩種取價的cash／caps及股數。daily11＋evaluation12＋既有review4，共27相關測試通過；未跑全套，未新呼叫模型，未commit／push。
