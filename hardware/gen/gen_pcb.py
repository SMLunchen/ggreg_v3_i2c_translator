"""Generate the KiCad 9 PCB from design.py: placement, maze-routed tracks, GND pours.

Run with KiCad's own Python:  "C:\\Program Files\\KiCad\\9.0\\bin\\python.exe" gen_pcb.py
"""
import heapq
import math
import os
import sys

import pcbnew

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import design as D
from sexpr import KICAD_SHARE

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.normpath(os.path.join(HERE, "..", D.PROJECT + ".kicad_pcb"))
FPDIR = os.path.join(KICAD_SHARE, "footprints")
OX, OY = D.BOARD_ORIGIN
W, H = D.BOARD_W, D.BOARD_H
mm = pcbnew.FromMM
LAYERS = [pcbnew.F_Cu, pcbnew.B_Cu]

GS = 0.25                       # routing grid
NX, NY = int(round(W / GS)) + 1, int(round(H / GS)) + 1
CLR = D.CLEARANCE
MARGIN = 0.03
EDGE_CLR = 0.5
VIA_R = D.VIA_DIA / 2
VIA_COST = 20.0
BOTTOM_FACTOR = 1.3
GND_STUB_W = 0.3


def P(x, y):
    return pcbnew.VECTOR2I(mm(OX + x), mm(OY + y))


# --------------------------------------------------------------------------- board
board = pcbnew.NewBoard(OUT)
ds = board.GetDesignSettings()
nc = ds.m_NetSettings.GetDefaultNetclass()
nc.SetClearance(mm(CLR))
nc.SetTrackWidth(mm(D.SIGNAL_WIDTH))
nc.SetViaDiameter(mm(D.VIA_DIA))
nc.SetViaDrill(mm(D.VIA_DRILL))
ds.m_TrackMinWidth = mm(0.2)
ds.m_ViasMinSize = mm(0.5)
ds.m_MinThroughDrill = mm(0.3)
ds.m_CopperEdgeClearance = mm(0.3)

nets = {}
for name in D.all_nets():
    ni = pcbnew.NETINFO_ITEM(board, "/" + name)
    board.Add(ni)
    nets[name] = ni

# outline with rounded corners
RAD = 2.0


def edge_line(x1, y1, x2, y2):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_SEGMENT)
    s.SetStart(P(x1, y1))
    s.SetEnd(P(x2, y2))
    s.SetLayer(pcbnew.Edge_Cuts)
    s.SetWidth(mm(0.1))
    board.Add(s)


def edge_arc(cx, cy, a0):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_ARC)
    pts = [(cx + RAD * math.cos(math.radians(a)), cy + RAD * math.sin(math.radians(a))) for a in (a0, a0 + 45, a0 + 90)]
    s.SetArcGeometry(P(*pts[0]), P(*pts[1]), P(*pts[2]))
    s.SetLayer(pcbnew.Edge_Cuts)
    s.SetWidth(mm(0.1))
    board.Add(s)


edge_line(RAD, 0, W - RAD, 0)
edge_line(W, RAD, W, H - RAD)
edge_line(W - RAD, H, RAD, H)
edge_line(0, H - RAD, 0, RAD)
edge_arc(RAD, RAD, 180)
edge_arc(W - RAD, RAD, 270)
edge_arc(W - RAD, H - RAD, 0)
edge_arc(RAD, H - RAD, 90)

