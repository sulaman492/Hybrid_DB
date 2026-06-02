import os

class StorageManager:
    def __init__(self, data_dir="data"):
        self.data_dir = data_dir
    
    def insert_row(self, db_name, table_name, values):
        """Insert a row into row_store.txt"""
        table_dir = os.path.join(self.data_dir, db_name, table_name)
        row_file = os.path.join(table_dir, "row_store.txt")
        
        row_line = ",".join(str(v) for v in values) + "\n"
        
        with open(row_file, "a") as f:
            f.write(row_line)
        
        return True
    
    def insert_into_column_store(self, db_name, table_name, column_name, value):
        """Insert value into column store"""
        col_file = os.path.join(self.data_dir, db_name, table_name, "col_store", f"{column_name}.txt")
        
        with open(col_file, "a") as f:
            f.write(str(value) + "\n")
        
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
                        converted_values = []
                        for v in values:
                            try:
                                converted_values.append(int(v))
                            except:
                                try:
                                    converted_values.append(float(v))
                                except:
                                    converted_values.append(v)
                        rows.append(dict(zip(headers, converted_values)))
        
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
                    try:
                        values.append(int(line))
                    except:
                        try:
                            values.append(float(line))
                        except:
                            values.append(line)
        
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
                f.write(str(val) + "\n")
        
        return True