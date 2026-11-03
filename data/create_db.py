"""Crea la base de datos SQLite con subastas finalizadas que sirven como referencia de precios.

El Analista usa estos datos para estimar precios comparando productos similares.
Los productos y precios son ficticios (en pesos argentinos), armados solo para el TP.

Uso:
    python data/create_db.py

Si la base ya existe, la borra y la vuelve a crear desde cero.
"""

import sqlite3
from pathlib import Path

# La base se crea en la misma carpeta que este script, sin importar desde dónde se ejecute.
DB_PATH = Path(__file__).parent / "products.db"

# "other" no tiene productos cargados: es la categoría para lo que no encaja en ninguna
# de las demás (ej. un juego de mesa). El Analista no va a encontrar similares y el flujo
# sigue el camino de "sin datos" definido en docs/diagrama.md.
CATEGORIES = ["consoles", "phones", "laptops", "tvs", "bicycles", "other"]

CONDITIONS = ["new", "used", "refurbished"]

# Cada tupla es una fila: (name, category, description, condition, final_price, date)
PRODUCTS = [
    # Consolas
    ("PlayStation 5 Standard", "consoles", "Incluye 1 joystick. Funciona perfecto.", "used", 420000, "2026-08-14"),
    ("PlayStation 5 Standard", "consoles", "Con caja original y todos los cables.", "used", 480000, "2026-09-02"),
    ("PlayStation 5 Standard", "consoles", "Incluye 2 joysticks y 3 juegos físicos.", "used", 520000, "2026-09-20"),
    ("PlayStation 5 Standard", "consoles", "Tiene rayones en la carcasa, funciona bien.", "used", 380000, "2026-07-30"),
    ("PlayStation 5 Standard", "consoles", "Poco uso, 1 joystick.", "used", 450000, "2026-10-05"),
    ("PlayStation 5 Digital", "consoles", "Versión sin lectora de discos. 1 joystick.", "used", 350000, "2026-08-22"),
    ("Nintendo Switch OLED", "consoles", "Con dock y joycons originales.", "used", 330000, "2026-09-11"),
    ("Nintendo Switch OLED", "consoles", "Sellada en caja.", "new", 480000, "2026-10-01"),
    ("Nintendo Switch Lite", "consoles", "Color turquesa, con cargador.", "used", 190000, "2026-08-03"),
    ("Xbox Series S", "consoles", "512 GB, 1 joystick.", "used", 290000, "2026-09-25"),
    # Celulares
    ("iPhone 13 128GB", "phones", "Batería al 88%. Con funda.", "used", 550000, "2026-09-08"),
    ("iPhone 13 128GB", "phones", "Batería al 82%, pantalla sin marcas.", "used", 500000, "2026-08-19"),
    ("iPhone 14 128GB", "phones", "Batería al 91%. Con caja.", "used", 700000, "2026-09-29"),
    ("Samsung Galaxy S23 256GB", "phones", "Excelente estado, con cargador.", "used", 600000, "2026-08-27"),
    ("Samsung Galaxy A54 128GB", "phones", "Pantalla con un detalle mínimo.", "used", 280000, "2026-07-21"),
    ("Samsung Galaxy A54 128GB", "phones", "Sellado, con garantía oficial.", "new", 420000, "2026-09-15"),
    ("Motorola Moto G84 256GB", "phones", "Funciona perfecto, con funda y vidrio templado.", "used", 200000, "2026-10-03"),
    ("Xiaomi Redmi Note 13 256GB", "phones", "Sellado en caja.", "new", 300000, "2026-09-18"),
    # Notebooks
    ("MacBook Air M1 8GB 256GB", "laptops", "Ciclos de batería: 210. Con cargador original.", "used", 750000, "2026-09-10"),
    ("MacBook Air M1 8GB 256GB", "laptops", "Tiene un golpe en una esquina, funciona perfecto.", "used", 700000, "2026-08-08"),
    ("MacBook Air M2 8GB 256GB", "laptops", "Como nueva, con caja.", "used", 1000000, "2026-09-27"),
    ("Lenovo IdeaPad 3 i5 8GB", "laptops", "SSD 512 GB, Windows 11.", "used", 450000, "2026-08-30"),
    ("Lenovo IdeaPad 3 Ryzen 5 8GB", "laptops", "Reacondicionada con garantía de 3 meses.", "refurbished", 480000, "2026-09-22"),
    ("HP 15 i3 8GB", "laptops", "SSD 256 GB. Batería dura unas 3 horas.", "used", 320000, "2026-07-28"),
    ("Dell Inspiron 15 i7 16GB", "laptops", "SSD 512 GB, ideal para trabajo.", "used", 650000, "2026-09-05"),
    ("Asus TUF Gaming F15 RTX 3050", "laptops", "i5 16 GB, SSD 512 GB. Para juegos.", "used", 900000, "2026-10-07"),
    # Televisores
    ("Samsung 50 pulgadas 4K Crystal UHD", "tvs", "Smart TV con control remoto original.", "used", 350000, "2026-08-16"),
    ("Samsung 55 pulgadas 4K Crystal UHD", "tvs", "Smart TV, sin pie (se usaba colgado).", "used", 420000, "2026-09-12"),
    ("LG 43 pulgadas Full HD", "tvs", "Smart TV webOS.", "used", 230000, "2026-07-25"),
    ("LG 55 pulgadas OLED C1", "tvs", "Imagen perfecta, sin pixeles quemados.", "used", 900000, "2026-09-30"),
    ("TCL 50 pulgadas 4K Google TV", "tvs", "Sellado en caja.", "new", 450000, "2026-10-02"),
    ("Philips 32 pulgadas HD", "tvs", "Smart TV, ideal para dormitorio.", "used", 140000, "2026-08-11"),
    ("Noblex 43 pulgadas Full HD", "tvs", "Smart TV Android, con control remoto.", "used", 180000, "2026-09-03"),
    # Bicicletas
    ("Mountain bike Venzo Raptor rodado 29", "bicycles", "Cambios Shimano 21 velocidades, frenos a disco.", "used", 420000, "2026-09-14"),
    ("Mountain bike Venzo Loki rodado 29", "bicycles", "Frenos a disco mecánicos, cubiertas nuevas.", "used", 380000, "2026-08-24"),
    ("Mountain bike Topmega rodado 29", "bicycles", "Cuadro de aluminio, 21 velocidades.", "used", 250000, "2026-07-19"),
    ("Bicicleta de ruta Specialized Allez", "bicycles", "Talle 54, grupo Shimano Claris.", "used", 1100000, "2026-09-21"),
    ("Bicicleta plegable Fire Bird rodado 20", "bicycles", "Ideal para combinar con transporte público.", "used", 150000, "2026-08-06"),
    ("Bicicleta urbana Olmo rodado 26", "bicycles", "Con canasto y portaequipaje.", "new", 320000, "2026-10-04"),
    ("BMX Raleigh rodado 20", "bicycles", "Con pegs, poco uso.", "used", 180000, "2026-09-09"),
]


