"""Línea de base para la evaluación: un único agente que hace todo en un solo prompt.

Sirve para responder con datos la pregunta "¿por qué varios agentes y no uno solo?".
Recibe el mismo mensaje y tiene acceso a los mismos datos que el sistema multiagente
(la tabla completa de subastas finalizadas), pero tiene que hacer todo en una única
llamada al LLM: clasificar el pedido, elegir comparables, calcular el precio y redactar
la publicación. No hay router, ni cálculos en Python, ni Validador.

Uso (desde src):
    python baseline.py "Quiero subastar mi PS5, ¿a cuánto la pongo?"
"""

import json
import sys
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from agents.coordinator import Product
from db import connect
from llm import llm

DEFAULT_DURATION_DAYS = 7

# Sin list_auctions: la comparación con el multiagente es la misma de antes.
Intent = Literal[
    "create_auction_no_price",
    "create_auction_with_price",
    "price_query",
    "missing_info",
    "off_topic",
]


class SingleAgentOutput(BaseModel):
    intent: Intent
    product: Product | None = Field(description="El producto. null en missing_info y off_topic.")
    user_price: int | None = Field(
        description="Precio que pide el usuario, en pesos enteros, solo si lo dice explícitamente "
        "(ej. '500 lucas' -> 500000). Si no dice un precio, null."
    )
    comparable_ids: list[int] = Field(
        description="ids de las subastas de referencia que usaste para estimar el precio. "
        "Lista vacía si no hay comparables."
    )
    suggested_price: int | None = Field(
        description="Precio sugerido en pesos enteros: la mediana de los precios finales de los "
        "comparables. null si hay menos de 2 comparables."
    )
    starting_price: int | None = Field(
        description="Precio base de la subasta: el del usuario si lo dio, si no el sugerido. "
        "null si no se crea una subasta."
    )
    title: str | None = Field(
        description="Título de la publicación, entre 10 y 80 caracteres. null si no se crea una subasta."
    )
    description: str | None = Field(
        description="Descripción de la publicación, entre 50 y 1000 caracteres. null si no se crea una subasta."
    )
    response: str = Field(description="Respuesta final para el usuario.")


SYSTEM_PROMPT = """Sos un asistente de un sistema de subastas. Hacés todo el trabajo vos solo.

1. Clasificá el mensaje en una de estas intenciones:
   - create_auction_no_price: quiere subastar un producto y NO dice a qué precio.
   - create_auction_with_price: quiere subastar un producto y dice a qué precio.
   - price_query: solo quiere saber cuánto vale un producto.
   - missing_info: quiere subastar algo pero no dice qué producto.
   - off_topic: el mensaje no tiene que ver con subastas ni con precios.
   La categoría del producto es una de: consoles, phones, laptops, tvs, bicycles, other.

2. Si hay un producto, buscá en la tabla de subastas finalizadas las que son realmente
   comparables (mismo modelo o equivalente). Si hay al menos 2, el precio sugerido es la
   mediana de sus precios finales. Si hay menos de 2, no hay datos suficientes: no sugieras
   un precio y, si el usuario quiere subastar sin dar precio, pedile uno.

3. Si quiere subastar y hay precio (el suyo o el sugerido), redactá la publicación:
   - Usá SOLO los datos que dio el usuario. Nunca inventes características, accesorios ni estado.
   - Título entre 10 y 80 caracteres; descripción entre 50 y 1000 caracteres.
   - No menciones el precio en el texto. Escribí en español rioplatense, como el vendedor.

4. En missing_info y off_topic, respondé breve y amable (off_topic: solo ayudás con subastas).

Respondé en español."""

structured_llm = llm.with_structured_output(SingleAgentOutput)


def load_reference_table():
    connection = connect()
    rows = connection.execute(
        "SELECT id, name, category, description, condition, final_price FROM products"
    ).fetchall()
    connection.close()
    return [dict(row) for row in rows]


def single_agent(message, history=None):
    """Devuelve un dict con la misma forma que usa la evaluación para el sistema multiagente."""
    table = load_reference_table()
    history_text = ""
    if history:
        history_text = "Conversación anterior:\n" + "\n".join(
            f"{m['role']}: {m['content']}" for m in history
        ) + "\n\n"

    result = structured_llm.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(
            content=f"Subastas finalizadas de referencia:\n{json.dumps(table, ensure_ascii=False)}\n\n"
            f"{history_text}Mensaje del usuario:\n{message}"
        ),
    ])

    draft = None
    if result.title or result.description:
        draft = {
            "title": result.title,
            "description": result.description,
            "category": result.product.category if result.product else None,
            "starting_price": result.starting_price,
            "duration_days": DEFAULT_DURATION_DAYS,
        }

    return {
        "intent": result.intent,
        "product": result.product.model_dump() if result.product else None,
        "user_price": result.user_price,
        "comparable_ids": result.comparable_ids,
        "suggested_price": result.suggested_price,
        "draft": draft,
        "response": result.response,
    }


if __name__ == "__main__":
    output = single_agent(" ".join(sys.argv[1:]) or "Quiero subastar mi PS5, ¿a cuánto la pongo?")
    print(json.dumps(output, ensure_ascii=False, indent=2))
