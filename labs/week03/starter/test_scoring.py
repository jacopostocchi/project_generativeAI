from queries import QUERIES
from router import Decision, Routed
from scoring import score_routes, report

q = {x.id: x for x in QUERIES}
picks = [q["Q-01"], q["Q-20"], q["Q-24"]]   # request, other, request(amb)

def routed(route, applied, conf=0.99, fired=None, ev=True):
    return Routed(decision=Decision(route=route, confidence=conf, evidence="x"),
                  applied_route=applied, policy_fired=fired, evidence_ok=ev)

results = [
    routed("request", "request"),                       # giusta
    routed("info", "info"),                             # sbagliata: other -> info
    routed("request", "complaint", 0.95, "low_confidence"),  # ambigua, policy
]
s = score_routes(results, picks)
print(report(s, "test"))
assert s.hits == 1 and s.total == 3
assert s.per_route["request"] == [1, 2] and s.per_route["other"] == [0, 1]
assert s.confusion[("other", "info")] == 1
assert s.confusion[("request", "complaint")] == 1
assert s.ambiguous_total == 1 and s.ambiguous_hits == 0
assert s.policy_fired["low_confidence"] == 1
print("ok")