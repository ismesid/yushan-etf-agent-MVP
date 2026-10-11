# 開發紀錄

日期：2026-10-11｜批次：01 共用合約與離線示例

## 授權與版本

- 使用者已明確同意第一批：Python 標準庫 `dataclass`／`Decimal`，六種共用合約、`AgentProvider` 介面、含既有持股的 demo fixture、CLI 及必要 `unittest`。
- 使用者追加：建立簡明 `diary.md`；為日後回測保留歷史與時間版本，訓練留出較新的測試期。這批增加 `DatasetSplitPlan` 與日期切分檢查。
- 已依根目錄 AGENTS.md v1.0、design1001.md v0.3、checklist.md（均 2026-10-11）合作。本會話第一輪已閱讀九份 F01–F09；本批沿用原版本、不修改來源。
- 本批安裝依賴、抓外部資料、投資決策模型呼叫、SQLite 帳本、完整因子、配置、D-Plan 編譯、提交或交易皆不在範圍內。

## 決定與理由

| 決定 | 理由 |
|---|---|
| 六種核心合約集中定義，金額用 Decimal／JSON 十進位字串，股數用整數 | 模組一致、可追溯與重播；HTTP／SDK 不進核心 |
| 草稿不接受 shares／orders／自造欄位 | 模型提意圖，數值和最終股數由程式處理 |
| demo 含 25 檔既有持股、現金 1,000 萬、NAV 1 億 | 後續能展示續抱、異動及帳務；不是正式期初帳 |
| 預留行情多日期／多版本與原價／因子價格 | 後續回測與公司行動處理不必重設整個格式 |
| train／validation／test 按時間分，保留較新 test 及標籤／gap 欄位 | 防資料洩漏；真正交易日隔離、標籤跨界檢查後續實作 |
| SQLite 帳務／必要索引，JSON／CSV 行情及產物 | 可本機檢查與備份；存儲尚待對應批次實作 |

設計中的策略權重、風控閾值尚未在本批定案。時間切分與 demo 數值為專案決定，不是官方規則。

## 本批檔案與驗收

已新增：

- 專案：`pyproject.toml`、`src/etf_agent/__init__.py`。
- 核心：`src/etf_agent/contracts.py`、`src/etf_agent/cli.py`、`src/etf_agent/agent/__init__.py`、`src/etf_agent/agent/base.py`。
- 合約與檢查：`specs/internal/agent_draft.schema.json`、`tests/fixtures/contracts_demo.json`、`tests/test_contracts.py`。
- 文件：`docs/data_contracts.md`、`diary.md`、本檔；`checklist.md` 由整合者更新證據。

實際結果：

| 指令／檢查 | 結果 |
|---|---|
| `python -B -m etf_agent.cli --help` | exit code 0 |
| `python -B -m etf_agent.cli contracts-demo --fixture tests/fixtures/contracts_demo.json` | exit code 0；八種合約 JSON 往返 PASS；26 列行情、兩個資料日、25 檔原持股、25 selections／25 reviews |
| demo 資產核對 | cash `10000000.00`＋stock value `90000000.00`＝NAV `100000000.00`，PASS |
| `python -B -m unittest discover -s tests -p test_contracts.py -v` | Ran 30 tests in 0.542s，OK |
| CLI 缺檔輸入 | 回傳 exit code 2 與清楚錯誤 |

在 PowerShell 重跑前設定 `$env:PYTHONPATH = (Resolve-Path 'src').Path`；完整命令見 `docs/data_contracts.md`。fixture 的價量、帳戶、草稿及因子皆為人工測試值；實際模型版本及用量是 null，`submission_ready=false`。

schema 只驗證 JSON 可讀及檢查結構，沒有執行 `jsonschema` 或官方 F04 完整驗證，原因是本批僅使用標準庫、未安裝依賴。沒有建立虛擬環境、初始化 git、建 SQLite、抓行情或呼叫投資模型。本批未完成正式因子、股數／費用計算、成交、核對或訓練／回測。

## 阻礙與下一步

- 尚未取得或確認：正式期初帳／本金、截止時刻與資訊區間、費用取整、公司行動、無成交與現金比例口徑、官方驗證器及完整 AI 資格要求。
- 本批只驗合約；白名單完整擷取、官方行情、真實交易日曆、因子、配置、帳務、官方結構／語意驗證及時間防洩漏的完整流程仍未完成。
- 回測還需決定歷史範圍、測試期長度、預測標籤與 gap，確認修正資料的當時可知版本、公司行動及存續偏差。
- 下一批建議先展示本批合約與 demo，再討論 F05 擷取為 150 檔 universe 與規則索引，接著討論歷史存檔／官方資料取得；未取得下一批明確同意前停止擴充。

## Git-01｜GitHub 版本管理（2026-10-11）

- 授權：使用者明確要求將現有專案建立為 GitHub repository，範圍包含本地 Git 初始化、必要說明／忽略設定、提交、建立遠端及推送。此要求不授權後續 ETF 功能批次。
- 本地：已初始化 `main`；沿用既有 Git 作者設定。新增 `README.md`、`.gitignore`、`.gitattributes`，官方來源設為不做文字換行轉換。
- 排除：環境金鑰、本機設定、真實帳戶、行情快取、產生的 runs／exports、SQLite 及日誌；測試 fixture 與官方參考來源保留。
- GitHub：已建立私有 [ismesid/yushan-etf-agent](https://github.com/ismesid/yushan-etf-agent)，`origin=https://github.com/ismesid/yushan-etf-agent.git`。用既有 Git Credential Manager 登入與 Python 標準庫完成，憑證僅在記憶體中使用，沒有安裝新套件。
- 驗證：忽略規則已命中 `.env`、`data/account/`、`data/cache/`、`runs/`；文字檔金鑰模式檢查無匹配。程式未變，本批不重跑既有 30 項合約測試。
- 提交／推送：初始提交 `d6cd05f` 成功推送，`main` 已追蹤 `origin/main`；九份官方檔案的工作檔與 Git blob SHA-256 比對全部相同。日記、README 及本紀錄的完成證據另作文件提交。
- Windows 環境：沙盒初始化的 Git 目錄與本機使用者不同；經工具批准，只將本專案的絕對路徑加入 Git `safe.directory`，未信任其他目錄。
