"""Emit code from a code IR (Module / Function / If / For / etc.).

Each emitter is a small visitor function that turns IR nodes into target
language source. Shared helpers handle indentation and brace blocks.
"""
import re

IND = "  "


def _i(n: int) -> str:
    return IND * n


# ---------- shared expression normalizer ----------
_PY_BOOL = {"True": "true", "False": "false", "None": "null", "nil": "null", "nullptr": "null", "NULL": "null"}


def norm_expr(e):
    if e is None:
        return ""
    s = str(e).strip()
    # python booleans/none → js
    s = re.sub(r"\bTrue\b", "true", s)
    s = re.sub(r"\bFalse\b", "false", s)
    s = re.sub(r"\bNone\b", "null", s)
    s = re.sub(r"\bnil\b", "null", s)
    # python word-ops → c-ops
    s = re.sub(r"\bnot\s+", "!", s)
    s = re.sub(r"\s+and\s+", " && ", s)
    s = re.sub(r"\s+or\s+", " || ", s)
    # JS strict equality → equality (keep semantics target-language-friendly)
    s = s.replace("===", "==").replace("!==", "!=")
    return s


def py_expr(e):
    if e is None:
        return ""
    s = str(e)
    s = re.sub(r"\btrue\b", "True", s)
    s = re.sub(r"\bfalse\b", "False", s)
    s = re.sub(r"\bnull\b", "None", s)
    s = s.replace("&&", " and ").replace("||", " or ")
    s = re.sub(r"!\s*([A-Za-z_(])", r"not \1", s)
    return s


# ---------- visitor framework ----------
class Emitter:
    """Each language is a subclass that overrides the relevant visit_* hooks."""
    stmt_end = ";"

    def program(self, ir_root):
        body = ir_root["body"] if ir_root["k"] == "module" else [ir_root]
        return self._emit_block(body, 0).rstrip() + "\n"

    # block helpers
    def _emit_block(self, body, depth):
        return "\n".join(self._emit(node, depth) for node in body if node is not None)

    def _brace_block(self, body, depth):
        return "{\n" + self._emit_block(body, depth + 1) + "\n" + _i(depth) + "}"

    def _emit(self, node, depth):
        kind = node["k"]
        m = getattr(self, f"v_{kind}", None)
        if m:
            return m(node, depth)
        if kind == "raw":
            return _i(depth) + node["text"]
        if kind == "block":
            return _i(depth) + self._brace_block(node["body"], depth)
        return _i(depth) + f"/* unsupported: {kind} */"


# ---------- JavaScript ----------
class JS(Emitter):
    name = "javascript"

    def v_comment(self, n, d): return _i(d) + "// " + n["text"]

    def v_print(self, n, d):
        args = ", ".join(norm_expr(a) for a in n["args"])
        return _i(d) + f"console.log({args});"

    def v_assign(self, n, d):
        decl = n.get("declare") or "let"
        if decl in ("let", "const", "var"):
            return _i(d) + f"{decl} {n['target']} = {norm_expr(n['value'])};"
        return _i(d) + f"{n['target']} = {norm_expr(n['value'])};"

    def v_aug(self, n, d):
        return _i(d) + f"{n['target']} {n['op']}= {norm_expr(n['value'])};"

    def v_return(self, n, d):
        v = n.get("value")
        return _i(d) + (f"return {norm_expr(v)};" if v else "return;")

    def v_break(self, n, d): return _i(d) + "break;"
    def v_continue(self, n, d): return _i(d) + "continue;"
    def v_call(self, n, d): return _i(d) + n["expr"] + ";"

    def v_fn(self, n, d):
        return _i(d) + f"function {n['name']}({', '.join(n['params'])}) " + self._brace_block(n["body"], d)

    def v_if(self, n, d):
        s = _i(d) + f"if ({norm_expr(n['test'])}) " + self._brace_block(n["body"], d)
        if n.get("orelse"):
            orelse = n["orelse"]
            if len(orelse) == 1 and orelse[0]["k"] == "if":
                s += " else " + self._emit(orelse[0], d).lstrip()
            else:
                s += " else " + self._brace_block(orelse, d)
        return s

    def v_while(self, n, d):
        return _i(d) + f"while ({norm_expr(n['test'])}) " + self._brace_block(n["body"], d)

    def v_forR(self, n, d):
        return _i(d) + (f"for (let {n['var']} = {n['start']}; {n['var']} < {n['end']}; "
                        f"{n['var']}++) ") + self._brace_block(n["body"], d)

    def v_forE(self, n, d):
        return _i(d) + f"for (const {n['var']} of {norm_expr(n['iter'])}) " + self._brace_block(n["body"], d)

    def v_cls(self, n, d):
        return _i(d) + f"class {n['name']} " + self._brace_block(n["body"], d)


