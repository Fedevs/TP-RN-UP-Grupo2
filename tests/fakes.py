"""LLM simulado para las pruebas sin IA."""


class FakeLLM:
    """Reemplaza a `structured_llm` de un agente.

    Devuelve, en orden, las respuestas de la lista `outputs` (objetos Pydantic, como el LLM real)
    y guarda los mensajes que recibió en cada llamada, para poder revisar qué se le mandó.
    """

    def __init__(self, *outputs):
        self.outputs = list(outputs)
        self.calls = []

    def invoke(self, messages, config=None):
        self.calls.append(messages)
        if not self.outputs:
            raise AssertionError("Se llamó al LLM más veces de las esperadas")
        return self.outputs.pop(0)
