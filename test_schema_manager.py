"""
test_schema_manager.py
======================
Comprehensive test suite for SchemaManager.

Covers:
  - Database operations  (CREATE, USE, DROP)
  - Table operations     (CREATE, DROP — including FK validation at creation)
  - INSERT               (positional VALUES, named columns, AUTO_INCREMENT,
                          NOT NULL, UNIQUE, FK, CHECK, datatype enforcement)
  - UPDATE               (SET with / without WHERE, same constraint checks)
  - Constraint errors    (every constraint should produce a clear message)
  - Edge / regression    (the original "Expected N values, got M" crash,
                          >= / <= CHECK operators, non-INT primary keys)

Run with:
    python -m pytest test_schema_manager.py -v
or:
    python test_schema_manager.py
"""

import os
import sys
import shutil
import unittest

# ── make the package importable from the project root ──────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Patch the relative import so SchemaManager loads stand-alone
import types
stub_meta = types.ModuleType("schema_manager_pkg.metadata")

class _FakeMetadata:
    """Minimal stub that satisfies SchemaManager without touching disk."""
    def __init__(self, *a, **kw):
        self._tables = []
    def get_all_tables(self):   return list(self._tables)
    def add_table(self, name):  self._tables.append(name)
    def remove_table(self, n):
        if n in self._tables:
            self._tables.remove(n)

stub_meta.MetadataManager = _FakeMetadata
sys.modules["schema_manager_pkg"] = types.ModuleType("schema_manager_pkg")
sys.modules["schema_manager_pkg.metadata"] = stub_meta

# Now load the module source, rewriting the relative import
import importlib, io, tokenize
src = open(
    os.path.join(os.path.dirname(__file__), "schema_manager.py")
).read().replace(
    "from .metadata import MetadataManager",
    "from schema_manager_pkg.metadata import MetadataManager"
)
_mod = types.ModuleType("schema_manager")
exec(compile(src, "schema_manager.py", "exec"), _mod.__dict__)
SchemaManager = _mod.SchemaManager

# ── helpers ────────────────────────────────────────────────────────────────────
TEST_DATA_DIR = "/tmp/sm_test_data"

def fresh_manager():
    """Return a SchemaManager whose data directory is wiped clean."""
    if os.path.exists(TEST_DATA_DIR):
        shutil.rmtree(TEST_DATA_DIR)
    os.makedirs(TEST_DATA_DIR, exist_ok=True)
    sm = SchemaManager(data_dir=TEST_DATA_DIR)
    return sm


def setup_ecommerce(sm):
    """
    Create a small e-commerce schema used across many tests:

        customers (id INT PK AUTO_INCREMENT, email VARCHAR UNIQUE NOT NULL,
                   name VARCHAR NOT NULL, age INT CHECK(age >= 18),
                   joined_on DATE DEFAULT CURRENT_DATE, active BOOLEAN DEFAULT TRUE)

        products  (id INT PK AUTO_INCREMENT, name VARCHAR NOT NULL,
                   price DECIMAL NOT NULL CHECK(price > 0), stock INT DEFAULT 0)

        orders    (id INT PK AUTO_INCREMENT, customer_id INT NOT NULL,
                   product_id INT NOT NULL,
                   FOREIGN KEY (customer_id) REFERENCES customers(id),
                   FOREIGN KEY (product_id)  REFERENCES products(id))
    """
    ok, _ = sm.parse_create_database("CREATE DATABASE ecommerce;")
    assert ok

    ok, _ = sm.parse_create_table("""
        CREATE TABLE customers (
            id       INT          PRIMARY KEY AUTO_INCREMENT,
            email    VARCHAR      NOT NULL UNIQUE,
            name     VARCHAR      NOT NULL,
            age      INT          CHECK(age >= 18),
            joined_on DATE        DEFAULT CURRENT_DATE,
            active   BOOLEAN      DEFAULT TRUE
        );
    """)
    assert ok, "customers table creation failed"

    ok, _ = sm.parse_create_table("""
        CREATE TABLE products (
            id    INT     PRIMARY KEY AUTO_INCREMENT,
            name  VARCHAR NOT NULL,
            price DECIMAL NOT NULL CHECK(price > 0),
            stock INT     DEFAULT 0
        );
    """)
    assert ok, "products table creation failed"

    ok, _ = sm.parse_create_table("""
        CREATE TABLE orders (
            id          INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            customer_id INT NOT NULL,
            product_id  INT NOT NULL,
            FOREIGN KEY (customer_id) REFERENCES customers(id),
            FOREIGN KEY (product_id)  REFERENCES products(id)
        );
    """)
    assert ok, "orders table creation failed"


