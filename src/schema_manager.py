import os
import re
from .metadata import MetadataManager

class SchemaManager:
    def __init__(self, data_dir="data"):
        self.data_dir = data_dir
        self.current_db = None
        self.metadata = None
        self.tables = {}
        
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
                checks = eval(lines[3].strip()) if len(lines) > 3 else []
                
                self.tables[table_name] = {
                    "columns": columns,
                    "primary_key": pk,
                    "foreign_keys": fk,
                    "checks": checks
                }
                
    def get_referencing_tables(self, target_table):
        """Returns a list of tuples (table_name, foreign_key_col) that reference the target_table"""
        referencing = []
        for table_name, schema in self.tables.items():
            for fk in schema.get("foreign_keys", []):
                if fk["ref_table"] == target_table:
                    referencing.append((table_name, fk["column"]))
        return referencing
    
    # ========== DATABASE METHODS ==========
    def parse_create_database(self, query):
        """Parse CREATE DATABASE query"""
        pattern = r"CREATE DATABASE (\w+)\s*;?"
        match = re.match(pattern, query, re.IGNORECASE)
        
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
        print(f"   You can now create tables with: CREATE TABLE ...")
        
        return True, f"Database '{db_name}' created and activated"
    
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
                    # Check if it has the structure of a database
                    if os.path.exists(os.path.join(item_path, "_metadata")):
                        databases.append(item)
        return databases
    
    # ========== VIEWS METHODS ==========
    def parse_create_view(self, query, parser):
        """Parse CREATE VIEW query and save it"""
        if not self.current_db:
            return False, "No database selected"
            
        view_name, select_query = parser.parse_create_view(query)
        if not view_name:
            return False, "Invalid CREATE VIEW syntax. Use: CREATE VIEW name AS SELECT ..."
            
        self.metadata.add_view(view_name, select_query)
        return True, f"View '{view_name}' created successfully"
        
    def get_view(self, view_name):
        """Get a view query by name"""
        if not self.metadata:
            return None
        views = self.metadata.get_views()
        return views.get(view_name)
        
    # ========== TRIGGERS METHODS ==========
    def parse_create_trigger(self, query, parser):
        """Parse CREATE TRIGGER query and save it"""
        if not self.current_db:
            return False, "No database selected"
            
        trigger_def = parser.parse_create_trigger(query)
        if not trigger_def:
            return False, "Invalid CREATE TRIGGER syntax."
            
        self.metadata.add_trigger(
            trigger_def["name"], 
            trigger_def["table"], 
            trigger_def["event"], 
            trigger_def["action"], 
            trigger_def["query"]
        )
        return True, f"Trigger '{trigger_def['name']}' created successfully"

    # ========== TABLE METHODS ==========
    def parse_create_table(self, query):
        """Parse CREATE TABLE query"""
        if not self.current_db:
            return False, "No database selected. Use: CREATE DATABASE db_name; or USE DATABASE db_name;"
        
        pattern = r"CREATE TABLE (\w+)\s*\((.*)\)\s*;?"
        match = re.match(pattern, query, re.IGNORECASE)
        
        if not match:
            return False, "Invalid CREATE TABLE syntax. Use: CREATE TABLE table_name (col1 TYPE, col2 TYPE, ...);"
        
        table_name = match.group(1)
        columns_def = match.group(2)
        
        columns = []
        primary_keys = []
        foreign_keys = []
        checks = []
        
        col_defs = self._split_column_defs(columns_def)
        
        for col_def in col_defs:
            col_def = col_def.strip()
            
            if not col_def:
                continue
            
            # Check for standalone CHECK constraint
            if col_def.upper().startswith("CHECK"):
                check_match = re.search(r"CHECK\s*\((.*)\)", col_def, re.IGNORECASE)
                if check_match:
                    checks.append(check_match.group(1).strip())
                continue

            # Check for standalone PRIMARY KEY constraint (e.g., PRIMARY KEY (dept_id))
            if col_def.upper().startswith("PRIMARY KEY"):
                pk_match = re.search(r"PRIMARY KEY\s*\((\w+)\)", col_def, re.IGNORECASE)
                if pk_match:
                    primary_keys.append(pk_match.group(1))
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
            
            # Check for inline CHECK constraint
            inline_check_match = re.search(r"CHECK\s*\((.*?)\)", col_def, re.IGNORECASE)
            if inline_check_match:
                checks.append(inline_check_match.group(1).strip())
                col_def = re.sub(r"CHECK\s*\(.*?\)", "", col_def, flags=re.IGNORECASE).strip()

            # Check for inline AUTOINCREMENT
            autoincrement = False
            if "AUTOINCREMENT" in col_def.upper():
                autoincrement = True
                col_def = re.sub(r"\bAUTOINCREMENT\b", "", col_def, flags=re.IGNORECASE).strip()

            # Check for inline UNIQUE
            unique = False
            if re.search(r"\bUNIQUE\b", col_def, re.IGNORECASE):
                unique = True
                col_def = re.sub(r"\bUNIQUE\b", "", col_def, flags=re.IGNORECASE).strip()

            # Check for inline NOT NULL
            not_null = False
            if re.search(r"\bNOT\s+NULL\b", col_def, re.IGNORECASE):
                not_null = True
                col_def = re.sub(r"\bNOT\s+NULL\b", "", col_def, flags=re.IGNORECASE).strip()

            # Check for inline DEFAULT
            default_val = None
            default_match = re.search(r"\bDEFAULT\s+((?:'[^']*')|(?:\"[^\"]*\")|\S+)", col_def, re.IGNORECASE)
            if default_match:
                raw_default = default_match.group(1)
                if raw_default.startswith("'") and raw_default.endswith("'"):
                    default_val = raw_default[1:-1]
                elif raw_default.startswith('"') and raw_default.endswith('"'):
                    default_val = raw_default[1:-1]
                else:
                    try:
                        if '.' in raw_default:
                            default_val = float(raw_default)
                        elif raw_default.upper() == 'TRUE':
                            default_val = True
                        elif raw_default.upper() == 'FALSE':
                            default_val = False
                        else:
                            default_val = int(raw_default)
                    except ValueError:
                        default_val = raw_default
                col_def = re.sub(r"\bDEFAULT\s+(?:(?:'[^']*')|(?:\"[^\"]*\")|\S+)", "", col_def, flags=re.IGNORECASE).strip()

            # Parse regular column: id INT or id INT PRIMARY KEY
            col_parts = col_def.split()
            if len(col_parts) >= 2:
                col_name = col_parts[0]
                col_type = col_parts[1].upper()
                
                # Check if this column has PRIMARY KEY (inline)
                has_primary_key = False
                remaining_parts = col_parts[2:]
                for i, part in enumerate(remaining_parts):
                    if part.upper() == "PRIMARY" and i+1 < len(remaining_parts) and remaining_parts[i+1].upper() == "KEY":
                        has_primary_key = True
                        break
                
                columns.append({
                    "name": col_name,
                    "type": col_type,
                    "autoincrement": autoincrement,
                    "unique": unique,
                    "not_null": not_null,
                    "default": default_val
                })
                
                if has_primary_key:
                    primary_keys.append(col_name)
                    columns[-1]["autoincrement"] = True
        
        if not columns:
            return False, "No valid columns defined"
            
        # Ensure all primary keys are marked as autoincrement (per user requirements)
        for col in columns:
            if col["name"] in primary_keys and col["type"] == "INT":
                col["autoincrement"] = True
        
        return self.create_table(table_name, columns, primary_keys, foreign_keys, checks)
    
    def _split_column_defs(self, columns_def):
        """Split column definitions handling parentheses and nested commas"""
        parts = []
        current = ""
        paren_count = 0
        in_quotes = False
        quote_char = None
        
        for char in columns_def:
            # Handle quotes
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
    
    def create_table(self, table_name, columns, primary_keys, foreign_keys, checks=[]):
        """Create a new table in current database"""
        if not self.current_db:
            return False, "No database selected"
        
        if table_name in self.tables:
            return False, f"Table '{table_name}' already exists in database '{self.current_db}'"
        
        table_dir = os.path.join(self.data_dir, self.current_db, table_name)
        os.makedirs(table_dir, exist_ok=True)
        os.makedirs(os.path.join(table_dir, "col_store"), exist_ok=True)
        
        # Save schema
        with open(os.path.join(table_dir, "schema.txt"), "w") as f:
            f.write(str(columns) + "\n")
            f.write(str(primary_keys) + "\n")
            f.write(str(foreign_keys) + "\n")
            f.write(str(checks) + "\n")
        
        # Create row_store.txt with header
        col_names = [col["name"] for col in columns]
        with open(os.path.join(table_dir, "row_store.txt"), "w") as f:
            f.write(",".join(col_names) + "\n")
        
        # Create column store files
        for col in columns:
            col_file = os.path.join(table_dir, "col_store", f"{col['name']}.txt")
            with open(col_file, "w") as f:
                f.write(f"# Column: {col['name']} Type: {col['type']}\n")
        
        # Store in memory
        self.tables[table_name] = {
            "columns": columns,
            "primary_key": primary_keys,
            "foreign_keys": foreign_keys,
            "checks": checks
        }
        
        # Update metadata
        if self.metadata:
            self.metadata.add_table(table_name)
        
        print(f"\n✅ Table '{table_name}' created successfully in database '{self.current_db}'!")
        print(f"   Columns: {[col['name'] for col in columns]}")
        if primary_keys:
            print(f"   Primary Key: {primary_keys}")
        if foreign_keys:
            print(f"   Foreign Keys: {foreign_keys}")
        if checks:
            print(f"   Checks: {checks}")
        
        return True, f"Table '{table_name}' created"
    
    def get_table_schema(self, table_name):
        """Get schema for a table"""
        return self.tables.get(table_name)
    
    def list_tables(self):
        """List all tables in current database"""
        if not self.metadata:
            return []
        return self.metadata.get_all_tables()
    
    def display_schema(self, table_name):
        """Display table schema nicely"""
        if not self.current_db:
            print("❌ No database selected")
            return
        
        if table_name not in self.tables:
            print(f"❌ Table '{table_name}' not found in database '{self.current_db}'")
            return
        
        schema = self.tables[table_name]
        print(f"\n📋 Schema for '{table_name}' (Database: {self.current_db}):")
        print("-" * 70)
        print(f"{'Column':<15} {'Type':<10} {'Constraints':<40}")
        print("-" * 70)
        
        for col in schema["columns"]:
            constraints = []
            if col["name"] in schema["primary_key"]:
                constraints.append("PRIMARY KEY")
            for fk in schema["foreign_keys"]:
                if fk["column"] == col["name"]:
                    constraints.append(f"FOREIGN KEY → {fk['ref_table']}.{fk['ref_column']}")
            
            constraint_str = ", ".join(constraints) if constraints else "-"
            print(f"{col['name']:<15} {col['type']:<10} {constraint_str:<40}")
        print("-" * 70)