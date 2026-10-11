"""離線合約驗收：精度、來源時間、草稿覆蓋及保留測試期間。"""

import copy
import json
import unittest
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from etf_agent.agent.base import AgentResult
from etf_agent.contracts import (
    AccountSnapshot,
    AgentDraft,
    ContractError,
    DatasetSplitPlan,
    FeatureTable,
    MarketSnapshot,
    PortfolioProposal,
    ValidationReport,
)


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "contracts_demo.json"
CONTRACT_TYPES = {
    "market_snapshot": MarketSnapshot,
    "account_snapshot": AccountSnapshot,
    "feature_table": FeatureTable,
    "agent_draft": AgentDraft,
    "portfolio_proposal": PortfolioProposal,
    "validation_report": ValidationReport,
    "dataset_split_plan": DatasetSplitPlan,
    "agent_result": AgentResult,
}


class ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    def data(self, name):
        return copy.deepcopy(self.fixture[name])

    def context(self):
        features = FeatureTable.from_dict(self.data("feature_table"))
        account = AccountSnapshot.from_dict(self.data("account_snapshot"))
        return {
            "allowed_tickers": {row.ticker for row in features.rows if row.eligible},
            "held_tickers": {position.ticker for position in account.positions},
            "observation_ids": {ref for row in features.rows for ref in row.observation_ids},
        }

    def test_fixture_round_trips_all_contracts_through_json(self):
        for name, contract_type in CONTRACT_TYPES.items():
            with self.subTest(contract=name):
                contract = contract_type.from_dict(self.data(name))
                encoded = json.loads(json.dumps(contract.to_dict(), ensure_ascii=False))
                self.assertEqual(contract_type.from_dict(encoded), contract)

    def test_demo_account_has_25_positions_and_reproducible_nav(self):
        account = AccountSnapshot.from_dict(self.data("account_snapshot"))
        market = MarketSnapshot.from_dict(self.data("market_snapshot"))
        latest_prices = {
            bar.ticker: bar.close_raw
            for bar in market.prices
            if bar.trade_date == market.previous_trade_date
        }
        self.assertEqual(len(account.positions), 25)
        valuation = sum(
            (latest_prices[position.ticker] * position.shares for position in account.positions),
            Decimal(0),
        )
        self.assertEqual(account.nav_twd, account.cash_twd + valuation)
        self.assertTrue(account.demo)
        self.assertFalse(account.reconciled)

    def test_money_precision_and_decimal_strings_are_preserved(self):
        data = self.data("account_snapshot")
        data.update(cash_twd="10000000.01", nav_twd="100000000.01")
        account = AccountSnapshot.from_dict(data)
        self.assertEqual(account.cash_twd + Decimal("0.09"), Decimal("10000000.10"))
        self.assertEqual(account.to_dict()["cash_twd"], "10000000.01")
        self.assertEqual(AccountSnapshot.from_dict(account.to_dict()), account)

    def test_money_rejects_float_bool_and_non_finite_values(self):
        for value in (10000000.01, True, "NaN", "Infinity"):
            with self.subTest(value=value):
                data = self.data("account_snapshot")
                data["cash_twd"] = value
                with self.assertRaises(ContractError):
                    AccountSnapshot.from_dict(data)

    def test_unknown_top_level_fields_are_rejected(self):
        for name, contract_type in CONTRACT_TYPES.items():
            with self.subTest(contract=name):
                data = self.data(name)
                data["unapproved_field"] = "test"
                with self.assertRaises(ContractError):
                    contract_type.from_dict(data)

    def test_unknown_nested_fields_are_rejected(self):
        cases = (
            ("market_snapshot", "prices", MarketSnapshot),
            ("account_snapshot", "positions", AccountSnapshot),
            ("feature_table", "rows", FeatureTable),
            ("agent_draft", "selections", AgentDraft),
            ("agent_draft", "held_reviews", AgentDraft),
            ("portfolio_proposal", "targets", PortfolioProposal),
            ("validation_report", "checks", ValidationReport),
        )
        for name, nested, contract_type in cases:
            with self.subTest(contract=name, nested=nested):
                data = self.data(name)
                data[nested][0]["unapproved_field"] = "test"
                with self.assertRaises(ContractError):
                    contract_type.from_dict(data)

    def test_agent_cannot_include_final_shares(self):
        for location in ("top", "market_proposal", "selections", "held_reviews"):
            with self.subTest(location=location):
                data = self.data("agent_draft")
                target = data if location == "top" else data[location]
                if isinstance(target, list):
                    target = target[0]
                target["shares"] = 20000
                with self.assertRaises(ContractError):
                    AgentDraft.from_dict(data)

    def test_ticker_must_be_a_four_digit_string(self):
        for value in (2891, True, "891", "ABCD", "02891"):
            with self.subTest(value=value):
                data = self.data("account_snapshot")
                data["positions"][0]["ticker"] = value
                with self.assertRaises(ContractError):
                    AccountSnapshot.from_dict(data)

    def test_shares_require_positive_integers_and_reject_bool(self):
        for value in (True, False, 1000.0, "1000", 0, -1000):
            with self.subTest(value=value):
                data = self.data("account_snapshot")
                data["positions"][0]["shares"] = value
                with self.assertRaises(ContractError):
                    AccountSnapshot.from_dict(data)

    def test_agent_json_numbers_reject_bool_strings_and_non_finite_values(self):
        for value in (True, "0.09", float("nan"), float("inf")):
            with self.subTest(value=value):
                data = self.data("agent_draft")
                data["market_proposal"]["cash_target"] = value
                with self.assertRaises(ContractError):
                    AgentDraft.from_dict(data)

    def test_agent_conviction_accepts_numeric_one(self):
        data = self.data("agent_draft")
        data["selections"][0]["conviction"] = 1
        self.assertEqual(AgentDraft.from_dict(data).selections[0].conviction, 1.0)
        for value in (True, "1", 0.9):
            with self.subTest(value=value):
                data["selections"][0]["conviction"] = value
                with self.assertRaises(ContractError):
                    AgentDraft.from_dict(data)

    def test_timestamp_requires_valid_taipei_offset(self):
        invalid = (
            "2026-10-15T08:00:00",
            "2026-10-15T00:00:00+00:00",
            "2026-10-15T08:00:00Z",
            "2026-13-15T08:00:00+08:00",
            "2026-10-15T25:00:00+08:00",
        )
        for value in invalid:
            with self.subTest(value=value):
                data = self.data("market_snapshot")
                data["snapshot_cutoff"] = value
                with self.assertRaises(ContractError):
                    MarketSnapshot.from_dict(data)

    def test_premarket_snapshot_rejects_t_day_and_future_quotes(self):
        base = MarketSnapshot.from_dict(self.data("market_snapshot"))
        for value in (base.trade_date, base.trade_date + timedelta(days=1)):
            with self.subTest(date=value):
                data = self.data("market_snapshot")
                data["prices"][0]["trade_date"] = value.isoformat()
                with self.assertRaises(ContractError):
                    MarketSnapshot.from_dict(data)

    def test_quote_known_after_cutoff_is_rejected(self):
        data = self.data("market_snapshot")
        snapshot = MarketSnapshot.from_dict(data)
        data["prices"][0]["known_at"] = (
            snapshot.snapshot_cutoff + timedelta(seconds=1)
        ).isoformat()
        with self.assertRaises(ContractError):
            MarketSnapshot.from_dict(data)

    def test_formal_source_requires_known_time_and_raw_evidence_hash(self):
        for missing in ("known_at", "raw_sha256"):
            with self.subTest(missing=missing):
                data = self.data("market_snapshot")
                data["data_origin"] = "official_cache"
                for bar in data["prices"]:
                    bar["known_at"] = data["snapshot_cutoff"]
                    bar["raw_sha256"] = "a" * 64
                data["prices"][0][missing] = None
                with self.assertRaises(ContractError):
                    MarketSnapshot.from_dict(data)

    def test_historical_quotes_for_one_stock_can_have_multiple_dates(self):
        data = self.data("market_snapshot")
        snapshot = MarketSnapshot.from_dict(data)
        oldest = min(bar.trade_date for bar in snapshot.prices)
        extra = copy.deepcopy(data["prices"][0])
        extra["trade_date"] = (oldest - timedelta(days=1)).isoformat()
        data["prices"].append(extra)
        self.assertEqual(len(MarketSnapshot.from_dict(data).prices), len(snapshot.prices) + 1)

    def test_same_stock_same_date_is_rejected_even_if_version_differs(self):
        for new_version in (False, True):
            with self.subTest(new_version=new_version):
                data = self.data("market_snapshot")
                extra = copy.deepcopy(data["prices"][0])
                if new_version:
                    extra["data_version"] += "-revised"
                data["prices"].append(extra)
                with self.assertRaises(ContractError):
                    MarketSnapshot.from_dict(data)

    def test_unknown_nullable_data_is_preserved_as_null(self):
        market_data = self.data("market_snapshot")
        market_data["prices"][0].update(
            open=None,
            high=None,
            low=None,
            close_raw=None,
            return_close=None,
            volume_shares=None,
            amount_twd=None,
            known_at=None,
            raw_sha256=None,
            price_valid=False,
            tradable=False,
        )
        encoded = MarketSnapshot.from_dict(market_data).to_dict()["prices"][0]
        for name in ("close_raw", "return_close", "volume_shares", "amount_twd", "known_at", "raw_sha256"):
            self.assertIsNone(encoded[name])

    def test_missing_feature_requires_reason_and_is_not_filled_with_zero(self):
        data = self.data("feature_table")
        row = data["rows"][0]
        name = next(iter(row["values"]))
        row["values"][name] = None
        row["missing_reasons"][name] = "測試：可用歷史資料不足"
        feature = FeatureTable.from_dict(data)
        self.assertIsNone(feature.rows[0].values[name])
        self.assertEqual(feature.to_dict()["rows"][0]["missing_reasons"][name], "測試：可用歷史資料不足")
        del row["missing_reasons"][name]
        with self.assertRaises(ContractError):
            FeatureTable.from_dict(data)

    def test_agent_context_accepts_complete_fixture(self):
        AgentDraft.from_dict(self.data("agent_draft")).validate_context(**self.context())

    def test_agent_context_rejects_stock_outside_candidate_pool(self):
        draft = AgentDraft.from_dict(self.data("agent_draft"))
        context = self.context()
        context["allowed_tickers"].discard(draft.selections[0].ticker)
        with self.assertRaises(ContractError):
            draft.validate_context(**context)

    def test_agent_context_rejects_missing_or_extra_held_review(self):
        data = self.data("agent_draft")
        data["held_reviews"].pop()
        with self.assertRaises(ContractError):
            AgentDraft.from_dict(data).validate_context(**self.context())
        context = self.context()
        context["held_tickers"].add("9999")
        with self.assertRaises(ContractError):
            AgentDraft.from_dict(self.data("agent_draft")).validate_context(**context)

    def test_agent_context_rejects_nonexistent_observation(self):
        data = self.data("agent_draft")
        data["selections"][0]["supporting_obs_ids"] = ["O999"]
        context = self.context()
        context["observation_ids"].discard("O999")
        with self.assertRaises(ContractError):
            AgentDraft.from_dict(data).validate_context(**context)

    def test_portfolio_covers_all_held_and_selected_stocks(self):
        portfolio = PortfolioProposal.from_dict(self.data("portfolio_proposal"))
        draft = AgentDraft.from_dict(self.data("agent_draft"))
        portfolio.validate_context(
            held_tickers=self.context()["held_tickers"],
            selected_tickers={selection.ticker for selection in draft.selections},
        )

    def test_portfolio_requires_explicit_zero_target_for_exited_stock(self):
        data = self.data("portfolio_proposal")
        exiting, other = data["targets"][:2]
        other["target_weight"] = str(Decimal(other["target_weight"]) + Decimal(exiting["target_weight"]))
        exiting["target_weight"] = "0"
        portfolio = PortfolioProposal.from_dict(data)
        held = {target.ticker for target in portfolio.targets}
        selected = held - {exiting["ticker"]}
        portfolio.validate_context(held_tickers=held, selected_tickers=selected)
        data["targets"].pop(0)
        with self.assertRaises(ContractError):
            PortfolioProposal.from_dict(data).validate_context(held_tickers=held, selected_tickers=selected)

    def test_portfolio_rejects_weights_not_summing_to_one(self):
        data = self.data("portfolio_proposal")
        data["cash_target"] = str(Decimal(data["cash_target"]) + Decimal("0.01"))
        with self.assertRaises(ContractError):
            PortfolioProposal.from_dict(data)

    def test_demo_or_contract_only_report_cannot_be_submission_ready(self):
        for mode, scope in (("demo", "official"), ("formal", "contract_only")):
            with self.subTest(mode=mode, scope=scope):
                data = self.data("validation_report")
                data.update(
                    mode=mode,
                    scope=scope,
                    official_rules_confirmed=True,
                    account_reconciled=True,
                    real_agent_decision=True,
                    submission_ready=True,
                )
                with self.assertRaises(ContractError):
                    ValidationReport.from_dict(data)

    def test_fixture_provider_keeps_unknown_model_and_usage_null(self):
        result = AgentResult.from_dict(self.data("agent_result"))
        self.assertEqual(result.provider, "fixture")
        self.assertIsNone(result.actual_model_version)
        self.assertIsNone(result.usage)
        self.assertIsNone(result.to_dict()["actual_model_version"])
        self.assertIsNone(result.to_dict()["usage"])

    def test_temporal_split_rejects_overlapping_or_out_of_order_periods(self):
        base = self.data("dataset_split_plan")
        invalid = (
            {"validation_start": base["train_end"]},
            {"test_start": base["validation_end"]},
            {"test_start": base["train_start"], "test_end": base["train_end"]},
            {"train_start": base["validation_start"]},
        )
        for changes in invalid:
            with self.subTest(changes=changes):
                data = self.data("dataset_split_plan")
                data.update(changes)
                with self.assertRaises(ContractError):
                    DatasetSplitPlan.from_dict(data)

    def test_temporal_split_keeps_label_gap_and_final_test_locked(self):
        for changes in (
            {"label_horizon_trading_days": 5, "gap_trading_days": 4},
            {"label_horizon_trading_days": 0},
            {"final_test_locked": False},
            {"label_horizon_trading_days": True},
            {"gap_trading_days": True},
        ):
            with self.subTest(changes=changes):
                data = self.data("dataset_split_plan")
                data.update(changes)
                with self.assertRaises(ContractError):
                    DatasetSplitPlan.from_dict(data)


if __name__ == "__main__":
    unittest.main()
