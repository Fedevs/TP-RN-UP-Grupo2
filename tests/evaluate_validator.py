"""Prueba del Validador con el LLM real, usando borradores hechos a mano.

En la evaluación de punta a punta (evaluate.py), Subastas casi no inventa datos, así que el
Validador casi nunca tiene algo que rechazar y no se puede medir si los detecta. Esta prueba
le da directamente borradores escritos a propósito: 5 fieles a lo que dijo el usuario
y 7 con un dato inventado. Todos cumplen las reglas formales (largo, precio,
categoría), así que lo que se mide es solo la parte del LLM.

Métricas:
- Detección: de los borradores con datos inventados, cuántos rechazó.
- Falsas alarmas: de los borradores correctos, cuántos rechazó sin motivo.

Uso (desde la raíz del repo):
    python tests/evaluate_validator.py            # 1 repetición (12 pedidos a Gemini)
    python tests/evaluate_validator.py --reps 3
"""

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from agents.validator import check_rules, validator  # noqa: E402

PS5 = {"name": "PlayStation 5", "category": "consoles", "condition": "used", "details": "2 joysticks, poco uso"}
IPHONE = {"name": "iPhone 13 128GB", "category": "phones", "condition": "used", "details": "batería al 85%"}
MACBOOK = {"name": "MacBook Air M1 8GB 256GB", "category": "laptops", "condition": "used", "details": None}
BICI = {"name": "Mountain bike Venzo rodado 29", "category": "bicycles", "condition": "used", "details": None}
CATAN = {"name": "Catan", "category": "other", "condition": None, "details": "completo"}


def draft(title, description, category, price):
    return {"title": title, "description": description, "category": category,
            "starting_price": price, "duration_days": 7}


