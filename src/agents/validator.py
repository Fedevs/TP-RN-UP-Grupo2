import json
from typing import get_args

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from agents.coordinator import Category
from llm import llm
from state import State, user_messages

VALID_CATEGORIES = get_args(Category)
REQUIRED_FIELDS = ["title", "description", "category", "starting_price", "duration_days"]


class ValidatorOutput(BaseModel):
    issues: list[str] = Field(
        description="Lista de problemas encontrados, cada uno en una oración corta en español. "
        "Lista vacía si la publicación está bien."
    )


SYSTEM_PROMPT = """Sos el validador de calidad de un sistema de subastas.
Recibís lo que escribió el usuario, los datos del producto y el borrador de la publicación.

Revisá SOLO estas dos cosas:
1. Que la descripción sea coherente con el título y con el producto.
2. Que la publicación no afirme ningún dato que el usuario no haya dicho: características,
   accesorios, estado o funcionamiento (ej. "con caja original" si el usuario nunca lo dijo).
   Calificar el estado o el funcionamiento también es inventar si el usuario no lo dijo:
   "impecable", "excelente estado", "buen estado", "como nuevo", "funciona perfecto",
   "anda de diez", "joysticks originales", etc. Revisá frase por frase contra lo que escribió el usuario.
   No cuentan como inventados el nombre oficial del producto (ej. "PS5" -> "PlayStation 5") ni las
   frases de venta que no afirman ningún dato (ej. "aprovechá esta oportunidad").

Por cada problema, decí qué frase hay que sacar o cambiar.

No revises la cantidad de caracteres del título o de la descripción, el precio ni la categoría:
eso ya lo verificó el sistema.
Si todo está bien, devolvé una lista de problemas vacía."""

structured_llm = llm.with_structured_output(ValidatorOutput)


def check_rules(draft):
    issues = []

    for field in REQUIRED_FIELDS:
        if draft.get(field) in (None, ""):
            issues.append(f"Falta el campo '{field}'")
    if issues:
        return issues

    if not 10 <= len(draft["title"]) <= 80:
        issues.append(f"El título tiene {len(draft['title'])} caracteres (tiene que tener entre 10 y 80)")
    if not 50 <= len(draft["description"]) <= 1000:
        issues.append(
            f"La descripción tiene {len(draft['description'])} caracteres (tiene que tener entre 50 y 1000)"
        )
    if draft["category"] not in VALID_CATEGORIES:
        issues.append(f"La categoría '{draft['category']}' no es válida")
    if draft["starting_price"] <= 0:
        issues.append("El precio base tiene que ser mayor a 0")
    if not 1 <= draft["duration_days"] <= 14:
        issues.append("La duración tiene que estar entre 1 y 14 días")

    return issues


def validator(state: State) -> dict:
    draft = state["draft"]

    issues = check_rules(draft)

    if not issues:
        user_message = (
            f"Lo que escribió el usuario:\n{user_messages(state)}\n\n"
            f"Producto:\n{json.dumps(state['product'], ensure_ascii=False, indent=2)}\n\n"
            f"Borrador:\n{json.dumps(draft, ensure_ascii=False, indent=2)}"
        )
        result = structured_llm.invoke([
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=user_message),
        ])
        issues = result.issues

    return {"validation": {"approved": not issues, "issues": issues}}
