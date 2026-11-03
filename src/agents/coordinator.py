from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from llm import llm
from state import State

Intent = Literal[
    "create_auction_no_price",
    "create_auction_with_price",
    "price_query",
    "list_auctions",
    "missing_info",
    "off_topic",
]
Category = Literal["consoles", "phones", "laptops", "tvs", "bicycles", "other"]
Condition = Literal["new", "used", "refurbished"]


class Product(BaseModel):
    name: str = Field(
        description="Nombre comercial completo del producto, con marca y modelo. "
        "Usar el nombre oficial y no abreviaturas (ej. 'PS5' -> 'PlayStation 5')."
    )
    category: Category = Field(description="Categoría del producto. Si no encaja en ninguna, 'other'.")
    condition: Condition | None = Field(description="Estado del producto, solo si el usuario lo dice.")
    details: str | None = Field(
        description="Otros detalles que dio el usuario (accesorios, uso, defectos). No inventar nada."
    )


class CoordinatorOutput(BaseModel):
    intent: Intent
    product: Product | None = Field(description="El producto. null en missing_info y off_topic.")
    user_price: int | None = Field(
        description="Precio que pide el usuario, en pesos enteros, solo si lo dice explícitamente "
        "(ej. '500 lucas' -> 500000). Si no dice un precio, null."
    )
    list_category: Category | None = Field(
        default=None,
        description="Solo en list_auctions: la categoría por la que quiere filtrar, si la dice "
        "(ej. 'qué consolas hay' -> 'consoles'). Si quiere ver todas, null.",
    )
    response: str | None = Field(
        description="Solo en missing_info y off_topic: respuesta breve y amable para el usuario. "
        "Si es off_topic, indicar que solo respondés a cuestiones de subastas. "
        "En el resto de los casos, null."
    )


SYSTEM_PROMPT = """Sos el coordinador de un sistema de subastas.
Tu tarea es entender qué quiere el usuario y extraer los datos del producto.

Clasificá el mensaje en una de estas intenciones:
- create_auction_no_price: quiere subastar un producto y NO dice a qué precio (aunque pregunte cuánto pedir).
- create_auction_with_price: quiere subastar un producto y dice a qué precio.
- price_query: solo quiere saber cuánto vale un producto, sin intención de subastarlo.
- list_auctions: quiere ver las subastas activas (todas o las de una categoría).
- missing_info: quiere subastar algo pero no dice qué producto.
- off_topic: el mensaje no tiene que ver con subastas ni con precios.

Puede haber mensajes anteriores de la conversación. Usalos para completar lo que el usuario ya dijo
(qué quiere hacer, el producto, el precio): si antes dijo que quería subastar y ahora da los datos
del producto, la intención sigue siendo subastar.

Nunca inventes datos que el usuario no dio."""

structured_llm = llm.with_structured_output(CoordinatorOutput)


# Intenciones que necesitan un producto para que el Analista tenga qué buscar
INTENTS_WITH_PRODUCT = ("create_auction_no_price", "create_auction_with_price", "price_query")

DEFAULT_RESPONSES = {
    "missing_info": "¿Qué producto querés subastar? Contame marca, modelo y en qué estado está.",
    "off_topic": "Solo puedo ayudarte con subastas: crear una publicación o estimar el precio de un producto.",
}


def coordinator(state: State) -> dict:
    history = [
        HumanMessage(content=m["content"]) if m["role"] == "user" else AIMessage(content=m["content"])
        for m in state.get("history", [])
    ]

    result = structured_llm.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        *history,
        HumanMessage(content=state["message"]),
    ])

    intent = result.intent
    response = result.response

    # Controles con código sobre la salida del LLM, para que un error de clasificación
    # no rompa el flujo:
    # 1. Si eligió una intención que necesita producto pero no extrajo ninguno,
    #    se trata como missing_info (si no, el Analista no tendría qué buscar).
    if intent in INTENTS_WITH_PRODUCT and result.product is None:
        intent = "missing_info"
        response = None
    # 2. Las dos intenciones de crear subasta se distinguen solo por si hay precio:
    #    se corrige la etiqueta según el precio que extrajo.
    if intent == "create_auction_with_price" and result.user_price is None:
        intent = "create_auction_no_price"
    elif intent == "create_auction_no_price" and result.user_price is not None:
        intent = "create_auction_with_price"
    # 3. Si el flujo termina acá, siempre tiene que haber una respuesta para el usuario.
    if intent in DEFAULT_RESPONSES and not response:
        response = DEFAULT_RESPONSES[intent]

    return {
        "intent": intent,
        "product": result.product.model_dump() if result.product else None,
        "user_price": result.user_price,
        "list_category": result.list_category if intent == "list_auctions" else None,
        "response": response,
    }
