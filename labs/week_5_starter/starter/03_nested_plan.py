"""DECISIONS entry 1: try the nested plan schema, and record what happens.

    PYTHONPATH=../../.. python 03_nested_plan.py

The brief says a list of nested Step objects fails every time on this model.
Three tries, same task, same model. Report the count either way.
"""

from __future__ import annotations

import asyncio
from typing import Literal

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.exceptions import UnexpectedModelBehavior

from agents import MODEL, error_detail

TASK = ("A test is failing. The off-peak discount is meant to apply to "
        "bookings that start at 20:00 or later, but a booking starting "
        "exactly at 20:00 does not receive it. Fix the bug. Do not change "
        "any test file.")


class Step(BaseModel):
    tool: Literal["list_files", "read_file", "replace_line", "run_tests"]
    argument: str
    why: str


class NestedPlan(BaseModel):
    goal: str
    steps: list[Step]
    suspect_file: str


nested = Agent(MODEL, output_type=NestedPlan, retries=3, system_prompt=(
    "You plan a small change to a Python repository. You have NO tools and "
    "you must not attempt to act: you are producing a plan that a person "
    "will read before anything runs.\n"
    "Keep it to between two and six steps. Name the file you suspect."))


async def main() -> None:
    ok = 0
    for i in range(1, 4):
        try:
            r = await nested.run(TASK)
            ok += 1
            print(f"try {i}: valid, {len(r.output.steps)} steps")
        except UnexpectedModelBehavior as exc:
            print(f"try {i}: FAILED after retries: {error_detail(exc)[:200]}")
    print(f"\nnested schema valid in {ok} of 3 tries")


asyncio.run(main())