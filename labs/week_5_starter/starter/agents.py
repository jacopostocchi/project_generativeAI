"""The three agents, on Pydantic AI. TODO 1 to 5.

This is the week the hand-rolled loop of weeks 1 to 4 gives way to a
framework. Read the week 4 `agent.py` next to this file: the loop, the
message list, the tool dispatch, and the schema envelope are all gone. What
is left is the part that was always the design.

Nothing underneath has changed. Pydantic AI is making the same calls to the
same endpoint in the same wire format. That is why you wrote the loop first.
"""

from __future__ import annotations

import time
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.exceptions import UnexpectedModelBehavior

from repo import Work, apply_fix, diff_summary, run_tests

from project.models import LARGE, pydantic_ai_model

MODEL = pydantic_ai_model(LARGE)


# --------------------------------------------------------------------------
# TODO 1. The plan schema, and a warning about its shape.
# --------------------------------------------------------------------------
#
# The obvious schema for a plan is a list of structured steps:
#
#     class Step(BaseModel):
#         tool: Literal[...]
#         argument: str
#         why: str
#
# It fails on this model, every time, with "Exceeded maximum output
# retries". A flat list of strings works. That is measured, not folklore.


class Plan(BaseModel):
    """TODO 1. Three fields: a goal, the steps, and the file you suspect.

    Read the comment above before you choose the type of `steps`. The
    obvious answer, a list of nested Step objects, does not work on this
    model. Keep it flat.
    """

    goal: str
    steps: list[str]
    suspect_file: str
    # TODO 1a: steps. Flat. What is the simplest type that still says
    #          "several ordered steps"?
    # TODO 1b: suspect_file. The file most likely to contain the bug.


planner = Agent(MODEL, output_type=Plan, retries=3,
                system_prompt=(
    "You plan a small change to a Python repository. You have NO tools and "
    "you must not attempt to act: you are producing a plan that a person "
    "will read before anything runs.\n"
    "Keep it to between two and six steps, one sentence each, and make one "
    "of them run the tests. Name the file you suspect as a bare filename, "
    "one of booking.py, discounts.py, pricing.py, report.py.\n"
    "Reply with a single JSON object with exactly the keys goal, steps and "
    "suspect_file, and nothing else."))


# --------------------------------------------------------------------------
# TODO 2. Validating the plan, for free, before anything runs.
# --------------------------------------------------------------------------

KNOWN_FILES = {"booking.py", "discounts.py", "pricing.py", "report.py"}


def validate_plan(plan: Plan) -> tuple[bool, list[str]]:
    """TODO 2. Four free checks. No model, no cost, run before anything else.

    Return (ok, problems). Check that:

      * the step count is inside a range you choose and can defend
      * `suspect_file` names a file that actually exists in the repository
      * some step runs the tests, because a plan with no verification step
        has no way of knowing whether it worked
      * no step proposes editing a test, which `apply_fix` refuses anyway

    A plan is an artifact you inspect. Inspecting it takes fifteen seconds
    and catches most of the failures you would otherwise spend the session
    debugging.

    Decide what happens on a failed check, repair once or refuse, and write
    the decision in DECISIONS.md.
    """

    import re

    MIN_STEPS, MAX_STEPS = 2, 6  # 1 step cannot both change and verify; >6 is thrashing

    _RUNS_TESTS = re.compile(
        r"\b(run|rerun|re-run|execute|verify|confirm)\b.*\btests?\b"
        r"|\bpytest\b|\brun_tests\b|\btest suite\b", re.I)
    _EDIT_VERB = re.compile(
        r"\b(edit|modify|change|update|rewrite|replace|patch|adjust|fix)\b", re.I)
    _TEST_FILE = re.compile(r"\btests/|\btest_\w+\.py\b|\bconftest\.py\b", re.I)

    problems: list[str] = []
    n = len(plan.steps)
    if not MIN_STEPS <= n <= MAX_STEPS:
        problems.append(f"{n} steps; expected {MIN_STEPS} to {MAX_STEPS}")

    if plan.suspect_file not in KNOWN_FILES:
        problems.append(f"suspect_file {plan.suspect_file!r} is not one of "
                        f"{sorted(KNOWN_FILES)}")

    if not any(_RUNS_TESTS.search(s) for s in plan.steps):
        problems.append("no step runs the tests, so the plan cannot verify itself")

    for i, s in enumerate(plan.steps, 1):
        if _EDIT_VERB.search(s) and _TEST_FILE.search(s):
            problems.append(f"step {i} edits a test file: {s!r}")

    return (not problems, problems)


