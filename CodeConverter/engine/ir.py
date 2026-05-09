"""Intermediate Representation (IR) used by all parsers + emitters.

Two distinct trees:
  * code IR  — Module / Function / If / For / While / Assign / Call / Print / Class / Return
  * html IR  — Document of Element / Text / Comment / Doctype nodes

Both are plain dicts so they JSON-serialize cleanly to the browser.
"""

# ---- Code IR factories ----
def Module(body):                   return {"k": "module", "body": body}
def FunctionDef(name, params, body, returns=None):
    return {"k": "fn", "name": name, "params": params, "body": body, "returns": returns}
def ClassDef(name, body, bases=None):
    return {"k": "cls", "name": name, "body": body, "bases": bases or []}
def If(test, body, orelse=None):
    return {"k": "if", "test": test, "body": body, "orelse": orelse or []}
def While(test, body):
    return {"k": "while", "test": test, "body": body}
def ForRange(var, start, end, body, step=1):
    return {"k": "forR", "var": var, "start": start, "end": end, "body": body, "step": step}
def ForEach(var, it, body):
    return {"k": "forE", "var": var, "iter": it, "body": body}
def Assign(target, value, declare=None, type_hint=None):
    return {"k": "assign", "target": target, "value": value, "declare": declare, "type": type_hint}
def AugAssign(target, op, value):
    return {"k": "aug", "target": target, "op": op, "value": value}
def Return(value=None):              return {"k": "return", "value": value}
def Print(args):                     return {"k": "print", "args": args}
def Call(expr):                      return {"k": "call", "expr": expr}
def Comment(text):                   return {"k": "comment", "text": text}
def Break():                         return {"k": "break"}
def Continue():                      return {"k": "continue"}
def Raw(text):                       return {"k": "raw", "text": text}

# ---- HTML IR factories ----
def Document(children):              return {"k": "doc", "children": children}
def Element(tag, attrs, children, void=False):
    return {"k": "el", "tag": tag, "attrs": attrs, "children": children, "void": void}
def Text(value):                     return {"k": "text", "value": value}
def HtmlComment(value):              return {"k": "hcomment", "value": value}
def Doctype(value):                  return {"k": "doctype", "value": value}
