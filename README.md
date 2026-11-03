# Sistema multiagente de subastas

TP integrador de Redes Neuronales. El usuario escribe en lenguaje natural (ej. _"Quiero subastar mi PS5, ¿a cuánto la pongo?"_) y cuatro agentes coordinados con **LangGraph** y **Gemini** le arman la subasta:

| Agente          | Qué hace                                                                                                                  |
| --------------- | ------------------------------------------------------------------------------------------------------------------------- |
| **Coordinador** | Entiende qué quiere el usuario y extrae los datos del producto                                                            |
| **Analista**    | Busca subastas similares en la base de datos y sugiere un precio                                                          |
| **Subastas**    | Redacta el título y la descripción de la publicación, la guarda en la base cuando se aprueba y lista las subastas activas |
| **Validador**   | Revisa que la publicación cumpla los requisitos; si no, vuelve a Subastas                                                 |

El diseño completo y el diagrama están en [docs/diagrama.md](docs/diagrama.md).

## Instalación

Requiere **Python 3.11 o superior**.

```powershell
git clone https://github.com/Fedevs/TP-RN-UP-Grupo2.git
cd TP-RN-UP-Grupo2

python -m venv .venv # o py -m venv .venv
.venv\Scripts\Activate.ps1        # en Mac/Linux: source .venv/bin/activate

pip install -r requirements.txt
```

Después:

1. Copiá `.env.example` como `.env` y completá tu API key de Gemini (se saca gratis en [Google AI Studio](https://aistudio.google.com/apikey)).
2. Creá la base de datos de productos:
   ```powershell
   python data/create_db.py
   ```

## Uso

Desde la carpeta `src`, con el entorno virtual activado:

```powershell
cd src
python main.py "Quiero subastar mi PS5 con 2 joysticks, ¿a cuánto la pongo?"   # un mensaje
python main.py "¿Qué subastas de consolas hay activas?"                        # lista las subastas guardadas
python main.py                                                                 # conversación ("salir" para terminar)
```

Cada subasta aprobada se guarda en la tabla `auctions` de `data/products.db` y queda activa durante su duración (7 días). Volver a correr `data/create_db.py` borra también esas subastas.

Se muestra cada paso del grafo (qué agente se ejecutó y qué devolvió) y al final la respuesta.

Para comparar, el mismo pedido se puede resolver con un **único agente** (un solo prompt que hace todo): `python baseline.py "Quiero subastar mi PS5"`.

> **Ojo con la cuota gratuita de Gemini:** permite pocos pedidos por minuto y por día, y crear una subasta usa unos 4. Si aparece `429 RESOURCE_EXHAUSTED`, esperá un minuto. Podés ver tu cuota en https://ai.dev/rate-limit. Para no pasarte del límite por minuto, poné `REQUESTS_PER_MINUTE` en el `.env` (por ejemplo, `10`).

## Pruebas

Hay tres tipos de pruebas, todas en la carpeta `tests` y ejecutadas desde la raíz del repo:

**1. Pruebas automáticas sin IA** (`pytest`). Reemplazan a Gemini por un LLM simulado con respuestas fijas y prueban el código que coordina a los agentes: los caminos del grafo según la intención, el lazo de corrección y su límite de intentos, las reglas del Validador, la búsqueda en la base (incluida la inyección SQL), el guardado y listado de subastas activas, y el cálculo del precio. Usan una copia de la base, así no dejan subastas guardadas en la real. Son rápidas, gratis y dan siempre el mismo resultado.

```powershell
python -m pytest tests -v
```

**2. Evaluación de punta a punta con Gemini** (`tests/evaluate.py`). Corre 13 casos de prueba ([tests/cases.py](tests/cases.py)) con el resultado esperado de cada uno, en el sistema multiagente y en un agente único como línea de base, y un juez independiente revisa si las publicaciones tienen datos inventados. Guarda los resultados y un reporte con las métricas en `tests/results/`.

```powershell
python tests/evaluate.py              # 1 repetición de cada caso (~60 pedidos a Gemini)
python tests/evaluate.py --reps 3     # 3 repeticiones, para ver si el resultado varía
python tests/evaluate.py --help       # todas las opciones
```

**3. Prueba del Validador con borradores hechos a mano** (`tests/evaluate_validator.py`). Le da al Validador 12 borradores escritos a propósito, 7 de ellos con un dato que el usuario no dijo, y mide cuántos detecta y cuántas falsas alarmas da (~12 pedidos a Gemini por repetición).

```powershell
python tests/evaluate_validator.py --reps 3
```

Si la cuota diaria no alcanza, se pueden repartir los casos entre varias API keys (`--cases ps5_sin_precio iphone13_con_precio ...`) y después juntar los resultados en un solo reporte con `--report tests/results/a.json tests/results/b.json`.

## Estructura

```
data/create_db.py      Crea la base SQLite con subastas de referencia (la tabla de subastas creadas la arma src/db.py)
docs/diagrama.md       Diseño: agentes, estado compartido y diagrama
src/main.py            Punto de entrada
src/graph.py           Grafo de LangGraph: nodos, aristas y routers
src/state.py           Estado compartido entre agentes
src/agents/            Un archivo por agente
src/llm.py             Configuración del modelo Gemini
src/tools.py, db.py    Búsqueda de productos similares, y guardado y listado de subastas activas
src/baseline.py        Agente único (línea de base para la evaluación)
tests/test_*.py        Pruebas automáticas sin IA (pytest)
tests/cases.py         Casos de prueba de punta a punta y su resultado esperado
tests/evaluate.py      Evaluación con Gemini: multiagente vs. agente único
tests/evaluate_validator.py  Prueba del Validador con borradores hechos a mano
tests/results/         Resultados y reportes de la evaluación
```
