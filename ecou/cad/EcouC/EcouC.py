"""Ecou, variant C: the low, one-head-servo build with an arm (08-ecou.md §1.1).

A Fusion script. In Fusion: Utilities > Add-Ins > Scripts and Add-Ins > the + next to
"My Scripts" > pick this folder > Run. It opens a new design with one component per
printed part, in assembled position, and writes ecou_c.step and stl/<part>.stl next to
this file.

Every size is in mm. Measure your own parts, change the values below and run it again:
clones of the HC-SR04, the OLED and the 6x6 button differ by a millimetre or two.
"""

import math
import os
import traceback

import adsk.core
import adsk.fusion

HERE = os.path.dirname(os.path.realpath(__file__))

# Case. Every part stays under 175 mm, so it fits a 180 mm printer bed.
W, D, H = 170.0, 100.0, 50.0  # tray, outside
WALL, FLOOR, LID = 2.4, 2.4, 3.0
FIT = 0.3  # clearance per side for pockets

# Arduino UNO Q lying flat, USB-C against the left wall. UNO footprint holes from its
# lower left corner.
UNO_X0, UNO_Y0 = -80.0, -26.65
UNO_W, UNO_D = 68.6, 53.3
UNO_HOLES = [(13.97, 2.54), (15.24, 50.8), (66.04, 7.62), (66.04, 35.56)]
UNO_STANDOFF = 5.0
# Window in the lid over the board, for the LED matrix. Move it once you see the matrix.
MATRIX_W, MATRIX_D = 46.0, 30.0
MATRIX_DX, MATRIX_DY = 0.0, 0.0

# SG90
SG_L, SG_W = 22.8, 12.2
SG_EAR_PITCH = 27.8
SG_SHAFT_OFF = 5.5  # shaft from the body centre, along its length
HORN_LIFT = 10.5  # lid top to the head's underside: servo top plus horn

# Pan servo shaft, seen from above
SX, SY = 0.0, 5.0

# HC-SR04
HC_PITCH = 26.0  # centre to centre of the two cans: measure yours
HC_CAN = 16.6  # hole for the 16 mm can
HC_PCB_W, HC_PCB_H, HC_PCB_T = 45.0, 20.0, 1.6
HC_GAP = 4.0  # PCB to the inside of the face, clears the crystal

# Head
HW, HD, HH = 64.0, 28.0, 30.0
FACE = 3.0

# OLED 0.96", behind the front wall
OLED_X, OLED_Z = 45.0, 22.0
OLED_WIN_W, OLED_WIN_H, OLED_WIN_DZ = 24.0, 13.0, 1.0
OLED_HOLE_DX, OLED_HOLE_DZ = 23.0, 23.5  # mounting hole spacing: measure yours
OLED_STANDOFF = 2.5

MIC_X, MIC_Z, MIC_D = 15.0, 25.0, 10.0  # MAX9814 behind a hole in the front wall
DHT_X, DHT_Z, DHT_WIN_W, DHT_WIN_H = 40.0, 30.0, 12.4, 16.0  # DHT11 in the back wall

# Button: a 6x6 tactile switch on a plate, pressed by a printed knob
BX, BY = 50.0, -22.0
BTN_H = 5.0  # from the switch's base to the top of its plunger: measure yours
KNOB_R, KNOB_FLANGE_R = 15.0, 17.5
CUP_R_IN, CUP_R_OUT, CUP_DEPTH = 18.3, 21.0, 10.0
CUP_SCREW_DX = 24.5
PLATE_T, BTN_POCKET = 2.5, 1.5
BTN_LEGS = (6.5, 4.5)

# Arm servo, through the right wall, shaft towards the back
ARM_Y, ARM_Z = 18.0, 30.0
ARM_X, ARM_T = 96.0, 3.5  # the arm's inner face, outside the wall
ARM_LEN, FAN_R = 50.0, 28.0

HX, HY = W / 2, D / 2
MM = 0.1  # Fusion's API works in cm


def check():
    assert max(W, D, HW) <= 175, "a part is too big for a 180 mm bed"
    assert UNO_X0 >= -HX + WALL, "the UNO Q is in the left wall"
    assert UNO_X0 + UNO_W < SX - SG_W / 2 - 2, "the UNO Q hits the pan servo"
    stem = (H - 2) - (H - CUP_DEPTH - BTN_POCKET + BTN_H + 0.1)
    assert stem > 1, "the button is too tall for the cup: raise CUP_DEPTH"
    assert KNOB_FLANGE_R < CUP_R_IN and KNOB_R + FIT < KNOB_FLANGE_R
    assert ARM_Y + 17 < HY - WALL - 8.5, "the arm servo pad hits a lid screw boss"
    assert BY - CUP_R_OUT > -HY + WALL + FIT + 2, "the button cup hits the lid's lip"


