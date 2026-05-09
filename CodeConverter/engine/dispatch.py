"""Dispatch a (source_lang, target_lang, code) request to the right
parser + emitter. Returns the converted source as a string.
"""
from .html_parser import parse_html
from .python_parser import parse_python
from .code_parser import parse_brace, parse_end_block
from .html_emitters import emit_html
from .code_emitters import emit_code

LANGUAGES = [
    ("javascript", "JavaScript", "js"),
    ("typescript", "TypeScript", "ts"),
    ("python", "Python", "py"),
    ("java", "Java", "java"),
    ("csharp", "C#", "cs"),
    ("cpp", "C++", "cpp"),
    ("c", "C", "c"),
    ("swift", "Swift", "swift"),
    ("go", "Go", "go"),
    ("rust", "Rust", "rs"),
    ("kotlin", "Kotlin", "kt"),
    ("php", "PHP", "php"),
    ("ruby", "Ruby", "rb"),
    ("dart", "Dart", "dart"),
    ("scala", "Scala", "scala"),
    ("groovy", "Groovy", "groovy"),
    ("perl", "Perl", "pl"),
    ("lua", "Lua", "lua"),
    ("r", "R", "r"),
    ("matlab", "MATLAB", "m"),
    ("bash", "Bash", "sh"),
    ("powershell", "PowerShell", "ps1"),
    ("sql", "SQL", "sql"),
    ("html", "HTML", "html"),
    ("css", "CSS", "css"),
    ("jsx", "React (JSX)", "jsx"),
    ("vue", "Vue", "vue"),
    ("swiftui", "SwiftUI", "swift"),
    ("haskell", "Haskell", "hs"),
    ("elixir", "Elixir", "ex"),
    ("julia", "Julia", "jl"),
    ("fsharp", "F#", "fs"),
    ("clojure", "Clojure", "clj"),
    ("erlang", "Erlang", "erl"),
    ("pascal", "Pascal", "pas"),
    ("vbnet", "VB.NET", "vb"),
    ("objc", "Objective-C", "m"),
]


def list_languages():
    return [{"id": i, "name": n, "ext": e} for i, n, e in LANGUAGES]


# --- parsers per source language ---
END_BLOCK = {"ruby", "lua", "elixir"}


# --- language families used to decide which pairs make sense ---
CODE_LANGS = {
    "javascript", "typescript", "python", "java", "csharp", "cpp", "c",
    "swift", "go", "rust", "kotlin", "php", "ruby", "dart", "scala",
    "groovy", "perl", "lua", "r", "matlab", "bash", "powershell",
    "haskell", "elixir", "julia", "fsharp", "clojure", "erlang",
    "pascal", "vbnet", "objc",
}
# Markup-ish targets that "describe a UI" rather than imperative logic
MARKUP_LANGS = {"html", "jsx", "vue", "swiftui"}


def compatibility(src: str, dst: str):
    """Return (possible: bool, reason: str). Empty reason means it's allowed."""
    if src == dst:
        return False, "Source and target are the same language."

    # Programming logic doesn't translate to a markup/styling/query language —
    # there's no meaningful way to render arbitrary control flow as HTML/CSS/SQL.
    if src in CODE_LANGS and dst in MARKUP_LANGS:
        return False, (f"Can't convert {src} → {dst}: program logic has no "
                       "structural equivalent in markup. Use a templating engine instead.")
    if src in CODE_LANGS and dst == "css":
        return False, "Can't convert program logic into CSS — CSS is a styling language."
    if src in CODE_LANGS and dst == "sql":
        return False, "Can't convert program logic into SQL — SQL describes queries, not control flow."

    # CSS is descriptive styling — no general translation target
    if src == "css" and dst != "css":
        return False, "CSS is purely for styling and has no equivalent in other languages."

    # Bare SQL is queries — doesn't carry over to general code
    if src == "sql":
        return False, "SQL queries don't translate meaningfully to general programming languages."

    # HTML → CSS/SQL doesn't make sense either
    if src == "html" and dst in {"css", "sql"}:
        return False, f"HTML structure has no meaningful {dst.upper()} equivalent."

    # Same idea in reverse for markup-ish sources we don't fully parse yet
    if src in {"jsx", "vue", "swiftui"} and dst not in MARKUP_LANGS | {"javascript", "typescript", "html"}:
        return False, f"Conversion from {src} to {dst} isn't supported."

    return True, ""


def compatibility_matrix():
    """Map of {src: {dst: bool}} so the UI can grey out impossible options."""
    out = {}
    for sid, _, _ in LANGUAGES:
        out[sid] = {}
        for did, _, _ in LANGUAGES:
            out[sid][did] = compatibility(sid, did)[0]
    return out


def parse(source: str, lang: str):
    """Parse source code into the appropriate IR (code or html)."""
    if lang == "html":
        return ("html", parse_html(source))
    if lang == "python":
        return ("code", parse_python(source))
    if lang in END_BLOCK:
        return ("code", parse_end_block(source, lang))
    return ("code", parse_brace(source, lang))


def emit(ir_kind: str, ir_root, target: str) -> str:
    if ir_kind == "html":
        return emit_html(ir_root, target)
    return emit_code(ir_root, target)


class IncompatiblePair(ValueError):
    pass


def convert(source: str, src_lang: str, dst_lang: str) -> str:
    if not source.strip():
        return ""
    ok, reason = compatibility(src_lang, dst_lang)
    if not ok:
        raise IncompatiblePair(reason)
    ir_kind, ir_root = parse(source, src_lang)
    return emit(ir_kind, ir_root, dst_lang)
