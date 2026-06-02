"""Tests for HAVING clause support in Hybrid_DB"""
import sys
import os
import shutil
import unittest

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.query_parser import QueryParser
from src.db_core import DBCore


class TestHavingParser(unittest.TestCase):
    """Test that the parser correctly extracts HAVING clauses."""

    def setUp(self):
        self.parser = QueryParser()

    def test_basic_having(self):
        """Parser extracts HAVING from a GROUP BY + HAVING query."""
        parsed = self.parser.parse_select(
            "SELECT dept, COUNT(*) FROM employees GROUP BY dept HAVING COUNT(*) > 2"
        )
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["type"], "aggregation")
        self.assertEqual(parsed["group_by"], "dept")
        self.assertEqual(parsed["having"], "COUNT(*) > 2")

    def test_having_with_where(self):
        """Parser captures both WHERE and HAVING."""
        parsed = self.parser.parse_select(
            "SELECT dept, AVG(salary) FROM employees WHERE age > 20 GROUP BY dept HAVING AVG(salary) > 50"
        )
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["where"], "age > 20")
        self.assertEqual(parsed["having"], "AVG(salary) > 50")
        self.assertEqual(parsed["group_by"], "dept")

    def test_having_with_order_by_and_limit(self):
        """Parser handles the full clause chain: GROUP BY + HAVING + ORDER BY + LIMIT."""
        parsed = self.parser.parse_select(
            "SELECT dept, COUNT(*) FROM employees GROUP BY dept HAVING COUNT(*) > 1 ORDER BY dept LIMIT 5"
        )
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["having"], "COUNT(*) > 1")
        self.assertEqual(parsed["group_by"], "dept")
        self.assertEqual(parsed["order_by"], "dept")
        self.assertEqual(parsed["limit"], 5)

    def test_no_having(self):
        """Queries without HAVING should have having=None."""
        parsed = self.parser.parse_select(
            "SELECT dept, COUNT(*) FROM employees GROUP BY dept"
        )
        self.assertIsNotNone(parsed)
        self.assertIsNone(parsed["having"])

    def test_having_in_simple_select(self):
        """Simple SELECT dict should also contain the having key."""
        parsed = self.parser.parse_select(
            "SELECT * FROM employees"
        )
        self.assertIsNotNone(parsed)
        self.assertIn("having", parsed)
        self.assertIsNone(parsed["having"])


class TestEvaluateHaving(unittest.TestCase):
    """Test the evaluate_having method with various operators."""

    def test_greater_than(self):
        row = {"dept": "Engineering", "COUNT(*)": 10}
        self.assertTrue(QueryParser.evaluate_having(row, "COUNT(*) > 5"))
        self.assertFalse(QueryParser.evaluate_having(row, "COUNT(*) > 15"))

    def test_less_than(self):
        row = {"dept": "HR", "COUNT(*)": 3}
        self.assertTrue(QueryParser.evaluate_having(row, "COUNT(*) < 5"))
        self.assertFalse(QueryParser.evaluate_having(row, "COUNT(*) < 2"))

    def test_greater_equal(self):
        row = {"dept": "Sales", "COUNT(*)": 5}
        self.assertTrue(QueryParser.evaluate_having(row, "COUNT(*) >= 5"))
        self.assertFalse(QueryParser.evaluate_having(row, "COUNT(*) >= 6"))

    def test_less_equal(self):
        row = {"dept": "Sales", "AVG(salary)": 50000}
        self.assertTrue(QueryParser.evaluate_having(row, "AVG(salary) <= 50000"))
        self.assertFalse(QueryParser.evaluate_having(row, "AVG(salary) <= 49999"))

    def test_equal(self):
        row = {"dept": "HR", "COUNT(*)": 3}
        self.assertTrue(QueryParser.evaluate_having(row, "COUNT(*) = 3"))
        self.assertFalse(QueryParser.evaluate_having(row, "COUNT(*) = 5"))

    def test_not_equal(self):
        row = {"dept": "HR", "COUNT(*)": 3}
        self.assertTrue(QueryParser.evaluate_having(row, "COUNT(*) != 5"))
        self.assertFalse(QueryParser.evaluate_having(row, "COUNT(*) != 3"))

    def test_and_condition(self):
        row = {"dept": "Engineering", "COUNT(*)": 5}
        self.assertTrue(QueryParser.evaluate_having(row, "COUNT(*) > 2 AND COUNT(*) < 10"))
        self.assertFalse(QueryParser.evaluate_having(row, "COUNT(*) > 2 AND COUNT(*) < 4"))

    def test_or_condition(self):
        row = {"dept": "HR", "COUNT(*)": 1}
        self.assertTrue(QueryParser.evaluate_having(row, "COUNT(*) > 5 OR COUNT(*) = 1"))
        self.assertFalse(QueryParser.evaluate_having(row, "COUNT(*) > 5 OR COUNT(*) = 2"))

    def test_none_condition(self):
        """None condition should return True (no filter)."""
        row = {"dept": "HR", "COUNT(*)": 3}
        self.assertTrue(QueryParser.evaluate_having(row, None))

    def test_case_insensitive_agg_func(self):
        """Aggregate function names should be case-insensitive."""
        row = {"dept": "HR", "COUNT(*)": 3}
        self.assertTrue(QueryParser.evaluate_having(row, "count(*) > 2"))

    def test_avg_with_float(self):
        row = {"dept": "Sales", "AVG(salary)": 62500.0}
        self.assertTrue(QueryParser.evaluate_having(row, "AVG(salary) > 60000"))
        self.assertFalse(QueryParser.evaluate_having(row, "AVG(salary) > 70000"))