def V(v):
    return adsk.core.ValueInput.createByReal(v * MM)


def P(x, y, z):
    return adsk.core.Point3D.create(x * MM, y * MM, z * MM)


def span(a, b):
    a, b = sorted((a, b))
    return (a + b) / 2, b - a


class Part:
    """One printed part: a component with one body, built from boxes and cylinders."""

    OPS = {
        "new": adsk.fusion.FeatureOperations.NewBodyFeatureOperation,
        "join": adsk.fusion.FeatureOperations.JoinFeatureOperation,
        "cut": adsk.fusion.FeatureOperations.CutFeatureOperation,
    }

    def __init__(self, root, name):
        occ = root.occurrences.addNewComponent(adsk.core.Matrix3D.create())
        self.c = occ.component
        self.c.name = name
        self.body = None
        self.base = {"x": self.c.yZConstructionPlane, "y": self.c.xZConstructionPlane, "z": self.c.xYConstructionPlane}

    def _sketch(self, axis, at):
        # Offset along the base plane's own normal, whichever way it points.
        base = self.base[axis]
        n = base.geometry.normal
        inp = self.c.constructionPlanes.createInput()
        inp.setByOffset(base, V(at[0] * n.x + at[1] * n.y + at[2] * n.z))
        plane = self.c.constructionPlanes.add(inp)
        plane.isLightBulbOn = False
        return self.c.sketches.add(plane)

    def _extrude(self, sk, length, op):
        ext = self.c.features.extrudeFeatures
        inp = ext.createInput(sk.profiles.item(0), self.OPS[op])
        inp.setSymmetricExtent(V(length), True)
        if op != "new":
            inp.participantBodies = [self.body]
        feat = ext.add(inp)
        if op == "new":
            self.body = feat.bodies.item(0)
            self.body.name = self.c.name
        sk.isVisible = False

    def box(self, x0, y0, z0, x1, y1, z1, op="join"):
        zc, dz = span(z0, z1)
        sk = self._sketch("z", (0, 0, zc))
        sk.sketchCurves.sketchLines.addTwoPointRectangle(
            sk.modelToSketchSpace(P(x0, y0, zc)), sk.modelToSketchSpace(P(x1, y1, zc))
        )
        self._extrude(sk, dz, op)

    def _circle(self, axis, c, r, length, op):
        sk = self._sketch(axis, c)
        sk.sketchCurves.sketchCircles.addByCenterRadius(sk.modelToSketchSpace(P(*c)), r * MM)
        self._extrude(sk, length, op)

    def cz(self, x, y, z0, z1, r, op="join"):
        zc, dz = span(z0, z1)
        self._circle("z", (x, y, zc), r, dz, op)

    def cy(self, x, z, y0, y1, r, op="join"):
        yc, dy = span(y0, y1)
        self._circle("y", (x, yc, z), r, dy, op)

    def cx(self, y, z, x0, x1, r, op="join"):
        xc, dx = span(x0, x1)
        self._circle("x", (xc, y, z), r, dx, op)

    def poly_x(self, xc, pts_yz, length, op="join"):
        """A closed polygon in a plane of constant x, extruded along x."""
        sk = self._sketch("x", (xc, 0, 0))
        lines = sk.sketchCurves.sketchLines
        pts = [sk.modelToSketchSpace(P(xc, y, z)) for y, z in pts_yz]
        first = prev = lines.addByTwoPoints(pts[0], pts[1])
        for p in pts[2:]:
            prev = lines.addByTwoPoints(prev.endSketchPoint, p)
        lines.addByTwoPoints(prev.endSketchPoint, first.startSketchPoint)
        self._extrude(sk, length, op)


def corners():
    x, y = HX - WALL - 4, HY - WALL - 4
    return [(sx * x, sy * y) for sx in (-1, 1) for sy in (-1, 1)]


def pan_body_y():
    return SY - SG_SHAFT_OFF