# ---------- TypeScript ----------
class TS(JS):
    name = "typescript"
    def v_assign(self, n, d):
        decl = n.get("declare") or "let"
        ann = f": {n['type']}" if n.get("type") else ""
        return _i(d) + f"{decl} {n['target']}{ann} = {norm_expr(n['value'])};"


# ---------- Python ----------
class PY(Emitter):
    name = "python"

    def _emit_block(self, body, depth):
        if not body:
            return _i(depth) + "pass"
        return "\n".join(self._emit(n, depth) for n in body if n is not None)

    def v_comment(self, n, d): return _i(d) + "# " + n["text"]

    def v_print(self, n, d):
        return _i(d) + "print(" + ", ".join(py_expr(a) for a in n["args"]) + ")"

    def v_assign(self, n, d):
        ann = f": {n['type']}" if n.get("type") else ""
        return _i(d) + f"{n['target']}{ann} = {py_expr(n['value'])}"

    def v_aug(self, n, d):
        return _i(d) + f"{n['target']} {n['op']}= {py_expr(n['value'])}"

    def v_return(self, n, d):
        v = n.get("value")
        return _i(d) + (f"return {py_expr(v)}" if v else "return")

    def v_break(self, n, d): return _i(d) + "break"
    def v_continue(self, n, d): return _i(d) + "continue"
    def v_call(self, n, d): return _i(d) + py_expr(n["expr"])

    def v_fn(self, n, d):
        head = _i(d) + f"def {n['name']}({', '.join(n['params'])}):"
        return head + "\n" + self._emit_block(n["body"], d + 1)

    def v_if(self, n, d):
        s = _i(d) + f"if {py_expr(n['test'])}:\n" + self._emit_block(n["body"], d + 1)
        orelse = n.get("orelse") or []
        if len(orelse) == 1 and orelse[0]["k"] == "if":
            inner = orelse[0]
            s += "\n" + _i(d) + f"elif {py_expr(inner['test'])}:\n" + self._emit_block(inner["body"], d + 1)
            sub = inner.get("orelse") or []
            if sub:
                s += "\n" + _i(d) + "else:\n" + self._emit_block(sub, d + 1)
        elif orelse:
            s += "\n" + _i(d) + "else:\n" + self._emit_block(orelse, d + 1)
        return s

    def v_while(self, n, d):
        return _i(d) + f"while {py_expr(n['test'])}:\n" + self._emit_block(n["body"], d + 1)

    def v_forR(self, n, d):
        return _i(d) + f"for {n['var']} in range({n['start']}, {n['end']}):\n" + self._emit_block(n["body"], d + 1)

    def v_forE(self, n, d):
        return _i(d) + f"for {n['var']} in {py_expr(n['iter'])}:\n" + self._emit_block(n["body"], d + 1)

    def v_cls(self, n, d):
        bases = n.get("bases") or []
        head = _i(d) + f"class {n['name']}" + (f"({', '.join(bases)})" if bases else "") + ":"
        body = self._emit_block(n["body"], d + 1) if n["body"] else _i(d + 1) + "pass"
        return head + "\n" + body


# ---------- Java ----------
class JAVA(JS):
    name = "java"

    def program(self, root):
        body = root["body"] if root["k"] == "module" else [root]
        has_class = any(n["k"] == "cls" for n in body)
        if has_class:
            return self._emit_block(body, 0) + "\n"
        return ("public class Main {\n" + IND + "public static void main(String[] args) "
                + self._brace_block(body, 1) + "\n}\n")

    def v_print(self, n, d):
        args = " + ".join(norm_expr(a) for a in n["args"]) or "\"\""
        return _i(d) + f"System.out.println({args});"

    def v_assign(self, n, d):
        ty = n.get("type") or "var"
        return _i(d) + f"{ty} {n['target']} = {norm_expr(n['value'])};"

    def v_fn(self, n, d):
        params = ", ".join(f"Object {p}" for p in n["params"])
        return _i(d) + f"public static Object {n['name']}({params}) " + self._brace_block(n["body"], d)

    def v_forR(self, n, d):
        return _i(d) + (f"for (int {n['var']} = {n['start']}; {n['var']} < {n['end']}; "
                        f"{n['var']}++) ") + self._brace_block(n["body"], d)

    def v_forE(self, n, d):
        return _i(d) + f"for (var {n['var']} : {norm_expr(n['iter'])}) " + self._brace_block(n["body"], d)

    def v_cls(self, n, d):
        return _i(d) + f"public class {n['name']} " + self._brace_block(n["body"], d)


