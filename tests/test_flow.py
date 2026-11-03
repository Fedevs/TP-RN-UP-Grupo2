"""Pruebas de la coordinación entre agentes, con el LLM simulado.

Cada prueba fija qué "respondería" el LLM de cada agente y verifica que el grafo recorra
los nodos correctos. Así se prueba la coordinación (routers, aristas y lazo de corrección)
sin depender de lo que conteste Gemini en cada corrida.
"""

import pytest

import agents.analyst
import agents.auction
import agents.coordinator
import agents.validator
from agents.analyst import AnalystOutput
from agents.auction import AuctionOutput
from agents.coordinator import CoordinatorOutput, Product
from agents.validator import ValidatorOutput
from fakes import FakeLLM
from graph import MAX_ATTEMPTS, graph
from main import final_answer
from tools import list_active_auctions

PS5 = Product(name="PlayStation 5", category="consoles", condition="used", details="2 joysticks, poco uso")
CATAN = Product(name="Catan", category="other", condition="used", details=None)
PS5_STANDARD_IDS = [1, 2, 3, 4, 5]  # ids de las PS5 Standard en data/create_db.py

GOOD_DRAFT = AuctionOutput(
    title="PlayStation 5 Standard con 2 joysticks",
    description="Vendo mi PlayStation 5 Standard usada, con poco uso. Incluye 2 joysticks.",
)
BAD_DRAFT = AuctionOutput(title="PS5", description="Muy corta")  # no cumple las reglas de largo


def run(message, history=None):
    """Ejecuta el grafo como main.py y devuelve (camino de nodos, estado final)."""
    state = {"message": message, "history": history or []}
    path = []
    for step in graph.stream(state, stream_mode="updates"):
        for node, update in step.items():
            path.append(node)
            state.update(update)
    return path, state


@pytest.fixture
def fake(monkeypatch):
    """Permite fijar las respuestas del LLM de cada agente: fake(coordinator=[...], ...)."""
    modules = {
        "coordinator": agents.coordinator,
        "analyst": agents.analyst,
        "auction": agents.auction,
        "validator": agents.validator,
    }

    def set_outputs(**outputs):
        fakes = {}
        for name, module in modules.items():
            fakes[name] = FakeLLM(*outputs.get(name, []))
            monkeypatch.setattr(module, "structured_llm", fakes[name])
        return fakes

    return set_outputs


def coordinator_says(intent, product=None, user_price=None, response=None):
    return CoordinatorOutput(intent=intent, product=product, user_price=user_price, response=response)


# --- Caminos según la intención ------------------------------------------------------


def test_off_topic_ends_at_coordinator(fake):
    fakes = fake(coordinator=[coordinator_says("off_topic", response="Solo ayudo con subastas.")])
    path, state = run("¿Qué hora es?")
    assert path == ["coordinator"]
    assert final_answer(state) == "Solo ayudo con subastas."
    assert len(fakes["analyst"].calls) == 0  # no se gastan llamadas en los demás agentes


def test_missing_info_asks_for_product(fake):
    fake(coordinator=[coordinator_says("missing_info", response="¿Qué producto querés subastar?")])
    path, state = run("Quiero subastar algo")
    assert path == ["coordinator"]
    assert "producto" in final_answer(state)


def test_price_query_ends_at_analyst(fake):
    fake(
        coordinator=[coordinator_says("price_query", product=PS5)],
        analyst=[AnalystOutput(comparable_ids=PS5_STANDARD_IDS, reasoning="Tu PS5...", user_price_feedback=None)],
    )
    path, state = run("¿Cuánto vale una PS5 usada?")
    assert path == ["coordinator", "analyst"]
    # Precio calculado por Python con los comparables que eligió el LLM
    assert state["analysis"]["suggested_price"] == 450000
    assert (state["analysis"]["min_price"], state["analysis"]["max_price"]) == (380000, 520000)
    assert "$450.000" in final_answer(state)


