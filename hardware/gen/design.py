"""Single source of truth for schematic and PCB: parts, nets, placement."""

PROJECT = "ggreg_i2c_translator"
TITLE = "GGreg20_V3 I2C translator (RadSens compatible)"
REV = "1.0"
DATE = "2026-11-23"

BOARD_W, BOARD_H = 40.0, 30.0       # mm
BOARD_ORIGIN = (100.0, 100.0)       # position of the board's top-left corner on the PCB sheet

R0603 = "Resistor_SMD:R_0603_1608Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
SOT23 = "Package_TO_SOT_SMD:SOT-23"
XH2 = "Connector_JST:JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical"
XH4 = "Connector_JST:JST_XH_B4B-XH-A_1x04_P2.50mm_Vertical"

# sch = (x, y) in units of 2.54 mm on the schematic sheet
# pcb = (x, y, rotation) in mm relative to the board's top-left corner
PARTS = [
    # --- MCU ----------------------------------------------------------------
    dict(ref="U1", sym="MCU_Microchip_ATtiny:ATtiny1614-SS", value="ATtiny1614-SS",
         fp="Package_SO:SOIC-14_3.9x8.7mm_P1.27mm", sch=(52, 34), pcb=(28.0, 15.6, 0),
         nets={"1": "VCC", "14": "GND", "2": "LED_DRV", "3": "GEIGER_EN", "4": "PULSE_MCU",
               "6": "XTAL1", "7": "XTAL2", "8": "SDA", "9": "SCL", "10": "UPDI"},
         nc={"5": "PA7", "11": "PA1", "12": "PA2", "13": "PA3"}),
    dict(ref="C1", sym="Device:C", value="100n", fp=C0603, sch=(26, 14), pcb=(28.0, 10.1, 0),
         nets={"1": "VCC", "2": "GND"}),
    dict(ref="C2", sym="Device:C", value="1u", fp=C0603, sch=(31, 14), pcb=(24.2, 10.1, 0),
         nets={"1": "GND", "2": "VCC"}),

    # --- I2C host connector (RadSens pinout) -----------------------------------
    dict(ref="J1", sym="Connector_Generic:Conn_01x04", value="I2C host (VCC GND SCL SDA)", fp=XH4,
         sch=(12, 13), pcb=(22.0, 25.1, 0),
         nets={"1": "VCC", "2": "GND", "3": "SCL", "4": "SDA"}),
    dict(ref="R1", sym="Device:R", value="4k7", fp=R0603, sch=(17, 22), pcb=(26.8, 21.4, 0), dnp=True,
         nets={"1": "VCC", "2": "SCL"}),
    dict(ref="R2", sym="Device:R", value="4k7", fp=R0603, sch=(22, 22), pcb=(33.5, 21.4, 0), dnp=True,
         nets={"1": "SDA", "2": "VCC"}),

    # --- UPDI programming header ---------------------------------------------
    dict(ref="J2", sym="Connector_Generic:Conn_01x03", value="UPDI (UPDI GND VCC)",
         fp="Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical",
         sch=(12, 33), pcb=(37.0, 9.5, 0),
         nets={"1": "UPDI", "2": "GND", "3": "VCC"}),

    # --- optional 32.768 kHz crystal -----------------------------------------
    dict(ref="Y1", sym="Device:Crystal", value="32.768kHz 7pF", fp="Crystal:Crystal_SMD_3215-2Pin_3.2x1.5mm",
         sch=(22, 44), pcb=(22.5, 19.5, 90), dnp=True,
         nets={"1": "XTAL1", "2": "XTAL2"}),
    dict(ref="C4", sym="Device:C", value="10p", fp=C0603, sch=(15, 50), pcb=(19.4, 18.25, 0), dnp=True,
         nets={"1": "GND", "2": "XTAL1"}),
    dict(ref="C5", sym="Device:C", value="10p", fp=C0603, sch=(29, 50), pcb=(19.4, 20.75, 0), dnp=True,
         nets={"1": "GND", "2": "XTAL2"}),

    # --- pulse input from GGreg20 OUT ----------------------------------------
    dict(ref="J4", sym="Connector_Generic:Conn_01x02", value="GGreg OUT (GND OUT)", fp=XH2,
         sch=(76, 14), pcb=(20.0, 4.0, 0),
         nets={"1": "GND", "2": "GG_OUT"}),
    dict(ref="R3", sym="Device:R", value="10k", fp=R0603, sch=(86, 14), pcb=(21.5, 15.7, 0),
         nets={"1": "GG_OUT", "2": "PULSE_MCU"}),
    dict(ref="R4", sym="Device:R", value="100k", fp=R0603, sch=(92, 14), pcb=(20.6, 10.1, 0), dnp=True,
         nets={"1": "GG_OUT", "2": "VCC"}),
    dict(ref="J6", sym="Connector_Generic:Conn_01x01", value="INT (pulse out)",
         fp="Connector_PinHeader_2.54mm:PinHeader_1x01_P2.54mm_Vertical",
         sch=(100, 14), pcb=(27.5, 4.0, 0),
         nets={"1": "GG_OUT"}),

    # --- indicator LED --------------------------------------------------------
    dict(ref="R5", sym="Device:R", value="1k", fp=R0603, sch=(80, 30), pcb=(21.5, 12.9, 0),
         nets={"1": "LED_A", "2": "LED_DRV"}),
    dict(ref="D1", sym="Device:LED", value="LED red", fp="LED_SMD:LED_0603_1608Metric",
         sch=(90, 30), pcb=(17.5, 12.9, 0),
         nets={"1": "GND", "2": "LED_A"}),

    # --- switched supply for the GGreg20 ---------------------------------------
    dict(ref="JP1", sym="Jumper:SolderJumper_3_Bridged12", value="VCC | VIN",
         fp="Jumper:SolderJumper-3_P1.3mm_Bridged12_RoundedPad1.0x1.5mm",
         sch=(80, 44), pcb=(11.3, 20.6, 0),
         nets={"1": "VCC", "2": "VSW_IN", "3": "VIN"}, bom=False),
    dict(ref="J5", sym="Connector_Generic:Conn_01x02", value="VIN 3.0-5.5V (GND +)", fp=XH2,
         sch=(100, 44), pcb=(10.0, 25.1, 0),
         nets={"1": "GND", "2": "VIN"}),
    dict(ref="Q1", sym="Transistor_FET:AO3401A", value="AO3401A", fp=SOT23, sch=(92, 56), pcb=(12.5, 16.4, 0),
         nets={"1": "GATE", "2": "VSW_IN", "3": "VGEIGER"}),
    dict(ref="R6", sym="Device:R", value="470k", fp=R0603, sch=(82, 56), pcb=(9.0, 16.4, 90),
         nets={"1": "VSW_IN", "2": "GATE"}),
    dict(ref="C3", sym="Device:C", value="100n", fp=C0603, sch=(106, 56), pcb=(12.9, 13.3, 0),
         nets={"1": "GATE", "2": "VGEIGER"}),
    dict(ref="R7", sym="Device:R", value="47k", fp=R0603, sch=(76, 56), pcb=(8.8, 13.3, 0),
         nets={"1": "Q2_D", "2": "GATE"}),
    dict(ref="Q2", sym="Transistor_FET:2N7002", value="2N7002", fp=SOT23, sch=(66, 58), pcb=(9.0, 10.3, 0),
         nets={"1": "GEIGER_EN", "2": "GND", "3": "Q2_D"}),
    dict(ref="R8", sym="Device:R", value="1M", fp=R0603, sch=(57, 58), pcb=(17.2, 10.1, 0),
         nets={"1": "GEIGER_EN", "2": "GND"}),
    dict(ref="J3", sym="Connector_Generic:Conn_01x02", value="GGreg BAT (- +)", fp=XH2,
         sch=(100, 61), pcb=(10.0, 4.0, 0),
         nets={"1": "GND", "2": "VGEIGER"}),

    # --- mechanics ------------------------------------------------------------
    dict(ref="H1", sym="Mechanical:MountingHole", value="M3", fp="MountingHole:MountingHole_3.2mm_M3",
         sch=(36, 62), pcb=(3.0, 3.0, 0), nets={}, bom=False),
    dict(ref="H2", sym="Mechanical:MountingHole", value="M3", fp="MountingHole:MountingHole_3.2mm_M3",
         sch=(40, 62), pcb=(3.0, 27.0, 0), nets={}, bom=False),
]