# --------------------------------------------------------------------------
# TODO 3. The fix, as a proposal rather than an edit.
# --------------------------------------------------------------------------
#
# The executor does not edit the file. It proposes exactly one line change
# and `repo.apply_fix` decides whether to apply it.
#
# That is a deliberate narrowing and it is the difference between a session
# that works and one that does not. Given free-form editing tools, this model
# thrashes: measured at 32 and 38 tool calls, three to four minutes, and zero
# successful fixes in three attempts. Given one structured proposal, it is
# correct three times in four.
#
# The engineering point generalizes past this lab. The narrower the action
# your agent can take, the more reliably it takes it, and the easier it is to
# check before it happens. "Give the agent a shell" is the widest possible
# action and it is why coding agents are hard.

class Fix(BaseModel):
    """TODO 3. One proposed line change.

    Four fields: the path, the exact line to replace, the corrected line,
    and why. The description you give `old_line` matters more than the type
    does, because `repo.apply_fix` refuses the edit unless that string
    appears in the file character for character.
    """

    # TODO 3a: path, old_line, new_line, why
    path: str = Field(description="Bare filename of the source file, e.g. discounts.py.")
    old_line: str = Field(
        description="The single wrong line, copied character for character from "
                    "the file shown, including its leading indentation. No line "
                    "number, no surrounding lines, no trailing newline, no edits.")
    new_line: str = Field(
        description="The corrected line, with the same indentation as old_line.")
    why: str = Field(description="One sentence: what was wrong with the logic.")


fixer = Agent(MODEL, output_type=Fix, retries=3,
              system_prompt=(
    "You propose exactly ONE line change that makes a failing test pass.\n"
    "You are given the whole file. Return the single wrong line, copied "
    "character for character, and the corrected version of it.\n"
    "Change the logic that is wrong. Do not change a constant to compensate "
    "for a wrong comparison, and never propose a change to a test."))


# --------------------------------------------------------------------------
# TODO 4. The baseline, for comparison. Given complete: read it.
# --------------------------------------------------------------------------

class Work_(BaseModel):
    root_str: str
    model_config = {"frozen": True}


baseline = Agent(MODEL, system_prompt=(
    "You fix a bug in a small Python repository using the tools provided.\n"
    "run_tests to see the failure, read_file to look at the source, "
    "replace_line to change one line, run_tests again to confirm.\n"
    "Never edit anything under tests/. Stop as soon as the tests pass."))


@baseline.tool
def list_files(ctx: RunContext[Work]) -> list[str]:
    """List the Python files in the repository."""
    return ctx.deps.files()


@baseline.tool
def read_file(ctx: RunContext[Work], path: str) -> str:
    """Read one file, by a path relative to the repository root."""
    return ctx.deps.read(path)


@baseline.tool
def replace_line(ctx: RunContext[Work], path: str, old_line: str,
                 new_line: str) -> str:
    """Replace one exact line. The old line must appear exactly once."""
    return apply_fix(ctx.deps, path, old_line, new_line)


@baseline.tool
def run_the_tests(ctx: RunContext[Work]) -> str:
    """Run the test suite and return its output."""
    return run_tests(ctx.deps).output


# --------------------------------------------------------------------------
# TODO 5. The reviewer, which is the second agent.
# --------------------------------------------------------------------------

class Verdict(BaseModel):
    decision: Literal["approve", "reject"]
    reason: str = Field(max_length=200)


# TODO 5. Write the reviewer's instructions.
#
# It is given the diff and the failing test output, and nothing else. Decide
# what it should reject. At least one of the things it must catch is a change
# that makes the failing test pass while being wrong anyway, and the fixer
# really does propose one sometimes.
#
# Do NOT give it the fixer's reasoning. If it inherits the reasoning it
# inherits the mistake, and the second opinion stops being a second opinion.

