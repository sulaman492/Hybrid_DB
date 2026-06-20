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

import re

def split_sql_queries(sql_script):
    queries = []
    current_query = []
    in_single_quote = False
    in_double_quote = False
    
    i = 0
    while i < len(sql_script):
        char = sql_script[i]
        
        if char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
        elif char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
            
        current_query.append(char)
        
        if char == ';' and not in_single_quote and not in_double_quote:
            qs = "".join(current_query).strip().upper()
            if qs.startswith("CREATE TRIGGER"):
                if re.search(r'\bEND\s*;$', qs):
                    queries.append("".join(current_query).strip())
                    current_query = []
            else:
                queries.append("".join(current_query).strip())
                current_query = []
                
        i += 1
        
    if current_query and "".join(current_query).strip():
        queries.append("".join(current_query).strip())
        
    return [q for q in queries if q]

@app.route('/api/execute', methods=['POST'])
def execute_query():
    """Execute SQL query and return results"""
    data = request.get_json()
    raw_query = data.get('query', '').strip()
    
    if not raw_query:
        return jsonify({'error': 'No query provided'})
    
    queries = split_sql_queries(raw_query)
    results = []
    
    for query in queries:
        try:
        # Remove trailing semicolon
            # Remove whitespace and trailing semicolon
            query_clean = query.strip().rstrip(';')
            query_upper = query_clean.upper()
            
            # Handle different query types
            if query_upper == 'BEGIN' or query_upper == 'BEGIN TRANSACTION':
                success, message = db.execute_begin()
                results.append({'type': 'message', 'success': success, 'message': message})
                
            elif query_upper == 'COMMIT':
                success, message = db.execute_commit()
                results.append({'type': 'message', 'success': success, 'message': message})
                
            elif query_upper == 'ROLLBACK':
                success, message = db.execute_rollback()
                results.append({'type': 'message', 'success': success, 'message': message})
                
            elif query_upper.startswith('CREATE DATABASE'):
                success, message = db.execute_create_database(query_clean)
                results.append({'type': 'message', 'success': success, 'message': message})
            
            elif query_upper.startswith('USE DATABASE'):
                parts = query_clean.split()
                if len(parts) >= 3:
                    db_name = parts[2]
                    success, message = db.use_database(db_name)
                    results.append({'type': 'message', 'success': success, 'message': message})
            
            elif query_upper == 'SHOW DATABASES':
                databases = db.list_databases()
                current_db = db.get_current_db()
                results.append({'type': 'databases', 'databases': databases, 'current_db': current_db})
            
            elif query_upper == 'SHOW TABLES':
                tables = db.show_tables()
                current_db = db.get_current_db()
                results.append({'type': 'tables', 'tables': tables, 'current_db': current_db})
            
            elif query_upper.startswith('CREATE TABLE'):
                success, message = db.execute_create_table(query_clean)
                results.append({'type': 'message', 'success': success, 'message': message})
                
            elif query_upper.startswith('CREATE VIEW'):
                success, message = db.execute_create_view(query_clean)
                results.append({'type': 'message', 'success': success, 'message': message})
                
            elif query_upper.startswith('CREATE TRIGGER'):
                success, message = db.execute_create_trigger(query_clean)
                results.append({'type': 'message', 'success': success, 'message': message})
            
            elif query_upper.startswith('DROP TABLE') or query_upper.startswith('DELETE TABLE'):
                success, message = db.execute_drop_table(query_clean)
                results.append({'type': 'message', 'success': success, 'message': message})
            
            elif query_upper.startswith('DROP DATABASE') or query_upper.startswith('DELETE DATABASE'):
                success, message = db.execute_drop_database(query_clean)
                results.append({'type': 'message', 'success': success, 'message': message})
            
            elif query_upper.startswith('DROP VIEW'):
                parts = query_clean.split()
                if len(parts) >= 3:
                    view_name = parts[2]
                    success, message = db.execute_drop_view(view_name)
                    results.append({'type': 'message', 'success': success, 'message': message})
                else:
                    results.append({'type': 'error', 'message': 'Invalid DROP VIEW syntax'})
            
            elif query_upper.startswith('DROP TRIGGER'):
                parts = query_clean.split()
                if len(parts) >= 3:
                    trigger_name = parts[2]
                    success, message = db.execute_drop_trigger(trigger_name)
                    results.append({'type': 'message', 'success': success, 'message': message})
                else:
                    results.append({'type': 'error', 'message': 'Invalid DROP TRIGGER syntax'})
            
            elif query_upper.startswith('DESCRIBE'):
                parts = query_clean.split()
                if len(parts) >= 2:
                    table_name = parts[1]
                    schema = db.schema_manager.get_table_schema(table_name)
                    if schema:
                        columns = [{'name': col['name'], 'type': col['type']} for col in schema['columns']]
                        results.append({'type': 'schema', 'table': table_name, 'columns': columns})
                    else:
                        view_query = db.schema_manager.get_view(table_name)
                        if view_query:
                            results.append({'type': 'message', 'success': True, 'message': f'View: {table_name} exists'})
                        else:
                            results.append({'type': 'message', 'success': False, 'message': f'Table/View {table_name} not found'})
            
            elif query_upper.startswith('INSERT INTO'):
                success, message = db.execute_insert(query_clean)
                results.append({'type': 'message', 'success': success, 'message': message})
            
            elif query_upper.startswith('DELETE FROM'):
                success, message = db.execute_delete(query_clean)
                results.append({'type': 'message', 'success': success, 'message': message})
                
            elif query_upper.startswith('UPDATE'):
                success, message = db.execute_update(query_clean)
                results.append({'type': 'message', 'success': success, 'message': message})
                
            elif query_upper.startswith('SELECT'):
                # Parse first to detect aggregation
                parsed = db.parser.parse_select(query_clean)
                current_db_name = db.get_current_db()
                benchmark = None
                
                if parsed and parsed.get("type") == "aggregation" and current_db_name:
                    try:
                        benchmark = db.benchmark_aggregation(parsed, current_db_name)
                    except Exception:
                        benchmark = None
                
                result, success, message = db.execute_select(query_clean)
                
                if not success:
                    results.append({'type': 'error', 'message': message})
                else:
                    entry = {}
                    if result and isinstance(result, list):
                        if isinstance(result[0], dict):
                            entry = {'type': 'select', 'rows': result, 'count': len(result)}
                        else:
                            entry = {'type': 'select', 'rows': [{'value': r} for r in result], 'count': len(result)}
                    elif isinstance(result, (int, float)):
                        entry = {'type': 'value', 'value': result}
                    else:
                        entry = {'type': 'select', 'rows': [], 'count': 0}
                    
                    if benchmark:
                        entry['benchmark'] = benchmark
                    results.append(entry)
            
            else:
                results.append({'type': 'error', 'message': f'Unknown command: {query}'})
    
        except Exception as e:
            results.append({'type': 'error', 'message': str(e)})
            
        # Auto-rollback on failure if in transaction
        if getattr(db, 'in_transaction', False) and results:
            last_res = results[-1]
            failed = (last_res.get('type') == 'error') or (last_res.get('success') is False)
            if failed:
                db.execute_rollback()
                results.append({'type': 'error', 'message': 'Transaction automatically rolled back due to failure.'})
                break

    return jsonify({'type': 'multi', 'results': results})

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