POWER_NETS = {"VCC": 0.5, "VIN": 0.5, "VSW_IN": 0.5, "VGEIGER": 0.5}   # track width in mm
SIGNAL_WIDTH = 0.25
CLEARANCE = 0.2
VIA_DIA, VIA_DRILL = 0.6, 0.3

# routing order: short local nets first, the long supply net last
ROUTE_ORDER = ["XTAL1", "XTAL2", "PULSE_MCU", "LED_DRV", "LED_A", "GATE", "Q2_D",
               "VGEIGER", "VSW_IN", "VIN", "SDA", "SCL", "UPDI", "GG_OUT", "GEIGER_EN", "VCC"]

# reference designators: ref -> (x, y, rotation); connectors get descriptive labels instead
HIDE_REF = ["J1", "J2", "J3", "J4", "J5", "J6", "H1", "H2"]
REF_POS = {
    "R8": (17.2, 8.75, 0), "R4": (20.6, 8.75, 0), "C2": (24.2, 8.75, 0), "C1": (28.0, 8.75, 0),
    "D1": (17.5, 11.55, 0), "R5": (21.5, 11.55, 0), "R3": (21.5, 14.35, 0),
    "C4": (17.1, 18.25, 0), "C5": (17.1, 20.75, 0), "Y1": (22.5, 22.05, 0),
    "R1": (29.3, 21.4, 0), "R2": (35.9, 21.4, 0), "U1": (33.3, 19.3, 0),
    "Q2": (11.8, 9.4, 0), "R7": (6.3, 13.3, 0), "C3": (12.9, 11.95, 0),
    "Q1": (15.4, 16.4, 0), "R6": (7.3, 16.4, 90), "JP1": (11.3, 19.0, 0),
}