# ---------- C# ----------
class CS(JAVA):
    name = "csharp"

    def program(self, root):
        body = root["body"] if root["k"] == "module" else [root]
        has_class = any(n["k"] == "cls" for n in body)
        if has_class:
            return "using System;\n\n" + self._emit_block(body, 0) + "\n"
        return ("using System;\n\nclass Program {\n" + IND + "static void Main() "
                + self._brace_block(body, 1) + "\n}\n")

    def v_print(self, n, d):
        args = ", ".join(norm_expr(a) for a in n["args"])
        return _i(d) + f"Console.WriteLine({args});"

    def v_forE(self, n, d):
        return _i(d) + f"foreach (var {n['var']} in {norm_expr(n['iter'])}) " + self._brace_block(n["body"], d)

    def v_cls(self, n, d):
        return _i(d) + f"class {n['name']} " + self._brace_block(n["body"], d)


# ---------- C++ ----------
class CPP(JS):
    name = "cpp"

    def program(self, root):
        body = root["body"] if root["k"] == "module" else [root]
        has_top = any(n["k"] in ("fn", "cls") for n in body)
        prelude = "#include <iostream>\n#include <string>\nusing namespace std;\n\n"
        if has_top:
            return prelude + self._emit_block(body, 0) + "\n"
        return prelude + "int main() " + self._brace_block(body + [{"k": "return", "value": "0"}], 0) + "\n"

    def v_print(self, n, d):
        chain = " << ".join(norm_expr(a) for a in n["args"]) or '""'
        return _i(d) + f"cout << {chain} << endl;"

    def v_assign(self, n, d):
        return _i(d) + f"auto {n['target']} = {norm_expr(n['value'])};"

    def v_fn(self, n, d):
        params = ", ".join(f"auto {p}" for p in n["params"])
        return _i(d) + f"auto {n['name']}({params}) " + self._brace_block(n["body"], d)

    def v_forE(self, n, d):
        return _i(d) + f"for (auto {n['var']} : {norm_expr(n['iter'])}) " + self._brace_block(n["body"], d)

    def v_cls(self, n, d):
        return _i(d) + f"class {n['name']} " + self._brace_block(n["body"], d) + ";"


# ---------- C ----------
class C(CPP):
    name = "c"
    def program(self, root):
        body = root["body"] if root["k"] == "module" else [root]
        has_top = any(n["k"] == "fn" for n in body)
        prelude = "#include <stdio.h>\n\n"
        if has_top:
            return prelude + self._emit_block(body, 0) + "\n"
        return prelude + "int main(void) " + self._brace_block(body + [{"k": "return", "value": "0"}], 0) + "\n"

    def v_print(self, n, d):
        if not n["args"]:
            return _i(d) + 'printf("\\n");'
        v = norm_expr(n["args"][0])
        return _i(d) + (f"printf({v});" if "%" in v else f'printf("%s\\n", {v});')

    def v_assign(self, n, d):
        ty = n.get("type") or "int"
        return _i(d) + f"{ty} {n['target']} = {norm_expr(n['value'])};"


# ---------- Swift ----------
class SWIFT(Emitter):
    name = "swift"
    stmt_end = ""

    def v_comment(self, n, d): return _i(d) + "// " + n["text"]
    def v_print(self, n, d):
        return _i(d) + f"print({', '.join(norm_expr(a) for a in n['args'])})"
    def v_assign(self, n, d):
        kw = "let" if n.get("declare") == "const" else "var"
        return _i(d) + f"{kw} {n['target']} = {norm_expr(n['value'])}"
    def v_aug(self, n, d):
        return _i(d) + f"{n['target']} {n['op']}= {norm_expr(n['value'])}"
    def v_return(self, n, d):
        v = n.get("value"); return _i(d) + (f"return {norm_expr(v)}" if v else "return")
    def v_break(self, n, d): return _i(d) + "break"
    def v_continue(self, n, d): return _i(d) + "continue"
    def v_call(self, n, d): return _i(d) + n["expr"]
    def v_fn(self, n, d):
        params = ", ".join(f"_ {p}: Any" for p in n["params"])
        return _i(d) + f"func {n['name']}({params}) " + self._brace_block(n["body"], d)
    def v_if(self, n, d):
        s = _i(d) + f"if {norm_expr(n['test'])} " + self._brace_block(n["body"], d)
        orelse = n.get("orelse") or []
        if len(orelse) == 1 and orelse[0]["k"] == "if":
            s += " else " + self._emit(orelse[0], d).lstrip()
        elif orelse:
            s += " else " + self._brace_block(orelse, d)
        return s
    def v_while(self, n, d):
        return _i(d) + f"while {norm_expr(n['test'])} " + self._brace_block(n["body"], d)
    def v_forR(self, n, d):
        return _i(d) + f"for {n['var']} in {n['start']}..<{n['end']} " + self._brace_block(n["body"], d)
    def v_forE(self, n, d):
        return _i(d) + f"for {n['var']} in {norm_expr(n['iter'])} " + self._brace_block(n["body"], d)
    def v_cls(self, n, d):
        return _i(d) + f"class {n['name']} " + self._brace_block(n["body"], d)


