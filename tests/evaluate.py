"""Evaluación de punta a punta con el LLM real (Gemini).

Corre los casos de tests/cases.py en dos sistemas y compara los resultados:
- "multi": el sistema multiagente (src/graph.py).
- "single": un único agente con un solo prompt (src/baseline.py), como línea de base.

Además, un "juez" (otra llamada al LLM, con un prompt distinto al del Validador) revisa cada
publicación generada y lista los datos que el usuario no dio. Es el mismo juez para los dos
sistemas, así la comparación es justa.

Uso (desde la raíz del repo, con el entorno virtual activado y el .env configurado):
    python tests/evaluate.py                       # todos los casos, 1 repetición, los dos sistemas
    python tests/evaluate.py --reps 3              # 3 repeticiones por caso (para ver la variabilidad)
    python tests/evaluate.py --system multi        # solo el multiagente (o "single")
    python tests/evaluate.py --cases ps5_sin_precio catan_sin_precio
    python tests/evaluate.py --report tests/results/a.json tests/results/b.json   # junta corridas

Cada corrida guarda en tests/results/:
- <fecha>.json: todo lo que pasó en cada caso (se guarda después de cada caso: si se corta
  por la cuota de Gemini, no se pierde lo anterior).
- <fecha>.md: el reporte con las métricas, la comparación y el detalle de cada caso.

Ojo con la cuota gratuita: una repetición completa usa unos 60 pedidos al LLM. Si aparece
429 RESOURCE_EXHAUSTED, el script espera un minuto y reintenta una vez. Se pueden repartir
los casos entre las API keys del grupo con --cases y después juntar todo con --report.
"""

import argparse
import json
import os
import shutil
import statistics
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "data"))
sys.path.insert(0, str(Path(__file__).parent))

from create_db import DB_PATH, create_db  # noqa: E402

if not DB_PATH.exists():
    create_db()

import db  # noqa: E402

# Copia temporal de la base: la evaluación no llena data/products.db.
db.DB_PATH = Path(tempfile.mkdtemp()) / "products.db"
shutil.copy(DB_PATH, db.DB_PATH)
with db.connect() as _connection:
    _connection.execute("DELETE FROM auctions")
    _connection.execute("DELETE FROM sqlite_sequence WHERE name = 'auctions'")
_connection.close()

from langchain_core.messages import HumanMessage, SystemMessage  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

import agents.analyst  # noqa: E402
import agents.auction  # noqa: E402
import agents.coordinator  # noqa: E402
import agents.validator  # noqa: E402
import baseline  # noqa: E402
from agents.validator import check_rules  # noqa: E402
from cases import CASES  # noqa: E402
from db import connect  # noqa: E402
from graph import graph  # noqa: E402
from llm import llm  # noqa: E402
from main import final_answer  # noqa: E402

RESULTS_DIR = Path(__file__).parent / "results"
SYSTEMS = {"multi": "Multiagente", "single": "Agente único"}


# --- Contador de llamadas al LLM -------------------------------------------------------


class CountingLLM:
    """Envuelve el structured_llm de un agente para contar cuántas veces se lo llama."""

    count = 0

    def __init__(self, wrapped):
        self.wrapped = wrapped

    def invoke(self, *args, **kwargs):
        CountingLLM.count += 1
        return self.wrapped.invoke(*args, **kwargs)


for module in (agents.coordinator, agents.analyst, agents.auction, agents.validator, baseline):
    module.structured_llm = CountingLLM(module.structured_llm)


def call_with_retry(function, *args):
    """Si Gemini responde que se acabó la cuota por minuto, espera y reintenta una vez."""
    try:
        return function(*args)
    except Exception as error:  # noqa: BLE001
        if "429" in str(error) or "RESOURCE_EXHAUSTED" in str(error):
            print("    Cuota de Gemini agotada, espero 60 segundos y reintento...")
            time.sleep(60)
            return function(*args)
        raise


# --- Juez independiente ------------------------------------------------------------------


class JudgeOutput(BaseModel):
    invented: list[str] = Field(
        description="Cada dato concreto de la publicación que el vendedor no dijo, en una oración corta. "
        "Lista vacía si no hay ninguno."
    )


JUDGE_PROMPT = """Sos un evaluador independiente de publicaciones de subastas generadas automáticamente.
Recibís los mensajes que escribió el vendedor y la publicación generada.

Listá cada dato concreto de la publicación que el vendedor NO dijo y que tampoco se deduce
directamente de lo que dijo: características, accesorios, estado, antigüedad, garantía, caja, etc.

No cuentes como inventado:
- El nombre oficial del producto (ej. "PS5" -> "PlayStation 5").
- Frases de venta genéricas que no afirman ningún dato concreto (ej. "ideal para jugar con amigos").

Sé estricto: si un dato no está en los mensajes del vendedor, está inventado."""

