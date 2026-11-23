import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agents.graph import FinanceAgentGraph
from tools.generic_query import GenericQueryTools
from tools.sql_tools import DataEngineeringTools


class GenericEcommerceAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self._write(
            "customers.csv",
            "customer_id,customer_state\nC1,SP\nC2,RJ\n",
        )
        self._write(
            "orders.csv",
            "order_id,customer_id,order_delivered_customer_date,order_estimated_delivery_date\n"
            "O1,C1,2018-01-15,2018-01-12\n"
            "O2,C2,2018-02-10,2018-02-12\n",
        )
        self._write(
            "order_payments.csv",
            "order_id,payment_value\nO1,100\nO2,200\n",
        )
        self._write(
            "order_items.csv",
            "order_id,product_id,price\nO1,P1,100\nO2,P2,50\n",
        )
        self._write(
            "products.csv",
            "product_id,product_category_name\nP1,books\nP2,toys\n",
        )
        self._write(
            "product_category_name_translation.csv",
            "product_category_name,product_category_name_english\nbooks,books\ntoys,toys\n",
        )
        self._write(
            "order_reviews.csv",
            "order_id,review_score\nO1,5\nO2,3\n",
        )

    def _write(self, filename: str, content: str) -> None:
        Path(self.directory.name, filename).write_text(content, encoding="utf-8")

    def _run_without_model_plan(self, request: str):
        with patch(
            "agents.planner_agent.llm_client.chat",
            side_effect=["INTENT: DATA", "null"],
        ):
            return FinanceAgentGraph().run(request, self.directory.name)

    def _query_result(self, request: str):
        state = self._run_without_model_plan(request)
        self.assertEqual(state["status"], "completed", state.get("clarification"))
        self.assertIn("query_data", state["tool_results"])
        for heading in (
            "Dataset understanding:",
            "Tables used:",
            "Analysis performed:",
            "Evidence:",
            "Interpretation:",
            "Recommended action:",
        ):
            self.assertIn(heading, state["recommendation"])
        return state["tool_results"]["query_data"]

    def test_customer_state_payment_value_uses_joined_sum(self):
        result = self._query_result("Which customer states generate the most payment value?")

        self.assertEqual(result["rows"][0]["customer_state"], "RJ")
        self.assertEqual(result["rows"][0]["total_payment_value"], 200.0)
        self.assertIn("customers", result["tables_used"])
        self.assertIn("order_payments", result["tables_used"])

    def test_best_performing_categories_uses_item_price(self):
        result = self._query_result("What are the best-performing product categories?")

        self.assertEqual(result["plan"]["aggregation"], "sum")
        self.assertEqual(result["plan"]["group_by"], "product_category_name")
        self.assertEqual(result["rows"][0]["total_price"], 100.0)
        self.assertIn("products", result["tables_used"])

    def test_late_delivery_count_compares_delivery_dates(self):
        result = self._query_result("How many orders were delivered late?")

        self.assertEqual(result["plan"]["task"], "count")
        self.assertEqual(result["rows"][0]["record_count"], 1)

    def test_average_review_score_by_category_uses_average(self):
        result = self._query_result("What is the average review score by product category?")

        self.assertEqual(result["plan"]["aggregation"], "avg")
        self.assertEqual(result["plan"]["group_by"], "product_category_name")
        self.assertEqual(result["rows"][0]["average_review_score"], 5.0)

    def test_ambiguous_request_still_asks_for_clarification(self):
        state = self._run_without_model_plan("Analyze this data")

        self.assertEqual(state["status"], "needs_clarification")
        self.assertNotIn("query_data", state["tool_results"])

    def test_validated_filter_is_applied_and_values_are_escaped(self):
        catalog = DataEngineeringTools.catalog_sources(self.directory.name)
        result = GenericQueryTools.execute_plan(
            catalog,
            {
                "task": "count",
                "tables": ["customers"],
                "filters": [
                    {
                        "column": "customer_state",
                        "operator": "=",
                        "value": "' OR 1=1 --",
                    },
                ],
            },
        )

        self.assertEqual(result["rows"][0]["record_count"], 0)

    def test_grouped_count_and_in_filter_are_supported(self):
        catalog = DataEngineeringTools.catalog_sources(self.directory.name)
        result = GenericQueryTools.execute_plan(
            catalog,
            {
                "task": "count",
                "group_by": "customer_state",
                "tables": ["customers"],
                "filters": [
                    {"column": "customer_state", "operator": "in", "value": ["SP", "RJ"]},
                ],
            },
        )

        self.assertEqual(
            {row["customer_state"]: row["record_count"] for row in result["rows"]},
            {"SP": 1, "RJ": 1},
        )


if __name__ == "__main__":
    unittest.main()
