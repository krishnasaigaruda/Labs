"""Real HTML parser using stdlib html.parser. Produces an HTML IR tree.

Handles: doctype, comments, void elements, raw-text elements (script/style),
boolean attributes, attributes without quotes, nested structures.
"""
from html.parser import HTMLParser
from .ir import Document, Element, Text, HtmlComment, Doctype

VOID = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}
RAW_TEXT = {"script", "style", "textarea", "title"}


class _Parser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.root = []          # top-level nodes
        self.stack = [self.root]
        self.raw_tag = None     # name of current raw-text element (e.g. 'script')
        self.raw_buf = []

    # convenience to push to current open element's children
    def _push(self, node):
        self.stack[-1].append(node)

    def handle_decl(self, decl):
        # e.g. 'DOCTYPE html'
        m = decl.strip()
        if m.lower().startswith("doctype"):
            value = m[len("doctype"):].strip() or "html"
            self._push(Doctype(value))
        else:
            self._push(Doctype(m))

    def handle_comment(self, data):
        self._push(HtmlComment(data))

    def handle_starttag(self, tag, attrs):
        attrs_d = {}
        for k, v in attrs:
            attrs_d[k] = True if v is None else v
        is_void = tag.lower() in VOID
        el = Element(tag, attrs_d, [], void=is_void)
        self._push(el)
        if is_void:
            return
        self.stack.append(el["children"])
        if tag.lower() in RAW_TEXT:
            self.raw_tag = tag.lower()
            self.raw_buf = []

    def handle_startendtag(self, tag, attrs):
        # <br/> or <img />
        attrs_d = {}
        for k, v in attrs:
            attrs_d[k] = True if v is None else v
        self._push(Element(tag, attrs_d, [], void=True))

    def handle_endtag(self, tag):
        if self.raw_tag and tag.lower() == self.raw_tag:
            # flush raw buffer as a Text child of the raw-text element
            text = "".join(self.raw_buf)
            if text:
                self.stack[-1].append(Text(text))
            self.raw_tag = None
            self.raw_buf = []
        # pop matching open element if any
        if len(self.stack) > 1:
            self.stack.pop()

    def handle_data(self, data):
        if self.raw_tag:
            self.raw_buf.append(data)
            return
        if data.strip() == "" and "\n" in data:
            # collapse pure-whitespace formatting between tags
            return
        self._push(Text(data))

    def handle_entityref(self, name):
        if self.raw_tag:
            self.raw_buf.append(f"&{name};")
        else:
            self._push(Text(f"&{name};"))

    def handle_charref(self, name):
        if self.raw_tag:
            self.raw_buf.append(f"&#{name};")
        else:
            self._push(Text(f"&#{name};"))


def parse_html(source: str):
    p = _Parser()
    p.feed(source)
    p.close()
    return Document(p.root)