def test_create_auction_full_path(fake):
    fake(
        coordinator=[coordinator_says("create_auction_no_price", product=PS5)],
        analyst=[AnalystOutput(comparable_ids=PS5_STANDARD_IDS, reasoning="Tu PS5...", user_price_feedback=None)],
        auction=[GOOD_DRAFT],
        validator=[ValidatorOutput(issues=[])],
    )
    path, state = run("Quiero subastar mi PS5 con 2 joysticks, ¿a cuánto la pongo?")
    assert path == ["coordinator", "analyst", "auction", "validator", "publish"]
    assert state["validation"]["approved"]
    assert state["draft"]["starting_price"] == 450000  # el sugerido por el Analista
    assert final_answer(state).startswith(f"¡Listo! Publiqué tu subasta con el número #{state['auction_id']}")
    [saved] = list_active_auctions()
    assert saved["id"] == state["auction_id"]
    assert (saved["title"], saved["starting_price"]) == (GOOD_DRAFT.title, 450000)


def test_analyst_discards_non_comparables(fake):
    # El LLM descarta la PS5 Digital (id 6): no entra en el cálculo del precio
    fake(
        coordinator=[coordinator_says("price_query", product=PS5)],
        analyst=[AnalystOutput(comparable_ids=[1, 2, 6], reasoning="...", user_price_feedback=None)],
    )
    _, with_digital = run("¿Cuánto vale una PS5?")
    assert with_digital["analysis"]["min_price"] == 350000

    fake(
        coordinator=[coordinator_says("price_query", product=PS5)],
        analyst=[AnalystOutput(comparable_ids=[1, 2], reasoning="...", user_price_feedback=None)],
    )
    _, without_digital = run("¿Cuánto vale una PS5?")
    assert without_digital["analysis"]["min_price"] == 420000


def test_analyst_ignores_ids_not_in_candidates(fake):
    # Si el LLM devuelve ids inventados, no se usan: solo cuentan los candidatos reales
    fake(
        coordinator=[coordinator_says("price_query", product=PS5)],
        analyst=[AnalystOutput(comparable_ids=[1, 999, 1000], reasoning="...", user_price_feedback=None)],
    )
    _, state = run("¿Cuánto vale una PS5?")
    assert state["analysis"]["enough_data"] is False  # queda 1 solo comparable real
    assert state["analysis"]["suggested_price"] is None


# --- Sin datos de referencia ----------------------------------------------------------


def test_no_data_and_no_price_asks_user(fake):
    fakes = fake(coordinator=[coordinator_says("create_auction_no_price", product=CATAN)])
    path, state = run("Quiero subastar mi Catan, ¿a cuánto lo pongo?")
    assert path == ["coordinator", "analyst"]  # no llega a Subastas: no se inventa un precio
    assert state["analysis"]["suggested_price"] is None
    assert "¿Cuánto te gustaría pedir" in final_answer(state)
    assert len(fakes["analyst"].calls) == 0  # sin candidatos, ni siquiera se llama al LLM


def test_no_data_but_user_price_continues(fake):
    fake(
        coordinator=[coordinator_says("create_auction_with_price", product=CATAN, user_price=40000)],
        auction=[AuctionOutput(title="Catan juego de mesa usado", description="Vendo mi juego de mesa Catan, usado. " * 2)],
        validator=[ValidatorOutput(issues=[])],
    )
    path, state = run("Quiero subastar mi Catan a $40.000")
    assert path == ["coordinator", "analyst", "auction", "validator", "publish"]
    assert state["draft"]["starting_price"] == 40000


# --- Lazo de corrección Validador -> Subastas -----------------------------------------


def test_rejected_draft_is_fixed_on_retry(fake):
    fakes = fake(
        coordinator=[coordinator_says("create_auction_no_price", product=PS5)],
        analyst=[AnalystOutput(comparable_ids=PS5_STANDARD_IDS, reasoning="...", user_price_feedback=None)],
        auction=[BAD_DRAFT, GOOD_DRAFT],
        validator=[ValidatorOutput(issues=[])],  # solo se llama al LLM con el borrador bueno
    )
    path, state = run("Quiero subastar mi PS5")
    assert path == ["coordinator", "analyst", "auction", "validator", "auction", "validator", "publish"]
    assert state["validation"]["approved"]
    assert state["retries"] == 2
    # En el reintento, Subastas recibe el borrador anterior y los problemas a corregir
    retry_prompt = fakes["auction"].calls[1][-1].content
    assert "Problemas a corregir" in retry_prompt and "título tiene 3 caracteres" in retry_prompt


