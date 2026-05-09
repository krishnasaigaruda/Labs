"""Python source → code IR using the stdlib `ast` module."""
import ast
import re
from . import ir

_SINGLE_STR_RE = re.compile(r"'((?:[^'\\]|\\.)*)'")


def _expr(node) -> str:
    """Render a Python AST expression to source text, normalising single-quoted
    string literals to double-quoted so downstream emitters (Go, Rust, C, ...)
    don't mistake them for char literals."""
    try:
        s = ast.unparse(node)
        return _SINGLE_STR_RE.sub(lambda m: '"' + m.group(1).replace('"', '\\"') + '"', s)
    except Exception:
        return "<expr>"


def _body(stmts):
    out = []
    for s in stmts:
        out.extend(_stmt(s))
    return out


def _stmt(node):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        params = [a.arg for a in node.args.args]
        return [ir.FunctionDef(node.name, params, _body(node.body))]

    if isinstance(node, ast.ClassDef):
        bases = [_expr(b) for b in node.bases]
        return [ir.ClassDef(node.name, _body(node.body), bases=bases)]

    if isinstance(node, ast.Return):
        return [ir.Return(_expr(node.value) if node.value is not None else None)]

    if isinstance(node, ast.Assign):
        if len(node.targets) == 1 and isinstance(node.targets[0], (ast.Name, ast.Attribute, ast.Subscript)):
            return [ir.Assign(_expr(node.targets[0]), _expr(node.value))]
        return [ir.Raw(_expr(node))]

    if isinstance(node, ast.AnnAssign):
        target = _expr(node.target)
        type_hint = _expr(node.annotation) if node.annotation else None
        val = _expr(node.value) if node.value else None
        return [ir.Assign(target, val, type_hint=type_hint)]

    if isinstance(node, ast.AugAssign):
        op_map = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/", ast.Mod: "%"}
        op = op_map.get(type(node.op), "?")
        return [ir.AugAssign(_expr(node.target), op, _expr(node.value))]

    if isinstance(node, ast.If):
        return [ir.If(_expr(node.test), _body(node.body), _body(node.orelse))]

    if isinstance(node, ast.While):
        return [ir.While(_expr(node.test), _body(node.body))]

    if isinstance(node, ast.For):
        if (isinstance(node.iter, ast.Call) and isinstance(node.iter.func, ast.Name)
                and node.iter.func.id == "range"):
            args = [_expr(a) for a in node.iter.args]
            if len(args) == 1:
                start, end = "0", args[0]
            elif len(args) >= 2:
                start, end = args[0], args[1]
            else:
                return [ir.ForEach(_expr(node.target), _expr(node.iter), _body(node.body))]
            return [ir.ForRange(_expr(node.target), start, end, _body(node.body))]
        return [ir.ForEach(_expr(node.target), _expr(node.iter), _body(node.body))]

    if isinstance(node, ast.Break):
        return [ir.Break()]
    if isinstance(node, ast.Continue):
        return [ir.Continue()]

    if isinstance(node, ast.Expr):
        if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name) and node.value.func.id == "print":
            return [ir.Print([_expr(a) for a in node.value.args])]
        return [ir.Call(_expr(node.value))]

    if isinstance(node, ast.Pass):
        return []

    if isinstance(node, ast.Import):
        names = ", ".join(n.name for n in node.names)
        return [ir.Comment(f"import {names}")]
    if isinstance(node, ast.ImportFrom):
        names = ", ".join(n.name for n in node.names)
        return [ir.Comment(f"from {node.module} import {names}")]

    return [ir.Raw(_expr(node))]


def parse_python(source: str):
    tree = ast.parse(source)
    return ir.Module(_body(tree.body))