def tray(root):
    t = Part(root, "Tray")
    t.box(-HX, -HY, 0, HX, HY, H, "new")
    t.box(-HX + WALL, -HY + WALL, FLOOR, HX - WALL, HY - WALL, H + 1, "cut")
    for x, y in corners():  # lid screws
        t.cz(x, y, FLOOR - 0.5, H, 4.5)
        t.cz(x, y, H - 12, H + 0.1, 1.3, "cut")
    for hx, hy in UNO_HOLES:
        x, y = UNO_X0 + hx, UNO_Y0 + hy
        t.cz(x, y, FLOOR - 0.5, FLOOR + UNO_STANDOFF, 3.0)
        t.cz(x, y, FLOOR + 1, FLOOR + UNO_STANDOFF + 0.1, 1.3, "cut")
    # USB-C: a long slot, since the connector's place along the edge varies
    t.box(-HX - 1, -15, FLOOR + 3, -HX + WALL + 0.5, 15, FLOOR + 15, "cut")
    for i in range(6):  # vents over the board, which warms up
        x = -70 + i * 8
        t.box(x, HY - WALL - 0.5, 15, x + 3, HY + 1, 35, "cut")
    # DHT11 in the back wall, away from the board's heat
    t.box(DHT_X - DHT_WIN_W / 2, HY - WALL - 0.5, DHT_Z - DHT_WIN_H / 2,
          DHT_X + DHT_WIN_W / 2, HY + 1, DHT_Z + DHT_WIN_H / 2, "cut")
    # OLED behind the front wall, on four M2 standoffs
    zc = OLED_Z + OLED_WIN_DZ
    t.box(OLED_X - OLED_WIN_W / 2, -HY - 1, zc - OLED_WIN_H / 2,
          OLED_X + OLED_WIN_W / 2, -HY + WALL + 0.5, zc + OLED_WIN_H / 2, "cut")
    for sx in (-1, 1):
        for sz in (-1, 1):
            x, z = OLED_X + sx * OLED_HOLE_DX / 2, OLED_Z + sz * OLED_HOLE_DZ / 2
            t.cy(x, z, -HY + WALL - 0.5, -HY + WALL + OLED_STANDOFF, 2.5)
            t.cy(x, z, -HY + WALL + 0.5, -HY + WALL + OLED_STANDOFF + 0.1, 0.85, "cut")
    t.cy(MIC_X, MIC_Z, -HY - 1, -HY + WALL + 1, MIC_D / 2, "cut")
    # Arm servo through the right wall; the wall is thickened to 6 mm for its screws
    pad = HX - WALL - 3.6
    t.box(pad, ARM_Y - 17, ARM_Z - 9, HX - WALL + 0.5, ARM_Y + 17, ARM_Z + 9)
    t.box(pad - 0.5, ARM_Y - SG_L / 2 - FIT, ARM_Z - SG_W / 2 - FIT,
          HX + 1, ARM_Y + SG_L / 2 + FIT, ARM_Z + SG_W / 2 + FIT, "cut")
    for s in (-1, 1):
        t.cx(ARM_Y + s * SG_EAR_PITCH / 2, ARM_Z, pad - 0.5, HX + 1, 0.9, "cut")


def lid(root):
    li = Part(root, "Lid")
    li.box(-HX, -HY, H, HX, HY, H + LID, "new")
    o = WALL + FIT  # a lip that drops into the tray and keeps the lid in place
    li.box(-HX + o, -HY + o, H - 3, HX - o, HY - o, H + 0.5)
    li.box(-HX + o + 2, -HY + o + 2, H - 3.1, HX - o - 2, HY - o - 2, H, "cut")
    for x, y in corners():
        li.cz(x, y, H - 3.1, H, 5.2, "cut")
        li.cz(x, y, H - 3.2, H + LID + 0.1, 1.7, "cut")
    # Pan servo, hanging from its ears
    by = pan_body_y()
    for s in (-1, 1):
        li.cz(SX, by + s * SG_EAR_PITCH / 2, H - 4, H + 0.5, 3.0)
    li.box(SX - SG_W / 2 - FIT, by - SG_L / 2 - FIT, H - 4.1,
           SX + SG_W / 2 + FIT, by + SG_L / 2 + FIT, H + LID + 0.1, "cut")
    for s in (-1, 1):
        li.cz(SX, by + s * SG_EAR_PITCH / 2, H - 4.1, H + LID + 0.1, 0.9, "cut")
    li.cz(SX + 13, SY, H - 0.1, H + LID + 0.1, 5.0, "cut")  # the head's wires
    mx = UNO_X0 + UNO_W / 2 + MATRIX_DX
    my = UNO_Y0 + UNO_D / 2 + MATRIX_DY
    li.box(mx - MATRIX_W / 2, my - MATRIX_D / 2, H - 0.1,
           mx + MATRIX_W / 2, my + MATRIX_D / 2, H + LID + 0.1, "cut")
    # The button's cup: the knob's flange slides in it, the plate closes it from below
    li.cz(BX, BY, H - CUP_DEPTH, H + 0.5, CUP_R_OUT)
    for s in (-1, 1):
        li.cz(BX + s * CUP_SCREW_DX, BY, H - CUP_DEPTH, H + 0.5, 3.5)
    li.cz(BX, BY, H - CUP_DEPTH - 0.1, H, CUP_R_IN, "cut")
    for s in (-1, 1):
        li.cz(BX + s * CUP_SCREW_DX, BY, H - CUP_DEPTH - 0.1, H - 2, 1.3, "cut")
    li.cz(BX, BY, H - 0.1, H + LID + 0.1, KNOB_R + FIT, "cut")


