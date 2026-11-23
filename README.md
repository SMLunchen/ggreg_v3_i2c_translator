# GGreg20_V3 → I2C-Übersetzer (RadSens-kompatibel)

Kleine Platine mit einem ATtiny1614, die die Impulse eines GGreg20_V3-Geigerzählers zählt und
sich am I2C-Bus wie ein ClimateGuard **RadSens** verhält (Adresse `0x66`, Device-ID `0x7D`).
Meshtastic erkennt die Platine dadurch ohne Firmware-Änderung als RadSens-Sensor.

**Stand: Firmware kompiliert, Schaltplan/PCB bestehen ERC und DRC – auf echter Hardware ist noch
nichts getestet.** Die offenen Punkte stehen ganz unten.

## Erst lesen: Stromverbrauch

Der ATtiny braucht im Schlaf ca. 1 µA (Datenblattwert). Der eigentliche Verbraucher ist das
GGreg20_V3 selbst: laut Hersteller **35 mA bei 5 V, 52 mA bei 3,7 V, 57 mA bei 3,3 V**, dauerhaft.

Deshalb schaltet die Platine die Versorgung des GGreg20 und betreibt es standardmäßig getaktet:

| Modus | GGreg20 an | mittlerer Strom bei 3,3 V |
|---|---|---|
| Low-Power (Default): alle 600 s für 15 s Aufwärmen + 60 s Messen | 12,5 % | ca. 7 mA |
| Dauerbetrieb (`LP_MODE = 0`) | 100 % | ca. 57 mA |

Im Low-Power-Modus wird nur während der Messphasen gezählt. Das 220-s-Fenster des Registers
`0x06` (das Meshtastic liest) erstreckt sich dann über die letzten knapp vier Messphasen, also
rund 37 Minuten. Für Hintergrundüberwachung reicht das, kurze Ereignisse zwischen den Messphasen
werden nicht erfasst. Zyklus und Messdauer sind einstellbar (siehe Register `0x20`–`0x24`).

## Anschluss

