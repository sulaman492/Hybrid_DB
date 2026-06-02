import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.schema_manager import SchemaManager

def test_create_table():
    sm = SchemaManager("test_data")
    success, msg = sm.parse_create_table("CREATE TABLE Users (id INT PRIMARY KEY, name STRING, age INT);")
    print(f"Test result: {msg}")
    
if __name__ == "__main__":
    test_create_table()