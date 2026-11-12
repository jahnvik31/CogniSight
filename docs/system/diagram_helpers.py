import html, sys

cells = []
org = {'1': (0, 0)}
par = {}
C = {}
ids = set()
edges_chk = []
_n = [0]


def esc(s):
    return html.escape(s, quote=True)


def uid(p='c'):
    _n[0] += 1
    return f'{p}{_n[0]}'


def lab(name, s=None, fs=8, col='#5F6B7A'):
    t = f'<b>{name}</b>'
    if s:
        t += f'<br><font style="font-size:{fs - 1}px" color="{col}">{s}</font>'
    return t


def vtx(id, val, style, x, y, w, h, parent='1'):
    ox, oy = org[parent]
    cells.append(f'<mxCell id="{id}" value="{esc(val)}" style="{style}html=1;" vertex="1" parent="{parent}">'
                 f'<mxGeometry x="{x-ox:g}" y="{y-oy:g}" width="{w:g}" height="{h:g}" as="geometry"/></mxCell>')
    par[id] = parent
    org[id] = (x, y)
    C[id] = (x + w / 2, y + h / 2)
    ids.add(id)
    return id


GRP = {
    'cloud': 'grIcon=mxgraph.aws4.group_aws_cloud_alt;strokeColor=#232F3E;fontColor=#232F3E;',
    'org': 'grIcon=mxgraph.aws4.group_account;strokeColor=#CD2264;fontColor=#CD2264;',
    'region': 'grIcon=mxgraph.aws4.group_region;strokeColor=#00A4A6;fontColor=#00797B;dashed=1;dashPattern=6 3;',
    'vpc': 'grIcon=mxgraph.aws4.group_vpc2;strokeColor=#8C4FFF;fontColor=#7A3FE0;',
    'dc': 'grIcon=mxgraph.aws4.group_corporate_data_center;strokeColor=#7D8998;fontColor=#4A5A70;',
}


def grp(id, label, x, y, w, h, parent, kind, fill='none'):
    st = ('points=[[0,0],[0.25,0],[0.5,0],[0.75,0],[1,0],[1,0.25],[1,0.5],[1,0.75],[1,1],[0.75,1],[0.5,1],[0.25,1],[0,1],[0,0.75],[0,0.5],[0,0.25]];'
          'outlineConnect=0;gradientColor=none;whiteSpace=wrap;fontSize=10;fontStyle=1;container=1;pointerEvents=0;collapsible=0;'
          'recursiveResize=0;shape=mxgraph.aws4.group;verticalAlign=top;align=left;spacingLeft=30;'
          f'fillColor={fill};' + GRP[kind])
    return vtx(id, label, st, x, y, w, h, parent)


def box(id, val, x, y, w, h, parent='1', fill='#FFFFFF', stroke='#9AA5B1', dashed=False, fs=9, fc='#232F3E',
        align='left', va='top', sl=8, sw=1, arc=4, container=True, st_extra=''):
    st = (f'rounded=1;arcSize={arc};whiteSpace=wrap;fillColor={fill};strokeColor={stroke};strokeWidth={sw};fontSize={fs};'
          f'fontColor={fc};align={align};verticalAlign={va};spacingLeft={sl};spacingTop=3;spacingRight=4;')
    if dashed:
        st += 'dashed=1;dashPattern=5 3;'
    if container:
        st += 'container=1;collapsible=0;pointerEvents=0;'
    return vtx(id, val, st + st_extra, x, y, w, h, parent)


def text(val, x, y, w, h, parent='1', fs=8, align='center', fc='#232F3E', va='top', id=None):
    return vtx(id or uid('t'), val, f'text;whiteSpace=wrap;align={align};verticalAlign={va};fontSize={fs};fontColor={fc};'
               'spacing=0;', x, y, w, h, parent)


def _label(name, sb, cx, cy, s, parent, lw, lh, fs, side, dy=0):
    if not name:
        return
    if side == 'left':
        text(lab(name, sb, fs), cx - s / 2 - 4 - lw, cy - lh / 2, lw, lh, parent, fs=fs, align='right', va='middle')
    elif side:
        text(lab(name, sb, fs), cx + s / 2 + 4, cy - lh / 2, lw, lh, parent, fs=fs, align='left', va='middle')
    else:
        text(lab(name, sb, fs), cx - lw / 2, cy + s / 2 + 2 + dy, lw, lh, parent, fs=fs)


