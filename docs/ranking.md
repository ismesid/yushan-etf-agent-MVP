# 三因子排名：分數、權重與執行方式

文件版本：1.0｜更新：2026-10-11｜對應設計：[design1001.md §8.1](../design1001.md)

本頁說明歷史原價三因子的相對排名。指標意義與權重查詢來源見 [三因子分析](factor_analysis.md)，整體架構見 [README](../README.md)。目前的排名母體是截至 2025-09-30 有完整視窗的 146 檔；排名表示同一批股票的相對位置，不是預測報酬或正式可交易名單。

## 怎麼計算

先讀 `history-features` 產生的 `metadata.json`，使用 `rows[].values` 的精確小數比率。CSV 已顯示六位百分數，僅供閱讀，不作排名輸入。所有股票使用同一個因子組合與配比；四檔視窗不足紀錄沿用原分析，不補零、也不逐股改權重。

每個因子按原始值由小到大排：相同值取平均名次。若有 `N > 1` 檔，分位得分為 `p = (平均名次 - 1) / (N - 1)`；單一股票或某因子全部相同時，該因子得分為 `0.5`。空的分析母體會報錯。

例如三股動能為 2%、4%、4%，平均名次是 1、2.5、2.5，動能得分是 0、0.75、0.75。最低與最高值平手時不一定落在 0 或 1，仍依平均名次計算。

| 因子 | 得分方式 | 配比 | 初始策略假設 |
|---|---|---:|---|
| `mom20` 動能 | `p(mom20)` | 40% | 近期原價表現較強，得分較高。 |
| `trend20` 均線偏離 | `p(trend20)` | 25% | 末價相對近期均線較高，得分較高；過熱或回撤仍待檢驗。 |
| `lowvol20` 低波動 | `1 - p(vol20)` | 35% | 近期波動較低，得分較高；不代表無風險。 |

綜合分數為 `score = 0.40 × rank_mom20 + 0.25 × rank_trend20 + 0.35 × rank_lowvol20`。只反向一次波動，不先取負再反向。原始值、因子得分與每項貢獻分開保存；分數由大到小排序，總分相同時按股票代號升序，最後名次為連續正整數。分位及加權總分先用標準庫 Fraction（精確分數）計算與排序，再轉為 34 位 Decimal 字串；例如 1/145 的循環小數不會在排序前捨入而拆開真正平手。

用一個**說明用假例子**：三個得分若是 0.8、0.6、0.7，貢獻是 0.32、0.15、0.245，總分是 0.715。CSV 顯示三項貢獻 32、15、24.5 分，總分 71.5 分；這些分數是相對位置的加權結果，並不表示會賺 71.5%。

