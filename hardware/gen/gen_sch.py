"""Generate the KiCad 9 schematic from design.py (label-style: every pin gets a named stub)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import design as D
from sexpr import S, Sym, dump, find, load_symbol, symbol_pins

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", D.PROJECT + ".kicad_sch")
G = 2.54
STUB = 2.54
ROOT = D.uid("root-sheet")
YES, NO = Sym("yes"), Sym("no")


def r(v):
    return round(v, 4)


def effects(size=1.27, justify=None, hide=False):
    e = S("effects", S("font", S("size", size, size)))
    if justify:
        e.append(S("justify", *[Sym(j) for j in justify]))
    if hide:
        e.append(S("hide", YES))
    return e


def wire(x1, y1, x2, y2, key):
    return S("wire", S("pts", S("xy", r(x1), r(y1)), S("xy", r(x2), r(y2))),
             S("stroke", S("width", 0), S("type", Sym("default"))), S("uuid", D.uid("w" + key)))


def label(net, x, y, ang, key):
    just = ("left", "bottom") if ang in (0, 90) else ("right", "bottom")
    return S("label", net, S("at", r(x), r(y), ang), effects(1.27, just), S("uuid", D.uid("l" + key)))


def text(t, x, y, size=1.5):
    return S("text", t, S("exclude_from_sim", NO), S("at", r(x), r(y), 0),
             effects(size, ("left", "bottom")), S("uuid", D.uid("t" + t)))


parts = list(D.PARTS) + [
    dict(ref="#FLG01", sym="power:PWR_FLAG", value="PWR_FLAG", fp="", sch=(36, 13), nets={"1": "VCC"}, bom=False, board=False),
    dict(ref="#FLG02", sym="power:PWR_FLAG", value="PWR_FLAG", fp="", sch=(40, 13), nets={"1": "GND"}, bom=False, board=False),
    # the GGreg20 supply rails are fed from connectors / the switch, tell ERC so
]

lib_symbols = S("lib_symbols")
loaded = {}
items = []

for p in parts:
    lib, name = p["sym"].split(":")
    if p["sym"] not in loaded:
        node = load_symbol(lib, name)
        node[1] = p["sym"]
        loaded[p["sym"]] = node
        lib_symbols.append(node)
    node = loaded[p["sym"]]
    pins = symbol_pins(node)
    sx, sy = p["sch"][0] * G, p["sch"][1] * G
    ref = p["ref"]

    inst = S("symbol", S("lib_id", p["sym"]), S("at", r(sx), r(sy), 0), S("unit", 1),
             S("exclude_from_sim", NO), S("in_bom", YES if p.get("bom", True) else NO),
             S("on_board", YES if p.get("board", True) else NO),
             S("dnp", YES if p.get("dnp") else NO), S("uuid", D.uid("sym:" + ref)))
    for prop in find(node, "property"):
        key = prop[1]
        val = {"Reference": ref, "Value": p["value"], "Footprint": p["fp"]}.get(key, prop[2])
        at = find(prop, "at")[0]
        new = S("property", key, val, S("at", r(sx + float(at[1])), r(sy - float(at[2])), at[3] if len(at) > 3 else 0))
        new += [c for c in prop[3:] if isinstance(c, list) and c[0] == "effects"]
        inst.append(new)
    for num in pins:
        inst.append(S("pin", num, S("uuid", D.uid("pin:%s:%s" % (ref, num)))))
    inst.append(S("instances", S("project", D.PROJECT, S("path", "/" + ROOT, S("reference", ref), S("unit", 1)))))
    items.append(inst)

    for num, (px, py, ang, _nm, _typ) in pins.items():
        x, y = sx + px, sy - py
        net = p["nets"].get(num)
        if net is None:
            items.append(S("no_connect", S("at", r(x), r(y)), S("uuid", D.uid("nc:%s:%s" % (ref, num)))))
            continue
        dx, dy, lang = {0: (-STUB, 0, 180), 180: (STUB, 0, 0), 90: (0, STUB, 270), 270: (0, -STUB, 90)}[int(ang)]
        key = "%s:%s" % (ref, num)
        items.append(wire(x, y, x + dx, y + dy, key))
        items.append(label(net, x + dx, y + dy, lang, key))

notes = [
    ("I2C host (RadSens pinout)", 8, 6),
    ("Decoupling", 24, 6),
    ("R1, R2: only fit if the host has no I2C pull-ups", 8, 27.5),
    ("UPDI programming", 8, 30.5),
    ("Optional crystal (USE_XTAL32K=1)", 12, 40),
    ("Pulse input from GGreg20_V3 OUT (active low, 3.0-3.3 V / 0.7 V)", 70, 6),
    ("R4: only fit if OUT has no pull-up of its own", 70, 7.2),
    ("Indicator LED", 76, 24),
    ("Switched GGreg20 supply (soft start via C3, default off via R8)", 62, 38),
    ("JP1: GGreg20 supply from I2C VCC (bridged 1-2, default) or from J5 VIN (2-3)", 62, 39.2),
    ("Unused MCU pins are left open (input buffer disabled in firmware)", 44, 46),
]
for t, x, y in notes:
    items.append(text(t, x * G, y * G))

sch = S("kicad_sch", S("version", 20250114), S("generator", "eeschema"), S("generator_version", "9.0"),
        S("uuid", ROOT), S("paper", "A4"),
        S("title_block", S("title", D.TITLE), S("date", D.DATE), S("rev", D.REV)),
        lib_symbols)
sch += items
sch.append(S("sheet_instances", S("path", "/", S("page", "1"))))
sch.append(S("embedded_fonts", NO))

with open(OUT, "w", encoding="utf-8", newline="\n") as f:
    f.write(dump(sch) + "\n")
print("wrote", os.path.normpath(OUT))
