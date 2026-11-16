"""Génère le document Word « Cahier des charges — Univers Academy ».

Le contenu de référence reste ``docs/CAHIER_DES_CHARGES.md`` : ce script le lit,
le met en forme et produit ``docs/CAHIER_DES_CHARGES.docx``. Une seule source,
donc, pour le Markdown et le Word.

Usage (depuis la racine du projet) :

    .\.venv\Scripts\python.exe docs\generate_cahier_des_charges_docx.py

Le script ne touche ni à Django ni à la base : il ne dépend que de
``python-docx``. Les éléments Markdown reconnus sont les titres (``#`` à
``####``), les paragraphes, les listes à puces et numérotées, les tableaux, les
citations (encadrés) et les blocs de code. La mise en forme inline accepte le
gras ``**…**``, l'italique ``*…*`` et le code `` `…` ``.

Les tableaux reçoivent une largeur minimale par colonne, calculée sur le plus
long jeton (identifiant, chemin, nom de rôle) : un mot n'est jamais coupé au
milieu. Si les minima ne tiennent pas dans la largeur utile, la police du
tableau est réduite par pas de 0,2 point avant de rogner une colonne.
"""
from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

DOCS_DIR = Path(__file__).resolve().parent
SOURCE = DOCS_DIR / 'CAHIER_DES_CHARGES.md'
OUTPUT = DOCS_DIR / 'CAHIER_DES_CHARGES.docx'

# ===========================================================================
# Palette et constantes de mise en page
# ===========================================================================

NAVY = RGBColor(0x1E, 0x3A, 0x5F)
BLUE = RGBColor(0x2F, 0x55, 0x97)
INDIGO = RGBColor(0x4F, 0x46, 0xE5)
GREY = RGBColor(0x5B, 0x5F, 0x85)
DARK = RGBColor(0x1E, 0x20, 0x44)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
GOLD = RGBColor(0xC8, 0xA4, 0x5A)

FILL_HEADER = '1E3A5F'
FILL_ZEBRA = 'F6F7FC'
FILL_CALLOUT = 'EEF0FB'
FILL_CODE = 'F4F5FA'

TEXT_WIDTH_CM = 17.0
FONT_BODY = 'Calibri'
FONT_CODE = 'Consolas'
ZWSP = '\u200b'


# ===========================================================================
# Primitives XML
# ===========================================================================

def set_cell_bg(cell, hex_color):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), hex_color)
    tc_pr.append(shd)


def set_cell_margins(cell, top=60, bottom=60, left=60, right=60):
    tc_pr = cell._tc.get_or_add_tcPr()
    mar = OxmlElement('w:tcMar')
    for tag, value in (('top', top), ('bottom', bottom),
                       ('left', left), ('right', right)):
        node = OxmlElement(f'w:{tag}')
        node.set(qn('w:w'), str(value))
        node.set(qn('w:type'), 'dxa')
        mar.append(node)
    tc_pr.append(mar)


def set_cell_left_accent(cell, color='4F46E5', size=24):
    tc_pr = cell._tc.get_or_add_tcPr()
    borders = OxmlElement('w:tcBorders')
    left = OxmlElement('w:left')
    left.set(qn('w:val'), 'single')
    left.set(qn('w:sz'), str(size))
    left.set(qn('w:space'), '0')
    left.set(qn('w:color'), color)
    borders.append(left)
    tc_pr.append(borders)


def repeat_header(row):
    tr_pr = row._tr.get_or_add_trPr()
    header = OxmlElement('w:tblHeader')
    header.set(qn('w:val'), 'true')
    tr_pr.append(header)


def no_split(row):
    tr_pr = row._tr.get_or_add_trPr()
    flag = OxmlElement('w:cantSplit')
    flag.set(qn('w:val'), 'true')
    tr_pr.append(flag)


def set_table_borders(table, color='C7CBDD', size=4):
    tbl_pr = table._tbl.tblPr
    borders = OxmlElement('w:tblBorders')
    for edge in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
        node = OxmlElement(f'w:{edge}')
        node.set(qn('w:val'), 'single')
        node.set(qn('w:sz'), str(size))
        node.set(qn('w:space'), '0')
        node.set(qn('w:color'), color)
        borders.append(node)
    tbl_pr.append(borders)