# --------------------------------------------------------------------------- footprints
pads = []       # dict(net, layers, rect, center, ref, num, smd)
for p in D.PARTS:
    lib, name = p["fp"].split(":")
    fp = pcbnew.FootprintLoad(os.path.join(FPDIR, lib + ".pretty"), name)
    fp.SetFPID(pcbnew.LIB_ID(lib, name))
    fp.SetReference(p["ref"])
    fp.SetValue(p["value"])
    x, y, rot = p["pcb"]
    fp.SetPosition(P(x, y))
    fp.SetOrientationDegrees(rot)
    fp.SetPath(pcbnew.KIID_PATH("/" + D.uid("sym:" + p["ref"])))
    fp.SetSheetname("/")
    fp.SetSheetfile(D.PROJECT + ".kicad_sch")
    attrs = fp.GetAttributes()
    if p.get("dnp"):
        attrs |= pcbnew.FP_DNP
        fp.SetDNP(True)
    if p.get("bom") is False:
        attrs |= pcbnew.FP_EXCLUDE_FROM_BOM | pcbnew.FP_EXCLUDE_FROM_POS_FILES
    fp.SetAttributes(attrs)
    rt = fp.Reference()
    rt.SetTextSize(pcbnew.VECTOR2I(mm(0.8), mm(0.8)))
    rt.SetTextThickness(mm(0.12))
    if p["ref"] in D.HIDE_REF:
        rt.SetVisible(False)
    if p["ref"] in D.REF_POS:
        rx, ry, rrot = D.REF_POS[p["ref"]]
        rt.SetPosition(P(rx, ry))
        rt.SetTextAngleDegrees(rrot)
    board.Add(fp)
    for pad in fp.Pads():
        num = pad.GetNumber()
        net = p["nets"].get(num)
        if net is None and num in p.get("nc", {}):
            # same name eeschema gives to a pin carrying a no-connect flag
            net = "unconnected-(%s-%s-Pad%s)" % (p["ref"], p["nc"][num], num)
            if net not in nets:
                nets[net] = pcbnew.NETINFO_ITEM(board, net)
                board.Add(nets[net])
        if net:
            pad.SetNet(nets[net])
        bb = pad.GetBoundingBox()
        rect = (pcbnew.ToMM(bb.GetLeft()) - OX, pcbnew.ToMM(bb.GetTop()) - OY,
                pcbnew.ToMM(bb.GetRight()) - OX, pcbnew.ToMM(bb.GetBottom()) - OY)
        c = pad.GetPosition()
        smd = pad.GetAttribute() == pcbnew.PAD_ATTRIB_SMD
        pads.append(dict(net=net, layers=(0,) if smd else (0, 1), rect=rect, smd=smd,
                         center=(pcbnew.ToMM(c.x) - OX, pcbnew.ToMM(c.y) - OY), ref=p["ref"], num=num))

# --------------------------------------------------------------------------- router
# obstacles: (layers, kind, geom, net); kind 'rect' -> (x1,y1,x2,y2), 'seg' -> (x1,y1,x2,y2,halfwidth)
obstacles = [(pd["layers"], "rect", pd["rect"], pd["net"]) for pd in pads]
via_keepout = [pd["rect"] for pd in pads]       # no via in or right next to any pad
HOLES = [(p["pcb"][0], p["pcb"][1]) for p in D.PARTS if p["ref"][0] == "H"]
for (hx, hy) in HOLES:                          # keep copper away from the screw heads
    obstacles.append(((0, 1), "seg", (hx, hy, hx, hy, D.MOUNT_KEEPOUT_R), None))
DIRS = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]
STEP = [1.0, 1.4142] * 4


def seg_dist(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    L = dx * dx + dy * dy
    t = 0.0 if L == 0 else max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / L))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def blocked_map(net, hw):
    """blocked[layer][i][j] for a track of half-width hw belonging to 'net'."""
    r = hw + CLR + MARGIN
    blk = [[[False] * NY for _ in range(NX)] for _ in range(2)]
    e = EDGE_CLR + hw
    for layer in range(2):
        b = blk[layer]
        for i in range(NX):
            for j in range(NY):
                x, y = i * GS, j * GS
                if x < e or y < e or x > W - e or y > H - e:
                    b[i][j] = True
    for layers, kind, g, onet in obstacles:
        if onet is not None and onet == net:
            continue
        if kind == "rect":
            x1, y1, x2, y2 = g[0] - r, g[1] - r, g[2] + r, g[3] + r
            ohw = 0
        else:
            ohw = g[4]
            x1, y1 = min(g[0], g[2]) - r - ohw, min(g[1], g[3]) - r - ohw
            x2, y2 = max(g[0], g[2]) + r + ohw, max(g[1], g[3]) + r + ohw
        i1, i2 = max(0, int(math.ceil(x1 / GS))), min(NX - 1, int(math.floor(x2 / GS)))
        j1, j2 = max(0, int(math.ceil(y1 / GS))), min(NY - 1, int(math.floor(y2 / GS)))
        for i in range(i1, i2 + 1):
            for j in range(j1, j2 + 1):
                if kind == "seg" and seg_dist(i * GS, j * GS, g[0], g[1], g[2], g[3]) > ohw + r:
                    continue
                for layer in layers:
                    blk[layer][i][j] = True
    return blk


def via_map(net):
    blk = blocked_map(net, VIA_R)
    ok = [[not (blk[0][i][j] or blk[1][i][j]) for j in range(NY)] for i in range(NX)]
    k = VIA_R + 0.25
    for (x1, y1, x2, y2) in via_keepout:
        i1, i2 = max(0, int(math.ceil((x1 - k) / GS))), min(NX - 1, int(math.floor((x2 + k) / GS)))
        j1, j2 = max(0, int(math.ceil((y1 - k) / GS))), min(NY - 1, int(math.floor((y2 + k) / GS)))
        for i in range(i1, i2 + 1):
            for j in range(j1, j2 + 1):
                ok[i][j] = False
    return ok