# (id, mensaje del usuario, producto, borrador, dato inventado o None si el borrador es correcto)
CASES = [
    ("ps5_ok", "Quiero subastar mi PS5 con 2 joysticks, la usé poco", PS5,
     draft("PlayStation 5 con 2 joysticks", "Vendo mi PlayStation 5 usada, con poco uso. Incluye 2 joysticks. "
           "Aprovechá esta oportunidad para sumarla a tu casa.", "consoles", 450000), None),
    ("ps5_impecable", "Quiero subastar mi PS5 con 2 joysticks, la usé poco", PS5,
     draft("PlayStation 5 impecable con 2 joysticks", "Vendo mi PlayStation 5 en estado impecable, con poco uso. "
           "Incluye 2 joysticks. Aprovechá esta oportunidad.", "consoles", 450000), "estado impecable"),
    ("ps5_caja", "Quiero subastar mi PS5 con 2 joysticks, la usé poco", PS5,
     draft("PlayStation 5 con 2 joysticks y caja", "Vendo mi PlayStation 5 usada, con poco uso. Incluye 2 joysticks "
           "y la caja original. Aprovechá esta oportunidad.", "consoles", 450000), "caja original"),
    ("iphone_ok", "Quiero subastar mi iPhone 13 de 128GB, batería al 85%", IPHONE,
     draft("iPhone 13 128GB batería 85%", "Vendo mi iPhone 13 de 128GB, usado. La batería está al 85%. "
           "Consultá lo que necesites antes de ofertar.", "phones", 525000), None),
    ("iphone_pantalla", "Quiero subastar mi iPhone 13 de 128GB, batería al 85%", IPHONE,
     draft("iPhone 13 128GB batería 85%", "Vendo mi iPhone 13 de 128GB, usado. La batería está al 85% y la "
           "pantalla no tiene ni un rayón. Consultá lo que necesites.", "phones", 525000), "pantalla sin rayones"),
    ("macbook_ok", "Subasto mi MacBook Air M1 de 8GB y 256GB", MACBOOK,
     draft("MacBook Air M1 8GB 256GB", "Vendo mi MacBook Air M1 con 8GB de RAM y 256GB de almacenamiento, usada. "
           "Consultá lo que necesites antes de ofertar.", "laptops", 725000), None),
    ("macbook_cargador", "Subasto mi MacBook Air M1 de 8GB y 256GB", MACBOOK,
     draft("MacBook Air M1 8GB 256GB con cargador", "Vendo mi MacBook Air M1 con 8GB de RAM y 256GB, usada. "
           "Incluye el cargador original y una funda. Consultá lo que necesites.", "laptops", 725000),
     "cargador original y funda"),
    ("bici_ok", "Quiero subastar mi mountain bike Venzo rodado 29, usada", BICI,
     draft("Mountain bike Venzo rodado 29", "Vendo mi mountain bike Venzo rodado 29, usada. "
           "Aprovechá esta oportunidad para salir a pedalear.", "bicycles", 400000), None),
    ("bici_cubiertas", "Quiero subastar mi mountain bike Venzo rodado 29, usada", BICI,
     draft("Mountain bike Venzo rodado 29", "Vendo mi mountain bike Venzo rodado 29, usada, con cubiertas nuevas "
           "y frenos a disco. Aprovechá esta oportunidad.", "bicycles", 400000), "cubiertas nuevas y frenos a disco"),
    ("catan_ok", "Quiero subastar mi juego de mesa Catan completo", CATAN,
     draft("Juego de mesa Catan completo", "Vendo mi juego de mesa Catan, completo. Ideal para jugar en familia "
           "o con amigos. Consultá lo que necesites.", "other", 40000), None),
    ("catan_sellado", "Quiero subastar mi juego de mesa Catan completo", CATAN,
     draft("Juego de mesa Catan completo y sellado", "Vendo mi juego de mesa Catan completo, nunca jugado y todavía "
           "en su caja sellada. Consultá lo que necesites.", "other", 40000), "nunca jugado, caja sellada"),
    ("catan_expansion", "Quiero subastar mi juego de mesa Catan completo", CATAN,
     draft("Juego de mesa Catan completo con expansión", "Vendo mi juego de mesa Catan completo, junto con la "
           "expansión Navegantes. Consultá lo que necesites.", "other", 40000), "expansión Navegantes"),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reps", type=int, default=1)
    args = parser.parse_args()

    for case_id, _, _, case_draft, _ in CASES:
        assert check_rules(case_draft) == [], f"{case_id} no cumple las reglas formales: {check_rules(case_draft)}"

    rows = []
    for rep in range(1, args.reps + 1):
        for case_id, message, product, case_draft, invented in CASES:
            print(f"rep {rep}  {case_id}")
            state = {"message": message, "history": [], "product": product, "draft": case_draft}
            try:
                result = validator(state)["validation"]
            except Exception as error:  # noqa: BLE001
                if "429" in str(error) or "RESOURCE_EXHAUSTED" in str(error):
                    print("    Cuota de Gemini agotada, espero 60 segundos y reintento...")
                    time.sleep(60)
                    result = validator(state)["validation"]
                else:
                    raise
            rows.append({"rep": rep, "id": case_id, "invented": invented,
                         "approved": result["approved"], "issues": result["issues"]})

    bad = [r for r in rows if r["invented"]]
    good = [r for r in rows if not r["invented"]]
    detected = sum(not r["approved"] for r in bad)
    false_alarms = sum(not r["approved"] for r in good)

    lines = [
        "# Prueba del Validador con borradores hechos a mano",
        "",
        f"- Fecha: {datetime.now().isoformat(timespec='seconds')}",
        f"- Borradores: {len(CASES)} ({sum(1 for c in CASES if c[4])} con un dato inventado) · "
        f"repeticiones: {args.reps}",
        "",
        "| Métrica | Resultado |",
        "|---|---|",
        f"| Detección: borradores con datos inventados que rechazó | {detected}/{len(bad)} ({100 * detected / len(bad):.0f}%) |",
        f"| Falsas alarmas: borradores correctos que rechazó | {false_alarms}/{len(good)} ({100 * false_alarms / len(good):.0f}%) |",
        "",
        "| Rep | Borrador | Dato inventado | Resultado | Problemas que reportó |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        ok = (not r["approved"]) == bool(r["invented"])
        verdict = ("rechazado" if not r["approved"] else "aprobado") + (" ✅" if ok else " ❌")
        issues = "; ".join(r["issues"]).replace("|", "/") or "–"
        lines.append(f"| {r['rep']} | `{r['id']}` | {r['invented'] or '–'} | {verdict} | {issues} |")

    out_dir = Path(__file__).parent / "results"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"{datetime.now().strftime('%Y-%m-%d_%H-%M')}_validador.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nDetección: {detected}/{len(bad)} · Falsas alarmas: {false_alarms}/{len(good)}")
    print(f"Reporte: {out}")


if __name__ == "__main__":
    main()
