"""Что лежит в SupplierItem: источники, ссылки на посты, наличие фото.

Нужно, чтобы понять, по какому ключу привязывать выгруженные из Telegram
фото к товарам. Только читает.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "data" / "avito_dvijenia.db"


def main() -> None:
    con = sqlite3.connect(DB)

    print("колонки supplieritem:")
    cols = [r[1] for r in con.execute("pragma table_info(supplieritem)")]
    print("   ", ", ".join(cols))

    print("\nпо источникам (ключ до первого ':'):")
    for row in con.execute("""
        select substr(source_key, 1, instr(source_key, ':') - 1) as src,
               count(*),
               sum(case when post_url is not null and post_url != '' then 1 else 0 end),
               sum(case when photo_urls != '' then 1 else 0 end)
        from supplieritem group by 1
    """):
        print(f"    {row[0]}: всего {row[1]}, со ссылкой на пост {row[2]}, с фото {row[3]}")

    print("\nпримеры (source_key | post_url | raw_title):")
    for row in con.execute(
        "select source_key, post_url, raw_title from supplieritem order by id limit 15"
    ):
        print(f"    {str(row[0])[:34]:<34} {str(row[1])[:40]:<40} {row[2][:36]}")


if __name__ == "__main__":
    main()
