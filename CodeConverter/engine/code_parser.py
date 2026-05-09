"""Generic code parser for brace-style and end-block languages.

Not as accurate as a true AST, but tokenizes brace structure, strings, and
comments correctly, and recognizes common idioms (functions, ifs, loops,
classes, prints, declarations, returns).
"""
import re
from . import ir


# ----- Tokenizer -----
_SEMI_TERMINATED = {"java", "c", "cpp", "csharp", "javascript", "typescript", "php", "rust", "go"}


def _tokenize_brace(code: str, dialect: str):
    """Split source into tokens: line / open-brace / close-brace.

    Strings and comments are kept intact. For semicolon-terminated dialects,
    newlines are treated as plain whitespace so multi-line method chains
    (e.g. `.stream()\\n  .filter(..)\\n  .collect()`) stay one statement.
    """
    out = []
    buf = ""
    i = 0
    n = len(code)
    in_str = False
    str_ch = ""
    in_line_com = False
    in_block_com = False
    paren_depth = 0      # don't break statements inside (...) / [...]
    bracket_depth = 0
    line_com_starts = ("//",)
    if dialect in ("ruby", "perl", "bash", "powershell", "r"):
        line_com_starts = ("#", "//")
    semi_terminated = dialect in _SEMI_TERMINATED
    while i < n:
        c = code[i]
        nx = code[i + 1] if i + 1 < n else ""
        if in_line_com:
            buf += c
            if c == "\n":
                in_line_com = False
            i += 1
            continue
        if in_block_com:
            buf += c
            if c == "*" and nx == "/":
                buf += nx
                i += 2
                in_block_com = False
                continue
            i += 1
            continue
        if in_str:
            buf += c
            if c == "\\" and nx:
                buf += nx
                i += 2
                continue
            if c == str_ch:
                in_str = False
            i += 1
            continue
        if c == "/" and nx == "/":
            in_line_com = True
            buf += c
            i += 1
            continue
        if c == "/" and nx == "*":
            in_block_com = True
            buf += c
            i += 1
            continue
        if c == "#" and "#" in line_com_starts:
            in_line_com = True
            buf += c
            i += 1
            continue
        if c in ("\"", "'", "`"):
            in_str = True
            str_ch = c
            buf += c
            i += 1
            continue
        if c == "(" or c == "[":
            paren_depth += 1
            buf += c
            i += 1
            continue
        if c == ")" or c == "]":
            paren_depth = max(0, paren_depth - 1)
            buf += c
            i += 1
            continue
        if c == "{" and paren_depth == 0:
            if buf.strip():
                out.append(("line", buf.strip()))
            buf = ""
            out.append(("open", None))
            i += 1
            continue
        if c == "}" and paren_depth == 0:
            if buf.strip():
                out.append(("line", buf.strip()))
            buf = ""
            out.append(("close", None))
            i += 1
            continue
        if c == ";" and paren_depth == 0:
            if buf.strip():
                out.append(("line", buf.strip()))
            buf = ""
            i += 1
            continue
        if c == "\n":
            if semi_terminated:
                # Newlines are whitespace in C/Java/JS-style dialects.
                buf += " "
                i += 1
                continue
            if paren_depth == 0:
                if buf.strip():
                    out.append(("line", buf.strip()))
                buf = ""
                i += 1
                continue
            buf += " "
            i += 1
            continue
        buf += c
        i += 1
    if buf.strip():
        out.append(("line", buf.strip()))
    return out


# ---- Per-line classifiers ----
_PRINT_RE = [
    re.compile(r"^console\.log\s*\((.*)\)$"),
    re.compile(r"^System\.out\.println\s*\((.*)\)$"),
    re.compile(r"^Console\.WriteLine\s*\((.*)\)$"),
    re.compile(r"^(?:std::)?cout\s*<<\s*(.+?)(?:\s*<<\s*(?:std::)?endl)?$"),
    re.compile(r"^printf\s*\((.*)\)$"),
    re.compile(r"^print(?:ln)?\s*\((.*)\)$"),
    re.compile(r"^fmt\.Println\s*\((.*)\)$"),
    re.compile(r"^echo\s+(.+)$"),
    re.compile(r"^puts\s+(.+)$"),
    re.compile(r"^Write-Host\s+(.+)$"),
    re.compile(r"^NSLog\s*\((.*)\)$"),
    re.compile(r"^println!\s*\((.*)\)$"),
]

