import json

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from llm import llm
from state import State
from tools import price_stats, search_similar

MIN_COMPARABLES = 2


class AnalystOutput(BaseModel):
    comparable_ids: list[int] = Field(
        description="ids de los candidatos que realmente son comparables con el producto del usuario "
        "(mismo modelo o equivalente). Descartar los que sean otro modelo o versión."
    )
    reasoning: str = Field(
        description="Explicación breve dirigida al usuario, hablándole de vos (ej. 'Tu PS5...', "
        "'No especificaste...'): qué comparables se usaron y si el producto debería ubicarse arriba "
        "o abajo del rango (por accesorios, estado, etc.)."
    )
    user_price_feedback: str | None = Field(
        description="Solo si el usuario dio un precio: opinión breve sobre si está dentro del mercado. "
        "Si no dio precio, null."
    )


SYSTEM_PROMPT = """Sos el analista de precios de un sistema de subastas.
Recibís el producto que el usuario quiere subastar y una lista de candidatos: subastas ya finalizadas
de productos parecidos, con su precio final.

Tu tarea es elegir cuáles candidatos son realmente comparables y explicar el precio.
No calcules promedios ni medianas: eso lo hace el sistema con los candidatos que elijas.

Si el usuario no especifica la versión del modelo (ej. "Nintendo Switch" sin decir OLED o Lite),
elegí la versión más probable o equivalente y aclaralo en el reasoning.
Si un candidato está en otro estado (nuevo vs. usado), podés incluirlo, pero aclaralo en el reasoning.
Respondé en español. No inventes datos que no estén en el producto o en los candidatos."""

structured_llm = llm.with_structured_output(AnalystOutput)


def format_price(price):
    return f"${price:,}".replace(",", ".")


def analyst(state: State) -> dict:
    product = state["product"]
    user_price = state.get("user_price")

    keywords = product["name"].split()
    candidates = search_similar(product["category"], keywords)

    if not candidates:
        return no_data_result(state)

    user_message = (
        f"Producto del usuario:\n{json.dumps(product, ensure_ascii=False, indent=2)}\n\n"
        f"Precio que pide el usuario: {user_price if user_price else 'no lo dijo'}\n\n"
        f"Candidatos:\n{json.dumps(candidates, ensure_ascii=False, indent=2)}"
    )
    result = structured_llm.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_message),
    ])

    comparables = [c for c in candidates if c["id"] in result.comparable_ids]
    if len(comparables) < MIN_COMPARABLES:
        return no_data_result(state, reasoning=result.reasoning, comparables=comparables)

    stats = price_stats(comparables)
    analysis = {
        "enough_data": True,
        "suggested_price": stats["median_price"],
        "min_price": stats["min_price"],
        "max_price": stats["max_price"],
        "comparables": [
            {"id": c["id"], "name": c["name"], "final_price": c["final_price"]} for c in comparables
        ],
        "reasoning": result.reasoning,
        "user_price_feedback": result.user_price_feedback,
    }

    response = None
    if state["intent"] == "price_query":
        response = (
            f"Según {stats['count']} subastas similares, se vendió entre "
            f"{format_price(stats['min_price'])} y {format_price(stats['max_price'])}. "
            f"Precio sugerido: {format_price(stats['median_price'])}.\n{result.reasoning}"
        )

    return {"analysis": analysis, "response": response}


def no_data_result(state, reasoning=None, comparables=None):
    comparables = comparables or []
    reasoning = reasoning or "No hay subastas similares en la base de datos."

    analysis = {
        "enough_data": False,
        "suggested_price": None,
        "min_price": None,
        "max_price": None,
        "comparables": [
            {"id": c["id"], "name": c["name"], "final_price": c["final_price"]} for c in comparables
        ],
        "reasoning": reasoning,
        "user_price_feedback": None,
    }

    response = None
    if state["intent"] == "price_query":
        response = (
            f"No tengo suficientes subastas similares para estimar el precio de ese producto.\n{reasoning}"
        )
    elif not state.get("user_price"):
        response = (
            f"No tengo suficientes subastas similares para sugerirte un precio.\n{reasoning}\n"
            "¿Cuánto te gustaría pedir por tu producto?"
        )

    return {"analysis": analysis, "response": response}

