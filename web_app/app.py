from flask import Flask, render_template, request, jsonify
import sys
import os

# Force UTF-8 encoding for standard output to avoid emoji crashes on Windows
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except AttributeError:
    pass

# Add parent directory to path to import your DBMS
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.db_core import DBCore

app = Flask(__name__)
db = DBCore()

@app.route('/')
def index():
    """Main page"""
    current_db = db.get_current_db()
    databases = db.list_databases()
    tables = db.show_tables() if current_db else []
    
    triggers = []
    views = []
    if current_db and db.schema_manager.metadata:
        triggers = db.schema_manager.metadata.get_all_triggers()
        views = list(db.schema_manager.metadata.get_views().keys())
    
    return render_template('index.html', 
                         current_db=current_db,
                         databases=databases,
                         tables=tables,
                         triggers=triggers,
                         views=views)

@app.route('/api/execute', methods=['POST'])
def execute_query():
    """Execute SQL query and return results"""
    data = request.get_json()
    query = data.get('query', '').strip()
    
    if not query:
        return jsonify({'error': 'No query provided'})
    
    try:
        # Remove trailing semicolon
        query_clean = query.rstrip(';')
        query_upper = query_clean.upper().strip()
        
        # Handle different query types
        if query_upper.startswith('CREATE DATABASE'):
            success, message = db.execute_create_database(query_clean)
            return jsonify({'type': 'message', 'success': success, 'message': message})
        
        elif query_upper.startswith('USE DATABASE'):
            parts = query_clean.split()
            if len(parts) >= 3:
                db_name = parts[2]
                success, message = db.use_database(db_name)
                return jsonify({'type': 'message', 'success': success, 'message': message})
        
        elif query_upper == 'SHOW DATABASES':
            databases = db.list_databases()
            current_db = db.get_current_db()
            return jsonify({'type': 'databases', 'databases': databases, 'current_db': current_db})
        
        elif query_upper == 'SHOW TABLES':
            tables = db.show_tables()
            current_db = db.get_current_db()
            return jsonify({'type': 'tables', 'tables': tables, 'current_db': current_db})
        
        elif query_upper.startswith('CREATE TABLE'):
            success, message = db.execute_create_table(query_clean)
            return jsonify({'type': 'message', 'success': success, 'message': message})
            
        elif query_upper.startswith('CREATE VIEW'):
            success, message = db.execute_create_view(query_clean)
            return jsonify({'type': 'message', 'success': success, 'message': message})
            
        elif query_upper.startswith('CREATE TRIGGER'):
            success, message = db.execute_create_trigger(query_clean)
            return jsonify({'type': 'message', 'success': success, 'message': message})
        
        # DROP TABLE - ADDED
        elif query_upper.startswith('DROP TABLE'):
            success, message = db.execute_drop_table(query_clean)
            return jsonify({'type': 'message', 'success': success, 'message': message})
        
        # DROP DATABASE - ADDED
        elif query_upper.startswith('DROP DATABASE'):
            success, message = db.execute_drop_database(query_clean)
            return jsonify({'type': 'message', 'success': success, 'message': message})
        
        # DROP VIEW - ADDED
        elif query_upper.startswith('DROP VIEW'):
            parts = query_clean.split()
            if len(parts) >= 3:
                view_name = parts[2]
                success, message = db.execute_drop_view(view_name)
                return jsonify({'type': 'message', 'success': success, 'message': message})
            else:
                return jsonify({'type': 'error', 'message': 'Invalid DROP VIEW syntax'})
        
        # DROP TRIGGER - ADDED
        elif query_upper.startswith('DROP TRIGGER'):
            parts = query_clean.split()
            if len(parts) >= 3:
                trigger_name = parts[2]
                success, message = db.execute_drop_trigger(trigger_name)
                return jsonify({'type': 'message', 'success': success, 'message': message})
            else:
                return jsonify({'type': 'error', 'message': 'Invalid DROP TRIGGER syntax'})
        
        elif query_upper.startswith('DESCRIBE'):
            parts = query_clean.split()
            if len(parts) >= 2:
                table_name = parts[1]
                # Get schema info
                schema = db.schema_manager.get_table_schema(table_name)
                if schema:
                    columns = [{'name': col['name'], 'type': col['type']} for col in schema['columns']]
                    return jsonify({'type': 'schema', 'table': table_name, 'columns': columns})
                else:
                    # Check if it's a view
                    view_query = db.schema_manager.get_view(table_name)
                    if view_query:
                        return jsonify({'type': 'message', 'success': True, 'message': f'View: {table_name} exists'})
                    else:
                        return jsonify({'type': 'message', 'success': False, 'message': f'Table/View {table_name} not found'})
        
        elif query_upper.startswith('INSERT INTO'):
            success, message = db.execute_insert(query_clean)
            return jsonify({'type': 'message', 'success': success, 'message': message})
        
        elif query_upper.startswith('DELETE FROM'):
            success, message = db.execute_delete(query_clean)
            return jsonify({'type': 'message', 'success': success, 'message': message})
        
        elif query_upper.startswith('UPDATE'):
            success, message = db.execute_update(query_clean)
            return jsonify({'type': 'message', 'success': success, 'message': message})
        
        elif query_upper.startswith('SELECT'):
            result, success, message = db.execute_select(query_clean)
            
            if not success:
                return jsonify({'type': 'error', 'message': message})
            
            # Convert result to list of dicts
            if result and isinstance(result, list):
                if isinstance(result[0], dict):
                    return jsonify({'type': 'select', 'rows': result, 'count': len(result)})
                else:
                    return jsonify({'type': 'select', 'rows': [{'value': r} for r in result], 'count': len(result)})
            elif isinstance(result, (int, float)):
                return jsonify({'type': 'value', 'value': result})
            else:
                return jsonify({'type': 'select', 'rows': [], 'count': 0})
        
        else:
            return jsonify({'type': 'error', 'message': f'Unknown command: {query}'})
    
    except Exception as e:
        return jsonify({'type': 'error', 'message': str(e)})

@app.route('/api/databases', methods=['GET'])
def get_databases():
    """Get list of databases"""
    databases = db.list_databases()
    current_db = db.get_current_db()
    return jsonify({'databases': databases, 'current_db': current_db})

@app.route('/api/tables', methods=['GET'])
def get_tables():
    """Get list of tables in current database"""
    current_db = db.get_current_db()
    if not current_db:
        return jsonify({'tables': [], 'current_db': None})
    tables = db.show_tables()
    
    triggers = []
    views = []
    if db.schema_manager.metadata:
        triggers = db.schema_manager.metadata.get_all_triggers()
        views = list(db.schema_manager.metadata.get_views().keys())
        
    return jsonify({'tables': tables, 'triggers': triggers, 'views': views, 'current_db': current_db})

if __name__ == '__main__':
    app.run(debug=True, port=5000)