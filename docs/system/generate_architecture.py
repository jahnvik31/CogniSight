"""Generate editable system diagram using the architecture skill's helpers.

Run from any directory: python3 docs/system/generate_architecture.py
No network, external packages, hardware, or private configuration is read.
"""
from pathlib import Path
from xml.etree import ElementTree as ET
import diagram_helpers as H

OUT = Path(__file__).resolve().parent


def tile(key, title, detail, x, y, w=250, h=84, parent="1", fill="#FFFFFF"):
    return H.box(key, f'<b>{title}</b><br><font color="#596579">{detail}</font>',
                 x, y, w, h, parent, fill=fill, stroke="#B8C4D3", fs=13,
                 va="middle", sl=12, container=False, arc=8)


def panel(key, title, lines, x, y, w, h):
    H.box(key, "", x, y, w, h, fill="#F5F7FB", stroke="#D8E0EB", container=False)
    H.text(f'<b>{title}</b>', x+16, y+14, w-32, 24, fs=15, align="left")
    for i, line in enumerate(lines):
        H.text(line, x+16, y+49+i*27, w-32, 24, fs=12, align="left")


H.text('<b>CogniSight · local system architecture</b>', 30, 20, 1400, 40,
       fs=26, align="left")
H.text('Raspberry Pi 5 / 8 GB · one wearer · same-Wi-Fi caregiver · hardware acceptance pending',
       30, 65, 1450, 25, fs=15, align="left", fc="#596579")
H.box('pi', '<b>Raspberry Pi · one service process / ordinary user</b>',
      340, 115, 900, 750, fill="#F2F6FC", stroke="#6B89B4", fs=17, sl=18)
H.text('SENSORS / WEARER', 30, 122, 270, 25, fs=14, align="left", fc="#596579")
H.text('LOCAL ACCESS', 1290, 122, 280, 25, fs=14, align="left", fc="#596579")

tile('camera', 'Camera PCB V2.0 †', '22 visible free-end contacts<br>Sensor / full cable compatibility unverified', 30, 175, 270, 100)
tile('vision', 'Vision · sole camera owner', 'Picamera2 → BGR copy → latest frame<br>YuNet / SFace · max 4 faces', 375, 175, 335, 100, 'pi')
tile('runtime', 'Recognition runtime', 'Tracker / verified context / enrollment<br>Meghana · recognition; Jahnvi · integration', 785, 175, 420, 100, 'pi')
tile('receiver', 'Reported SIMA7670C / RS232 †', 'Positioning capability unverified<br>Navigation disabled until verified', 30, 340, 270, 100)
tile('gpsd', 'GPSD · loopback :2947', 'Verified receiver setup required †<br>GPSD alone owns receiver', 375, 340, 335, 100, 'pi')
tile('navigation', 'NavigationService', 'Independent GPSD worker / reconnect<br>Location + status only · Sharanya', 785, 340, 420, 100, 'pi')
tile('aux', 'Owned AUX headset / earphones', 'USB sound adapter required †<br>Mic + plug compatibility unverified †', 30, 505, 270, 130)
tile('audio', 'One AudioEngine', 'Vosk → commands / Piper → speech<br>Explicit USB routes · no speaker fallback', 375, 505, 335, 130, 'pi')
tile('snapshot', 'Snapshot → allowlisted projection', 'Original evidence age / independent GPS<br>No native or database work in HTTP', 785, 505, 420, 130, 'pi')
tile('private', 'Private SQLite / profiles / models', 'State outside Git · no raw camera storage<br>Enrollment owns profile changes', 375, 710, 335, 105, 'pi')
tile('dashboard', 'Read-only caregiver backend', 'Waitress · 127.0.0.1:8766<br>Schema 1 · indoor unavailable', 785, 710, 420, 105, 'pi')
tile('enrollment', 'Laptop → local enrollment', 'SSH tunnel → Pi 127.0.0.1:8765<br>No LAN proxy / caregiver controls', 1290, 175, 280, 100)
tile('phone', 'Caregiver phone', 'Same private Wi-Fi · login / 15 min session<br>HTTPS public root CA trust required', 1290, 505, 280, 130)
tile('caddy', 'Caddy · LAN HTTPS :443', 'Proxies dashboard only<br>No enrollment or GPSD exposure', 1290, 710, 280, 105)