def aws(id, parent, cx, cy, res, color, name, sb=None, s=34, lw=88, lh=30, fs=8, side=False):
    st = (f'sketch=0;outlineConnect=0;fontColor=#232F3E;fillColor={color};strokeColor=#ffffff;dashed=0;aspect=fixed;'
          f'shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.{res};')
    vtx(id, '', st, cx - s / 2, cy - s / 2, s, s, parent)
    _label(name, sb, cx, cy, s, parent, lw, lh, fs, side)
    return id


def awsp(id, parent, cx, cy, shape, color, name, sb=None, s=34, lw=88, lh=30, fs=8, side=False, dy=0):
    st = (f'sketch=0;outlineConnect=0;fillColor={color};strokeColor=none;dashed=0;aspect=fixed;pointerEvents=1;'
          f'shape=mxgraph.aws4.{shape};')
    vtx(id, '', st, cx - s / 2, cy - s / 2, s, s, parent)
    _label(name, sb, cx, cy, s, parent, lw, lh, fs, side, dy)
    return id


def gen(id, parent, cx, cy, glyph, color, name, sb=None, s=34, lw=88, lh=30, fs=8, side=False):
    """generic (non-AWS) icon: neutral rounded tile"""
    vtx(id, glyph, f'rounded=1;arcSize=16;fillColor={color};strokeColor=none;fontColor=#FFFFFF;fontStyle=1;fontSize=8;whiteSpace=wrap;',
        cx - s / 2, cy - s / 2, s, s, parent)
    _label(name, sb, cx, cy, s, parent, lw, lh, fs, side)
    return id


EC = {
    'black': ('#1A1A1A', False, 1.5), 'grey': ('#7F7F7F', True, 1.5), 'blue': ('#0972D3', True, 2),
    'red': ('#D13212', True, 1.5), 'purple': ('#8C4FFF', True, 1.5),
}


def estyle(kind, dbl, ortho):
    c, d, w = EC[kind]
    s = f'rounded=1;strokeColor={c};strokeWidth={w};endArrow=block;endFill=1;endSize=4;startSize=4;'
    if ortho:
        s += 'edgeStyle=orthogonalEdgeStyle;'
    if d:
        s += 'dashed=1;dashPattern=6 3;'
    if dbl:
        s += 'startArrow=block;startFill=1;'
    return s


def edge(a, b, kind='black', via=None, dbl=False):
    pts = ''
    if via:
        pts = '<Array as="points">' + ''.join(f'<mxPoint x="{x}" y="{y}"/>' for x, y in via) + '</Array>'
    cells.append(f'<mxCell id="{uid("e")}" value="" style="{estyle(kind, dbl, bool(via))}html=1;" edge="1" parent="1" source="{a}" target="{b}">'
                 f'<mxGeometry relative="1" as="geometry">{pts}</mxGeometry></mxCell>')
    edges_chk.append((a, b))


def fl(x1, y1, x2, y2, kind='black', dbl=False, via=None):
    pts = ''
    if via:
        pts = '<Array as="points">' + ''.join(f'<mxPoint x="{x}" y="{y}"/>' for x, y in via) + '</Array>'
    cells.append(f'<mxCell id="{uid("f")}" value="" style="{estyle(kind, dbl, bool(via))}html=1;" edge="1" parent="1">'
                 f'<mxGeometry relative="1" as="geometry"><mxPoint x="{x1}" y="{y1}" as="sourcePoint"/>'
                 f'<mxPoint x="{x2}" y="{y2}" as="targetPoint"/>{pts}</mxGeometry></mxCell>')


BADGES = []


def bn(n, x, y):
    BADGES.append(('n', n, x, y))


def ba(l, x, y):
    BADGES.append(('a', l, x, y))


def emit_badges():
    for k, v, x, y in BADGES:
        fill = '#1A1A1A' if k == 'n' else '#0972D3'
        vtx(uid('b'), str(v), f'ellipse;fillColor={fill};strokeColor=#FFFFFF;strokeWidth=1.5;fontColor=#FFFFFF;fontStyle=1;fontSize=9;'
            'whiteSpace=wrap;spacing=0;', x - 9, y - 9, 18, 18, '1')


SEC, NET, CMP, STO, DB, ML, MGT, GEN = '#DD344C', '#8C4FFF', '#ED7100', '#7AA116', '#C925D1', '#01A88D', '#E7157B', '#7D8998'
TEAL_BG = '#E6F6F7'
