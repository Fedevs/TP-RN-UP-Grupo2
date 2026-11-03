"""Casos de prueba de punta a punta, con el resultado esperado de cada uno.

Los usa evaluate.py para correr el sistema multiagente y el agente único con Gemini.

Campos de cada caso:
- id, description: identificación y qué se quiere probar.
- message, history: lo que escribe el usuario (history = mensajes anteriores, opcional).
- intents: intenciones aceptadas como correctas.
- path: nodos que tiene que recorrer el grafo (solo multiagente).
- reference_ids: ids de data/create_db.py que son los comparables correctos. El precio
  sugerido tiene que caer entre el mínimo y el máximo de esos precios; la mediana es el
  precio de referencia para medir el error.
- no_price: True si no hay datos suficientes ni precio del usuario: el sistema NO tiene
  que inventar un precio ni crear la subasta.
- user_price: precio que dio el usuario; la publicación tiene que usar exactamente ese.
- creates_auction: True si se espera una publicación.
- multi_only: True si el caso no se corre en el agente único (ej. listar subastas).
"""

FULL_PATH = ["coordinator", "analyst", "auction", "validator", "publish"]

CASES = [
    {
        "id": "ps5_sin_precio",
        "description": "Caso normal: subastar sin precio, con varios comparables en la base",
        "message": "Quiero subastar mi PS5 con 2 joysticks, la usé poco. ¿A cuánto la pongo?",
        "intents": ["create_auction_no_price"],
        "path": FULL_PATH,
        "reference_ids": [1, 2, 3, 4, 5],
        "creates_auction": True,
    },
    {
        "id": "iphone13_con_precio",
        "description": "Subastar con precio del usuario por encima del mercado ('600 lucas')",
        "message": "Quiero subastar mi iPhone 13 de 128GB, batería al 85%, a 600 lucas",
        "intents": ["create_auction_with_price"],
        "path": FULL_PATH,
        "reference_ids": [11, 12],
        "user_price": 600000,
        "creates_auction": True,
    },
    {
        "id": "macbook_con_precio",
        "description": "Subastar con precio del usuario dentro del mercado",
        "message": "Subasto mi MacBook Air M1 de 8GB y 256GB, la quiero largar a $720.000",
        "intents": ["create_auction_with_price"],
        "path": FULL_PATH,
        "reference_ids": [19, 20],
        "user_price": 720000,
        "creates_auction": True,
    },
    {
        "id": "consulta_switch_oled",
        "description": "Solo consulta de precio: no se crea subasta",
        "message": "¿Cuánto vale una Nintendo Switch OLED?",
        "intents": ["price_query"],
        "path": ["coordinator", "analyst"],
        "reference_ids": [7, 8],
        "creates_auction": False,
    },
    {
        "id": "consulta_a54",
        "description": "Consulta de precio sin aclarar el estado (hay uno nuevo y uno usado)",
        "message": "Che, ¿a cuánto se está vendiendo el Samsung Galaxy A54 de 128?",
        "intents": ["price_query"],
        "path": ["coordinator", "analyst"],
        "reference_ids": [15, 16],
        "creates_auction": False,
    },
    {
        "id": "bici_venzo_sin_precio",
        "description": "La búsqueda trae muchas bicis: el Analista tiene que quedarse con las Venzo",
        "message": "Quiero subastar mi mountain bike Venzo rodado 29, usada. ¿Qué precio le pongo?",
        "intents": ["create_auction_no_price"],
        "path": FULL_PATH,
        "reference_ids": [34, 35],
        "creates_auction": True,
    },
    {
        "id": "xbox_series_x_sin_datos",
        "description": "Modelo que no está en la base (solo hay Series S): no debe usar otro modelo",
        "message": "Quiero subastar mi Xbox Series X, ¿cuánto pido?",
        "intents": ["create_auction_no_price"],
        "path": ["coordinator", "analyst"],
        "no_price": True,
        "creates_auction": False,
    },
    {
        "id": "catan_sin_precio",
        "description": "Categoría sin datos y sin precio: tiene que pedirle un precio al usuario",
        "message": "Quiero subastar mi juego de mesa Catan, ¿a cuánto lo pongo?",
        "intents": ["create_auction_no_price"],
        "path": ["coordinator", "analyst"],
        "no_price": True,
        "creates_auction": False,
    },
    {
        "id": "catan_con_precio",
        "description": "Categoría sin datos pero con precio del usuario: se crea la subasta igual",
        "message": "Quiero subastar mi juego de mesa Catan completo a $40.000",
        "intents": ["create_auction_with_price"],
        "path": FULL_PATH,
        "user_price": 40000,
        "creates_auction": True,
    },
    {
        "id": "pedido_incompleto",
        "description": "Quiere subastar pero no dice qué",
        "message": "Quiero subastar algo",
        "intents": ["missing_info"],
        "path": ["coordinator"],
        "creates_auction": False,
    },
    {
        "id": "fuera_de_tema",
        "description": "Mensaje que no tiene que ver con subastas",
        "message": "¿Qué hora es?",
        "intents": ["off_topic"],
        "path": ["coordinator"],
        "creates_auction": False,
    },
    {
        "id": "listar_subastas",
        "description": "Ver las subastas activas de una categoría (Subastas consulta la base, sin LLM)",
        "message": "¿Qué subastas de consolas hay activas?",
        "intents": ["list_auctions"],
        "path": ["coordinator", "auction"],
        "creates_auction": False,
        "multi_only": True,
    },
    {
        "id": "multiturno_ps5",
        "description": "Completa los datos en un segundo mensaje (usa el historial)",
        "history": [
            {"role": "user", "content": "Quiero subastar algo"},
            {"role": "assistant", "content": "¿Qué producto querés subastar? Contame marca, modelo y en qué estado está."},
        ],
        "message": "Una PS5 Standard usada, con un joystick",
        "intents": ["create_auction_no_price"],
        "path": FULL_PATH,
        "reference_ids": [1, 2, 3, 4, 5],
        "creates_auction": True,
    },
]
