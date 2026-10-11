"""把同一計畫／投影與原模型草稿渲染為檢查用Markdown，沒有計算或模型呼叫。"""

from __future__ import annotations

import html
import json
import re
from decimal import Decimal

from etf_agent.contracts import WeightedAgentDraft


def _text(value) -> str:
    """未知留明文，原文字轉義後保留換行；不讓資料變成HTML或Markdown指令。"""
    if value is None:
        return "未知"
    if isinstance(value, Decimal):
        value = format(value, "f")
    elif isinstance(value, (dict, list, tuple)):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    else:
        value = str(value)
    escaped = html.escape(value, quote=False)
    escaped = re.sub(r"([\\`*_\[\]{}()#!+|~])", r"\\\1", escaped)
    return re.sub(r"\r\n|\r|\n", "<br>", escaped)


def _refs(values) -> str:
    if values is None:
        return "未知"
    return "、".join(_text(value) for value in values) if values else "無"


def _status(value) -> str:
    return "PASS" if value is True else "BLOCK" if value is False else "未知"


def _flag(value) -> str:
    return "是" if value is True else "否" if value is False else "未知"


def _table(headers, rows) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    lines.extend("| " + " | ".join(_text(value) for value in row) + " |" for row in rows)
    return lines


def _action(value) -> str | None:
    labels = {"KEEP": "續抱", "BUY": "新買", "ADD": "加碼", "TRIM": "減碼", "SELL_ALL": "退出"}
    return f"{labels[value]}（{value}）" if value in labels else value