# ---------- Go ----------
class GO(Emitter):
    name = "go"
    stmt_end = ""
    def program(self, root):
        body = root["body"] if root["k"] == "module" else [root]
        has_top = any(n["k"] in ("fn", "cls") for n in body)
        prelude = "package main\n\nimport \"fmt\"\n\n"
        if has_top:
            return prelude + self._emit_block(body, 0) + "\n"
        return prelude + "func main() " + self._brace_block(body, 0) + "\n"

    def v_comment(self, n, d): return _i(d) + "// " + n["text"]
    def v_print(self, n, d):
        return _i(d) + f"fmt.Println({', '.join(norm_expr(a) for a in n['args'])})"
    def v_assign(self, n, d):
        return _i(d) + f"{n['target']} := {norm_expr(n['value'])}"
    def v_aug(self, n, d):
        return _i(d) + f"{n['target']} {n['op']}= {norm_expr(n['value'])}"
    def v_return(self, n, d):
        v = n.get("value"); return _i(d) + (f"return {norm_expr(v)}" if v else "return")
    def v_break(self, n, d): return _i(d) + "break"
    def v_continue(self, n, d): return _i(d) + "continue"
    def v_call(self, n, d): return _i(d) + n["expr"]
    def v_fn(self, n, d):
        params = ", ".join(f"{p} interface{{}}" for p in n["params"])
        return _i(d) + f"func {n['name']}({params}) " + self._brace_block(n["body"], d)
    def v_if(self, n, d):
        s = _i(d) + f"if {norm_expr(n['test'])} " + self._brace_block(n["body"], d)
        orelse = n.get("orelse") or []
        if len(orelse) == 1 and orelse[0]["k"] == "if":
            s += " else " + self._emit(orelse[0], d).lstrip()
        elif orelse:
            s += " else " + self._brace_block(orelse, d)
        return s
    def v_while(self, n, d):
        return _i(d) + f"for {norm_expr(n['test'])} " + self._brace_block(n["body"], d)
    def v_forR(self, n, d):
        return _i(d) + f"for {n['var']} := {n['start']}; {n['var']} < {n['end']}; {n['var']}++ " + self._brace_block(n["body"], d)
    def v_forE(self, n, d):
        return _i(d) + f"for _, {n['var']} := range {norm_expr(n['iter'])} " + self._brace_block(n["body"], d)
    def v_cls(self, n, d):
        return _i(d) + f"type {n['name']} struct " + self._brace_block(n["body"], d)


# ---------- Rust ----------
class RUST(JS):
    name = "rust"
    def program(self, root):
        body = root["body"] if root["k"] == "module" else [root]
        if any(n["k"] == "fn" for n in body):
            return self._emit_block(body, 0) + "\n"
        return "fn main() " + self._brace_block(body, 0) + "\n"
    def v_print(self, n, d):
        v = ", ".join(norm_expr(a) for a in n["args"])
        return _i(d) + f"println!(\"{{:?}}\", {v});"
    def v_assign(self, n, d):
        kw = "let" if n.get("declare") == "const" else "let mut"
        return _i(d) + f"{kw} {n['target']} = {norm_expr(n['value'])};"
    def v_fn(self, n, d):
        params = ", ".join(f"{p}: i32" for p in n["params"])
        return _i(d) + f"fn {n['name']}({params}) " + self._brace_block(n["body"], d)
    def v_forR(self, n, d):
        return _i(d) + f"for {n['var']} in {n['start']}..{n['end']} " + self._brace_block(n["body"], d)
    def v_forE(self, n, d):
        return _i(d) + f"for {n['var']} in {norm_expr(n['iter'])} " + self._brace_block(n["body"], d)
    def v_cls(self, n, d):
        return _i(d) + f"struct {n['name']} " + self._brace_block(n["body"], d)