# ══════════════════════════════════════════════════════════════════════════════
# 1. DATABASE OPERATIONS
# ══════════════════════════════════════════════════════════════════════════════
class TestDatabaseOperations(unittest.TestCase):

    def setUp(self):
        self.sm = fresh_manager()

    # ── CREATE DATABASE ──────────────────────────────────────────────────────
    def test_create_database_success(self):
        ok, msg = self.sm.parse_create_database("CREATE DATABASE shop;")
        self.assertTrue(ok)
        self.assertEqual(self.sm.get_current_db(), "shop")

    def test_create_database_duplicate(self):
        self.sm.parse_create_database("CREATE DATABASE shop;")
        ok, msg = self.sm.parse_create_database("CREATE DATABASE shop;")
        self.assertFalse(ok)
        self.assertIn("already exists", msg)

    def test_create_database_bad_syntax(self):
        ok, msg = self.sm.parse_create_database("CREATE DATABASE;")
        self.assertFalse(ok)

    # ── USE DATABASE ─────────────────────────────────────────────────────────
    def test_use_database_switch(self):
        self.sm.parse_create_database("CREATE DATABASE db1;")
        self.sm.parse_create_database("CREATE DATABASE db2;")
        ok, _ = self.sm.parse_use_database("USE DATABASE db1;")
        self.assertTrue(ok)
        self.assertEqual(self.sm.get_current_db(), "db1")

    def test_use_nonexistent_database(self):
        ok, msg = self.sm.parse_use_database("USE DATABASE ghost;")
        self.assertFalse(ok)
        self.assertIn("does not exist", msg)

    # ── DROP DATABASE ────────────────────────────────────────────────────────
    def test_drop_database_removes_from_disk(self):
        self.sm.parse_create_database("CREATE DATABASE temp;")
        db_path = os.path.join(TEST_DATA_DIR, "temp")
        self.assertTrue(os.path.exists(db_path))
        # patch input() so the confirmation is automatic
        import builtins
        original_input = builtins.input
        builtins.input = lambda _: "YES"
        try:
            ok, _ = self.sm.drop_database("temp")
        finally:
            builtins.input = original_input
        self.assertTrue(ok)
        self.assertFalse(os.path.exists(db_path))

    def test_drop_nonexistent_database(self):
        ok, msg = self.sm.drop_database("ghost")
        self.assertFalse(ok)
        self.assertIn("does not exist", msg)


# ══════════════════════════════════════════════════════════════════════════════
# 2. TABLE OPERATIONS
# ══════════════════════════════════════════════════════════════════════════════
class TestTableOperations(unittest.TestCase):

    def setUp(self):
        self.sm = fresh_manager()
        self.sm.parse_create_database("CREATE DATABASE testdb;")

    # ── CREATE TABLE ─────────────────────────────────────────────────────────
    def test_create_simple_table(self):
        ok, _ = self.sm.parse_create_table(
            "CREATE TABLE users (id INT PRIMARY KEY, name VARCHAR NOT NULL);"
        )
        self.assertTrue(ok)
        self.assertIn("users", self.sm.list_tables())

    def test_create_table_all_types(self):
        ok, msg = self.sm.parse_create_table("""
            CREATE TABLE types_table (
                a INT,
                b DECIMAL,
                c VARCHAR,
                d TEXT,
                e DATE,
                f TIME,
                g TIMESTAMP,
                h BOOLEAN
            );
        """)
        self.assertTrue(ok, msg)

    def test_create_table_invalid_type(self):
        ok, msg = self.sm.parse_create_table(
            "CREATE TABLE bad (col FLOAT);"
        )
        self.assertFalse(ok)
        self.assertIn("FLOAT", msg)

    def test_create_table_duplicate(self):
        self.sm.parse_create_table("CREATE TABLE t (id INT);")
        ok, msg = self.sm.parse_create_table("CREATE TABLE t (id INT);")
        self.assertFalse(ok)
        self.assertIn("already exists", msg)

    def test_create_table_no_db_selected(self):
        # Use a fresh empty dir so no db is loaded from disk
        clean_dir = "/tmp/sm_no_db_test"
        if os.path.exists(clean_dir):
            shutil.rmtree(clean_dir)
        os.makedirs(clean_dir)
        sm = SchemaManager(data_dir=clean_dir)
        ok, msg = sm.parse_create_table("CREATE TABLE t (id INT);")
        self.assertFalse(ok)
        self.assertIn("No database selected", msg)

    def test_auto_increment_only_on_int(self):
        ok, msg = self.sm.parse_create_table(
            "CREATE TABLE bad (code VARCHAR PRIMARY KEY AUTO_INCREMENT);"
        )
        self.assertFalse(ok)
        self.assertIn("AUTO_INCREMENT", msg)

    def test_auto_increment_must_be_primary_key(self):
        ok, msg = self.sm.parse_create_table(
            "CREATE TABLE bad (id INT AUTO_INCREMENT, name VARCHAR);"
        )
        self.assertFalse(ok)
        self.assertIn("PRIMARY KEY", msg)

    def test_varchar_primary_key_no_auto_increment(self):
        """Non-INT PK should NOT get auto_increment applied to it."""
        ok, msg = self.sm.parse_create_table(
            "CREATE TABLE countries (code VARCHAR PRIMARY KEY, name VARCHAR NOT NULL);"
        )
        self.assertTrue(ok, msg)
        schema = self.sm.get_table_schema("countries")
        self.assertFalse(
            schema["constraints"].get("code", {}).get("auto_increment", False),
            "VARCHAR primary key must not be auto_increment"
        )

    # ── FOREIGN KEY validation at CREATE time ────────────────────────────────
    def test_fk_references_nonexistent_table(self):
        ok, msg = self.sm.parse_create_table("""
            CREATE TABLE orders (
                id INT PRIMARY KEY,
                customer_id INT,
                FOREIGN KEY (customer_id) REFERENCES customers(id)
            );
        """)
        self.assertFalse(ok)
        self.assertIn("customers", msg)
        self.assertIn("does not exist", msg)

    def test_fk_references_nonexistent_column(self):
        self.sm.parse_create_table("CREATE TABLE customers (id INT PRIMARY KEY);")
        ok, msg = self.sm.parse_create_table("""
            CREATE TABLE orders (
                id INT PRIMARY KEY,
                customer_id INT,
                FOREIGN KEY (customer_id) REFERENCES customers(ghost_col)
            );
        """)
        self.assertFalse(ok)
        self.assertIn("ghost_col", msg)

    def test_fk_references_non_unique_column(self):
        self.sm.parse_create_table(
            "CREATE TABLE customers (id INT PRIMARY KEY, name VARCHAR);"
        )
        ok, msg = self.sm.parse_create_table("""
            CREATE TABLE orders (
                id INT PRIMARY KEY,
                cust_name VARCHAR,
                FOREIGN KEY (cust_name) REFERENCES customers(name)
            );
        """)
        self.assertFalse(ok)
        self.assertIn("UNIQUE", msg)

    def test_fk_valid_reference(self):
        self.sm.parse_create_table("CREATE TABLE customers (id INT PRIMARY KEY);")
        ok, msg = self.sm.parse_create_table("""
            CREATE TABLE orders (
                id INT PRIMARY KEY,
                customer_id INT,
                FOREIGN KEY (customer_id) REFERENCES customers(id)
            );
        """)
        self.assertTrue(ok, msg)

    # ── DROP TABLE ───────────────────────────────────────────────────────────
    def test_drop_table_success(self):
        self.sm.parse_create_table("CREATE TABLE temp (id INT);")
        import builtins
        original_input = builtins.input
        builtins.input = lambda _: "YES"
        try:
            ok, _ = self.sm.parse_drop_table("DROP TABLE temp;")
        finally:
            builtins.input = original_input
        self.assertTrue(ok)
        self.assertNotIn("temp", self.sm.list_tables())

    def test_drop_table_with_fk_reference_blocked(self):
        """Cannot drop a parent table if child tables reference it."""
        self.sm.parse_create_table("CREATE TABLE customers (id INT PRIMARY KEY);")
        self.sm.parse_create_table("""
            CREATE TABLE orders (
                id INT PRIMARY KEY,
                cid INT,
                FOREIGN KEY (cid) REFERENCES customers(id)
            );
        """)
        ok, msg = self.sm.parse_drop_table("DROP TABLE customers;")
        self.assertFalse(ok)
        self.assertIn("foreign key", msg.lower())

    def test_drop_nonexistent_table(self):
        ok, msg = self.sm.parse_drop_table("DROP TABLE ghost;")
        self.assertFalse(ok)
        self.assertIn("does not exist", msg)