def set_fixed_layout(table):
    tbl_pr = table._tbl.tblPr
    layout = OxmlElement('w:tblLayout')
    layout.set(qn('w:type'), 'fixed')
    tbl_pr.append(layout)


def add_field(paragraph, instruction, *, size=8.5, color=GREY):
    run = paragraph.add_run()
    begin = OxmlElement('w:fldChar')
    begin.set(qn('w:fldCharType'), 'begin')
    instr = OxmlElement('w:instrText')
    instr.set(qn('xml:space'), 'preserve')
    instr.text = instruction
    separate = OxmlElement('w:fldChar')
    separate.set(qn('w:fldCharType'), 'separate')
    text = OxmlElement('w:t')
    text.text = '1'
    end = OxmlElement('w:fldChar')
    end.set(qn('w:fldCharType'), 'end')
    for node in (begin, instr, separate, text, end):
        run._r.append(node)
    run.font.size = Pt(size)
    run.font.color.rgb = color


def enable_field_update(doc):
    """Demande à Word de recalculer le sommaire à l'ouverture."""
    settings = doc.settings.element
    update = OxmlElement('w:updateFields')
    update.set(qn('w:val'), 'true')
    settings.append(update)


# ===========================================================================
# Lecture du Markdown
# ===========================================================================

TABLE_SEPARATOR = re.compile(r'^\|[\s:|-]+\|$')
NUMBERED_ITEM = re.compile(r'^(\d+)\.\s+(.*)$')
BULLET_ITEM = re.compile(r'^[-*]\s+(.*)$')


def split_row(line):
    line = line.strip()
    if line.startswith('|'):
        line = line[1:]
    if line.endswith('|'):
        line = line[:-1]
    return [cell.strip().replace('\\|', '|') for cell in line.split('|')]


def parse_markdown(text):
    lines = text.splitlines()
    blocks = []
    i = 0
    total = len(lines)

    while i < total:
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        if stripped.startswith('```'):
            fence = stripped[3:].strip()
            i += 1
            code = []
            while i < total and not lines[i].strip().startswith('```'):
                code.append(lines[i].rstrip())
                i += 1
            i += 1  # ferme le bloc
            blocks.append({'type': 'code', 'lang': fence, 'lines': code})
            continue

        if stripped == '---':
            blocks.append({'type': 'hr'})
            i += 1
            continue

        heading = re.match(r'^(#{1,4})\s+(.*)$', stripped)
        if heading:
            level = len(heading.group(1))
            blocks.append({
                'type': f'h{level - 1}' if level > 1 else 'h0',
                'text': heading.group(2).strip(),
            })
            i += 1
            continue

        if stripped.startswith('>'):
            quote = []
            while i < total and lines[i].strip().startswith('>'):
                content = lines[i].strip()[1:]
                quote.append(content[1:] if content.startswith(' ') else content)
                i += 1
            blocks.append({'type': 'quote', 'lines': quote})
            continue

        if stripped.startswith('|') and i + 1 < total \
                and TABLE_SEPARATOR.match(lines[i + 1].strip()):
            rows = [split_row(stripped)]
            i += 2
            while i < total and lines[i].strip().startswith('|'):
                rows.append(split_row(lines[i]))
                i += 1
            blocks.append({'type': 'table', 'rows': rows})
            continue

        numbered = NUMBERED_ITEM.match(stripped)
        if numbered:
            items = []
            while i < total:
                match = NUMBERED_ITEM.match(lines[i].strip())
                if not match:
                    break
                items.append((match.group(1), match.group(2).strip()))
                i += 1
            blocks.append({'type': 'ol', 'items': items})
            continue

        bullet = BULLET_ITEM.match(stripped)
        if bullet:
            items = []
            while i < total:
                match = BULLET_ITEM.match(lines[i].strip())
                if not match:
                    break
                items.append(match.group(1).strip())
                i += 1
            blocks.append({'type': 'ul', 'items': items})
            continue

        # Paragraphe : on recolle les lignes de continuation.
        paragraph = [stripped]
        i += 1
        while i < total:
            nxt = lines[i].strip()
            if not nxt or nxt.startswith(('|', '>', '```', '#')) \
                    or NUMBERED_ITEM.match(nxt) or BULLET_ITEM.match(nxt) \
                    or nxt == '---':
                break
            paragraph.append(nxt)
            i += 1
        blocks.append({'type': 'p', 'text': ' '.join(paragraph)})

    return blocks


