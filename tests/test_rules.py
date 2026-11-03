"""Pruebas de las partes que son código normal (sin IA): búsqueda, cálculos y reglas."""

import pytest

from agents.auction import choose_starting_price
from agents.validator import check_rules
from tools import price_stats, search_similar

VALID_DRAFT = {
    "title": "PlayStation 5 Standard con 2 joysticks",
    "description": "Vendo mi PlayStation 5 Standard usada, con poco uso. Incluye 2 joysticks.",
    "category": "consoles",
    "starting_price": 450000,
    "duration_days": 7,
}


# --- search_similar -----------------------------------------------------------------


def test_search_filters_by_category_and_keyword():
    products = search_similar("consoles", ["PlayStation"])
    assert len(products) == 6  # 5 PS5 Standard + 1 PS5 Digital
    assert all(p["category"] == "consoles" for p in products)
    assert all("PlayStation" in p["name"] for p in products)


def test_search_without_keywords_returns_whole_category():
    assert len(search_similar("phones", [])) == 8


def test_search_other_category_has_no_products():
    # "other" no tiene datos cargados: es el camino de "sin datos" del Analista
    assert search_similar("other", ["Catan"]) == []


def test_search_is_safe_against_sql_injection():
    # Las keywords vienen de un LLM: con consultas parametrizadas, esto es texto y no SQL
    assert search_similar("consoles", ["' OR 1=1 --"]) == []
    assert len(search_similar("consoles", [])) == 10  # la tabla sigue intacta


# --- price_stats --------------------------------------------------------------------


def test_price_stats_uses_median_not_mean():
    products = [{"final_price": p} for p in (100, 200, 1000)]
    stats = price_stats(products)
    assert stats == {"count": 3, "min_price": 100, "max_price": 1000, "median_price": 200}


def test_price_stats_even_count():
    stats = price_stats([{"final_price": 500000}, {"final_price": 550000}])
    assert stats["median_price"] == 525000


def test_price_stats_empty():
    assert price_stats([]) is None


# --- Reglas del Validador (check_rules) ----------------------------------------------


def test_valid_draft_has_no_issues():
    assert check_rules(VALID_DRAFT) == []


@pytest.mark.parametrize(
    "change, expected_fragment",
    [
        ({"title": "PS5"}, "título tiene 3 caracteres"),
        ({"title": "x" * 81}, "título tiene 81 caracteres"),
        ({"description": "Muy corta"}, "descripción tiene 9 caracteres"),
        ({"category": "autos"}, "categoría 'autos' no es válida"),
        ({"starting_price": 0}, "mayor a 0"),
        ({"duration_days": 30}, "entre 1 y 14 días"),
        ({"title": ""}, "Falta el campo 'title'"),
        ({"starting_price": None}, "Falta el campo 'starting_price'"),
    ],
)
def test_invalid_drafts_are_rejected(change, expected_fragment):
    issues = check_rules({**VALID_DRAFT, **change})
    assert any(expected_fragment in issue for issue in issues), issues


# --- Precio base de Subastas (lo decide el código, no el LLM) -----------------------


def test_starting_price_prefers_user_price():
    state = {"user_price": 600000, "analysis": {"suggested_price": 525000}}
    assert choose_starting_price(state) == 600000


def test_starting_price_falls_back_to_suggested():
    state = {"user_price": None, "analysis": {"suggested_price": 525000}}
    assert choose_starting_price(state) == 525000


def test_starting_price_never_invented():
    with pytest.raises(ValueError):
        choose_starting_price({"user_price": None, "analysis": {"suggested_price": None}})
