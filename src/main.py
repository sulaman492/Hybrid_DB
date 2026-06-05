from .db_core import DBCore

class HybridDBConsole:
    def __init__(self):
        self.db = DBCore()
        self.running = True
    
    def run(self):
        """Main console loop"""
        self.print_welcome()
        
        while self.running:
            try:
                query = input("\n🔍 SQL> ").strip()
                
                if not query:
                    continue
                
                self.execute_query(query)
            
            except KeyboardInterrupt:
                print("\n\n👋 Goodbye!")
                break
            except Exception as e:
                print(f"❌ Error: {e}")
    
    def print_welcome(self):
        """Print welcome message"""
        print("=" * 70)
        print("🎓 HYBRID DBMS - Console Database")
        print("=" * 70)
        
        # Show current database if any
        current_db = self.db.get_current_db()
        if current_db:
            print(f"\n💾 Loaded last database: {current_db}")
            print(f"   Type 'USE DATABASE {current_db}' if you want to switch")
        else:
            print("\n💾 No database loaded. Use SHOW DATABASES to see available databases")
        
        print("\n📖 Quick Commands:")
        print("   SHOW DATABASES - List all databases")
        print("   USE DATABASE db_name - Switch to a database")
        print("   SHOW TABLES - Show tables in current database")
        print("   SELECT * FROM table_name - Query data")
        print("   SELECT DISTINCT column FROM table_name - Unique values")
        print("   SELECT AVG(column) FROM table_name - Aggregation")
        print("   SELECT dept, COUNT(*) FROM t GROUP BY dept HAVING COUNT(*) > 2 - Filter groups")
        print("   SELECT * FROM table1 JOIN table2 ON condition - JOIN")
        print("   DELETE FROM table WHERE condition - Delete rows")
        print("   UPDATE table SET column = value WHERE condition - Update rows")
        print("   EXIT - Quit")
        print("=" * 70)
    
    def execute_query(self, query):
        """Execute user query"""
        # Remove trailing semicolon if present
        query = query.rstrip(';')
        query_upper = query.upper().strip()
        
        # EXIT
        if query_upper in ["EXIT", "QUIT", "BYE"]:
            print("👋 Goodbye!")
            self.running = False
            return
        
        # CREATE DATABASE
        if query_upper.startswith("CREATE DATABASE"):
            success, message = self.db.execute_create_database(query)
            print(f"{'✅' if success else '❌'} {message}")
            return
        
        # USE DATABASE
        if query_upper.startswith("USE DATABASE"):
            parts = query.split()
            if len(parts) >= 3:
                db_name = parts[2]
                success, message = self.db.use_database(db_name)
                print(f"{'✅' if success else '❌'} {message}")
            else:
                print("❌ Usage: USE DATABASE db_name")
            return
        
        # SHOW DATABASES
        if query_upper == "SHOW DATABASES":
            databases = self.db.list_databases()
            if databases:
                print("\n📁 Databases:")
                current_db = self.db.get_current_db()
                for db in databases:
                    if db == current_db:
                        print(f"   🟢 {db} (current)")
                    else:
                        print(f"   📁 {db}")
            else:
                print("📭 No databases found. Create one with: CREATE DATABASE db_name;")
            return
        
        # SHOW TABLES
        if query_upper == "SHOW TABLES":
            tables = self.db.show_tables()
            current_db = self.db.get_current_db()
            if not current_db:
                print("❌ No database selected. First use: USE DATABASE db_name;")
            elif tables:
                print(f"\n📁 Tables in database '{current_db}':")
                for t in tables:
                    print(f"   📋 {t}")
            else:
                print(f"📭 No tables found in database '{current_db}'")
            return
        
        # CREATE TABLE
        if query_upper.startswith("CREATE TABLE"):
            success, message = self.db.execute_create_table(query)
            print(f"{'✅' if success else '❌'} {message}")
            return
            
        # CREATE VIEW
        if query_upper.startswith("CREATE VIEW"):
            success, message = self.db.execute_create_view(query)
            print(f"{'✅' if success else '❌'} {message}")
            return
            
        # CREATE TRIGGER
        if query_upper.startswith("CREATE TRIGGER"):
            success, message = self.db.execute_create_trigger(query)
            print(f"{'✅' if success else '❌'} {message}")
            return
        
        # DESCRIBE
        if query_upper.startswith("DESCRIBE"):
            parts = query.split()
            if len(parts) >= 2:
                table_name = parts[1]
                self.db.describe_table(table_name)
            else:
                print("❌ Usage: DESCRIBE table_name")
            return
        
        # INSERT INTO
        if query_upper.startswith("INSERT INTO"):
            success, message = self.db.execute_insert(query)
            print(f"{'✅' if success else '❌'} {message}")
            return
        
        # DELETE FROM
        if query_upper.startswith("DELETE FROM"):
            success, message = self.db.execute_delete(query)
            print(f"{'✅' if success else '❌'} {message}")
            return
        
        # UPDATE
        if query_upper.startswith("UPDATE"):
            success, message = self.db.execute_update(query)
            print(f"{'✅' if success else '❌'} {message}")
            return
        
        # SELECT
        if query_upper.startswith("SELECT"):
            result, success, message = self.db.execute_select(query)
            
            if not success:
                print(f"❌ {message}")
            else:
                self.display_results(result)
            return
        
        # Unknown command
        print(f"❌ Unknown command: {query}")
        print("   Available commands: CREATE DATABASE, USE DATABASE, SHOW DATABASES, SHOW TABLES, CREATE TABLE, DESCRIBE, INSERT INTO, DELETE FROM, UPDATE, SELECT, EXIT")
    
    def display_results(self, result):
        """Display query results"""
        if result is None:
            print("📭 No results")
            return
        
        # Check if result is a single value (aggregation result)
        if isinstance(result, (int, float)):
            print(f"\n📊 Result: {result}")
            return
        
        # Check if result is a list
        if isinstance(result, list):
            if not result:
                print("📭 No data found")
                return
            
            # Check if first element is a dict (multiple columns)
            if isinstance(result[0], dict):
                # Multiple columns
                print(f"\n📊 Results ({len(result)} row(s)):")
                print("-" * 80)
                headers = list(result[0].keys())
                print(" | ".join(f"{h:<12}" for h in headers))
                print("-" * 80)
                for row in result:
                    values = [str(row.get(h, ""))[:12] for h in headers]
                    print(" | ".join(f"{v:<12}" for v in values))
                print("-" * 80)
            else:
                # Single column list
                print(f"\n📊 Results ({len(result)} row(s)):")
                print("-" * 40)
                for row in result:
                    print(f"   {row}")
                print("-" * 40)
            return
        
        # Handle any other single value
        print(f"\n📊 Result: {result}")

def main():
    console = HybridDBConsole()
    console.run()

if __name__ == "__main__":
    main()