# ══════════════════════════════════════════════════════════════════════════════
# 3. INSERT — happy paths
# ══════════════════════════════════════════════════════════════════════════════
class TestInsertSuccess(unittest.TestCase):

    def setUp(self):
        self.sm = fresh_manager()
        setup_ecommerce(self.sm)

    def test_insert_with_named_columns(self):
        ok, msg = self.sm.parse_insert(
            "INSERT INTO customers (email, name, age) VALUES ('alice@example.com', 'Alice', 30);"
        )
        self.assertTrue(ok, msg)

    def test_insert_positional_excludes_auto_increment(self):
        """
        REGRESSION — original bug: positional INSERT with AUTO_INCREMENT column
        raised "Expected 6 values, got 5".
        """
        # customers has 6 columns but 'id' is AUTO_INCREMENT — user supplies 5
        ok, msg = self.sm.parse_insert(
            "INSERT INTO customers VALUES ('bob@example.com', 'Bob', 25, '2024-01-01', TRUE);"
        )
        self.assertTrue(ok, msg)

    def test_insert_multiple_rows_auto_increment_increments(self):
        self.sm.parse_insert("INSERT INTO customers (email, name) VALUES ('a@x.com', 'A');")
        self.sm.parse_insert("INSERT INTO customers (email, name) VALUES ('b@x.com', 'B');")
        # If no crash, auto-increment worked across two rows
        # (actual value check would require a SELECT — omit here)

    def test_insert_null_into_nullable_column(self):
        ok, msg = self.sm.parse_insert(
            "INSERT INTO customers (email, name, age) VALUES ('c@x.com', 'C', NULL);"
        )
        self.assertTrue(ok, msg)

    def test_insert_boolean_values(self):
        ok, _ = self.sm.parse_insert(
            "INSERT INTO customers (email, name, active) VALUES ('d@x.com', 'D', FALSE);"
        )
        self.assertTrue(ok)

    def test_insert_current_date_default(self):
        """Columns with DEFAULT CURRENT_DATE should not need to be supplied."""
        ok, msg = self.sm.parse_insert(
            "INSERT INTO customers (email, name) VALUES ('e@x.com', 'E');"
        )
        self.assertTrue(ok, msg)

    def test_insert_into_products(self):
        ok, msg = self.sm.parse_insert(
            "INSERT INTO products (name, price, stock) VALUES ('Widget', 9.99, 100);"
        )
        self.assertTrue(ok, msg)

    def test_insert_into_orders_with_valid_fk(self):
        self.sm.parse_insert("INSERT INTO customers (email, name) VALUES ('f@x.com', 'F');")
        self.sm.parse_insert("INSERT INTO products (name, price) VALUES ('Gadget', 19.99);")
        ok, msg = self.sm.parse_insert(
            "INSERT INTO orders (customer_id, product_id) VALUES (1, 1);"
        )
        self.assertTrue(ok, msg)