def pad_cells(pd, blk):
    x1, y1, x2, y2 = pd["rect"]
    s = 0.05
    cells = []
    for layer in pd["layers"]:
        for i in range(int(math.ceil((x1 + s) / GS)), int(math.floor((x2 - s) / GS)) + 1):
            for j in range(int(math.ceil((y1 + s) / GS)), int(math.floor((y2 - s) / GS)) + 1):
                if 0 <= i < NX and 0 <= j < NY and not blk[layer][i][j]:
                    cells.append((layer, i, j))
    return cells


def search(sources, is_target, blk, vok, allow_via=True):
    """Dijkstra over (layer, i, j, direction). Returns list of (layer, i, j) or None."""
    def key(l, i, j, d):
        return ((l * NX + i) * NY + j) * 9 + d
    dist = {}
    prev = {}
    heap = []
    for (l, i, j) in sources:
        k = key(l, i, j, 8)
        dist[k] = 0.0
        heap.append((0.0, l, i, j, 8))
    heapq.heapify(heap)
    while heap:
        c, l, i, j, d = heapq.heappop(heap)
        k = key(l, i, j, d)
        if dist.get(k, 1e18) < c:
            continue
        if is_target(l, i, j) and c > 0:
            path = [(l, i, j)]
            while k in prev:
                k, (l, i, j) = prev[k]
                path.append((l, i, j))
            return path[::-1]
        b = blk[l]
        f = BOTTOM_FACTOR if l == 1 else 1.0
        for nd in range(8):
            if d != 8:
                turn = abs(nd - d)
                turn = min(turn, 8 - turn)
                if turn > 2:
                    continue
                tc = (0.0, 0.25, 1.5)[turn]
            else:
                tc = 0.0
            dx, dy = DIRS[nd]
            ni, nj = i + dx, j + dy
            if not (0 <= ni < NX and 0 <= nj < NY) or b[ni][nj]:
                continue
            if dx and dy and (b[ni][j] or b[i][nj]):
                continue
            ncost = c + STEP[nd] * f + tc
            nk = key(l, ni, nj, nd)
            if ncost < dist.get(nk, 1e18):
                dist[nk] = ncost
                prev[nk] = (k, (l, i, j))
                heapq.heappush(heap, (ncost, l, ni, nj, nd))
        if allow_via and vok[i][j] and not blk[1 - l][i][j]:
            nk = key(1 - l, i, j, 8)
            ncost = c + VIA_COST
            if ncost < dist.get(nk, 1e18):
                dist[nk] = ncost
                prev[nk] = (k, (l, i, j))
                heapq.heappush(heap, (ncost, 1 - l, i, j, 8))
    return None


def add_track(net, layer, x1, y1, x2, y2, width):
    if abs(x1 - x2) < 1e-6 and abs(y1 - y2) < 1e-6:
        return
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(P(x1, y1))
    t.SetEnd(P(x2, y2))
    t.SetWidth(mm(width))
    t.SetLayer(LAYERS[layer])
    t.SetNet(nets[net])
    board.Add(t)
    obstacles.append(((layer,), "seg", (x1, y1, x2, y2, width / 2), net))


def add_via(net, x, y):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(P(x, y))
    v.SetWidth(pcbnew.F_Cu, mm(D.VIA_DIA))
    v.SetDrill(mm(D.VIA_DRILL))
    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    v.SetNet(nets[net])
    board.Add(v)
    obstacles.append(((0, 1), "seg", (x, y, x, y, VIA_R), net))
    via_keepout.append((x - VIA_R, y - VIA_R, x + VIA_R, y + VIA_R))


def emit_path(net, path, width):
    """Turn a cell path into merged track segments and vias."""
    pts = [(l, i * GS, j * GS) for (l, i, j) in path]
    start = 0
    for n in range(1, len(pts) + 1):
        if n == len(pts) or pts[n][0] != pts[start][0]:
            run = pts[start:n]
            a = 0
            for b in range(1, len(run)):
                last = b == len(run) - 1
                if not last:
                    d1 = (run[b][1] - run[b - 1][1], run[b][2] - run[b - 1][2])
                    d2 = (run[b + 1][1] - run[b][1], run[b + 1][2] - run[b][2])
                    if abs(d1[0] - d2[0]) < 1e-9 and abs(d1[1] - d2[1]) < 1e-9:
                        continue
                add_track(net, run[0][0], run[a][1], run[a][2], run[b][1], run[b][2], width)
                a = b
            if n < len(pts):
                add_via(net, pts[n][1], pts[n][2])
            start = n


failed = []