# ---------- Kotlin ----------
class KOTLIN(SWIFT):
    name = "kotlin"
    def program(self, root):
        body = root["body"] if root["k"] == "module" else [root]
        if any(n["k"] == "fn" for n in body):
            return self._emit_block(body, 0) + "\n"
        return "fun main() " + self._brace_block(body, 0) + "\n"
    def v_print(self, n, d):
        return _i(d) + f"println({', '.join(norm_expr(a) for a in n['args'])})"
    def v_assign(self, n, d):
        kw = "val" if n.get("declare") == "const" else "var"
        return _i(d) + f"{kw} {n['target']} = {norm_expr(n['value'])}"
    def v_fn(self, n, d):
        params = ", ".join(f"{p}: Any" for p in n["params"])
        return _i(d) + f"fun {n['name']}({params}) " + self._brace_block(n["body"], d)
    def v_forR(self, n, d):
        return _i(d) + f"for ({n['var']} in {n['start']} until {n['end']}) " + self._brace_block(n["body"], d)
    def v_forE(self, n, d):
        return _i(d) + f"for ({n['var']} in {norm_expr(n['iter'])}) " + self._brace_block(n["body"], d)
    def v_cls(self, n, d):
        return _i(d) + f"class {n['name']} " + self._brace_block(n["body"], d)


# ---------- PHP ----------
# PHP-specific expression rewriting: add $ prefix to variable references,
# turn `.` member access into `->`, and Class.staticMethod into Class::method.
_PHP_KEYWORDS = {
    "true", "false", "null", "new", "return", "if", "else", "elseif", "while",
    "for", "foreach", "as", "function", "class", "echo", "self",
    "parent", "and", "or", "not", "use", "namespace",
}
# Simple list of common stdlib/built-in function names we should NOT prefix
_PHP_FN_HINTS = {
    "echo", "print", "isset", "empty", "count", "array", "implode", "explode",
    "strlen", "strpos", "str_replace", "intval", "floatval", "json_encode",
    "json_decode", "var_dump", "die", "exit",
}


def _php_rewrite(expr: str) -> str:
    """Best-effort Java/JS expression → PHP."""
    if not expr:
        return ""
    s = norm_expr(expr)

    placeholders = []

    def stash(m):
        placeholders.append(m.group(0))
        return f"\x01{len(placeholders) - 1}\x02"

    # protect string literals
    s = re.sub(r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'', stash, s)

    # Capitalized identifier followed by `.method` → `Class::method`
    s = re.sub(r"\b([A-Z][A-Za-z0-9_]*)\.([A-Za-z_]\w*)", r"\1::\2", s)

    # $ prefix on bare lowercase identifiers used as variables
    def maybe_prefix(m):
        word = m.group(1)
        bp = m.start(1)
        before = s[bp - 2:bp] if bp >= 2 else (s[:bp] if bp else "")
        after = s[m.end(1):m.end(1) + 1]
        if word in _PHP_KEYWORDS or word in _PHP_FN_HINTS:
            return word
        if bp > 0 and s[bp - 1] in "$.":
            return word
        if before.endswith("->") or before.endswith("::"):
            return word
        if after == "(":
            return word
        return "$" + word

    s = re.sub(r"\b([a-z_][A-Za-z0-9_]*)\b", maybe_prefix, s)

    # Member access: `.name` → `->name`
    s = re.sub(r"(?<=[\w\)\]])\.(?=[A-Za-z_])", "->", s)

    # restore strings, then convert `+` between strings/anything to PHP `.`
    s = re.sub(r"\x01(\d+)\x02", lambda m: placeholders[int(m.group(1))], s)

    # If there's a string literal in the expression, switch all `+` to `.`
    # (PHP uses `.` for concatenation, never `+`).
    if re.search(r'"|\'', s) and "+" in s:
        # naive: any `+` not inside a string becomes `.`. Re-protect strings.
        ph2 = []

        def stash2(m):
            ph2.append(m.group(0))
            return f"\x01{len(ph2) - 1}\x02"

        protected = re.sub(r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'', stash2, s)
        protected = re.sub(r"\s*\+\s*", " . ", protected)
        s = re.sub(r"\x01(\d+)\x02", lambda m: ph2[int(m.group(1))], protected)

    # Trim runs of internal whitespace from collapsed multi-line chains.
    s = re.sub(r" {2,}", " ", s)
    return s


