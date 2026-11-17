"""探查甲方标注表的结构：表头行、说明行、列索引、有效行数。"""
from pathlib import Path
import json
import openpyxl

SRC = Path("/Users/lixin/WorkBuddy/2026-10-24-20-33-54/refs/20260608影片片段标注.xlsx")


def main() -> None:
    wb = openpyxl.load_workbook(SRC, read_only=True, data_only=True)
    print("sheets:", wb.sheetnames)

    ws = wb["评测表"]
    print(f"\n评测表 dims: {ws.max_row} x {ws.max_column}")

    rows = []
    for i, row in enumerate(ws.iter_rows(min_row=1, max_row=6, values_only=True), start=1):
        rows.append(row)
        print(f"\n--- row {i} ---")
        for j, v in enumerate(row):
            if v is not None and str(v).strip():
                col = openpyxl.utils.get_column_letter(j + 1)
                s = str(v).replace("\n", " ")
                print(f"  {col:>3}({j:>2}) = {s[:110]}")

    # 统计有效行
    n_valid = 0
    n_empty = 0
    for row in ws.iter_rows(min_row=3, values_only=True):
        if all(v is None or str(v).strip() == "" for v in row):
            n_empty += 1
        else:
            n_valid += 1
    print(f"\n数据行：有效 {n_valid}，整行空 {n_empty}")

    wb.close()


if __name__ == "__main__":
    main()