MOUNT_KEEPOUT_R = 3.0       # copper-free radius around the M3 holes (screw head)

# silkscreen labels: (text, x, y, size, rotation[, layer])
SILK = [
    ("GGreg20 I2C", 34.2, 1.6, 1.0, 0),
    ("RadSens 0x66", 34.2, 3.3, 0.8, 0),
    ("v" + REV, 34.2, 4.8, 0.8, 0),
    # J3 GGreg supply output
    ("-", 10.0, 0.85, 0.9, 0), ("+", 12.5, 0.85, 0.9, 0), ("PWR", 16.25, 4.5, 0.8, 90),
    # J4 GGreg pulse input, J6 pulse pass-through
    ("G", 20.0, 0.85, 0.8, 0), ("OUT", 22.6, 0.85, 0.8, 0), ("INT", 27.5, 2.0, 0.8, 0),
    # J5 external supply for the GGreg
    ("-", 10.0, 29.35, 0.9, 0), ("+", 12.5, 29.35, 0.9, 0), ("VIN", 17.25, 27.2, 0.8, 0),
    # J1 I2C
    ("V", 22.0, 29.35, 0.8, 0), ("G", 24.5, 29.35, 0.8, 0), ("C", 27.0, 29.35, 0.8, 0), ("D", 29.5, 29.35, 0.8, 0),
    ("I2C", 34.6, 26.5, 0.9, 0),
    # J2 UPDI
    ("UPDI", 37.0, 7.3, 0.8, 0), ("U", 34.8, 9.5, 0.8, 0), ("G", 34.8, 12.04, 0.8, 0), ("V", 34.8, 14.58, 0.8, 0),
    # JP1
    ("VCC", 7.9, 20.6, 0.8, 0), ("VIN", 14.7, 20.6, 0.8, 0),
    # bottom side legend (one label per pin, so it is correct when the board is flipped)
    ("GGreg BAT", 11.25, 8.3, 0.8, 0, "B"), ("-", 10.0, 6.5, 0.9, 0, "B"), ("+", 12.5, 6.5, 0.9, 0, "B"),
    ("GGreg OUT", 21.25, 9.9, 0.8, 0, "B"), ("GND", 20.0, 7.3, 0.8, 90, "B"), ("OUT", 22.5, 7.3, 0.8, 90, "B"),
    ("INT", 27.5, 6.3, 0.8, 0, "B"),
    ("VIN 3-5.5V", 11.25, 20.6, 0.8, 0, "B"), ("-", 10.0, 22.6, 0.9, 0, "B"), ("+", 12.5, 22.6, 0.9, 0, "B"),
    ("I2C", 25.75, 18.6, 0.9, 0, "B"),
    ("VCC", 22.0, 21.6, 0.8, 90, "B"), ("GND", 24.5, 21.6, 0.8, 90, "B"),
    ("SCL", 27.0, 21.6, 0.8, 90, "B"), ("SDA", 29.5, 21.6, 0.8, 90, "B"),
    ("UPDI", 33.6, 9.5, 0.8, 0, "B"), ("GND", 33.9, 12.04, 0.8, 0, "B"), ("VCC", 33.9, 14.58, 0.8, 0, "B"),
]


def all_nets():
    names = []
    for p in PARTS:
        for n in p["nets"].values():
            if n not in names:
                names.append(n)
    return names


def uid(key):
    """Deterministic UUID so that schematic and PCB reference the same objects."""
    import uuid
    return str(uuid.uuid5(uuid.UUID("6f1d7f0e-4f0b-4a52-9d0e-2b0c7f3a1c55"), key))