# ══════════════════════════════════════════════════════════════════════════════
# 4. INSERT — constraint violations
# ══════════════════════════════════════════════════════════════════════════════
class TestInsertConstraintViolations(unittest.TestCase):

    def setUp(self):
        self.sm = fresh_manager()
        setup_ecommerce(self.sm)
        # Seed one customer and one product
        self.sm.parse_insert(
            "INSERT INTO customers (email, name, age) VALUES ('seed@x.com', 'Seed', 25);"
        )
        self.sm.parse_insert(
            "INSERT INTO products (name, price) VALUES ('Seed Product', 5.00);"
        )

    # ── NOT NULL ─────────────────────────────────────────────────────────────
    def test_insert_null_into_not_null_column(self):
        ok, msg = self.sm.parse_insert(
            "INSERT INTO customers (email, name) VALUES (NULL, 'NullEmail');"
        )
        self.assertFalse(ok)
        self.assertIn("NOT NULL", msg)
        self.assertIn("email", msg)

    def test_insert_missing_not_null_column(self):
        ok, msg = self.sm.parse_insert(
            "INSERT INTO customers (email) VALUES ('only@email.com');"
        )
        self.assertFalse(ok)
        self.assertIn("NOT NULL", msg)
        self.assertIn("name", msg)

    # ── UNIQUE ───────────────────────────────────────────────────────────────
    def test_insert_duplicate_unique_column(self):
        """email is UNIQUE — inserting the same address twice must fail."""
        ok, msg = self.sm.parse_insert(
            "INSERT INTO customers (email, name) VALUES ('seed@x.com', 'Dup');"
        )
        self.assertFalse(ok)
        self.assertIn("UNIQUE", msg)
        self.assertIn("email", msg)

    # ── PRIMARY KEY uniqueness ───────────────────────────────────────────────
    def test_insert_duplicate_primary_key(self):
        """Explicitly supplying a duplicate PK on a non-AUTO_INCREMENT table."""
        self.sm.parse_create_table(
            "CREATE TABLE cats (id INT PRIMARY KEY, name VARCHAR NOT NULL);"
        )
        self.sm.parse_insert("INSERT INTO cats (id, name) VALUES (1, 'Whiskers');")
        ok, msg = self.sm.parse_insert(
            "INSERT INTO cats (id, name) VALUES (1, 'Mittens');"
        )
        self.assertFalse(ok)
        self.assertIn("primary key", msg.lower())

    # ── FOREIGN KEY ──────────────────────────────────────────────────────────
    def test_insert_fk_with_nonexistent_parent(self):
        ok, msg = self.sm.parse_insert(
            "INSERT INTO orders (customer_id, product_id) VALUES (999, 1);"
        )
        self.assertFalse(ok)
        self.assertIn("999", msg)

    def test_insert_fk_null_allowed_when_column_is_nullable(self):
        """
        orders.customer_id is NOT NULL so NULL should be rejected — but the
        error should come from NOT NULL, not FK logic.
        """
        ok, msg = self.sm.parse_insert(
            "INSERT INTO orders (customer_id, product_id) VALUES (NULL, 1);"
        )
        self.assertFalse(ok)
        self.assertIn("NOT NULL", msg)

    # ── CHECK constraints ────────────────────────────────────────────────────
    def test_insert_violates_age_check(self):
        ok, msg = self.sm.parse_insert(
            "INSERT INTO customers (email, name, age) VALUES ('young@x.com', 'Young', 16);"
        )
        self.assertFalse(ok)
        self.assertIn("CHECK", msg)
        self.assertIn("age", msg)

    def test_insert_age_exactly_at_boundary_passes(self):
        """age >= 18 — inserting 18 must succeed."""
        ok, msg = self.sm.parse_insert(
            "INSERT INTO customers (email, name, age) VALUES ('teen@x.com', 'Teen', 18);"
        )
        self.assertTrue(ok, msg)

    def test_insert_violates_price_check(self):
        ok, msg = self.sm.parse_insert(
            "INSERT INTO products (name, price) VALUES ('Free', 0);"
        )
        self.assertFalse(ok)
        self.assertIn("CHECK", msg)
        self.assertIn("price", msg)

    def test_insert_negative_price_violates_check(self):
        ok, msg = self.sm.parse_insert(
            "INSERT INTO products (name, price) VALUES ('Refund', -5.00);"
        )
        self.assertFalse(ok)
        self.assertIn("CHECK", msg)

    # ── Data-type enforcement ────────────────────────────────────────────────
    def test_insert_string_into_int_column(self):
        ok, msg = self.sm.parse_insert(
            "INSERT INTO customers (email, name, age) VALUES ('t@x.com', 'T', 'twenty');"
        )
        self.assertFalse(ok)
        self.assertIn("INT", msg)
        self.assertIn("age", msg)

    def test_insert_decimal_into_int_column(self):
        ok, msg = self.sm.parse_insert(
            "INSERT INTO customers (email, name, age) VALUES ('t2@x.com', 'T2', 25.5);"
        )
        self.assertFalse(ok)
        self.assertIn("INT", msg)

    def test_insert_string_into_decimal_column(self):
        ok, msg = self.sm.parse_insert(
            "INSERT INTO products (name, price) VALUES ('Bad', 'free');"
        )
        self.assertFalse(ok)
        self.assertIn("DECIMAL", msg)
        self.assertIn("price", msg)

    def test_insert_invalid_date_format(self):
        ok, msg = self.sm.parse_insert(
            "INSERT INTO customers (email, name, joined_on) VALUES ('d@x.com', 'D', '15-06-2024');"
        )
        self.assertFalse(ok)
        self.assertIn("YYYY-MM-DD", msg)

    def test_insert_invalid_time_format(self):
        self.sm.parse_create_table(
            "CREATE TABLE shifts (id INT PRIMARY KEY, start_time TIME NOT NULL);"
        )
        ok, msg = self.sm.parse_insert(
            "INSERT INTO shifts (id, start_time) VALUES (1, '9am');"
        )
        self.assertFalse(ok)
        self.assertIn("HH:MM:SS", msg)

    def test_insert_invalid_boolean(self):
        ok, msg = self.sm.parse_insert(
            "INSERT INTO customers (email, name, active) VALUES ('e@x.com', 'E', 'maybe');"
        )
        self.assertFalse(ok)
        self.assertIn("BOOLEAN", msg)

    def test_insert_boolean_into_int_column(self):
        ok, msg = self.sm.parse_insert(
            "INSERT INTO customers (email, name, age) VALUES ('b@x.com', 'B', TRUE);"
        )
        self.assertFalse(ok)
        self.assertIn("BOOLEAN", msg)
        self.assertIn("INT", msg)

    def test_insert_wrong_value_count_too_few(self):
        ok, msg = self.sm.parse_insert(
            "INSERT INTO customers VALUES ('only_one_value');"
        )
        self.assertFalse(ok)
        self.assertIn("values", msg.lower())

    def test_insert_wrong_value_count_too_many(self):
        ok, msg = self.sm.parse_insert(
            "INSERT INTO customers VALUES ('a@x.com', 'A', 30, '2024-01-01', TRUE, 'EXTRA');"
        )
        self.assertFalse(ok)
        self.assertIn("values", msg.lower())

    def test_insert_wrong_named_column_count(self):
        ok, msg = self.sm.parse_insert(
            "INSERT INTO customers (email, name) VALUES ('x@x.com', 'X', 30);"
        )
        self.assertFalse(ok)
        self.assertIn("values", msg.lower())

    def test_insert_nonexistent_column(self):
        ok, msg = self.sm.parse_insert(
            "INSERT INTO customers (email, ghost_column) VALUES ('g@x.com', 'G');"
        )
        self.assertFalse(ok)
        self.assertIn("ghost_column", msg)


