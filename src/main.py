import json
import sys

from agents.analyst import format_price
from graph import graph


MAX_HISTORY = 6  # cuántos mensajes anteriores se le pasan al Coordinador


def run(message, history):
    state = {"message": message, "history": history[-MAX_HISTORY:]}

    # stream_mode="updates" devuelve, después de cada nodo, lo que ese nodo escribió en el estado
    for step in graph.stream(state, stream_mode="updates"):
        for node, update in step.items():
            print(f"\n--- [{node}] ---")
            print(json.dumps(update, ensure_ascii=False, indent=2))
            state.update(update)

    return state


def final_answer(state):
    draft = state.get("draft")

    if draft and state["validation"]["approved"]:
        lines = [
            f"¡Listo! Publiqué tu subasta con el número #{state['auction_id']}:",
            "",
            f"  {draft['title']}",
            f"  {draft['description']}",
            f"  Precio base: {format_price(draft['starting_price'])}",
            f"  Duración: {draft['duration_days']} días",
        ]
        # El razonamiento del Analista se muestra siempre: si no había subastas similares,
        # explica por qué se usó el precio del usuario.
        analysis = state.get("analysis") or {}
        if analysis.get("reasoning"):
            lines += ["", analysis["reasoning"]]
        if analysis.get("user_price_feedback"):
            lines += ["", analysis["user_price_feedback"]]
        return "\n".join(lines)

    if draft:
        issues = "\n".join(f"  - {issue}" for issue in state["validation"]["issues"])
        return (
            f"No pude generar una publicación válida después de {state['retries']} intentos.\n"
            f"Problemas:\n{issues}"
        )

    return state.get("response") or "No pude procesar tu mensaje."


def main():
    # Con argumento: procesa ese mensaje y termina. Sin argumento: modo conversación.
    if len(sys.argv) > 1:
        messages = [" ".join(sys.argv[1:])]
    else:
        messages = None

    history = []

    while True:
        message = messages.pop() if messages else input("\nVos: ").strip()
        if not message or message.lower() == "salir":
            break

        state = run(message, history)
        answer = final_answer(state)
        print("\n=== Respuesta ===")
        print(answer)

        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": answer})

        if messages is not None:
            break


if __name__ == "__main__":
    main()
