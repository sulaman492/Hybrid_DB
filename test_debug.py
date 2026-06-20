import re

def test_between():
    condition = 'attendance BETWEEN 0 AND 100'
    row = {'attendance': 95}
    match = re.match(r'(\w+)\s+BETWEEN\s+([^\s]+)\s+AND\s+([^\s]+)', condition, re.IGNORECASE)
    if match:
        col = match.group(1)
        low = match.group(2)
        high = match.group(3)
        print(f"Col: {col}, Low: {low}, High: {high}")
        try:
            low = int(low)
            high = int(high)
        except Exception as e:
            print("Int conversion failed:", e)
        row_val = row.get(col)
        print(f"Row val: {row_val}, Type: {type(row_val)}")
        print(f"Low: {low}, Type: {type(low)}")
        print(f"High: {high}, Type: {type(high)}")
        print("Result:", low <= row_val <= high)

test_between()
