"""math_solver.py — Symbolic math via sympy (algebra, calculus, equations).

Falls back to AST-based safe arithmetic evaluator if sympy is not installed.
"""
import ast
import math
import operator


# ── AST-based safe arithmetic evaluator (no eval/exec) ───────────────────────

_SAFE_FUNCS = {
    "sqrt": math.sqrt, "abs": abs, "round": round,
    "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "asin": math.asin, "acos": math.acos, "atan": math.atan,
    "log": math.log, "log2": math.log2, "log10": math.log10,
    "exp": math.exp, "floor": math.floor, "ceil": math.ceil,
    "pi": math.pi, "e": math.e,
}

_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
}

_UNARY_OPS = {
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _eval_node(node):
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.Name):
        if node.id in _SAFE_FUNCS:
            return _SAFE_FUNCS[node.id]
        raise ValueError(f"Ruxsatsiz nom: '{node.id}'")
    if isinstance(node, ast.BinOp):
        op = _BIN_OPS.get(type(node.op))
        if op is None:
            raise ValueError(f"Ruxsatsiz operator: {type(node.op).__name__}")
        return op(_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp):
        op = _UNARY_OPS.get(type(node.op))
        if op is None:
            raise ValueError(f"Ruxsatsiz unary operator")
        return op(_eval_node(node.operand))
    if isinstance(node, ast.Call):
        func = _eval_node(node.func)
        if not callable(func):
            raise ValueError("Chaqirish mumkin bo'lmagan ob'ekt")
        args = [_eval_node(a) for a in node.args]
        return func(*args)
    raise ValueError(f"Ruxsatsiz AST turi: {type(node).__name__}")


def _safe_eval(expr: str) -> str:
    clean = expr.strip().replace("^", "**").replace(",", "")
    try:
        tree = ast.parse(clean, mode="eval")
        result = _eval_node(tree)
        val = float(result)
        if val == int(val) and abs(val) < 1e15:
            return str(int(val))
        return f"{val:.10g}"
    except (ValueError, ZeroDivisionError, OverflowError) as e:
        return f"Hisob xatosi: {e}"
    except SyntaxError:
        return f"Noto'g'ri ifoda: {expr}"


# ── Sympy-based solver ────────────────────────────────────────────────────────

def _sympy_solve(params: dict) -> str:
    import sympy as sp
    from sympy.parsing.sympy_parser import (
        parse_expr, standard_transformations,
        implicit_multiplication_application,
    )

    transforms = standard_transformations + (implicit_multiplication_application,)
    action   = params.get("action", "solve").lower()
    expr_str = (params.get("expression") or params.get("equation") or params.get("expr") or "").strip()

    if not expr_str:
        return "Ifoda yoki tenglamani ko'rsating."

    var_str = (params.get("variable") or params.get("var") or "x").strip()

    try:
        # ^ → ** so users can write x^2 naturally
        expr_str = expr_str.replace("^", "**")
        var        = sp.Symbol(var_str)
        local_dict = {var_str: var}

        if action in ("solve", "yech", "yeching"):
            if "=" in expr_str:
                lhs, rhs = expr_str.split("=", 1)
                lhs_e = parse_expr(lhs.strip(), local_dict=local_dict, transformations=transforms)
                rhs_e = parse_expr(rhs.strip(), local_dict=local_dict, transformations=transforms)
                eq = sp.Eq(lhs_e, rhs_e)
            else:
                eq = parse_expr(expr_str, local_dict=local_dict, transformations=transforms)
            solutions = sp.solve(eq, var)
            if not solutions:
                return f"{expr_str} — yechim topilmadi."
            return f"{expr_str}\n{var_str} = {', '.join(str(sp.simplify(s)) for s in solutions)}"

        if action in ("simplify", "soddalash"):
            e = parse_expr(expr_str, local_dict=local_dict, transformations=transforms)
            return f"Soddalashtirildi: {sp.simplify(e)}"

        if action in ("expand", "yoy"):
            e = parse_expr(expr_str, local_dict=local_dict, transformations=transforms)
            return f"Yoyildi: {sp.expand(e)}"

        if action in ("factor", "ko'paytuvchi"):
            e = parse_expr(expr_str, local_dict=local_dict, transformations=transforms)
            return f"Ko'paytuvchilarga ajratildi: {sp.factor(e)}"

        if action in ("diff", "derivative", "hosila", "differentiate"):
            e     = parse_expr(expr_str, local_dict=local_dict, transformations=transforms)
            order = int(params.get("order") or 1)
            d     = sp.diff(e, var, order)
            return f"d/d{var_str}({expr_str}) = {d}"

        if action in ("integrate", "integral"):
            consts = {"e": sp.E, "pi": sp.pi, "i": sp.I, "inf": sp.oo}
            e = parse_expr(expr_str, local_dict={**local_dict, **consts}, transformations=transforms)
            a = params.get("from")
            b = params.get("to")
            if a is not None and b is not None:
                a_e = parse_expr(str(a), local_dict=consts, transformations=transforms)
                b_e = parse_expr(str(b), local_dict=consts, transformations=transforms)
                result = sp.integrate(e, (var, a_e, b_e))
                return f"∫({expr_str}) [{a}..{b}] = {sp.simplify(result)}"
            result = sp.integrate(e, var)
            return f"∫({expr_str}) d{var_str} = {result} + C"

        if action in ("eval", "calculate", "hisob"):
            consts = {"e": sp.E, "pi": sp.pi, "i": sp.I, "inf": sp.oo}
            e = parse_expr(expr_str, local_dict=consts, transformations=transforms)
            result = e.evalf()
            return f"{expr_str} = {float(result):g}"

        return f"Noma'lum amal: {action}. Amallar: solve|simplify|expand|factor|diff|integrate|eval"

    except Exception as e:
        return f"Xato: {e}"


# ── Public entry point ────────────────────────────────────────────────────────

def math_solver(parameters=None, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    expr   = (params.get("expression") or params.get("equation") or params.get("expr") or "").strip()

    if not expr:
        return "Ifoda ko'rsating. Masalan: {expression: 'x^2 - 4 = 0', action: 'solve'}"

    action = params.get("action", "solve").lower()

    try:
        import sympy  # noqa: F401
        return _sympy_solve(params)
    except ImportError:
        if action not in ("eval", "calculate", "hisob", "solve"):
            return "Murakkab matematik amallar uchun sympy kerak: pip install sympy"
        return _safe_eval(expr)