40／25／35 是使用者已同意的 MVP 初始配比，來自專案草案，目前沒有文獻證明此精確配比是業界標準或最佳值。公開方法、來源連結及開會問題集中在 [權重查詢紀錄](factor_analysis.md#權重查詢紀錄供開會討論)。

## 設定與模組責任

[config/ranking.json](../config/ranking.json) 集中設定，`factor_profile=price_only_v1`，啟用 `mom20`、`trend20`、`lowvol20`；權重以十進位字串保存，合計須為 1。此版只處理這個三因子組合；新增因子須同步計算與輸入合約，不能僅在設定寫入任意名稱。

[ranking.py](../src/etf_agent/ranking.py) 的 `calculate_factor_rankings()` 是純計算，與讀檔及匯出分開。`analyze_history_rankings()` 讀取特徵 JSON／設定並保存輸入版本與 SHA-256；`write_ranking_analysis()` 建立新的結果目錄。[CLI](../src/etf_agent/cli.py) 組合這三步。全程使用 Python 標準庫，不抓行情、不呼叫投資模型，也不改帳戶。

## 執行與重算

在專案根目錄用 PowerShell 執行，替換為前一步顯示的特徵 metadata 路徑：

```powershell
$env:PYTHONPATH = (Resolve-Path -LiteralPath 'src').Path
python -B -m etf_agent.cli history-rankings --feature-metadata data/cache/features/2025-09-30/20261011T160349_3b42fa16/metadata.json --profile config/ranking.json --output data/cache/rankings
```

`--feature-metadata` 必填；`--profile` 預設 `config/ranking.json`，`--output` 預設 `data/cache/rankings`。只讀既有特徵與設定，離線計算；不重抓行情或重算三因子。成功時顯示排名檔、metadata 與本頁位置，回傳 exit 0。輸入格式、股票／因子數值或配比不符時回傳 exit 2，應核對對應輸入，不能用補值強行繼續。

每次另建 `data/cache/rankings/<as_of>/<執行版本>/`，不覆寫舊版。相同輸入與設定產生相同數值與 `ranking_version`，執行時間與目錄另行保存。`as_of` 是歷史資料截止日，並非已證明當日盤前可知的決策時間。

## 先看哪個檔案

| 檔案 | 用途 | 閱讀注意事項 |
|---|---|---|
| `rankings.csv` | 用 Excel 排序與對照每股原始值、因子得分、貢獻及總分。 | UTF-8 BOM，數值顯示六位小數，`ROUND_HALF_UP`；一股一列，依總分排序。 |
| `metadata.json` | 核對精確值、完整設定、來源版本、輸入 hash、排除紀錄及限制。 | 得分為 0～1 的 Decimal 字串，以 34 位精度、`ROUND_HALF_EVEN` 輸出；保存原特徵來源，便於逐股回查。 |

CSV 共 16 欄：

| 欄位 | 單位與意義 |
|---|---|
| `rank`、`ticker`、`name`、`market` | 本批綜合名次、股票代號、名稱及市場。 |
| `mom20_pct`、`trend20_pct`、`vol20_annual_pct` | 原始三因子的百分數；例如 10 代表 10%。 |
| `rank_mom20_pct`、`rank_trend20_pct`、`rank_lowvol20_pct` | 因子得分乘以 100，範圍 0～100 分；欄名的 `_pct` 是換算顯示，不是報酬率。 |
| `contribution_mom20_pct`、`contribution_trend20_pct`、`contribution_lowvol20_pct` | 各因子得分乘上配比，再乘 100；三項加總為總分，顯示四捨五入可能有極小差異。 |
| `score_pct` | 綜合分數乘以 100，範圍 0～100 分；不是預測報酬。 |
| `analysis_included`、`formal_eligible` | 是否納入本批分析與是否已確認正式資格；本批已排名股票為 true／false。 |

JSON `rows[].values` 保留原始精確比率，`rank_scores` 與 `contributions` 各含 `mom20`、`trend20`、`lowvol20`，`score` 保存 34 位精度的總分，`rank` 是最終名次。每股沿用 `source_metadata`。共同 metadata 保留 `feature_version`、股票池／日曆版本、完整 `profile`、輸入路徑與 hash、`ranking_version`、統計及 `excluded_stocks`。

生成結果保留在 Git 忽略的本機快取；本頁是固定解釋，不為每次執行另產生重複 Markdown。

## 2025-09-30 固定歷史例子

以下是使用既有歷史原價因子及 40／25／35 配比實際產生的排名：150 檔中有 146 檔參與，四檔排除為 3718、7750、7769、7828；執行版本 `20261011T165509_b1899354`，排名版本 `price-rankings-v1-3f25120fa996`。這份表保留當次例子，不隨後續執行更新；分數依同批股票的相對位置計算，仍屬歷史分析，未驗證正式選股或回測表現。

| 名次 | 股票 | 綜合分數（分） |
|---:|---|---:|
| 1 | 3231 緯創 | 78.482759 |
| 2 | 2382 廣達 | 78.206897 |
| 3 | 2303 聯電 | 76.758621 |
| 4 | 2887 台新新光金 | 76.275862 |
| 5 | 3227 原相 | 75.586207 |
| 7 | 2330 台積電 | 73.655172 |

2330 的原始動能、均線偏離、年化波動見 [因子歷史例子](factor_analysis.md#目前的真實歷史例子)；轉成同批因子得分後，依序為 76.551724、76.551724、68.275862 分，低波動得分已反向。按 40／25／35 合成後排名第 7，這表示本批的相對位置，不能用來推論下一個月報酬。

每一欄都獨立顯示到六位小數。例如緯創的三項貢獻為 36.965517、24.137931、17.379310 分，這三個顯示值相加是 78.482758 分，而 `score_pct` 顯示 78.482759 分；差 0.000001 分來自各欄獨立四捨五入。計算與排序使用精確分數，不用 CSV 的顯示值重算總分或名次。

完整結果可在本機用 Excel／IDE 開啟：

- `data/cache/rankings/2025-09-30/20261011T165509_b1899354/rankings.csv`
- `data/cache/rankings/2025-09-30/20261011T165509_b1899354/metadata.json`

## 分析範圍與後續

146 檔表示有完整原價因子可參與比較；3718、7750、7769、7828 沿用四檔不足紀錄，不參與本批排名。`formal_eligible=false`、`submission_ready=false` 維持：公司行動、`known_at`、臨時休市、流動性與正式候選資格仍待核實，排名也尚未串接正式 `MarketSnapshot`／`FeatureTable`。

排名與正式持股配置是不同步驟。後續需補候選資格、證據包及真實模型決策，再處理配置與風控；目前未自動選前 25 檔、決定買賣或配置股票權重。更多歷史期間、因子相關性、配比比較與含成本回測，留待下一批討論。

必要檢查聚焦手算與平手、低波動方向、實際股票集合及重算一致；可依本批修改重跑，不必只因閱讀文件而執行全套：

```powershell
python -B -m unittest discover -s tests -p test_ranking.py -v
```
