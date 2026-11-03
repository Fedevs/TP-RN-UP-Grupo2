import os

from dotenv import load_dotenv
from langchain_core.rate_limiters import InMemoryRateLimiter
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

# Límite opcional de pedidos por minuto, para no pasarse de la cuota gratuita de Gemini
# (sobre todo al correr la evaluación, que hace muchos pedidos seguidos).
# Se configura en el .env con REQUESTS_PER_MINUTE. Si no está o vale 0, no hay límite.
requests_per_minute = float(os.getenv("REQUESTS_PER_MINUTE") or 0)
rate_limiter = (
    InMemoryRateLimiter(requests_per_second=requests_per_minute / 60, check_every_n_seconds=0.1)
    if requests_per_minute > 0
    else None
)

llm = ChatGoogleGenerativeAI(
    model=os.environ["MODEL_NAME"],
    timeout=30,
    max_retries=2,
    rate_limiter=rate_limiter,
)