def button_plate(root):
    p = Part(root, "ButtonPlate")
    z1 = H - CUP_DEPTH
    z0 = z1 - PLATE_T
    p.cz(BX, BY, z0, z1, CUP_R_OUT, "new")
    p.box(BX - CUP_SCREW_DX - 3.5, BY - 4.5, z0, BX + CUP_SCREW_DX + 3.5, BY + 4.5, z1)
    for s in (-1, 1):
        p.cz(BX + s * CUP_SCREW_DX, BY, z0 - 0.1, z1 + 0.1, 1.7, "cut")
    p.box(BX - 3.15, BY - 3.15, z1 - BTN_POCKET, BX + 3.15, BY + 3.15, z1 + 0.1, "cut")
    for sx in (-1, 1):
        for sy in (-1, 1):
            p.cz(BX + sx * BTN_LEGS[0] / 2, BY + sy * BTN_LEGS[1] / 2, z0 - 0.1, z1 + 0.1, 0.8, "cut")


def knob(root):
    k = Part(root, "Knob")
    stem_bottom = H - CUP_DEPTH - BTN_POCKET + BTN_H + 0.1  # 0.1 mm above the plunger
    k.cz(BX, BY, H - 2, H, KNOB_FLANGE_R, "new")
    k.cz(BX, BY, H - 0.5, H + LID + 2, KNOB_R)
    k.cz(BX, BY, stem_bottom, H - 1.5, 1.5)


def head_frame():
    z0 = H + LID + HORN_LIFT
    yf = SY - 14  # front of the head
    return z0, z0 + HH, yf, yf + HD, z0 + 3.5 + (HH - 3.5 - WALL) / 2


def head(root):
    z0, z1, yf, yb, zc = head_frame()
    h = Part(root, "Head")
    h.box(SX - HW / 2, yf, z0, SX + HW / 2, yb, z1, "new")
    h.box(SX - HW / 2 + WALL, yf + FACE, z0 + 3.5, SX + HW / 2 - WALL, yb + 1, z1 - WALL, "cut")
    for s in (-1, 1):  # the eyes
        h.cy(SX + s * HC_PITCH / 2, zc, yf - 1, yf + FACE + 1, HC_CAN / 2, "cut")
    pcb_front = yf + FACE + HC_GAP
    for s in (-1, 1):  # ribs the PCB's edges rest on
        x = SX + s * (HC_PCB_W / 2 - 1)
        h.box(x - 1, yf + FACE - 0.5, z0 + 3, x + 1, pcb_front, z1 - WALL + 0.5)
    pins = pcb_front + HC_PCB_T / 2
    h.box(SX - 7, pins - 2.3, z0 - 0.1, SX + 7, pins + 2.3, z0 + 3.6, "cut")  # header and wires
    h.cz(SX, SY, z0 - 0.1, z0 + 3.6, 3.8, "cut")  # horn hub and its screw
    h.box(SX - 17.5, SY - 3.3, z0 - 0.1, SX + 17.5, SY + 3.3, z0 + 2.0, "cut")  # double-arm horn
    for s in (-1, 1):  # bosses for the back cover
        h.cy(SX + s * 27, zc, yb - 10, yb, 3.0)
        h.cy(SX + s * 27, zc, yb - 8, yb + 0.1, 1.3, "cut")