_FN_RES = [
    re.compile(r"^function\s+([A-Za-z_]\w*)\s*\(([^)]*)\)$"),
    re.compile(r"^func\s+([A-Za-z_]\w*)\s*\(([^)]*)\)\s*(?:->\s*[\w<>\[\],\s]+)?$"),
    re.compile(r"^fun\s+([A-Za-z_]\w*)\s*\(([^)]*)\)\s*(?::\s*[\w<>\[\],\s]+)?$"),
    re.compile(r"^def\s+([A-Za-z_]\w*)\s*\(([^)]*)\)$"),
    re.compile(r"^fn\s+([A-Za-z_]\w*)\s*\(([^)]*)\)\s*(?:->\s*[\w<>\[\],\s]+)?$"),
    re.compile(r"^(?:public|private|protected|static|async|export|final|abstract|\s)+\s*[\w<>\[\],\s]+\s+([A-Za-z_]\w*)\s*\(([^)]*)\)(?:\s+throws\s+[\w,\s]+)?$"),
    # Type methodName(args) — no modifier (package-private Java methods)
    re.compile(r"^[\w<>\[\]]+\s+([A-Za-z_]\w*)\s*\(([^)]*)\)(?:\s+throws\s+[\w,\s]+)?$"),
    # Java-style constructor: ClassName(args) — no return type, no modifier required
    re.compile(r"^(?:public\s+|private\s+|protected\s+)?([A-Za-z_]\w*)\s*\(([^)]*)\)(?:\s+throws\s+[\w,\s]+)?$"),
]


# Java-style field declaration: "Type name;" or "Type name = value;" or "Type a, b, c;"
# We also allow generics, arrays, and modifiers.
_FIELD_RE = re.compile(
    r"^(?:public\s+|private\s+|protected\s+|static\s+|final\s+)*"
    r"[A-Za-z_][\w<>\[\],\s]*\s+"           # type
    r"([A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*)*)"  # 1+ names
    r"$"
)


def _strip_param_types(params: str):
    out = []
    for p in [s.strip() for s in params.split(",") if s.strip()]:
        # "Type name" → "name"
        p = re.sub(r"^[\w<>\[\]:&*]+(\s+[\w<>\[\]:&*]+)*\s+", "", p)
        # "name: Type" → "name"
        p = re.sub(r":\s*[\w<>\[\],\s]+$", "", p)
        # default values
        p = re.sub(r"\s*=\s*[^,]+$", "", p)
        out.append(p.strip())
    return out


def _parse_block(toks, i, dialect):
    body = []
    while i < len(toks):
        kind, payload = toks[i]
        if kind == "close":
            return body, i + 1
        if kind == "open":
            inner, i = _parse_block(toks, i + 1, dialect)
            body.append({"k": "block", "body": inner})
            continue
        # line
        node, ni = _parse_line(toks, i, dialect)
        i = ni
        if node is not None:
            body.append(node)
    return body, i


_PREAMBLE_RES = [
    re.compile(r"^import\s+[\w.*\s,{}]+$"),                  # Java/Kotlin/Swift/TS
    re.compile(r"^from\s+[\w.]+\s+import\s+.+$"),            # not used here (python parser handles)
    re.compile(r"^package\s+[\w.]+$"),                       # Java/Go/Kotlin
    re.compile(r"^using\s+[\w.=:<>\s]+$"),                   # C#/C++
    re.compile(r"^namespace\s+\w[\w.]*$"),                   # C#/C++
    re.compile(r"^#include\s*[<\"][\w./]+[>\"]$"),           # C/C++
    re.compile(r"^use\s+[\w:]+(?:::\{[\w,\s:]+\})?$"),       # Rust
    re.compile(r"^require\s+['\"][\w/.-]+['\"]$"),           # Ruby/Node
    re.compile(r"^module\s+\w+(?:\s+where)?$"),              # Haskell/Erlang
    re.compile(r"^@\w[\w.]*(?:\([^)]*\))?$"),                # decorator/annotation
]


def _is_preamble(line: str) -> bool:
    """Imports / packages / using / include — language-specific noise that
    should be dropped when converting to a different target."""
    for rx in _PREAMBLE_RES:
        if rx.match(line):
            return True
    return False


