"""
Expression evaluator for the Rules Engine JSON-AST.

Node types:
  literal    — {"type": "literal", "value": <any>}
  field_ref  — {"type": "field_ref", "field": "amount"}
  math       — {"type": "math", "op": "add|subtract|multiply|divide|modulo|power",
                "left": expr, "right": expr}
  func       — {"type": "func", "name": "now|today|len|upper|lower|concat|coalesce|if|round|abs",
                "args": [...]}

Security limits:
  - Max nesting depth: 15
  - No I/O, no imports, no exec/eval
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

_MAX_DEPTH = 15
_SAFE_MATH_OPS = {"add", "subtract", "multiply", "divide", "modulo", "power"}
_SAFE_FUNCS = {"now", "today", "len", "upper", "lower", "concat", "coalesce", "if", "round", "abs"}


class ExpressionError(Exception):
    pass


def evaluate(node: dict[str, Any], context: dict[str, Any], _depth: int = 0) -> Any:
    """Recursively evaluate an expression node. Returns a Python value."""
    if _depth > _MAX_DEPTH:
        raise ExpressionError("Expression nesting depth exceeded")

    if not isinstance(node, dict):
        # Raw literal shorthand — accept plain Python values as-is
        return node

    node_type = node.get("type")

    match node_type:
        case "literal":
            return node.get("value")

        case "field_ref":
            field = node.get("field")
            if not isinstance(field, str):
                raise ExpressionError("field_ref.field must be a string")
            return context.get(field)

        case "math":
            op = node.get("op")
            if op not in _SAFE_MATH_OPS:
                raise ExpressionError(f"Unknown math op: {op!r}")
            left = _to_number(evaluate(node["left"], context, _depth + 1), "left")
            right = _to_number(evaluate(node["right"], context, _depth + 1), "right")
            return _apply_math(op, left, right)

        case "func":
            name = node.get("name")
            if name not in _SAFE_FUNCS:
                raise ExpressionError(f"Unknown function: {name!r}")
            args = [evaluate(a, context, _depth + 1) for a in node.get("args", [])]
            return _apply_func(name, args)

        case _:
            raise ExpressionError(f"Unknown expression type: {node_type!r}")


def _to_number(val: Any, label: str) -> float:
    if isinstance(val, int | float):
        return float(val)
    try:
        return float(val)
    except (TypeError, ValueError) as exc:
        raise ExpressionError(f"{label} is not a number: {val!r}") from exc


def _apply_math(op: str, left: float, right: float) -> float:
    match op:
        case "add":
            return left + right
        case "subtract":
            return left - right
        case "multiply":
            return left * right
        case "divide":
            if right == 0:
                raise ExpressionError("Division by zero")
            return left / right
        case "modulo":
            if right == 0:
                raise ExpressionError("Modulo by zero")
            return left % right
        case "power":
            result = left**right
            try:
                return float(result)
            except TypeError as exc:  # negative base with a fractional exponent -> complex
                raise ExpressionError("power produced a non-real result") from exc
        case _:
            raise ExpressionError(f"Unknown op: {op}")  # unreachable


def _apply_func(name: str, args: list[Any]) -> Any:
    match name:
        case "now":
            return datetime.now(UTC).isoformat()
        case "today":
            return date.today().isoformat()
        case "len":
            if not args:
                raise ExpressionError("len() requires 1 argument")
            val = args[0]
            return len(val) if isinstance(val, str | list | dict) else 0
        case "upper":
            return str(args[0]).upper() if args else ""
        case "lower":
            return str(args[0]).lower() if args else ""
        case "concat":
            return "".join(str(a) for a in args)
        case "coalesce":
            for a in args:
                if a is not None:
                    return a
            return None
        case "if":
            # if(condition, then_value, else_value)
            if len(args) < 2:
                raise ExpressionError("if() requires 2-3 arguments")
            cond, then_val = args[0], args[1]
            else_val = args[2] if len(args) > 2 else None
            return then_val if cond else else_val
        case "round":
            if not args:
                raise ExpressionError("round() requires 1-2 arguments")
            ndigits = int(args[1]) if len(args) > 1 else 0
            return round(float(args[0]), ndigits)
        case "abs":
            if not args:
                raise ExpressionError("abs() requires 1 argument")
            return abs(float(args[0]))
        case _:
            raise ExpressionError(f"Unknown function: {name}")  # unreachable