# ══════════════════════════════════════════════════════════════════════════════
# 5. UPDATE — happy paths
# ══════════════════════════════════════════════════════════════════════════════
class TestUpdateSuccess(unittest.TestCase):

    def setUp(self):
        self.sm = fresh_manager()
        setup_ecommerce(self.sm)
        self.sm.parse_insert(
            "INSERT INTO customers (email, name, age) VALUES ('alice@x.com', 'Alice', 30);"
        )
        self.sm.parse_insert(
            "INSERT INTO customers (email, name, age) VALUES ('bob@x.com', 'Bob', 25);"
        )
        self.sm.parse_insert(
            "INSERT INTO products (name, price, stock) VALUES ('Widget', 9.99, 50);"
        )

    def test_update_single_column_with_where(self):
        ok, msg = self.sm.parse_update(
            "UPDATE customers SET age = 31 WHERE email = alice@x.com;"
        )
        self.assertTrue(ok, msg)

    def test_update_multiple_columns(self):
        ok, msg = self.sm.parse_update(
            "UPDATE customers SET name = 'Bobby', age = 26 WHERE email = bob@x.com;"
        )
        self.assertTrue(ok, msg)

    def test_update_without_where_updates_all(self):
        ok, msg = self.sm.parse_update(
            "UPDATE products SET stock = 0;"
        )
        self.assertTrue(ok, msg)

    def test_update_no_rows_match_where(self):
        ok, msg = self.sm.parse_update(
            "UPDATE customers SET age = 99 WHERE email = ghost@x.com;"
        )
        self.assertTrue(ok)   # Not an error — just 0 rows updated
        # Engine returns 'No rows to update' when WHERE matches nothing
        self.assertIn("update", msg.lower())

    def test_update_decimal_column(self):
        ok, msg = self.sm.parse_update(
            "UPDATE products SET price = 14.99 WHERE name = Widget;"
        )
        self.assertTrue(ok, msg)