class PHP(JS):
    name = "php"

    def program(self, root):
        body = root["body"] if root["k"] == "module" else [root]
        return "<?php\n" + self._emit_block(body, 0) + "\n"

    def v_print(self, n, d):
        args = ", ".join(_php_rewrite(a) for a in n["args"])
        return _i(d) + f'echo {args}, "\\n";'

    def v_assign(self, n, d):
        target = n["target"]
        # rewrite member-access targets like this.x → $this->x
        if "." in target:
            target = _php_rewrite(target)
        else:
            target = "$" + target
        return _i(d) + f"{target} = {_php_rewrite(n['value'])};"

    def v_aug(self, n, d):
        target = n["target"]
        if "." in target:
            target = _php_rewrite(target)
        else:
            target = "$" + target
        return _i(d) + f"{target} {n['op']}= {_php_rewrite(n['value'])};"

    def v_return(self, n, d):
        v = n.get("value")
        return _i(d) + (f"return {_php_rewrite(v)};" if v else "return;")

    def v_call(self, n, d):
        return _i(d) + _php_rewrite(n["expr"]) + ";"

    def v_if(self, n, d):
        s = _i(d) + f"if ({_php_rewrite(n['test'])}) " + self._brace_block(n["body"], d)
        orelse = n.get("orelse") or []
        if len(orelse) == 1 and orelse[0]["k"] == "if":
            s += " else " + self._emit(orelse[0], d).lstrip()
        elif orelse:
            s += " else " + self._brace_block(orelse, d)
        return s

    def v_while(self, n, d):
        return _i(d) + f"while ({_php_rewrite(n['test'])}) " + self._brace_block(n["body"], d)

    def v_fn(self, n, d):
        name = n["name"]
        # if this method matches the enclosing class name, rename to __construct
        if getattr(self, "_cls_stack", None) and self._cls_stack[-1] == name:
            name = "__construct"
        params = ", ".join(f"${p}" for p in n["params"])
        return _i(d) + f"function {name}({params}) " + self._brace_block(n["body"], d)

    def v_forR(self, n, d):
        v = n["var"]
        return _i(d) + f"for (${v} = {n['start']}; ${v} < {n['end']}; ${v}++) " + self._brace_block(n["body"], d)

    def v_forE(self, n, d):
        return _i(d) + f"foreach ({_php_rewrite(n['iter'])} as ${n['var']}) " + self._brace_block(n["body"], d)

    # Track the enclosing class so v_fn knows when to emit __construct,
    # and emit class fields as `public $name` instead of bare assignments.
    def v_cls(self, n, d):
        if not hasattr(self, "_cls_stack"):
            self._cls_stack = []
        self._cls_stack.append(n["name"])
        try:
            head = _i(d) + f"class {n['name']} "
            # transform direct child Assign nodes to property declarations
            inner_body = []
            for child in n["body"]:
                if child["k"] == "assign" and "." not in child["target"]:
                    val = child.get("value")
                    if val is not None and val.strip():
                        inner_body.append(_i(d + 1) + f"public ${child['target']} = {_php_rewrite(val)};")
                    else:
                        inner_body.append(_i(d + 1) + f"public ${child['target']};")
                else:
                    inner_body.append(self._emit(child, d + 1))
            inner = "\n".join(inner_body)
            return head + "{\n" + inner + "\n" + _i(d) + "}"
        finally:
            self._cls_stack.pop()


# ---------- Ruby ----------
class RUBY(Emitter):
    name = "ruby"
    def v_comment(self, n, d): return _i(d) + "# " + n["text"]
    def v_print(self, n, d):
        return _i(d) + f"puts {', '.join(norm_expr(a) for a in n['args'])}"
    def v_assign(self, n, d):
        return _i(d) + f"{n['target']} = {norm_expr(n['value'])}"
    def v_aug(self, n, d):
        return _i(d) + f"{n['target']} {n['op']}= {norm_expr(n['value'])}"
    def v_return(self, n, d):
        v = n.get("value"); return _i(d) + (f"return {norm_expr(v)}" if v else "return")
    def v_break(self, n, d): return _i(d) + "break"
    def v_continue(self, n, d): return _i(d) + "next"
    def v_call(self, n, d): return _i(d) + n["expr"]
    def v_fn(self, n, d):
        return (_i(d) + f"def {n['name']}({', '.join(n['params'])})\n"
                + self._emit_block(n["body"], d + 1) + "\n" + _i(d) + "end")
    def v_if(self, n, d):
        s = _i(d) + f"if {norm_expr(n['test'])}\n" + self._emit_block(n["body"], d + 1)
        orelse = n.get("orelse") or []
        if len(orelse) == 1 and orelse[0]["k"] == "if":
            inner = orelse[0]
            s += "\n" + _i(d) + f"elsif {norm_expr(inner['test'])}\n" + self._emit_block(inner["body"], d + 1)
            sub = inner.get("orelse") or []
            if sub:
                s += "\n" + _i(d) + "else\n" + self._emit_block(sub, d + 1)
        elif orelse:
            s += "\n" + _i(d) + "else\n" + self._emit_block(orelse, d + 1)
        return s + "\n" + _i(d) + "end"
    def v_while(self, n, d):
        return (_i(d) + f"while {norm_expr(n['test'])}\n"
                + self._emit_block(n["body"], d + 1) + "\n" + _i(d) + "end")
    def v_forR(self, n, d):
        return (_i(d) + f"({n['start']}...{n['end']}).each do |{n['var']}|\n"
                + self._emit_block(n["body"], d + 1) + "\n" + _i(d) + "end")
    def v_forE(self, n, d):
        return (_i(d) + f"{norm_expr(n['iter'])}.each do |{n['var']}|\n"
                + self._emit_block(n["body"], d + 1) + "\n" + _i(d) + "end")
    def v_cls(self, n, d):
        return (_i(d) + f"class {n['name']}\n" + self._emit_block(n["body"], d + 1)
                + "\n" + _i(d) + "end")


