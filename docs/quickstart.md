# 環境與基本使用

這份文件說明環境設定、可離線執行的基本命令、必要測試與版本管理。整體架構見 [README](../README.md)。

## 環境設定

需要 Python 3.11 以上，目前程式與測試只使用標準庫，沒有第三方 Python 依賴。從專案根目錄開啟 PowerShell：

```powershell
python --version
$env:PYTHONPATH = (Resolve-Path 'src').Path
python -B -m etf_agent.cli --help
```

`PYTHONPATH` 讓 Python 找到 `src/etf_agent`，設定只影響目前 PowerShell 工作階段；另開終端時重新設定。`-B` 避免執行時產生 Python 位元碼快取。

九個命令的個別參數可用 `--help` 查看，例如：

```powershell
python -B -m etf_agent.cli history-universe --help
python -B -m etf_agent.cli history-features --help
```

下載命令的 `--transport auto` 優先使用系統既有 curl，否則使用 Python `urllib`；也可明確選 `curl` 或 `urllib`。都保留 HTTPS 憑證驗證，不需為目前功能另安裝 Python 套件。

## 合約示例

新 clone 可直接執行此命令，不需行情快取、不連網、不呼叫模型：

```powershell
python -B -m etf_agent.cli contracts-demo --fixture tests/fixtures/contracts_demo.json
```

示例載入六種核心合約（MarketSnapshot、AccountSnapshot、FeatureTable、AgentDraft、PortfolioProposal、ValidationReport），以及 DatasetSplitPlan 與 AgentResult。它展示 JSON 往返、帳戶市值／現金核對與資料格式，全部為人工測試資料。

預期重點：

```text
JSON 往返：PASS
持股：25 檔
現金：10,000,000 元
股票市值：90,000,000 元
NAV：100,000,000 元
現金＋股票市值核對：PASS
submission_ready：false
```

加入 `--json` 可輸出機器可讀摘要。fixture 中的因子與選股是假值，模型版本及用量為 null；這個命令沒有產生正式 D-Plan。

fixture 示範 2020～2023 訓練、2024 驗證、2025～2026-09 測試的時間切分設定，並沒有對應的長期歷史資料或已完成回測。詳見 [資料合約](data_contracts.md)。

## 白名單核對

```powershell
python -B -m etf_agent.cli universe-check --universe data/universe.csv
```

預期核對格式、檔數與來源雜湊 PASS：150 檔、TWSE 100／TPEX 50，代號無重複。來源是官方 F05 v1；[universe.csv](../data/universe.csv) 保存股票，配套 [manifest](../data/universe.manifest.json) 保存來源版本。

預設使用白名單同名 `.manifest.json`；`--manifest` 可指定其他來源紀錄，`--json` 可輸出摘要。競賽白名單不等於每個歷史日期的可投資股票池；歷史掛牌範圍仍需另外判斷。

## 必要測試

日常修改優先執行受影響的測試。從根目錄、已設定 `PYTHONPATH` 的 PowerShell 執行，例如：

```powershell
python -B -m unittest discover -s tests -p test_contracts.py -v
python -B -m unittest discover -s tests -p test_features.py -v
python -B -m unittest discover -s tests -p 'test_*.py' -k CalendarTests -k HistoryWindowTests -v
```

第一條驗核心合約，第二條驗因子，第三條驗日曆與價格視窗；依當批修改選擇。只有跨模組或共用規則變更等需要整體確認時，才擴大執行：

```powershell
python -B -m unittest discover -s tests -p 'test_*.py' -v
```

這些是可重跑的指令，不表示每批都已跑過全套；實際結果與未執行範圍記在 [development_notes.md](../development_notes.md)。

## 產物與版本管理

程式、官方參考來源及白名單放在倉庫；行情與分析各次執行另建 `data/cache/<功能>/<月份或截止日>/<執行版本>/`。新產物不覆寫舊版本，下一個命令應使用剛產生的 manifest／報告路徑。

[.gitignore](../.gitignore) 忽略 `data/cache/`、真實帳戶 `data/account/`、執行產物、資料庫、日誌、金鑰與本機設定。文件所列快取路徑供本機查閱，GitHub 的可點擊入口連到已提交的說明；需要重建時依序使用 [歷史資料](history_data.md)、[日曆／視窗](calendar_windows.md)、[三因子分析](factor_analysis.md)。

每次提交前先檢查差異，明確加入本批檔案；以下只是合約與文件修改的示例：

```powershell
git status
git diff
git add src/etf_agent/contracts.py docs/data_contracts.md development_notes.md checklist.md
git commit -m "Update contracts and development notes"
git push
```

`git push` 需已設定 GitHub 遠端與分支追蹤關係。金鑰、真實帳戶及大量行情快取保留在忽略的位置。

CLI 的一般退碼為 0 成功、2 輸入或執行失敗；下載及覆蓋命令對缺資料的解讀不同，詳見 [歷史資料](history_data.md) 與 [價格視窗](calendar_windows.md)。