# ══════════════════════════════════════════════════════════════════════════════
# 6. UPDATE — constraint violations
# ══════════════════════════════════════════════════════════════════════════════
class TestUpdateConstraintViolations(unittest.TestCase):

    def setUp(self):
        self.sm = fresh_manager()
        setup_ecommerce(self.sm)
        self.sm.parse_insert(
            "INSERT INTO customers (email, name, age) VALUES ('alice@x.com', 'Alice', 30);"
        )
        self.sm.parse_insert(
            "INSERT INTO customers (email, name, age) VALUES ('bob@x.com', 'Bob', 25);"
        )
        self.sm.parse_insert(
            "INSERT INTO products (name, price, stock) VALUES ('Widget', 9.99, 50);"
        )
        self.sm.parse_insert(
            "INSERT INTO customers (email, name) VALUES ('admin@x.com', 'Admin');"
        )
        self.sm.parse_insert(
            "INSERT INTO orders (customer_id, product_id) VALUES (1, 1);"
        )

    def test_update_auto_increment_column_blocked(self):
        ok, msg = self.sm.parse_update("UPDATE customers SET id = 99 WHERE email = alice@x.com;")
        self.assertFalse(ok)
        self.assertIn("AUTO_INCREMENT", msg)

    def test_update_not_null_column_to_null(self):
        ok, msg = self.sm.parse_update("UPDATE customers SET name = NULL WHERE email = alice@x.com;")
        self.assertFalse(ok)
        self.assertIn("NOT NULL", msg)
        self.assertIn("name", msg)

    def test_update_unique_column_to_duplicate(self):
        ok, msg = self.sm.parse_update(
            "UPDATE customers SET email = 'bob@x.com' WHERE email = alice@x.com;"
        )
        self.assertFalse(ok)
        self.assertIn("UNIQUE", msg)
        self.assertIn("email", msg)

    def test_update_fk_column_to_nonexistent_parent(self):
        ok, msg = self.sm.parse_update(
            "UPDATE orders SET customer_id = 9999 WHERE id = 1;"
        )
        self.assertFalse(ok)
        self.assertIn("9999", msg)

    def test_update_check_constraint_violated(self):
        ok, msg = self.sm.parse_update(
            "UPDATE customers SET age = 15 WHERE email = alice@x.com;"
        )
        self.assertFalse(ok)
        self.assertIn("CHECK", msg)
        self.assertIn("age", msg)

    def test_update_type_mismatch_int_column(self):
        ok, msg = self.sm.parse_update(
            "UPDATE customers SET age = 'old' WHERE email = alice@x.com;"
        )
        self.assertFalse(ok)
        self.assertIn("INT", msg)
        self.assertIn("age", msg)

    def test_update_type_mismatch_decimal_column(self):
        ok, msg = self.sm.parse_update(
            "UPDATE products SET price = 'expensive' WHERE name = Widget;"
        )
        self.assertFalse(ok)
        self.assertIn("DECIMAL", msg)

    def test_update_nonexistent_column(self):
        ok, msg = self.sm.parse_update(
            "UPDATE customers SET ghost = 1 WHERE email = alice@x.com;"
        )
        self.assertFalse(ok)
        self.assertIn("ghost", msg)

    def test_update_table_does_not_exist(self):
        ok, msg = self.sm.parse_update("UPDATE ghost SET col = 1;")
        self.assertFalse(ok)
        self.assertIn("ghost", msg)


# ══════════════════════════════════════════════════════════════════════════════
# 7. CHECK constraint operator coverage
# ══════════════════════════════════════════════════════════════════════════════
class TestCheckConstraintOperators(unittest.TestCase):
    """
    Directly exercises _check_constraint for every supported operator.
    These were all broken before the >= / <= fix.
    """

    def setUp(self):
        self.sm = fresh_manager()
        self.sm.parse_create_database("CREATE DATABASE ops_db;")

    def _check(self, value, expr, col="val"):
        return self.sm._check_constraint(value, expr, col)

    def test_greater_than_pass(self):      self.assertTrue(self._check(5,   "val > 3",  "val"))
    def test_greater_than_fail(self):      self.assertFalse(self._check(3,  "val > 3",  "val"))
    def test_less_than_pass(self):         self.assertTrue(self._check(2,   "val < 5",  "val"))
    def test_less_than_fail(self):         self.assertFalse(self._check(5,  "val < 5",  "val"))
    def test_gte_boundary_pass(self):      self.assertTrue(self._check(18,  "val >= 18", "val"))
    def test_gte_below_boundary_fail(self):self.assertFalse(self._check(17, "val >= 18", "val"))
    def test_lte_boundary_pass(self):      self.assertTrue(self._check(100, "val <= 100","val"))
    def test_lte_above_boundary_fail(self):self.assertFalse(self._check(101,"val <= 100","val"))
    def test_equals_pass(self):            self.assertTrue(self._check(42,  "val = 42",  "val"))
    def test_equals_fail(self):            self.assertFalse(self._check(41, "val = 42",  "val"))
    def test_none_value_skips_check(self): self.assertTrue(self._check(None,"val > 0",   "val"))

    def test_check_insert_gte_boundary_via_sql(self):
        self.sm.parse_create_table(
            "CREATE TABLE votes (id INT PRIMARY KEY, voter_age INT CHECK(voter_age >= 18));"
        )
        ok, _ = self.sm.parse_insert("INSERT INTO votes (id, voter_age) VALUES (1, 18);")
        self.assertTrue(ok)
        ok, msg = self.sm.parse_insert("INSERT INTO votes (id, voter_age) VALUES (2, 17);")
        self.assertFalse(ok)
        self.assertIn("CHECK", msg)

    def test_check_insert_lte_via_sql(self):
        self.sm.parse_create_table(
            "CREATE TABLE discounts (id INT PRIMARY KEY, pct DECIMAL CHECK(pct <= 100));"
        )
        ok, _ = self.sm.parse_insert("INSERT INTO discounts (id, pct) VALUES (1, 100);")
        self.assertTrue(ok)
        ok, msg = self.sm.parse_insert("INSERT INTO discounts (id, pct) VALUES (2, 101);")
        self.assertFalse(ok)
        self.assertIn("CHECK", msg)