# ===========================================================================
# Mise en forme inline
# ===========================================================================

INLINE = re.compile(r'(\*\*.+?\*\*|`[^`]+`|\*[^*\n]+\*)')


def add_inline(paragraph, text, *, size=10.4, color=DARK, bold=False,
               italic=False):
    """Ajoute un texte en interprétant gras, code et italique.

    Les marqueurs se imbriquent (``**gras avec du `code`)**``) : le fragment
    gras est réanalysé au lieu d'être écrit tel quel.
    """
    for part in INLINE.split(text):
        if not part:
            continue
        if part.startswith('**') and part.endswith('**') and len(part) > 4:
            add_inline(paragraph, part[2:-2], size=size, color=color,
                       bold=True, italic=italic)
            continue
        if part.startswith('*') and part.endswith('*') and len(part) > 2:
            add_inline(paragraph, part[1:-1], size=size, color=color,
                       bold=bold, italic=True)
            continue
        if part.startswith('`') and part.endswith('`') and len(part) > 2:
            run = paragraph.add_run(part[1:-1])
            run.bold = bold
            run.italic = italic
            run.font.size = Pt(size - 0.6)
            run.font.name = FONT_CODE
            run.font.color.rgb = NAVY
            continue
        run = paragraph.add_run(part)
        run.bold = bold
        run.italic = italic
        run.font.size = Pt(size)
        if color is not None:
            run.font.color.rgb = color
    return paragraph


# ===========================================================================
# Blocs de mise en page
# ===========================================================================

def add_paragraph(text, *, size=10.4, color=DARK, space_after=6,
                  align=None, italic=False, bold=False,
                  keep_with_next=False):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(space_after)
    p.paragraph_format.line_spacing = 1.15
    p.paragraph_format.keep_with_next = keep_with_next
    if align is not None:
        p.alignment = align
    add_inline(p, text, size=size, color=color, italic=italic, bold=bold)
    return p


def add_heading(text, level, *, page_break_before=False, as_heading=True):
    p = doc.add_paragraph(style=f'Heading {level}' if as_heading else None)
    p.paragraph_format.page_break_before = page_break_before
    p.paragraph_format.keep_with_next = True
    run = p.add_run(text)
    if level == 1:
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(10)
        run.font.size = Pt(17)
        run.font.color.rgb = NAVY
        run.bold = True
        p_pr = p._p.get_or_add_pPr()
        borders = OxmlElement('w:pBdr')
        bottom = OxmlElement('w:bottom')
        bottom.set(qn('w:val'), 'single')
        bottom.set(qn('w:sz'), '8')
        bottom.set(qn('w:space'), '4')
        bottom.set(qn('w:color'), 'C8A45A')
        borders.append(bottom)
        p_pr.append(borders)
    elif level == 2:
        p.paragraph_format.space_before = Pt(12)
        p.paragraph_format.space_after = Pt(5)
        run.font.size = Pt(13)
        run.font.color.rgb = BLUE
        run.bold = True
    else:
        p.paragraph_format.space_before = Pt(9)
        p.paragraph_format.space_after = Pt(3)
        run.font.size = Pt(11.3)
        run.font.color.rgb = INDIGO
        run.bold = True
    return p


def add_bullets(items, *, numbered=False):
    for index, item in enumerate(items, start=1):
        if numbered:
            number, content = item
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Cm(0.9)
            p.paragraph_format.first_line_indent = Cm(-0.55)
            p.paragraph_format.space_after = Pt(2.5)
            p.paragraph_format.line_spacing = 1.1
            run = p.add_run(f'{number}. ')
            run.bold = True
            run.font.size = Pt(10.2)
            run.font.color.rgb = NAVY
            add_inline(p, content, size=10.2)
        else:
            p = doc.add_paragraph(style='List Bullet')
            p.paragraph_format.left_indent = Cm(0.9)
            p.paragraph_format.first_line_indent = Cm(-0.45)
            p.paragraph_format.space_after = Pt(2.5)
            p.paragraph_format.line_spacing = 1.1
            add_inline(p, item, size=10.2)


