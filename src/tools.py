import statistics
from datetime import datetime, timedelta

from db import connect


def search_similar(category, keywords):
    """Devuelve los productos de una categoría cuyo nombre contiene al menos una de las keywords.

    Si keywords está vacía, devuelve todos los productos de la categoría.
    """
    query = "SELECT * FROM products WHERE category = ?"
    values = [category]

    if keywords:
        keyword_conditions = " OR ".join(["name LIKE ?"] * len(keywords))
        query += f" AND ({keyword_conditions})"
        values += [f"%{keyword}%" for keyword in keywords]

    connection = connect()
    cursor = connection.cursor()
    cursor.execute(query, values)
    rows = cursor.fetchall()
    products = [dict(row) for row in rows]
    connection.close()

    return products


def price_stats(products):
    """Devuelve la cantidad, el mínimo, el máximo y la mediana de los precios finales.

    Devuelve None si la lista está vacía.
    """
    if not products:
        return None

    prices = [product["final_price"] for product in products]

    return {
        "count": len(prices),
        "min_price": min(prices),
        "max_price": max(prices),
        "median_price": round(statistics.median(prices)),
    }


def save_auction(draft, product, now=None):
    created_at = now or datetime.now()
    ends_at = created_at + timedelta(days=draft["duration_days"])

    connection = connect()
    cursor = connection.cursor()
    cursor.execute(
        """
        INSERT INTO auctions (title, description, category, product_name, condition,
                              starting_price, duration_days, created_at, ends_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            draft["title"],
            draft["description"],
            draft["category"],
            product["name"],
            product.get("condition"),
            draft["starting_price"],
            draft["duration_days"],
            created_at.isoformat(timespec="seconds"),
            ends_at.isoformat(timespec="seconds"),
        ),
    )
    connection.commit()
    auction_id = cursor.lastrowid
    connection.close()

    return auction_id


def list_active_auctions(category=None):
    query = "SELECT * FROM auctions WHERE ends_at > ?"
    values = [datetime.now().isoformat(timespec="seconds")]

    if category:
        query += " AND category = ?"
        values.append(category)

    query += " ORDER BY ends_at"

    connection = connect()
    rows = connection.execute(query, values).fetchall()
    auctions = [dict(row) for row in rows]
    connection.close()

    return auctions
