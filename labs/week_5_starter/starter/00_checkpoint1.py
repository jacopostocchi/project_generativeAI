"""Checkpoint 1 checks that need no model. Run from the starter/ folder."""

from repo import Work, apply_fix, run_tests
from agents import Plan, validate_plan

# 1. the suite on a fresh copy
w = Work.fresh()
r = run_tests(w)
print(r.passed, r.ran, r.failures)
print(r.output)  # which test fails, and which module does it point at?

# 2. apply_fix refusing
print(apply_fix(w, "tests/test_discounts.py", "x", "y"))            # test file
print(apply_fix(w, "discounts.py", "questa riga non esiste", "y"))  # absent line
w.cleanup()

# 3. a deliberately broken plan
bad = Plan(goal="x", steps=["Edit tests/test_discounts.py"],
           suspect_file="foo.py")
print(validate_plan(bad))