def add_callout(lines):
    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    set_fixed_layout(table)
    cell = table.rows[0].cells[0]
    cell.width = Cm(TEXT_WIDTH_CM)
    set_cell_bg(cell, FILL_CALLOUT)
    set_cell_left_accent(cell)
    set_cell_margins(cell, top=130, bottom=130, left=180, right=150)
    cell.text = ''
    first = True
    for line in lines:
        if not line.strip():
            continue
        p = cell.paragraphs[0] if first else cell.add_paragraph()
        first = False
        p.paragraph_format.space_after = Pt(3)
        p.paragraph_format.line_spacing = 1.15
        add_inline(p, line.strip(), size=9.4)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


def add_code_block(lines, lang=''):
    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    set_fixed_layout(table)
    cell = table.rows[0].cells[0]
    cell.width = Cm(TEXT_WIDTH_CM)
    set_cell_bg(cell, FILL_CODE)
    set_cell_margins(cell, top=110, bottom=110, left=160, right=140)
    cell.text = ''
    if not lines:
        lines = ['']
    for index, line in enumerate(lines):
        p = cell.paragraphs[0] if index == 0 else cell.add_paragraph()
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.line_spacing = 1.0
        run = p.add_run(line if line else ' ')
        run.font.name = FONT_CODE
        run.font.size = Pt(8.3)
        run.font.color.rgb = GREY if line.lstrip().startswith('#') else DARK
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


def compute_widths(rows, floors):
    """Répartit 17 cm en garantissant à chaque colonne sa largeur minimale."""
    columns = len(rows[0])
    weights = []
    for index in range(columns):
        values = [row[index] if index < len(row) else '' for row in rows]
        average = sum(len(value) for value in values) / len(values)
        header = len(values[0])
        weight = 0.55 * average + 0.45 * header
        weights.append(max(4.0, min(48.0, weight)))

    total_floor = sum(floors)
    if total_floor >= TEXT_WIDTH_CM:
        factor = TEXT_WIDTH_CM / total_floor
        return [floor * factor for floor in floors]

    surplus = TEXT_WIDTH_CM - total_floor
    total_weight = sum(weights)
    return [floors[index] + surplus * weights[index] / total_weight
            for index in range(columns)]


def column_floors(rows, font):
    """Largeur minimale pour qu'aucun identifiant ne soit coupé au milieu."""
    columns = len(rows[0])
    base = 1.15 if columns >= 8 else (1.35 if columns >= 6 else 1.7)
    floors = []
    for index in range(columns):
        longest = 0
        for row in rows:
            for token in re.split(r'[\s/_\-' + ZWSP + r']+', row[index]):
                longest = max(longest, len(token))
        needed = longest * 0.0215 * font + 0.24
        floors.append(max(base, min(5.2, needed)))
    return floors


def break_hints(text):
    """Autorise les coupures dans les identifiants et chemins des tableaux."""
    return text.replace('_', f'_{ZWSP}').replace('/', f'/{ZWSP}')


def clean_cell(text):
    """Retire le balisage inline : sert au calcul des largeurs."""
    text = text.replace('**', '').replace('`', '').replace('*', '')
    return break_hints(text)


