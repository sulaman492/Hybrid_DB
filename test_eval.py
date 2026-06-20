from src.query_parser import QueryParser
qp = QueryParser()
print('attendance BETWEEN 0 AND 100:', qp.evaluate_where({'attendance': 95}, 'attendance BETWEEN 0 AND 100'))
print('grade IN:', qp.evaluate_where({'grade': 'A'}, "grade IN ('A', 'B', 'C', 'D', 'F', 'W')"))
