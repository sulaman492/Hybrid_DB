import os
import datetime

class StorageManager:
    def __init__(self, data_dir="data"):
        self.data_dir = data_dir
        self.schema_manager = "schema_manager "     # Will be set by SchemaManager
    
    def set_schema_manager(self, schema_manager):
        """Set reference to SchemaManager for constraint validation"""
        self.schema_manager = schema_manager
    
    def insert_row(self, db_name, table_name, values, columns=None):
        """
        Insert a row into row_store.txt with proper validation.
        Allows partial column specification (missing columns get NULL or DEFAULT).
        """
        if not self.schema_manager:
            raise Exception("StorageManager not linked to SchemaManager")
        
        # Get table schema
        table_key = table_name.lower()
        if table_key not in self.schema_manager.tables:
            return False, f"Table '{table_name}' does not exist"
        
        schema = self.schema_manager.tables[table_key]
        expected_columns = [col["name"] for col in schema["columns"]]
        constraints = schema.get("constraints", {})
        
        # Build complete row data
        row_data = {}
        
        # Case 1: No columns specified - assume values are for ALL columns in order
        if columns is None:
            if len(values) != len(expected_columns):
                # Check if values are for non-auto-increment columns only
                non_auto_cols = [col for col in expected_columns 
                                if not constraints.get(col, {}).get("auto_increment", False)]
                
                if len(values) == len(non_auto_cols):
                    # Values provided for non-auto columns only
                    value_idx = 0
                    for col_name in expected_columns:
                        col_constraints = constraints.get(col_name, {})
                        if col_constraints.get("auto_increment", False):
                            row_data[col_name] = "AUTO_INCREMENT"
                        else:
                            row_data[col_name] = values[value_idx]
                            value_idx += 1
                else:
                    auto_cols = [col for col in expected_columns 
                                if constraints.get(col, {}).get("auto_increment", False)]
                    if auto_cols:
                        return False, f"Expected {len(non_auto_cols)} values (excluding AUTO_INCREMENT columns: {auto_cols}), got {len(values)}"
                    else:
                        return False, f"Expected {len(expected_columns)} values, got {len(values)}"
        else:
            # Case 2: Columns specified - match values to named columns
            if len(values) != len(columns):
                return False, f"Expected {len(columns)} values for specified columns, got {len(values)}"
            
            # Initialize all columns with NULL
            for col_name in expected_columns:
                row_data[col_name] = None
            
            # Fill in provided values
            for col_name, value in zip(columns, values):
                if col_name not in expected_columns:
                    return False, f"Column '{col_name}' does not exist in table '{table_name}'"
                row_data[col_name] = value
            
            # Apply DEFAULT values for columns that weren't provided
            for col_name in expected_columns:
                if row_data[col_name] is None:
                    col_constraints = constraints.get(col_name, {})
                    if "default" in col_constraints and col_constraints["default"] is not None:
                        row_data[col_name] = self._get_default_value(col_constraints["default"])
        
        # ========== VALIDATION PHASE ==========
        
        # 1. Check NOT NULL constraints
        for col_name, value in row_data.items():
            col_constraints = constraints.get(col_name, {})
            if col_constraints.get("not_null", False) and (value is None or value == "AUTO_INCREMENT"):
                return False, f"NOT NULL constraint violated: Column '{col_name}' cannot be NULL"
        
        # 2. Validate data types and convert
        converted_data = {}
        for col in schema["columns"]:
            col_name = col["name"]
            value = row_data.get(col_name)
            
            if value == "AUTO_INCREMENT":
                # Handle auto-increment after validation
                continue
            
            if value is not None:
                is_valid, converted_value = self._validate_type(value, col["type"], col_name)
                if not is_valid:
                    return False, converted_value
                converted_data[col_name] = converted_value
            else:
                converted_data[col_name] = None
        
        # Update row_data with converted values
        for col_name, converted_value in converted_data.items():
            row_data[col_name] = converted_value
        
        # 3. Check PRIMARY KEY uniqueness
        for pk in schema.get("primary_key", []):
            pk_value = row_data.get(pk)
            if pk_value is not None and pk_value != "AUTO_INCREMENT":
                if self._check_primary_key_exists(db_name, table_name, pk, pk_value):
                    return False, f"Duplicate primary key value '{pk_value}' for column '{pk}'"
        
        # 4. Check UNIQUE constraints
        for col_name, value in row_data.items():
            if value is not None and value != "AUTO_INCREMENT":
                col_constraints = constraints.get(col_name, {})
                if col_constraints.get("unique", False) or col_name in schema.get("unique_constraints", {}):
                    if self._check_unique_constraint(db_name, table_name, col_name, value):
                        return False, f"UNIQUE constraint violated: Value '{value}' already exists in column '{col_name}'"
        
        # 5. Check FOREIGN KEY constraints
        for fk in schema.get("foreign_keys", []):
            fk_column = fk["column"]
            fk_value = row_data.get(fk_column)
            if fk_value is not None and fk_value != "AUTO_INCREMENT":
                is_valid, error_msg = self._check_foreign_key_constraint(db_name, fk, fk_value)
                if not is_valid:
                    return False, error_msg
        
        # 6. Check CHECK constraints
        for col_name, value in row_data.items():
            if value is not None and value != "AUTO_INCREMENT":
                col_constraints = constraints.get(col_name, {})
                check_expr = col_constraints.get("check")
                if check_expr and not self._check_constraint(value, check_expr, col_name):
                    return False, f"CHECK constraint violated for column '{col_name}': {check_expr}"
        
        # ========== ALL VALIDATIONS PASSED - NOW STORE DATA ==========
        
        # Process AUTO_INCREMENT values
        for col in schema["columns"]:
            col_name = col["name"]
            if row_data.get(col_name) == "AUTO_INCREMENT":
                # Get next auto-increment value
                counter_key = f"{table_key}.{col_name}"
                next_val = self.schema_manager.auto_increment_counters.get(counter_key, 0) + 1
                row_data[col_name] = next_val
                self.schema_manager._save_auto_increment_counter(table_name, col_name, next_val)
        
        # Insert into row_store.txt
        table_dir = os.path.join(self.data_dir, db_name, table_name)
        row_file = os.path.join(table_dir, "row_store.txt")
        
        # Build row values in correct column order
        row_values = []
        for col in schema["columns"]:
            value = row_data[col["name"]]
            row_values.append(str(value) if value is not None else "")
        
        row_line = ",".join(row_values) + "\n"
        
        with open(row_file, "a") as f:
            f.write(row_line)
        
        # Insert into column store files
        for col in schema["columns"]:
            col_name = col["name"]
            value = row_data[col_name]
            self._insert_into_column_store(db_name, table_name, col_name, value)
        
        return True, f"Successfully inserted row"
    
    def _insert_into_column_store(self, db_name, table_name, column_name, value):
        """Insert value into column store"""
        col_file = os.path.join(self.data_dir, db_name, table_name, "col_store", f"{column_name}.txt")
        
        with open(col_file, "a") as f:
            f.write(str(value) if value is not None else "" + "\n")
        
        return True
    
    def _validate_type(self, value, col_type, col_name):
        """Validate and convert value to correct type"""
        if value is None:
            return True, None
        
        try:
            if col_type == "INT":
                if isinstance(value, bool):
                    return False, f"Column '{col_name}' is INT but received boolean"
                if isinstance(value, int):
                    return True, value
                if isinstance(value, float):
                    if value.is_integer():
                        return True, int(value)
                    return False, f"Column '{col_name}' is INT but received decimal {value}"
                if isinstance(value, str):
                    if value.lstrip('-').isdigit():
                        return True, int(value)
                    return False, f"Column '{col_name}' is INT but received '{value}'"
                return False, f"Column '{col_name}' is INT but received {type(value).__name__}"
            
            elif col_type == "DECIMAL":
                if isinstance(value, (int, float)):
                    return True, float(value)
                if isinstance(value, str):
                    try:
                        return True, float(value)
                    except ValueError:
                        return False, f"Column '{col_name}' is DECIMAL but received '{value}'"
                return False, f"Column '{col_name}' is DECIMAL but received {type(value).__name__}"
            
            elif col_type == "BOOLEAN":
                if isinstance(value, bool):
                    return True, value
                if isinstance(value, str):
                    if value.upper() in ['TRUE', 'YES', '1', 'T']:
                        return True, True
                    elif value.upper() in ['FALSE', 'NO', '0', 'F']:
                        return True, False
                if isinstance(value, (int, float)):
                    return True, bool(value)
                return False, f"Column '{col_name}' is BOOLEAN but received '{value}'"
            
            elif col_type in ["VARCHAR", "TEXT"]:
                return True, str(value)
            
            elif col_type == "DATE":
                if isinstance(value, str):
                    try:
                        datetime.date.fromisoformat(value)
                        return True, value
                    except ValueError:
                        return False, f"Column '{col_name}' is DATE but '{value}' is not valid (use YYYY-MM-DD)"
                return False, f"Column '{col_name}' is DATE but received {type(value).__name__}"
            
            elif col_type == "TIME":
                if isinstance(value, str):
                    try:
                        datetime.datetime.strptime(value, "%H:%M:%S")
                        return True, value
                    except ValueError:
                        return False, f"Column '{col_name}' is TIME but '{value}' is not valid (use HH:MM:SS)"
                return False, f"Column '{col_name}' is TIME but received {type(value).__name__}"
            
            elif col_type == "TIMESTAMP":
                if isinstance(value, str):
                    try:
                        datetime.datetime.fromisoformat(value.replace(' ', 'T'))
                        return True, value
                    except ValueError:
                        return False, f"Column '{col_name}' is TIMESTAMP but '{value}' is not valid"
                return False, f"Column '{col_name}' is TIMESTAMP but received {type(value).__name__}"
            
            else:
                return True, value
                
        except Exception as e:
            return False, f"Error validating column '{col_name}': {str(e)}"
    
    def _get_default_value(self, default_val):
        """Get the actual value for a DEFAULT constraint"""
        if default_val == "CURRENT_DATE":
            return datetime.date.today().isoformat()
        elif default_val == "CURRENT_TIME":
            return datetime.datetime.now().time().isoformat()
        elif default_val == "CURRENT_TIMESTAMP":
            return datetime.datetime.now().isoformat()
        else:
            return default_val
    
    def _check_primary_key_exists(self, db_name, table_name, pk_column, pk_value):
        """Check if primary key value already exists"""
        col_file = os.path.join(self.data_dir, db_name, table_name, "col_store", f"{pk_column}.txt")
        
        if not os.path.exists(col_file):
            return False
        
        with open(col_file, 'r') as f:
            next(f)  # Skip header
            for line in f:
                line = line.strip()
                if line and str(line) == str(pk_value):
                    return True
        
        return False
    
    def _check_unique_constraint(self, db_name, table_name, col_name, value):
        """Check if value violates unique constraint"""
        col_file = os.path.join(self.data_dir, db_name, table_name, "col_store", f"{col_name}.txt")
        
        if not os.path.exists(col_file):
            return False
        
        with open(col_file, 'r') as f:
            next(f)  # Skip header
            for line in f:
                line = line.strip()
                if line and str(line) == str(value):
                    return True
        
        return False
    
    def _check_foreign_key_constraint(self, db_name, fk_info, fk_value):
        """Check if foreign key value exists in referenced table"""
        ref_table = fk_info["ref_table"]
        ref_column = fk_info["ref_column"]
        
        ref_table_lower = ref_table.lower()
        if ref_table_lower not in self.schema_manager.tables:
            return False, f"Referenced table '{ref_table}' does not exist"
        
        # Check if reference exists
        ref_dir = os.path.join(self.data_dir, db_name, self.schema_manager.tables[ref_table_lower]["original_name"])
        ref_col_file = os.path.join(ref_dir, "col_store", f"{ref_column}.txt")
        
        if not os.path.exists(ref_col_file):
            return False, f"Referenced column '{ref_column}' does not exist in table '{ref_table}'"
        
        with open(ref_col_file, 'r') as f:
            next(f)  # Skip header
            for line in f:
                line = line.strip()
                if line and str(line) == str(fk_value):
                    return True, None
        
        return False, f"Foreign key value '{fk_value}' not found in {ref_table}.{ref_column}"
    
    def _check_constraint(self, value, constraint_expr, col_name):
        """Check if value satisfies a CHECK constraint"""
        if not constraint_expr:
            return True
        
        # Simple constraint parsing
        expr = constraint_expr.lower().strip()
        
        for op in [">=", "<=", ">", "<", "="]:
            if op in expr:
                parts = expr.split(op, 1)
                if len(parts) == 2:
                    left = parts[0].strip()
                    right = parts[1].strip()
                    
                    if left != col_name.lower():
                        continue
                    
                    # Strip quotes
                    if right.startswith("'") and right.endswith("'"):
                        right = right[1:-1]
                    
                    try:
                        num_right = float(right)
                        num_value = float(value)
                        if op == ">=":
                            return num_value >= num_right
                        elif op == "<=":
                            return num_value <= num_right
                        elif op == ">":
                            return num_value > num_right
                        elif op == "<":
                            return num_value < num_right
                        elif op == "=":
                            return num_value == num_right
                    except (ValueError, TypeError):
                        if op == "=":
                            return str(value) == str(right)
                        return False
        
        return True
    
    def load_rows(self, db_name, table_name):
        """Load all rows from row_store.txt"""
        row_file = os.path.join(self.data_dir, db_name, table_name, "row_store.txt")
        
        if not os.path.exists(row_file):
            return []
        
        rows = []
        with open(row_file, "r") as f:
            lines = f.readlines()
            if not lines:
                return []
            
            headers = lines[0].strip().split(",")
            for line in lines[1:]:
                line = line.strip()
                if line:
                    values = line.split(",")
                    if values and values[0]:
                        row = {}
                        for i, header in enumerate(headers):
                            if i < len(values):
                                val = values[i]
                                # Don't aggressively convert - keep as string
                                row[header] = val if val else None
                            else:
                                row[header] = None
                        rows.append(row)
        
        return rows
    
    def load_column(self, db_name, table_name, column_name):
        """Load a single column from column store"""
        col_file = os.path.join(self.data_dir, db_name, table_name, "col_store", f"{column_name}.txt")
        
        if not os.path.exists(col_file):
            return []
        
        values = []
        with open(col_file, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    values.append(line)  # Keep as string, don't auto-convert
        
        return values
    
    def rewrite_rows(self, db_name, table_name, rows, columns):
        """Rewrite entire row_store.txt with new data"""
        table_dir = os.path.join(self.data_dir, db_name, table_name)
        row_file = os.path.join(table_dir, "row_store.txt")
        
        # Write header
        col_names = [col["name"] for col in columns]
        
        with open(row_file, "w") as f:
            f.write(",".join(col_names) + "\n")
            for row in rows:
                values = [str(row.get(col["name"], "")) for col in columns]
                f.write(",".join(values) + "\n")
        
        return True
    
    def rewrite_column(self, db_name, table_name, column_name, values):
        """Rewrite entire column store file"""
        col_file = os.path.join(self.data_dir, db_name, table_name, "col_store", f"{column_name}.txt")
        
        with open(col_file, "w") as f:
            f.write(f"# Column: {column_name}\n")
            for val in values:
                f.write(str(val) if val is not None else "" + "\n")
        
        return True