def test_llm_validator_rejects_invented_features(fake):
    fake(
        coordinator=[coordinator_says("create_auction_no_price", product=PS5)],
        analyst=[AnalystOutput(comparable_ids=PS5_STANDARD_IDS, reasoning="...", user_price_feedback=None)],
        auction=[GOOD_DRAFT, GOOD_DRAFT],
        validator=[ValidatorOutput(issues=["Menciona caja original, que el usuario no dijo"]), ValidatorOutput(issues=[])],
    )
    path, state = run("Quiero subastar mi PS5")
    assert path.count("auction") == 2
    assert state["validation"]["approved"]


def test_retries_are_limited(fake):
    fake(
        coordinator=[coordinator_says("create_auction_no_price", product=PS5)],
        analyst=[AnalystOutput(comparable_ids=PS5_STANDARD_IDS, reasoning="...", user_price_feedback=None)],
        auction=[BAD_DRAFT] * MAX_ATTEMPTS,
    )
    path, state = run("Quiero subastar mi PS5")
    assert path.count("auction") == MAX_ATTEMPTS  # no queda en un bucle infinito
    assert path[-1] == "validator"
    assert not state["validation"]["approved"]
    assert final_answer(state).startswith(f"No pude generar una publicación válida después de {MAX_ATTEMPTS}")
    assert list_active_auctions() == []


def test_list_auctions_goes_to_auction_without_llm(fake):
    fake(
        coordinator=[coordinator_says("create_auction_no_price", product=PS5)],
        analyst=[AnalystOutput(comparable_ids=PS5_STANDARD_IDS, reasoning="...", user_price_feedback=None)],
        auction=[GOOD_DRAFT],
        validator=[ValidatorOutput(issues=[])],
    )
    _, created = run("Quiero subastar mi PS5")

    fakes = fake(coordinator=[CoordinatorOutput(
        intent="list_auctions", product=None, user_price=None, list_category="consoles", response=None,
    )])
    path, state = run("¿Qué consolas hay en subasta?")
    assert path == ["coordinator", "auction"]
    assert len(fakes["auction"].calls) == 0
    answer = final_answer(state)
    assert answer.startswith("Subastas activas de consolas (1):")
    assert f"#{created['auction_id']} {GOOD_DRAFT.title}" in answer
    assert "$450.000" in answer


def test_list_auctions_empty_category(fake):
    fake(coordinator=[CoordinatorOutput(
        intent="list_auctions", product=None, user_price=None, list_category="phones", response=None,
    )])
    _, state = run("¿Hay celulares en subasta?")
    assert final_answer(state) == "No hay subastas activas de celulares."


# --- Controles con código sobre la salida del Coordinador -------------------------------


def test_intent_without_product_becomes_missing_info(fake):
    # Si el LLM dice price_query pero no extrae producto, el Analista no se ejecuta (antes fallaba)
    fake(coordinator=[coordinator_says("price_query", product=None)])
    path, state = run("¿Cuánto vale?")
    assert path == ["coordinator"]
    assert state["intent"] == "missing_info"
    assert final_answer(state)  # siempre hay respuesta para el usuario


def test_intent_label_is_fixed_by_price(fake):
    fake(coordinator=[coordinator_says("create_auction_with_price", product=CATAN, user_price=None)])
    _, state = run("Quiero subastar mi Catan")
    assert state["intent"] == "create_auction_no_price"


def test_history_is_sent_to_coordinator(fake):
    fakes = fake(coordinator=[coordinator_says("missing_info", response="¿Qué estado tiene?")])
    history = [
        {"role": "user", "content": "Quiero subastar algo"},
        {"role": "assistant", "content": "¿Qué producto?"},
    ]
    run("Una PS5", history)
    sent = [m.content for m in fakes["coordinator"].calls[0]]
    assert sent[1:] == ["Quiero subastar algo", "¿Qué producto?", "Una PS5"]


def test_auction_and_validator_see_original_message(fake):
    # Subastas y el Validador reciben lo que escribió el usuario, no solo lo que extrajo el
    # Coordinador: así no se pierden detalles y el Validador puede detectar datos inventados.
    fakes = fake(
        coordinator=[coordinator_says("create_auction_no_price", product=PS5)],
        analyst=[AnalystOutput(comparable_ids=PS5_STANDARD_IDS, reasoning="...", user_price_feedback=None)],
        auction=[GOOD_DRAFT],
        validator=[ValidatorOutput(issues=[])],
    )
    run("Quiero subastar mi PS5, la usé poco")
    assert "la usé poco" in fakes["auction"].calls[0][-1].content
    assert "la usé poco" in fakes["validator"].calls[0][-1].content