def _parse_line(toks, i, dialect):
    line = toks[i][1]
    nxt = toks[i + 1] if i + 1 < len(toks) else None

    # comments
    if line.startswith("//"):
        return ir.Comment(line[2:].strip()), i + 1
    if line.startswith("/*") and line.endswith("*/"):
        return ir.Comment(line[2:-2].strip()), i + 1
    if line.startswith("#") and dialect in ("ruby", "perl", "bash", "powershell", "r"):
        return ir.Comment(line[1:].strip()), i + 1

    # drop language-specific preamble (imports, package, using, #include, etc.)
    if _is_preamble(line):
        return None, i + 1

    # class
    m = re.match(r"^(?:public\s+|private\s+|export\s+|open\s+|final\s+|static\s+)*class\s+([A-Za-z_]\w*)", line)
    if m and nxt and nxt[0] == "open":
        body, ni = _parse_block(toks, i + 2, dialect)
        return ir.ClassDef(m.group(1), body), ni

    # if / else  (must run BEFORE function patterns — otherwise `for (...) { }`
    # gets greedily matched as a constructor named "for")
    m = re.match(r"^if\s*\((.+)\)$", line) or re.match(r"^if\s+(.+)$", line)
    if m and nxt and nxt[0] == "open":
        cond = m.group(1)
        body, ni = _parse_block(toks, i + 2, dialect)
        orelse = []
        if ni < len(toks) and toks[ni][0] == "line" and re.match(r"^else\b", toks[ni][1]):
            after_else = toks[ni][1]
            if re.match(r"^else\s+if\b", after_else):
                # parse nested if
                rest = after_else.replace("else ", "", 1)
                # rebuild a sub-tokens pair: synthetic line for the if
                fake = [("line", rest)] + list(toks[ni + 1:])
                sub, used = _parse_line(fake, 0, dialect)
                if sub is not None:
                    orelse = [sub]
                ni = ni + 1 + (used - 1)
            else:
                if ni + 1 < len(toks) and toks[ni + 1][0] == "open":
                    orelse, ni = _parse_block(toks, ni + 2, dialect)
                else:
                    ni += 1
        return ir.If(cond, body, orelse), ni

    # while
    m = re.match(r"^while\s*\((.+)\)$", line) or re.match(r"^while\s+(.+)$", line)
    if m and nxt and nxt[0] == "open":
        body, ni = _parse_block(toks, i + 2, dialect)
        return ir.While(m.group(1), body), ni

    # for(...;...;...)
    m = re.match(r"^for\s*\(\s*(?:int\s+|var\s+|let\s+|const\s+|long\s+)?([A-Za-z_]\w*)\s*=\s*(.+?)\s*;\s*\1\s*<\s*(.+?)\s*;\s*\1\s*\+\+\s*\)$", line)
    if m and nxt and nxt[0] == "open":
        body, ni = _parse_block(toks, i + 2, dialect)
        return ir.ForRange(m.group(1), m.group(2), m.group(3), body), ni

    # for-each: handles JS `of`, Java `:`, Kotlin/Swift `in`
    m = (
        re.match(r"^for\s*\(\s*(?:var\s+|let\s+|const\s+|auto\s+|[\w<>\[\],\s]+\s+)?([A-Za-z_]\w*)\s*:\s*(.+?)\)$", line)
        or re.match(r"^for\s*\(\s*(?:var\s+|let\s+|const\s+|auto\s+|[\w<>\[\],\s]+\s+)?([A-Za-z_]\w*)\s+(?:of|in)\s+(.+?)\)$", line)
        or re.match(r"^for\s+([A-Za-z_]\w*)\s+in\s+(.+)$", line)
    )
    if m and nxt and nxt[0] == "open":
        body, ni = _parse_block(toks, i + 2, dialect)
        return ir.ForEach(m.group(1), m.group(2), body), ni

    # function (after control-flow checks so `for (...)` isn't read as a fn)
    if nxt and nxt[0] == "open":
        for rx in _FN_RES:
            m = rx.match(line)
            if m and m.group(1) not in {"if", "for", "while", "switch", "do",
                                         "else", "return", "try", "catch",
                                         "synchronized", "throw"}:
                params = _strip_param_types(m.group(2))
                body, ni = _parse_block(toks, i + 2, dialect)
                return ir.FunctionDef(m.group(1), params, body), ni

    # return / break / continue
    m = re.match(r"^return\s*(.*)$", line)
    if m:
        v = m.group(1).strip()
        return ir.Return(v if v else None), i + 1
    if line == "break":
        return ir.Break(), i + 1
    if line == "continue":
        return ir.Continue(), i + 1

    # print-likes
    for rx in _PRINT_RE:
        m = rx.match(line)
        if m:
            return ir.Print([m.group(1)]), i + 1

    # const / let / var / val
    m = re.match(r"^(const|let|var|val)\s+([A-Za-z_]\w*)\s*(?::\s*([\w<>\[\],\s]+))?\s*=\s*(.+)$", line)
    if m:
        decl = m.group(1)
        return ir.Assign(m.group(2), m.group(4), declare=decl, type_hint=m.group(3)), i + 1

    # typed declaration: int x = 3 / Map<String, Book> books = new HashMap<>() / int[] xs = {...}
    m = re.match(
        r"^([A-Za-z_]\w*(?:\s*<[^<>]*(?:<[^<>]*>[^<>]*)*>)?(?:\s*\[\s*\])?)\s+([A-Za-z_]\w*)\s*=\s*(.+)$",
        line,
    )
    if m and m.group(1) not in {"return", "if", "while", "for", "else", "switch", "case", "do"}:
        return ir.Assign(m.group(2), m.group(3), declare="var", type_hint=m.group(1)), i + 1

    # plain assignment
    m = re.match(r"^([A-Za-z_][\w\.\[\]]*)\s*=\s*(.+)$", line)
    if m:
        return ir.Assign(m.group(1), m.group(2)), i + 1

    # bare Java/C# field declaration like "String isbn, title, author" or "int x"
    # — no assignment, no parens, no braces. Drop it (target lang may not need typed decls).
    if "(" not in line and "=" not in line and _FIELD_RE.match(line):
        return None, i + 1

    return ir.Call(line), i + 1