def render_plan_markdown(result: dict, packet: dict, draft: WeightedAgentDraft) -> str:
    """純檢查視圖；所有委託、權重、股數及財務數字直接讀取輸入，不改寫。

    草稿引用採原資料包編號，官方引用採編譯後plan編號，兩者分開呈現。
    """
    plan, portfolio, validation = (result.get(key) or {} for key in ("plan", "portfolio", "validation"))
    account = packet.get("account_snapshot") or {}
    data = packet.get("data_report") or {}
    market = draft.market_proposal
    selected = {row.ticker: row for row in draft.selections}
    held = {row.ticker: row for row in draft.held_reviews}
    decisions = {row["ticker"]: row for row in plan.get("decisions", [])}
    no_trade = {row["ticker"]: row for row in plan.get("no_trade_decisions", [])}
    projected_decisions = {row["ticker"]: row for row in portfolio.get("decisions", [])}
    unchanged = set(portfolio.get("no_trade_tickers", [])) | set(no_trade)
    positions = portfolio.get("positions")
    named_rows = [*data.get("rankings", []), *data.get("held_positions", []),
                  *(packet.get("account_report") or {}).get("current_positions", [])]
    names = {row["ticker"]: row.get("name") for row in named_rows if row.get("name") is not None}
    passed = validation.get("local_validation_ok")
    real = result.get("real_agent_decision")
    accepted = result.get("accepted_demo_plan", real is True and passed is True)
    title = "歷史 demo 計畫（本地 PASS）" if accepted is True else "候選計畫"
    if passed is False:
        title += "／BLOCK"
    lines = [f"# ETF 決策檢查：{title}", "",
             "本頁直接呈現同份 JSON 與原始模型草稿；金額、股數與權重以 JSON 為依據。", "",
             "## 日期、來源與驗證", ""]
    lines += _table(("項目", "結果"), [
        ("資料截止日 as_of", result.get("as_of", packet.get("as_of"))),
        ("預定交易日 trade_date", result.get("trade_date", packet.get("trade_date"))),
        ("資料情境", data.get("mode", validation.get("mode"))),
        ("草稿來源 decision_source", result.get("decision_source")),
        ("真實模型執行旗標", _flag(real)),
        ("模型 ID", (plan.get("agent_metadata") or {}).get("model_version")),
        ("配置檢查", _status(portfolio.get("portfolio_ok"))),
        ("官方 schema 檢查", _status(validation.get("schema_ok"))),
        ("本地語意檢查", _status(validation.get("semantic_ok"))),
        ("本地整體檢查", _status(passed)),
        ("正式資格", _flag(validation.get("formal_eligible"))),
        ("可正式提交", _flag(result.get("submission_ready", validation.get("submission_ready")))),
    ])
    if result.get("decision_source") == "fixture":
        lines += ["", "草稿來源為人工 fixture，沒有真實模型呼叫證據。"]
    lines += ["", "## 市場姿態與現金理由", ""]
    lines += _table(("項目", "模型草稿"), [
        ("市場狀態", market.regime), ("配置姿態", market.stance),
        ("淨曝險意圖", market.intended_flow), ("目標現金比率（0～1）", market.cash_target),
        ("宣告現金比率區間（0～1）", list(market.proposed_cash_range)),
    ])
    lines += ["", f"模型市場理由：{_text(market.rationale)}", "",
              f"市場反方證據：{_text(market.counter_evidence)}", "",
              f"草稿原始 O 引用：{_refs(market.basis_obs_ids)}", "",
              f"官方計畫 O 引用：{_refs((plan.get('market_view') or {}).get('basis_refs'))}", "",
              "## 前收財務估算", "",
              "以下為決策時的前收估算，金額單位是新臺幣元，比率是 0～1；尚非當日實際成交。", ""]
    money_fields = [("期初帳戶 NAV", account.get("nav_twd")),
                    ("期初現金", portfolio.get("cash_before_twd")),
                    ("買進名目金額", portfolio.get("buy_notional_twd")),
                    ("賣出名目金額", portfolio.get("sell_notional_twd")),
                    ("買賣手續費", portfolio.get("fees_twd")), ("賣出證交稅", portfolio.get("tax_twd")),
                    ("費後預估現金", portfolio.get("cash_after_twd")),
                    ("費後投影 NAV", portfolio.get("projected_nav_twd")),
                    ("淨買進金額", portfolio.get("net_flow_twd")),
                    ("費後現金比率（0～1）", portfolio.get("cash_ratio"))]
    lines += _table(("項目", "JSON 值"), money_fields)
    lines += ["", "## 完整持股與目標", "",
              "包含原持股、選股及退出股；股數直接採用配置結果，KEEP 仍顯示原／目標股數。", ""]
    if isinstance(positions, list):
        rows = []
        for position in positions:
            ticker = position["ticker"]
            official = decisions.get(ticker)
            action = (official or projected_decisions.get(ticker) or {}).get("action")
            if action is None and ticker in unchanged:
                action = "KEEP"
            rows.append((ticker, names.get(ticker), _action(action), position.get("current_shares"),
                         position.get("target_shares"), position.get("target_weight"),
                         position.get("projected_weight"), position.get("close_twd_per_share"),
                         official.get("decision_id") if official else "無" if ticker in no_trade else None,
                         (official.get("inference_refs") if official else
                          no_trade[ticker].get("reason_refs") if ticker in no_trade else None)))
        lines += _table(("股票", "名稱", "動作", "原持股（股）", "目標（股）", "目標權重比率",
                         "費後投影權重比率", "前收（元／股）", "官方 D", "官方 I"), rows)
    else:
        lines.append("持股投影：未知。")
    lines += ["", "## 買賣委託", ""]
    orders = plan.get("orders")
    if isinstance(orders, list):
        lines += _table(("股票", "買賣方向", "委託股數（股）", "官方決策引用"),
                        [(row.get("ticker"), row.get("side"), row.get("shares"), row.get("decision_ref"))
                         for row in orders])
        if not orders:
            lines += ["", "本計畫沒有買賣委託；完整續抱持股仍列於上表。"]
    else:
        lines.append("委託清單：未知。")
    lines += ["", "## 模型原始個股理由與反方證據", "",
              "此處的 O 引用是草稿原資料包編號；官方計畫可能裁剪並重排編號。", ""]
    for ticker in sorted(set(selected) | set(held)):
        selection, review = selected.get(ticker), held.get(ticker)
        lines += [f"### {_text(ticker)} · {_text(names.get(ticker))}", ""]
        if selection:
            lines += [f"選股理由：{_text(selection.rationale)}", "",
                      f"選股反方證據：{_text(selection.counter_evidence)}", "",
                      f"選股原始 O 引用：{_refs(selection.supporting_obs_ids)}", ""]
        if review:
            lines += [f"原持股意圖：{_text(review.intent)}", "",
                      f"原持股理由：{_text(review.rationale)}", "",
                      f"原持股反方證據：{_text(review.counter_evidence)}", "",
                      f"持股原始 O 引用：{_refs(review.supporting_obs_ids)}", ""]
    lines += ["## 官方引用鏈", "",
              "以下直接列出已編譯計畫中的 S／O／I；D 與 I 的關係列於持股表，委託引用列於買賣表。", ""]
    lines += _table(("來源 S", "名稱", "URL", "內容截至"),
                    [(row.get("source_id"), row.get("name"), row.get("url"), row.get("content_as_of"))
                     for row in plan.get("sources", [])])
    lines += [""]
    lines += _table(("觀察 O", "來源 S", "原計畫事實"),
                    [(row.get("obs_id"), row.get("source_ref"), row.get("statement"))
                     for row in plan.get("observations", [])])
    lines += [""]
    lines += _table(("推論 I", "官方前提 O"),
                    [(row.get("inf_id"), row.get("premise_refs")) for row in plan.get("inferences", [])])
    lines += ["", "## 資料問題與 BLOCK", ""]
    issue_rows = []
    for label, document in (("資料", data), ("帳戶", packet.get("account_report") or {}),
                            ("前日檢視", packet.get("review_report") or {}),
                            ("配置", portfolio), ("驗證", validation)):
        for issue in document.get("issues", []):
            issue_rows.append((label, issue.get("severity"), issue.get("code"),
                               issue.get("ticker"), issue.get("message")))
    lines += _table(("來源", "嚴重程度", "問題代碼", "股票", "原問題訊息"), issue_rows)
    if not issue_rows:
        lines += ["", "輸入問題清單為空；驗證結果仍以上方旗標為準。"]
    if "excluded_stocks" in data:
        lines += ["", "未參與排名的既有股票紀錄：", ""]
        lines += _table(("股票", "狀態", "缺少日期", "無效價格日期"),
                        [(row.get("ticker"), row.get("status"), row.get("missing_dates"), row.get("invalid_price_dates"))
                         for row in data["excluded_stocks"]])
    review = packet.get("review_report") or {}
    lines += ["", f"前日檢視狀態：{_text(review.get('status'))}", "",
              f"前日檢視原因：{_text(review.get('reason'))}", "", "本地逐項檢查：", ""]
    lines += _table(("檢查", "結果／嚴重程度", "原訊息"),
                    [(row.get("code"), row.get("severity"), row.get("message"))
                     for row in validation.get("checks", [])])
    limitations = []
    for document in (result, packet, portfolio, validation):
        for value in document.get("limitations", []):
            if value not in limitations:
                limitations.append(value)
    if limitations:
        lines += ["", "## 已記錄限制", ""]
        lines += [f"- {_text(value)}" for value in limitations]
    return "\n".join(lines).rstrip() + "\n"