reviewer = Agent(MODEL, output_type=Verdict, retries=3,
                 system_prompt=(
    "You review a one-line change to a Python library. You see only the diff "
    "and the output of the test that was failing before it. You do not know "
    "why the author made the change, and you should not guess charitably.\n"
    "The failing test describes the intended behaviour. Judge the change "
    "against that intent, not against whether the test now passes.\n"
    "REJECT if any of these hold:\n"
    "- it touches a test file or a test's expected value;\n"
    "- it moves a constant or threshold (for example an hour, a price, a "
    "boundary) instead of correcting the comparison or logic that uses it, "
    "since that can make the test pass while billing other times wrongly;\n"
    "- it special-cases the tested value (e.g. `== 20`) rather than fixing "
    "the general rule;\n"
    "- it changes behaviour unrelated to the failing test;\n"
    "- the change does not plausibly explain the failure shown.\n"
    "APPROVE only a minimal correction of the faulty logic that matches the "
    "intended behaviour at the boundary and on both sides of it.\n"
    "Reply with a single JSON object and nothing else, in this form: "
    '{"decision": "reject", "reason": "one sentence, at most 150 characters"}.'))


# --------------------------------------------------------------------------
# What the reviewer is NOT given, and why it matters
# --------------------------------------------------------------------------
#
# It does not see the fixer's reasoning. It sees the artifact and the test
# output. If it inherited the reasoning it would inherit the mistake, and the
# second opinion would stop being a second opinion. That is the mechanism
# behind the critic pattern and it is the thing worth demonstrating today.


def error_detail(exc: Exception) -> str:
    """The validation error behind an exhausted-retries exception."""
    return str(exc.__cause__ or exc)[:400]


async def _run(agent, prompt: str, out: dict, label: str):
    """Run one agent. If its output never validates, record it and return None."""
    try:
        r = await agent.run(prompt)
    except UnexpectedModelBehavior as exc:
        out["failure"] = f"{label} output invalid after retries"
        out["failure_detail"] = error_detail(exc)
        return None
    out["tokens"] += r.usage.total_tokens or 0
    return r


async def propose(work: Work, task: str, use_plan: bool) -> dict:
    """One attempt: optionally plan, then propose a fix.

    out["fix"] is None when the attempt failed, and out["failure"] says why:
    the planner's output never validated, validate_plan refused the plan
    after one repair, or the fixer's output never validated.
    """
    out: dict = {"plan": None, "plan_ok": None, "plan_problems": [],
                 "plan_repaired": False, "fix": None, "applied": None,
                 "failure": None, "failure_detail": None, "tokens": 0}
    t0 = time.perf_counter()

    def done() -> dict:
        out["seconds"] = time.perf_counter() - t0
        return out

    context = ""
    if use_plan:
        r = await _run(planner, task, out, "planner")
        if r is None:
            return done()
        ok, problems = validate_plan(r.output)
        if not ok:
            # Repair once, feeding the problems back to the planner.
            out["plan_repaired"] = True
            r = await _run(
                planner,
                f"{task}\n\nYour previous plan was rejected:\n- "
                + "\n- ".join(problems) + "\nReturn a corrected plan.",
                out, "planner")
            if r is None:
                return done()
            ok, problems = validate_plan(r.output)
        out["plan"], out["plan_ok"], out["plan_problems"] = (
            r.output, ok, problems)
        if not ok:
            out["failure"] = "plan refused by validate_plan"
            return done()
        context = (f"A plan has already been made. Suspect file: "
                   f"{r.output.suspect_file}. Goal: {r.output.goal}\n")
        source_name = r.output.suspect_file
    else:
        source_name = "discounts.py"

    failing = run_tests(work).output
    source = work.read(source_name)
    prompt = (f"{context}File {source_name}:\n{source}\n\n"
              f"Failing test output:\n{failing}\n\n{task}")
    r = await _run(fixer, prompt, out, "fixer")
    if r is None:
        return done()
    out["fix"] = r.output
    return done()