def parse_brace(source: str, dialect: str = "javascript"):
    toks = _tokenize_brace(source, dialect)
    body, _ = _parse_block(toks + [("close", None)], 0, dialect)
    return ir.Module(body)


# ---- End-block parser (Ruby/Lua/Elixir-ish) ----
def parse_end_block(source: str, dialect: str = "ruby"):
    lines = source.splitlines()
    root = []
    stack = [{"body": root, "kind": "root"}]

    def cur():
        return stack[-1]["body"]

    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if dialect == "ruby" and line.startswith("#"):
            cur().append(ir.Comment(line[1:].strip()))
            continue
        if dialect == "lua" and line.startswith("--"):
            cur().append(ir.Comment(line[2:].strip()))
            continue

        m = re.match(r"^def\s+([A-Za-z_]\w*)\s*(?:\(([^)]*)\))?$", line)
        if m:
            params = [p.strip() for p in (m.group(2) or "").split(",") if p.strip()]
            node = ir.FunctionDef(m.group(1), params, [])
            cur().append(node)
            stack.append({"body": node["body"], "kind": "fn"})
            continue

        m = re.match(r"^class\s+([A-Za-z_]\w*)\s*$", line)
        if m:
            node = ir.ClassDef(m.group(1), [])
            cur().append(node)
            stack.append({"body": node["body"], "kind": "cls"})
            continue

        m = re.match(r"^if\s+(.+?)(?:\s+then)?$", line)
        if m and "=>" not in line:
            node = ir.If(m.group(1), [], [])
            cur().append(node)
            stack.append({"body": node["body"], "kind": "if", "_if": node})
            continue

        m = re.match(r"^els(?:e\s*)?if\s+(.+?)(?:\s+then)?$", line)
        if m:
            top = stack[-1]
            if "_if" in top:
                inner = ir.If(m.group(1), [], [])
                top["_if"]["orelse"].append(inner)
                stack.pop()
                stack.append({"body": inner["body"], "kind": "if", "_if": inner})
                continue

        if re.match(r"^else\s*$", line):
            top = stack[-1]
            if "_if" in top:
                stack.pop()
                stack.append({"body": top["_if"]["orelse"], "kind": "else"})
                continue

        m = re.match(r"^while\s+(.+?)(?:\s+do)?$", line)
        if m:
            node = ir.While(m.group(1), [])
            cur().append(node)
            stack.append({"body": node["body"], "kind": "while"})
            continue

        m = re.match(r"^for\s+([A-Za-z_]\w*)\s+in\s+(.+?)(?:\s+do)?$", line)
        if m:
            node = ir.ForEach(m.group(1), m.group(2), [])
            cur().append(node)
            stack.append({"body": node["body"], "kind": "for"})
            continue

        if line == "end":
            if len(stack) > 1:
                stack.pop()
            continue

        m = re.match(r"^return\s*(.*)$", line)
        if m:
            cur().append(ir.Return(m.group(1) or None))
            continue
        m = re.match(r"^puts\s+(.+)$", line)
        if m:
            cur().append(ir.Print([m.group(1)]))
            continue
        m = re.match(r"^print\s*\((.*)\)$", line)
        if m:
            cur().append(ir.Print([m.group(1)]))
            continue
        m = re.match(r"^([A-Za-z_]\w*)\s*=\s*(.+)$", line)
        if m:
            cur().append(ir.Assign(m.group(1), m.group(2)))
            continue
        cur().append(ir.Call(line))
    return ir.Module(root)
