import os
import json

class MetadataManager:
    def __init__(self, metadata_dir):
        self.metadata_dir = metadata_dir
        self.tables_file = os.path.join(metadata_dir, "tables.txt")
        self.constraints_file = os.path.join(metadata_dir, "constraints.txt")
        self.views_file = os.path.join(metadata_dir, "views.txt")
        self.triggers_file = os.path.join(metadata_dir, "triggers.txt")
        
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

    # ========== VIEWS ==========
    def add_view(self, view_name, query):
        """Add a view to metadata"""
        # Read existing views
        views = self.get_views()
        views[view_name] = query
        
        with open(self.views_file, "w") as f:
            f.write(json.dumps(views))

    def get_views(self):
        """Get all views as a dictionary of {name: query}"""
        if not os.path.exists(self.views_file):
            return {}
        
        with open(self.views_file, "r") as f:
            content = f.read().strip()
            if not content:
                return {}
            return json.loads(content)

    def remove_view(self, view_name):
        """Remove a view from metadata"""
        views = self.get_views()
        if view_name in views:
            del views[view_name]
            with open(self.views_file, "w") as f:
                f.write(json.dumps(views))

    # ========== TRIGGERS ==========
    def add_trigger(self, name, table, event, action, query):
        """Add a trigger to metadata. Event is BEFORE/AFTER, action is INSERT/UPDATE/DELETE."""
        triggers = self.get_all_triggers()
        # Ensure uniqueness by name
        triggers = [t for t in triggers if t["name"] != name]
        triggers.append({
            "name": name,
            "table": table,
            "event": event,
            "action": action,
            "query": query
        })
        
        with open(self.triggers_file, "w") as f:
            for t in triggers:
                f.write(json.dumps(t) + "\n")

    def get_all_triggers(self):
        """Get all triggers"""
        if not os.path.exists(self.triggers_file):
            return []
        
        triggers = []
        with open(self.triggers_file, "r") as f:
            for line in f:
                if line.strip():
                    triggers.append(json.loads(line.strip()))
        return triggers

    def get_triggers(self, table):
        """Get triggers for a specific table"""
        all_triggers = self.get_all_triggers()
        return [t for t in all_triggers if t["table"] == table]

    def remove_trigger(self, name):
        """Remove a trigger from metadata"""
        triggers = self.get_all_triggers()
        triggers = [t for t in triggers if t["name"] != name]
        
        with open(self.triggers_file, "w") as f:
            for t in triggers:
                f.write(json.dumps(t) + "\n")