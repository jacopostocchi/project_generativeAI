import sys
from statistics import mean

from openai import OpenAI

from project.models import BASE_URL, API_KEY, SMALL
from queries import QUERIES
from router import classify

# Modello da riga di comando, altrimenti SMALL.name.
model = sys.argv[1] if len(sys.argv) > 1 else SMALL.name
client = OpenAI(base_url=BASE_URL, api_key=API_KEY)

rows, invalid = [], []
for q in QUERIES:
    d, meta = classify(client, q.text, model=model)
    if d is None:
        invalid.append((q.id, meta["error"], meta["finish_reason"]))
        continue
    rows.append({
        "id": q.id, "gold": q.route, "pred": d.route,
        "conf": d.confidence, "ev_ok": d.evidence in q.text,
        "amb": q.ambiguous, "ok": d.route == q.route,
    })

rows.sort(key=lambda r: r["conf"])

print(f"model: {model}\n")
print(f"{'conf':>5}  {'id':<5} {'gold':<10} {'pred':<10} {'esito':<10} "
      f"{'evid.':<6} amb")
for r in rows:
    esito = "GIUSTO" if r["ok"] else "SBAGLIATO"
    evid = "ok" if r["ev_ok"] else "NO"
    print(f"{r['conf']:5.2f}  {r['id']:<5} {r['gold']:<10} {r['pred']:<10} "
          f"{esito:<10}{evid:<6} {'Y' if r['amb'] else '-'}")

right = [r["conf"] for r in rows if r["ok"]]
wrong = [r["conf"] for r in rows if not r["ok"]]
print(f"\ngiuste:    {len(right)} su {len(QUERIES)}")
print(f"sbagliate: {len(wrong)}")
print(f"invalide:  {len(invalid)} {invalid}")
if right:
    print(f"confidenza nelle giuste:    min {min(right):.2f}  "
          f"media {mean(right):.2f}  max {max(right):.2f}")
if wrong:
    print(f"confidenza nelle sbagliate: min {min(wrong):.2f}  "
          f"media {mean(wrong):.2f}  max {max(wrong):.2f}")
print(f"valori distinti di confidenza: {sorted(set(r['conf'] for r in rows))}")
print(f"evidenza non trovata nel testo: "
      f"{[r['id'] for r in rows if not r['ev_ok']]}")
