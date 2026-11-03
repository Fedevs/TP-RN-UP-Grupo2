import json
from datetime import datetime

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from agents.analyst import format_price
from llm import llm
from state import State, user_messages
from tools import list_active_auctions, save_auction

DEFAULT_DURATION_DAYS = 7


class AuctionOutput(BaseModel):
    title: str = Field(
        description="Título de la publicación, entre 10 y 80 caracteres. Producto, modelo y lo más importante."
    )
    description: str = Field(
        description="Descripción de la publicación, entre 50 y 1000 caracteres. Clara y atractiva, "
        "usando solo los datos que dio el usuario."
    )


SYSTEM_PROMPT = """Sos el redactor de publicaciones de un sistema de subastas.
A partir de los datos del producto, escribí el título y la descripción de la subasta.

Reglas:
- Usá SOLO los datos que dio el usuario. Nunca inventes características, accesorios ni estado
  (ej. no digas "con caja original" si el usuario no lo dijo).
- Tampoco califiques el estado ni el funcionamiento si el usuario no lo hizo: nada de "impecable",
  "excelente estado", "buen estado", "como nuevo", "funciona perfecto", "anda de diez" ni "original".
  Si el usuario dijo algo del estado (ej. "la usé poco"), repetí eso mismo, sin exagerarlo.
- Podés usar frases de venta que no afirman ningún dato (ej. "aprovechá esta oportunidad").
- El título tiene entre 10 y 80 caracteres.
- La descripción tiene entre 50 y 1000 caracteres.
- No menciones el precio: el sistema lo agrega aparte.
- Escribí en español rioplatense, como si fueras el vendedor publicando su producto.
- No menciones "los datos", "el sistema" ni nada del funcionamiento interno: el comprador no lo ve.

Si te pasan un borrador anterior con problemas, corregí esos problemas manteniendo lo que estaba bien."""

structured_llm = llm.with_structured_output(AuctionOutput)


def choose_starting_price(state):
    if state.get("user_price"):
        return state["user_price"]

    analysis = state.get("analysis") or {}
    if analysis.get("suggested_price"):
        return analysis["suggested_price"]

    raise ValueError("Auction agent needs a price: neither user_price nor suggested_price is set")


CATEGORY_NAMES = {
    "consoles": "consolas",
    "phones": "celulares",
    "laptops": "notebooks",
    "tvs": "televisores",
    "bicycles": "bicicletas",
    "other": "otros",
}


def format_auction_list(auctions, category):
    of_category = f" de {CATEGORY_NAMES[category]}" if category else ""
    if not auctions:
        return f"No hay subastas activas{of_category}."

    lines = [f"Subastas activas{of_category} ({len(auctions)}):"]
    for item in auctions:
        ends_at = datetime.fromisoformat(item["ends_at"])
        lines.append(
            f"  #{item['id']} {item['title']} · precio base {format_price(item['starting_price'])}"
            f" · termina el {ends_at:%d/%m}"
        )
    return "\n".join(lines)


def list_auctions(state: State) -> dict:
    category = state.get("list_category")
    return {"response": format_auction_list(list_active_auctions(category), category)}


def auction(state: State) -> dict:
    if state["intent"] == "list_auctions":
        return list_auctions(state)

    product = state["product"]
    starting_price = choose_starting_price(state)

    user_message = (
        f"Producto:\n{json.dumps(product, ensure_ascii=False, indent=2)}\n\n"
        f"Lo que escribió el usuario:\n{user_messages(state)}"
    )

    validation = state.get("validation")
    if validation and not validation["approved"]:
        user_message += (
            f"\n\nBorrador anterior:\n{json.dumps(state['draft'], ensure_ascii=False, indent=2)}"
            f"\n\nProblemas a corregir:\n- " + "\n- ".join(validation["issues"])
        )

    result = structured_llm.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_message),
    ])

    draft = {
        "title": result.title,
        "description": result.description,
        "category": product["category"],
        "starting_price": starting_price,
        "duration_days": DEFAULT_DURATION_DAYS,
    }

    return {"draft": draft, "retries": state.get("retries", 0) + 1}


# Nodo aparte: solo se llega si el Validador aprobó, así nunca se guarda un borrador sin validar.
def publish(state: State) -> dict:
    return {"auction_id": save_auction(state["draft"], state["product"])}