def route_net(net):
    width = D.POWER_NETS.get(net, D.SIGNAL_WIDTH)
    npads = [pd for pd in pads if pd["net"] == net]
    if len(npads) < 2:
        return
    blk = blocked_map(net, width / 2)
    vok = via_map(net)
    cell_pad = {}
    for pd in npads:
        cs = pad_cells(pd, blk)
        if not cs:
            failed.append("%s: pad %s.%s has no free cell" % (net, pd["ref"], pd["num"]))
            return
        pd["cells"] = cs
        for c in cs:
            cell_pad[c] = pd
    # start at the pad closest to the centroid, keeps the tree compact
    cx = sum(pd["center"][0] for pd in npads) / len(npads)
    cy = sum(pd["center"][1] for pd in npads) / len(npads)
    npads.sort(key=lambda pd: math.hypot(pd["center"][0] - cx, pd["center"][1] - cy))
    tree = set(npads[0]["cells"])
    todo = npads[1:]
    while todo:
        targets = set()
        for pd in todo:
            targets.update(pd["cells"])
        path = search(list(tree), lambda l, i, j: (l, i, j) in targets, blk, vok)
        if path is None:
            failed.append("%s: no route to %s" % (net, ", ".join(pd["ref"] + "." + pd["num"] for pd in todo)))
            return
        emit_path(net, path, width)
        for end in (path[0], path[-1]):         # tie the track ends to the pad centres
            pd = cell_pad.get(end)
            if pd:
                add_track(net, end[0], end[1] * GS, end[2] * GS, pd["center"][0], pd["center"][1], width)
        hit = cell_pad[path[-1]]
        todo.remove(hit)
        tree.update(path)
        tree.update(hit["cells"])


for net in D.ROUTE_ORDER:
    route_net(net)
unrouted = [n for n in D.all_nets() if n not in D.ROUTE_ORDER and n != "GND"]
if unrouted:
    failed.append("nets missing from ROUTE_ORDER: " + ", ".join(unrouted))

# GND: every SMD pad gets a short stub to a via into the bottom pour
blk = blocked_map("GND", GND_STUB_W / 2)
for pd in [pd for pd in pads if pd["net"] == "GND" and pd["smd"]]:
    vok = via_map("GND")
    cs = pad_cells(pd, blk)
    path = search(cs, lambda l, i, j: l == 0 and vok[i][j], blk, vok, allow_via=False) if cs else None
    if path is None or len(path) > 20:
        failed.append("GND: no via position near %s.%s" % (pd["ref"], pd["num"]))
        continue
    emit_path("GND", path, GND_STUB_W)
    add_track("GND", 0, path[0][1] * GS, path[0][2] * GS, pd["center"][0], pd["center"][1], GND_STUB_W)
    add_via("GND", path[-1][1] * GS, path[-1][2] * GS)

# --------------------------------------------------------------------------- GND pours
for layer in LAYERS:
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    z.SetNetCode(nets["GND"].GetNetCode())
    ol = z.Outline()
    ol.NewOutline()
    for (x, y) in ((0, 0), (W, 0), (W, H), (0, H)):
        ol.Append(mm(OX + x), mm(OY + y))
    z.SetLocalClearance(mm(0.25))
    z.SetMinThickness(mm(0.25))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    z.SetThermalReliefGap(mm(0.25))
    z.SetThermalReliefSpokeWidth(mm(0.4))
    z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    z.SetAssignedPriority(0)
    board.Add(z)
for (hx, hy) in HOLES:
    k = pcbnew.ZONE(board)
    k.SetIsRuleArea(True)
    k.SetDoNotAllowCopperPour(True)
    k.SetDoNotAllowTracks(False)
    k.SetDoNotAllowVias(False)
    k.SetDoNotAllowPads(False)
    k.SetDoNotAllowFootprints(False)
    k.SetLayerSet(pcbnew.LSET.AllCuMask())
    ol = k.Outline()
    ol.NewOutline()
    for a in range(0, 360, 10):
        ol.Append(mm(OX + hx + D.MOUNT_KEEPOUT_R * math.cos(math.radians(a))),
                  mm(OY + hy + D.MOUNT_KEEPOUT_R * math.sin(math.radians(a))))
    board.Add(k)
pcbnew.ZONE_FILLER(board).Fill(board.Zones())

# --------------------------------------------------------------------------- silkscreen
for item in D.SILK:
    txt, x, y, size, rot = item[:5]
    back = len(item) > 5 and item[5] == "B"
    t = pcbnew.PCB_TEXT(board)
    t.SetText(txt)
    t.SetPosition(P(x, y))
    t.SetLayer(pcbnew.B_SilkS if back else pcbnew.F_SilkS)
    t.SetMirrored(back)
    t.SetTextSize(pcbnew.VECTOR2I(mm(size), mm(size)))
    t.SetTextThickness(mm(max(0.1, size * 0.15)))
    t.SetTextAngleDegrees(rot)
    board.Add(t)

pcbnew.SaveBoard(OUT, board)
print("wrote", OUT)
print("tracks+vias:", len(board.GetTracks()))
if failed:
    print("ROUTING PROBLEMS:")
    for f in failed:
        print("  -", f)
    sys.exit(1)