# ---------- Lua ----------
class LUA(RUBY):
    name = "lua"
    def v_comment(self, n, d): return _i(d) + "-- " + n["text"]
    def v_print(self, n, d):
        return _i(d) + f"print({', '.join(norm_expr(a) for a in n['args'])})"
    def v_assign(self, n, d):
        return _i(d) + f"local {n['target']} = {norm_expr(n['value'])}"
    def v_continue(self, n, d): return _i(d) + "-- continue (not native in Lua)"
    def v_fn(self, n, d):
        return (_i(d) + f"function {n['name']}({', '.join(n['params'])})\n"
                + self._emit_block(n["body"], d + 1) + "\n" + _i(d) + "end")
    def v_if(self, n, d):
        s = _i(d) + f"if {norm_expr(n['test'])} then\n" + self._emit_block(n["body"], d + 1)
        orelse = n.get("orelse") or []
        if len(orelse) == 1 and orelse[0]["k"] == "if":
            inner = orelse[0]
            s += "\n" + _i(d) + f"elseif {norm_expr(inner['test'])} then\n" + self._emit_block(inner["body"], d + 1)
            sub = inner.get("orelse") or []
            if sub:
                s += "\n" + _i(d) + "else\n" + self._emit_block(sub, d + 1)
        elif orelse:
            s += "\n" + _i(d) + "else\n" + self._emit_block(orelse, d + 1)
        return s + "\n" + _i(d) + "end"
    def v_while(self, n, d):
        return (_i(d) + f"while {norm_expr(n['test'])} do\n"
                + self._emit_block(n["body"], d + 1) + "\n" + _i(d) + "end")
    def v_forR(self, n, d):
        return (_i(d) + f"for {n['var']} = {n['start']}, ({n['end']})-1 do\n"
                + self._emit_block(n["body"], d + 1) + "\n" + _i(d) + "end")
    def v_forE(self, n, d):
        return (_i(d) + f"for _, {n['var']} in ipairs({norm_expr(n['iter'])}) do\n"
                + self._emit_block(n["body"], d + 1) + "\n" + _i(d) + "end")


# ---------- Bash ----------
class BASH(Emitter):
    name = "bash"
    def program(self, root):
        body = root["body"] if root["k"] == "module" else [root]
        return "#!/usr/bin/env bash\n" + self._emit_block(body, 0) + "\n"
    def v_comment(self, n, d): return _i(d) + "# " + n["text"]
    def v_print(self, n, d):
        return _i(d) + f"echo {' '.join(norm_expr(a) for a in n['args'])}"
    def v_assign(self, n, d):
        return _i(d) + f"{n['target']}={norm_expr(n['value'])}"
    def v_aug(self, n, d):
        return _i(d) + f"((${n['target']} {n['op']}= {norm_expr(n['value'])}))"
    def v_return(self, n, d):
        v = n.get("value"); return _i(d) + (f"return {norm_expr(v)}" if v else "return")
    def v_break(self, n, d): return _i(d) + "break"
    def v_continue(self, n, d): return _i(d) + "continue"
    def v_call(self, n, d): return _i(d) + n["expr"]
    def v_fn(self, n, d):
        return (_i(d) + f"{n['name']}() {{\n" + self._emit_block(n["body"], d + 1)
                + "\n" + _i(d) + "}")
    def v_if(self, n, d):
        s = (_i(d) + f"if [[ {norm_expr(n['test'])} ]]; then\n"
             + self._emit_block(n["body"], d + 1))
        orelse = n.get("orelse") or []
        if orelse:
            s += "\n" + _i(d) + "else\n" + self._emit_block(orelse, d + 1)
        return s + "\n" + _i(d) + "fi"
    def v_while(self, n, d):
        return (_i(d) + f"while [[ {norm_expr(n['test'])} ]]; do\n"
                + self._emit_block(n["body"], d + 1) + "\n" + _i(d) + "done")
    def v_forR(self, n, d):
        v = n["var"]
        return (_i(d) + f"for (({v}={n['start']}; {v}<{n['end']}; {v}++)); do\n"
                + self._emit_block(n["body"], d + 1) + "\n" + _i(d) + "done")
    def v_forE(self, n, d):
        return (_i(d) + f"for {n['var']} in {norm_expr(n['iter'])}; do\n"
                + self._emit_block(n["body"], d + 1) + "\n" + _i(d) + "done")
    def v_cls(self, n, d):
        return _i(d) + f"# class {n['name']} (bash has no classes)"