def add_table(rows, *, font=None):
    columns = len(rows[0])
    rows = [row + [''] * (columns - len(row)) if len(row) < columns else row
            for row in rows]
    if font is None:
        font = 7.6 if columns >= 8 else (8.0 if columns >= 6 else 8.6)
    analysis = [[clean_cell(value) for value in row] for row in rows]
    # Si les plus longs jetons ne tiennent pas, on réduit légèrement la police
    # du tableau plutôt que de couper un mot en deux.
    while font > 6.4 and sum(column_floors(analysis, font)) > TEXT_WIDTH_CM:
        font -= 0.2
    widths = compute_widths(analysis, column_floors(analysis, font))

    table = doc.add_table(rows=1, cols=columns)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    set_fixed_layout(table)
    set_table_borders(table)

    header = table.rows[0]
    repeat_header(header)
    no_split(header)
    for index, label in enumerate(rows[0]):
        cell = header.cells[index]
        cell.width = Cm(widths[index])
        set_cell_bg(cell, FILL_HEADER)
        set_cell_margins(cell)
        cell.text = ''
        p = cell.paragraphs[0]
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.line_spacing = 1.0
        run = p.add_run(break_hints(label))
        run.bold = True
        run.font.size = Pt(font)
        run.font.color.rgb = WHITE

    for row_index, values in enumerate(rows[1:]):
        cells = table.add_row().cells
        no_split(table.rows[-1])
        for column, value in enumerate(values):
            cell = cells[column]
            cell.width = Cm(widths[column])
            set_cell_margins(cell)
            if row_index % 2 == 1:
                set_cell_bg(cell, FILL_ZEBRA)
            cell.text = ''
            p = cell.paragraphs[0]
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(0)
            p.paragraph_format.line_spacing = 1.0
            add_inline(p, break_hints(value), size=font,
                       bold=(column == 0 and columns == 2))

    for index, width in enumerate(widths):
        table.columns[index].width = Cm(width)

    # Un petit tableau ne se coupe pas entre deux pages : les lignes restent
    # solidaires, sinon une fin de tableau isolée laisse une page presque vide.
    if len(table.rows) <= 20:
        for row in table.rows[:-1]:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    paragraph.paragraph_format.keep_with_next = True

    doc.add_paragraph().paragraph_format.space_after = Pt(3)
    return table


def add_toc():
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.space_after = Pt(8)
    run = paragraph.add_run()
    begin = OxmlElement('w:fldChar')
    begin.set(qn('w:fldCharType'), 'begin')
    instr = OxmlElement('w:instrText')
    instr.set(qn('xml:space'), 'preserve')
    instr.text = 'TOC \\o "1-2" \\h \\z \\u'
    separate = OxmlElement('w:fldChar')
    separate.set(qn('w:fldCharType'), 'separate')
    text = OxmlElement('w:t')
    text.text = ("Sommaire généré par Word : ouvrez le document puis "
                 "actualisez les champs (F9) si nécessaire.")
    end = OxmlElement('w:fldChar')
    end.set(qn('w:fldCharType'), 'end')
    for node in (begin, instr, separate, text, end):
        run._r.append(node)
    run.font.size = Pt(9.5)
    run.font.color.rgb = GREY


# ===========================================================================
# Document
# ===========================================================================

doc = Document()

core = doc.core_properties
core.title = "Cahier des charges — Univers Academy"
core.subject = ("Plateforme de gestion d'un centre de formation : "
                "périmètre, exigences, règles, architecture, recette")
core.author = 'Univers Academy'
core.language = 'fr-FR'
core.keywords = ('cahier des charges; Django; centre de formation; '
                 'pédagogie; comptabilité; Google Sheets')

normal = doc.styles['Normal']
normal.font.name = FONT_BODY
normal.font.size = Pt(10.4)
normal.font.color.rgb = DARK
normal.paragraph_format.space_after = Pt(6)
normal.paragraph_format.line_spacing = 1.15
normal.paragraph_format.widow_control = True

for style_name, size, color in (('Heading 1', 17, NAVY),
                                ('Heading 2', 13, BLUE),
                                ('Heading 3', 11.3, INDIGO)):
    style = doc.styles[style_name]
    style.font.name = FONT_BODY
    style.font.size = Pt(size)
    style.font.bold = True
    style.font.color.rgb = color
    style.paragraph_format.keep_with_next = True

section = doc.sections[0]
section.page_height = Cm(29.7)
section.page_width = Cm(21)
section.top_margin = Cm(2)
section.bottom_margin = Cm(1.8)
section.left_margin = Cm(2)
section.right_margin = Cm(2)
section.header_distance = Cm(1)
section.footer_distance = Cm(0.9)
section.different_first_page_header_footer = True

header = section.header.paragraphs[0]
header.alignment = WD_ALIGN_PARAGRAPH.RIGHT
run = header.add_run('Cahier des charges — Univers Academy  ·  version 1.0')
run.font.size = Pt(8)
run.font.color.rgb = GREY

