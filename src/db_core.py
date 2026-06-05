from .schema_manager import SchemaManager
from .storage_manager import StorageManager
from .query_parser import QueryParser

class DBCore:
    def __init__(self, data_dir="data"):
        self.data_dir = data_dir
        self.schema_manager = SchemaManager(data_dir)
        self.storage_manager = StorageManager(data_dir)
        self.parser = QueryParser()
    
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
    
    # ========== TABLE METHODS ==========
    def execute_create_table(self, query):
        """Execute CREATE TABLE"""
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
                return False, f"Expected {expected_count - 1} values (excluding AUTOINCREMENT column '{autoincrement_col}'), got {len(values)}"
            elif len(values) != expected_count - 1:
                return False, f"Expected {expected_count - 1} values (excluding AUTOINCREMENT column '{autoincrement_col}'), got {len(values)}"
            
            # Load existing rows for autoincrement calculation
            rows = self.storage_manager.load_rows(current_db, table_name)
            
            if not rows:
                next_id = 1
            else:
                existing_ids = [r.get(autoincrement_col) for r in rows if r.get(autoincrement_col) is not None]
                next_id = max(existing_ids) + 1 if existing_ids else 1
                
            # Insert the next_id into the values list at the correct index
            values.insert(autoincrement_idx, next_id)
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

        self.storage_manager.insert_row(current_db, table_name, values)
        
        for i, col in enumerate(schema["columns"]):
            self.storage_manager.insert_into_column_store(
                current_db, table_name, col["name"], values[i]
            )
        
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
        
        # Rewrite the file if any rows were deleted
        if deleted_count > 0:
            self.storage_manager.rewrite_rows(current_db, table_name, rows_to_keep, schema["columns"])
            # Also update column store
            for col in schema["columns"]:
                col_values = [str(row[col["name"]]) for row in rows_to_keep]
                self.storage_manager.rewrite_column(current_db, table_name, col["name"], col_values)
            
            return True, f"Deleted {deleted_count} row(s) from '{table_name}'"
        else:
            return True, f"No rows matched the condition. Deleted 0 row(s) from '{table_name}'"
    
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
        if updated_count > 0:
            self.storage_manager.rewrite_rows(current_db, table_name, rows, schema["columns"])
            # Also update column store
            for col in schema["columns"]:
                col_values = [str(row[col["name"]]) for row in rows]
                self.storage_manager.rewrite_column(current_db, table_name, col["name"], col_values)
            
            return True, f"Updated {updated_count} row(s) in '{table_name}'"
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
            
            schema = self.schema_manager.get_table_schema(table_name)
            if not schema:
                return None, False, f"Table '{table_name}' not found"
            
            # Load rows
            rows = self.storage_manager.load_rows(current_db, table_name)
            
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
    
    def _execute_join(self, parsed, current_db):
        """Execute JOIN query"""
        table1 = parsed["table1"]
        table2 = parsed["table2"]
        join_type = parsed["join_type"]
        on_condition = parsed["on_condition"]
        select_col = parsed["select_col"]
        where_condition = parsed["where"]
        is_distinct = parsed["distinct"]
        
        schema1 = self.schema_manager.get_table_schema(table1)
        schema2 = self.schema_manager.get_table_schema(table2)
        
        if not schema1 or not schema2:
            return None, False, f"Table not found"
        
        rows1 = self.storage_manager.load_rows(current_db, table1)
        rows2 = self.storage_manager.load_rows(current_db, table2)
        
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
            if select_col in [col["name"] for col in schema1["columns"]]:
                result = [row.get(f"{table1}.{select_col}") for row in result]
            else:
                result = [row.get(f"{table2}.{select_col}") for row in result]
        
        return result, True, None
    
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