| Stecker | Pins (Pin 1 = quadratisches Pad) | Zweck |
|---|---|---|
| J1 `I2C` | VCC, GND, SCL, SDA | zum Meshtastic-Node, Pinbelegung wie RadSens, 3,3 V |
| J3 `PWR` | −, + | geschaltete Versorgung zum GGreg20 (Anschluss „BAT") |
| J4 `G OUT` | GND, OUT | Impulsausgang des GGreg20 |
| J5 `VIN` | −, + | optionale eigene Versorgung für das GGreg20, 3,0–5,5 V |
| J6 `INT` | OUT | Impuls des GGreg20 unverändert durchgeschleift |
| J2 `UPDI` | UPDI, GND, VCC | Programmierung |

Alle Stecker sind JST-XH-Footprints (2,5 mm); Stiftleisten oder direkt eingelötete Drähte passen
ebenfalls. Die Beschriftung auf der Rückseite steht direkt am jeweiligen Pin.

**Lötjumper JP1** wählt, woher das GGreg20 versorgt wird:

- `VCC` (Auslieferungszustand, gebrückt): aus den 3,3 V des I2C-Steckers. Der Node muss dann
  ca. 60 mA liefern können. Das GGreg20 braucht wegen seiner Schutzdiode mindestens 3,0 V.
- `VIN`: aus J5, z. B. direkt vom Akku oder aus 5 V. Dazu die Brücke VCC–Mitte auftrennen und
  Mitte–VIN brücken. Effizienter, weil das GGreg20 bei höherer Spannung weniger Strom zieht.

Die 3,3 V am I2C-Stecker müssen dauerhaft anliegen. Schaltet der Node die Sensorversorgung ab,
verliert der ATtiny seine Messhistorie und beginnt neu.

## Registerübersicht

RadSens-Register (Datenblatt `RadSens_datasheet_ENG.pdf` und offizielle Arduino-Library):

| Adresse | Inhalt | Zugriff |
|---|---|---|
| `0x00` | Device-ID `0x7D` | R |
| `0x01` | Firmware-Version | R |
| `0x03`–`0x05` | Dosisleistung, dynamisches Fenster (≤ 123 s), 0,1 µR/h, MSB zuerst | R |
| `0x06`–`0x08` | Dosisleistung, festes Fenster 220 s, 0,1 µR/h, MSB zuerst | R |
| `0x09`–`0x0A` | Impulszähler, wird beim Lesen gelöscht, MSB zuerst | R |
| `0x0C` | Low-Power-Modus: 1 = getaktet, 0 = Dauerbetrieb | R/W, EEPROM |
| `0x10` | I2C-Adresse (`0x03`–`0x77`) | R/W, EEPROM |
| `0x11` | „HV-Generator": 1 = GGreg20 darf laufen, 0 = aus | R/W |
| `0x12`–`0x13` | Empfindlichkeit in Impulsen/µR, LSB zuerst | R/W, EEPROM |
| `0x14` | LED auf der Platine: 1 = an, 0 = aus | R/W, EEPROM |

Eigene Erweiterungen:

| Adresse | Inhalt | Zugriff |
|---|---|---|
| `0x20`–`0x21` | Zyklusdauer in s, LSB zuerst (Default 600) | R/W, EEPROM |
| `0x22`–`0x23` | Messdauer pro Zyklus in s, LSB zuerst (Default 60) | R/W, EEPROM |
| `0x24` | Aufwärmzeit in s (Default 15) | R/W, EEPROM |
| `0x25` | Status: Bit 0 GGreg20 versorgt, Bit 1 zählt, Bit 2 Fenster voll, Bit 3 Taktung aktiv | R |
| `0x26` | Sekunden im 220-s-Fenster | R |
| `0x28`–`0x29` | Restsekunden der aktuellen Phase, LSB zuerst | R |

Berechnung wie im RadSens-Datenblatt: `µR/h = Impulse × 3600 / (Empfindlichkeit × Sekunden)`.
Empfindlichkeit **105** für das SBM-20 (Default), **74** für das J305. 100 µR/h ≈ 1 µSv/h.

Abweichungen vom Original:

- Der Algorithmus des dynamischen Fensters ist im Datenblatt nicht beschrieben. Hier geht das
  Fenster so weit zurück, bis 50 Impulse enthalten sind, höchstens 123 s.
- J6 gibt den GGreg20-Impuls direkt weiter, nicht auf 11,2 ms gedehnt.
- Ist die Zyklusdauer nicht größer als Messdauer + Aufwärmzeit, läuft das GGreg20 dauerhaft.

Alle Defaults stehen in [firmware/src/config.h](firmware/src/config.h).

## Meshtastic

Nichts zu flashen: Meshtastic erkennt beim Booten an `0x66` die ID `0x7D` und liest danach
Register `0x06`. Unter *Telemetry → Environment* die Messung aktivieren; der Wert erscheint als
„Radiation" in µR/h. Nach dem Einschalten liefert die Platine etwa 16 s lang 0, bis die erste
Messsekunde vorliegt.

## Firmware

ATtiny1614, bare-metal C, PlatformIO. 2,9 kB Flash, 485 Byte RAM.

```
cd firmware
pio run                                  # bauen
pio run -t upload --upload-port COM5     # flashen
```

Programmiert wird über UPDI mit einem gewöhnlichen USB-Seriell-Adapter (SerialUPDI): Adapter-TX
über 1–4,7 kΩ an UPDI, Adapter-RX direkt an UPDI, dazu GND und 3,3 V. Die Werks-Fuses passen.
Beim Flashen wird das EEPROM gelöscht, die Einstellungen stehen danach wieder auf den Defaults.

Der ATtiny schläft im Power-Down und wacht nur für einen Impuls, den Sekundentakt oder eine
I2C-Adressierung auf. Die Dosisleistung wird erst berechnet, wenn der Host tatsächlich liest.
Ein Watchdog (8 s) und ein Timeout für hängende I2C-Transaktionen verhindern, dass die Platine
den Bus des Nodes blockiert.

## Hardware

KiCad-9-Projekt in [hardware/](hardware/), 40 × 30 mm, zweilagig, Bauteile nur oben.

- [hardware/doc/schematic.pdf](hardware/doc/schematic.pdf), Renderings in [hardware/doc/](hardware/doc/)
- Fertigungsdaten in [hardware/fab/](hardware/fab/): `gerber_ggreg_i2c_translator.zip`, `bom.csv`, `positions.csv`

Schaltplan und PCB werden aus [hardware/gen/design.py](hardware/gen/design.py) erzeugt
(Bauteile, Netze, Platzierung; die Leiterbahnen legt ein kleiner Router im Skript). Nach
Änderungen dort alles neu erzeugen und prüfen:

```
powershell -ExecutionPolicy Bypass -File hardware\gen\build.ps1
```

Wer lieber in KiCad von Hand weiterarbeitet, kann das tun; ein erneuter Skriptlauf überschreibt
die Dateien dann aber.

Nicht bestückt (DNP), nur bei Bedarf:

- **R1, R2** (4,7 kΩ): I2C-Pull-ups, falls der Node keine hat.
- **R4** (100 kΩ): Pull-up am Impulseingang, falls der GGreg20-Ausgang keinen eigenen hat.
- **Y1, C4, C5**: 32,768-kHz-Quarz für eine genaue Zeitbasis, dazu `USE_XTAL32K 1` setzen.
  Ohne Quarz läuft der interne Oszillator, dessen Fehler direkt in die Dosisleistung eingeht
  (typisch wenige Prozent, bei extremen Temperaturen mehr).

## Offene Punkte vor der Bestellung

1. **Impulsausgang des GGreg20.** Der Hersteller nennt 3,0–3,3 V High und „etwa 0,7 V" Low,
   aber weder Impulsbreite noch Ausgangsstufe. 0,7 V liegt knapp über dem garantierten
   Low-Pegel des ATtiny (0,66 V bei 3,3 V), aber deutlich unter der typischen Schaltschwelle.
   Am besten einmal mit dem Oszilloskop nachmessen. Reicht der Pegel nicht, ist R3 die Stelle
   für eine Anpassung.
2. **Polarität der GGreg20-Stecker.** Welcher Pin der beiden XH-Stecker Pin 1 ist, geht aus dem
   Datenblatt nicht hervor. Vor dem Anstecken mit dem Multimeter gegen die Beschriftung prüfen.
3. **Montagelöcher.** Zwei M3-Löcher im Abstand von 24 mm, aus der Maßzeichnung des GGreg20
   abgelesen, nicht nachgemessen.
4. **Aufwärmzeit.** 15 s sind aus der Herstellerangabe „10–15 Sekunden bis zum ersten Signal"
   abgeleitet und eher vorsichtig gewählt.
5. **Stromwerte.** ATtiny- und GGreg20-Ströme sind Datenblattwerte, nicht gemessen.