class TestHavingExecution(unittest.TestCase):
    """End-to-end tests: insert data, run GROUP BY + HAVING, verify filtered results."""

    def setUp(self):
        self.test_data_dir = os.path.join(os.path.dirname(__file__), "test_having_data")
        self.db = DBCore(data_dir=self.test_data_dir)
        # Create test database and table
        self.db.execute_create_database("CREATE DATABASE test_having_db")
        self.db.use_database("test_having_db")
        self.db.execute_create_table(
            "CREATE TABLE employees (name TEXT, dept TEXT, salary INT)"
        )
        # Insert test data
        test_data = [
            ("Alice", "Engineering", 90000),
            ("Bob", "Engineering", 85000),
            ("Charlie", "Sales", 60000),
            ("Diana", "Engineering", 95000),
            ("Eve", "Sales", 65000),
            ("Frank", "HR", 55000),
        ]
        for name, dept, salary in test_data:
            self.db.execute_insert(
                f"INSERT INTO employees VALUES ('{name}', '{dept}', {salary})"
            )

    def tearDown(self):
        if os.path.exists(self.test_data_dir):
            shutil.rmtree(self.test_data_dir)

    def test_having_filters_groups(self):
        """HAVING COUNT(*) > 1 should exclude HR (only 1 employee)."""
        result, success, err = self.db.execute_select(
            "SELECT dept, COUNT(*) FROM employees GROUP BY dept HAVING COUNT(*) > 1"
        )
        self.assertTrue(success)
        self.assertIsInstance(result, list)
        dept_names = [row["dept"] for row in result]
        self.assertIn("Engineering", dept_names)
        self.assertIn("Sales", dept_names)
        self.assertNotIn("HR", dept_names)

    def test_having_with_avg(self):
        """HAVING AVG(salary) > 60000 should keep Engineering and Sales, exclude HR."""
        result, success, err = self.db.execute_select(
            "SELECT dept, AVG(salary) FROM employees GROUP BY dept HAVING AVG(salary) > 60000"
        )
        self.assertTrue(success)
        dept_names = [row["dept"] for row in result]
        self.assertIn("Engineering", dept_names)
        self.assertIn("Sales", dept_names)
        self.assertNotIn("HR", dept_names)

    def test_having_excludes_all(self):
        """HAVING with a condition no group satisfies returns empty."""
        result, success, err = self.db.execute_select(
            "SELECT dept, COUNT(*) FROM employees GROUP BY dept HAVING COUNT(*) > 100"
        )
        self.assertTrue(success)
        self.assertEqual(result, [])

    def test_having_with_where(self):
        """WHERE filters rows first, then HAVING filters groups."""
        result, success, err = self.db.execute_select(
            "SELECT dept, COUNT(*) FROM employees WHERE salary > 60000 GROUP BY dept HAVING COUNT(*) > 1"
        )
        self.assertTrue(success)
        dept_names = [row["dept"] for row in result]
        # Engineering: Alice(90k), Bob(85k), Diana(95k) → 3 > 1 ✓
        # Sales: Eve(65k) → 1, not > 1 ✗
        # HR: none pass WHERE
        self.assertIn("Engineering", dept_names)
        self.assertNotIn("Sales", dept_names)
        self.assertNotIn("HR", dept_names)

    def test_having_without_group_by_error(self):
        """HAVING without GROUP BY should return an error."""
        result, success, err = self.db.execute_select(
            "SELECT COUNT(*) FROM employees HAVING COUNT(*) > 1"
        )
        self.assertFalse(success)
        self.assertIn("HAVING clause requires GROUP BY", err)

    def test_having_with_order_by_and_limit(self):
        """Full clause chain: GROUP BY + HAVING + ORDER BY + LIMIT."""
        result, success, err = self.db.execute_select(
            "SELECT dept, COUNT(*) FROM employees GROUP BY dept HAVING COUNT(*) > 1 ORDER BY dept LIMIT 1"
        )
        self.assertTrue(success)
        self.assertEqual(len(result), 1)


if __name__ == "__main__":
    unittest.main()
