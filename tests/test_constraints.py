"""Tests for AUTOINCREMENT, type constraints, and CHECK constraints in Hybrid_DB"""
import sys
import os
import shutil
import unittest

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.db_core import DBCore
from src.query_parser import QueryParser


class TestConstraintsAndAutoIncrement(unittest.TestCase):
    def setUp(self):
        self.test_data_dir = os.path.join(os.path.dirname(__file__), "test_constraints_data")
        self.db = DBCore(data_dir=self.test_data_dir)
        self.db.execute_create_database("CREATE DATABASE test_constraints_db")
        self.db.use_database("test_constraints_db")

    def tearDown(self):
        if os.path.exists(self.test_data_dir):
            shutil.rmtree(self.test_data_dir)

    def test_autoincrement(self):
        """AUTOINCREMENT should automatically assign sequential IDs starting from 1."""
        success, msg = self.db.execute_create_table(
            "CREATE TABLE items (id INT PRIMARY KEY AUTOINCREMENT, name TEXT, price FLOAT)"
        )
        self.assertTrue(success)

        # Insert first item (omit autoincrement column)
        success, msg = self.db.execute_insert("INSERT INTO items VALUES ('Item A', 10.5)")
        self.assertTrue(success)

        # Insert second item
        success, msg = self.db.execute_insert("INSERT INTO items VALUES ('Item B', 20.0)")
        self.assertTrue(success)

        # Verify items
        result, success, err = self.db.execute_select("SELECT * FROM items")
        self.assertTrue(success)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["id"], 1)
        self.assertEqual(result[0]["name"], "Item A")
        self.assertEqual(result[1]["id"], 2)
        self.assertEqual(result[1]["name"], "Item B")

    def test_strict_type_validation_insert(self):
        """Strict type checking should reject incorrect types on INSERT."""
        success, msg = self.db.execute_create_table(
            "CREATE TABLE users (id INT PRIMARY KEY, age INT, name TEXT, score FLOAT)"
        )
        self.assertTrue(success)

        # Valid insert
        success, msg = self.db.execute_insert("INSERT INTO users VALUES (25, 'Alice', 95.5)")
        self.assertTrue(success)

        # Invalid insert: float into INT
        success, msg = self.db.execute_insert("INSERT INTO users VALUES (25.5, 'Bob', 80.0)")
        self.assertFalse(success)
        self.assertIn("Type mismatch", msg)

        # Invalid insert: string into INT
        success, msg = self.db.execute_insert("INSERT INTO users VALUES ('twenty', 'Charlie', 80.0)")
        self.assertFalse(success)
        self.assertIn("Type mismatch", msg)

        # Invalid insert: string into FLOAT
        success, msg = self.db.execute_insert("INSERT INTO users VALUES (30, 'Diana', 'high')")
        self.assertFalse(success)
        self.assertIn("Type mismatch", msg)

        # Invalid insert: boolean into INT
        success, msg = self.db.execute_insert("INSERT INTO users VALUES (True, 'Eve', 85.0)")
        self.assertFalse(success)
        self.assertIn("Type mismatch", msg)

    def test_strict_type_validation_update(self):
        """Strict type checking should reject incorrect types on UPDATE."""
        self.db.execute_create_table("CREATE TABLE products (id INT, qty INT, price FLOAT)")
        self.db.execute_insert("INSERT INTO products VALUES (1, 10, 5.99)")

        # Invalid update: float into INT
        success, msg = self.db.execute_update("UPDATE products SET qty = 12.5 WHERE id = 1")
        self.assertFalse(success)
        self.assertIn("Type mismatch", msg)

        # Invalid update: string into INT
        success, msg = self.db.execute_update("UPDATE products SET qty = 'zero' WHERE id = 1")
        self.assertFalse(success)
        self.assertIn("Type mismatch", msg)

        # Valid update
        success, msg = self.db.execute_update("UPDATE products SET qty = 15 WHERE id = 1")
        self.assertTrue(success)

    def test_check_constraints_insert(self):
        """CHECK constraints should validate insert values."""
        # 1. Inline check constraint
        success, msg = self.db.execute_create_table(
            "CREATE TABLE accounts (id INT, balance INT CHECK (balance >= 0), status TEXT)"
        )
        self.assertTrue(success)

        # Valid insert
        success, msg = self.db.execute_insert("INSERT INTO accounts VALUES (1, 100, 'Active')")
        self.assertTrue(success)

        # Invalid insert (violates check)
        success, msg = self.db.execute_insert("INSERT INTO accounts VALUES (2, -10, 'Active')")
        self.assertFalse(success)
        self.assertIn("Check constraint violated", msg)

        # 2. Standalone table-level check constraint
        success, msg = self.db.execute_create_table(
            "CREATE TABLE orders (id INT, qty INT, price INT, CHECK (qty > 0 AND price > 0))"
        )
        self.assertTrue(success)

        # Valid insert
        success, msg = self.db.execute_insert("INSERT INTO orders VALUES (1, 5, 10)")
        self.assertTrue(success)

        # Invalid insert
        success, msg = self.db.execute_insert("INSERT INTO orders VALUES (2, 0, 10)")
        self.assertFalse(success)
        self.assertIn("Check constraint violated", msg)

    def test_check_constraints_update(self):
        """CHECK constraints should validate updated values."""
        self.db.execute_create_table(
            "CREATE TABLE accounts (id INT, balance INT CHECK (balance >= 0))"
        )
        self.db.execute_insert("INSERT INTO accounts VALUES (1, 100)")

        # Invalid update (violates check balance >= 0)
        success, msg = self.db.execute_update("UPDATE accounts SET balance = -50 WHERE id = 1")
        self.assertFalse(success)
        self.assertIn("Check constraint violated", msg)

        # Verify balance remains unchanged
        result, _, _ = self.db.execute_select("SELECT balance FROM accounts WHERE id = 1")
        self.assertEqual(result[0], 100)


    def test_unique_not_null_default(self):
        """Test UNIQUE, NOT NULL, and DEFAULT constraints."""
        success, msg = self.db.execute_create_table(
            "CREATE TABLE students (id INT PRIMARY KEY, email TEXT UNIQUE, role TEXT DEFAULT 'user', score INT NOT NULL)"
        )
        self.assertTrue(success)

        # 1. Valid insert with all fields
        success, msg = self.db.execute_insert("INSERT INTO students VALUES ('test@example.com', 'admin', 100)")
        self.assertTrue(success)

        # 2. UNIQUE constraint violation
        success, msg = self.db.execute_insert("INSERT INTO students VALUES ('test@example.com', 'student', 90)")
        self.assertFalse(success)
        self.assertIn("UNIQUE constraint violated", msg)

        # 3. NOT NULL constraint violation (empty string interpreted as null)
        success, msg = self.db.execute_insert("INSERT INTO students VALUES ('test2@example.com', 'student', \"\")")
        self.assertFalse(success)
        self.assertIn("NOT NULL constraint violated", msg)

        # 4. DEFAULT constraint applied (empty string triggers default)
        success, msg = self.db.execute_insert("INSERT INTO students VALUES ('test3@example.com', \"\", 85)")
        self.assertTrue(success)
        
        # Verify default value
        result, _, _ = self.db.execute_select("SELECT * FROM students WHERE email = 'test3@example.com'")
        self.assertEqual(result[0]["role"], "user")
        self.assertEqual(result[0]["score"], 85)

if __name__ == "__main__":
    unittest.main()