# Lightweight emitters for the long tail: produce reasonable output by reusing
# the JS emitter and adjusting print + braces minimally.
class _PassthroughJS(JS):
    """Languages that look enough like JS that the JS emitter is a fine starting point."""
    pass


class DART(JAVA):
    name = "dart"
    def program(self, root):
        body = root["body"] if root["k"] == "module" else [root]
        if any(n["k"] == "fn" for n in body):
            return self._emit_block(body, 0) + "\n"
        return "void main() " + self._brace_block(body, 0) + "\n"
    def v_print(self, n, d):
        return _i(d) + f"print({', '.join(norm_expr(a) for a in n['args'])});"
    def v_assign(self, n, d):
        return _i(d) + f"var {n['target']} = {norm_expr(n['value'])};"


class SCALA(KOTLIN):
    name = "scala"
    def program(self, root):
        body = root["body"] if root["k"] == "module" else [root]
        if any(n["k"] == "fn" for n in body):
            return self._emit_block(body, 0) + "\n"
        return ("object Main {\n" + IND + "def main(args: Array[String]): Unit = "
                + self._brace_block(body, 1) + "\n}\n")
    def v_print(self, n, d):
        return _i(d) + f"println({', '.join(norm_expr(a) for a in n['args'])})"
    def v_assign(self, n, d):
        kw = "val" if n.get("declare") == "const" else "var"
        return _i(d) + f"{kw} {n['target']} = {norm_expr(n['value'])}"
    def v_fn(self, n, d):
        params = ", ".join(f"{p}: Any" for p in n["params"])
        return _i(d) + f"def {n['name']}({params}): Any = " + self._brace_block(n["body"], d)


class GROOVY(JAVA):
    name = "groovy"
    def program(self, root):
        body = root["body"] if root["k"] == "module" else [root]
        return self._emit_block(body, 0) + "\n"
    def v_print(self, n, d):
        return _i(d) + f"println({', '.join(norm_expr(a) for a in n['args'])})"
    def v_assign(self, n, d):
        return _i(d) + f"def {n['target']} = {norm_expr(n['value'])}"
    def v_fn(self, n, d):
        return _i(d) + f"def {n['name']}({', '.join(n['params'])}) " + self._brace_block(n["body"], d)


# Long-tail languages: simpler emitters, adequate for common idioms
class POWERSHELL(JS):
    name = "powershell"
    def v_print(self, n, d):
        return _i(d) + f"Write-Host {' '.join(norm_expr(a) for a in n['args'])}"
    def v_assign(self, n, d):
        return _i(d) + f"${n['target']} = {norm_expr(n['value'])}"
    def v_forE(self, n, d):
        return _i(d) + f"foreach (${n['var']} in {norm_expr(n['iter'])}) " + self._brace_block(n["body"], d)
    def v_forR(self, n, d):
        v = n["var"]
        return _i(d) + f"for (${v}={n['start']}; ${v} -lt {n['end']}; ${v}++) " + self._brace_block(n["body"], d)


# ---------- Registry ----------
EMITTERS = {
    cls.name: cls() for cls in [
        JS, TS, PY, JAVA, CS, CPP, C, SWIFT, GO, RUST, KOTLIN, PHP, RUBY, LUA,
        BASH, POWERSHELL, DART, SCALA, GROOVY,
    ]
}


def emit_code(ir_root, target: str) -> str:
    e = EMITTERS.get(target)
    if e is None:
        # fall back to JS for unsupported targets; still valid code
        e = EMITTERS["javascript"]
    return e.program(ir_root)
