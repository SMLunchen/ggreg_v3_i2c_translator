"""Minimal S-expression reader/writer for KiCad files, plus symbol-library helpers."""
import os
import re

KICAD_SHARE = r"C:\Program Files\KiCad\9.0\share\kicad"

_TOKEN = re.compile(r'\s*(?:(\()|(\))|"((?:[^"\\]|\\.)*)"|([^\s()"]+))')


class Sym(str):
    """An unquoted atom (keyword / number)."""


def parse(text):
    stack = [[]]
    pos = 0
    n = len(text)
    while pos < n:
        m = _TOKEN.match(text, pos)
        if not m:
            break
        pos = m.end()
        if m.group(1):
            new = []
            stack[-1].append(new)
            stack.append(new)
        elif m.group(2):
            stack.pop()
        elif m.group(3) is not None:
            stack[-1].append(m.group(3).replace('\\"', '"').replace("\\\\", "\\"))
        else:
            stack[-1].append(Sym(m.group(4)))
    return stack[0][0]


def dump(node, indent=0):
    if isinstance(node, Sym):
        return str(node)
    if isinstance(node, str):
        return '"' + node.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(node, (int, float)):
        return ("%.4f" % node).rstrip("0").rstrip(".") if isinstance(node, float) else str(node)
    simple = all(not isinstance(c, list) for c in node)
    if simple:
        return "(" + " ".join(dump(c) for c in node) + ")"
    pad = "\t" * (indent + 1)
    out = "(" + dump(node[0])
    for c in node[1:]:
        if isinstance(c, list):
            out += "\n" + pad + dump(c, indent + 1)
        else:
            out += " " + dump(c)
    return out + "\n" + "\t" * indent + ")"


def S(*items):
    """Build a list node; first item is the keyword."""
    return [Sym(items[0])] + list(items[1:])


def find(node, key):
    return [c for c in node[1:] if isinstance(c, list) and c and c[0] == key]


_lib_cache = {}


def load_symbol(lib, name):
    """Return a flattened (no 'extends') symbol node named 'lib:name'."""
    if lib not in _lib_cache:
        path = os.path.join(KICAD_SHARE, "symbols", lib + ".kicad_sym")
        with open(path, encoding="utf-8") as f:
            _lib_cache[lib] = parse(f.read())
    root = _lib_cache[lib]
    by_name = {c[1]: c for c in find(root, "symbol")}
    node = by_name[name]
    ext = find(node, "extends")
    if ext:
        parent = load_symbol(lib, ext[0][1])
        pname = ext[0][1]
        flat = [Sym("symbol"), name]
        props = {p[1]: p for p in find(node, "property")}
        seen = set()
        for c in parent[2:]:
            if isinstance(c, list) and c[0] == "property":
                seen.add(c[1])
                flat.append(props.get(c[1], c))
            elif isinstance(c, list) and c[0] == "symbol":
                sub = _deep(c)
                sub[1] = name + sub[1][len(pname):]
                flat.append(sub)
            else:
                flat.append(c)
        for k, p in props.items():
            if k not in seen:
                flat.append(p)
        node = flat
    else:
        node = _deep(node)
    node[1] = name
    return node


def _deep(n):
    return [_deep(c) if isinstance(c, list) else c for c in n]


def symbol_pins(sym):
    """{number: (x, y, angle, name, type)} in symbol coordinates (y up)."""
    pins = {}
    for sub in find(sym, "symbol"):
        for p in find(sub, "pin"):
            at = find(p, "at")[0]
            num = find(p, "number")[0][1]
            nm = find(p, "name")[0][1]
            ang = float(at[3]) if len(at) > 3 else 0.0
            pins[str(num)] = (float(at[1]), float(at[2]), ang, str(nm), str(p[1]))
    return pins


if __name__ == "__main__":
    import sys
    for spec in sys.argv[1:]:
        lib, name = spec.split(":")
        s = load_symbol(lib, name)
        print(spec)
        for num, v in sorted(symbol_pins(s).items(), key=lambda kv: (len(kv[0]), kv[0])):
            print("   pin %-3s at (%7.2f,%7.2f) ang %3d  %-22s %s" % (num, v[0], v[1], v[2], v[3], v[4]))