judge_llm = llm.with_structured_output(JudgeOutput)


def judge(case, draft):
    seller = [m["content"] for m in case.get("history", []) if m["role"] == "user"] + [case["message"]]
    result = judge_llm.invoke([
        SystemMessage(content=JUDGE_PROMPT),
        HumanMessage(
            content="Mensajes del vendedor:\n" + "\n".join(f"- {m}" for m in seller)
            + f"\n\nPublicación:\nTítulo: {draft.get('title')}\nDescripción: {draft.get('description')}"
        ),
    ])
    return result.invented


# --- Ejecución de cada sistema ------------------------------------------------------------


def run_multi(case):
    state = {"message": case["message"], "history": case.get("history", [])}
    path = []
    for step in graph.stream(state, stream_mode="updates"):
        for node, update in step.items():
            path.append(node)
            state.update(update)

    analysis = state.get("analysis") or {}
    validation = state.get("validation") or {}
    draft = state.get("draft") if validation.get("approved") else None
    return {
        "path": path,
        "intent": state.get("intent"),
        "product": state.get("product"),
        "user_price": state.get("user_price"),
        "comparable_ids": [c["id"] for c in analysis.get("comparables", [])],
        "suggested_price": analysis.get("suggested_price"),
        "draft": draft,
        "rejected_draft": state.get("draft") if state.get("draft") and not draft else None,
        "retries": state.get("retries", 0),
        "validation_issues": validation.get("issues", []),
        "answer": final_answer(state),
    }


def run_single(case):
    output = baseline.single_agent(case["message"], case.get("history"))
    output["answer"] = output.pop("response")
    return output


RUNNERS = {"multi": run_multi, "single": run_single}


# --- Verificaciones -----------------------------------------------------------------------


def reference_prices(ids):
    connection = connect()
    placeholders = ",".join("?" * len(ids))
    rows = connection.execute(f"SELECT final_price FROM products WHERE id IN ({placeholders})", ids).fetchall()
    connection.close()
    return [row[0] for row in rows]


def without_retries(path):
    """Saca las vueltas del lazo de corrección: [..., auction, validator, auction, validator]
    queda como [..., auction, validator]. Una corrección no es un recorrido incorrecto."""
    result = []
    for node in path:
        if node == "auction" and result[-1:] == ["validator"]:
            result.pop()
            continue
        result.append(node)
    return result


def check(case, record, system):
    """Devuelve las verificaciones del caso: True (bien), False (mal) o None (no aplica)."""
    draft = record.get("draft")
    suggested = record.get("suggested_price")
    checks = {
        "intent_ok": record.get("intent") in case["intents"],
        "path_ok": without_retries(record.get("path") or []) == case["path"] if system == "multi" else None,
        "auction_ok": bool(draft) == case["creates_auction"],
        "price_in_range": None,
        "no_invented_price": None,
        "user_price_ok": None,
        "rules_ok": None,
        "judge_ok": None,
    }
    metrics = {"price_error": None}

    if case.get("reference_ids"):
        prices = reference_prices(case["reference_ids"])
        checks["price_in_range"] = suggested is not None and min(prices) <= suggested <= max(prices)
        if suggested is not None:
            median = statistics.median(prices)
            metrics["price_error"] = abs(suggested - median) / median

    if case.get("no_price"):
        checks["no_invented_price"] = suggested is None and not draft

    if case.get("user_price"):
        checks["user_price_ok"] = bool(draft) and draft.get("starting_price") == case["user_price"]

    if draft:
        checks["rules_ok"] = check_rules(draft) == []
        if record.get("judge_invented") is not None:
            checks["judge_ok"] = record["judge_invented"] == []

    applicable = [value for value in checks.values() if value is not None]
    return checks, metrics, all(applicable)


# --- Corrida ---------------------------------------------------------------------------------


def evaluate(cases, systems, reps, use_judge, out_path):
    results = {
        "model": os.environ.get("MODEL_NAME"),
        "date": datetime.now().isoformat(timespec="seconds"),
        "runs": [],
    }
    def runs_case(case, system):
        return system == "multi" or not case.get("multi_only")

    total = sum(runs_case(case, system) for case in cases for system in systems) * reps
    done = 0

    for rep in range(1, reps + 1):
        for case in cases:
            for system in systems:
                if not runs_case(case, system):
                    continue
                done += 1
                print(f"[{done}/{total}] {SYSTEMS[system]:<12} rep {rep}  {case['id']}")
                CountingLLM.count = 0
                start = time.perf_counter()
                try:
                    record = call_with_retry(RUNNERS[system], case)
                    record["error"] = None
                except Exception as error:  # noqa: BLE001
                    record = {"error": f"{type(error).__name__}: {error}"}
                    print(f"    ERROR: {record['error'][:200]}")
                record["seconds"] = round(time.perf_counter() - start, 2)
                record["llm_calls"] = CountingLLM.count

                if use_judge and record.get("draft"):
                    try:
                        record["judge_invented"] = call_with_retry(judge, case, record["draft"])
                    except Exception as error:  # noqa: BLE001
                        print(f"    ERROR en el juez: {error}")

                record.update({"case": case["id"], "system": system, "rep": rep})
                results["runs"].append(record)
                out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    return results


