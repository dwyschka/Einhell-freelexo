# Fehlercodes des Freelexo

Es gibt **zwei verschiedene Dinge**, die beide wie „Fehler" aussehen:

| Quelle | Kommando | Inhalt |
|---|---|---|
| **Aktuelle Warnung** | `0x00` (BasicInfo), Byte 8 | ein einzelner Code, gerade jetzt aktiv |
| **Fehlerspeicher** | `0x1E` → `0x8E` | **ein** zeitgestempelter Eintrag (Datum + Code) |

> Wichtig: der Fehlerspeicher liefert **acht Bytes = einen Eintrag**, nicht acht
> Codes. Die Firmware speichert intern mehrere 8-Byte-Records (u. a. bei
> `+0x3b` und `+0x43`), über die Schnittstelle ist aber nur einer abrufbar.

Aufbau des 8-Byte-Records (Firmware `0x0802eb48` formatiert ihn als
`YYYYMMDD-HH-MM-SS`):

| Byte | Bedeutung |
|---|---|
| 1 | Jahr, höherwertig |
| 2 | Jahr, niederwertig (zusammen: 16 Bit, z. B. `0x07EA` = 2026) |
| 3 | Monat |
| 4 | Tag |
| 5 | Stunde |
| 6 | Minute |
| 7 | Sekunde |
| 8 | **Warncode** |

---

## Warncodes

Die Codes sind absichtlich druckbare ASCII-Zeichen — der Mäher speichert den
Fehlerspeicher als kurzen String. Quelle: Enum `Basic.Enums.Warning` aus der
offiziellen App plus die Klartext-Texte der Firmware.

| Code | Hex | ASCII | Enum (App) | Anzeige (DE) | Bedeutung | Typische Ursache / Abhilfe |
|---:|---|---|---|---|---|---|
| 0 | `00` | – | `None` | – | kein Fehler | – |
| 66 | `42` | `B` | `BatteryError` | Batteriefehler | Akku/BMS meldet Störung | Akku laden; bleibt es: Akku oder BMS defekt → Service |
| 67 | `43` | `C` | `MotorOverCurrent` | Motor überlastet | Motor zieht zu viel Strom | Gras zu hoch/nass, Messer blockiert, Hindernis unter dem Mäher |
| 76 | `4C` | `L` | `MowerLifted` | Mäher angehoben | Hebesensor ausgelöst | Mäher absetzen, Gehäuse/Lift-Sensor prüfen |
| 77 | `4D` | `M` | `MotorFault` | Motorfehler | Motor oder Endstufe meldet Störung | Messer blockiert, Hallsensor, Kabel → Service |
| 78 | `4E` | `N` | `SignalError` | Signalfehler | Begrenzungsdraht-Signal fehlt/falsch | Drahtbruch, Kurzschluss, Ladestation ohne Strom, Draht zu lang |
| 80 | `50` | `P` | `PCBOverTemperature` | Warnung! / Stop the mower | Platine zu heiß | Abkühlen lassen, Lüftung/Sonneneinstrahlung, Gras unter dem Gehäuse |
| 82 | `52` | `R` | `RollingOver` | Mäher umgefallen | Lageänderung erkannt (umgekippt) | Aufrichten, Fläche auf Steine/Stufen prüfen |
| 83 | `53` | `S` | `BatteryOverTemperature` | Akku zu warm | Akku über Temperaturgrenze | Im Schatten laden, Akku abkühlen lassen |
| 84 | `54` | `T` | `MowerTilted` | Mäher gekippt | Neigung über Grenzwert | Hang zu steil, Kante/Steigung prüfen |
| 88 | `58` | `X` | `MowerTrapped` | Mäher festgefahren | kommt nicht frei | Mäher befreien, Hindernis beseitigen |

### Nicht zugeordnet

Diese Werte kennt die App als Enum, aber ohne Bedeutung:

| Code | Hex | ASCII | Enum-Name |
|---:|---|---|---|
| 50 | `32` | `2` | `UnknownFifty` |
| 51 | `33` | `3` | `UnknownFiftyone` |
| 65 | `41` | `A` | `UnknownSixtyfive` |
| 255 | `FF` | – | `UnknownTwofivefive` |

**Vermutung** (nicht belegt): die Firmware hat eigene Bildschirme für
„Hall Error", „BatteryPCB Error", „Charge incomplete" und „Over temperature,
Stop the mower", die keinem der zehn bekannten Codes entsprechen. Einer davon
könnte 50, 51 oder 65 sein. Klären lässt sich das mit einem gezielten Test:
Fehler provozieren, `0x1E` abfragen und den Code notieren.

---

## Statuscodes (nicht verwechseln)

Der Statusbyte im `0x80`-Frame ist **kein** Fehlercode, sondern der
Betriebszustand (`Basic.Enums.MowerStatus`):

| Wert | Name | Bedeutung |
|---:|---|---|
| 0 | `UnknownZero` | unbekannt |
| 1 | `Mowing` | mäht |
| 3 | `AlongBoundary` | fährt am Rand |
| 4 | `EdgeCutting` | Randmähen |
| 5 | `SecondAreaMowing` | zweiter Bereich |
| 6 | `SpotMowing` | Spot-Mähen |
| 7 | `Idle` | Leerlauf |
| 19 | `Stopped` | angehalten |
| 20 | `Paused` | pausiert |
| 22 | `ErrorBoundarySignalHasIncorrectFrequencyMagic` | **Drahtsignal fehlerhaft** (der „Signalfehler"-Fall) |
| 25 | `UnknownNineteen` | unbekannt |
| 32 | `UnknownTwenty` | unbekannt |

Der Signalfehler taucht also an **zwei** Stellen auf: als Status 22 (akuter
Zustand) und als Warncode 78 (im Fehlerspeicher).

---

## Anzeige im Home Assistant

- `sensor.last_error` — Name des Codes aus dem Fehlerspeicher, mit
  `code`, `timestamp` und `raw` als Attribute
- `sensor.warning` — der aktuell aktive Code aus dem `0x80`-Frame
- `binary_sensor.error_active` — an, sobald ein Fehler gespeichert ist
- `sensor.error_memory` (Diagnose) — Rohdaten des Records

## Nachbauen

```yaml
action: einhell_mower.send_command
data:
  command: 0x1E      # Fehlerspeicher lesen
```

Antwort: `44 59 4D 8E <jahr_hi> <jahr_lo> <monat> <tag> <std> <min> <sek> <code> …`
