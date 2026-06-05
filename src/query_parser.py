import re

class QueryParser:
    @staticmethod
    def parse_insert(query):
        """Parse INSERT INTO query"""
        pattern = r"INSERT INTO (\w+)\s*VALUES\s*\((.*)\)\s*;?"
        match = re.match(pattern, query, re.IGNORECASE)
        
        if not match:
            return None, None
        
        table_name = match.group(1)
        values_str = match.group(2)
        
        values = []
        for val in values_str.split(','):
            val = val.strip()
            if val.upper() == "NULL":
                values.append(None)
            else:
                val = val.strip("'\"")
                try:
                    val = int(val)
                except:
                    try:
                        val = float(val)
                    except:
                        pass
                values.append(val)
        
        return table_name, values
    
    @staticmethod
    def parse_select(query):
        """Parse SELECT query including WHERE, JOIN, DISTINCT, GROUP BY, ORDER BY, LIMIT"""
        query_clean = query.strip()
        if query_clean.endswith(';'):
            query_clean = query_clean[:-1].strip()

        limit = None
        limit_match = re.search(r'\s+LIMIT\s+(\d+)$', query_clean, re.IGNORECASE)
        if limit_match:
            limit = int(limit_match.group(1))
            query_clean = query_clean[:limit_match.start()].strip()

        order_by = None
        order_desc = False
        order_match = re.search(r'\s+ORDER\s+BY\s+([\w.]+)(?:\s+(ASC|DESC))?$', query_clean, re.IGNORECASE)
        if order_match:
            order_by = order_match.group(1)
            order_desc = (order_match.group(2) and order_match.group(2).upper() == 'DESC')
            query_clean = query_clean[:order_match.start()].strip()

        having = None
        having_match = re.search(r'\s+HAVING\s+(.+)$', query_clean, re.IGNORECASE)
        if having_match:
            having = having_match.group(1).strip()
            query_clean = query_clean[:having_match.start()].strip()

        group_by = None
        group_match = re.search(r'\s+GROUP\s+BY\s+([\w.]+)$', query_clean, re.IGNORECASE)
        if group_match:
            group_by = group_match.group(1)
            query_clean = query_clean[:group_match.start()].strip()
            
        # Add semicolon back for regexes that expect it
        query_clean += ";"
        
        query_upper = query_clean.upper()
        
        # Check for DISTINCT
        is_distinct = "SELECT DISTINCT" in query_upper
        
        # Pattern for SELECT with JOIN
        # SELECT * FROM table1 JOIN table2 ON table1.col = table2.col WHERE condition
        join_pattern = r"SELECT\s+(DISTINCT\s+)?(\*|\w+)\s+FROM\s+(\w+)\s+(INNER|LEFT)\s+JOIN\s+(\w+)\s+ON\s+(\w+)\.(\w+)\s*=\s*(\w+)\.(\w+)(?:\s+WHERE\s+(.+))?\s*;?"
        join_match = re.match(join_pattern, query_clean, re.IGNORECASE)
        
        if join_match:
            distinct_flag = join_match.group(1) is not None
            select_col = join_match.group(2)
            table1 = join_match.group(3)
            join_type = join_match.group(4).upper()
            table2 = join_match.group(5)
            # FIX: Swap t1_table and t1_col to correctly match regex groups
            t1_table = join_match.group(6)
            t1_col = join_match.group(7)
            t2_table = join_match.group(8)
            t2_col = join_match.group(9)
            where_condition = join_match.group(10) if join_match.group(10) else None
            
            return {
                "type": "join",
                "distinct": distinct_flag,
                "select_col": select_col,
                "table1": table1,
                "table2": table2,
                "join_type": join_type,
                "on_condition": {
                    "left": (t1_table, t1_col),
                    "right": (t2_table, t2_col)
                },
                "where": where_condition,
                "having": having,
                "group_by": group_by,
                "order_by": order_by,
                "order_desc": order_desc,
                "limit": limit
            }
        
        # Pattern for regular SELECT with WHERE — supports multi-column: SELECT col1, col2 FROM t
        reg_pattern = r"SELECT\s+(DISTINCT\s+)?(\*|(?:\w+)(?:\s*,\s*\w+)*)\s+FROM\s+(\w+)(?:\s+WHERE\s+(.+?))?\s*;?\s*$"
        reg_match = re.match(reg_pattern, query_clean, re.IGNORECASE)
        
        if reg_match:
            distinct_flag = reg_match.group(1) is not None
            select_col_raw = reg_match.group(2).strip()
            table_name = reg_match.group(3)
            where_condition = reg_match.group(4).strip() if reg_match.group(4) else None
            
            # Parse columns: "*", single string, or list for multi-column
            if select_col_raw == "*":
                select_col = "*"
            elif "," in select_col_raw:
                select_col = [c.strip() for c in select_col_raw.split(",")]
            else:
                select_col = select_col_raw
            
            return {
                "type": "simple",
                "distinct": distinct_flag,
                "select_col": select_col,
                "table_name": table_name,
                "where": where_condition,
                "having": having,
                "group_by": group_by,
                "order_by": order_by,
                "order_desc": order_desc,
                "limit": limit
            }
        
        # Aggregation patterns — now supports optional WHERE clause and optional group column
        agg_pattern = r"SELECT\s+(?:([\w.]+)\s*,\s*)?(AVG|SUM|COUNT|MAX|MIN)\s*\(\s*(\w+|\*)\s*\)\s+FROM\s+(\w+)(?:\s+WHERE\s+(.+?))?\s*;?\s*$"
        agg_match = re.match(agg_pattern, query_clean, re.IGNORECASE)
        if agg_match:
            return {
                "type": "aggregation",
                "group_select_col": agg_match.group(1),
                "agg_func": agg_match.group(2).upper(),
                "agg_col": agg_match.group(3),
                "table_name": agg_match.group(4),
                "where": agg_match.group(5).strip() if agg_match.group(5) else None,
                "having": having,
                "group_by": group_by,
                "order_by": order_by,
                "order_desc": order_desc,
                "limit": limit
            }
        
        return None
    
    @staticmethod
    def parse_delete(query):
        """Parse DELETE FROM table (with or without WHERE)"""
        pattern = r"DELETE\s+FROM\s+(\w+)(?:\s+WHERE\s+(.+))?\s*;?"
        match = re.match(pattern, query, re.IGNORECASE)
        
        if not match:
            return None, None
        
        table_name = match.group(1)
        where_condition = match.group(2) if match.group(2) else None
        
        return table_name, where_condition
    @staticmethod
    def parse_update(query):
        """Parse UPDATE table SET column = value WHERE condition"""
        # Try with WHERE clause first
        pattern_with_where = r"UPDATE\s+(\w+)\s+SET\s+(\w+)\s*=\s*(.+?)\s+WHERE\s+(.+?)\s*;?\s*$"
        match = re.match(pattern_with_where, query, re.IGNORECASE)
        
        if match:
            table_name = match.group(1)
            set_column = match.group(2)
            set_value = match.group(3).strip().strip("'\"")
            where_condition = match.group(4).strip()
        else:
            # No WHERE clause — update all rows
            pattern_no_where = r"UPDATE\s+(\w+)\s+SET\s+(\w+)\s*=\s*(.+?)\s*;?\s*$"
            match = re.match(pattern_no_where, query, re.IGNORECASE)
            
            if not match:
                return None, None, None, None
            
            table_name = match.group(1)
            set_column = match.group(2)
            set_value = match.group(3).strip().strip("'\"")
            where_condition = None
        
        # Convert value to appropriate type
        try:
            set_value = int(set_value)
        except:
            try:
                set_value = float(set_value)
            except:
                pass
            
        return table_name, set_column, set_value, where_condition
    @staticmethod
    def evaluate_where(row, condition):
        """Evaluate WHERE condition on a row"""
        if not condition:
            return True
        
        # Handle AND conditions
        if " AND " in condition.upper():
            parts = re.split(r'\s+AND\s+', condition, flags=re.IGNORECASE)
            for part in parts:
                if not QueryParser._evaluate_single_condition(row, part):
                    return False
            return True
        
        # Handle OR conditions
        if " OR " in condition.upper():
            parts = re.split(r'\s+OR\s+', condition, flags=re.IGNORECASE)
            for part in parts:
                if QueryParser._evaluate_single_condition(row, part):
                    return True
            return False
        
        # Single condition
        return QueryParser._evaluate_single_condition(row, condition)
    
    @staticmethod
    def _evaluate_single_condition(row, condition):
        """Evaluate a single condition"""
        # Handle IN operator
        if " IN " in condition.upper():
            match = re.match(r'(\w+)\s+IN\s+\((.*?)\)', condition, re.IGNORECASE)
            if match:
                col = match.group(1)
                values_str = match.group(2)
                values = [v.strip().strip("'\"") for v in values_str.split(',')]
                
                # Convert values to appropriate types
                converted_values = []
                for v in values:
                    try:
                        converted_values.append(int(v))
                    except:
                        try:
                            converted_values.append(float(v))
                        except:
                            converted_values.append(v)
                
                row_val = row.get(col)
                return row_val in converted_values
            return False
        
        # Handle BETWEEN operator
        if " BETWEEN " in condition.upper():
            match = re.match(r'(\w+)\s+BETWEEN\s+([^\s]+)\s+AND\s+([^\s]+)', condition, re.IGNORECASE)
            if match:
                col = match.group(1)
                low = match.group(2)
                high = match.group(3)
                
                try:
                    low = int(low)
                    high = int(high)
                except:
                    try:
                        low = float(low)
                        high = float(high)
                    except:
                        pass
                
                row_val = row.get(col)
                return low <= row_val <= high
            return False
        
        # Handle LIKE operator (basic)
        if " LIKE " in condition.upper():
            match = re.match(r'(\w+)\s+LIKE\s+\'(.+?)\'', condition, re.IGNORECASE)
            if match:
                col = match.group(1)
                pattern = match.group(2)
                row_val = str(row.get(col, ''))
                
                # Convert SQL LIKE pattern to regex
                regex_pattern = pattern.replace('%', '.*').replace('_', '.')
                import re as regex
                return regex.match(regex_pattern, row_val) is not None
            return False
        
        # Standard comparison operators (using regex for precise matching)
        match = re.match(r"^\s*([\w.]+)\s*(>=|<=|!=|=|>|<)\s*(.+?)\s*$", condition)
        if match:
            col = match.group(1)
            op = match.group(2)
            val = match.group(3).strip().strip("'\"")
            
            # Convert value to appropriate type
            try:
                val = int(val)
            except:
                try:
                    val = float(val)
                except:
                    pass
            
            row_val = row.get(col)
            
            try:
                if op == '=': return row_val == val
                elif op == '>': return row_val > val
                elif op == '<': return row_val < val
                elif op == '>=': return row_val >= val
                elif op == '<=': return row_val <= val
                elif op == '!=': return row_val != val
            except TypeError:
                return False
        
        return True

    @staticmethod
    def evaluate_having(row, condition):
        """Evaluate HAVING condition on an aggregated row.
        
        Unlike WHERE, HAVING conditions reference aggregate columns
        like COUNT(*), SUM(salary), etc. These are stored as keys in
        the aggregated result dict.
        """
        if not condition:
            return True
        
        # Handle AND conditions
        if " AND " in condition.upper():
            parts = re.split(r'\s+AND\s+', condition, flags=re.IGNORECASE)
            return all(QueryParser._evaluate_having_single(row, p) for p in parts)
        
        # Handle OR conditions
        if " OR " in condition.upper():
            parts = re.split(r'\s+OR\s+', condition, flags=re.IGNORECASE)
            return any(QueryParser._evaluate_having_single(row, p) for p in parts)
        
        return QueryParser._evaluate_having_single(row, condition)

    @staticmethod
    def _evaluate_having_single(row, condition):
        """Evaluate a single HAVING condition.
        
        Supports patterns like:
          COUNT(*) > 5
          AVG(salary) >= 50000
          SUM(amount) != 0
        """
        # Pattern: AGG_FUNC(col) operator value
        match = re.match(
            r'\s*((?:COUNT|SUM|AVG|MAX|MIN)\s*\(\s*[\w*]+\s*\))\s*(>=|<=|!=|=|>|<)\s*(.+?)\s*$',
            condition, re.IGNORECASE
        )
        if match:
            # Normalize aggregate expression: "COUNT( * )" → "COUNT(*)"
            agg_expr = match.group(1).upper()
            agg_expr = re.sub(r'\s*\(\s*', '(', agg_expr)
            agg_expr = re.sub(r'\s*\)\s*', ')', agg_expr)
            op = match.group(2)
            val = match.group(3).strip().strip("'\"")
            
            try:
                val = int(val)
            except ValueError:
                try:
                    val = float(val)
                except ValueError:
                    pass
            
            # Find matching key in row (normalize both sides)
            row_val = None
            for key in row:
                normalized_key = key.upper()
                normalized_key = re.sub(r'\s*\(\s*', '(', normalized_key)
                normalized_key = re.sub(r'\s*\)\s*', ')', normalized_key)
                if normalized_key == agg_expr:
                    row_val = row[key]
                    break
            
            if row_val is None:
                return False
            
            try:
                if op == '=':  return row_val == val
                elif op == '>':  return row_val > val
                elif op == '<':  return row_val < val
                elif op == '>=': return row_val >= val
                elif op == '<=': return row_val <= val
                elif op == '!=': return row_val != val
            except TypeError:
                return False
        
        return False

    @staticmethod
    def parse_create_view(query):
        """Parse CREATE VIEW query"""
        pattern = r"CREATE\s+VIEW\s+(\w+)\s+AS\s+(.+)\s*;?"
        match = re.match(pattern, query, re.IGNORECASE | re.DOTALL)
        
        if not match:
            return None, None
            
        view_name = match.group(1)
        select_query = match.group(2).strip()
        if select_query.endswith(';'):
            select_query = select_query[:-1].strip()
            
        return view_name, select_query

    @staticmethod
    def parse_create_trigger(query):
        """Parse CREATE TRIGGER query
        Example: CREATE TRIGGER trigger_name BEFORE INSERT ON table_name BEGIN query END
        """
        pattern = r"CREATE\s+TRIGGER\s+(\w+)\s+(BEFORE|AFTER)\s+(INSERT|UPDATE|DELETE)\s+ON\s+(\w+)\s+BEGIN\s+(.+?)\s+END\s*;?"
        match = re.match(pattern, query, re.IGNORECASE | re.DOTALL)
        
        if not match:
            return None
            
        return {
            "name": match.group(1),
            "event": match.group(2).upper(),
            "action": match.group(3).upper(),
            "table": match.group(4),
            "query": match.group(5).strip()
        }