# --- Reporte ---------------------------------------------------------------------------------

CHECK_LABELS = {
    "intent_ok": "Intención correcta",
    "path_ok": "Recorrido del grafo correcto",
    "auction_ok": "Crea la subasta solo cuando corresponde",
    "price_in_range": "Precio sugerido dentro del rango de referencia",
    "no_invented_price": "No inventa un precio cuando no hay datos",
    "user_price_ok": "Respeta el precio que pidió el usuario",
    "rules_ok": "Publicación cumple las reglas formales",
    "judge_ok": "Publicación sin datos inventados (según el juez)",
}


def mark(value):
    return {True: "✅", False: "❌", None: "–"}[value]


def price(value):
    return "–" if value is None else f"${value:,}".replace(",", ".")


def build_report(results):
    cases = {case["id"]: case for case in CASES}
    runs = [run for run in results["runs"] if run["case"] in cases]
    systems = [s for s in SYSTEMS if any(run["system"] == s for run in runs)]
    for run in runs:
        if run.get("error"):
            run["checks"], run["metrics"], run["passed"] = {}, {"price_error": None}, False
        else:
            run["checks"], run["metrics"], run["passed"] = check(cases[run["case"]], run, run["system"])

    reps = max(run["rep"] for run in runs)
    lines = [
        "# Resultados de la evaluación",
        "",
        f"- Fecha: {results['date']}",
        f"- Modelo: `{results['model']}`",
        f"- Casos: {len({run['case'] for run in runs})} · repeticiones por caso: {reps} · "
        f"corridas: {len(runs)}",
        "",
        "## Resumen",
        "",
        "Cada celda dice en cuántas corridas se cumplió la verificación, sobre las corridas en las que aplica.",
        "",
        "| Métrica | " + " | ".join(SYSTEMS[s] for s in systems) + " |",
        "|---|" + "---|" * len(systems),
    ]

    def by_system(system):
        return [run for run in runs if run["system"] == system]

    def ratio(values):
        values = [v for v in values if v is not None]
        if not values:
            return "–"
        return f"{sum(values)}/{len(values)} ({100 * sum(values) / len(values):.0f}%)"

    rows = [("Casos que pasan todas las verificaciones", [ratio([r["passed"] for r in by_system(s)]) for s in systems])]
    for key, label in CHECK_LABELS.items():
        rows.append((label, [ratio([r["checks"].get(key) for r in by_system(s)]) for s in systems]))

    def mean_of(system, getter, fmt):
        values = [getter(r) for r in by_system(system) if not r.get("error") and getter(r) is not None]
        return fmt(statistics.mean(values)) if values else "–"

    rows += [
        ("Error medio del precio sugerido vs. la mediana de referencia",
         [mean_of(s, lambda r: r["metrics"]["price_error"], lambda v: f"{100 * v:.1f}%") for s in systems]),
        ("Borradores corregidos por el lazo Validador → Subastas (promedio, solo multiagente)",
         [mean_of(s, lambda r: r["retries"] - 1 if r.get("retries") else None, lambda v: f"{v:.2f}")
          if s == "multi" else "–" for s in systems]),
        ("Llamadas al LLM por caso (promedio, sin el juez)",
         [mean_of(s, lambda r: r["llm_calls"], lambda v: f"{v:.1f}") for s in systems]),
        ("Tiempo por caso (promedio)",
         [mean_of(s, lambda r: r["seconds"], lambda v: f"{v:.1f} s") for s in systems]),
        ("Corridas con error de ejecución", [str(sum(1 for r in by_system(s) if r.get("error"))) for s in systems]),
    ]
    lines += [f"| {label} | " + " | ".join(values) + " |" for label, values in rows]

    lines += ["", "## Resultado por caso", ""]
    header = "| Caso | Qué prueba | " + " | ".join(SYSTEMS[s] for s in systems) + " |"
    lines += [header, "|---|---|" + "---|" * len(systems)]
    for case_id, case in cases.items():
        cells = []
        for system in systems:
            case_runs = [r for r in runs if r["case"] == case_id and r["system"] == system]
            if case_runs:
                cells.append(f"{sum(r['passed'] for r in case_runs)}/{len(case_runs)} " + "".join(mark(r["passed"]) for r in case_runs))
            else:
                cells.append("–")
        if any(cell != "–" for cell in cells):
            lines.append(f"| `{case_id}` | {case['description']} | " + " | ".join(cells) + " |")

    if reps > 1:
        lines += [
            "",
            "## Variabilidad entre repeticiones",
            "",
            "Precio sugerido en cada repetición del mismo caso (el LLM no siempre responde lo mismo).",
            "",
            "| Caso | " + " | ".join(SYSTEMS[s] for s in systems) + " |",
            "|---|" + "---|" * len(systems),
        ]
        for case_id, case in cases.items():
            if not case.get("reference_ids"):
                continue
            cells = []
            for system in systems:
                values = [price(r.get("suggested_price")) for r in runs if r["case"] == case_id and r["system"] == system]
                cells.append(", ".join(values) or "–")
            lines.append(f"| `{case_id}` | " + " | ".join(cells) + " |")

    lines += ["", "## Detalle de cada corrida", ""]
    for case_id, case in cases.items():
        case_runs = [r for r in runs if r["case"] == case_id]
        if not case_runs:
            continue
        lines += [f"### `{case_id}`", "", f"**Mensaje:** {case['message']}", ""]
        if case.get("history"):
            lines += ["**Historial:** " + " / ".join(f"{m['role']}: {m['content']}" for m in case["history"]), ""]
        if case.get("reference_ids"):
            prices = reference_prices(case["reference_ids"])
            lines += [f"**Referencia:** ids {case['reference_ids']}, rango {price(min(prices))} a "
                      f"{price(max(prices))}, mediana {price(round(statistics.median(prices)))}", ""]
        for run in case_runs:
            title = f"{SYSTEMS[run['system']]} · rep {run['rep']} · {mark(run['passed'])}"
            lines += ["<details>", f"<summary>{title}</summary>", ""]
            if run.get("error"):
                lines += ["```", run["error"][:1500], "```", "", "</details>", ""]
                continue
            failed = [CHECK_LABELS[k] for k, v in run["checks"].items() if v is False]
            if run.get("path"):
                lines.append(f"- Recorrido: {' → '.join(run['path'])}")
            lines += [
                f"- Intención: `{run.get('intent')}` · precio del usuario: {price(run.get('user_price'))} · "
                f"precio sugerido: {price(run.get('suggested_price'))}",
                f"- Comparables usados: {run.get('comparable_ids')}",
                f"- Llamadas al LLM: {run['llm_calls']} · tiempo: {run['seconds']} s",
            ]
            if run.get("retries"):
                lines.append(f"- Borradores generados: {run['retries']}")
            if run.get("judge_invented"):
                lines.append("- Juez, datos inventados: " + "; ".join(run["judge_invented"]))
            if failed:
                lines.append("- **Falló:** " + "; ".join(failed))
            lines += ["", "Respuesta al usuario:", "", "```", run.get("answer") or "", "```", "", "</details>", ""]

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reps", type=int, default=1, help="repeticiones por caso (default: 1)")
    parser.add_argument("--system", choices=["multi", "single", "both"], default="both")
    parser.add_argument("--cases", nargs="+", help="ids de los casos a correr (default: todos)")
    parser.add_argument("--no-judge", action="store_true", help="no usar el juez (ahorra pedidos al LLM)")
    parser.add_argument("--report", nargs="+", metavar="JSON", help="no corre nada: arma el reporte con estos resultados")
    args = parser.parse_args()

    RESULTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M")

    if args.report:
        loaded = [json.loads(Path(p).read_text(encoding="utf-8")) for p in args.report]
        results = {
            "model": ", ".join(sorted({r["model"] or "?" for r in loaded})),
            "date": ", ".join(r["date"] for r in loaded),
            "runs": [run for r in loaded for run in r["runs"]],
        }
        out_md = RESULTS_DIR / f"{stamp}_combinado.md"
    else:
        cases = [c for c in CASES if not args.cases or c["id"] in args.cases]
        unknown = set(args.cases or []) - {c["id"] for c in CASES}
        if unknown:
            parser.error(f"casos desconocidos: {', '.join(sorted(unknown))}")
        systems = ["multi", "single"] if args.system == "both" else [args.system]
        out_json = RESULTS_DIR / f"{stamp}.json"
        results = evaluate(cases, systems, args.reps, not args.no_judge, out_json)
        out_md = out_json.with_suffix(".md")
        print(f"\nResultados: {out_json}")

    out_md.write_text(build_report(results), encoding="utf-8")
    print(f"Reporte: {out_md}")


if __name__ == "__main__":
    main()