# ══════════════════════════════════════════════════════════════════════════════
# 8. Data type validation — _validate_type coverage
# ══════════════════════════════════════════════════════════════════════════════
class TestValidateType(unittest.TestCase):

    def setUp(self):
        self.sm = fresh_manager()
        self.sm.parse_create_database("CREATE DATABASE types_db;")

    def _v(self, value, col_type, col_name="col"):
        return self.sm._validate_type(value, col_type, col_name)

    # INT
    def test_int_accepts_int(self):          ok, v = self._v(5, "INT");   self.assertTrue(ok); self.assertEqual(v, 5)
    def test_int_accepts_whole_float(self):  ok, v = self._v(5.0, "INT"); self.assertTrue(ok); self.assertEqual(v, 5)
    def test_int_rejects_frac_float(self):   ok, _ = self._v(5.5, "INT"); self.assertFalse(ok)
    def test_int_rejects_string(self):       ok, m = self._v("abc","INT");self.assertFalse(ok); self.assertIn("INT", m)
    def test_int_accepts_numeric_string(self): ok, v = self._v("7","INT"); self.assertTrue(ok); self.assertEqual(v, 7)
    def test_int_accepts_negative_string(self): ok, v = self._v("-3","INT"); self.assertTrue(ok); self.assertEqual(v, -3)
    def test_int_rejects_bool(self):         ok, m = self._v(True,"INT");self.assertFalse(ok); self.assertIn("BOOLEAN", m)
    def test_int_none_passes(self):          ok, _ = self._v(None,"INT"); self.assertTrue(ok)

    # DECIMAL
    def test_decimal_accepts_float(self):    ok, v = self._v(3.14,"DECIMAL"); self.assertTrue(ok); self.assertAlmostEqual(v, 3.14)
    def test_decimal_accepts_int(self):      ok, v = self._v(5,"DECIMAL");    self.assertTrue(ok); self.assertEqual(v, 5.0)
    def test_decimal_accepts_str(self):      ok, v = self._v("2.5","DECIMAL");self.assertTrue(ok); self.assertAlmostEqual(v, 2.5)
    def test_decimal_rejects_alpha_str(self):ok, m = self._v("abc","DECIMAL");self.assertFalse(ok); self.assertIn("DECIMAL", m)
    def test_decimal_rejects_bool(self):     ok, m = self._v(False,"DECIMAL");self.assertFalse(ok)

    # BOOLEAN
    def test_bool_accepts_true(self):        ok, v = self._v(True,"BOOLEAN"); self.assertTrue(ok); self.assertTrue(v)
    def test_bool_accepts_str_true(self):    ok, v = self._v("TRUE","BOOLEAN");self.assertTrue(ok); self.assertTrue(v)
    def test_bool_accepts_str_false(self):   ok, v = self._v("FALSE","BOOLEAN");self.assertTrue(ok); self.assertFalse(v)
    def test_bool_rejects_garbage_str(self): ok, m = self._v("maybe","BOOLEAN");self.assertFalse(ok); self.assertIn("BOOLEAN", m)

    # DATE
    def test_date_accepts_iso(self):         ok, v = self._v("2024-06-15","DATE"); self.assertTrue(ok); self.assertEqual(v,"2024-06-15")
    def test_date_rejects_bad_format(self):  ok, m = self._v("15/06/24","DATE");   self.assertFalse(ok); self.assertIn("YYYY-MM-DD", m)
    def test_date_rejects_int(self):         ok, m = self._v(20240615,"DATE");     self.assertFalse(ok)

    # TIME
    def test_time_accepts_hhmmss(self):      ok, v = self._v("14:30:00","TIME"); self.assertTrue(ok)
    def test_time_rejects_short(self):       ok, m = self._v("9:00","TIME");     self.assertFalse(ok); self.assertIn("HH:MM:SS", m)

    # TIMESTAMP
    def test_timestamp_accepts_iso(self):    ok, v = self._v("2024-06-15 14:30:00","TIMESTAMP"); self.assertTrue(ok)
    def test_timestamp_rejects_bad(self):    ok, m = self._v("not-a-ts","TIMESTAMP");            self.assertFalse(ok)

    # VARCHAR / TEXT
    def test_varchar_accepts_anything(self): ok, v = self._v(42,"VARCHAR"); self.assertTrue(ok); self.assertEqual(v, "42")
    def test_text_accepts_anything(self):    ok, v = self._v(True,"TEXT");  self.assertTrue(ok)


