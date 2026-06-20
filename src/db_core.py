import os
import re
import threading
from .schema_manager import SchemaManager
from .storage_manager import StorageManager
from .query_parser import QueryParser

class DBCore:
    def __init__(self, data_dir="data"):
        self.data_dir = data_dir
        self.schema_manager = SchemaManager(data_dir)
        self.storage_manager = StorageManager(data_dir)
        self.parser = QueryParser()
        
        # Transaction state
        self.db_lock = threading.RLock()
        self.in_transaction = False
        self.transaction_tables = set()
        
        # Auto-recover any orphaned transactions from previous crashes
        for db_name in os.listdir(data_dir):
            db_path = os.path.join(data_dir, db_name)
            if os.path.isdir(db_path) and db_name != "_metadata":
                self.storage_manager.auto_recover_crashes(db_name)
    
    # ========== DATABASE METHODS ==========
    def execute_create_database(self, query):
        """Execute CREATE DATABASE"""
        return self.schema_manager.parse_create_database(query)
    
    def use_database(self, db_name):
        """Switch to another database"""
        return self.schema_manager.use_database(db_name)
    
    def list_databases(self):
        """List all databases"""
        return self.schema_manager.list_databases()
    
    def get_current_db(self):
        """Get current database name"""
        return self.schema_manager.get_current_db()
        
    # ========== TRANSACTION METHODS ==========
    def execute_begin(self):
        """Begin a transaction"""
        self.in_transaction = True
        self.transaction_tables = set()
        return True, "Transaction started"
        
    def execute_commit(self):
        """Commit a transaction"""
        if not self.in_transaction:
            return False, "No active transaction to commit"
            
        current_db = self.get_current_db()
        if current_db:
            self.storage_manager.discard_backups(current_db, self.transaction_tables)
            
        self.in_transaction = False
        self.transaction_tables = set()
        return True, "Transaction committed"
        
    def execute_rollback(self):
        """Rollback a transaction"""
        if not self.in_transaction:
            return False, "No active transaction to rollback"
            
        current_db = self.get_current_db()
        if current_db:
            self.storage_manager.restore_backups(current_db, self.transaction_tables)
            # Reload schema cache in case tables were created/dropped
            self.schema_manager._load_all_schemas()
            
        self.in_transaction = False
        self.transaction_tables = set()
        return True, "Transaction rolled back"
        
    def _ensure_transaction_backup(self, table_name):
        """Backup table before modification if in a transaction"""
        if self.in_transaction and table_name not in self.transaction_tables:
            current_db = self.get_current_db()
            if current_db:
                self.storage_manager.backup_table(current_db, table_name)
                self.transaction_tables.add(table_name)
    
    # ========== TABLE METHODS ==========
    def execute_create_table(self, query):
        """Execute CREATE TABLE"""
        match = re.search(r"CREATE TABLE (\w+)", query, re.IGNORECASE)
        if match:
            self._ensure_transaction_backup(match.group(1))
        return self.schema_manager.parse_create_table(query)
    
    def show_tables(self):
        """Show all tables in current database"""
        current_db = self.schema_manager.get_current_db()
        if not current_db:
            return []
        return self.schema_manager.list_tables()
    
    def describe_table(self, table_name):
        """Describe table schema"""
        self.schema_manager.display_schema(table_name)
    
    # ========== VIEWS AND TRIGGERS METHODS ==========
    def execute_create_view(self, query):
        """Execute CREATE VIEW"""
        return self.schema_manager.parse_create_view(query, self.parser)
        
    def execute_create_trigger(self, query):
        """Execute CREATE TRIGGER"""
        return self.schema_manager.parse_create_trigger(query, self.parser)
        
    def _execute_triggers(self, table_name, event, action, new_row=None, old_row=None):
        """Execute triggers for a given table, event (BEFORE/AFTER), and action (INSERT/UPDATE/DELETE)"""
        current_db = self.schema_manager.get_current_db()
        if not current_db or not self.schema_manager.metadata:
            return True, ""
            
        triggers = self.schema_manager.metadata.get_triggers(table_name)
        for t in triggers:
            if t["event"] == event and t["action"] == action:
                # Execute the trigger query
                query = t["query"]
                
                # Replace NEW.* and OLD.* variables
                if new_row:
                    for col, val in new_row.items():
                        rep = f"'{val}'" if isinstance(val, str) else ("NULL" if val is None else str(val))
                        query = re.sub(fr"\bNEW\.{col}\b", rep, query, flags=re.IGNORECASE)
                if old_row:
                    for col, val in old_row.items():
                        rep = f"'{val}'" if isinstance(val, str) else ("NULL" if val is None else str(val))
                        query = re.sub(fr"\bOLD\.{col}\b", rep, query, flags=re.IGNORECASE)
                
                # Try executing the query by determining its type
                q_upper = query.upper()
                if q_upper.startswith("INSERT INTO"):
                    success, msg = self.execute_insert(query)
                elif q_upper.startswith("UPDATE "):
                    success, msg = self.execute_update(query)
                elif q_upper.startswith("DELETE FROM"):
                    success, msg = self.execute_delete(query)
                else:
                    success, msg = False, "Unsupported trigger query type"
                    
                if not success:
                    return False, f"Trigger '{t['name']}' failed: {msg}"
        return True, ""

    # ========== DATA METHODS ==========
    def execute_insert(self, query):
        """Execute INSERT INTO"""
        current_db = self.schema_manager.get_current_db()
        if not current_db:
            return False, "No database selected"
        
        table_name, values = self.parser.parse_insert(query)
        
        if not table_name:
            return False, "Invalid INSERT syntax"
        
        schema = self.schema_manager.get_table_schema(table_name)
        if not schema:
            return False, f"Table '{table_name}' not found"
        
        # Resolve autoincrement
        autoincrement_col = None
        autoincrement_idx = -1
        for i, col in enumerate(schema["columns"]):
            if col.get("autoincrement") or (col["name"] in schema.get("primary_key", []) and col["type"] == "INT"):
                autoincrement_col = col["name"]
                autoincrement_idx = i
                break
        
        expected_count = len(schema["columns"])
        
        if autoincrement_idx != -1:
            if len(values) == expected_count:
                # User provided all columns including AUTOINCREMENT — use as-is
                # (common from triggers or explicit inserts)
                rows = self.storage_manager.load_rows(current_db, table_name)
            elif len(values) == expected_count - 1:
                # User omitted AUTOINCREMENT column — auto-generate the ID
                rows = self.storage_manager.load_rows(current_db, table_name)
                
                if not rows:
                    next_id = 1
                else:
                    existing_ids = [r.get(autoincrement_col) for r in rows if r.get(autoincrement_col) is not None]
                    next_id = max(existing_ids) + 1 if existing_ids else 1
                    
                # Insert the next_id into the values list at the correct index
                values.insert(autoincrement_idx, next_id)
            else:
                return False, f"Expected {expected_count - 1} values (excluding AUTOINCREMENT column '{autoincrement_col}'), got {len(values)}"
        else:
            if len(values) != expected_count:
                return False, f"Expected {expected_count} values, got {len(values)}"
            
            # Load existing rows
            rows = self.storage_manager.load_rows(current_db, table_name)

        # Resolve Defaults, NOT NULL, and UNIQUE constraints
        for i, col in enumerate(schema["columns"]):
            if i >= len(values):
                break
                
            val = values[i]
            
            # 1. Resolve Default and NOT NULL
            if val == "" or val is None:
                if col.get("default") is not None:
                    values[i] = col["default"]
                    val = values[i]
                elif col.get("not_null"):
                    return False, f"NOT NULL constraint violated: column '{col['name']}' cannot be empty/null"
            
            # 2. Enforce UNIQUE (and PRIMARY KEY implies UNIQUE)
            is_unique = col.get("unique") or col["name"] in schema.get("primary_key", [])
            if is_unique and val is not None and val != "":
                for row in rows:
                    if row.get(col["name"]) == val:
                        return False, f"UNIQUE constraint violated: value '{val}' already exists in column '{col['name']}'"

        # Strict type verification
        for i, col in enumerate(schema["columns"]):
            val = values[i]
            if val is not None:
                if col["type"] == "INT":
                    if not isinstance(val, int) or isinstance(val, bool):
                        return False, f"Type mismatch: column '{col['name']}' expects INT, got {type(val).__name__}"
                elif col["type"] in ("FLOAT", "REAL"):
                    if not isinstance(val, (int, float)) or isinstance(val, bool):
                        return False, f"Type mismatch: column '{col['name']}' expects FLOAT/REAL, got {type(val).__name__}"

        # Evaluate CHECK constraints
        row_dict = {col["name"]: values[i] for i, col in enumerate(schema["columns"])}
        checks = schema.get("checks", [])
        for check in checks:
            if not self.parser.evaluate_where(row_dict, check):
                return False, f"Check constraint violated: {check}"

        # Evaluate FOREIGN KEY constraints
        foreign_keys = schema.get("foreign_keys", [])
        for fk in foreign_keys:
            fk_col = fk["column"]
            ref_table = fk["ref_table"]
            ref_col = fk["ref_column"]
            
            val = row_dict.get(fk_col)
            if val is not None and val != "":
                ref_rows = self.storage_manager.load_rows(current_db, ref_table)
                if ref_rows is None:
                    return False, f"Foreign key constraint violated: referenced table '{ref_table}' does not exist"
                exists = any(r.get(ref_col) == val for r in ref_rows)
                if not exists:
                    return False, f"Foreign key constraint violated: value '{val}' not found in {ref_table}({ref_col})"

        # Fire BEFORE INSERT triggers
        success, msg = self._execute_triggers(table_name, "BEFORE", "INSERT", new_row=row_dict)
        if not success:
            return False, msg

        # Backup before writing
        self._ensure_transaction_backup(table_name)

        self.storage_manager.insert_row(current_db, table_name, values)
        
        for i, col in enumerate(schema["columns"]):
            self.storage_manager.insert_into_column_store(
                current_db, table_name, col["name"], values[i]
            )
        
        # Fire AFTER INSERT triggers
        success, msg = self._execute_triggers(table_name, "AFTER", "INSERT", new_row=row_dict)
        if not success:
            return False, msg

        return True, f"Inserted into '{table_name}'"
    
    def execute_delete(self, query):
        """Execute DELETE FROM (with or without WHERE)"""
        current_db = self.schema_manager.get_current_db()
        if not current_db:
            return False, "No database selected"
        
        table_name, where_condition = self.parser.parse_delete(query)
        
        if not table_name:
            return False, "Invalid DELETE syntax. Use: DELETE FROM table_name; or DELETE FROM table_name WHERE condition;"
        
        schema = self.schema_manager.get_table_schema(table_name)
        if not schema:
            return False, f"Table '{table_name}' not found"
        
        # Load all rows
        rows = self.storage_manager.load_rows(current_db, table_name)
        
        if not rows:
            return True, f"No rows to delete from '{table_name}'"
        
        # Enforce ON DELETE RESTRICT for foreign keys pointing to this table
        referencing = self.schema_manager.get_referencing_tables(table_name)
        if referencing:
            for row in rows:
                if where_condition and not self.parser.evaluate_where(row, where_condition):
                    continue
                # This row is going to be deleted
                for ref_t, ref_c in referencing:
                    ref_schema = self.schema_manager.get_table_schema(ref_t)
                    if not ref_schema: continue
                    fk_def = next((f for f in ref_schema.get("foreign_keys", []) if f["ref_table"] == table_name), None)
                    if not fk_def: continue
                    
                    target_col = fk_def["ref_column"]
                    target_val = row.get(target_col)
                    
                    ref_rows = self.storage_manager.load_rows(current_db, ref_t)
                    if ref_rows:
                        if any(r.get(ref_c) == target_val for r in ref_rows):
                            return False, f"Foreign key constraint violated: row in '{table_name}' is referenced by '{ref_t}({ref_c})'"
        
        # Filter rows to keep
        rows_to_keep = []
        deleted_count = 0
        
        if where_condition:
            # DELETE with WHERE clause - only delete matching rows
            for row in rows:
                if self.parser.evaluate_where(row, where_condition):
                    deleted_count += 1
                else:
                    rows_to_keep.append(row)
        else:
            # DELETE without WHERE clause - delete ALL rows
            deleted_count = len(rows)
            rows_to_keep = []
        
        # Fire BEFORE DELETE triggers
        for row in rows: # We need to know which rows are actually going to be deleted
            if not where_condition or self.parser.evaluate_where(row, where_condition):
                success, msg = self._execute_triggers(table_name, "BEFORE", "DELETE", old_row=row)
                if not success:
                    return False, msg
            
        # Perform DELETE
        self._ensure_transaction_backup(table_name)

        # Rewrite files if any deletions were made
        if deleted_count > 0:
            self.storage_manager.rewrite_rows(current_db, table_name, rows_to_keep, schema["columns"])
            # Full rewrite of column files
            for col in schema["columns"]:
                col_name = col["name"]
                col_values = [row.get(col_name) for row in rows_to_keep]
                self.storage_manager.rewrite_column(current_db, table_name, col_name, col_values)
            
        # Fire AFTER DELETE triggers
        # (This is a simplified approach; ideally we fire for each row deleted)
        if deleted_count > 0:
            success, msg = self._execute_triggers(table_name, "AFTER", "DELETE")
            if not success:
                return False, msg
            
        return True, f"Deleted {deleted_count} rows from '{table_name}'"
    
    def execute_update(self, query):
        """Execute UPDATE with proper WHERE handling"""
        current_db = self.schema_manager.get_current_db()
        if not current_db:
            return False, "No database selected"
        
        table_name, set_column, set_value, where_condition = self.parser.parse_update(query)
        
        print(f"DEBUG: table={table_name}, column={set_column}, value={set_value}, where={where_condition}")
        
        if not table_name:
            return False, "Invalid UPDATE syntax. Use: UPDATE table SET column = value WHERE condition;"
        
        schema = self.schema_manager.get_table_schema(table_name)
        if not schema:
            return False, f"Table '{table_name}' not found"
        
        # Check if column exists
        col_exists = False
        target_col_schema = None
        for col in schema["columns"]:
            if col["name"] == set_column:
                col_exists = True
                target_col_schema = col
                break
        
        if not col_exists:
            return False, f"Column '{set_column}' not found in table '{table_name}'"
        
        # Load all rows
        rows = self.storage_manager.load_rows(current_db, table_name)
        
        if not rows:
            return True, f"No rows to update in '{table_name}'"
        
        # Validate type for update value
        if set_value is not None:
            if target_col_schema["type"] == "INT":
                if not isinstance(set_value, int) or isinstance(set_value, bool):
                    return False, f"Type mismatch: column '{set_column}' expects INT, got {type(set_value).__name__}"
            elif target_col_schema["type"] in ("FLOAT", "REAL"):
                if not isinstance(set_value, (int, float)) or isinstance(set_value, bool):
                    return False, f"Type mismatch: column '{set_column}' expects FLOAT/REAL, got {type(set_value).__name__}"

        # Validate DEFAULT and NOT NULL for update value
        if set_value == "" or set_value is None:
            if target_col_schema.get("default") is not None:
                set_value = target_col_schema["default"]
            elif target_col_schema.get("not_null"):
                return False, f"NOT NULL constraint violated: column '{set_column}' cannot be empty/null"

        # Validate UNIQUE for update value
        is_unique = target_col_schema.get("unique") or set_column in schema.get("primary_key", [])
        if is_unique and set_value is not None and set_value != "":
            # We must check against all OTHER rows not being updated to this value, 
            # or just simply check if any row already has this value (which isn't the current row being updated to the same value).
            # The safest approach for UNIQUE update is checking if ANY row that IS NOT the current one has it.
            # But we evaluate WHERE later. For now, if updating to a unique value, check if it's already there in ANY row that won't be updated.
            # Actually, if we update MULTIPLE rows to the same value and it's UNIQUE, it'll fail. 
            pass  # We will do UNIQUE check during the row update loop instead.

        # Evaluate FOREIGN KEY constraints for updated column
        foreign_keys = schema.get("foreign_keys", [])
        for fk in foreign_keys:
            if fk["column"] == set_column and set_value is not None and set_value != "":
                ref_table = fk["ref_table"]
                ref_col = fk["ref_column"]
                ref_rows = self.storage_manager.load_rows(current_db, ref_table)
                if ref_rows is None:
                    return False, f"Foreign key constraint violated: referenced table '{ref_table}' does not exist"
                exists = any(r.get(ref_col) == set_value for r in ref_rows)
                if not exists:
                    return False, f"Foreign key constraint violated: value '{set_value}' not found in {ref_table}({ref_col})"

        # Evaluate CHECK and UNIQUE constraints on simulated updates
        checks = schema.get("checks", [])
        new_values = [] # To track uniqueness within updated set
        for row in rows:
            should_update = False
            if where_condition:
                if self.parser.evaluate_where(row, where_condition):
                    should_update = True
            else:
                should_update = True
            
            if should_update:
                test_row = row.copy()
                test_row[set_column] = set_value
                for check in checks:
                    if not self.parser.evaluate_where(test_row, check):
                        return False, f"Check constraint violated: {check}"
                
                if is_unique and set_value is not None and set_value != "":
                    # Check if already exists in other rows that are not being updated, or within new updates
                    if set_value in new_values:
                        return False, f"UNIQUE constraint violated: multiple rows updated to '{set_value}' in column '{set_column}'"
                    for r in rows:
                        if not (where_condition and self.parser.evaluate_where(r, where_condition)) and not (not where_condition):
                            # This row `r` is NOT being updated
                            if r.get(set_column) == set_value:
                                return False, f"UNIQUE constraint violated: value '{set_value}' already exists in column '{set_column}'"
                    new_values.append(set_value)

        # Fire BEFORE UPDATE triggers
        for row in rows:
            if not where_condition or self.parser.evaluate_where(row, where_condition):
                new_row = row.copy()
                new_row[set_column] = set_value
                success, msg = self._execute_triggers(table_name, "BEFORE", "UPDATE", new_row=new_row, old_row=row)
                if not success:
                    return False, msg

        # Perform UPDATE
        self._ensure_transaction_backup(table_name)
            
        # Update matching rows
        updated_count = 0
        for row in rows:
            should_update = False
            
            if where_condition:
                # Check if this row matches WHERE condition
                if self.parser.evaluate_where(row, where_condition):
                    should_update = True
            else:
                # No WHERE clause - update ALL rows
                should_update = True
            
            if should_update:
                row[set_column] = set_value
                updated_count += 1
        
        # Rewrite files if any updates were made
        # Rewrite files if any updates were made
        if updated_count > 0:
            self.storage_manager.rewrite_rows(current_db, table_name, rows, schema["columns"])
            # Full rewrite of column files
            for col in schema["columns"]:
                col_name = col["name"]
                col_values = [row.get(col_name) for row in rows]
                self.storage_manager.rewrite_column(current_db, table_name, col_name, col_values)
            
            # Fire AFTER UPDATE triggers
            # (Simplified: we do not pass individual old/new rows for AFTER triggers here)
            success, msg = self._execute_triggers(table_name, "AFTER", "UPDATE")
            if not success:
                return False, msg
                
            return True, f"Updated {updated_count} rows in '{table_name}'"
        else:
            return True, f"No rows matched the condition. Updated 0 row(s) in '{table_name}'"
    
    def execute_select(self, query):
        """Execute SELECT query"""
        parsed = self.parser.parse_select(query)
        
        if not parsed:
            return None, False, "Invalid SELECT syntax"
        
        current_db = self.schema_manager.get_current_db()
        if not current_db:
            return None, False, "No database selected"
        
        # Handle JOIN queries
        if parsed["type"] == "join":
            result, success, err = self._execute_join(parsed, current_db)
        # Handle aggregation queries
        elif parsed["type"] == "aggregation":
            # Validate: HAVING requires GROUP BY
            if parsed.get("having") and not parsed.get("group_by"):
                return None, False, "HAVING clause requires GROUP BY"
            result, success, err = self._execute_aggregation(parsed, current_db)
        # Handle simple SELECT
        else:
            table_name = parsed["table_name"]
            select_col = parsed["select_col"]
            where_condition = parsed["where"]
            is_distinct = parsed["distinct"]
            
            rows, schema, err = self._get_table_rows_or_view(table_name, current_db)
            if err:
                return None, False, err
            
            # Apply WHERE filter
            if where_condition:
                rows = [row for row in rows if self.parser.evaluate_where(row, where_condition)]
            
            # Extract columns — handles "*", single column string, or list of columns
            if select_col == "*":
                result = rows
            elif isinstance(select_col, list):
                # Multi-column: project only requested columns as dicts
                result = [{col: row.get(col) for col in select_col} for row in rows]
            else:
                # Single column: return plain list of values
                result = [row.get(select_col) for row in rows]
            
            # Apply DISTINCT
            if is_distinct and result:
                if isinstance(result[0], dict):
                    unique = []
                    seen = set()
                    for row in result:
                        row_tuple = tuple(sorted(row.items()))
                        if row_tuple not in seen:
                            seen.add(row_tuple)
                            unique.append(row)
                    result = unique
                else:
                    result = list(dict.fromkeys(result))
            
            success, err = True, None

        if not success:
            return result, success, err

        # Apply ORDER BY
        if parsed.get("order_by") and isinstance(result, list) and result:
            order_by = parsed["order_by"]
            order_desc = parsed.get("order_desc", False)
            if isinstance(result[0], dict):
                def get_sort_val(x):
                    v = x.get(order_by)
                    return v if v is not None else ""
                try:
                    result.sort(key=get_sort_val, reverse=order_desc)
                except TypeError:
                    result.sort(key=lambda x: str(get_sort_val(x)), reverse=order_desc)
            else:
                try:
                    result.sort(reverse=order_desc)
                except TypeError:
                    result.sort(key=str, reverse=order_desc)

        # Apply LIMIT
        if parsed.get("limit") is not None and isinstance(result, list):
            result = result[:parsed["limit"]]

        return result, True, None
    
    def _get_table_rows_or_view(self, table_name, current_db):
        """Helper to get rows and schema for a table or evaluate a view"""
        view_query = self.schema_manager.get_view(table_name)
        if view_query:
            rows, success, err = self.execute_select(view_query)
            if not success:
                return None, None, f"View execution failed: {err}"
            
            schema = {"columns": []}
            if rows and isinstance(rows[0], dict):
                for k in rows[0].keys():
                    schema["columns"].append({"name": k, "type": "ANY"})
            return rows, schema, None
        else:
            schema = self.schema_manager.get_table_schema(table_name)
            if not schema:
                return None, None, f"Table/View '{table_name}' not found"
            rows = self.storage_manager.load_rows(current_db, table_name)
            return rows, schema, None

    def _execute_join(self, parsed, current_db):
        """Execute JOIN query"""
        table1 = parsed["table1"]
        table2 = parsed["table2"]
        join_type = parsed["join_type"]
        on_condition = parsed["on_condition"]
        select_col = parsed["select_col"]
        where_condition = parsed["where"]
        is_distinct = parsed["distinct"]
        
        rows1, schema1, err1 = self._get_table_rows_or_view(table1, current_db)
        rows2, schema2, err2 = self._get_table_rows_or_view(table2, current_db)
        
        if err1: return None, False, err1
        if err2: return None, False, err2
        
        result = []
        left_col, right_col = on_condition["left"][1], on_condition["right"][1]
        
        for r1 in rows1:
            matched = False
            for r2 in rows2:
                if r1.get(left_col) == r2.get(right_col):
                    matched = True
                    merged = {}
                    for k, v in r1.items():
                        merged[f"{table1}.{k}"] = v
                    for k, v in r2.items():
                        merged[f"{table2}.{k}"] = v
                    
                    if where_condition is None or self.parser.evaluate_where(merged, where_condition):
                        result.append(merged)
            
            if join_type == "LEFT" and not matched:
                merged = {}
                for k, v in r1.items():
                    merged[f"{table1}.{k}"] = v
                for col in schema2["columns"]:
                    merged[f"{table2}.{col['name']}"] = None
                
                if where_condition is None or self.parser.evaluate_where(merged, where_condition):
                    result.append(merged)
        
        if is_distinct and result:
            unique = []
            seen = set()
            for row in result:
                row_tuple = tuple(sorted(row.items()))
                if row_tuple not in seen:
                    seen.add(row_tuple)
                    unique.append(row)
            result = unique
        
        if select_col != "*":
            new_result = []
            cols = select_col if isinstance(select_col, list) else [select_col]
            for row in result:
                new_row = {}
                for col in cols:
                    if col in row:
                        new_row[col] = row[col]
                    else:
                        # Try to match without table prefix
                        for k in row.keys():
                            if k.endswith(f".{col}"):
                                new_row[k] = row[k]
                                break
                new_result.append(new_row)
            result = new_result
        
        return result, True, None
    def benchmark_aggregation(self, parsed, current_db):
        """Run the same aggregation on both column store and row store, return timing comparison."""
        import time
        
        agg_func = parsed["agg_func"]
        agg_col = parsed["agg_col"]
        table_name = parsed["table_name"]
        where_condition = parsed.get("where")
        group_by = parsed.get("group_by")
        
        schema = self.schema_manager.get_table_schema(table_name)
        if not schema:
            return None
        
        num_columns = len(schema["columns"])
        all_rows = self.storage_manager.load_rows(current_db, table_name)
        num_rows = len(all_rows)
        
        # ── ROW STORE benchmark ──
        row_start = time.perf_counter()
        for _ in range(100):  # Run 100 iterations for more reliable timing
            rows = self.storage_manager.load_rows(current_db, table_name)
            if where_condition:
                filtered = [r for r in rows if self.parser.evaluate_where(r, where_condition)]
            else:
                filtered = rows
            
            if group_by:
                groups = {}
                for r in filtered:
                    g_val = r.get(group_by)
                    if g_val not in groups:
                        groups[g_val] = []
                    groups[g_val].append(r)
                for g_val, g_rows in groups.items():
                    if agg_col == "*":
                        _ = len(g_rows)
                    else:
                        vals = [float(r.get(agg_col, 0)) for r in g_rows if r.get(agg_col) is not None]
                        if agg_func == "COUNT": _ = len(vals)
                        elif agg_func == "SUM": _ = sum(vals)
                        elif agg_func == "AVG": _ = sum(vals) / len(vals) if vals else 0
                        elif agg_func == "MAX": _ = max(vals) if vals else None
                        elif agg_func == "MIN": _ = min(vals) if vals else None
            else:
                if agg_col == "*":
                    _ = len(filtered)
                else:
                    vals = [float(r.get(agg_col, 0)) for r in filtered if r.get(agg_col) is not None]
                    if agg_func == "COUNT": _ = len(vals)
                    elif agg_func == "SUM": _ = sum(vals)
                    elif agg_func == "AVG": _ = sum(vals) / len(vals) if vals else 0
                    elif agg_func == "MAX": _ = max(vals) if vals else None
                    elif agg_func == "MIN": _ = min(vals) if vals else None
        row_end = time.perf_counter()
        row_time_ms = ((row_end - row_start) / 100) * 1000  # Average per iteration in ms
        
        # ── COLUMN STORE benchmark ──
        col_start = time.perf_counter()
        for _ in range(100):
            if group_by or where_condition:
                # Column store can't handle WHERE/GROUP BY natively, still loads column
                if agg_col == "*":
                    first_col = schema["columns"][0]["name"]
                    raw = self.storage_manager.load_column(current_db, table_name, first_col)
                    _ = len(raw)
                else:
                    raw = self.storage_manager.load_column(current_db, table_name, agg_col)
                    vals = [float(v) for v in raw if v is not None]
                    if agg_func == "COUNT": _ = len(vals)
                    elif agg_func == "SUM": _ = sum(vals)
                    elif agg_func == "AVG": _ = sum(vals) / len(vals) if vals else 0
                    elif agg_func == "MAX": _ = max(vals) if vals else None
                    elif agg_func == "MIN": _ = min(vals) if vals else None
            else:
                if agg_col == "*":
                    first_col = schema["columns"][0]["name"]
                    raw = self.storage_manager.load_column(current_db, table_name, first_col)
                    _ = len(raw)
                else:
                    raw = self.storage_manager.load_column(current_db, table_name, agg_col)
                    vals = [float(v) for v in raw if v is not None]
                    if agg_func == "COUNT": _ = len(vals)
                    elif agg_func == "SUM": _ = sum(vals)
                    elif agg_func == "AVG": _ = sum(vals) / len(vals) if vals else 0
                    elif agg_func == "MAX": _ = max(vals) if vals else None
                    elif agg_func == "MIN": _ = min(vals) if vals else None
        col_end = time.perf_counter()
        col_time_ms = ((col_end - col_start) / 100) * 1000
        
        # Determine which was faster
        if col_time_ms < row_time_ms:
            speedup = row_time_ms / col_time_ms if col_time_ms > 0 else 1
            winner = "column"
        else:
            speedup = col_time_ms / row_time_ms if row_time_ms > 0 else 1
            winner = "row"
        
        # What the actual query used
        if group_by or where_condition:
            used_store = "row"
        else:
            used_store = "column"
        
        return {
            "row_time_ms": round(row_time_ms, 4),
            "col_time_ms": round(col_time_ms, 4),
            "winner": winner,
            "speedup": round(speedup, 2),
            "used_store": used_store,
            "agg_func": agg_func,
            "agg_col": agg_col,
            "table_name": table_name,
            "num_rows": num_rows,
            "num_columns": num_columns,
            "columns_loaded_row": num_columns,
            "columns_loaded_col": 1,
            "has_where": where_condition is not None,
            "has_group_by": group_by is not None,
        }

    def _execute_aggregation(self, parsed, current_db):
        """Execute aggregation query — uses column store (no WHERE) or row store (with WHERE/GROUP BY)"""
        agg_func = parsed["agg_func"]
        agg_col = parsed["agg_col"]
        table_name = parsed["table_name"]
        where_condition = parsed.get("where")  # None if no WHERE clause
        group_by = parsed.get("group_by")
        
        schema = self.schema_manager.get_table_schema(table_name)
        if not schema:
            return None, False, f"Table '{table_name}' not found"
            
        if group_by:
            # ── GROUP BY present: must use row store ──
            print(f"\n[INFO] Using ROW STORE for {agg_func}({agg_col}) GROUP BY {group_by}")
            all_rows = self.storage_manager.load_rows(current_db, table_name)
            if where_condition:
                filtered = [r for r in all_rows if self.parser.evaluate_where(r, where_condition)]
            else:
                filtered = all_rows
            
            groups = {}
            for r in filtered:
                g_val = r.get(group_by)
                if g_val not in groups:
                    groups[g_val] = []
                groups[g_val].append(r)
            
            result = []
            for g_val, g_rows in groups.items():
                if agg_col == "*":
                    agg_val = len(g_rows)
                else:
                    values = [r.get(agg_col) for r in g_rows if r.get(agg_col) is not None]
                    numeric_values = []
                    for v in values:
                        try:
                            numeric_values.append(float(v))
                        except (ValueError, TypeError):
                            numeric_values.append(0)
                    
                    if agg_func == "COUNT": agg_val = len(values)
                    elif agg_func == "SUM": agg_val = sum(numeric_values)
                    elif agg_func == "AVG": agg_val = sum(numeric_values) / len(numeric_values) if numeric_values else 0
                    elif agg_func == "MAX": agg_val = max(numeric_values) if numeric_values else None
                    elif agg_func == "MIN": agg_val = min(numeric_values) if numeric_values else None
                    else: return None, False, f"Unknown aggregation: {agg_func}"
                
                row_res = {}
                proj_col = parsed.get("group_select_col")
                if proj_col:
                    row_res[proj_col] = g_val
                else:
                    row_res[group_by] = g_val
                    
                row_res[f"{agg_func}({agg_col})"] = agg_val
                result.append(row_res)

            # ── Apply HAVING filter ──
            having_condition = parsed.get("having")
            if having_condition:
                result = [row for row in result if self.parser.evaluate_having(row, having_condition)]
                
            return result, True, None
        
        elif where_condition:
            # ── WHERE present: must filter rows first, then extract column values ──
            print(f"\n[INFO] Using ROW STORE for {agg_func}({agg_col}) [WHERE filter active]")
            all_rows = self.storage_manager.load_rows(current_db, table_name)
            filtered = [r for r in all_rows if self.parser.evaluate_where(r, where_condition)]
            
            # COUNT(*) just counts filtered rows
            if agg_col == "*":
                return len(filtered), True, None
            
            # Extract the target column from filtered rows
            values = [r.get(agg_col) for r in filtered if r.get(agg_col) is not None]
        else:
            # ── No WHERE: use fast column store path ──
            print(f"\n[INFO] Using COLUMN STORE for {agg_func}({agg_col})")
            print(f"   [INFO] I/O Saved: Only loaded 1 column instead of {len(schema['columns'])} columns")
            
            if agg_col == "*":
                first_col = schema["columns"][0]["name"]
                raw = self.storage_manager.load_column(current_db, table_name, first_col)
                return len(raw), True, None
            
            values = self.storage_manager.load_column(current_db, table_name, agg_col)
        
        # ── Empty result handling ──
        if not values:
            return 0 if agg_func == "COUNT" else None, True, None
        
        # ── Convert to numbers for numeric operations ──
        numeric_values = []
        for v in values:
            try:
                numeric_values.append(float(v))
            except (ValueError, TypeError):
                numeric_values.append(0)
        
        if agg_func == "COUNT":
            result = len(values)
        elif agg_func == "SUM":
            result = sum(numeric_values)
        elif agg_func == "AVG":
            result = sum(numeric_values) / len(numeric_values) if numeric_values else 0
        elif agg_func == "MAX":
            result = max(numeric_values) if numeric_values else None
        elif agg_func == "MIN":
            result = min(numeric_values) if numeric_values else None
        else:
            return None, False, f"Unknown aggregation: {agg_func}"
        
        return result, True, None
    # ========== DROP METHODS ==========
    def execute_drop_table(self, query):
        """Execute DROP TABLE"""
        current_db = self.schema_manager.get_current_db()
        if not current_db:
            return False, "No database selected"

        table_name = self.parser.parse_drop_table(query)

        if not table_name:
            return False, "Invalid DROP TABLE syntax. Use: DROP TABLE table_name;"

        # Check if table exists
        schema = self.schema_manager.get_table_schema(table_name)
        if not schema:
            return False, f"Table '{table_name}' not found in database '{current_db}'"

        # Check for foreign key dependencies (tables that reference this table)
        referencing = self.schema_manager.get_referencing_tables(table_name)
        if referencing:
            ref_list = ", ".join([f"'{r[0]}'" for r in referencing])
            return False, f"Cannot drop table '{table_name}' because it is referenced by: {ref_list}. Drop those tables first or remove foreign key constraints."

        # Backup table before dropping if in transaction
        self._ensure_transaction_backup(table_name)
        
        # Delete table directory and files
        import shutil
        table_dir = os.path.join(self.data_dir, current_db, table_name)

        if os.path.exists(table_dir):
            shutil.rmtree(table_dir)

        # Remove from metadata
        self.schema_manager.metadata.remove_table(table_name)

        # Remove from memory
        if table_name in self.schema_manager.tables:
            del self.schema_manager.tables[table_name]

        return True, f"Table '{table_name}' dropped successfully"

    def execute_drop_database(self, query):
        """Execute DROP DATABASE"""
        import shutil

        db_name = self.parser.parse_drop_database(query)

        if not db_name:
            return False, "Invalid DROP DATABASE syntax. Use: DROP DATABASE db_name;"

        db_path = os.path.join(self.data_dir, db_name)

        if not os.path.exists(db_path):
            return False, f"Database '{db_name}' not found"

        # Check if trying to drop current database
        current_db = self.schema_manager.get_current_db()
        is_current = (current_db == db_name)

        # Delete database directory
        shutil.rmtree(db_path)

        # If current database was dropped, clear current_db
        if is_current:
            current_db_file = os.path.join(self.data_dir, "current_db.txt")
            if os.path.exists(current_db_file):
                os.remove(current_db_file)
            self.schema_manager.current_db = None
            self.schema_manager.metadata = None
            self.schema_manager.tables = {}
            print(f"\n⚠️ You dropped the current database '{db_name}'")
            print("   Please use 'CREATE DATABASE' or 'USE DATABASE' to select a database")

        return True, f"Database '{db_name}' dropped successfully"
    
    def execute_drop_view(self, view_name):
        """Execute DROP VIEW"""
        current_db = self.schema_manager.get_current_db()
        if not current_db:
            return False, "No database selected"

        if not self.schema_manager.metadata:
            return False, "No database selected"

        views = self.schema_manager.metadata.get_views()
        if view_name not in views:
            return False, f"View '{view_name}' not found"

        self.schema_manager.metadata.remove_view(view_name)
        return True, f"View '{view_name}' dropped successfully"

    def execute_drop_trigger(self, trigger_name):
        """Execute DROP TRIGGER"""
        current_db = self.schema_manager.get_current_db()
        if not current_db:
            return False, "No database selected"

        if not self.schema_manager.metadata:
            return False, "No database selected"

        triggers = self.schema_manager.metadata.get_all_triggers()
        trigger_names = [t["name"] for t in triggers]

        if trigger_name not in trigger_names:
            return False, f"Trigger '{trigger_name}' not found"

        self.schema_manager.metadata.remove_trigger(trigger_name)
        return True, f"Trigger '{trigger_name}' dropped successfully"