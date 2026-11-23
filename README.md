# GGreg20_V3 → I2C translator (RadSens compatible)

A small board with an ATtiny1614 that counts the pulses of a GGreg20_V3 Geiger counter module and
behaves like a ClimateGuard **RadSens** on the I2C bus (address `0x66`, device ID `0x7D`).
Meshtastic therefore detects the board as a RadSens sensor without any firmware change.

**Status: the firmware compiles and the schematic/PCB pass ERC and DRC, but nothing has been
tested on real hardware yet.** The open points are listed at the bottom.

## Read first: power consumption

The ATtiny draws about 1 µA in sleep (datasheet value). The real consumer is the GGreg20_V3
itself: according to the vendor **35 mA at 5 V, 52 mA at 3.7 V, 57 mA at 3.3 V**, continuously.

The board therefore switches the GGreg20 supply and duty-cycles it by default:

| Mode | GGreg20 on | Average current at 3.3 V |
|---|---|---|
| Low power (default): every 600 s, 15 s warm-up + 60 s measuring | 12.5 % | approx. 7 mA |
| Continuous (`LP_MODE = 0`) | 100 % | approx. 57 mA |

In low-power mode, pulses are only counted during the measuring phases. The 220 s window of
register `0x06` (the one Meshtastic reads) then spans the last almost four measuring phases,
i.e. roughly 37 minutes. That is sufficient for background monitoring, but short events between
measuring phases are missed. Cycle period and measuring time are configurable (see registers
`0x20`–`0x24`).

## Connections

| Connector | Pins (pin 1 = square pad) | Purpose |
|---|---|---|
| J1 `I2C` | VCC, GND, SCL, SDA | to the Meshtastic node, same pinout as RadSens, 3.3 V |
| J3 `PWR` | −, + | switched supply to the GGreg20 ("BAT" connector) |
| J4 `G OUT` | GND, OUT | pulse output of the GGreg20 |
| J5 `VIN` | −, + | optional separate supply for the GGreg20, 3.0–5.5 V |
| J6 `INT` | OUT | GGreg20 pulse passed through unchanged |
| J2 `UPDI` | UPDI, GND, VCC | programming |

All connectors use JST XH footprints (2.5 mm); pin headers or directly soldered wires fit as
well. The labels on the back are placed right next to each pin.

**Solder jumper JP1** selects where the GGreg20 is powered from:

- `VCC` (as delivered, bridged): from the 3.3 V of the I2C connector. The node must then be able
  to supply about 60 mA. Because of its protection diode the GGreg20 needs at least 3.0 V.
- `VIN`: from J5, e.g. directly from the battery or from 5 V. Cut the bridge VCC–centre and
  bridge centre–VIN instead. More efficient, because the GGreg20 draws less current at a higher
  voltage.

The 3.3 V on the I2C connector must be present permanently. If the node switches off the sensor
supply, the ATtiny loses its measurement history and starts over.

## Register overview

RadSens registers (datasheet `RadSens_datasheet_ENG.pdf` and the official Arduino library):

| Address | Content | Access |
|---|---|---|
| `0x00` | Device ID `0x7D` | R |
| `0x01` | Firmware version | R |
| `0x03`–`0x05` | Dose rate, dynamic window (≤ 123 s), 0.1 µR/h, MSB first | R |
| `0x06`–`0x08` | Dose rate, fixed 220 s window, 0.1 µR/h, MSB first | R |
| `0x09`–`0x0A` | Pulse counter, cleared on read, MSB first | R |
| `0x0C` | Low-power mode: 1 = duty-cycled, 0 = continuous | R/W, EEPROM |
| `0x10` | I2C address (`0x03`–`0x77`) | R/W, EEPROM |
| `0x11` | "HV generator": 1 = GGreg20 may run, 0 = off | R/W |
| `0x12`–`0x13` | Sensitivity in pulses/µR, LSB first | R/W, EEPROM |
| `0x14` | On-board LED: 1 = on, 0 = off | R/W, EEPROM |

Extensions specific to this board:

