import unittest
import os
import shutil
from src.db_core import DBCore

class TestViewsAndTriggers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_dir = os.path.join(os.path.dirname(__file__), "test_views_triggers_data")
        if os.path.exists(cls.test_dir):
            shutil.rmtree(cls.test_dir)
        os.makedirs(cls.test_dir)
        
    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.test_dir):
            shutil.rmtree(cls.test_dir)
            
    def setUp(self):
        self.db = DBCore(data_dir=self.test_dir)
        self.db.execute_create_database("CREATE DATABASE test_db")
        self.db.use_database("test_db")
        
    def test_views(self):
        # Create base table
        self.db.execute_create_table("CREATE TABLE employees (id INT PRIMARY KEY, name TEXT, salary INT, dept TEXT)")
        self.db.execute_insert("INSERT INTO employees VALUES ('Alice', 50000, 'HR')")
        self.db.execute_insert("INSERT INTO employees VALUES ('Bob', 70000, 'Engineering')")
        self.db.execute_insert("INSERT INTO employees VALUES ('Charlie', 80000, 'Engineering')")

        # Create view for Engineering dept
        success, msg = self.db.execute_create_view("CREATE VIEW eng_employees AS SELECT * FROM employees WHERE dept = 'Engineering'")
        self.assertTrue(success, msg)
        
        # Query view
        result, success, err = self.db.execute_select("SELECT * FROM eng_employees")
        self.assertTrue(success)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["name"], "Bob")
        self.assertEqual(result[1]["name"], "Charlie")
        
        # Query view with distinct
        self.db.execute_insert("INSERT INTO employees VALUES ('Dave', 70000, 'Engineering')")
        result, success, err = self.db.execute_select("SELECT DISTINCT salary FROM eng_employees")
        self.assertTrue(success)
        self.assertEqual(len(result), 2)
        
    def test_triggers(self):
        self.db.execute_create_table("CREATE TABLE users (id INT PRIMARY KEY, name TEXT)")
        self.db.execute_create_table("CREATE TABLE logs (id INT PRIMARY KEY, msg TEXT)")

        # Create AFTER INSERT trigger
        success, msg = self.db.execute_create_trigger(
            "CREATE TRIGGER log_user_insert AFTER INSERT ON users BEGIN INSERT INTO logs VALUES ('User added') END"
        )
        self.assertTrue(success, msg)
        
        # Trigger it
        self.db.execute_insert("INSERT INTO users VALUES ('Alice')")
        self.db.execute_insert("INSERT INTO users VALUES ('Bob')")
        
        # Check logs
        result, success, err = self.db.execute_select("SELECT * FROM logs")
        self.assertTrue(success)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["msg"], "User added")

if __name__ == "__main__":
    unittest.main()
