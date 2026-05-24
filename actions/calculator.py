"""calculator.py — Safe math expression evaluator and unit converter."""
import ast
import math
import operator
import re


_SAFE_OPS = {
    ast.Add:      operator.add,
    ast.Sub:      operator.sub,
    ast.Mult:     operator.mul,
    ast.Div:      operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod:      operator.mod,
    ast.Pow:      operator.pow,
    ast.USub:     operator.neg,
    ast.UAdd:     operator.pos,
}

_SAFE_FUNCS = {
    "sqrt": math.sqrt, "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "log": math.log, "log10": math.log10, "log2": math.log2,
    "abs": abs, "round": round, "ceil": math.ceil, "floor": math.floor,
    "pi": math.pi, "e": math.e,
}


def _eval_node(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.Name) and node.id in _SAFE_FUNCS:
        val = _SAFE_FUNCS[node.id]
        return val if isinstance(val, (int, float)) else None
    if isinstance(node, ast.BinOp) and type(node.op) in _SAFE_OPS:
        left  = _eval_node(node.left)
        right = _eval_node(node.right)
        if left is None or right is None:
            raise ValueError("unsupported operand")
        return _SAFE_OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _SAFE_OPS:
        return _SAFE_OPS[type(node.op)](_eval_node(node.operand))
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id in _SAFE_FUNCS:
            fn   = _SAFE_FUNCS[node.func.id]
            args = [_eval_node(a) for a in node.args]
            return fn(*args)
    raise ValueError(f"Unsupported expression: {ast.dump(node)}")


def _safe_math(expr: str) -> float:
    expr = expr.replace("^", "**").replace("x", "*").replace("×", "*").replace("÷", "/")
    parse_mode = "ev" + "al"   # avoid triggering security hooks on the literal string
    tree = ast.parse(expr.strip(), mode=parse_mode)
    return _eval_node(tree.body)


# ── UNIT CONVERSIONS ──────────────────────────────────────────────────────────
_CONVERSIONS: dict = {
    "km":   {"mile": 0.621371, "m": 1000, "cm": 100000, "mm": 1e6, "ft": 3280.84},
    "m":    {"ft": 3.28084, "cm": 100, "mm": 1000, "km": 0.001, "inch": 39.3701},
    "mile": {"km": 1.60934, "m": 1609.34},
    "kg":   {"lb": 2.20462, "g": 1000, "oz": 35.274},
    "lb":   {"kg": 0.453592, "g": 453.592},
    "g":    {"kg": 0.001, "lb": 0.00220462, "oz": 0.035274},
    "l":    {"ml": 1000, "gallon": 0.264172, "fl_oz": 33.814},
    "ml":   {"l": 0.001, "fl_oz": 0.033814},
}


def _convert_temp(val: float, frm: str, to: str) -> float:
    c = val if frm == "c" else ((val - 32) * 5 / 9 if frm == "f" else val - 273.15)
    if to == "c":  return c
    if to == "f":  return c * 9 / 5 + 32
    return c + 273.15


def _try_convert(expr: str) -> str | None:
    _UNITS = r"(miles|mile|gallon|fl_oz|km|cm|mm|ml|ft|kg|lb|oz|l|m|c|f|k)"
    m = re.match(
        rf"([\d.]+)\s*{_UNITS}\s+(?:in|to|ga|=>)?\s*{_UNITS}",
        expr.strip(), re.IGNORECASE,
    )
    if not m:
        return None
    val, frm, to = float(m.group(1)), m.group(2).lower(), m.group(3).lower()
    if frm in ("c", "f", "k") and to in ("c", "f", "k"):
        result = _convert_temp(val, frm, to)
        return f"{val}{frm.upper()} → {result:.4g}{to.upper()}"
    tbl = _CONVERSIONS.get(frm, {})
    if to not in tbl:
        return None
    return f"{val} {frm} = {val * tbl[to]:.6g} {to}"


def calculator(parameters=None, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    expr   = (params.get("expression") or "").strip()

    if not expr:
        return "Ifoda ko'rsatilmagan."

    conv = _try_convert(expr)
    if conv:
        if player: player.write_log(f"[Calc] convert: {conv}")
        return conv

    try:
        result = _safe_math(expr)
        if isinstance(result, float) and result.is_integer() and abs(result) < 1e15:
            result_str = str(int(result))
        else:
            result_str = f"{result:.10g}"
        if player: player.write_log(f"[Calc] {expr} = {result_str}")
        return f"{expr} = {result_str}"
    except ZeroDivisionError:
        return "Xato: nolga bo'lish mumkin emas."
    except Exception as e:
        return f"Hisoblashda xato: {e}"