| Address | Content | Access |
|---|---|---|
| `0x20`–`0x21` | Cycle period in s, LSB first (default 600) | R/W, EEPROM |
| `0x22`–`0x23` | Measuring time per cycle in s, LSB first (default 60) | R/W, EEPROM |
| `0x24` | Warm-up time in s (default 15) | R/W, EEPROM |
| `0x25` | Status: bit 0 GGreg20 powered, bit 1 counting, bit 2 window full, bit 3 duty cycling active | R |
| `0x26` | Seconds in the 220 s window | R |
| `0x28`–`0x29` | Seconds remaining in the current phase, LSB first | R |

Calculation as in the RadSens datasheet: `µR/h = pulses × 3600 / (sensitivity × seconds)`.
Sensitivity **105** for the SBM-20 (default), **74** for the J305. 100 µR/h ≈ 1 µSv/h.

Deviations from the original:

- The algorithm of the dynamic window is not described in the datasheet. Here the window
  reaches back until it contains 50 pulses, at most 123 s.
- J6 passes the GGreg20 pulse on directly, not stretched to 11.2 ms.
- If the cycle period is not greater than measuring time + warm-up time, the GGreg20 runs
  continuously.

All defaults are in [firmware/src/config.h](firmware/src/config.h).

## Meshtastic

Nothing to flash: at boot Meshtastic finds the ID `0x7D` at address `0x66` and then reads
register `0x06`. Enable the measurement under *Telemetry → Environment*; the value appears as
"Radiation" in µR/h. After power-up the board reports 0 for about 16 s until the first measured
second is available.

## Firmware

ATtiny1614, bare-metal C, PlatformIO. 2.9 kB flash, 485 bytes RAM.

```
cd firmware
pio run                                  # build
pio run -t upload --upload-port COM5     # flash
```

Programming is done via UPDI with an ordinary USB-serial adapter (SerialUPDI): adapter TX
through 1–4.7 kΩ to UPDI, adapter RX directly to UPDI, plus GND and 3.3 V. The factory fuses are
fine. Flashing erases the EEPROM, so the settings are back at their defaults afterwards.

The ATtiny sleeps in power-down and only wakes up for a pulse, the one-second tick or an I2C
address match. The dose rate is computed only when the host actually reads it. A watchdog (8 s)
and a timeout for stuck I2C transactions prevent the board from blocking the node's bus.

## Hardware

KiCad 9 project in [hardware/](hardware/), 40 × 30 mm, two layers, components on the top side
only.

- [hardware/doc/schematic.pdf](hardware/doc/schematic.pdf), renderings in [hardware/doc/](hardware/doc/)
- Fabrication data in [hardware/fab/](hardware/fab/): `gerber_ggreg_i2c_translator.zip`, `bom.csv`, `positions.csv`

Schematic and PCB are generated from [hardware/gen/design.py](hardware/gen/design.py)
(components, nets, placement; the traces are laid by a small router in the script). After
changing it, regenerate and check everything with:

```
powershell -ExecutionPolicy Bypass -File hardware\gen\build.ps1
```

You can also continue by hand in KiCad, but running the script again will overwrite the files.

Not populated (DNP), only if needed:

- **R1, R2** (4.7 kΩ): I2C pull-ups, in case the node has none.
- **R4** (100 kΩ): pull-up on the pulse input, in case the GGreg20 output has none of its own.
- **Y1, C4, C5**: 32.768 kHz crystal for an accurate time base; also set `USE_XTAL32K 1`.
  Without the crystal the internal oscillator is used, and its error goes directly into the
  dose rate (typically a few percent, more at extreme temperatures).

## Open points before ordering

1. **Pulse output of the GGreg20.** The vendor states 3.0–3.3 V high and "about 0.7 V" low, but
   neither the pulse width nor the output stage. 0.7 V is slightly above the guaranteed low
   level of the ATtiny (0.66 V at 3.3 V), but well below the typical switching threshold. Best
   checked once with an oscilloscope. If the level is not sufficient, R3 is the place to adapt
   it.
2. **Polarity of the GGreg20 connectors.** The datasheet does not say which pin of the two XH
   connectors is pin 1. Check against the labels with a multimeter before plugging in.
3. **Mounting holes.** Two M3 holes 24 mm apart, read from the GGreg20 dimensional drawing, not
   measured.
4. **Warm-up time.** 15 s is derived from the vendor's "10–15 seconds until the first signal"
   and chosen rather conservatively.
5. **Current figures.** ATtiny and GGreg20 currents are datasheet values, not measured.
