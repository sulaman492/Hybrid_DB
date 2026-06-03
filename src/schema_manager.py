import os
import re
import datetime
import shutil
from .metadata import MetadataManager

class SchemaManager:
    def __init__(self, data_dir="data"):
        self.data_dir = data_dir
        self.current_db = None
        self.metadata = None
        self.tables = {}
        self.auto_increment_counters = {}  # Track auto-increment values
        
        # Load current database if exists
        self._load_current_db()
    
    def _load_current_db(self):
        """Load the currently active database"""
        current_db_file = os.path.join(self.data_dir, "current_db.txt")
        if os.path.exists(current_db_file):
            with open(current_db_file, 'r') as f:
                self.current_db = f.read().strip()
                if self.current_db:
                    self.metadata = MetadataManager(os.path.join(self.data_dir, self.current_db))
                    self._load_all_schemas()
    
    def _load_all_schemas(self):
        """Load all existing table schemas from current database"""
        if not self.metadata:
            return
        
        for table_name in self.metadata.get_all_tables():
            self._load_table_schema(table_name)
            self._load_auto_increment_counter(table_name)
    
    def _load_table_schema(self, table_name):
        """Load schema for a specific table"""
        if not self.current_db:
            return
            
        schema_file = os.path.join(self.data_dir, self.current_db, table_name, "schema.txt")
        if os.path.exists(schema_file):
            with open(schema_file, 'r') as f:
                lines = f.readlines()
                columns = eval(lines[0].strip())
                pk = eval(lines[1].strip()) if len(lines) > 1 else []
                fk = eval(lines[2].strip()) if len(lines) > 2 else []
                constraints = eval(lines[3].strip()) if len(lines) > 3 else {}
                unique_constraints = eval(lines[4].strip()) if len(lines) > 4 else {}
                check_constraints = eval(lines[5].strip()) if len(lines) > 5 else {}
                
                self.tables[table_name.lower()] = {
                    "original_name": table_name,
                    "columns": columns,
                    "primary_key": pk,
                    "foreign_keys": fk,
                    "constraints": constraints,
                    "unique_constraints": unique_constraints,
                    "check_constraints": check_constraints
                }
    
    def _load_auto_increment_counter(self, table_name):
        """Load auto-increment counter for a table"""
        table_dir = os.path.join(self.data_dir, self.current_db, table_name)
        counter_file = os.path.join(table_dir, "auto_increment.txt")
        
        if os.path.exists(counter_file):
            with open(counter_file, 'r') as f:
                for line in f:
                    if ':' in line:
                        col_name, value = line.strip().split(':')
                        self.auto_increment_counters[f"{table_name.lower()}.{col_name}"] = int(value)
    
    def _save_auto_increment_counter(self, table_name, col_name, value):
        """Save auto-increment counter for a table"""
        table_dir = os.path.join(self.data_dir, self.current_db, table_name)
        counter_file = os.path.join(table_dir, "auto_increment.txt")
        
        key = f"{table_name.lower()}.{col_name}"
        self.auto_increment_counters[key] = value
        
        # Save all counters for this table
        counters_to_save = {}
        for k, v in self.auto_increment_counters.items():
            if k.startswith(f"{table_name.lower()}."):
                counters_to_save[k.split('.')[1]] = v
        
        with open(counter_file, 'w') as f:
            for col, val in counters_to_save.items():
                f.write(f"{col}:{val}\n")
    
    def parse_query(self, query):
        """
        Parse a multi-line query that ends with semicolon.
        Returns the parsed query without the semicolon.
        """
        # Remove leading/trailing whitespace
        query = query.strip()
        
        # Remove the trailing semicolon if present
        if query.endswith(';'):
            query = query[:-1].strip()
        
        return query
    
    def _normalize_name(self, name):
        """Convert name to lowercase for case-insensitive access"""
        return name.lower() if name else name
    
    # ========== DATABASE METHODS ==========
    def parse_create_database(self, query):
        """Parse CREATE DATABASE query"""
        query = self.parse_query(query)
        
        pattern = r"CREATE DATABASE (\w+)\s*$"
        match = re.match(pattern, query, re.IGNORECASE | re.MULTILINE | re.DOTALL)
        
        if not match:
            return False, "Invalid CREATE DATABASE syntax. Use: CREATE DATABASE db_name;"
        
        db_name = match.group(1)
        return self.create_database(db_name)
    
    def create_database(self, db_name):
        """Create a new database"""
        db_path = os.path.join(self.data_dir, db_name)
        
        if os.path.exists(db_path):
            return False, f"Database '{db_name}' already exists"
        
        # Create database directory structure
        os.makedirs(db_path, exist_ok=True)
        os.makedirs(os.path.join(db_path, "_metadata"), exist_ok=True)
        
        # Store current database in metadata
        current_db_file = os.path.join(self.data_dir, "current_db.txt")
        with open(current_db_file, "w") as f:
            f.write(db_name)
        
        self.current_db = db_name
        self.metadata = MetadataManager(os.path.join(self.data_dir, db_name))
        self.tables = {}
        
        print(f"\n✅ Database '{db_name}' created successfully!")
        print(f"   Location: {db_path}")
        print(f"   Now using database: {db_name}")
        
        return True, f"Database '{db_name}' created and activated"
    
    def parse_use_database(self, query):
        """Parse USE DATABASE query"""
        query = self.parse_query(query)
        
        pattern = r"USE DATABASE (\w+)\s*$"
        match = re.match(pattern, query, re.IGNORECASE | re.MULTILINE | re.DOTALL)
        
        if not match:
            return False, "Invalid USE DATABASE syntax. Use: USE DATABASE db_name;"
        
        db_name = match.group(1)
        return self.use_database(db_name)
    
    def use_database(self, db_name):
        """Switch to another database"""
        db_path = os.path.join(self.data_dir, db_name)
        
        if not os.path.exists(db_path):
            return False, f"Database '{db_name}' does not exist. Create it first with CREATE DATABASE {db_name};"
        
        # Update current database
        current_db_file = os.path.join(self.data_dir, "current_db.txt")
        with open(current_db_file, "w") as f:
            f.write(db_name)
        
        self.current_db = db_name
        self.metadata = MetadataManager(os.path.join(self.data_dir, db_name))
        self.tables = {}
        self._load_all_schemas()
        
        print(f"\n✅ Switched to database: {db_name}")
        return True, f"Now using database '{db_name}'"
    
    def parse_drop_database(self, query):
        """Parse DROP DATABASE query"""
        query = self.parse_query(query)
        
        pattern = r"DROP DATABASE (\w+)\s*$"
        match = re.match(pattern, query, re.IGNORECASE | re.MULTILINE | re.DOTALL)
        
        if not match:
            return False, "Invalid DROP DATABASE syntax. Use: DROP DATABASE db_name;"
        
        db_name = match.group(1)
        return self.drop_database(db_name)
    
    def drop_database(self, db_name):
        """Delete a database"""
        db_path = os.path.join(self.data_dir, db_name)
        
        if not os.path.exists(db_path):
            return False, f"Database '{db_name}' does not exist"
        
        # Confirm deletion
        confirm = input(f"⚠️  WARNING: This will permanently delete database '{db_name}' and all its tables!\nType 'YES' to confirm: ")
        
        if confirm != 'YES':
            return False, "Database deletion cancelled"
        
        # Remove database directory
        shutil.rmtree(db_path)
        
        # If current database was deleted, clear current_db
        if self.current_db == db_name:
            self.current_db = None
            self.metadata = None
            self.tables = {}
            current_db_file = os.path.join(self.data_dir, "current_db.txt")
            if os.path.exists(current_db_file):
                os.remove(current_db_file)
        
        print(f"\n✅ Database '{db_name}' deleted successfully!")
        return True, f"Database '{db_name}' deleted"
    
    def get_current_db(self):
        """Get current database name"""
        return self.current_db
    
    def list_databases(self):
        """List all databases"""
        databases = []
        if os.path.exists(self.data_dir):
            for item in os.listdir(self.data_dir):
                item_path = os.path.join(self.data_dir, item)
                if os.path.isdir(item_path) and item != "_metadata" and not item.startswith("."):
                    if os.path.exists(os.path.join(item_path, "_metadata")):
                        databases.append(item)
        return databases
    
    # ========== TABLE METHODS ==========
    def parse_create_table(self, query):
        """Parse CREATE TABLE query"""
        if not self.current_db:
            return False, "No database selected. Use: CREATE DATABASE db_name; or USE DATABASE db_name;"
        
        query = self.parse_query(query)
        
        pattern = r"CREATE TABLE (\w+)\s*\((.*)\)\s*$"
        match = re.match(pattern, query, re.IGNORECASE | re.MULTILINE | re.DOTALL)
        
        if not match:
            return False, "Invalid CREATE TABLE syntax. Use: CREATE TABLE table_name (col1 TYPE, col2 TYPE, ...);"
        
        table_name = match.group(1)
        columns_def = match.group(2)
        
        columns = []
        primary_keys = []
        foreign_keys = []
        constraints = {}
        unique_constraints = {}
        check_constraints = {}
        
        col_defs = self._split_column_defs(columns_def)
        
        for col_def in col_defs:
            col_def = col_def.strip()
            
            if not col_def:
                continue
            
            # Check for standalone PRIMARY KEY constraint
            if col_def.upper().startswith("PRIMARY KEY"):
                pk_match = re.search(r"PRIMARY KEY\s*\(([^)]+)\)", col_def, re.IGNORECASE)
                if pk_match:
                    pk_cols = [c.strip() for c in pk_match.group(1).split(',')]
                    primary_keys.extend(pk_cols)
                continue
            
            # Check for FOREIGN KEY constraint
            if col_def.upper().startswith("FOREIGN KEY"):
                fk_match = re.search(r"FOREIGN KEY\s*\((\w+)\)\s*REFERENCES\s*(\w+)\s*\((\w+)\)", col_def, re.IGNORECASE)
                if fk_match:
                    foreign_keys.append({
                        "column": fk_match.group(1),
                        "ref_table": fk_match.group(2),
                        "ref_column": fk_match.group(3)
                    })
                continue
            
            # Check for UNIQUE constraint
            if col_def.upper().startswith("UNIQUE"):
                unique_match = re.search(r"UNIQUE\s*\(([^)]+)\)", col_def, re.IGNORECASE)
                if unique_match:
                    unique_cols = [c.strip() for c in unique_match.group(1).split(',')]
                    for col in unique_cols:
                        unique_constraints[col] = True
                continue
            
            # Check for CHECK constraint
            if col_def.upper().startswith("CHECK"):
                check_match = re.search(r"CHECK\s*\((.+)\)", col_def, re.IGNORECASE)
                if check_match:
                    check_expr = check_match.group(1).strip()
                    check_constraints["_global_check"] = check_expr
                continue
            
            # Parse regular column
            col_parts = col_def.split()
            if len(col_parts) >= 2:
                col_name = col_parts[0]
                col_type = col_parts[1].upper()
                
                # Validate column type
                valid_types = ["INT", "DECIMAL", "VARCHAR", "TEXT", "DATE", "TIME", "TIMESTAMP", "BOOLEAN"]
                if col_type not in valid_types:
                    return False, f"Invalid data type '{col_type}' for column '{col_name}'. Valid types: {', '.join(valid_types)}"
                
                # Initialize constraints for this column
                constraints[col_name] = {
                    "not_null": False,
                    "auto_increment": False,
                    "default": None,
                    "unique": False,
                    "check": None
                }
                
                # Check for constraints
                remaining_parts = col_parts[2:]
                i = 0
                while i < len(remaining_parts):
                    part_upper = remaining_parts[i].upper()
                    
                    if part_upper == "NOT" and i+1 < len(remaining_parts) and remaining_parts[i+1].upper() == "NULL":
                        constraints[col_name]["not_null"] = True
                        i += 2
                    
                    elif part_upper == "AUTO_INCREMENT":
                        if col_type != "INT":
                            return False, f"AUTO_INCREMENT can only be used with INT columns, not {col_type}"
                        constraints[col_name]["auto_increment"] = True
                        constraints[col_name]["not_null"] = True
                        constraints[col_name]["unique"] = True
                        i += 1
                    
                    elif part_upper == "PRIMARY" and i+1 < len(remaining_parts) and remaining_parts[i+1].upper() == "KEY":
                        primary_keys.append(col_name)
                        constraints[col_name]["not_null"] = True
                        constraints[col_name]["unique"] = True
                        i += 2
                    
                    elif part_upper == "UNIQUE":
                        constraints[col_name]["unique"] = True
                        i += 1
                    
                    elif part_upper == "DEFAULT" and i+1 < len(remaining_parts):
                        default_value = remaining_parts[i+1].strip()
                        # Remove quotes if present
                        if default_value.startswith("'") and default_value.endswith("'"):
                            default_value = default_value[1:-1]
                        constraints[col_name]["default"] = default_value
                        i += 2
                    
                    elif part_upper.startswith("CHECK"):
                        # For column-level CHECK constraint — handles both
                        # "CHECK (expr)" (space-separated) and "CHECK(expr)" (no space)
                        remaining_str = ' '.join(remaining_parts[i:])
                        check_match = re.search(r"CHECK\s*\((.+?)\)\s*$", remaining_str, re.IGNORECASE)
                        if check_match:
                            constraints[col_name]["check"] = check_match.group(1).strip()
                        # skip all remaining tokens (they're part of the CHECK expr)
                        i = len(remaining_parts)
                    else:
                        i += 1
                
                # Validate AUTO_INCREMENT only for primary key
                if constraints[col_name]["auto_increment"] and col_name not in primary_keys:
                    return False, f"AUTO_INCREMENT column '{col_name}' must be a PRIMARY KEY"
                
                columns.append({
                    "name": col_name,
                    "type": col_type
                })
        
        if not columns:
            return False, "No valid columns defined"
        
        # Ensure each primary key column exists
        for pk in primary_keys:
            if pk not in [col["name"] for col in columns]:
                return False, f"Primary key column '{pk}' not defined"
        
        # Set auto_increment only for INT primary keys that haven't been explicitly configured
        for pk in primary_keys:
            pk_col = next((col for col in columns if col["name"] == pk), None)
            if pk_col and pk_col["type"] == "INT":
                if not constraints.get(pk, {}).get("auto_increment", False):
                    constraints.setdefault(pk, {})["auto_increment"] = True
            # Always ensure NOT NULL for any primary key type
            constraints.setdefault(pk, {})["not_null"] = True
        
        # Validate foreign key references exist at creation time
        for fk in foreign_keys:
            ref_table_lower = fk["ref_table"].lower()
            ref_col = fk["ref_column"]
            if ref_table_lower not in self.tables:
                return False, (
                    f"Cannot create table '{table_name}': FOREIGN KEY on column '{fk['column']}' "
                    f"references table '{fk['ref_table']}' which does not exist. "
                    f"Create '{fk['ref_table']}' first."
                )
            ref_schema = self.tables[ref_table_lower]
            ref_col_names = [col["name"] for col in ref_schema["columns"]]
            if ref_col not in ref_col_names:
                return False, (
                    f"Cannot create table '{table_name}': FOREIGN KEY on column '{fk['column']}' "
                    f"references '{fk['ref_table']}.{ref_col}' but that column does not exist."
                )
            # The referenced column should be a PRIMARY KEY or UNIQUE
            ref_constraints = ref_schema.get("constraints", {})
            is_pk = ref_col in ref_schema.get("primary_key", [])
            is_unique = ref_constraints.get(ref_col, {}).get("unique", False)
            if not is_pk and not is_unique:
                return False, (
                    f"Cannot create table '{table_name}': FOREIGN KEY on column '{fk['column']}' "
                    f"references '{fk['ref_table']}.{ref_col}', but that column is neither a PRIMARY KEY "
                    f"nor UNIQUE. Foreign keys must reference a unique column."
                )
        
        return self.create_table(table_name, columns, primary_keys, foreign_keys, constraints, unique_constraints, check_constraints)
    
    def _split_column_defs(self, columns_def):
        """Split column definitions handling parentheses and nested commas"""
        parts = []
        current = ""
        paren_count = 0
        in_quotes = False
        quote_char = None
        
        for char in columns_def:
            if char in ['"', "'"] and not in_quotes:
                in_quotes = True
                quote_char = char
                current += char
            elif char == quote_char and in_quotes:
                in_quotes = False
                quote_char = None
                current += char
            elif char == '(' and not in_quotes:
                paren_count += 1
                current += char
            elif char == ')' and not in_quotes:
                paren_count -= 1
                current += char
            elif char == ',' and paren_count == 0 and not in_quotes:
                parts.append(current.strip())
                current = ""
            else:
                current += char
        
        if current.strip():
            parts.append(current.strip())
        
        return parts
    
    def create_table(self, table_name, columns, primary_keys, foreign_keys, constraints, unique_constraints, check_constraints):
        """Create a new table in current database"""
        if not self.current_db:
            return False, "No database selected"
        
        # Check if table already exists (case-insensitive)
        if table_name.lower() in self.tables:
            return False, f"Table '{table_name}' already exists in database '{self.current_db}'"
        
        table_dir = os.path.join(self.data_dir, self.current_db, table_name)
        os.makedirs(table_dir, exist_ok=True)
        os.makedirs(os.path.join(table_dir, "col_store"), exist_ok=True)
        
        # Save schema
        with open(os.path.join(table_dir, "schema.txt"), "w") as f:
            f.write(str(columns) + "\n")
            f.write(str(primary_keys) + "\n")
            f.write(str(foreign_keys) + "\n")
            f.write(str(constraints) + "\n")
            f.write(str(unique_constraints) + "\n")
            f.write(str(check_constraints) + "\n")
        
        # Create row_store.txt with header
        col_names = [col["name"] for col in columns]
        with open(os.path.join(table_dir, "row_store.txt"), "w") as f:
            f.write(",".join(col_names) + "\n")
        
        # Create column store files
        for col in columns:
            col_file = os.path.join(table_dir, "col_store", f"{col['name']}.txt")
            with open(col_file, "w") as f:
                f.write(f"# Column: {col['name']} Type: {col['type']}\n")
        
        # Store in memory (case-insensitive)
        self.tables[table_name.lower()] = {
            "original_name": table_name,
            "columns": columns,
            "primary_key": primary_keys,
            "foreign_keys": foreign_keys,
            "constraints": constraints,
            "unique_constraints": unique_constraints,
            "check_constraints": check_constraints
        }
        
        # Initialize auto-increment counters
        for col in columns:
            if constraints.get(col["name"], {}).get("auto_increment", False):
                self._save_auto_increment_counter(table_name, col["name"], 0)
        
        # Update metadata
        if self.metadata:
            self.metadata.add_table(table_name)
        
        print(f"\n✅ Table '{table_name}' created successfully in database '{self.current_db}'!")
        print(f"   Columns: {[col['name'] for col in columns]}")
        if primary_keys:
            print(f"   Primary Key: {primary_keys}")
        if foreign_keys:
            print(f"   Foreign Keys: {[(fk['column'], fk['ref_table'], fk['ref_column']) for fk in foreign_keys]}")
        
        return True, f"Table '{table_name}' created"
    
    def parse_drop_table(self, query):
        """Parse DROP TABLE query"""
        if not self.current_db:
            return False, "No database selected"
        
        query = self.parse_query(query)
        
        pattern = r"DROP TABLE (\w+)\s*$"
        match = re.match(pattern, query, re.IGNORECASE | re.MULTILINE | re.DOTALL)
        
        if not match:
            return False, "Invalid DROP TABLE syntax. Use: DROP TABLE table_name;"
        
        table_name = match.group(1)
        return self.drop_table(table_name)
    
    def drop_table(self, table_name):
        """Delete a table"""
        table_key = table_name.lower()
        
        if table_key not in self.tables:
            return False, f"Table '{table_name}' does not exist"
        
        # Check if any other tables have foreign keys referencing this table
        for other_table_key, other_schema in self.tables.items():
            for fk in other_schema.get("foreign_keys", []):
                if fk["ref_table"].lower() == table_key:
                    return False, f"Cannot drop table '{table_name}' because it is referenced by foreign key in table '{other_schema['original_name']}'"
        
        # Confirm deletion
        confirm = input(f"⚠️  WARNING: This will permanently delete table '{table_name}' and all its data!\nType 'YES' to confirm: ")
        
        if confirm != 'YES':
            return False, "Table deletion cancelled"
        
        # Remove table directory
        original_name = self.tables[table_key]["original_name"]
        table_dir = os.path.join(self.data_dir, self.current_db, original_name)
        shutil.rmtree(table_dir)
        
        # Remove from metadata
        if self.metadata:
            self.metadata.remove_table(original_name)
        
        # Remove from memory
        del self.tables[table_key]
        
        # Remove auto-increment counters
        keys_to_remove = [k for k in self.auto_increment_counters.keys() if k.startswith(f"{table_key}.")]
        for key in keys_to_remove:
            del self.auto_increment_counters[key]
        
        print(f"\n✅ Table '{table_name}' deleted successfully!")
        return True, f"Table '{table_name}' deleted"
    
    # ========== INSERT METHODS ==========
    def parse_insert(self, query):
        """Parse INSERT INTO query"""
        if not self.current_db:
            return False, "No database selected. Use: CREATE DATABASE db_name; or USE DATABASE db_name;"
        
        query = self.parse_query(query)
        
        # Pattern for INSERT INTO table_name VALUES (...)
        pattern1 = r"INSERT INTO (\w+)\s*VALUES\s*\((.*)\)\s*$"
        match1 = re.match(pattern1, query, re.IGNORECASE | re.MULTILINE | re.DOTALL)
        
        # Pattern for INSERT INTO table_name (col1, col2) VALUES (...)
        pattern2 = r"INSERT INTO (\w+)\s*\((.*)\)\s*VALUES\s*\((.*)\)\s*$"
        match2 = re.match(pattern2, query, re.IGNORECASE | re.MULTILINE | re.DOTALL)
        
        if match1:
            table_name = match1.group(1)
            values_str = match1.group(2)
            values = self._parse_values(values_str)
            return self.insert_into_table(table_name, None, values)
        
        elif match2:
            table_name = match2.group(1)
            columns_str = match2.group(2)
            values_str = match2.group(3)
            
            columns = [col.strip() for col in columns_str.split(',')]
            values = self._parse_values(values_str)
            
            return self.insert_into_table(table_name, columns, values)
        
        else:
            return False, "Invalid INSERT syntax. Use: INSERT INTO table_name VALUES (val1, val2, ...); or INSERT INTO table_name (col1, col2) VALUES (val1, val2, ...);"
    
    def _parse_values(self, values_str):
        """Parse values from INSERT statement"""
        values = []
        current = ""
        in_quotes = False
        quote_char = None
        
        for char in values_str:
            if char in ['"', "'"] and not in_quotes:
                in_quotes = True
                quote_char = char
                current += char
            elif char == quote_char and in_quotes:
                in_quotes = False
                quote_char = None
                current += char
            elif char == ',' and not in_quotes:
                value = current.strip()
                values.append(self._convert_value(value))
                current = ""
            else:
                current += char
        
        if current.strip():
            values.append(self._convert_value(current.strip()))
        
        return values
    
    def _convert_value(self, value_str):
        """Convert string value to appropriate Python type"""
        value_str = value_str.strip()
        
        if value_str.upper() == 'NULL':
            return None
        
        # Handle quoted strings
        if (value_str.startswith("'") and value_str.endswith("'")) or \
           (value_str.startswith('"') and value_str.endswith('"')):
            return value_str[1:-1]
        
        # Handle special date/time values
        if value_str.upper() == 'CURRENT_DATE':
            return datetime.date.today().isoformat()
        
        if value_str.upper() == 'CURRENT_TIME':
            return datetime.datetime.now().time().isoformat()
        
        if value_str.upper() == 'CURRENT_TIMESTAMP':
            return datetime.datetime.now().isoformat()
        
        if value_str.upper() == 'TRUE':
            return True
        
        if value_str.upper() == 'FALSE':
            return False
        
        # Try to convert to int
        try:
            return int(value_str)
        except ValueError:
            pass
        
        # Try to convert to float
        try:
            return float(value_str)
        except ValueError:
            pass
        
        return value_str
    
    def _validate_type(self, value, col_type, col_name):
        """Strictly validate value against column type with descriptive error messages"""
        if value is None:
            return True, None

        try:
            if col_type == "INT":
                if isinstance(value, bool):
                    return False, (
                        f"Type mismatch: column '{col_name}' is INT but received a BOOLEAN value '{value}'. "
                        f"Use an integer number instead."
                    )
                if isinstance(value, int):
                    return True, value
                if isinstance(value, float):
                    if value.is_integer():
                        return True, int(value)
                    return False, (
                        f"Type mismatch: column '{col_name}' is INT but received a decimal number '{value}'. "
                        f"INT columns do not allow fractional values. Use a whole number or change the column type to DECIMAL."
                    )
                if isinstance(value, str):
                    # Allow strings that represent plain integers (e.g. returned from file reads)
                    stripped = value.lstrip('-')
                    if stripped.isdigit():
                        return True, int(value)
                    return False, (
                        f"Type mismatch: column '{col_name}' is INT but received the text value '{value}'. "
                        f"INT columns only accept whole numbers."
                    )
                return False, (
                    f"Type mismatch: column '{col_name}' is INT but received a {type(value).__name__} value '{value}'. "
                    f"INT columns only accept whole numbers."
                )

            elif col_type == "DECIMAL":
                if isinstance(value, bool):
                    return False, (
                        f"Type mismatch: column '{col_name}' is DECIMAL but received a BOOLEAN value '{value}'. "
                        f"Use a numeric value instead."
                    )
                if isinstance(value, (int, float)):
                    return True, float(value)
                if isinstance(value, str):
                    try:
                        return True, float(value)
                    except ValueError:
                        return False, (
                            f"Type mismatch: column '{col_name}' is DECIMAL but received the text value '{value}'. "
                            f"DECIMAL columns only accept numeric values (e.g. 3.14, 100, -0.5)."
                        )
                return False, (
                    f"Type mismatch: column '{col_name}' is DECIMAL but received a {type(value).__name__} value '{value}'. "
                    f"DECIMAL columns only accept numeric values."
                )
            
            elif col_type == "BOOLEAN":
                if isinstance(value, bool):
                    return True, value
                if isinstance(value, str):
                    if value.upper() in ['TRUE', 'YES', '1', 'T']:
                        return True, True
                    elif value.upper() in ['FALSE', 'NO', '0', 'F']:
                        return True, False
                    return False, (
                        f"Type mismatch: column '{col_name}' is BOOLEAN but received the text value '{value}'. "
                        f"Use TRUE or FALSE."
                    )
                if isinstance(value, (int, float)):
                    return True, bool(value)
                return False, (
                    f"Type mismatch: column '{col_name}' is BOOLEAN but received a {type(value).__name__} value '{value}'. "
                    f"Use TRUE or FALSE."
                )

            elif col_type == "DATE":
                if isinstance(value, str):
                    try:
                        datetime.date.fromisoformat(value)
                        return True, value
                    except ValueError:
                        return False, (
                            f"Type mismatch: column '{col_name}' is DATE but '{value}' is not a valid date. "
                            f"Use the format YYYY-MM-DD (e.g. '2024-06-15')."
                        )
                elif isinstance(value, datetime.date):
                    return True, value.isoformat()
                return False, (
                    f"Type mismatch: column '{col_name}' is DATE but received a {type(value).__name__} value '{value}'. "
                    f"Dates must be strings in YYYY-MM-DD format."
                )

            elif col_type == "TIME":
                if isinstance(value, str):
                    try:
                        datetime.datetime.strptime(value, "%H:%M:%S")
                        return True, value
                    except ValueError:
                        return False, (
                            f"Type mismatch: column '{col_name}' is TIME but '{value}' is not a valid time. "
                            f"Use the format HH:MM:SS (e.g. '14:30:00')."
                        )
                return False, (
                    f"Type mismatch: column '{col_name}' is TIME but received a {type(value).__name__} value '{value}'. "
                    f"Times must be strings in HH:MM:SS format."
                )

            elif col_type == "TIMESTAMP":
                if isinstance(value, str):
                    try:
                        datetime.datetime.fromisoformat(value)
                        return True, value
                    except ValueError:
                        return False, (
                            f"Type mismatch: column '{col_name}' is TIMESTAMP but '{value}' is not a valid timestamp. "
                            f"Use ISO format: 'YYYY-MM-DD HH:MM:SS' (e.g. '2024-06-15 14:30:00')."
                        )
                elif isinstance(value, datetime.datetime):
                    return True, value.isoformat()
                return False, (
                    f"Type mismatch: column '{col_name}' is TIMESTAMP but received a {type(value).__name__} value '{value}'. "
                    f"Use ISO format: 'YYYY-MM-DD HH:MM:SS'."
                )

            elif col_type in ["VARCHAR", "TEXT"]:
                return True, str(value)

            else:
                return True, value

        except (ValueError, TypeError) as e:
            return False, f"Type error for column '{col_name}': {str(e)}"
    
    def _check_unique_constraint(self, table_name, col_name, value, exclude_row_id=None):
        """Check if value violates unique constraint"""
        table_dir = os.path.join(self.data_dir, self.current_db, table_name)
        col_file = os.path.join(table_dir, "col_store", f"{col_name}.txt")
        
        if not os.path.exists(col_file):
            return False
        
        with open(col_file, 'r') as f:
            next(f)  # Skip header
            for row_id, line in enumerate(f, start=1):
                if exclude_row_id == row_id:
                    continue
                line = line.strip()
                if line and str(line) == str(value):
                    return True
        
        return False
    
    def _check_foreign_key_constraint(self, table_name, fk_column, fk_value):
        """Check if foreign key value exists in referenced table"""
        schema = self.tables[table_name.lower()]
        
        for fk in schema.get("foreign_keys", []):
            if fk["column"] == fk_column:
                ref_table = fk["ref_table"].lower()
                ref_column = fk["ref_column"]
                
                # Check if referenced table exists
                if ref_table not in self.tables:
                    return False, f"Referenced table '{fk['ref_table']}' does not exist"
                
                # Check if reference exists
                ref_dir = os.path.join(self.data_dir, self.current_db, self.tables[ref_table]["original_name"])
                ref_col_file = os.path.join(ref_dir, "col_store", f"{ref_column}.txt")
                
                if not os.path.exists(ref_col_file):
                    return False, f"Referenced column '{ref_column}' does not exist in table '{fk['ref_table']}'"
                
                with open(ref_col_file, 'r') as f:
                    next(f)  # Skip header
                    for line in f:
                        line = line.strip()
                        if line and str(line) == str(fk_value):
                            return True, None
                
                return False, f"Foreign key value '{fk_value}' not found in {fk['ref_table']}.{ref_column}"
        
        return True, None  # No foreign key constraint for this column

    def _check_constraint(self, value, constraint_expr, col_name):
        """Check if value satisfies a CHECK constraint"""
        if not constraint_expr:
            return True
        if value is None:
            return True  # NULL values skip CHECK constraints

        # Normalise expression for comparison
        expr = constraint_expr.lower().strip()

        # IMPORTANT: check two-char operators BEFORE single-char ones to avoid mis-parsing
        for op in [">=", "<=", ">", "<", "="]:
            if op in expr:
                parts = expr.split(op, 1)
                if len(parts) == 2:
                    left = parts[0].strip()
                    right = parts[1].strip()

                    if left != col_name.lower():
                        continue  # constraint references a different column

                    # Strip surrounding quotes from right side
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
                        # Fall back to string comparison for = only
                        if op == "=":
                            return str(value) == str(right)
                        return False

        return True

    def insert_into_table(self, table_name, columns=None, values=None):
        """Insert data into a table with full constraint validation - NO DATA STORED if validation fails"""
        table_key = table_name.lower()
        
        if table_key not in self.tables:
            return False, f"Table '{table_name}' does not exist in database '{self.current_db}'"
        
        schema = self.tables[table_key]
        original_name = schema["original_name"]
        expected_columns = [col["name"] for col in schema["columns"]]
        constraints = schema.get("constraints", {})
        
        # Build complete row data (tentative - not yet stored)
        row_data = {}
        
        # CASE 1: No columns specified - VALUES should match non-AUTO_INCREMENT columns in order
        if columns is None:
            # Exclude AUTO_INCREMENT columns from the expected count — users must not supply them
            non_auto_columns = [
                col_name for col_name in expected_columns
                if not constraints.get(col_name, {}).get("auto_increment", False)
            ]
            if len(values) != len(non_auto_columns):
                auto_cols = [c for c in expected_columns if constraints.get(c, {}).get("auto_increment", False)]
                if auto_cols:
                    return False, (
                        f"Expected {len(non_auto_columns)} values (excluding AUTO_INCREMENT "
                        f"column(s): {', '.join(auto_cols)}), got {len(values)}"
                    )
                return False, f"Expected {len(expected_columns)} values for all columns, got {len(values)}"

            # Map values to non-auto columns first, then fill auto-increment placeholders
            value_iter = iter(values)
            for col_name in expected_columns:
                col_constraints = constraints.get(col_name, {})

                # Handle AUTO_INCREMENT
                if col_constraints.get("auto_increment", False):
                    # Don't increment yet - do it after validation
                    row_data[col_name] = "AUTO_INCREMENT"  # Placeholder
                    continue

                value = next(value_iter, None)
                col_constraints = constraints.get(col_name, {})

                if value is not None:
                    row_data[col_name] = value
                elif col_constraints.get("default") is not None:
                    # Use default value
                    default_val = col_constraints["default"]
                    if default_val in ["CURRENT_DATE", "CURRENT_TIME", "CURRENT_TIMESTAMP"]:
                        if default_val == "CURRENT_DATE":
                            row_data[col_name] = datetime.date.today().isoformat()
                        elif default_val == "CURRENT_TIME":
                            row_data[col_name] = datetime.datetime.now().time().isoformat()
                        elif default_val == "CURRENT_TIMESTAMP":
                            row_data[col_name] = datetime.datetime.now().isoformat()
                    else:
                        row_data[col_name] = self._convert_value(default_val)
                elif col_constraints.get("not_null", False):
                    return False, f"NOT NULL constraint violated: Column '{col_name}' requires a value"
                else:
                    row_data[col_name] = None
        
        # CASE 2: Columns specified - match values to named columns
        else:
            # Validate column names
            for col in columns:
                if col not in expected_columns:
                    return False, f"Column '{col}' does not exist in table '{original_name}'"
            
            if len(values) != len(columns):
                return False, f"Expected {len(columns)} values for specified columns, got {len(values)}"
            
            # Initialize all columns with defaults or NULL
            for col in schema["columns"]:
                col_name = col["name"]
                col_constraints = constraints.get(col_name, {})
                
                if col_constraints.get("auto_increment", False):
                    row_data[col_name] = "AUTO_INCREMENT"  # Placeholder
                elif col_constraints.get("default") is not None and col_name not in columns:
                    default_val = col_constraints["default"]
                    if default_val in ["CURRENT_DATE", "CURRENT_TIME", "CURRENT_TIMESTAMP"]:
                        if default_val == "CURRENT_DATE":
                            row_data[col_name] = datetime.date.today().isoformat()
                        elif default_val == "CURRENT_TIME":
                            row_data[col_name] = datetime.datetime.now().time().isoformat()
                        elif default_val == "CURRENT_TIMESTAMP":
                            row_data[col_name] = datetime.datetime.now().isoformat()
                    else:
                        row_data[col_name] = self._convert_value(default_val)
                else:
                    row_data[col_name] = None
            
            # Fill in user-provided values
            for col_name, value in zip(columns, values):
                row_data[col_name] = value
        
        # ========== VALIDATION PHASE - Check all constraints BEFORE any write ==========
        
        # 1. Validate NOT NULL constraints
        # AUTO_INCREMENT columns will be assigned by the engine — never flag them as NULL
        for col_name, value in row_data.items():
            if value == "AUTO_INCREMENT":
                continue  # will be filled in after validation
            col_constraints = constraints.get(col_name, {})
            if col_constraints.get("not_null", False) and value is None:
                return False, f"NOT NULL constraint violated: Column '{col_name}' cannot be NULL"
        
        # 2. Validate data types and convert if needed
        converted_data = {}
        for col in schema["columns"]:
            col_name = col["name"]
            value = row_data.get(col_name)
            
            if value == "AUTO_INCREMENT":
                # Handle AUTO_INCREMENT after validation
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
        for pk in schema["primary_key"]:
            pk_value = row_data.get(pk)
            if pk_value is not None and pk_value != "AUTO_INCREMENT":
                if self._check_primary_key_exists(original_name, pk, pk_value):
                    return False, f"Duplicate primary key value '{pk_value}' for column '{pk}'"
        
        # 4. Check UNIQUE constraints
        for col_name, value in row_data.items():
            if value is not None and value != "AUTO_INCREMENT":
                # Check column-level unique
                col_constraints = constraints.get(col_name, {})
                if col_constraints.get("unique", False):
                    if self._check_unique_constraint(original_name, col_name, value):
                        return False, f"UNIQUE constraint violated: Value '{value}' already exists in column '{col_name}'"
                
                # Check table-level unique constraints
                if col_name in schema.get("unique_constraints", {}):
                    if self._check_unique_constraint(original_name, col_name, value):
                        return False, f"UNIQUE constraint violated: Value '{value}' already exists in column '{col_name}'"
        
        # 5. Check FOREIGN KEY constraints
        for fk in schema.get("foreign_keys", []):
            fk_column = fk["column"]
            fk_value = row_data.get(fk_column)
            if fk_value is not None and fk_value != "AUTO_INCREMENT":
                is_valid, error_msg = self._check_foreign_key_constraint(table_key, fk_column, fk_value)
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
        
        # Process AUTO_INCREMENT values (only now, after validation)
        for col in schema["columns"]:
            col_name = col["name"]
            if row_data.get(col_name) == "AUTO_INCREMENT":
                key = f"{table_key}.{col_name}"
                # Get next value
                next_val = self.auto_increment_counters.get(key, 0) + 1
                row_data[col_name] = next_val
                # Save the updated counter
                self._save_auto_increment_counter(original_name, col_name, next_val)
        
        # Get next row ID
        table_dir = os.path.join(self.data_dir, self.current_db, original_name)
        row_store_file = os.path.join(table_dir, "row_store.txt")
        
        with open(row_store_file, 'r') as f:
            row_count = sum(1 for line in f) - 1
        
        row_id = row_count + 1
        
        # Insert into row_store.txt in column order
        row_values = []
        for col in schema["columns"]:
            value = row_data[col["name"]]
            row_values.append(str(value) if value is not None else "")
        
        with open(row_store_file, 'a') as f:
            f.write(",".join(row_values) + "\n")
        
        # Insert into column store files
        for col in schema["columns"]:
            col_name = col["name"]
            col_file = os.path.join(table_dir, "col_store", f"{col_name}.txt")
            value = row_data[col_name] if row_data[col_name] is not None else ""
            
            with open(col_file, 'a') as f:
                f.write(str(value) + "\n")
        
        print(f"\n✅ Inserted 1 row into '{original_name}'")
        return True, f"Inserted successfully into '{original_name}'"
    
    def _check_primary_key_exists(self, table_name, pk_column, pk_value):
        """Check if a primary key value already exists"""
        table_dir = os.path.join(self.data_dir, self.current_db, table_name)
        col_file = os.path.join(table_dir, "col_store", f"{pk_column}.txt")
        
        if not os.path.exists(col_file):
            return False
        
        with open(col_file, 'r') as f:
            next(f)  # Skip header
            for line in f:
                line = line.strip()
                if line and str(line) == str(pk_value):
                    return True
        
        return False
    
    # ========== UPDATE METHODS ==========
    def parse_update(self, query):
        """Parse UPDATE query"""
        if not self.current_db:
            return False, "No database selected. Use: CREATE DATABASE db_name; or USE DATABASE db_name;"
        
        query = self.parse_query(query)
        
        # Pattern: UPDATE table_name SET col1=val1, col2=val2 WHERE condition
        pattern = r"UPDATE (\w+)\s+SET\s+(.+?)(?:\s+WHERE\s+(.+))?$"
        match = re.match(pattern, query, re.IGNORECASE | re.MULTILINE | re.DOTALL)
        
        if not match:
            return False, "Invalid UPDATE syntax. Use: UPDATE table_name SET col1=val1, col2=val2 WHERE condition;"
        
        table_name = match.group(1)
        set_clause = match.group(2)
        where_clause = match.group(3) if match.group(3) else None
        
        # Parse SET clause
        updates = {}
        set_parts = self._split_set_clause(set_clause)
        
        for part in set_parts:
            if '=' not in part:
                return False, f"Invalid SET clause: '{part}'"
            
            col, val = part.split('=', 1)
            col = col.strip()
            val = val.strip()
            updates[col] = self._convert_value(val)
        
        return self.update_table(table_name, updates, where_clause)
    
    def _split_set_clause(self, set_clause):
        """Split SET clause handling commas in values"""
        parts = []
        current = ""
        paren_count = 0
        in_quotes = False
        quote_char = None
        
        for char in set_clause:
            if char in ['"', "'"] and not in_quotes:
                in_quotes = True
                quote_char = char
                current += char
            elif char == quote_char and in_quotes:
                in_quotes = False
                quote_char = None
                current += char
            elif char == '(' and not in_quotes:
                paren_count += 1
                current += char
            elif char == ')' and not in_quotes:
                paren_count -= 1
                current += char
            elif char == ',' and paren_count == 0 and not in_quotes:
                parts.append(current.strip())
                current = ""
            else:
                current += char
        
        if current.strip():
            parts.append(current.strip())
        
        return parts
    
    def update_table(self, table_name, updates, where_clause=None):
        """Update data in a table with full constraint validation - NO DATA STORED if validation fails"""
        table_key = table_name.lower()
        
        if table_key not in self.tables:
            return False, f"Table '{table_name}' does not exist in database '{self.current_db}'"
        
        schema = self.tables[table_key]
        original_name = schema["original_name"]
        constraints = schema.get("constraints", {})
        
        # Validate column names in SET clause
        for col_name in updates.keys():
            if col_name not in [col["name"] for col in schema["columns"]]:
                return False, f"Column '{col_name}' does not exist in table '{original_name}'"
        
        # Check if trying to update AUTO_INCREMENT column
        for col_name in updates.keys():
            if constraints.get(col_name, {}).get("auto_increment", False):
                return False, f"Cannot update AUTO_INCREMENT column '{col_name}'"
        
        # Get all rows to update based on WHERE clause
        rows_to_update = self._get_rows_matching_condition(original_name, where_clause)
        
        if not rows_to_update:
            print(f"\nℹ️  No rows found matching the WHERE condition")
            return True, "No rows to update"
        
        # ========== VALIDATION PHASE - Check all constraints BEFORE any write ==========
        
        # Store original data for rollback (in memory)
        original_rows = {}
        validated_updates = {}
        
        for row_id in rows_to_update:
            # Get current row data
            current_row = self._get_row_by_id(original_name, row_id)
            if not current_row:
                continue
            
            # Create updated row data (tentative)
            updated_row = current_row.copy()
            for col_name, new_value in updates.items():
                updated_row[col_name] = new_value
            
            # 1. Validate NOT NULL constraints for updated columns
            for col_name, new_value in updates.items():
                col_constraints = constraints.get(col_name, {})
                if col_constraints.get("not_null", False) and new_value is None:
                    return False, f"NOT NULL constraint violated: Column '{col_name}' cannot be NULL (row {row_id})"
            
            # 2. Validate data types and convert if needed
            converted_updates = {}
            for col_name, new_value in updates.items():
                if new_value is not None:
                    col_type = next((col["type"] for col in schema["columns"] if col["name"] == col_name), None)
                    if col_type:
                        is_valid, converted_value = self._validate_type(new_value, col_type, col_name)
                        if not is_valid:
                            return False, f"UPDATE rejected (row {row_id}): {converted_value}"
                        converted_updates[col_name] = converted_value
            
            # Apply converted values
            for col_name, converted_value in converted_updates.items():
                updated_row[col_name] = converted_value
            
            # 3. Check PRIMARY KEY uniqueness (if primary key is being updated)
            for pk in schema["primary_key"]:
                if pk in updates:
                    new_pk_value = updated_row.get(pk)
                    if new_pk_value is not None:
                        # Check if new PK value already exists in another row
                        if self._check_primary_key_exists_excluding_row(original_name, pk, new_pk_value, row_id):
                            return False, f"Duplicate primary key value '{new_pk_value}' for column '{pk}' (would conflict with existing row)"
            
            # 4. Check UNIQUE constraints for updated columns
            for col_name, new_value in updates.items():
                if new_value is not None:
                    # Check column-level unique
                    col_constraints = constraints.get(col_name, {})
                    if col_constraints.get("unique", False):
                        if self._check_unique_constraint_excluding_row(original_name, col_name, new_value, row_id):
                            return False, f"UNIQUE constraint violated: Value '{new_value}' already exists in column '{col_name}' (row {row_id})"
                    
                    # Check table-level unique constraints
                    if col_name in schema.get("unique_constraints", {}):
                        if self._check_unique_constraint_excluding_row(original_name, col_name, new_value, row_id):
                            return False, f"UNIQUE constraint violated: Value '{new_value}' already exists in column '{col_name}' (row {row_id})"
            
            # 5. Check FOREIGN KEY constraints for updated columns
            for fk in schema.get("foreign_keys", []):
                fk_column = fk["column"]
                if fk_column in updates:
                    fk_value = updated_row.get(fk_column)
                    if fk_value is not None:
                        is_valid, error_msg = self._check_foreign_key_constraint(table_key, fk_column, fk_value)
                        if not is_valid:
                            return False, f"Foreign key constraint failed for row {row_id}: {error_msg}"
            
            # 6. Check CHECK constraints for updated columns
            for col_name, new_value in updates.items():
                if new_value is not None:
                    col_constraints = constraints.get(col_name, {})
                    check_expr = col_constraints.get("check")
                    if check_expr and not self._check_constraint(new_value, check_expr, col_name):
                        return False, f"CHECK constraint violated for column '{col_name}': {check_expr} (row {row_id})"
            
            # Store validated update for this row
            validated_updates[row_id] = {
                "updates": converted_updates,
                "original_row": current_row
            }
        
        # ========== ALL VALIDATIONS PASSED - NOW APPLY UPDATES ==========
        
        # Apply all validated updates
        updated_count = 0
        for row_id, update_info in validated_updates.items():
            # Update row_store.txt
            success = self._update_row_in_store(original_name, row_id, update_info["updates"])
            if success:
                # Update column store files
                self._update_row_in_column_stores(original_name, row_id, update_info["updates"])
                updated_count += 1
        
        print(f"\n✅ Updated {updated_count} row(s) in '{original_name}'")
        return True, f"Updated {updated_count} row(s) in '{original_name}'"
    
    def _get_rows_matching_condition(self, table_name, where_clause):
        """Get row IDs that match the WHERE condition"""
        if not where_clause:
            # No WHERE clause means update all rows
            table_dir = os.path.join(self.data_dir, self.current_db, table_name)
            row_store_file = os.path.join(table_dir, "row_store.txt")
            
            with open(row_store_file, 'r') as f:
                # Skip header
                next(f)
                row_ids = [i + 1 for i, line in enumerate(f)]
            return row_ids
        
        # Parse simple WHERE condition (can be extended)
        # Support format: column = value
        condition = where_clause.strip()
        
        if '=' in condition:
            parts = condition.split('=', 1)
            col_name = parts[0].strip()
            value = self._convert_value(parts[1].strip())
            
            # Find rows where column equals value
            matching_rows = []
            table_dir = os.path.join(self.data_dir, self.current_db, table_name)
            col_file = os.path.join(table_dir, "col_store", f"{col_name}.txt")
            
            if os.path.exists(col_file):
                with open(col_file, 'r') as f:
                    next(f)  # Skip header
                    for row_id, line in enumerate(f, start=1):
                        line = line.strip()
                        if line and str(line) == str(value):
                            matching_rows.append(row_id)
            return matching_rows
        
        # If condition not parsed, return all rows (with warning)
        print(f"⚠️  Warning: Complex WHERE clause not fully supported. Updating all rows.")
        table_dir = os.path.join(self.data_dir, self.current_db, table_name)
        row_store_file = os.path.join(table_dir, "row_store.txt")
        
        with open(row_store_file, 'r') as f:
            next(f)
            row_ids = [i + 1 for i, line in enumerate(f)]
        return row_ids
    
    def _get_row_by_id(self, table_name, row_id):
        """Get row data by row ID"""
        table_dir = os.path.join(self.data_dir, self.current_db, table_name)
        row_store_file = os.path.join(table_dir, "row_store.txt")
        
        # Get schema to know column order
        table_key = table_name.lower()
        if table_key not in self.tables:
            return None
        
        schema = self.tables[table_key]
        columns = [col["name"] for col in schema["columns"]]
        
        with open(row_store_file, 'r') as f:
            # Skip header
            next(f)
            for current_id, line in enumerate(f, start=1):
                if current_id == row_id:
                    values = line.strip().split(',')
                    row_data = {}
                    for i, col_name in enumerate(columns):
                        if i < len(values):
                            val = values[i]
                            row_data[col_name] = val if val else None
                        else:
                            row_data[col_name] = None
                    return row_data
        
        return None
    
    def _check_primary_key_exists_excluding_row(self, table_name, pk_column, pk_value, exclude_row_id):
        """Check if a primary key value already exists excluding a specific row"""
        table_dir = os.path.join(self.data_dir, self.current_db, table_name)
        col_file = os.path.join(table_dir, "col_store", f"{pk_column}.txt")
        
        if not os.path.exists(col_file):
            return False
        
        with open(col_file, 'r') as f:
            next(f)  # Skip header
            for row_id, line in enumerate(f, start=1):
                if row_id == exclude_row_id:
                    continue
                line = line.strip()
                if line and str(line) == str(pk_value):
                    return True
        
        return False
    
    def _check_unique_constraint_excluding_row(self, table_name, col_name, value, exclude_row_id):
        """Check if value violates unique constraint excluding a specific row"""
        table_dir = os.path.join(self.data_dir, self.current_db, table_name)
        col_file = os.path.join(table_dir, "col_store", f"{col_name}.txt")
        
        if not os.path.exists(col_file):
            return False
        
        with open(col_file, 'r') as f:
            next(f)  # Skip header
            for row_id, line in enumerate(f, start=1):
                if row_id == exclude_row_id:
                    continue
                line = line.strip()
                if line and str(line) == str(value):
                    return True
        
        return False
    
    def _update_row_in_store(self, table_name, row_id, updates):
        """Update a row in row_store.txt"""
        table_dir = os.path.join(self.data_dir, self.current_db, table_name)
        row_store_file = os.path.join(table_dir, "row_store.txt")
        
        # Get schema to know column order
        table_key = table_name.lower()
        if table_key not in self.tables:
            return False
        
        schema = self.tables[table_key]
        columns = [col["name"] for col in schema["columns"]]
        
        # Read all rows
        rows = []
        with open(row_store_file, 'r') as f:
            header = f.readline().strip()
            for line in f:
                rows.append(line.strip().split(','))
        
        # Update the specific row
        if row_id - 1 < len(rows):
            row = rows[row_id - 1]
            for col_name, new_value in updates.items():
                if col_name in columns:
                    col_index = columns.index(col_name)
                    row[col_index] = str(new_value) if new_value is not None else ""
        
        # Write back all rows
        with open(row_store_file, 'w') as f:
            f.write(header + "\n")
            for row in rows:
                f.write(",".join(row) + "\n")
        
        return True
    
    def _update_row_in_column_stores(self, table_name, row_id, updates):
        """Update a row in column store files"""
        table_dir = os.path.join(self.data_dir, self.current_db, table_name)
        
        for col_name, new_value in updates.items():
            col_file = os.path.join(table_dir, "col_store", f"{col_name}.txt")
            
            # Read all values for this column
            values = []
            with open(col_file, 'r') as f:
                header = f.readline()
                for line in f:
                    values.append(line.strip())
            
            # Update the specific row
            if row_id - 1 < len(values):
                values[row_id - 1] = str(new_value) if new_value is not None else ""
            
            # Write back all values
            with open(col_file, 'w') as f:
                f.write(header)
                for value in values:
                    f.write(value + "\n")
        
        return True
    
    # ========== UTILITY METHODS ==========
    def get_table_schema(self, table_name):
        """Get schema for a table (case-insensitive)"""
        return self.tables.get(table_name.lower())
    
    def list_tables(self):
        """List all tables in current database"""
        if not self.metadata:
            return []
        return self.metadata.get_all_tables()
    
    def display_schema(self, table_name):
        """Display table schema nicely (case-insensitive)"""
        if not self.current_db:
            print("❌ No database selected")
            return
        
        table_key = table_name.lower()
        if table_key not in self.tables:
            print(f"❌ Table '{table_name}' not found in database '{self.current_db}'")
            return
        
        schema = self.tables[table_key]
        original_name = schema["original_name"]
        constraints = schema.get("constraints", {})
        
        print(f"\n📋 Schema for '{original_name}' (Database: {self.current_db}):")
        print("-" * 80)
        print(f"{'Column':<15} {'Type':<12} {'Constraints':<50}")
        print("-" * 80)
        
        for col in schema["columns"]:
            col_name = col["name"]
            col_type = col["type"]
            col_constraints = constraints.get(col_name, {})
            
            constraint_list = []
            if col_name in schema["primary_key"]:
                constraint_list.append("PRIMARY KEY")
            if col_constraints.get("auto_increment"):
                constraint_list.append("AUTO_INCREMENT")
            if col_constraints.get("not_null"):
                constraint_list.append("NOT NULL")
            if col_constraints.get("unique"):
                constraint_list.append("UNIQUE")
            if col_constraints.get("default") is not None:
                constraint_list.append(f"DEFAULT {col_constraints['default']}")
            if col_constraints.get("check"):
                constraint_list.append(f"CHECK {col_constraints['check']}")
            
            for fk in schema["foreign_keys"]:
                if fk["column"] == col_name:
                    constraint_list.append(f"FOREIGN KEY → {fk['ref_table']}.{fk['ref_column']}")
            
            constraint_str = ", ".join(constraint_list) if constraint_list else "-"
            print(f"{col_name:<15} {col_type:<12} {constraint_str:<50}")
        print("-" * 80)