"""第二版加權草稿的主要拒絕條件；沿用人工fixture，沒有模型或行情呼叫。"""

import copy
import json
import re
import unittest
from decimal import Decimal
from pathlib import Path

from etf_agent.decision.providers.base import AgentResult
from etf_agent.contracts import (
    AgentDraft, ContractError, PortfolioProposal, WeightedAgentDraft, WeightedSelection,
)


ROOT = Path(__file__).resolve().parents[1]


class WeightedDraftTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads((ROOT / "tests/fixtures/contracts_demo.json").read_text(encoding="utf-8"))

    def data(self):
        draft = copy.deepcopy(self.fixture["agent_draft"])
        draft["contract_version"] = "2.0"
        weights = {row["ticker"]: row["target_weight"] for row in self.fixture["portfolio_proposal"]["targets"]}
        for selection in draft["selections"]:
            del selection["conviction"]
            selection["target_weight"] = weights[selection["ticker"]]
        return draft

    def context(self):
        return {
            "allowed_tickers": {row["ticker"] for row in self.fixture["agent_draft"]["selections"]},
            "held_tickers": {row["ticker"] for row in self.fixture["account_snapshot"]["positions"]},
            "observation_ids": {ref for row in self.fixture["feature_table"]["rows"] for ref in row["observation_ids"]},
        }

    def test_weighted_draft_roundtrip_and_exact_cash_plus_weights(self):
        draft = WeightedAgentDraft.from_dict(self.data())
        draft.validate_context(**self.context())
        self.assertEqual(draft.contract_version, "2.0")
        self.assertEqual(draft.selections[0].target_weight, Decimal("0.04"))
        self.assertEqual(sum((row.target_weight for row in draft.selections), Decimal(0))
                         + Decimal(str(draft.market_proposal.cash_target)), Decimal(1))
        encoded = json.loads(json.dumps(draft.to_dict(), allow_nan=False))
        self.assertEqual(encoded["selections"][0]["target_weight"], "0.04")
        self.assertEqual(WeightedAgentDraft.from_dict(encoded), draft)

    def test_weights_reject_zero_negative_numbers_and_over_cap_but_accept_boundaries(self):
        normal = self.data()["selections"][0]
        for ticker, weight in (("2330", "0.25"), ("2891", "0.10")):
            with self.subTest(ticker=ticker, weight=weight):
                selection = WeightedSelection.from_dict({**normal, "ticker": ticker, "target_weight": weight})
                self.assertEqual(selection.target_weight, Decimal(weight))
        for ticker, weight in (("2330", "0.250001"), ("2891", "0.100001"),
                               ("2891", "0"), ("2891", "-0.01"), ("2891", 0.04),
                               ("2891", True), ("2891", "NaN"), ("2891", "Infinity")):
            with self.subTest(ticker=ticker, weight=weight), self.assertRaises(ContractError):
                WeightedSelection.from_dict({**normal, "ticker": ticker, "target_weight": weight})

    def test_sum_count_and_duplicate_errors_stop_including_beyond_default_decimal_precision(self):
        wrong_sum = self.data()
        wrong_sum["selections"][-1]["target_weight"] = "0.0362500000000000000000000000000000001"
        wrong_cash = self.data()
        wrong_cash["market_proposal"]["cash_target"] = 0.10
        duplicate = self.data()
        duplicate["selections"].append(copy.deepcopy(duplicate["selections"][0]))
        too_few = self.data()
        too_few["selections"] = too_few["selections"][:19]
        too_many = self.data()
        too_many["selections"] += copy.deepcopy(too_many["selections"][:6])
        for name, data in (("sum", wrong_sum), ("cash", wrong_cash), ("duplicate", duplicate),
                           ("19_stocks", too_few), ("31_stocks", too_many)):
            with self.subTest(name=name), self.assertRaises(ContractError):
                WeightedAgentDraft.from_dict(data)

    def test_context_rejects_outside_candidates_missing_held_review_and_unknown_observation(self):
        draft = WeightedAgentDraft.from_dict(self.data())
        context = self.context()
        context["allowed_tickers"].remove(draft.selections[0].ticker)
        with self.assertRaises(ContractError):
            draft.validate_context(**context)
        data = self.data()
        data["held_reviews"].pop()
        with self.assertRaises(ContractError):
            WeightedAgentDraft.from_dict(data).validate_context(**self.context())
        data = self.data()
        data["selections"][0]["supporting_obs_ids"] = ["O999"]
        with self.assertRaises(ContractError):
            WeightedAgentDraft.from_dict(data).validate_context(**self.context())

    def test_keep_and_exit_must_match_positive_selection_set(self):
        data = self.data()
        data["held_reviews"][1]["intent"] = "exit"
        with self.assertRaises(ContractError):
            WeightedAgentDraft.from_dict(data)
        data["selections"].pop(1)
        data["selections"][0]["target_weight"] = "0.07625"
        draft = WeightedAgentDraft.from_dict(data)
        draft.validate_context(**self.context())
        self.assertNotIn("2330", {selection.ticker for selection in draft.selections})
        for intent in ("keep", "rebalance"):
            with self.subTest(intent=intent):
                data["held_reviews"][1]["intent"] = intent
                with self.assertRaises(ContractError):
                    WeightedAgentDraft.from_dict(data)

    def test_final_shares_are_forbidden_and_provider_roundtrips_both_draft_versions(self):
        for location in ("top", "market_proposal", "selections", "held_reviews"):
            with self.subTest(location=location):
                data = self.data()
                target = data if location == "top" else data[location]
                if isinstance(target, list):
                    target = target[0]
                target["shares"] = 1000
                with self.assertRaises(ContractError):
                    WeightedAgentDraft.from_dict(data)
        old = AgentResult.from_dict(copy.deepcopy(self.fixture["agent_result"]))
        self.assertIsInstance(old.draft, AgentDraft)
        data = {**copy.deepcopy(self.fixture["agent_result"]), "draft": self.data()}
        weighted = AgentResult.from_dict(data)
        self.assertIsInstance(weighted.draft, WeightedAgentDraft)
        for result in (old, weighted):
            self.assertEqual(AgentResult.from_dict(json.loads(json.dumps(result.to_dict()))), result)
            self.assertEqual(result.provider, "fixture")
            self.assertIsNone(result.actual_model_version)
            self.assertIsNone(result.usage)
        proposal = PortfolioProposal.from_dict({**copy.deepcopy(self.fixture["portfolio_proposal"]),
                                                "allocation_method": "agent_target_weights"})
        self.assertEqual(proposal.contract_version, "1.0")
        proposal.validate_context(held_tickers=self.context()["held_tickers"],
                                  selected_tickers=self.context()["allowed_tickers"])

    def test_schema_requires_version_and_decimal_strings_and_forbids_extra_fields(self):
        schema = json.loads((ROOT / "specs/internal/weighted_agent_draft.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(schema["properties"]["contract_version"]["const"], "2.0")
        self.assertIn("contract_version", schema["required"])
        objects = [schema, schema["$defs"]["market_proposal"], schema["$defs"]["weighted_selection"],
                   schema["$defs"]["held_review"]]
        for definition in objects:
            self.assertIs(definition["additionalProperties"], False)
            self.assertEqual(set(definition["required"]), set(definition["properties"]))
            self.assertNotIn("shares", definition["properties"])
        weight = schema["$defs"]["weighted_selection"]["properties"]["target_weight"]
        self.assertEqual(weight["type"], "string")
        self.assertIsNotNone(re.fullmatch(weight["pattern"], "0.04"))
        for invalid in ("NaN", "Infinity", "-0.04"):
            self.assertIsNone(re.fullmatch(weight["pattern"], invalid))
        self.assertNotIn("conviction", schema["$defs"]["weighted_selection"]["properties"])


if __name__ == "__main__":
    unittest.main()