# Explicit lanes avoid labels and unrelated components. Solid = data, dashed = control.
H.edge('camera','vision'); H.bn(1,337,225)
H.edge('vision','runtime')
H.edge('receiver','gpsd','grey'); H.bn(2,337,390)
H.edge('gpsd','navigation')
H.edge('runtime','snapshot',via=[(1220,225),(1220,485),(995,485)])
H.edge('navigation','snapshot'); H.bn(3,995,471)
H.edge('snapshot','dashboard')
H.edge('phone','caddy',dbl=True)
H.edge('caddy','dashboard',dbl=True); H.bn(4,1247,762)
H.fl(300,545,375,545); H.bn(5,337,545)
H.fl(375,595,300,595)
H.edge('audio','runtime','purple',via=[(744,570),(744,290),(995,290)])
H.bn(6,337,595)
H.edge('runtime','audio','purple',via=[(761,225),(761,655),(543,655)])
H.edge('enrollment','runtime',dbl=True); H.bn(7,1247,225)
H.edge('runtime','private',via=[(726,225),(726,685),(543,685)],dbl=True)
H.edge('private','vision','purple',via=[(358,762),(358,290),(543,290)])
H.emit_badges()

panel('flows','Numbered paths',[
 '1  Camera frames → recognition / enrollment.',
 '2  Verified receiver † → GPSD → navigation (disabled now).',
 '3  Recognition + outdoor → snapshot → dashboard.',
 '4  Phone ↔ Caddy HTTPS ↔ read-only backend.',
 '5  Headset mic † → USB adapter † → Vosk commands.',
 '6  Valid speech → one queue / Piper → AUX via USB †.',
 '7  Local enrollment ↔ profiles / SQLite → recognition.',
],30,905,750,260)
panel('contracts','Contracts / limits',[
 'Schema 1 · no images, embeddings or raw audio in API.',
 'Freshness: recognition <1s; GPS <10s by default (configurable).',
 'Capture monotonic time ≠ response / inference completion time.',
 'Last-known location is historical; UTC may be unavailable.',
 'Queues: frame 1; speech 8; subscribers 8 × 64 (lossy events).',
 'Speech: explicit 1 / automatic 0; stop cancels generation.',
 'Requested 640×480 / 15 fps is not measured throughput.',
],805,905,765,260)
panel('limits','Qualification / notation',[
 '† Hardware path / identity is unverified; physical contributor must confirm it.',
 'Solid black = data; dashed purple = control; dashed grey = disabled/unverified input.',
 'Neutral shapes = local / non-AWS components. No cloud service is part of this design.',
 'Indoor #5 deferred (Jahnvi / Archisha); no route guidance or emergency guarantee.',
 '#7 actual Pi/camera/audio and #8 phone/TLS/load acceptance remain pending.',
],30,1185,1540,200)
assert all(a in H.ids and b in H.ids for a,b in H.edges_chk)
model = ('<mxGraphModel adaptiveColors="auto" grid="1" gridSize="10" page="1" '
         'pageWidth="1600" pageHeight="1420" background="#FFFFFF">'
         '<root><mxCell id="0"/><mxCell id="1" parent="0"/>' + ''.join(H.cells) +
         '</root></mxGraphModel>')
xml = '<mxfile host="app.diagrams.net"><diagram id="cognisight" name="Local system">'+model+'</diagram></mxfile>'
ET.fromstring(xml)
(OUT/'cognisight-architecture.drawio').write_text(xml+'\n')
print(f'Generated {len(H.cells)} cells; {len(H.edges_chk)} validated edges')
