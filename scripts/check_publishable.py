"""Сколько карточек реально можно опубликовать прямо сейчас.

Считает по цепочке: APPROVED-товар → есть уникализированное фото →
собранный Listing. Ничего не меняет, только читает.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "data" / "avito_dvijenia.db"


def main() -> None:
    con = sqlite3.connect(DB)

    approved = con.execute("select count(*) from product where status = 'APPROVED'").fetchone()[0]

    with_photo = con.execute("""
        select count(distinct p.id)
        from product p
        join mediaasset m on m.supplier_item_id = p.supplier_item_id
        where p.status = 'APPROVED' and m.kind = 'VARIATE'
    """).fetchone()[0]

    listings = con.execute("""
        select count(*)
        from listing l
        join product p on p.id = l.product_id
        where p.status = 'APPROVED'
    """).fetchone()[0]

    print(f"APPROVED-товаров:                {approved}")
    print(f"из них с уникализированным фото: {with_photo}")
    print(f"собранных Listing на них:        {listings}")
    print()
    print("Товары, готовые к публикации:")
    for row in con.execute("""
        select p.id, p.title, count(distinct l.id)
        from product p
        join mediaasset m on m.supplier_item_id = p.supplier_item_id and m.kind = 'VARIATE'
        join listing l on l.product_id = p.id
        where p.status = 'APPROVED'
        group by p.id
        order by p.id
    """):
        print(f"  #{row[0]:>3}  {row[1][:45]:<45}  гео-копий: {row[2]}")


if __name__ == "__main__":
    main()