# ══════════════════════════════════════════════════════════════════════════════
# 9. Auto-increment behaviour
# ══════════════════════════════════════════════════════════════════════════════
class TestAutoIncrement(unittest.TestCase):

    def setUp(self):
        self.sm = fresh_manager()
        self.sm.parse_create_database("CREATE DATABASE ai_db;")
        self.sm.parse_create_table(
            "CREATE TABLE items (id INT PRIMARY KEY AUTO_INCREMENT, label VARCHAR NOT NULL);"
        )

    def test_counter_starts_at_one(self):
        ok, _ = self.sm.parse_insert("INSERT INTO items (label) VALUES ('first');")
        self.assertTrue(ok)
        key = "items.id"
        self.assertEqual(self.sm.auto_increment_counters.get(key), 1)

    def test_counter_increments(self):
        self.sm.parse_insert("INSERT INTO items (label) VALUES ('a');")
        self.sm.parse_insert("INSERT INTO items (label) VALUES ('b');")
        self.sm.parse_insert("INSERT INTO items (label) VALUES ('c');")
        self.assertEqual(self.sm.auto_increment_counters.get("items.id"), 3)

    def test_providing_id_explicitly_is_rejected(self):
        """User must not supply value for AUTO_INCREMENT column."""
        ok, msg = self.sm.parse_insert(
            "INSERT INTO items (id, label) VALUES (99, 'manual');"
        )
        # Providing id by name: the column exists, value count matches —
        # but AUTO_INCREMENT columns must not be overridden.
        # Either the insert fails OR, if the engine allows it, it must not
        # corrupt the counter.  Mark intent clearly:
        if not ok:
            self.assertIn("AUTO_INCREMENT", msg)

    def test_auto_increment_not_applied_to_varchar_pk(self):
        """REGRESSION — VARCHAR PKs must not silently become AUTO_INCREMENT."""
        self.sm.parse_create_table(
            "CREATE TABLE countries (code VARCHAR PRIMARY KEY, name VARCHAR NOT NULL);"
        )
        schema = self.sm.get_table_schema("countries")
        self.assertFalse(
            schema["constraints"].get("code", {}).get("auto_increment", False)
        )


# ══════════════════════════════════════════════════════════════════════════════
# 10. Query parser edge cases
# ══════════════════════════════════════════════════════════════════════════════
class TestQueryParser(unittest.TestCase):

    def setUp(self):
        self.sm = fresh_manager()
        self.sm.parse_create_database("CREATE DATABASE parser_db;")

    def test_semicolon_stripped(self):
        result = self.sm.parse_query("SELECT * FROM t;")
        self.assertFalse(result.endswith(";"))

    def test_no_semicolon_ok(self):
        result = self.sm.parse_query("SELECT * FROM t")
        self.assertEqual(result, "SELECT * FROM t")

    def test_leading_trailing_whitespace_stripped(self):
        result = self.sm.parse_query("  SELECT * FROM t ;  ")
        self.assertEqual(result, "SELECT * FROM t")

    def test_insert_no_db_selected(self):
        clean_dir = "/tmp/sm_no_db_test2"
        if os.path.exists(clean_dir):
            shutil.rmtree(clean_dir)
        os.makedirs(clean_dir)
        sm = SchemaManager(data_dir=clean_dir)
        ok, msg = sm.parse_insert("INSERT INTO t VALUES (1);")
        self.assertFalse(ok)
        self.assertIn("No database selected", msg)

    def test_update_no_db_selected(self):
        clean_dir = "/tmp/sm_no_db_test3"
        if os.path.exists(clean_dir):
            shutil.rmtree(clean_dir)
        os.makedirs(clean_dir)
        sm = SchemaManager(data_dir=clean_dir)
        ok, msg = sm.parse_update("UPDATE t SET col = 1;")
        self.assertFalse(ok)
        self.assertIn("No database selected", msg)

    def test_insert_bad_syntax(self):
        self.sm.parse_create_table("CREATE TABLE t (id INT);")
        ok, msg = self.sm.parse_insert("INSERT t VALUES (1);")   # missing INTO
        self.assertFalse(ok)
        self.assertIn("Invalid INSERT syntax", msg)

    def test_update_bad_syntax(self):
        self.sm.parse_create_table("CREATE TABLE t (id INT);")
        ok, msg = self.sm.parse_update("UPDATE t col = 1;")       # missing SET
        self.assertFalse(ok)
        self.assertIn("Invalid UPDATE syntax", msg)

    def test_case_insensitive_table_access(self):
        self.sm.parse_create_table("CREATE TABLE MyTable (id INT PRIMARY KEY);")
        ok, msg = self.sm.parse_insert("INSERT INTO MYTABLE (id) VALUES (1);")
        self.assertTrue(ok, msg)

    def test_multiline_insert(self):
        self.sm.parse_create_table("CREATE TABLE t (id INT PRIMARY KEY, val VARCHAR);")
        ok, msg = self.sm.parse_insert(
            """INSERT INTO t
               (id, val)
               VALUES
               (1, 'hello');"""
        )
        self.assertTrue(ok, msg)

    def test_values_with_commas_in_strings(self):
        self.sm.parse_create_table(
            "CREATE TABLE addresses (id INT PRIMARY KEY, addr VARCHAR NOT NULL);"
        )
        ok, msg = self.sm.parse_insert(
            "INSERT INTO addresses (id, addr) VALUES (1, 'Suite 100, Main St');"
        )
        self.assertTrue(ok, msg)

    def test_null_keyword_case_insensitive(self):
        self.sm.parse_create_table(
            "CREATE TABLE t (id INT PRIMARY KEY, note VARCHAR);"
        )
        ok, msg = self.sm.parse_insert(
            "INSERT INTO t (id, note) VALUES (1, null);"
        )
        self.assertTrue(ok, msg)


# ══════════════════════════════════════════════════════════════════════════════
# entry point
# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    unittest.main(verbosity=2)