def create_db():
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()

    # Empezamos desde cero cada vez, así todos en el grupo tienen la misma base.
    cursor.execute("DROP TABLE IF EXISTS products")

    # CHECK hace que SQLite rechace filas inválidas (ej. un precio negativo).
    # El precio es INTEGER (pesos enteros) y no REAL, para evitar errores de redondeo.
    # La fecha es TEXT en formato AAAA-MM-DD: así se puede ordenar y comparar como texto.
    cursor.execute("""
        CREATE TABLE products (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL,
            category    TEXT    NOT NULL,
            description TEXT,
            condition   TEXT    NOT NULL CHECK (condition IN ('new', 'used', 'refurbished')),
            final_price INTEGER NOT NULL CHECK (final_price > 0),
            date        TEXT    NOT NULL
        )
    """)

    # Consulta parametrizada: cada "?" se reemplaza por los valores de cada tupla.
    # executemany ejecuta el mismo INSERT una vez por cada producto de la lista.
    cursor.executemany(
        """
        INSERT INTO products (name, category, description, condition, final_price, date)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        PRODUCTS,
    )

    connection.commit()

    # Resumen para verificar que se cargó todo bien.
    print(f"Database created at: {DB_PATH}")
    cursor.execute("""
        SELECT category, COUNT(*), MIN(final_price), MAX(final_price)
        FROM products
        GROUP BY category
        ORDER BY category
    """)
    for category, count, min_price, max_price in cursor.fetchall():
        print(f"  {category:<10} {count:>2} products  (${min_price:,} to ${max_price:,})")

    connection.close()


if __name__ == "__main__":
    create_db()
