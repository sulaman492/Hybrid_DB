import os
import json

class MetadataManager:
    def __init__(self, metadata_dir):
        self.metadata_dir = metadata_dir
        self.tables_file = os.path.join(metadata_dir, "tables.txt")
        self.constraints_file = os.path.join(metadata_dir, "constraints.txt")
        
        # Ensure directory exists
        os.makedirs(metadata_dir, exist_ok=True)
    
    def add_table(self, table_name):
        """Add table to metadata"""
        with open(self.tables_file, "a") as f:
            f.write(table_name + "\n")
    
    def get_all_tables(self):
        """Get list of all tables"""
        if not os.path.exists(self.tables_file):
            return []
        
        with open(self.tables_file, "r") as f:
            return [line.strip() for line in f if line.strip()]
    
    def remove_table(self, table_name):
        """Remove table from metadata"""
        tables = self.get_all_tables()
        tables = [t for t in tables if t != table_name]
        
        with open(self.tables_file, "w") as f:
            for t in tables:
                f.write(t + "\n")
    
    def add_constraint(self, constraint):
        """Add foreign key constraint"""
        with open(self.constraints_file, "a") as f:
            f.write(json.dumps(constraint) + "\n")
    
    def get_constraints(self):
        """Get all constraints"""
        if not os.path.exists(self.constraints_file):
            return []
        
        constraints = []
        with open(self.constraints_file, "r") as f:
            for line in f:
                if line.strip():
                    constraints.append(json.loads(line.strip()))
        return constraints