footer = section.footer.paragraphs[0]
footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = footer.add_run('Cahier des charges  ·  page ')
run.font.size = Pt(8)
run.font.color.rgb = GREY
add_field(footer, 'PAGE')
run = footer.add_run(' sur ')
run.font.size = Pt(8)
run.font.color.rgb = GREY
add_field(footer, 'NUMPAGES')

# ---------------------------------------------------------------------------
# Page de garde
# ---------------------------------------------------------------------------

blocks = parse_markdown(SOURCE.read_text(encoding='utf-8'))

title_block = blocks.pop(0)
subtitle_block = blocks.pop(0)
meta_block = blocks.pop(0)
legend_block = blocks.pop(0)
toc_block = blocks.pop(0)

band = doc.add_table(rows=1, cols=1)
band.autofit = False
set_fixed_layout(band)
band_cell = band.rows[0].cells[0]
band_cell.width = Cm(TEXT_WIDTH_CM)
set_cell_bg(band_cell, FILL_HEADER)
set_cell_margins(band_cell, top=240, bottom=240, left=260, right=260)
band_cell.text = ''
p = band_cell.paragraphs[0]
p.paragraph_format.space_after = Pt(2)
run = p.add_run('UNIVERS ACADEMY')
run.bold = True
run.font.size = Pt(13)
run.font.color.rgb = GOLD
p = band_cell.add_paragraph()
run = p.add_run('Brazzaville — République du Congo')
run.font.size = Pt(10)
run.font.color.rgb = WHITE

doc.add_paragraph().paragraph_format.space_after = Pt(38)

p = doc.add_paragraph()
p.paragraph_format.space_after = Pt(4)
run = p.add_run(title_block['text'])
run.bold = True
run.font.size = Pt(34)
run.font.color.rgb = NAVY

p = doc.add_paragraph()
p.paragraph_format.space_after = Pt(16)
run = p.add_run(subtitle_block['text'])
run.font.size = Pt(14.5)
run.font.color.rgb = GREY

p = doc.add_paragraph()
p.paragraph_format.space_after = Pt(18)
p_pr = p._p.get_or_add_pPr()
borders = OxmlElement('w:pBdr')
bottom = OxmlElement('w:bottom')
bottom.set(qn('w:val'), 'single')
bottom.set(qn('w:sz'), '12')
bottom.set(qn('w:space'), '4')
bottom.set(qn('w:color'), 'C8A45A')
borders.append(bottom)
p_pr.append(borders)

add_table(meta_block['rows'], font=9.2)

doc.add_paragraph().paragraph_format.space_after = Pt(10)
add_callout(legend_block['lines'])

# ---------------------------------------------------------------------------
# Sommaire
# ---------------------------------------------------------------------------

add_heading(toc_block['text'], 1, page_break_before=True, as_heading=False)
add_toc()

# Le sommaire rédigé dans le Markdown est remplacé par le champ TOC de Word.
while blocks and blocks[0]['type'] in ('ol', 'ul', 'hr'):
    blocks.pop(0)

# ---------------------------------------------------------------------------
# Corps du document
# ---------------------------------------------------------------------------

for index, block in enumerate(blocks):
    kind = block['type']
    following = blocks[index + 1]['type'] if index + 1 < len(blocks) else None

    if kind == 'hr':
        continue

    if kind == 'h1':
        add_heading(block['text'], 1, page_break_before=True)
    elif kind == 'h2':
        add_heading(block['text'], 2)
    elif kind == 'h3':
        add_heading(block['text'], 3)
    elif kind == 'h0':
        add_heading(block['text'], 1, page_break_before=True)
    elif kind == 'p':
        add_paragraph(
            block['text'],
            keep_with_next=(following in ('ul', 'ol', 'table', 'code')
                            and len(block['text']) <= 120),
        )
    elif kind == 'ul':
        add_bullets(block['items'])
    elif kind == 'ol':
        add_bullets(block['items'], numbered=True)
    elif kind == 'table':
        add_table(block['rows'])
    elif kind == 'quote':
        add_callout(block['lines'])
    elif kind == 'code':
        add_code_block(block['lines'], block.get('lang', ''))

enable_field_update(doc)
doc.save(OUTPUT)

print(f'Document généré : {OUTPUT}')
print(f'Paragraphes     : {len(doc.paragraphs)}')
print(f'Tableaux        : {len(doc.tables)}')
