"""Configuración común de pytest.

Las pruebas de esta carpeta (test_*.py) NO llaman a Gemini: reemplazan el LLM por uno
simulado con respuestas fijas. Así prueban el código que coordina a los agentes (routers,
reglas, cálculos, lazo de corrección) de forma rápida, gratis y siempre con el mismo resultado.
La evaluación con el LLM real está en evaluate.py.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "data"))

# llm.py necesita estas variables para crear el modelo, aunque en estas pruebas no se use.
os.environ.setdefault("MODEL_NAME", "modelo-de-prueba")
os.environ.setdefault("GOOGLE_API_KEY", "clave-de-prueba")

# La base de datos no se sube a git: si no existe, se crea.
from create_db import DB_PATH, create_db  # noqa: E402

if not DB_PATH.exists():
    create_db()


import shutil  # noqa: E402

import pytest  # noqa: E402

import db  # noqa: E402


# Cada prueba usa una copia de la base con la tabla auctions vacía.
@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    path = tmp_path / "products.db"
    shutil.copy(DB_PATH, path)
    monkeypatch.setattr(db, "DB_PATH", path)
    connection = db.connect()
    connection.execute("DELETE FROM auctions")
    connection.execute("DELETE FROM sqlite_sequence WHERE name = 'auctions'")
    connection.commit()
    connection.close()
    return path
