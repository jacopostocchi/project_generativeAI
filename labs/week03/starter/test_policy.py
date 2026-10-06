from router import Decision, apply_policy

text = "The door is open. Someone must come."

def d(route="request", conf=0.99, ev="The door is open."):
    return Decision(route=route, confidence=conf, evidence=ev)

a = apply_policy(None, text)
b = apply_policy(d(ev="invented span"), text)
c = apply_policy(d(conf=0.5), text)
e = apply_policy(d(), text)

print(a.policy_fired, a.applied_route)
print(b.policy_fired, b.applied_route, b.evidence_ok)
print(c.policy_fired, c.applied_route)
print(e.policy_fired, e.applied_route)

assert a.policy_fired == "no_decision"
assert b.policy_fired == "evidence" and b.evidence_ok is False
assert c.policy_fired == "low_confidence"
assert e.policy_fired is None and e.applied_route == "request"
print("ok")