def head_back(root):
    z0, z1, yf, yb, zc = head_frame()
    b = Part(root, "HeadBack")
    b.box(SX - HW / 2, yb, z0, SX + HW / 2, yb + WALL, z1, "new")
    for s in (-1, 1):
        b.cy(SX + s * 27, zc, yb - 0.1, yb + WALL + 0.1, 1.7, "cut")
    b.box(SX - 8, yb - 0.1, z0 - 0.1, SX + 8, yb + WALL + 0.1, z0 + 6, "cut")  # wires, if the pins point back
    pcb_back = yf + FACE + HC_GAP + HC_PCB_T
    for s in (-1, 1):  # press the PCB against its ribs
        b.cy(SX + s * 20, zc + 8, pcb_back, yb + 0.5, 2.0)


def arm(root):
    a = Part(root, "Arm")
    py, pz = ARM_Y + SG_SHAFT_OFF, ARM_Z
    x0, x1 = ARM_X, ARM_X + ARM_T
    a.cx(py, pz, x0, x1, 7.0, "new")
    a.box(x0, py - 5, pz, x1, py + 5, pz + ARM_LEN + 2)
    top = pz + ARM_LEN
    fan = [(py, top)] + [
        (py + FAN_R * math.cos(math.radians(t)), top + FAN_R * math.sin(math.radians(t)))
        for t in range(45, 136, 10)
    ]
    a.poly_x((x0 + x1) / 2, fan, ARM_T)
    a.cx(py, pz, x0 - 0.1, x1 + 0.1, 3.8, "cut")  # horn hub and its screw
    a.box(x0 - 0.1, py - 3.3, pz - 3, x0 + 1.6, py + 3.3, pz + 19, "cut")  # single-arm horn, pointing up


def test_plate(root):
    """Print this first: if the servo, an eye, the OLED and the knob fit here, they fit the case."""
    y0, y1 = -HY - 60, -HY - 20
    yc = (y0 + y1) / 2
    tp = Part(root, "TestPlate")
    tp.box(-60, y0, 0, 60, y1, 3, "new")
    tp.box(-42 - SG_L / 2 - FIT, yc - SG_W / 2 - FIT, -0.1, -42 + SG_L / 2 + FIT, yc + SG_W / 2 + FIT, 3.1, "cut")
    for s in (-1, 1):
        tp.cz(-42 + s * SG_EAR_PITCH / 2, yc, -0.1, 3.1, 0.9, "cut")
    tp.cz(-12, yc, -0.1, 3.1, HC_CAN / 2, "cut")
    tp.box(12 - OLED_WIN_W / 2, yc - OLED_WIN_H / 2, -0.1, 12 + OLED_WIN_W / 2, yc + OLED_WIN_H / 2, 3.1, "cut")
    for s in (-1, 1):
        tp.cz(12 + s * OLED_HOLE_DX / 2, yc + OLED_HOLE_DZ / 2, -0.1, 3.1, 0.85, "cut")
    tp.cz(42, yc, -0.1, 3.1, KNOB_R + FIT, "cut")


PARTS = (tray, lid, button_plate, knob, head, head_back, arm, test_plate)


def export(design):
    em = design.exportManager
    os.makedirs(os.path.join(HERE, "stl"), exist_ok=True)
    em.execute(em.createSTEPExportOptions(os.path.join(HERE, "ecou_c.step"), design.rootComponent))
    for occ in design.rootComponent.occurrences:
        opt = em.createSTLExportOptions(occ, os.path.join(HERE, "stl", occ.component.name + ".stl"))
        opt.meshRefinement = adsk.fusion.MeshRefinementSettings.MeshRefinementHigh
        em.execute(opt)


def run(context):
    ui = None
    try:
        check()
        app = adsk.core.Application.get()
        ui = app.userInterface
        app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
        design = adsk.fusion.Design.cast(app.activeProduct)
        design.designType = adsk.fusion.DesignTypes.ParametricDesignType
        design.fusionUnitsManager.distanceDisplayUnits = adsk.fusion.DistanceUnits.MillimeterDistanceUnits
        for build in PARTS:
            build(design.rootComponent)
        export(design)
        app.activeViewport.fit()
        ui.messageBox("Ecou C e gata.\nSTEP și STL-urile sunt în:\n" + HERE)
    except Exception:
        if ui:
            ui.messageBox("Nu a mers:\n" + traceback.format_exc())
        else:
            raise
