from langgraph.graph import END, START, StateGraph

from agents.analyst import analyst
from agents.auction import auction, publish
from agents.coordinator import coordinator
from agents.validator import validator
from state import State

MAX_ATTEMPTS = 3


def route_after_coordinator(state: State) -> str:
    if state["intent"] in ("price_query", "create_auction_no_price", "create_auction_with_price"):
        return "analyst"
    if state["intent"] == "list_auctions":
        return "auction"
    return END  # missing_info, off_topic: el Coordinador ya escribió la respuesta


def route_after_analyst(state: State) -> str:
    if state["intent"] == "price_query":
        return END  # el Analista ya escribió la respuesta

    if state["analysis"]["enough_data"] or state.get("user_price"):
        return "auction"
    return END  # sin datos ni precio: el Analista le pidió al usuario un precio de referencia


def route_after_auction(state: State) -> str:
    if state["intent"] == "list_auctions":
        return END
    return "validator"


def route_after_validator(state: State) -> str:
    if state["validation"]["approved"]:
        return "publish"
    if state["retries"] < MAX_ATTEMPTS:
        return "auction"
    return END  # demasiados intentos: se corta


def build_graph():
    builder = StateGraph(State)

    builder.add_node("coordinator", coordinator)
    builder.add_node("analyst", analyst)
    builder.add_node("auction", auction)
    builder.add_node("validator", validator)
    builder.add_node("publish", publish)

    builder.add_edge(START, "coordinator")
    builder.add_edge("publish", END)

    builder.add_conditional_edges("coordinator", route_after_coordinator, ["analyst", "auction", END])
    builder.add_conditional_edges("analyst", route_after_analyst, ["auction", END])
    builder.add_conditional_edges("auction", route_after_auction, ["validator", END])
    builder.add_conditional_edges("validator", route_after_validator, ["publish", "auction", END])

    return builder.compile()


graph = build_graph()


if __name__ == "__main__":
    print(graph.get_graph().draw_mermaid())
