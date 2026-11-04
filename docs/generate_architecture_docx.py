"""Génère le document Word « Architecture métier — Univers Academy ».

Usage (depuis la racine du projet) :
    .\\env\\Scripts\\python.exe docs\\generate_architecture_docx.py

Le script introspecte les modèles Django pour produire les tableaux de champs
(annexe D) et le catalogue des routes (annexe B), afin que le document reste
aligné sur le code. Le reste du contenu est rédigé dans ce fichier.
"""
from __future__ import annotations

import os
import sys
from datetime import date

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'univers_academy.settings')

import django  # noqa: E402

django.setup()

from django.apps import apps  # noqa: E402
from django.urls import get_resolver  # noqa: E402

from docx import Document  # noqa: E402
from docx.enum.section import WD_SECTION  # noqa: E402
from docx.enum.table import WD_TABLE_ALIGNMENT  # noqa: E402
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK  # noqa: E402
from docx.oxml import OxmlElement  # noqa: E402
from docx.oxml.ns import qn  # noqa: E402
from docx.shared import Cm, Pt, RGBColor  # noqa: E402

NAVY = RGBColor(0x1E, 0x3A, 0x5F)
BLUE = RGBColor(0x2F, 0x55, 0x97)
INDIGO = RGBColor(0x4F, 0x46, 0xE5)
GREY = RGBColor(0x5B, 0x5F, 0x85)
DARK = RGBColor(0x1E, 0x20, 0x44)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
RED = RGBColor(0xB4, 0x23, 0x18)

FILL_HEADER = '1E3A5F'
FILL_SUBHEADER = 'E8EDF7'
FILL_ZEBRA = 'F6F7FC'
FILL_CALLOUT = 'EEF0FB'
FILL_WARNING = 'FFF4E5'

TODAY = '1er novembre 2026'
VERSION = '1.0'

OUTPUT = os.path.join(BASE_DIR, 'docs', 'Architecture_metier_Univers_Academy.docx')

core_app = apps.get_app_config('core')
MODELS = list(core_app.get_models())
MODEL_BY_NAME = {m.__name__: m for m in MODELS}

# ===========================================================================
# Primitives de mise en page
# ===========================================================================


def set_cell_bg(cell, hex_color):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), hex_color)
    tc_pr.append(shd)


def set_cell_margins(cell, top=60, bottom=60, left=90, right=90):
    tc_pr = cell._tc.get_or_add_tcPr()
    mar = OxmlElement('w:tcMar')
    for tag, value in (('top', top), ('bottom', bottom),
                       ('left', left), ('right', right)):
        node = OxmlElement(f'w:{tag}')
        node.set(qn('w:w'), str(value))
        node.set(qn('w:type'), 'dxa')
        mar.append(node)
    tc_pr.append(mar)


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
    tbl = table._tbl
    tbl_pr = tbl.tblPr
    borders = OxmlElement('w:tblBorders')
    for edge in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
        node = OxmlElement(f'w:{edge}')
        node.set(qn('w:val'), 'single')
        node.set(qn('w:sz'), str(size))
        node.set(qn('w:space'), '0')
        node.set(qn('w:color'), color)
        borders.append(node)
    tbl_pr.append(borders)


def cell_text(cell, text, *, bold=False, size=8.5, color=None,
              align=None, italic=False):
    cell.text = ''
    p = cell.paragraphs[0]
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.line_spacing = 1.0
    if align is not None:
        p.alignment = align
    run = p.add_run(str(text))
    run.font.size = Pt(size)
    run.bold = bold
    run.italic = italic
    if color is not None:
        run.font.color.rgb = color


def add_table(headers, rows, widths=None, *, size=8.5, header_size=8.5,
              zebra=True, align_center=None, first_col_bold=False):
    table = glossary_table = None
    table = doc.add_table(rows=1, cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    set_table_borders(table)
    hdr = table.rows[0]
    repeat_header(hdr)
    no_split(hdr)
    for idx, label in enumerate(headers):
        cell = hdr.cells[idx]
        cell_text(cell, label, bold=True, size=header_size, color=WHITE)
        set_cell_bg(cell, FILL_HEADER)
        set_cell_margins(cell)
        if widths:
            cell.width = Cm(widths[idx])
    for r_idx, row in enumerate(rows):
        cells = table.add_row().cells
        no_split(table.rows[-1])
        for c_idx, value in enumerate(row):
            cell = cells[c_idx]
            center = align_center and c_idx in align_center
            cell_text(
                cell, value, size=size,
                bold=(first_col_bold and c_idx == 0),
                align=WD_ALIGN_PARAGRAPH.CENTER if center else None,
            )
            set_cell_margins(cell)
            if zebra and r_idx % 2 == 1:
                set_cell_bg(cell, FILL_ZEBRA)
            if widths:
                cell.width = Cm(widths[c_idx])
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return table


def add_paragraph(text, *, style=None, bold_lead=None, size=None,
                  color=None, italic=False, space_after=6, align=None):
    p = doc.add_paragraph(style=style)
    p.paragraph_format.space_after = Pt(space_after)
    p.paragraph_format.line_spacing = 1.15
    if align is not None:
        p.alignment = align
    if bold_lead:
        run = p.add_run(bold_lead)
        run.bold = True
        if size:
            run.font.size = Pt(size)
        if color:
            run.font.color.rgb = color
    run = p.add_run(text)
    run.italic = italic
    if size:
        run.font.size = Pt(size)
    if color:
        run.font.color.rgb = color
    return p


def bullets(items, *, style='List Bullet', size=10):
    for item in items:
        p = doc.add_paragraph(style=style)
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.line_spacing = 1.1
        if isinstance(item, tuple):
            lead, rest = item
            run = p.add_run(lead)
            run.bold = True
            run.font.size = Pt(size)
            run = p.add_run(rest)
            run.font.size = Pt(size)
        else:
            run = p.add_run(item)
            run.font.size = Pt(size)


def numbered(items, *, size=10):
    bullets(items, style='List Number', size=size)


def h1(number, title):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(10)
    p.paragraph_format.keep_with_next = True
    run = p.add_run(f'{number}. {title}' if number else title)
    run.bold = True
    run.font.size = Pt(18)
    run.font.color.rgb = NAVY
    # filet inférieur
    p_pr = p._p.get_or_add_pPr()
    borders = OxmlElement('w:pBdr')
    bottom = OxmlElement('w:bottom')
    bottom.set(qn('w:val'), 'single')
    bottom.set(qn('w:sz'), '8')
    bottom.set(qn('w:space'), '4')
    bottom.set(qn('w:color'), 'C8A45A')
    borders.append(bottom)
    p_pr.append(borders)
    return p


def h2(number, title):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(12)
    p.paragraph_format.space_after = Pt(5)
    p.paragraph_format.keep_with_next = True
    run = p.add_run(f'{number} {title}')
    run.bold = True
    run.font.size = Pt(13.5)
    run.font.color.rgb = BLUE
    return p


def h3(title):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(9)
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.keep_with_next = True
    run = p.add_run(title)
    run.bold = True
    run.font.size = Pt(11.5)
    run.font.color.rgb = INDIGO
    return p


def callout(title, text, *, warning=False, size=9.5):
    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    cell = table.rows[0].cells[0]
    cell.width = Cm(17)
    set_cell_bg(cell, FILL_WARNING if warning else FILL_CALLOUT)
    set_cell_margins(cell, top=110, bottom=110, left=160, right=160)
    cell.text = ''
    p = cell.paragraphs[0]
    p.paragraph_format.space_after = Pt(2)
    run = p.add_run(title)
    run.bold = True
    run.font.size = Pt(10)
    run.font.color.rgb = RED if warning else NAVY
    p2 = cell.add_paragraph()
    p2.paragraph_format.space_after = Pt(0)
    run = p2.add_run(text)
    run.font.size = Pt(size)
    run.font.color.rgb = DARK
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


def code_block(lines):
    table = doc.add_table(rows=1, cols=1)
    table.autofit = False
    cell = table.rows[0].cells[0]
    cell.width = Cm(17)
    set_cell_bg(cell, 'F4F5FA')
    set_cell_margins(cell, top=100, bottom=100, left=140, right=140)
    cell.text = ''
    for index, line in enumerate(lines):
        p = cell.paragraphs[0] if index == 0 else cell.add_paragraph()
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.line_spacing = 1.0
        run = p.add_run(line)
        run.font.name = 'Consolas'
        run.font.size = Pt(8.5)
        run.font.color.rgb = DARK
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


def page_break():
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


def add_field(paragraph, instruction, *, size=8.5):
    run = paragraph.add_run()
    begin = OxmlElement('w:fldChar')
    begin.set(qn('w:fldCharType'), 'begin')
    instr = OxmlElement('w:instrText')
    instr.set(qn('xml:space'), 'preserve')
    instr.text = instruction
    sep = OxmlElement('w:fldChar')
    sep.set(qn('w:fldCharType'), 'separate')
    text = OxmlElement('w:t')
    text.text = '1'
    end = OxmlElement('w:fldChar')
    end.set(qn('w:fldCharType'), 'end')
    run._r.append(begin)
    run._r.append(instr)
    run._r.append(sep)
    run._r.append(text)
    run._r.append(end)
    run.font.size = Pt(size)


def footer_page_number(section):
    footer = section.footer
    p = footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run('Univers Academy — Architecture métier  ·  page ')
    run.font.size = Pt(8)
    run.font.color.rgb = GREY
    add_field(p, 'PAGE')
    run = p.add_run(' sur ')
    run.font.size = Pt(8)
    run.font.color.rgb = GREY
    add_field(p, 'NUMPAGES')


def header_text(section):
    header = section.header
    p = header.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = p.add_run('Document d’architecture métier — version 1.0')
    run.font.size = Pt(8)
    run.font.color.rgb = GREY


# ===========================================================================
# Données de référence
# ===========================================================================

DOMAINS = [
    ('Identité et accès', 'Comptes, rôles, permissions, demandes d’accès',
     ['User', 'Role', 'Permission', 'UserRole', 'RolePermission',
      'AccessRequest', 'Notification']),
    ('Admissions et accueil', 'Visites, contacts, prospects, suivi commercial',
     ['Contact', 'Visit', 'VisitReason', 'Prospect', 'ProspectFollowUp',
      'AccessEvent']),
    ('Scolarité', 'Dossiers étudiants, inscriptions, documents',
     ['Enrollment', 'StudentDocument', 'Certificate']),
    ('Pédagogie', 'Formations, groupes, programme, séances, ressources',
     ['Course', 'CourseSession', 'Module', 'Lesson', 'SessionRecord',
      'Resource', 'ResourceFeedback']),
    ('Assiduité et fiches de cours', 'Présences et fiches papier numérisées',
     ['Attendance', 'StudentSessionNote']),
    ('Finances', 'Paiements, caisses, opérations, clôtures',
     ['Payment', 'CashAccount', 'TransactionCategory', 'CashTransaction',
      'CashClosure', 'Expense']),
    ('Bourses', 'Candidatures et pièces justificatives',
     ['Destination', 'ScholarshipApplication', 'ScholarshipDocument']),
    ('Supervision et audit', 'Traçabilité et contrôle de gestion',
     ['AuditLog']),
]

MODEL_DESCRIPTIONS = {
    'User': 'Compte utilisateur (authentification locale ou Clerk), statut '
            'd’accès, code interne, profil et rôles.',
    'Role': 'Rôle métier (neuf valeurs) porteur de permissions.',
    'Permission': 'Permission applicative atomique (19 clés).',
    'UserRole': 'Attribution d’un rôle à un utilisateur, avec auteur et date.',
    'RolePermission': 'Association rôle ↔ permission.',
    'AccessRequest': 'Demande d’accès avec rôle souhaité, décision et trace.',
    'Notification': 'Notification interne adressée à un utilisateur.',
    'Contact': 'Personne physique contactée (visiteur, prospect, parent).',
    'Visit': 'Visite enregistrée à l’accueil, de l’arrivée au départ.',
    'VisitReason': 'Motif de visite paramétrable.',
    'Prospect': 'Personne intéressée par une formation, avant inscription.',
    'ProspectFollowUp': 'Relance ou échange tracé avec un prospect.',
    'AccessEvent': 'Entrée ou sortie d’une personne dans l’établissement.',
    'Enrollment': 'Inscription d’un étudiant à un groupe de formation, avec '
                  'tarif, remise, montant net et statut.',
    'StudentDocument': 'Pièce du dossier étudiant stockée en privé.',
    'Certificate': 'Certificat de fin de formation, numéroté.',
    'Course': 'Formation cataloguée (domaine, durée, tarif).',
    'CourseSession': 'Groupe/classe planifié pour une formation, avec '
                     'formateurs affectés et capacité.',
    'Module': 'Module pédagogique d’une formation.',
    'Lesson': 'Leçon d’un module.',
    'SessionRecord': 'Séance réalisée ou planifiée : compte rendu, cahier de '
                     'texte, heures, effectif et observations.',
    'Resource': 'Support de cours, exercice, devoir ou ressource, fichier ou '
                'HTML, brouillon/publié/archivé.',
    'ResourceFeedback': 'Note et commentaire d’un étudiant sur une ressource.',
    'Attendance': 'Présence d’un étudiant à une date donnée.',
    'StudentSessionNote': 'Fiche de cours remplie par l’étudiant après une '
                          'séance : présence, heures suivies, notions, '
                          'difficultés, observations.',
    'Payment': 'Paiement étudiant rattaché à une inscription et à une '
               'opération de caisse validée.',
    'CashAccount': 'Caisse, compte Mobile Money ou compte bancaire.',
    'TransactionCategory': 'Catégorie d’entrée, de sortie ou de transfert.',
    'CashTransaction': 'Mouvement de caisse (entrée, sortie, transfert) avec '
                       'statut brouillon/validé/annulé.',
    'CashClosure': 'Clôture journalière d’une caisse avec écart constaté.',
    'Expense': 'Dépense héritée, conservée pour l’historique ; n’alimente '
               'plus les indicateurs.',
    'Destination': 'Pays ou destination de bourse.',
    'ScholarshipApplication': 'Candidature à une bourse, avec suivi et jeton '
                              'de consultation.',
    'ScholarshipDocument': 'Pièce jointe à une candidature de bourse.',
    'AuditLog': 'Journal d’audit append-only : acteur, action, entité, '
                'valeurs avant/après, IP, horodatage.',
}

FIELD_TYPE_LABELS = {
    'CharField': 'Texte',
    'TextField': 'Texte long',
    'UUIDField': 'UUID',
    'DateField': 'Date',
    'DateTimeField': 'Date et heure',
    'TimeField': 'Heure',
    'BooleanField': 'Booléen',
    'IntegerField': 'Entier',
    'PositiveIntegerField': 'Entier ≥ 0',
    'PositiveSmallIntegerField': 'Entier ≥ 0',
    'BigIntegerField': 'Entier long',
    'DecimalField': 'Décimal',
    'JSONField': 'JSON',
    'FileField': 'Fichier',
    'ImageField': 'Image',
    'EmailField': 'E-mail',
    'GenericIPAddressField': 'Adresse IP',
    'ForeignKey': 'Référence',
    'OneToOneField': 'Référence 1–1',
    'ManyToManyField': 'Référence N–N',
}


def field_rows(model):
    rows = []
    fields = list(model._meta.fields) + list(model._meta.many_to_many)
    for field in fields:
        internal = field.get_internal_type()
        if field.is_relation and field.related_model is not None:
            kind = f'{FIELD_TYPE_LABELS.get(internal, internal)} → ' \
                   f'{field.related_model.__name__}'
        else:
            kind = FIELD_TYPE_LABELS.get(internal, internal)
        flags = []
        if getattr(field, 'null', False):
            flags.append('facultatif')
        if getattr(field, 'blank', False):
            flags.append('vide autorisé')
        if getattr(field, 'unique', False):
            flags.append('unique')
        if getattr(field, 'choices', None):
            values = ' / '.join(str(choice[0]) for choice in field.choices)
            flags.append(f'valeurs : {values}')
        label = str(getattr(field, 'verbose_name', field.name))
        rows.append([field.name, kind, label, ', '.join(flags) or '—'])
    return rows


AUDIT_ACTIONS = [
    ('REGISTER', 'Identité', 'Création d’un compte local.'),
    ('REGISTER_CLERK', 'Identité', 'Création d’un compte à la première '
     'connexion Clerk.'),
    ('LOGIN', 'Identité', 'Connexion réussie.'),
    ('LOGIN_CLERK', 'Identité', 'Connexion via Clerk.'),
    ('LOGOUT', 'Identité', 'Déconnexion.'),
    ('ACCESS_REQUEST_SUBMIT', 'Identité', 'Dépôt d’une demande d’accès.'),
    ('ACCESS_APPROVE', 'Identité', 'Approbation d’une demande et attribution du rôle.'),
    ('ACCESS_REJECT', 'Identité', 'Refus d’une demande d’accès.'),
    ('USER_CREATE', 'Identité', 'Création d’un compte par le super administrateur.'),
    ('USER_EDIT', 'Identité', 'Modification d’un compte.'),
    ('USER_STATUS_CHANGE', 'Identité', 'Changement du statut d’accès.'),
    ('ROLE_ASSIGN', 'Identité', 'Attribution d’un rôle.'),
    ('ROLE_REMOVE', 'Identité', 'Retrait d’un rôle.'),
    ('PROFILE_UPDATE', 'Identité', 'Mise à jour du profil.'),
    ('PROFILE_EMAIL_REQUEST', 'Identité', 'Demande de changement d’e-mail.'),
    ('PROFILE_EMAIL_CONFIRM', 'Identité', 'Confirmation du changement d’e-mail.'),
    ('PROFILE_AVATAR', 'Identité', 'Photo de profil enregistrée — par '
     'l’intéressé, le secrétariat ou le SUPER_ADMIN ; l’acteur et la personne '
     'concernée sont journalisés.'),
    ('PROFILE_AVATAR_DELETE', 'Identité', 'Photo de profil retirée, avatar par '
     'défaut (initiales) rétabli.'),
    ('PROFILE_PASSWORD', 'Identité', 'Mot de passe changé par l’intéressé ; '
     'seule la présence d’un mot de passe avant/après est journalisée, jamais la '
     'valeur.'),
    ('VISIT_CREATE', 'Accueil', 'Enregistrement d’une visite.'),
    ('VISIT_UPDATE', 'Accueil', 'Modification d’une visite.'),
    ('VISIT_DEPARTURE', 'Accueil', 'Enregistrement du départ.'),
    ('VISIT_REASON_TOGGLE', 'Accueil', 'Activation/désactivation d’un motif.'),
    ('VISIT_REASON_CREATE', 'Accueil', 'Création d’un motif de visite.'),
    ('ACCESS_EVENT', 'Accueil', 'Entrée ou sortie d’une personne.'),
    ('PROSPECT_CREATE', 'Accueil', 'Création d’un prospect.'),
    ('PROSPECT_UPDATE', 'Accueil', 'Modification d’un prospect.'),
    ('PROSPECT_FOLLOW_UP', 'Accueil', 'Relance d’un prospect.'),
    ('PROSPECT_FROM_VISIT', 'Accueil', 'Conversion d’une visite en prospect.'),
    ('STUDENT_CREATE', 'Scolarité', 'Création d’un étudiant et de son inscription.'),
    ('STUDENT_EDIT', 'Scolarité', 'Modification d’un dossier étudiant.'),
    ('STUDENT_DOCUMENT_UPLOAD', 'Scolarité', 'Dépôt d’une pièce du dossier.'),
    ('ENROLLMENT_CREATE', 'Scolarité', 'Création d’une inscription.'),
    ('ENROLLMENT_EDIT', 'Scolarité', 'Modification d’une inscription.'),
    ('ENROLLMENT_VALIDATE', 'Scolarité',
     'Validation par la direction d’une inscription créée au guichet.'),
    ('COURSE_SESSION_CREATE', 'Pédagogie', 'Création d’un groupe de formation.'),
    ('COURSE_SESSION_EDIT', 'Pédagogie', 'Modification d’un groupe.'),
    ('MODULE_CREATE', 'Pédagogie', 'Création d’un module.'),
    ('MODULE_EDIT', 'Pédagogie', 'Modification d’un module.'),
    ('LESSON_CREATE', 'Pédagogie', 'Création d’une leçon.'),
    ('LESSON_EDIT', 'Pédagogie', 'Modification d’une leçon.'),
    ('SESSION_CREATE', 'Pédagogie', 'Création d’une séance ou d’une ligne de cahier de texte.'),
    ('SESSION_UPDATE', 'Pédagogie', 'Modification d’une séance.'),
    ('ATTENDANCE_RECORD', 'Pédagogie', 'Pointage des présences.'),
    ('RESOURCE_FEEDBACK', 'Pédagogie', 'Retour d’un étudiant sur une ressource.'),
    ('RESOURCE_CREATE', 'Pédagogie', 'Dépôt d’une ressource pédagogique.'),
    ('RESOURCE_EDIT', 'Pédagogie', 'Modification d’une ressource.'),
    ('STUDENT_NOTE_CREATE', 'Pédagogie', 'Création d’une fiche de cours étudiant.'),
    ('STUDENT_NOTE_UPDATE', 'Pédagogie', 'Modification d’une fiche de cours étudiant.'),
    ('PAYMENT_CREATE', 'Finances', 'Encaissement d’un paiement étudiant.'),
    ('PAYMENT_RECEIPT', 'Finances', 'Consultation ou impression d’un reçu.'),
    ('CASH_TRANSACTION_CREATE', 'Finances', 'Création d’une opération de caisse.'),
    ('CASH_TRANSACTION_CANCEL', 'Finances', 'Annulation d’une opération.'),
    ('CASH_TRANSACTION_EDIT', 'Finances',
     'Correction d’une écriture enregistrée, motif à l’appui.'),
    ('CASH_CLOSURE', 'Finances', 'Clôture d’une caisse.'),
    ('CASH_ACCOUNT_CREATE', 'Finances', 'Création d’une caisse ou d’un compte.'),
    ('CASH_ACCOUNT_EDIT', 'Finances',
     'Administration d’un compte : état, découvert, compte de remplacement.'),
    ('TRANSACTION_CATEGORY_CREATE', 'Finances',
     'Création d’une catégorie d’écriture.'),
    ('TRANSACTION_CATEGORY_EDIT', 'Finances',
     'Renommage ou activation/désactivation d’une catégorie.'),
    ('JOURNAL_EXPORT', 'Finances', 'Export CSV du journal de caisse.'),
    ('FINANCE_EXPORT', 'Finances', 'Export CSV de la supervision financière.'),
    ('SCHOLARSHIP_SUBMIT', 'Bourses', 'Dépôt d’une candidature.'),
    ('SCHOLARSHIP_REVIEW', 'Bourses', 'Décision sur une candidature.'),
    ('FILE_ACCESS', 'Sécurité', 'Téléchargement contrôlé d’un fichier privé.'),
    ('UNAUTHORIZED_FILE_ACCESS', 'Sécurité', 'Tentative d’accès non autorisée à un fichier.'),
]

# Le catalogue des droits et la matrice par défaut viennent de l’application :
# la note d’architecture ne peut plus décrire des droits qui n’existent plus.
from core.management.commands.seed_roles import (  # noqa: E402
    PERMISSIONS as PERMISSIONS_KEYS, ROLE_PERMISSIONS,
)

PERMISSIONS = [(cle, str(libelle).replace("'", "’"))
               for cle, libelle in PERMISSIONS_KEYS]

ROLE_INFO = [
    ('SUPER_ADMIN', 'Super Administrateur', 'UA-ADM',
     'Administration complète : comptes, rôles, accès, audit, supervision '
     'financière et décisions de bourse. Lecture totale du métier, sans '
     'écriture opérationnelle.'),
    ('ADMIN', 'Administrateur', 'UA-ADM',
     'Accès transversal en lecture à tous les modules, revue des demandes '
     'd’accès, supervision. Ne peut ni créer/modifier un compte, ni attribuer '
     'un rôle, ni écrire dans le métier.'),
    ('DIRECTION', 'Direction', 'UA-DIR',
     'Pilotage : lecture des dossiers, formations, présences et finances ; '
     'écriture pédagogique (modules, leçons, groupes) et encaissements.'),
    ('SECRETAIRE', 'Secrétaire', 'UA-SEC',
     'Admissions, dossiers étudiants, inscriptions, documents, consultation '
     'des séances et présences, saisie des paiements étudiants.'),
    ('ASSISTANT_ADMIN', 'Assistant administratif', 'UA-ASY',
     'Le poste qui reprend l’accueil et la caisse : visites, contacts, '
     'prospects, journal des entrées/sorties, inscriptions au guichet, '
     'encaissements, reçus, clôtures.'),
    ('RESP_PEDA', 'Responsable pédagogique', 'UA-RPD',
     'Programme, groupes, séances, présences, ressources, certificats, '
     'encaissements.'),
    ('FORMATEUR', 'Formateur', 'UA-FRM',
     'Ses groupes et séances : cahier de texte, présences, ressources, '
     'consultation des fiches de ses apprenants.'),
    ('ETUDIANT', 'Étudiant', 'UA-ETU',
     'Ses ressources, ses présences, ses fiches de cours et sa feuille de '
     'suivi. Aucun accès aux autres parcours.'),
]

GLOSSARY = [
    ('Année / période', 'Bornes du groupe de formation (`starts_at`, `ends_at`).'),
    ('Cahier de texte', 'Ligne de séance renseignée par le formateur : date, '
                        'heures, notions, effectif, observations.'),
    ('Caisse', 'Compte de trésorerie : espèces, Mobile Money ou banque.'),
    ('Clôture', 'Contrôle journalier du solde théorique et du montant compté.'),
    ('Code interne', 'Identifiant lisible attribué selon le rôle (UA-ETU-0001…).'),
    ('Demande d’accès', 'Souhait de rôle exprimé par un compte en attente.'),
    ('Écriture métier', 'Création ou modification d’une donnée opérationnelle.'),
    ('Fiche de cours', 'Fiche étudiant remplie après une séance.'),
    ('Groupe / classe', '`CourseSession` : formation planifiée avec formateurs.'),
    ('Inscription', 'Lien entre un étudiant et un groupe, avec montant net.'),
    ('Montant net', 'Frais de formation moins la remise accordée.'),
    ('Reste à payer', 'Montant net moins les paiements validés, jamais négatif.'),
    ('Rôle élevé', 'SUPER_ADMIN ou ADMIN : lecture transversale, écriture métier refusée.'),
    ('Séance', '`SessionRecord` : occurrence datée d’un groupe.'),
    ('Statut d’accès', 'PENDING_APPROVAL, ACTIVE, SUSPENDED, DISABLED, REJECTED.'),
    ('Transfert', 'Mouvement neutre entre deux caisses de l’établissement.'),
    ('Trop-perçu', 'Paiements validés supérieurs au montant net d’un dossier.'),
    ('Unité monétaire', 'Franc CFA (XAF), montants entiers.'),
]

# ===========================================================================
# Document
# ===========================================================================

doc = Document()

# Styles de base
normal = doc.styles['Normal']
normal.font.name = 'Calibri'
normal.font.size = Pt(10.5)
normal.font.color.rgb = DARK
normal.paragraph_format.space_after = Pt(6)
normal.paragraph_format.line_spacing = 1.15

for style_name in ('List Bullet', 'List Number'):
    style = doc.styles[style_name]
    style.font.name = 'Calibri'
    style.font.size = Pt(10)

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

header_text(section)
footer_page_number(section)

# ---------------------------------------------------------------------------
# Page de garde
# ---------------------------------------------------------------------------
band = doc.add_table(rows=1, cols=1)
band.autofit = False
band_cell = band.rows[0].cells[0]
band_cell.width = Cm(17)
set_cell_bg(band_cell, '1E3A5F')
set_cell_margins(band_cell, top=260, bottom=260, left=260, right=260)
band_cell.text = ''
p = band_cell.paragraphs[0]
p.paragraph_format.space_after = Pt(2)
run = p.add_run('UNIVERS ACADEMY')
run.bold = True
run.font.size = Pt(13)
run.font.color.rgb = RGBColor(0xC8, 0xA4, 0x5A)
p = band_cell.add_paragraph()
run = p.add_run('Brazzaville — République du Congo')
run.font.size = Pt(10)
run.font.color.rgb = WHITE

doc.add_paragraph().paragraph_format.space_after = Pt(40)
p = doc.add_paragraph()
run = p.add_run('Architecture métier')
run.bold = True
run.font.size = Pt(34)
run.font.color.rgb = NAVY
p = doc.add_paragraph()
run = p.add_run('Plateforme de gestion académique, pédagogique, '
                'administrative et financière')
run.font.size = Pt(15)
run.font.color.rgb = GREY

doc.add_paragraph().paragraph_format.space_after = Pt(26)
p = doc.add_paragraph()
run = p.add_run('Document de référence — version 1.0')
run.bold = True
run.font.size = Pt(11)
run.font.color.rgb = INDIGO
p = doc.add_paragraph()
run = p.add_run(TODAY)
run.font.size = Pt(10.5)
run.font.color.rgb = GREY

doc.add_paragraph().paragraph_format.space_after = Pt(30)
meta_rows = [
    ['Objet', 'Description complète de l’architecture métier, des acteurs, '
              'des processus, des règles et des contrôles.'],
    ['Périmètre', 'Application Django `core` : identité, admissions, '
                  'scolarité, pédagogie, assiduité, finances, bourses, '
                  'supervision.'],
    ['Public', 'Direction, administration, responsables pédagogiques, '
               'comptabilité, équipe informatique.'],
    ['Statut', 'Version validée techniquement — tests automatisés au vert.'],
    ['Base de référence', 'Code source du projet, migrations `0001` à `0009`, '
                          'base de développement SQLite.'],
]
add_table(['Rubrique', 'Contenu'], meta_rows, widths=[4, 13], size=9.5,
          header_size=9.5, zebra=True, first_col_bold=True)

doc.add_paragraph().paragraph_format.space_after = Pt(8)
callout(
    'Avertissement de lecture',
    'Ce document décrit le fonctionnement réellement implémenté et testé. '
    'Les fonctions annoncées mais non terminées sont regroupées au chapitre '
    '14 « Limites connues et feuille de route » et ne doivent pas être '
    'considérées comme livrées.',
)

page_break()

# ---------------------------------------------------------------------------
# Sommaire
# ---------------------------------------------------------------------------
h1('', 'Sommaire')
sommaire = [
    ('1', 'Synthèse exécutive'),
    ('2', 'Contexte, périmètre et principes directeurs'),
    ('3', 'Vue d’ensemble et architecture technique'),
    ('4', 'Cartographie des domaines métier'),
    ('5', 'Modèle de domaine'),
    ('6', 'Acteurs, rôles et habilitations'),
    ('7', 'Processus métier'),
    ('8', 'Règles de gestion'),
    ('9', 'Sécurité et contrôle d’accès'),
    ('10', 'Traçabilité et audit'),
    ('11', 'Parcours, interfaces et routes'),
    ('12', 'Architecture applicative et conventions'),
    ('13', 'Qualité, tests et exploitation'),
    ('14', 'Limites connues et feuille de route'),
    ('A', 'Annexe A — Glossaire'),
    ('B', 'Annexe B — Catalogue des routes'),
    ('C', 'Annexe C — Catalogue des actions d’audit'),
    ('D', 'Annexe D — Modèle de données détaillé'),
    ('E', 'Annexe E — Correspondance fiches papier / écrans'),
    ('F', 'Annexe F — Références et fichiers sources'),
]
for number, label in sommaire:
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.left_indent = Cm(0.4)
    run = p.add_run(f'{number}.  ')
    run.bold = True
    run.font.color.rgb = INDIGO
    run = p.add_run(label)
    run.font.size = Pt(10.5)

add_paragraph(
    'Le sommaire présente les chapitres dans l’ordre de lecture. Les tableaux '
    'de l’annexe D sont générés automatiquement à partir des modèles Django : '
    'ils reflètent l’état du code au moment de la production du document.',
    italic=True, size=9.5, color=GREY,
)

page_break()

# ===========================================================================
# 1. Synthèse exécutive
# ===========================================================================
h1('1', 'Synthèse exécutive')

add_paragraph(
    'Univers Academy est une plateforme de gestion d’établissement de '
    'formation qui couvre l’ensemble du cycle de vie d’un apprenant, depuis '
    'le premier contact à l’accueil jusqu’à la délivrance du certificat, en '
    'passant par l’admission, l’inscription, le suivi pédagogique, '
    'l’assiduité, les fiches de cours et la comptabilité.'
)

add_paragraph(
    'Le système poursuit un objectif simple : remplacer la dispersion des '
    'registres papier et des tableurs par une source unique, consultable par '
    'les bonnes personnes, avec une trace de chaque opération sensible. Il ne '
    'cherche pas à imposer un nouveau logiciel de gestion : il prolonge les '
    'pratiques existantes (fiches papier, cahier de texte, reçus) en les '
    'rendant consultables, imprimables et contrôlables.'
)

h2('1.1', 'Ce que couvre la plateforme')
add_table(
    ['Domaine', 'Réponse apportée'],
    [
        ['Identité et accès', 'Comptes approuvés par un humain, rôles '
         'multiples, permissions, code interne, Clerk ou mot de passe local.'],
        ['Admissions et accueil', 'Visites, contacts, prospects, relances et '
         'conversion en étudiant.'],
        ['Scolarité', 'Dossier étudiant, inscriptions, tarifs, remises, '
         'documents, certificats.'],
        ['Pédagogie', 'Formations, groupes, modules, leçons, séances, '
         'cahier de texte, ressources.'],
        ['Assiduité', 'Feuille de présence par séance et fiche de cours '
         'étudiant après chaque séance.'],
        ['Finances', 'Paiements, caisses, transferts, clôtures, reçus, '
         'supervision et contrôles de cohérence.'],
        ['Bourses', 'Candidature publique, pièces jointes, instruction et '
         'décision.'],
        ['Supervision', 'Journal d’audit, indicateurs consolidés, exports, '
         'rapports de contrôle.'],
    ],
    widths=[4.2, 12.8], size=9.5, header_size=9.5, first_col_bold=True,
)

h2('1.2', 'Cinq principes structurants')
numbered([
    ('Séparation lecture / écriture. ', 'Les rôles transversaux '
     '(SUPER_ADMIN, ADMIN) voient tout mais n’écrivent pas dans le métier — '
     'la caisse exceptée, que la direction leur a ouverte en écriture. Les '
     'actes d’administration des comptes restent réservés au SUPER_ADMIN.'),
    ('Une seule vérité financière. ', 'Tout encaissement crée, dans la même '
     'transaction, un `Payment` et une `CashTransaction` validée. Les '
     'indicateurs ne lisent que les opérations validées.'),
    ('Traçabilité systématique. ', 'Chaque création, modification, décision '
     'ou export sensible écrit une entrée dans `AuditLog`, avec acteur, '
     'valeurs avant/après et horodatage.'),
    ('Validation côté serveur. ', 'Les contrôles ne reposent jamais sur '
     'l’interface : rôles, appartenance, montants, dates et doublons sont '
     'revérifiés dans la vue et le formulaire.'),
    ('Admission humaine. ', 'Aucune inscription ne donne de rôle '
     'automatiquement : une demande d’accès doit être approuvée, et un '
     'étudiant doit être rattaché à un groupe.'),
])

h2('1.3', 'Chiffres clés')
add_table(
    ['Indicateur', 'Valeur', 'Commentaire'],
    [
        ['Domaines métier', '8', 'Identité, accueil, scolarité, pédagogie, '
         'assiduité, finances, bourses, supervision.'],
        ['Rôles', '9', 'Dont 2 rôles transversaux et 7 rôles opérationnels.'],
        ['Permissions atomiques', '19', 'Catalogue `seed_roles`.'],
        ['Modèles de données', str(len(MODELS)),
         'Tous rattachés à l’application `core`.'],
        ['Migrations', '14', '`0001` à `0014`, additives — aucune colonne, '
         'aucune ligne supprimée.'],
        ['Tests automatisés', '519', 'Base de test isolée, aucun accès à la '
         'base réelle.'],
        ['Statut technique', 'OK', '`check` sans erreur ; `makemigrations '
         '--check` ne signale aucun changement en attente (14 migrations '
         'appliquées).'],
    ],
    widths=[4.5, 3, 9.5], size=9.5, header_size=9.5, first_col_bold=True,
    align_center={1},
)

page_break()

# ===========================================================================
# 2. Contexte et principes
# ===========================================================================
h1('2', 'Contexte, périmètre et principes directeurs')

h2('2.1', 'Contexte')
add_paragraph(
    'Univers Academy est un établissement de formation situé à Brazzaville. '
    'Son activité combine des formations diplômantes ou certifiantes, des '
    'groupes planifiés, des formateurs vacataires, un accueil physique, un '
    'secrétariat, une comptabilité de caisse et un dispositif de bourses.'
)
add_paragraph(
    'Avant la plateforme, les informations étaient réparties entre registres '
    'de visite, fiches d’inscription, cahiers de texte, feuilles de présence, '
    'reçus manuscrits et tableurs de trésorerie. Cette organisation rendait '
    'difficile la réponse à des questions simples : qui est inscrit, quel '
    'formateur a assuré quelle séance, combien reste-t-il à recouvrer, qui a '
    'modifié un montant, où est la fiche de cours d’un étudiant ?'
)

h2('2.2', 'Objectifs')
bullets([
    ('Centraliser. ', 'Un dossier unique par étudiant, une inscription par '
     'groupe, une trace par opération.'),
    ('Sécuriser. ', 'Des accès différenciés, vérifiés côté serveur, et un '
     'journal d’audit exploitable.'),
    ('Piloter. ', 'Des tableaux de bord par rôle et des indicateurs calculés '
     'sur les données réelles.'),
    ('Respecter l’existant. ', 'Conserver les pages, les parcours et les '
     'fiches papier, en les numérisant sans les réinventer.'),
    ('Rester maintenable. ', 'Un modèle additif, des vues découpées par '
     'domaine, des migrations traçables.'),
])

h2('2.3', 'Périmètre fonctionnel')
add_table(
    ['Inclus', 'Exclu ou partiel'],
    [
        ['Comptes, rôles, demandes d’accès et audit.',
         'Paiement en ligne et passerelle bancaire.'],
        ['Visites, prospects, inscriptions et dossiers étudiants.',
         'Gestion de la paie complète et des contrats de travail.'],
        ['Groupes, séances, cahier de texte, présences, fiches de cours.',
         'Visio, classes virtuelles et messagerie instantanée.'],
        ['Paiements, caisses, transferts, clôtures et reçus imprimables.',
         'Comptabilité générale normée (plan comptable, grand livre).'],
        ['Ressources pédagogiques et retours étudiants.',
         'Application mobile native.'],
        ['Candidatures de bourse et instruction.',
         'Connexion directe aux universités partenaires.'],
        ['Supervision financière, exports CSV et contrôles de cohérence.',
         'Décision automatisée d’octroi de bourse.'],
    ],
    widths=[9, 8], size=9.5, header_size=9.5,
)

h2('2.4', 'Principes directeurs détaillés')
h3('Principe 1 — Le rôle ne se déduit jamais d’une inscription')
add_paragraph(
    'L’inscription publique crée un compte `PENDING_APPROVAL` sans aucun '
    '`UserRole`. Le rôle souhaité est enregistré dans `AccessRequest` mais '
    'n’est pas attribué. Seule une décision humaine (SUPER_ADMIN ou ADMIN) '
    'attribue un rôle, dans la limite des rôles demandables. Les métadonnées '
    'Clerk ne sont jamais lues pour accorder un privilège.'
)
h3('Principe 2 — L’écriture métier appartient aux rôles opérationnels')
add_paragraph(
    'Le décorateur `business_write_required` refuse les rôles élevés sur les '
    'écritures opérationnelles. Deux exceptions, toutes deux voulues par la '
    'direction : la modification d’une inscription existante reste ouverte aux '
    'rôles élevés, car elle relève de la correction administrative, et la '
    'caisse tout entière leur est ouverte en écriture (`cash_write_required`) '
    '— le super administrateur et l’administrateur peuvent encaisser, saisir, '
    'corriger, annuler, ajuster et archiver eux-mêmes, chaque geste restant '
    'journalisé.'
)
h3('Principe 3 — Le montant affiché doit être reconstructible')
add_paragraph(
    'Le reste à payer n’est jamais stocké : il est recalculé à partir du '
    'montant net et des paiements validés. Le solde d’une caisse est reconstruit '
    'à partir du solde d’ouverture et des mouvements validés. Cette règle évite '
    'les écarts entre plusieurs écrans.'
)
h3('Principe 4 — Une opération sensible est atomique')
add_paragraph(
    'Un encaissement, une conversion de prospect ou une approbation de compte '
    's’exécutent dans une transaction de base de données. Si une étape échoue, '
    'aucune écriture partielle ne subsiste.'
)
h3('Principe 5 — Une règle métier ne vit qu’à un seul endroit, côté serveur')
add_paragraph(
    'Les règles qui décident de l’argent sont descendues dans le modèle et dans '
    'le service `core/caisse.py`, jamais répétées dans les vues : `juger` rend '
    'le verdict de solde, `sortie_prevue` dit ce qu’une écriture en projet '
    'débite, `avertissement` choisit le mot à montrer. L’écran appelle ces '
    'fonctions plutôt que de recalculer : une requête envoyée directement à '
    'l’API rencontre le même refus, avec le même chiffre.'
)

page_break()

# ===========================================================================
# 3. Architecture technique
# ===========================================================================
h1('3', 'Vue d’ensemble et architecture technique')

h2('3.1', 'Architecture applicative')
add_table(
    ['Couche', 'Technologie', 'Rôle'],
    [
        ['Présentation', 'Django Templates, Tailwind CSS compilé, JavaScript '
         'léger', 'Pages publiques, tableaux de bord, formulaires, fiches '
         'imprimables.'],
        ['Application', 'Python 3, Django 5.1.15', 'Routage, vues, '
         'formulaires, règles métier, permissions.'],
        ['Persistance', 'SQLite en développement ; PostgreSQL visé en '
         'production', 'Données métier, audit, sessions.'],
        ['Authentification', 'Session Django + Clerk (v6) en option',
         'Connexion locale ou Clerk, sans privilège déduit du fournisseur.'],
        ['Fichiers', 'Système de fichiers `media/` privé + vue avatar',
         'Pièces justificatives, ressources, photos de profil.'],
        ['Impression', 'HTML/CSS `@media print`', 'Cahier de texte, feuille '
         'de suivi, reçu.'],
        ['Supervision', 'Commandes de gestion', 'Audit financier, audit des '
         'privilèges, initialisation.'],
    ],
    widths=[3.5, 6, 7.5], size=9.5, header_size=9.5, first_col_bold=True,
)

h2('3.2', 'Chaîne de traitement d’une requête')
add_paragraph(
    'Chaque requête suit le même chemin, ce qui rend les contrôles '
    'prévisibles et testables :'
)
code_block([
    'Navigateur',
    '   │  requête HTTP (session, CSRF)',
    '   ▼',
    'AccountStatusMiddleware  ──► compte en attente / suspendu : redirection',
    '   ▼',
    'Décorateur de vue        ──► role_required / business_write_required',
    '   │                            / super_admin_required / active_account',
    '   ▼',
    'Vue (views*.py)          ──► lecture, filtres, garde par objet',
    '   ▼',
    'Formulaire (forms.py)    ──► validation des champs et des règles',
    '   ▼',
    'Modèles (models.py)      ──► écriture atomique, propriétés calculées',
    '   ▼',
    'AuditLog                 ──► action, acteur, avant/après, IP',
    '   ▼',
    'Template                 ──► rendu HTML ou page imprimable',
])

h2('3.3', 'Découpage du code')
add_table(
    ['Élément', 'Contenu', 'Responsabilité'],
    [
        ['`core/models.py`', '35 modèles, propriétés calculées, contraintes',
         'Source de vérité du domaine.'],
        ['`core/views.py`', 'Accueil, authentification, dashboards, '
         'utilisateurs, bourses, audit', 'Pilotage et identité.'],
        ['`core/views_accueil.py`', 'Visites, contacts, prospects, motifs',
         'Domaine accueil.'],
        ['`core/views_secretariat.py`', 'Étudiants, inscriptions, documents',
         'Domaine scolarité.'],
        ['`core/views_pedagogie.py`', 'Programme, groupes, séances, '
         'cahier de texte, ressources, espace étudiant', 'Domaine pédagogie.'],
        ['`core/views_comptabilite.py`', 'Journal, caisses, catégories, '
         'clôtures, paiements, reçus', 'Domaine finances (écrans).'],
        ['`core/caisse.py`', 'juger, poster, annuler, ajuster, réinitialiser, '
         'corriger, avertissement, sortie_prevue',
         'Service unique d’écriture en caisse : c’est lui qui tient la garde '
         'de solde, pas les vues.'],
        ['`core/views_supervision.py`', 'Supervision financière', 'Contrôle '
         'de gestion.'],
        ['`core/views_profile.py`', 'Profil, avatar, e-mail signé', 'Identité '
         'personnelle.'],
        ['`core/forms.py`', 'Formulaires et validation', 'Règles de saisie.'],
        ['`core/decorators.py`', 'Contrôles d’accès', 'Autorisation.'],
        ['`core/utils.py`', 'Audit, soldes, helpers', 'Services transverses.'],
        ['`core/urls.py`', 'Routes publiques et tableau de bord', 'Navigation.'],
        ['`templates/`', 'Pages publiques et dashboards par rôle', 'Présentation.'],
        ['`core/management/commands/`', '5 commandes', 'Exploitation.'],
    ],
    widths=[4.6, 7.4, 5], size=9, header_size=9, first_col_bold=True,
)

h2('3.4', 'Modèle de déploiement')
add_paragraph(
    'L’application est monolithique : un serveur Django sert les pages et les '
    'fichiers autorisés. Cette simplicité est adaptée à un établissement de '
    'taille moyenne et facilite l’exploitation locale. En production, les '
    'éléments suivants doivent être externalisés ou sauvegardés : base de '
    'données, répertoire `media/`, clés Clerk et `SECRET_KEY`.'
)
add_table(
    ['Élément', 'Développement', 'Production visée'],
    [
        ['Base', '`db.sqlite3`', 'PostgreSQL avec sauvegardes quotidiennes.'],
        ['Serveur', '`runserver` avec autoreload', 'WSGI/ASGI derrière un '
         'reverse proxy HTTPS.'],
        ['Statiques', 'Servis par Django', 'Collectés puis servis par le '
         'proxy ou un CDN.'],
        ['Médias', '`media/` local', 'Stockage privé sauvegardé, accès '
         'contrôlé.'],
        ['Erreurs', '`DEBUG=True`', '`DEBUG=False`, journalisation et '
         'alertes.'],
        ['E-mail', 'Backend console/mémoire', 'SMTP authentifié.'],
    ],
    widths=[3.5, 6, 7.5], size=9.5, header_size=9.5, first_col_bold=True,
)

page_break()

# ===========================================================================
# 4. Cartographie des domaines
# ===========================================================================
h1('4', 'Cartographie des domaines métier')

add_paragraph(
    'La plateforme est organisée en huit domaines. Chaque domaine possède ses '
    'modèles, ses vues, ses routes et ses règles. Les domaines communiquent '
    'par des références explicites (clés étrangères), jamais par duplication '
    'de données.'
)

add_table(
    ['Domaine', 'Finalité', 'Modèles principaux'],
    [[name, purpose, ', '.join(models)] for name, purpose, models in DOMAINS],
    widths=[3.4, 7, 6.6], size=8.5, header_size=8.5, first_col_bold=True,
)

h2('4.1', 'Dépendances entre domaines')
code_block([
    'Identité et accès',
    '   └── porte les rôles de tous les autres domaines',
    '',
    'Admissions et accueil',
    '   └── Contact ──► Visit ──► Prospect ──► (conversion) ──► User/Enrollment',
    '',
    'Scolarité',
    '   └── Enrollment ──► Payment, Attendance, StudentSessionNote,',
    '                     StudentDocument, Certificate',
    '',
    'Pédagogie',
    '   └── Course ──► CourseSession ──► SessionRecord ──► StudentSessionNote',
    '        └── Module ──► Lesson ──► Resource ──► ResourceFeedback',
    '',
    'Finances',
    '   └── Payment ──► CashTransaction ──► CashAccount',
    '   └── CashClosure ──► CashAccount',
    '',
    'Supervision',
    '   └── AuditLog (lecture transverse, toutes entités)',
])

h2('4.2', 'Flux de valeur')
add_paragraph(
    'Le parcours principal relie six étapes : un contact est reçu à l’accueil, '
    'devient un prospect, puis un étudiant après inscription ; il est rattaché '
    'à un groupe ; il suit des séances, pointe ses présences et remplit ses '
    'fiches ; il règle ses frais ; enfin il peut recevoir un certificat. '
    'Chaque étape produit une trace et un état consultable.'
)
add_table(
    ['Étape', 'Entrée', 'Sortie', 'Responsable'],
    [
        ['Accueil', 'Personne physique', 'Visite + contact', 'ASSISTANT_ADMIN'],
        ['Qualification', 'Visite ou appel', 'Prospect + relances', 'ASSISTANT_ADMIN'],
        ['Admission', 'Prospect ou candidature', 'Compte approuvé + rôle',
         'SUPER_ADMIN / ADMIN'],
        ['Inscription', 'Compte étudiant + groupe', 'Enrollment avec montant net',
         'SECRETAIRE / ASSISTANT_ADMIN'],
        ['Formation', 'Groupe + formateur', 'Séances, présences, fiches',
         'FORMATEUR / RESP_PEDA'],
        ['Encaissement', 'Enrollment + montant', 'Payment + opération de caisse',
         'droit finance.write'],
        ['Certification', 'Enrollment complété', 'Certificate', 'RESP_PEDA'],
    ],
    widths=[2.8, 5, 5.6, 3.6], size=9, header_size=9, first_col_bold=True,
)

page_break()

# ===========================================================================
# 5. Modèle de domaine
# ===========================================================================
h1('5', 'Modèle de domaine')

add_paragraph(
    'Le modèle de données comporte ' + str(len(MODELS)) + ' modèles, tous '
    'rattachés à l’application `core`. Les identifiants sont des UUID, ce qui '
    'évite l’énumération des ressources dans les URL. Les montants sont des '
    'entiers exprimés en francs CFA. Les dates et heures sont stockées '
    'séparément lorsque le métier l’exige (une séance a une date et des '
    'horaires).'
)

h2('5.1', 'Vue relationnelle simplifiée')
code_block([
    'User 1 ─── N UserRole N ─── 1 Role 1 ─── N RolePermission N ─── 1 Permission',
    'User 1 ─── N AccessRequest',
    'User 1 ─── N Enrollment N ─── 1 CourseSession N ─── 1 Course',
    'Course 1 ─── N Module 1 ─── N Lesson',
    'CourseSession 1 ─── N SessionRecord 1 ─── N Attendance',
    'SessionRecord 1 ─── N StudentSessionNote',
    'Enrollment 1 ─── N Attendance',
    'Enrollment 1 ─── N StudentSessionNote',
    'Enrollment 1 ─── N Payment 1 ─── 1 CashTransaction',
    'CashTransaction N ─── 1 CashAccount',
    'CashTransaction N ─── 1 TransactionCategory',
    'CashClosure N ─── 1 CashAccount',
    'Contact 1 ─── N Visit',
    'Contact 1 ─── N Prospect 1 ─── N ProspectFollowUp',
    'Prospect 1 ─── 0..1 User (converted_student)',
    'ScholarshipApplication 1 ─── N ScholarshipDocument',
    'User 1 ─── N Notification',
    'User 1 ─── N AuditLog (actor)',
])

h2('5.2', 'Description par domaine')

DOMAIN_DETAILS = {
    'Identité et accès': [
        ['User', 'Compte, profil, statut, code interne, Clerk, avatar.',
         'N–N Role ; 1–N AccessRequest ; 1–N AuditLog'],
        ['Role', 'Rôle métier et indicateur de privilège.',
         'N–N User ; N–N Permission'],
        ['Permission', 'Permission atomique.', 'N–N Role'],
        ['AccessRequest', 'Demande, rôle souhaité, décision, note.',
         'N–1 User ; N–1 User (reviewer)'],
        ['Notification', 'Message interne, lu/non lu, envoi éventuel.',
         'N–1 User'],
    ],
    'Admissions et accueil': [
        ['Contact', 'Identité, téléphone, e-mail, ville.',
         '1–N Visit ; 1–N Prospect'],
        ['Visit', 'Arrivée, départ, motif, service, statut.',
         'N–1 Contact ; N–1 VisitReason ; N–1 User (agent)'],
        ['VisitReason', 'Motif actif ou inactif.', '1–N Visit'],
        ['Prospect', 'Intérêt, source, statut, prochaine relance.',
         'N–1 Contact ; N–1 Course ; 1–N ProspectFollowUp'],
        ['ProspectFollowUp', 'Échange, résultat, prochaine action.',
         'N–1 Prospect ; N–1 User (agent)'],
        ['AccessEvent', 'Entrée/sortie, personne ou visiteur libre.',
         'N–1 User ; N–1 User (recorded_by)'],
    ],
    'Scolarité': [
        ['Enrollment', 'Lien étudiant–groupe, tarif, remise, net, statut.',
         'N–1 User ; N–1 CourseSession ; 1–N Payment'],
        ['StudentDocument', 'Pièce du dossier, type, fichier, taille.',
         'N–1 User ; N–1 Enrollment'],
        ['Certificate', 'Numéro, date, statut, émetteur.',
         '1–1 Enrollment'],
    ],
    'Pédagogie': [
        ['Course', 'Titre, domaine, durée, tarif, éligibilité certificat.',
         '1–N CourseSession ; 1–N Module'],
        ['CourseSession', 'Groupe, dates, horaires, capacité, statut.',
         'N–1 Course ; N–N User (formateurs) ; 1–N Enrollment'],
        ['Module', 'Titre, ordre, heures prévues.', 'N–1 Course ; 1–N Lesson'],
        ['Lesson', 'Titre, objectifs, ordre, heures.', 'N–1 Module'],
        ['SessionRecord', 'Séance : date, horaires, contenu, statut, effectif.',
         'N–1 CourseSession ; N–1 Module ; N–1 Lesson'],
        ['Resource', 'Support, exercice, devoir ; fichier ou HTML.',
         'N–1 Course ; N–1 Module/Lesson/Session'],
        ['ResourceFeedback', 'Note 1–5 et commentaire.',
         'N–1 Resource ; N–1 User (student)'],
    ],
    'Assiduité et fiches de cours': [
        ['Attendance', 'Présent, absent, retard, excusé ; motif ; heure.',
         'N–1 Enrollment ; N–1 SessionRecord'],
        ['StudentSessionNote', 'Présence déclarée, heures suivies, notions, '
         'difficultés, observations.',
         'N–1 Enrollment ; N–1 SessionRecord'],
    ],
    'Finances': [
        ['Payment', 'Montant, moyen, référence, statut, caisse liée.',
         'N–1 Enrollment ; 1–1 CashTransaction'],
        ['CashAccount', 'Caisse/banque, type, devise, solde d’ouverture, état '
         '(actif, inactif, archivé), découvert autorisé, compte de '
         'remplacement ; solde et disponible calculés, jamais stockés.',
         '1–N CashTransaction ; 1–N CashClosure ; N–1 lui-même (replaced_by)'],
        ['TransactionCategory', 'Libellé, direction (IN/OUT/TRANSFER), '
         'activée ou désactivée.',
         '1–N CashTransaction'],
        ['CashTransaction', 'Mouvement, montant, statut (validé, brouillon, '
         'annulé), nature (ordinaire, ajustement, réinitialisation), '
         'justificatif.',
         'N–1 CashAccount ; N–1 TransactionCategory'],
        ['CashClosure', 'Solde ouverture, théorique, compté, écart.',
         'N–1 CashAccount ; N–1 User (closed_by)'],
        ['Expense', 'Dépense héritée, sans effet sur les indicateurs.',
         '1–1 CashTransaction'],
    ],
    'Bourses': [
        ['Destination', 'Pays/destination active.', '1–N ScholarshipApplication'],
        ['ScholarshipApplication', 'Référence, identité, programme, statut, '
         'jeton de suivi.', 'N–1 Destination ; 1–N ScholarshipDocument'],
        ['ScholarshipDocument', 'Type, fichier, nom d’origine, MIME, taille.',
         'N–1 ScholarshipApplication'],
    ],
    'Supervision et audit': [
        ['AuditLog', 'Acteur, action, entité, avant/après, IP, date.',
         'N–1 User (actor)'],
    ],
}

for name, purpose, models in DOMAINS:
    h3(f'{name} — {purpose}')
    rows = DOMAIN_DETAILS.get(name, [])
    if rows:
        add_table(['Modèle', 'Rôle métier', 'Relations'],
                  rows, widths=[4, 8, 5], size=8.5, header_size=8.5,
                  first_col_bold=True)

h2('5.3', 'Modèles pivots en détail')
for model_name, intro in [
    ('User', 'Le compte porte l’identité, le statut d’accès et les rôles. '
             'Le statut conditionne l’accès à toute l’application.'),
    ('Enrollment', 'L’inscription est le point de convergence de la '
                   'scolarité, de la pédagogie et des finances.'),
    ('SessionRecord', 'La séance porte à la fois le compte rendu '
                      'pédagogique et la ligne du cahier de texte.'),
    ('StudentSessionNote', 'La fiche de cours est unique par couple '
                           'inscription–séance.'),
    ('Payment', 'Le paiement est toujours lié à une opération de caisse.'),
    ('CashTransaction', 'L’opération de caisse est la seule source des '
                        'indicateurs financiers.'),
    ('AuditLog', 'Le journal est append-only : aucune vue ne le modifie.'),
]:
    h3(model_name)
    add_paragraph(intro, size=9.5)
    add_table(['Champ', 'Type', 'Libellé', 'Contraintes'],
              field_rows(MODEL_BY_NAME[model_name]),
              widths=[3.4, 4.8, 4.4, 4.4], size=7.8, header_size=8)

page_break()

# ===========================================================================
# 6. Acteurs, rôles et habilitations
# ===========================================================================
h1('6', 'Acteurs, rôles et habilitations')

add_paragraph(
    'Un utilisateur peut porter plusieurs rôles. Le rôle principal détermine '
    'le tableau de bord d’arrivée ; les autres rôles élargissent les droits. '
    'Les contrôles sont cumulatifs : un rôle suffit pour ouvrir une route, '
    'mais les règles d’écriture restent vérifiées séparément.'
)

h2('6.1', 'Catalogue des rôles')
add_table(['Clé', 'Libellé', 'Code interne', 'Périmètre'],
          [[key, label, prefix, desc] for key, label, prefix, desc in ROLE_INFO],
          widths=[3, 4.2, 2.2, 7.6], size=8.6, header_size=8.6,
          first_col_bold=True)

h2('6.2', 'Permissions applicatives')
perm_rows = []
for key, desc in PERMISSIONS:
    holders = [role for role, keys in ROLE_PERMISSIONS.items() if key in keys]
    perm_rows.append([key, desc, ', '.join(holders) if holders else '—'])
add_table(['Clé', 'Description', 'Rôles porteurs'],
          perm_rows, widths=[4.6, 6.4, 6], size=8.3, header_size=8.5,
          first_col_bold=True)

add_paragraph(
    'La matrice ci-dessus est la dotation par défaut, posée par la commande '
    '`seed_roles`. Elle n’est pas figée : l’onglet « Permissions » du tableau '
    'de bord super administrateur présente un tableau à cocher, poste par poste '
    'et droit par droit, et l’enregistrement écrit dans les mêmes tables. Une '
    'case décochée ferme immédiatement l’écran correspondant, une case cochée '
    'l’ouvre — l’écran d’encaissement des paiements étudiants est désormais '
    'gardé par ce droit, non par une liste de rôles. Les deux rôles '
    'transversaux n’ont pas de case éditable : leur lecture totale est écrite '
    'dans les décorateurs, cocher leurs droits ne changerait rien.'
)

h2('6.3', 'Matrice des accès par module')
matrix_headers = ['Module', 'SUPER', 'ADMIN', 'DIR.', 'ASY.', 'SECR.',
                  'PEDA', 'FORM.', 'ÉTUD.']
matrix_rows = [
    ['Compte et profil', 'É', 'É', 'É', 'É', 'É', 'É', 'É', 'É'],
    ['Revue des demandes d’accès', 'A', 'D', '—', '—', '—', '—', '—', '—'],
    ['Utilisateurs et rôles', 'A', 'L', 'L', '—', '—', '—', '—', '—'],
    ['Matrice des permissions', 'A', '—', '—', '—', '—', '—', '—', '—'],
    ['Accueil, visites, prospects', 'L', 'L', 'L', 'É', 'L', '—', '—', '—'],
    ['Scolarité et inscriptions', 'L', 'L', 'É', 'É', 'É', 'L', 'L', '—'],
    ['Groupes et programme', 'L', 'L', 'L', 'L', 'L', 'É', 'L', '—'],
    ['Cahier de texte et présences', 'L', 'L', 'L', 'L', 'L', 'É', 'É', '—'],
    ['Ressources pédagogiques', 'L', 'L', 'L', 'L', 'L', 'É', 'É', 'L'],
    ['Fiches de cours étudiant', '—', '—', 'L', 'L', 'L', 'L', 'L', 'É'],
    ['Paiements étudiants', 'É', 'É', 'É', 'É', 'É', 'É', '—', 'L'],
    ['Journal, caisses et clôtures', 'É', 'É', 'É', 'É', '—', '—', '—', '—'],
    ['Bourses', 'A', 'L', '—', '—', '—', '—', '—', 'L'],
    ['Supervision financière', 'A', 'L', '—', '—', '—', '—', '—', '—'],
    ['Journal d’audit', 'A', 'L', '—', '—', '—', '—', '—', '—'],
]
add_table(matrix_headers, matrix_rows,
          widths=[5.6, 1.42, 1.42, 1.42, 1.42, 1.42, 1.42, 1.42, 1.42],
          size=8, header_size=7.5, align_center=set(range(1, 9)),
          first_col_bold=True)
add_paragraph(
    'Légende : A = administration (écriture de privilège), É = écriture '
    'métier, D = décision d’accès, L = lecture seule, — = aucun accès. '
    '« ASY. » est l’assistant administratif, qui tient l’accueil et la caisse. '
    '« ÉTUD. » ne voit que ses propres données ; « FORM. » ne voit que ses '
    'groupes et les fiches de ses apprenants.',
    size=8.5, color=GREY, italic=True,
)
add_paragraph(
    'La caisse fait exception à la lecture seule des rôles transversaux : '
    'SUPER_ADMIN et ADMIN encaissent, saisissent une opération, corrigent, '
    'annulent, ajustent et archivent, comme le font la direction et '
    'l’assistant administratif. Chaque geste reste journalisé. Le reste du '
    'métier (comptes, inscriptions à créer, pédagogie, accueil) leur demeure '
    'en consultation.',
    size=9,
)

h2('6.4', 'Règles d’habilitation')
bullets([
    ('Rôles transversaux. ', '`role_required` autorise toujours SUPER_ADMIN et '
     'ADMIN, ce qui garantit la lecture de tous les modules.'),
    ('Écriture métier. ', '`business_write_required` refuse explicitement les '
     'deux rôles transversaux et exige un rôle opérationnel listé.'),
    ('Caisse à part. ', '`cash_write_required` est la garde des écrans de '
     'caisse (journal, opération, annulation, correction, paiement, clôture, '
     'comptes, catégories) : elle autorise les rôles transversaux, sur '
     'décision de la direction, en plus des postes listés. Les rôles '
     'transversaux ne rencontrent donc jamais le message « Consultation '
     'seule » devant une écriture d’argent.'),
    ('Actes sensibles. ', '`super_admin_required` réserve au SUPER_ADMIN la '
     'création/modification de compte, l’attribution de rôle et le changement '
     'de statut.'),
    ('Compte actif. ', '`active_account_required` redirige un compte en '
     'attente vers `/pending-approval/` et un compte suspendu, désactivé ou '
     'rejeté vers `/access-denied/`.'),
    ('Auto-modification interdite. ', 'Nul ne peut modifier ses propres rôles '
     'ou son propre statut ; la fiche affiche un message explicite.'),
    ('Dernier super administrateur. ', 'Le retrait du rôle SUPER_ADMIN est '
     'refusé s’il ne resterait plus aucun SUPER_ADMIN actif.'),
    ('Droits exécutables. ', 'Les écrans de paiement étudiant exigent le droit '
     '`finance.write` : l’onglet « Permissions » décide donc, en pratique, qui '
     'peut encaisser. Les autres écrans restent gardés par les rôles.'),
    ('Rôles dissous. ', 'COMPTABLE et ACCUEIL ont fusionné dans ASSISTANT_ADMIN. '
     'Leurs lignes demeurent en base pour que l’audit, les paiements encaissés '
     'et les demandes passées gardent leur sens ; ils ne sont plus attribuables '
     'et n’ont plus de menu.'),
    ('Rôles demandables. ', 'Seuls ETUDIANT, FORMATEUR, SECRETAIRE, '
     'ASSISTANT_ADMIN et RESP_PEDA peuvent être demandés ou accordés à '
     'l’approbation. SUPER_ADMIN, ADMIN et DIRECTION restent hors formulaire '
     'public.'),
    ('Exception d’écriture. ', 'La modification d’une inscription existante '
     'est ouverte aux rôles élevés (correction administrative), mais la '
     'création reste réservée au secrétariat et à la direction.'),
])

h2('6.5', 'Cycle de vie d’un compte')
add_table(
    ['État', 'Origine', 'Accès', 'Transition possible'],
    [
        ['PENDING_APPROVAL', 'Inscription locale ou Clerk ; fiche étudiante '
         'du secrétariat ou import des classeurs', 'Aucun écran métier ; page '
         'd’attente. Le dossier reste lisible du personnel.',
         'ACTIVE (approbation, ou validation d’une inscription) ou REJECTED '
         '(refus)'],
        ['ACTIVE', 'Décision d’approbation', 'Selon les rôles attribués',
         'SUSPENDED, DISABLED, REJECTED'],
        ['SUSPENDED', 'Décision administrative', 'Refusé', 'ACTIVE '
         '(réactivation)'],
        ['DISABLED', 'Décision administrative', 'Refusé', 'ACTIVE '
         '(réactivation)'],
        ['REJECTED', 'Refus d’une demande', 'Refusé', 'Réexamen possible par '
         'une nouvelle demande'],
    ],
    widths=[3.4, 5, 4.2, 4.4], size=9, header_size=9, first_col_bold=True,
)

add_paragraph(
    'Le code interne est généré à la première attribution d’un rôle : '
    '`UA-ETU`, `UA-FRM`, `UA-SEC`, `UA-ASY`, `UA-RPD`, `UA-DIR` ou `UA-ADM`, '
    'suivi d’un numéro sur quatre chiffres. Il sert d’identifiant lisible au '
    'guichet et dans les échanges avec l’établissement. Les racines `UA-CPT` '
    'et `UA-ACC`, héritées des postes dissous, restent valables sur les '
    'comptes qui les portent déjà.'
)

add_paragraph(
    'Un compte étudiant est ouvert en attente d’approbation, y compris quand sa '
    'fiche vient des classeurs. L’approuver est un acte du personnel : valider '
    'son inscription, ou passer le statut à « Actif » écran « Utilisateurs ». '
    'En attente ne veut pas dire supprimé : les inscriptions, les paiements, '
    'les pièces et l’historique d’un compte non approuvé restent consultables '
    'par le secrétariat, la direction et la comptabilité ; le compte ne compte '
    'simplement pas dans les effectifs et n’est pas proposé à la caisse. Une '
    'approbation déjà accordée ne se défait ni par une relance d’import, ni par '
    'aucune commande : `manage.py mettre_en_attente` ne reprend que les fiches '
    'nées d’un classeur, sans login distribué, et une fois cette reprise faite '
    'elle ne remplace plus rien — les comptes encore actifs sont des '
    'approbations données après coup.'
)

page_break()

# ===========================================================================
# 7. Processus métier
# ===========================================================================
h1('7', 'Processus métier')

add_paragraph(
    'Les processus ci-dessous décrivent le comportement attendu et réellement '
    'implémenté. Chaque étape indique l’acteur, l’action et le contrôle '
    'associé. Les contrôles sont exécutés côté serveur, même si l’interface '
    'les rend invisibles.'
)

h2('7.1', 'Admission et demande d’accès')
add_table(
    ['#', 'Acteur', 'Action', 'Contrôle / résultat'],
    [
        ['1', 'Visiteur', 'Crée un compte local ou se connecte via Clerk.',
         'Compte `PENDING_APPROVAL`, aucun `UserRole`.'],
        ['2', 'Visiteur', 'Choisit un rôle demandé.', 'Rôle limité à la liste '
         '`REQUESTABLE_ROLES` ; enregistré dans `AccessRequest`.'],
        ['3', 'SUPER_ADMIN / ADMIN', 'Ouvre la demande et vérifie le rôle '
         'suggéré.', 'Le formulaire présélectionne le rôle demandé ; les rôles '
         'élevés ne sont pas proposés.'],
        ['4', 'Décideur', 'Approuve ou refuse.', 'Décision tracée avec auteur, '
         'date et note.'],
        ['5', 'Système', 'En cas d’approbation : attribue le rôle, active le '
         'compte, génère le code interne.', 'Transaction atomique ; '
         'notification ; audit `ACCESS_APPROVE`.'],
        ['6', 'Système', 'Si le rôle est ETUDIANT : crée l’inscription au '
         'groupe choisi.', 'Groupe obligatoire sauf inscription existante ; '
         'aucun doublon ; audit `ENROLLMENT_CREATE`.'],
        ['7', 'Système', 'En cas de refus : passe le compte en `REJECTED`.',
         'Accès bloqué ; note conservée ; audit `ACCESS_REJECT`.'],
    ],
    widths=[0.9, 3.4, 6.4, 6.3], size=8.6, header_size=8.6,
    align_center={0},
)
callout(
    'Point de vigilance',
    'Un compte étudiant sans groupe ne peut pas être approuvé. Cette règle '
    'garantit qu’un étudiant apparaît immédiatement dans les inscrits, dans '
    'le formulaire de paiement et dans les feuilles de présence.',
)

h2('7.2', 'Création administrative d’un compte')
add_table(
    ['#', 'Acteur', 'Action', 'Contrôle / résultat'],
    [
        ['1', 'SUPER_ADMIN', 'Ouvre « Créer un compte ».', 'Route protégée par '
         '`super_admin_required` ; ADMIN reçoit un 403.'],
        ['2', 'SUPER_ADMIN', 'Saisit identité, rôle et, si étudiant, le groupe.',
         'Validation du formulaire ; groupe obligatoire pour un étudiant.'],
        ['3', 'Système', 'Crée l’utilisateur, le rôle et l’inscription.',
         'Transaction atomique ; code interne généré ; audit `USER_CREATE` et '
         '`ENROLLMENT_CREATE`.'],
    ],
    widths=[0.9, 3.4, 6.4, 6.3], size=8.6, header_size=8.6,
    align_center={0},
)

h2('7.3', 'Dossier étudiant et inscription')
add_table(
    ['#', 'Acteur', 'Action', 'Contrôle / résultat'],
    [
        ['1', 'SECRETAIRE', 'Recherche ou crée l’étudiant.', 'Recherche par '
         'nom, e-mail, code interne, statut, formation.'],
        ['2', 'SECRETAIRE', 'Crée l’inscription : groupe, tarif, remise.',
         'Montant net = tarif − remise ; contrôle des doublons ; audit '
         '`ENROLLMENT_CREATE`.'],
        ['3', 'SECRETAIRE', 'Dépose les pièces du dossier.', 'Types contrôlés, '
         'taille limitée, stockage privé, audit `STUDENT_DOCUMENT_UPLOAD`.'],
        ['4', 'SECRETAIRE / ASSISTANT_ADMIN', 'Consulte le solde et l’historique.',
         'Lecture seule pour la comptabilité ; soldes recalculés.'],
        ['5', 'SECRETAIRE / DIRECTION', 'Modifie une inscription existante.',
         'Exception : les rôles élevés peuvent aussi corriger une inscription ; '
         'audit `ENROLLMENT_EDIT`.'],
        ['6', 'ASSISTANT_ADMIN', 'Ouvre une inscription au guichet '
         'depuis l’écran d’encaissement.', 'Statut « En attente » forcé ; '
         'tarif catalogue repris par défaut ; audit `ENROLLMENT_CREATE`.'],
        ['7', 'DIRECTION / ASSISTANT_ADMIN / RESP_PEDA / SUPER_ADMIN',
         'Valide une inscription en attente.',
         'Statut « Active » ; audit `ENROLLMENT_VALIDATE` ; seul un dossier '
         'validé devient encaissable.'],
    ],
    widths=[0.9, 3.4, 6.4, 6.3], size=8.6, header_size=8.6,
    align_center={0},
)

h2('7.4', 'Accueil : visite, prospect et conversion')
add_table(
    ['#', 'Acteur', 'Action', 'Contrôle / résultat'],
    [
        ['1', 'ASSISTANT_ADMIN', 'Enregistre une visite.', 'Contact créé ou réutilisé '
         'par téléphone/e-mail ; heure d’arrivée ; motif ; audit `VISIT_CREATE`.'],
        ['2', 'ASSISTANT_ADMIN', 'Enregistre le départ.', 'Statut terminé ; durée '
         'calculable ; audit `VISIT_DEPARTURE`.'],
        ['3', 'ASSISTANT_ADMIN', 'Convertit la visite en prospect.', 'Pas de doublon ; '
         'audit `PROSPECT_FROM_VISIT`.'],
        ['4', 'ASSISTANT_ADMIN', 'Planifie et trace les relances.', 'Statut, prochaine '
         'date, résumé ; audit `PROSPECT_FOLLOW_UP`.'],
        ['5', 'SECRETAIRE', 'Convertit le prospect en étudiant.', 'Compte et '
         'inscription créés ; prospect marqué converti ; audit.'],
    ],
    widths=[0.9, 3.4, 6.4, 6.3], size=8.6, header_size=8.6,
    align_center={0},
)

h2('7.5', 'Planification pédagogique')
add_table(
    ['#', 'Acteur', 'Action', 'Contrôle / résultat'],
    [
        ['1', 'DIRECTION / RESP_PEDA', 'Crée la formation.', 'Titre, domaine, '
         'durée, tarif, éligibilité certificat.'],
        ['2', 'DIRECTION / RESP_PEDA', 'Crée le groupe (`CourseSession`).',
         'Dates cohérentes (fin > début), capacité, statut, formateurs '
         'affectés ; audit `COURSE_SESSION_CREATE`.'],
        ['3', 'DIRECTION / RESP_PEDA', 'Structure les modules et leçons.',
         'Rattachement à la formation ; ordre et heures prévues.'],
        ['4', 'RESP_PEDA / FORMATEUR', 'Planifie les séances.', 'Date, '
         'horaires prévus, module, leçon ; audit `SESSION_CREATE`.'],
        ['5', 'RESP_PEDA / FORMATEUR', 'Publie les ressources.', 'Brouillon, '
         'publié ou archivé ; visibilité limitée aux inscrits.'],
    ],
    widths=[0.9, 3.4, 6.4, 6.3], size=8.6, header_size=8.6,
    align_center={0},
)

h2('7.6', 'Séance, cahier de texte et fiches de cours')
add_paragraph(
    'Ce processus numérise les deux fiches papier remises au formateur et aux '
    'étudiants. La fiche formateur reprend l’en-tête « Formateur / Filière / '
    'Classe » et cinq colonnes : Dates, Heures, Notions enseignées, Nombre '
    'd’apprenants, Observations. La fiche étudiant reprend la même logique '
    'avec la présence, les heures suivies, les notions retenues, les '
    'difficultés et les observations.'
)

h3('A. Après le cours — côté formateur')
add_table(
    ['#', 'Acteur', 'Action', 'Contrôle / résultat'],
    [
        ['1', 'FORMATEUR', 'Ouvre « Cahier de texte » et choisit son groupe.',
         'Un formateur ne voit que les groupes auxquels il est affecté.'],
        ['2', 'FORMATEUR', 'Saisit la date, l’heure de début et de fin.',
         'L’heure de fin doit être postérieure au début.'],
        ['3', 'FORMATEUR', 'Saisit les notions enseignées.', 'Champ obligatoire '
         'dans le formulaire du cahier de texte.'],
        ['4', 'FORMATEUR', 'Saisit le nombre d’apprenants et les observations.',
         'Entier positif ou nul ; observations libres.'],
        ['5', 'FORMATEUR', 'Choisit le statut de la séance.', 'Planifiée, '
         'réalisée, annulée ou reportée.'],
        ['6', 'Système', 'Enregistre la ligne.', 'Anti-doublon sur '
         '(groupe, date, heure de début) ; si réalisée, les heures réelles '
         'reprennent les heures prévues ; audit `SESSION_CREATE`.'],
        ['7', 'FORMATEUR', 'Imprime le cahier de texte.', 'En-tête officiel '
         'RCCM/NIU/CNSS, identité formateur/filière/classe, tableau à cinq '
         'colonnes, totaux ; accès refusé aux étudiants.'],
    ],
    widths=[0.9, 3.2, 6.3, 6.6], size=8.6, header_size=8.6,
    align_center={0},
)

h3('B. Après le cours — côté étudiant')
add_table(
    ['#', 'Acteur', 'Action', 'Contrôle / résultat'],
    [
        ['1', 'ETUDIANT', 'Ouvre « Mes fiches de cours ».', 'Seules les '
         'séances réalisées de ses propres inscriptions sont proposées.'],
        ['2', 'ETUDIANT', 'Indique sa présence et les heures suivies.',
         'Heure de fin > heure de début ; présence déclarative.'],
        ['3', 'ETUDIANT', 'Saisit les notions retenues.', 'Champ obligatoire.'],
        ['4', 'ETUDIANT', 'Saisit difficultés et observations.', 'Facultatif.'],
        ['5', 'Système', 'Crée ou met à jour la fiche.', 'Une seule fiche par '
         '(inscription, séance) ; audit `STUDENT_NOTE_CREATE` ou '
         '`STUDENT_NOTE_UPDATE`.'],
        ['6', 'ETUDIANT', 'Imprime sa feuille de suivi.', 'Une feuille par '
         'formation, regroupant dates, heures, notions, présence et '
         'observations ; accès strictement personnel.'],
        ['7', 'FORMATEUR', 'Consulte les fiches de la séance.', 'Visible sur '
         'la fiche séance, en lecture seule.'],
    ],
    widths=[0.9, 3.2, 6.3, 6.6], size=8.6, header_size=8.6,
    align_center={0},
)

callout(
    'Articulation avec la feuille de présence',
    'La feuille de présence (`Attendance`) est l’enregistrement officiel du '
    'pointage par le formateur. La fiche étudiant (`StudentSessionNote`) est '
    'une déclaration de l’apprenant. Les deux sont conservées séparément : '
    'elles ne se écrasent pas et permettent de détecter un écart.',
)

h2('7.7', 'Ressources et retours étudiants')
add_paragraph(
    'Le formateur ou le responsable pédagogique dépose un support (fichier ou '
    'contenu HTML), le rattache à une formation, éventuellement à un module, '
    'une leçon ou un groupe, puis le publie. Un étudiant ne voit que les '
    'ressources publiées de ses formations. Il peut déposer une note de 1 à 5 '
    'et un commentaire ; une seule fiche de retour par ressource et par '
    'étudiant. Les rôles élevés consultent les retours sans pouvoir en créer.'
)

h2('7.8', 'Encaissement et comptabilité')
add_paragraph(
    'L’écran d’encaissement est ouvert à tout poste portant le droit '
    '`finance.write` — la matrice « Permissions » en décide, pas une liste de '
    'rôles — et aux rôles transversaux, qui tiennent la caisse comme le '
    'secrétariat. Chaque paiement porte un motif (mensualité, frais '
    'd’inscription, autre paiement) et, pour une mensualité, le mois et '
    'l’année réglés, distincts de la date d’encaissement. Avant toute sortie, '
    'l’écran montre ce que chaque caisse peut réellement débourser ; une '
    'sortie qui en consomme 80 % ou plus demande un second geste, une case '
    'explicitement cochée.'
)
add_table(
    ['#', 'Acteur', 'Action', 'Contrôle / résultat'],
    [
        ['1', 'droit `finance.write`', 'Choisit l’inscription à encaisser.',
         'Liste des inscriptions validées, non annulées ; solde affiché.'],
        ['2', 'droit `finance.write`', 'Saisit le montant et le moyen de '
         'paiement.', 'Montant ≥ 1 et ≤ reste à payer ; refus du trop-perçu. '
         'Date de la recette jamais postérieure au jour de la saisie.'],
        ['3', 'droit `finance.write`', 'Coche les mois réglés sur la grille des '
         'douze mois.', 'Un paiement par mois coché ; le mois déjà réglé est '
         'marqué et non re-cochable ; mensualité pré-remplie depuis le dossier '
         '(net dû réparti sur la durée de la formation).'],
        ['4', 'Système', 'Détecte une double soumission.', 'Même dossier, même '
         'montant, même minute : refus explicite. Un même mois ne peut être '
         'réglé deux fois : contrôle de formulaire et contrainte en base.'],
        ['5', 'Système', 'Crée le paiement et l’opération de caisse.',
         'Transaction atomique ; opération validée ; catégorie « Paiements des '
         'étudiants » ; audit `PAYMENT_CREATE`.'],
        ['6', 'Assistant administratif', 'Imprime le reçu.', 'Le reçu mentionne '
         'le motif et le mois réglé ; accessible au guichet, au secrétariat, à '
         'la direction et à l’étudiant propriétaire.'],
        ['7', 'caisse (direction, assistant, rôles transversaux)',
         'Saisit une opération directe (entrée/sortie).',
         'Catégorie cohérente, compte valide et non archivé, solde disponible '
         'affiché par caisse ; la caisse ne descend jamais sous son plancher ; '
         'audit `CASH_TRANSACTION_CREATE`.'],
        ['8', 'caisse (direction, assistant, rôles transversaux)',
         'Effectue un transfert entre caisses.', 'Compte destinataire '
         'obligatoire et différent ; neutre au niveau global ; la caisse source '
         'ne se vide pas au-delà de son solde.'],
        ['9', 'caisse (direction, assistant, rôles transversaux)',
         'Annule une opération.',
         'Motif obligatoire ; statut annulé ; audit `CASH_TRANSACTION_CANCEL` ; '
         'refusé si l’entrée déjà dépensée ferait passer la caisse sous zéro.'],
        ['10', 'caisse (direction, assistant, rôles transversaux)',
         'Corrige une écriture enregistrée.', 'Montant, catégorie, libellé ou '
         'date, avec motif obligatoire ; solde projeté hors de la ligne '
         'elle-même ; changement de caisse refusé ici — annuler et ressaisir. '
         'Écriture annulée fermée ; audit `CASH_TRANSACTION_EDIT`.'],
        ['11', 'caisse (direction, assistant, rôles transversaux)',
         'Administre un compte : état, type, devise, description, découvert.',
         'Nom et solde d’ouverture figés dès la première écriture ; devise '
         'inchangée si le compte a des écritures ; découvert interdit par '
         'défaut et réservé au SUPER_ADMIN ; archivage exigeant un compte de '
         'remplacement quand le '
         'solde ou des brouillons restent ; historique et audit '
         '`CASH_ACCOUNT_EDIT`.'],
        ['12', 'caisse (direction, assistant, rôles transversaux)',
         'Ajuste un solde.', 'Un montant, un sens, un motif obligatoire ; '
         'daté du jour ; écriture d’ajustement tracée, jamais une retouche '
         'silencieuse du solde ; catégorie « Ajustements de solde » créée si '
         'besoin.'],
        ['13', 'caisse (direction, assistant, rôles transversaux)',
         'Réinitialise une caisse.', 'Aperçu du solde, confirmation explicite, '
         'motif ; une écriture contraire ramène le solde à zéro et l’historique '
         'entier reste consultable ; les brouillons encore en attente sont '
         'signalés avant coup.'],
        ['14', 'caisse (direction, assistant, rôles transversaux)',
         'Administre les catégories d’écriture.', 'Création, renommage, '
         'compteur d’écritures ; désactivation plutôt que suppression, pour que '
         'les lignes passées gardent leur sens ; audit '
         '`TRANSACTION_CATEGORY_CREATE` et `TRANSACTION_CATEGORY_EDIT`.'],
    ],
    widths=[0.9, 3.6, 6, 6.5], size=8.6, header_size=8.6,
    align_center={0},
)

h2('7.9', 'Clôture de caisse')
add_paragraph(
    'La clôture compare le solde théorique (ouverture + mouvements validés) au '
    'montant physiquement compté. L’écart est conservé, positif ou négatif. '
    'Une seule clôture est autorisée par caisse et par date. L’opération est '
    'tracée (`CASH_CLOSURE`) et reste consultable dans l’historique.'
)

h2('7.10', 'Candidature et décision de bourse')
add_table(
    ['#', 'Acteur', 'Action', 'Contrôle / résultat'],
    [
        ['1', 'Candidat', 'Dépose une candidature publique.', 'Référence et '
         'jeton de suivi générés ; audit `SCHOLARSHIP_SUBMIT`.'],
        ['2', 'Candidat', 'Ajoute ses pièces.', 'Types contrôlés, taille '
         'limitée, stockage privé.'],
        ['3', 'SUPER_ADMIN / ADMIN', 'Consulte le dossier.', 'L’ADMIN voit le '
         'dossier mais ne peut pas statuer.'],
        ['4', 'SUPER_ADMIN', 'Statue : approuve, refuse, demande des pièces.',
         'Statut mis à jour, note conservée, audit `SCHOLARSHIP_REVIEW`.'],
        ['5', 'Candidat', 'Suit sa candidature avec son jeton.', 'Aucune '
         'énumération possible des dossiers.'],
    ],
    widths=[0.9, 3.4, 6.4, 6.3], size=8.6, header_size=8.6,
    align_center={0},
)

h2('7.11', 'Supervision et contrôles')
add_paragraph(
    'Le SUPER_ADMIN dispose d’une supervision financière exhaustive : toutes '
    'les opérations, y compris brouillons et annulations, avec filtres, totaux '
    'sur les seules validées, soldes par caisse et export CSV audité. Il '
    'consulte également le journal d’audit global, filtrable par action, '
    'entité, acteur et période. L’ADMIN partage la lecture de la supervision '
    'et du journal d’audit, mais les décisions de bourse et les actes '
    'de gestion des comptes restent réservés au SUPER_ADMIN.'
)

page_break()

# ===========================================================================
# 8. Règles de gestion
# ===========================================================================
h1('8', 'Règles de gestion')

add_paragraph(
    'Les règles ci-dessous constituent le contrat fonctionnel du système. '
    'Chacune est appliquée côté serveur et, lorsque c’est pertinent, couverte '
    'par un test automatisé.'
)

RULES = [
    ('Identité et accès', [
        ('RG-01', 'Tout compte créé par inscription est `PENDING_APPROVAL` et '
                  'ne porte aucun rôle.'),
        ('RG-02', 'Le rôle demandé est enregistré dans `AccessRequest` mais '
                  'n’est jamais attribué automatiquement.'),
        ('RG-03', 'Seuls cinq rôles sont demandables : ETUDIANT, FORMATEUR, '
                  'SECRETAIRE, ASSISTANT_ADMIN, RESP_PEDA.'),
        ('RG-04', 'Un rôle inconnu ou hors liste est refusé sans écriture.'),
        ('RG-05', 'Un compte ne peut pas examiner sa propre demande d’accès.'),
        ('RG-06', 'Nul ne peut modifier ses propres rôles ou son propre statut.'),
        ('RG-07', 'Le dernier SUPER_ADMIN actif ne peut pas perdre son rôle.'),
        ('RG-08', 'Le code interne est généré une seule fois, au premier rôle '
                  'attribué, et n’est plus modifié.'),
        ('RG-09', 'Un compte non actif est bloqué sur tous les écrans métier, '
                  'y compris avec une session déjà ouverte.'),
        ('RG-10', 'L’approbation prend effet sans reconnexion.'),
    ]),
    ('Scolarité', [
        ('RG-11', 'Un étudiant approuvé doit être rattaché à un groupe ; à '
                  'défaut, l’approbation est refusée.'),
        ('RG-12', 'Une approbation ne crée jamais une deuxième inscription '
                  'pour un étudiant déjà inscrit.'),
        ('RG-13', 'Le montant net d’une inscription est le tarif moins la '
                  'remise, sans jamais être négatif.'),
        ('RG-14', 'Le reste à payer est `max(net − paiements validés, 0)` ; il '
                  'n’est pas stocké.'),
        ('RG-15', 'Un paiement partiel ne solde pas le dossier ; un trop-perçu '
                  'est refusé à la saisie.'),
        ('RG-16', 'Un document étudiant n’est téléchargeable que par son '
                  'propriétaire ou un rôle habilité.'),
    ]),
    ('Pédagogie et assiduité', [
        ('RG-17', 'Une séance appartient à un groupe et à une date ; l’heure '
                  'de fin doit suivre l’heure de début.'),
        ('RG-18', 'Une séance réalisée doit avoir une heure réelle de début.'),
        ('RG-19', 'Une ligne de cahier de texte est unique par groupe, date et '
                  'heure de début.'),
        ('RG-20', 'Les notions enseignées sont obligatoires dans le cahier de '
                  'texte.'),
        ('RG-21', 'Le nombre d’apprenants saisi fait foi ; à défaut, il est '
                  'déduit de la feuille de présence.'),
        ('RG-22', 'Une présence est unique par inscription et par date.'),
        ('RG-23', 'Une présence déjà saisie pour une autre séance le même jour '
                  'n’est pas écrasée silencieusement.'),
        ('RG-24', 'Une fiche de cours étudiant est unique par inscription et '
                  'par séance.'),
        ('RG-25', 'Une fiche étudiant n’est possible que pour une séance '
                  'réalisée et une inscription de l’étudiant.'),
        ('RG-26', 'L’heure de fin suivie doit être postérieure à l’heure de '
                  'début suivie.'),
        ('RG-27', 'Les notions retenues sont obligatoires dans la fiche '
                  'étudiant.'),
        ('RG-28', 'Un étudiant ne voit ni la fiche ni la feuille d’un autre '
                  'parcours ; les rôles élevés n’y ont pas accès.'),
        ('RG-29', 'Une ressource brouillon ou archivée n’est pas visible de '
                  'l’étudiant.'),
        ('RG-30', 'Un étudiant ne peut déposer qu’un seul retour par ressource.'),
    ]),
    ('Finances', [
        ('RG-31', 'Tout paiement validé crée une opération de caisse validée, '
                  'dans la même transaction.'),
        ('RG-32', 'Une opération de caisse est la seule source des indicateurs '
                  'financiers.'),
        ('RG-33', 'Le solde d’une caisse est `ouverture + entrées validées − '
                  'sorties validées`.'),
        ('RG-34', 'Un transfert est neutre au niveau global ; il ne crée ni '
                  'recette ni dépense.'),
        ('RG-35', 'Le compte destinataire d’un transfert est obligatoire et '
                  'différent du compte source.'),
        ('RG-36', 'Une opération ne peut être annulée qu’avec un motif, et '
                  'l’annulation est tracée.'),
        ('RG-37', 'Une clôture est unique par caisse et par date.'),
        ('RG-38', 'L’écart de clôture est conservé, même négatif.'),
        ('RG-39', 'Une double soumission de paiement identique est refusée.'),
        ('RG-40', 'Le reçu n’est accessible qu’aux rôles habilités et à '
                  'l’étudiant propriétaire.'),
    ]),
    ('Encaissement mensuel et droits', [
        ('RG-41', 'Un paiement étudiant porte l’année et le mois qu’il solde, '
                  'distincts de la date d’encaissement.'),
        ('RG-42', 'Un mois ne se solde qu’une fois par dossier : la grille des '
                  'douze mois désactive les mois déjà encaissés et la base le '
                  'contraint.'),
        ('RG-43', 'La mensualité proposée vient du dossier (net dû réparti sur '
                  'la durée de la formation) ; elle reste modifiable.'),
        ('RG-44', 'L’accès à l’encaissement se décide par le droit « Saisir des '
                  'paiements » de la matrice des permissions, non par une liste '
                  'de rôles écrite dans le code.'),
        ('RG-45', 'Un poste dissous n’apparaît dans aucun menu, filtre ni '
                  'demande d’accès ; les comptes déjà marqués restent lisibles '
                  'pour l’historique.'),
    ]),
    ('Vie du compte étudiant', [
        ('RG-46', 'Un compte étudiant naît « en attente d’approbation » — import '
                  'des classeurs comme écran du secrétariat. Créer d’emblée un '
                  'dossier « Active » vaut approbation immédiate.'),
        ('RG-47', 'Valider une inscription approuve le compte étudiant tant que '
                  'son approbation est encore en attente.'),
        ('RG-48', 'Un compte étudiant ouvert depuis une fiche de classeur — donc '
                  'sans login distribué, mot de passe vide — n’est pas un compte '
                  'approuvé : il est en attente. Les comptes ouverts à la main '
                  'gardent l’approbation qu’ils ont reçue ; '
                  '`manage.py mettre_en_attente` remplace ceux de la vague déjà '
                  'écrite, sans rien supprimer ni reclasser.'),
    ]),
    ('Bourses et audit', [
        ('RG-49', 'La décision de bourse est réservée au SUPER_ADMIN.'),
        ('RG-50', 'Le suivi public d’une candidature exige son jeton, sans '
                  'énumération possible.'),
        ('RG-51', 'Toute action sensible écrit une entrée d’audit avec acteur, '
                  'entité, avant/après et horodatage.'),
        ('RG-52', 'Le journal d’audit est append-only : aucune vue ne le '
                  'modifie.'),
        ('RG-53', 'Une action sans effet (rôle déjà attribué, statut identique) '
                  'ne crée pas d’entrée d’audit.'),
        ('RG-54', 'Un export CSV de supervision est lui-même audité.'),
    ]),
    ('Photo de profil', [
        ('RG-55', 'La photo de profil se voit partout où la personne est '
                  'nommée — listes d’étudiants, file de validation, présences, '
                  'tableaux de bord, utilisateurs et demandes d’accès, en-têtes '
                  'de fiche — par la balise unique `{% vignette %}` ; à défaut '
                  'de photo, la personne garde ses initiales.'),
        ('RG-56', 'Elle se pose par l’intéressé sur « Mon profil », par le '
                  'secrétariat sur la fiche étudiant, par le SUPER_ADMIN sur la '
                  'fiche d’un compte. Le personnel doit pouvoir la poser : une '
                  'fiche sortie des classeurs ne se connecte jamais.'),
        ('RG-57', 'Le dépôt d’une photo ne change ni le statut du compte ni '
                  'ses rôles ; un dépôt refusé (format, taille, aucun fichier) '
                  'laisse la photo en place et affiche la raison du refus.'),
        ('RG-58', 'Le fichier remplacé est supprimé du disque (accord de la '
                  'direction du 03/11/2026), le retrait rend les initiales ; '
                  'les deux sont audités `PROFILE_AVATAR` / '
                  '`PROFILE_AVATAR_DELETE` avec l’acteur et la personne '
                  'concernée.'),
    ]),
    ('Mot de passe et adresse e-mail', [
        ('RG-59', 'Chaque utilisateur change son mot de passe lui-même sur '
                  '« Mon profil » (mot de passe actuel, nouveau, confirmation) ; '
                  'le nouveau passe les quatre règles de validité du projet, et '
                  'un refus laisse le mot de passe en place.'),
        ('RG-60', 'Le mot de passe actuel n’est exigé que si le compte en '
                  'possède un : une fiche sortie des classeurs ou un compte lié '
                  'à Clerk arrive sans mot de passe local et l’écran sert alors '
                  'à en poser un. La même règle vaut pour la preuve du '
                  'changement d’adresse e-mail.'),
        ('RG-61', 'Après un changement, la session en cours reste valide ; les '
                  'autres appareils ne sont pas déconnectés, faute de suivi des '
                  'sessions. L’audit `PROFILE_PASSWORD` journalise l’acteur et '
                  'la présence d’un mot de passe, jamais sa valeur.'),
    ]),
    ('Date de la recette', [
        ('RG-62', 'Une recette ne se date jamais plus tard que le jour de sa '
                  'saisie : l’écran d’encaissement refuse une date postérieure à '
                  'aujourd’hui et n’écrit ni paiement ni opération de caisse.'),
        ('RG-63', 'Régler un mois à venir sur la grille des douze mois reste '
                  'possible — c’est une avance — mais la recette se date du jour '
                  'présent : `paid_at` porte l’entrée d’argent, `period_year` et '
                  '`period_month` le mois couvert.'),
        ('RG-64', 'À l’import des classeurs, une case chiffrée pour un mois non '
                  'encore commencé annonce le plan de la promotion : elle est '
                  'signalée comme écart et ne devient pas un paiement.'),
        ('RG-65', 'Les écritures déjà enregistrées avant cette règle ne sont pas '
                  'retouchées — la direction arbitre ligne à ligne ; l’audit '
                  '`audit_finances` les liste sous `DATE FUTURE` et `CAISSE '
                  'FUTURE`, jusqu’à 20 lignes par famille avec le total restant.'),
    ]),
    ('Solde de caisse', [
        ('RG-66', 'Le solde d’une caisse ne passe jamais sous son plancher. La '
                  'règle vit une seule fois, dans le modèle (`balance_after`, '
                  '`decouvert`) et dans le service `caisse.juger`, appelés de '
                  'l’écran de saisie, de l’annulation, de l’ajustement, de '
                  'l’import du journal et de `save()` : une requête envoyée '
                  'directement à l’API rencontre le même refus, montant '
                  'manquant à l’appui.'),
        ('RG-67', 'Annuler une entrée déjà dépensée est refusé du même contrôle : '
                  'la régularisation passe par une écriture contraire, jamais par '
                  'l’effacement de l’entrée d’origine. Un brouillon reste '
                  'saisissable car il ne compte pas en caisse.'),
        ('RG-68', 'La reprise du journal de caisse juge le lot entier avant '
                  'd’écrire : si la caisse choisie finirait sous zéro, '
                  '`importer_feuille --ecrire` refuse et demande la caisse '
                  'réellement débitée.'),
        ('RG-69', 'Le creux constaté le 01/11/2026 sur « Mobile Money » a été '
                  'régularisé le 04/11/2026 après analyse de cause : deux '
                  'sorties du 30/10 y avaient été portées alors que le '
                  'portefeuille ne contenait aucune recette. Elles restent au '
                  'journal, annulées et motivées, et sont ressaisies sur la '
                  'caisse qui a payé (arbitrage de la direction, « ressaisir '
                  'sur la Caisse principale »). `audit_finances` ne signale plus '
                  'aucun solde négatif, et le plancher rendu infranchissable '
                  'empêche ce creux de se rouvrir.'),
    ]),
    ('Compte administrable', [
        ('RG-70', 'Un compte se règle après coup depuis « Comptes » : type, '
                  'devise, description, découvert autorisé, état (actif, '
                  'inactif, archivé) et compte de remplacement. Le nom et le '
                  'solde d’ouverture restent hors du formulaire : le nom sert '
                  'de clé aux reprises du journal, et l’ouverture d’une caisse '
                  'qui a déjà des écritures se régularise par un ajustement, '
                  'jamais en réécrivant le passé.'),
        ('RG-71', 'La devise d’un compte qui a des écritures ne change pas : '
                  'la consigne est d’ouvrir un second compte et d’archiver le '
                  'premier.'),
        ('RG-72', 'Archiver une caisse encore pleine ou chargée de brouillons '
                  'exige de désigner le compte qui reprend l’un et les autres. '
                  'Une caisse archivée refuse toute écriture nouvelle et '
                  'disparaît des listes de saisie, mais son solde et son '
                  'historique restent consultables.'),
        ('RG-73', 'Le découvert autorisé vaut 0 par défaut et le lever '
                  'n’appartient qu’au SUPER_ADMIN. Il reste exceptionnel : la '
                  'garde de solde descend au plancher −« découvert autorisé », '
                  'et le message de refus rappelle le plafond.'),
        ('RG-74', 'Chaque changement d’état d’un compte est journalisé '
                  '(`CASH_ACCOUNT_EDIT`, valeurs avant et après) et la fiche du '
                  'compte montre son historique.'),
    ]),
    ('Ajuster et réinitialiser un solde', [
        ('RG-75', 'Le solde d’un compte ne se retouche jamais en silence : '
                  'l’ajustement passe par `caisse.ajuster`, qui écrit une ligne '
                  '« Ajustement de solde » dans la catégorie « Ajustements de '
                  'solde », au jour présent, avec motif obligatoire. Le solde '
                  'd’ouverture reste intact.'),
        ('RG-76', 'Un ajustement en baisse obéit à la même garde qu’une sortie '
                  'ordinaire : il ne peut pas faire passer la caisse sous son '
                  'plancher.'),
        ('RG-77', 'Réinitialiser une caisse demande une confirmation explicite '
                  'et un motif. Une écriture contraire (`Nature.RESET`) ramène '
                  'le solde à zéro ; l’historique entier reste en place, rien '
                  'n’est effacé. Une caisse déjà à zéro n’écrit rien.'),
        ('RG-78', 'Avant la remise à zéro, l’écran affiche le solde emporté et '
                  'compte les brouillons encore en attente : une réinitialisation '
                  'ne rapproche pas ce qui n’est pas saisi.'),
    ]),
    ('Disponible annoncé, sortie confirmée', [
        ('RG-79', 'Le disponible d’une caisse — solde plus découvert autorisé — '
                  'est ce qu’elle peut réellement débourser : c’est lui qui '
                  'décide du verrou d’écriture, de l’avertissement et des '
                  'badges.'),
        ('RG-80', 'Le disponible se lit avant le geste : au pied du nom de '
                  'chaque caisse au moment de choisir où payer, en badges sur '
                  'l’écran d’opération et dans la colonne « Solde disponible » '
                  'de la liste des comptes.'),
        ('RG-81', 'Une sortie qui consomme 80 % ou plus du disponible est '
                  'annoncée et demande un second geste : une case à cocher. '
                  'Sans elle, rien ne s’écrit. Une recette et un brouillon '
                  'n’entrent pas dans ce discours — ils ne déboursent rien '
                  '(`sortie_prevue`, la même règle que l’enregistrement).'),
        ('RG-82', 'Au-delà du disponible, ce n’est plus un avertissement mais '
                  'un refus, et c’est `juger` qui le dit : l’écran ne tient pas '
                  'deux discours sur le même argent. Une caisse vide se '
                  'signale — « Solde épuisé » sur la liste, « Aucun fonds '
                  'disponible » à la saisie — mais ne bloque pas une recette, '
                  'c’est elle qui comble le creux.'),
    ]),
    ('Corriger une écriture, administrer les catégories', [
        ('RG-83', 'Une écriture enregistrée se corrige sur sa propre fiche : '
                  'montant, catégorie, libellé ou date, avec motif obligatoire '
                  'et écriture annulée fermée à la correction. Le solde projeté '
                  'exclut la ligne telle qu’elle est en base, pour ne pas la '
                  'compter deux fois.'),
        ('RG-84', 'Changer de caisse ne se fait pas par correction : une '
                  'écriture portée sur la mauvaise caisse s’annule et se '
                  'ressaisit à côté, les deux lignes restant visibles et '
                  'reliées dans le journal.'),
        ('RG-85', 'Une écriture ordinaire antidatée ne revient pas sur une '
                  'période déjà clôturée : `juger` la refuse et renvoie vers '
                  'une écriture d’ajustement.'),
        ('RG-86', 'Les catégories d’écriture se créent et se règlent à l’écran, '
                  'avec le compteur d’écritures attachées ; on les désactive '
                  'plutôt que de les supprimer, pour que le classement des '
                  'lignes passées survive.'),
    ]),
    ('Caisse ouverte aux rôles élevés', [
        ('RG-87', 'Sur décision de la direction, SUPER_ADMIN et ADMIN tiennent '
                  'la caisse : journal, opération, annulation, correction, '
                  'encaissement, clôture, comptes et catégories sont en '
                  'écriture pour eux (`cash_write_required`), comme pour la '
                  'direction et l’assistant administratif.'),
        ('RG-88', 'Cette ouverture ne vaut que pour l’argent. La création d’une '
                  'inscription, les écrans étudiants, la pédagogie et l’accueil '
                  'restent en consultation seule pour les rôles transversaux '
                  '(`business_write_required`).'),
        ('RG-89', 'Ouvrir la caisse n’enlève rien à la traçabilité : chaque '
                  'geste, quel que soit le rôle, écrit une entrée d’audit avec '
                  'l’acteur, la valeur d’avant et la valeur d’après.'),
    ]),
]

for group, rules in RULES:
    h2('8.' + str(RULES.index((group, rules)) + 1), group)
    add_table(['Règle', 'Énoncé'],
              [[code, text] for code, text in rules],
              widths=[2.2, 14.8], size=8.8, header_size=8.8,
              first_col_bold=True, align_center={0})

page_break()

# ===========================================================================
# 9. Sécurité
# ===========================================================================
h1('9', 'Sécurité et contrôle d’accès')

h2('9.1', 'Authentification')
bullets([
    ('Double voie. ', 'Connexion locale par e-mail ou code interne, ou '
     'connexion Clerk (Google ou e-mail/mot de passe). Les deux formulaires '
     'cohabitent sur `/login/`.'),
    ('Aucun privilège déduit du fournisseur. ', 'Les métadonnées Clerk ne '
     'sont jamais lues pour accorder un rôle. Un compte Clerk reste soumis à '
     'l’approbation humaine.'),
    ('Mots de passe. ', 'Hachage Django ; les tests utilisent un hasheur rapide '
     'isolé. Les mots de passe de démonstration doivent être renouvelés avant '
     'production.'),
    ('Session. ', 'Cookie de session Django, expiration et déconnexion '
     'explicite. Le changement de statut est relu à chaque requête.'),
])

h2('9.2', 'Autorisation en profondeur')
add_table(
    ['Niveau', 'Mécanisme', 'Effet'],
    [
        ['Middleware', '`AccountStatusMiddleware`', 'Bloque les comptes non '
         'actifs avant toute vue métier.'],
        ['Décorateur de rôle', '`role_required`, `super_admin_required`',
         'Vérifie l’appartenance aux rôles autorisés.'],
        ['Décorateur d’écriture', '`business_write_required`', 'Refuse les '
         'rôles transversaux sur le métier.'],
        ['Garde par objet', 'Filtres `student=request.user`, '
         '`session__formateurs=request.user`, appartenance à l’inscription',
         'Empêche l’accès à une ressource d’un autre utilisateur (IDOR).'],
        ['Formulaire', 'Validation des montants, dates, doublons',
         'Empêche les incohérences et les doubles soumissions.'],
        ['Interface', 'Boutons et formulaires masqués', 'Réduit les erreurs, '
         'sans jamais remplacer le contrôle serveur.'],
    ],
    widths=[3.2, 6.6, 7.2], size=8.8, header_size=8.8, first_col_bold=True,
)

h2('9.3', 'Protection des fichiers')
add_paragraph(
    'Le répertoire `media/` n’est pas servi publiquement. Les pièces '
    'justificatives, ressources et documents étudiants passent par des vues '
    'contrôlées qui vérifient l’identité, le rôle et l’appartenance avant de '
    'renvoyer le fichier. Les avatars bénéficient d’une vue dédiée '
    '(`core:avatar`), accessible aux utilisateurs actifs. Toute tentative '
    'refusée est auditée (`UNAUTHORIZED_FILE_ACCESS`). La photo d’une personne '
    's’affiche par la balise `{% vignette %}` — photo posée, sinon initiales ; '
    'le fichier qu’une nouvelle photo remplace est supprimé du disque, la fiche '
    'ne conservant que l’image en cours.'
)

h2('9.4', 'Menaces et mesures')
add_table(
    ['Menace', 'Mesure'],
    [
        ['Élévation de privilèges par POST forgé', 'Liste blanche serveur des '
         'rôles ; vérification du rôle réel ; refus des rôles élevés.'],
        ['Accès à une ressource d’un autre utilisateur (IDOR)',
         'Filtres par propriétaire et par groupe ; UUID non énumérables.'],
        ['Double encaissement', 'Contrôle de doublon à deux minutes ; '
         'transaction atomique ; audit.'],
        ['Incohérence de caisse', 'Source unique `CashTransaction` ; statut '
         'validé ; transfert neutre.'],
        ['Falsification d’un montant', 'Validation `montant ≤ reste à payer` '
         'côté serveur.'],
        ['Injection SQL', 'ORM Django et requêtes paramétrées.'],
        ['XSS', 'Échappement des templates ; contenu HTML des ressources '
         'maîtrisé par les formateurs.'],
        ['CSRF', 'Jeton CSRF sur tous les formulaires POST.'],
        ['Clickjacking', 'En-tête `X-Frame-Options` via middleware.'],
        ['Fuite de fichiers privés', 'Médias non servis directement ; vues '
         'authentifiées ; audit des refus.'],
        ['Comptes dormants ou de démonstration', 'Audit des privilèges ; '
         'checklist de mise en production.'],
    ],
    widths=[6, 11], size=8.8, header_size=8.8, first_col_bold=True,
)

h2('9.5', 'Recommandations avant production')
numbered([
    'Passer `DEBUG=False` et définir une `SECRET_KEY` longue et secrète.',
    'Activer HTTPS, HSTS, cookies sécurisés et redirection HTTP → HTTPS.',
    'Désactiver ou renouveler les comptes de démonstration, notamment le '
    'superutilisateur `admin@univers.academy`.',
    'Vérifier l’attribution SUPER_ADMIN du compte Clerk '
    '`japhetsamba52@gmail.com`.',
    'Configurer un backend e-mail réel et tester l’envoi des confirmations.',
    'Mettre en place des sauvegardes chiffrées de la base et de `media/`.',
    'Restreindre l’accès à l’admin Django ou le désactiver si inutile.',
    'Surveiller les commandes `audit_finances` et `audit_privileges`.',
])

page_break()

# ===========================================================================
# 10. Audit
# ===========================================================================
h1('10', 'Traçabilité et audit')

h2('10.1', 'Modèle `AuditLog`')
add_paragraph(
    'Chaque entrée décrit qui a fait quoi, sur quelle entité, quand et avec '
    'quelles valeurs. Les résumés avant/après sont stockés en JSON, ce qui '
    'permet de reconstituer une modification sans conserver une copie '
    'complète de l’objet.'
)
add_table(['Champ', 'Type', 'Rôle'], [
    ['actor', 'Référence → User', 'Auteur de l’action (facultatif si système).'],
    ['action', 'Texte', 'Code de l’action (ex. `PAYMENT_CREATE`).'],
    ['entity_type', 'Texte', 'Nom du modèle concerné.'],
    ['entity_id', 'Texte', 'Identifiant de l’entité (UUID ou référence).'],
    ['before_summary', 'JSON', 'Valeurs avant modification.'],
    ['after_summary', 'JSON', 'Valeurs après modification.'],
    ['ip_address', 'Adresse IP', 'Adresse du client.'],
    ['created_at', 'Date et heure', 'Horodatage automatique.'],
], widths=[3.4, 4.6, 9], size=9, header_size=9, first_col_bold=True)

h2('10.2', 'Consultation')
bullets([
    ('Journal global. ', 'Ouvert aux rôles transversaux (SUPER_ADMIN et '
     'ADMIN) en lecture seule ; filtres par recherche, '
     'action, entité, acteur et période ; valeurs avant/après lisibles ; '
     'pagination conservant les filtres.'),
    ('Historique par fiche. ', 'Chaque fiche métier (étudiant, inscription, '
     'séance, visite, prospect, opération) affiche son propre fil d’audit.'),
    ('Liens d’entité. ', 'Le journal renvoie vers la fiche concernée lorsque '
     'l’identifiant est un UUID ; les références non UUID (exports) '
     'n’engendrent aucun lien cassé.'),
    ('Contrôle de cohérence. ', '`audit_finances` et `audit_privileges` sont '
     'des commandes de lecture seule, utilisables en supervision '
     'automatisée.'),
])

h2('10.3', 'Catalogue des actions')
add_paragraph(
    'Le catalogue complet des codes d’action (' + str(len(AUDIT_ACTIONS)) +
    ' entrées), leur domaine et leur signification figure en annexe C. Il '
    'constitue la référence pour les filtres du journal et pour les contrôles '
    'automatisés ; il n’est volontairement pas dupliqué ici.'
)

h2('10.4', 'Limites du dispositif')
bullets([
    'Le journal n’est pas scellé cryptographiquement : un administrateur de '
    'la base pourrait le modifier. Une horodatation externe ou un chaînage '
    'de hachage serait nécessaire pour une non-répudiation forte.',
    'Aucune politique de rétention ou de purge n’est définie à ce stade.',
    'Les actions de consultation ne sont pas toutes journalisées ; seules les '
    'actions sensibles et les accès fichiers le sont.',
])

page_break()

# ===========================================================================
# 11. Parcours, interfaces et routes
# ===========================================================================
h1('11', 'Parcours, interfaces et routes')

h2('11.1', 'Parcours public')
add_table(['Écran', 'Route', 'Fonction'], [
    ['Accueil', '`/`', 'Présentation de l’établissement, formations, appel à '
     'candidature.'],
    ['Connexion', '`/login/`', 'Compte local (e-mail ou code interne) et '
     'connexion Clerk sur la même page.'],
    ['Inscription', '`/register/`', 'Création de compte et choix du rôle '
     'demandé.'],
    ['Demande d’accès', '`/demande-acces/`', 'Complément de rôle pour un '
     'compte existant en attente.'],
    ['Attente', '`/pending-approval/`', 'Information sur l’état de la demande.'],
    ['Accès refusé', '`/access-denied/`', 'Compte suspendu, désactivé ou '
     'rejeté.'],
    ['Candidature bourse', '`/candidature/`', 'Formulaire public de bourse.'],
    ['Suivi de bourse', '`/suivi/`', 'Consultation par référence et jeton.'],
], widths=[3.6, 4.4, 9], size=9, header_size=9, first_col_bold=True)

h2('11.2', 'Tableaux de bord par rôle')
add_table(['Rôle', 'Route', 'Contenu principal'], [
    ['SUPER_ADMIN', '`/dashboard/super-admin/`', 'Indicateurs consolidés, '
     'utilisateurs, demandes, finances, bourses, audit.'],
    ['ADMIN', '`/dashboard/admin/`', 'Vue transversale, demandes en attente, '
     'accès directs aux modules.'],
    ['DIRECTION', '`/dashboard/direction/`', 'Pilotage académique et '
     'financier.'],
    ['SECRETAIRE', '`/dashboard/secretaire/`', 'Étudiants, inscriptions, '
     'documents, séances.'],
    ['ASSISTANT_ADMIN', '`/dashboard/comptabilite/`', 'Journal, caisses, '
     'clôtures, paiements par mois, reçus ; et dans la même barre latérale, '
     'visites, prospects et entrées/sorties.'],
    ['RESP_PEDA', '`/dashboard/responsable-pedagogique/`', 'Groupes, séances, '
     'progression, ressources.'],
    ['FORMATEUR', '`/dashboard/formateur/`', 'Ses groupes, séances, cahier de '
     'texte, présences, ressources.'],
    ['ETUDIANT', '`/dashboard/etudiant/`', 'Ressources, présences, fiches de '
     'cours, solde.'],
], widths=[3.2, 6.2, 7.6], size=9, header_size=9, first_col_bold=True)

h2('11.3', 'Routes structurantes par module')
add_table(['Module', 'Routes principales', 'Usage'], [
    ['Utilisateurs', '`/super-admin/users/`, `.../create/`, `.../<id>/`, '
     '`.../<id>/roles/`, `.../<id>/status/`', 'Gestion des comptes et des '
     'accès.'],
    ['Permissions', '`/super-admin/permissions/`', 'Matrice postes × droits, '
     'éditée par le super administrateur ; l’encaissement en dépend.'],
    ['Demandes', '`/super-admin/access-requests/`, `.../<id>/`', 'Revue et '
     'décision.'],
    ['Accueil', '`/accueil/visites/`, `.../nouvelle/`, '
     '`/accueil/prospects/`, `/accueil/motifs/`', 'Visites, prospects, '
     'motifs.'],
    ['Scolarité', '`/secretaire/etudiants/`, `.../nouveau/`, '
     '`.../<id>/`, `/secretaire/inscriptions/nouvelle/`', 'Dossiers et '
     'inscriptions.'],
    ['Pédagogie', '`/pedagogie/programmes/`, `/pedagogie/groupes/`, '
     '`/pedagogie/seances/`, `/pedagogie/progression/`', 'Programme et suivi.'],
    ['Cahier de texte', '`/pedagogie/cahier-de-texte/`, `.../<groupe>/`, '
     '`.../<groupe>/imprimer/`', 'Saisie et impression.'],
    ['Ressources', '`/pedagogie/ressources/`, `.../nouvelle/`, '
     '`.../<id>/voir/`, `.../telecharger/`', 'Supports et retours.'],
    ['Comptabilité', '`/comptabilite/journal/`, `.../operations/nouvelle/`, '
     '`.../operations/<id>/corriger/`, `/comptabilite/caisses/`, '
     '`.../caisses/<id>/{administrer,ajuster,reinitialiser}/`, '
     '`/comptabilite/categories/`, `.../categories/<id>/`, '
     '`/comptabilite/clotures/`, `/comptabilite/paiement/`, '
     '`.../paiement/mois/`',
     'Caisse, comptes administrables, catégories, clôtures et encaissements.'],
    ['Espace étudiant', '`/etudiant/ressources/`, `/etudiant/presences/`, '
     '`/etudiant/fiches/`, `/etudiant/feuille/<groupe>/`', 'Ressources, '
     'présences, fiches.'],
    ['Bourses', '`/candidature/`, `/suivi/`, `/super-admin/scholarships/`',
     'Candidature et instruction.'],
    ['Supervision', '`/super-admin/audit/`, `/super-admin/finances/`', 'Audit '
     'et contrôle de gestion.'],
], widths=[3.2, 9.4, 4.4], size=8.4, header_size=8.6, first_col_bold=True)

h2('11.4', 'Navigation et cohérence des interfaces')
add_paragraph(
    'Chaque espace possède une navigation latérale dédiée (`_nav.html`) et un '
    'bandeau d’actions (hero). Les rôles transversaux partagent une navigation '
    'unifiée (`dashboard/admin/_nav.html`) qui donne accès à tous les modules. '
    'Les boutons d’écriture sont masqués pour les rôles qui n’y ont pas droit, '
    'mais le contrôle serveur reste la référence.'
)
add_paragraph(
    'Les listes proposent systématiquement une recherche et des filtres '
    'contextuels : statut, formation, période, caisse, catégorie, acteur. Les '
    'écrans vides affichent un message explicite plutôt qu’un tableau sans '
    'explication.'
)

h2('11.5', 'Documents imprimables')
add_table(['Document', 'Route', 'Contenu'], [
    ['Cahier de texte', '`/pedagogie/cahier-de-texte/<groupe>/imprimer/`',
     'En-tête officiel, formateur, filière, classe, cinq colonnes, totaux.'],
    ['Feuille de suivi étudiant', '`/etudiant/feuille/<groupe>/`', 'Dates, '
     'heures suivies, notions, présence, observations.'],
    ['Reçu de paiement', '`/comptabilite/recu/<paiement>/`', 'Référence, '
     'étudiant, formation, montant, moyen, solde restant.'],
], widths=[4, 7.4, 5.6], size=9, header_size=9, first_col_bold=True)

page_break()

# ===========================================================================
# 12. Architecture applicative
# ===========================================================================
h1('12', 'Architecture applicative et conventions')

h2('12.1', 'Arborescence')
code_block([
    'academy/',
    '├── manage.py',
    '├── univers_academy/          réglages, URLs racine, WSGI',
    '├── core/',
    '│   ├── models.py             35 modèles et propriétés métier',
    '│   ├── caisse.py             service unique d’écriture en caisse',
    '│                             (juger, poster, annuler, ajuster,',
    '│                              réinitialiser, corriger)',
    '│   ├── forms.py              formulaires et validation',
    '│   ├── decorators.py         contrôles d’accès — caisse à part :',
    '│                             `cash_write_required`',
    '│   ├── middleware.py         statut de compte',
    '│   ├── utils.py              audit, soldes, helpers',
    '│   ├── views.py             identité, dashboards, bourses, audit',
    '│   ├── views_accueil.py',
    '│   ├── views_secretariat.py',
    '│   ├── views_pedagogie.py',
    '│   ├── views_comptabilite.py',
    '│   ├── views_supervision.py',
    '│   ├── views_profile.py',
    '│   ├── urls.py',
    '│   ├── migrations/          0001 → 0014',
    '│   ├── management/commands/ audit_finances, audit_privileges,',
    '│   │                         create_superadmin, seed_demo, seed_roles,',
    '│   │                         importer_etudiants, importer_feuille,',
    '│   │                         importer_formations, mettre_en_attente,',
    '│   │                         compiler_traductions, verifier_i18n',
    '│   └── tests/               22 modules, 519 tests',
    '├── templates/',
    '│   ├── public/              accueil, login, register, bourses',
    '│   └── dashboard/           base, partiels, espaces par rôle',
    '├── static/                  CSS compilé, images, JS',
    '├── media/                   fichiers privés (non servis directement)',
    '├── docs/                    ce document et son générateur',
    '└── db.sqlite3               base de développement',
])

h2('12.2', 'Conventions de développement')
add_table(['Convention', 'Règle'], [
    ['Modèles', 'Évolution additive : nouveaux champs nullables ou avec '
     'valeur par défaut, jamais de suppression silencieuse.'],
    ['Migrations', 'Une migration par évolution, nommée et appliquée ; '
     '`makemigrations --check` doit rester vide.'],
    ['Vues', 'Un module `views_<domaine>.py` par domaine ; les helpers privés '
     'sont préfixés par `_`.'],
    ['Formulaires', 'Toute règle de saisie est dans `forms.py` ; la vue ne '
     'duplique que les contrôles d’objet.'],
    ['Gabarits', 'Un gabarit de base `base_dashboard.html`, des partiels '
     '`_stat.html`, `_form.html`, `_audit_trail.html`.'],
    ['Styles', 'Classes `ua-*` du thème ; Tailwind compilé dans '
     '`static/css/output.css`.'],
    ['Tests', 'Un fichier par domaine, héritant de `BusinessTestBase` ; base '
     'isolée et hasheur rapide.'],
], widths=[4, 13], size=9, header_size=9, first_col_bold=True)

h2('12.3', 'Composants transverses')
add_table(['Composant', 'Rôle'], [
    ['`role_required(*roles)`', 'Autorise les rôles listés et les rôles '
     'élevés ; redirige les comptes non actifs.'],
    ['`business_write_required(*roles)`', 'Interdit l’écriture aux rôles '
     'élevés et exige un rôle opérationnel.'],
    ['`cash_write_required(*roles)`', 'Garde des écrans de caisse : rôles '
     'listés et rôles élevés admis, autres rôles refusés avec message '
     'explicite.'],
    ['`super_admin_required`', 'Réserve une vue au SUPER_ADMIN.'],
    ['`active_account_required`', 'Vérifie le statut du compte.'],
    ['`log_audit(request, action, …)`', 'Écrit une entrée normalisée dans '
     '`AuditLog`.'],
    ['`outstanding_receivables()`', 'Calcule le reste à recouvrer dossier par '
     'dossier.'],
    ['`accounts_with_balance()`', 'Retourne les caisses, leur solde et leur '
     'disponible.'],
    ['`caisse.juger` / `caisse.poster`', 'Verdict puis écriture d’une '
     'mouvement de caisse, dans une transaction atomique — l’écran et le '
     'service rendent le même verdict.'],
    ['`serve_private_file`', 'Sert un fichier après contrôle d’accès.'],
], widths=[6, 11], size=9, header_size=9, first_col_bold=True)

h2('12.4', 'Commandes de gestion')
add_table(['Commande', 'Usage', 'Effet'], [
    ['`seed_roles`', 'Initialiser rôles et permissions.', 'Crée les 9 rôles, '
     '19 permissions et les associations.'],
    ['`seed_demo`', 'Charger un jeu de démonstration.', 'Mots de passe '
     'générés, affichés une seule fois.'],
    ['`create_superadmin`', 'Créer le premier administrateur.', 'Exige un '
     'secret d’environnement ; aucun compte privilégié par inscription.'],
    ['`audit_finances`', 'Contrôler la cohérence financière.', 'Signale '
     'trop-perçus, paiements sans caisse, écarts et soldes négatifs.'],
    ['`audit_privileges`', 'Contrôler les privilèges.', 'Signale les '
     'attributions à vérifier.'],
], widths=[3.8, 6.2, 7], size=9, header_size=9, first_col_bold=True)

h2('12.5', 'Dépendances et configuration')
add_paragraph(
    'Le projet repose sur Django 5.1, `django-cleanup` pour la suppression des '
    'fichiers orphelins, Tailwind CSS pour la compilation des styles et Clerk '
    'pour l’authentification optionnelle. Les réglages sensibles sont lus dans '
    '`.env` : `SECRET_KEY`, `DEBUG`, clés Clerk, backend e-mail et chemins de '
    'stockage.'
)

page_break()

# ===========================================================================
# 13. Qualité, tests et exploitation
# ===========================================================================
h1('13', 'Qualité, tests et exploitation')

h2('13.1', 'Stratégie de test')
add_paragraph(
    'Les tests sont des tests Django exécutés sur une base de test créée puis '
    'détruite. La base de production `db.sqlite3` n’est jamais touchée. Les '
    'tests couvrent les modèles, les formulaires, les vues, les permissions, '
    'les rendus et les effets d’audit. Les mots de passe utilisent un hasheur '
    'rapide uniquement pendant les tests.'
)

h2('13.2', 'Couverture par module')
test_rows = [
    ['`test_public.py`', '16', 'Landing, connexion locale prioritaire, code '
     'interne, inscription, rôles demandés, comptes bloqués.'],
    ['`test_auth_roles.py`', '31', 'Clerk, onboarding, approbation/refus, '
     'rôle suggéré, inscription automatique de l’étudiant, anti-doublon.'],
    ['`test_profile.py`', '22', 'Profil, avatar, mot de passe (session '
     'conservée, refus, compte sans mot de passe local), e-mail signé, échecs '
     'd’envoi.'],
    ['`test_photo_profil.py`', '12', 'Vignette sur les listes (photo ou '
     'initiales), pose par le secrétariat et par le SUPER_ADMIN, fichier '
     'remplacé effacé, statut inchangé, refus.'],
    ['`test_accueil.py`', '16', 'Visites, contacts, prospects, relances, '
     'motifs, recherche.'],
    ['`test_secretariat.py`', '15', 'Étudiants, conversion, inscriptions, '
     'remises, documents.'],
    ['`test_pedagogie.py`', '58', 'Modules, groupes, séances, présences, '
     'ressources, retours, fiches de cours, impressions.'],
    ['`test_comptabilite.py`', '111', 'Journal, CSV, opérations, transferts, '
     'soldes, clôtures, paiements, reçus, permissions, encaissement '
     'multi-mois, date de recette, solde de caisse jamais négatif, '
     'administration des comptes (état, découvert, archivage, historique), '
     'ajustement et réinitialisation traçables, catégories administrables, '
     'correction d’une écriture, disponible affiché et avertissement avant '
     'sortie.'],
    ['`test_permissions.py`', '46', 'Routage, accès croisés, rôles '
     'transversaux, lecture seule du métier sauf la caisse (journal, '
     'encaissement, clôture, comptes et catégories ouverts en écriture et '
     'audités), bourses, historiques, assistant administratif.'],
    ['`test_supervision.py`', '10', 'Supervision financière, indicateurs, '
     'reste à recouvrer, audit.'],
    ['`test_admin_access.py`', '9', 'Accès transversal ADMIN, refus des actes '
     'sensibles.'],
    ['`test_audit_finances.py`', '4', 'Cohérence financière.'],
    ['`test_user_access.py`', '30', 'Rôles, statuts, garde-fous, dernier '
     'super administrateur.'],
    ['`test_statut_etudiant.py`', '12', 'Statut par défaut de l’étudiant, '
     'approbation à la validation, reprise des fiches de classeur, aucune '
     'révocation automatique.'],
    ['`test_import_eleves.py`', '37', 'Vague 2 : comptes, groupes, '
     'inscriptions et paiements devenus exploitables ou refusés.'],
    ['`test_feuille_import.py`', '16', 'Rapprochement du journal de caisse '
     '« Contrôles Mensuels » avec les écritures.'],
    ['`test_importer_formations.py`', '15', 'Tarif lu dans les classeurs et '
     'portique de la vague 1.'],
    ['`test_data_tools.py`', '9', 'Lecteurs de classeurs : en-têtes, dates, '
     'montants, lignes vides.'],
    ['`test_editeur_permissions.py`', '10', 'Matrice postes × droits et son '
     'effet réel à l’écran.'],
    ['`test_graphiques.py`', '19', 'Séries numériques des graphiques de '
     'tableau de bord.'],
    ['`test_i18n_theme.py`', '17', 'Coquille bilingue, thème neutre, '
     'notifications empilées.'],
    ['`test_sans_melange.py`', '4', 'Aucun mélange de langue au rendu, page '
     'par page.'],
]
add_table(['Fichier', 'Tests', 'Périmètre'], test_rows,
          widths=[4.6, 2.2, 10.2], size=8.6, header_size=8.6,
          first_col_bold=True, align_center={1})
add_paragraph(
    'Total : 519 tests, 0 échec (04/11/2026). `manage.py check` est sans '
    'erreur et `makemigrations --check` ne signale aucun changement en '
    'attente : les modèles et les 14 migrations appliquées sont alignés.',
    bold_lead='Résultat de référence : ', size=10,
)

h2('13.3', 'Ce que les tests garantissent')
bullets([
    'Persistance réelle des formulaires et présence des entrées d’audit.',
    'Refus serveur (403) des accès et écritures non autorisés.',
    'Paiement partiel non soldé, trop-perçu refusé, double soumission '
    'bloquée.',
    'Transfert de caisse neutre au niveau global.',
    'Clôture : écart calculé et doublon refusé.',
    'Ressource brouillon invisible pour l’étudiant.',
    'Document téléchargeable uniquement par le propriétaire ou le staff.',
    'Fiche étudiant limitée à ses propres séances réalisées.',
    'Cahier de texte : accès formateur affecté, lecture seule des autres '
    'rôles, impression réservée.',
    'Compte suspendu bloqué même avec une session ouverte ; approbation '
    'effective sans reconnexion.',
    'Journal d’audit : liens d’entité valides, pagination conservant les '
    'filtres.',
    'Caisse : aucun solde sous le plancher, à l’écran comme au service ; '
    'découvert réservé au SUPER_ADMIN ; écriture antidatée sur période clôturée '
    'refusée.',
    'Disponible affiché avant toute sortie, avertissement à 80 % et case à '
    'cocher exigée ; recette et brouillon dispensés de ce second geste.',
    'Ajustement et réinitialisation : écriture contraire, motif obligatoire, '
    'rien n’est effacé, historique conservé.',
    'Comptes administrables : nom et ouverture figés après engagement, devise '
    'inchangée, archivage avec compte de remplacement.',
    'Rôles élevés : écriture ouverte sur la caisse et journalisée, lecture '
    'seule maintenue sur le reste du métier.',
])

h2('13.4', 'Exploitation courante')
add_table(['Tâche', 'Commande / action'], [
    ['Appliquer les migrations', '`manage.py migrate`'],
    ['Initialiser les rôles', '`manage.py seed_roles`'],
    ['Créer le premier super admin', '`manage.py create_superadmin` avec '
     '`SUPERADMIN_SETUP_SECRET`'],
    ['Contrôler la cohérence financière', '`manage.py audit_finances`'],
    ['Contrôler les privilèges', '`manage.py audit_privileges`'],
    ['Vérifier le projet', '`manage.py check` et `makemigrations --check`'],
    ['Lancer les tests', '`manage.py test core.tests`'],
    ['Sauvegarder', 'Base de données + répertoire `media/`'],
], widths=[6, 11], size=9, header_size=9, first_col_bold=True)

h2('13.5', 'Checklist de mise en production')
numbered([
    '`DEBUG=False`, `SECRET_KEY` longue, `ALLOWED_HOSTS` renseigné.',
    'HTTPS, HSTS, cookies sécurisés et redirection HTTP.',
    'Base PostgreSQL et sauvegardes testées.',
    'Comptes de démonstration désactivés ou mots de passe renouvelés.',
    'Attribution SUPER_ADMIN du compte Clerk vérifiée.',
    'Backend e-mail configuré et testé.',
    'Accès à l’admin Django restreint.',
    'Surveillance planifiée de `audit_finances` et `audit_privileges`.',
])

page_break()

# ===========================================================================
# 14. Limites et feuille de route
# ===========================================================================
h1('14', 'Limites connues et feuille de route')

add_paragraph(
    'Les éléments ci-dessous ne sont pas déclarés terminés. Ils sont conservés '
    'dans cette section pour éviter toute ambiguïté lors de la recette.'
)

h2('14.1', 'Limites fonctionnelles')
add_table(['Sujet', 'État actuel', 'Impact'], [
    ['Maintenance, missions et salaires', 'Catégories comptables existantes, '
     'pas de modèles ni de workflow dédiés.', 'Suivi par catégorie de sortie '
     'uniquement ; pas de masse salariale budgétée.'],
    ['Remboursement d’un paiement', 'Pas de workflow dédié ; l’annulation se '
     'fait au niveau de l’opération de caisse.', 'Le statut du `Payment` ne '
     'suit pas automatiquement.'],
    ['Modèle `Expense`', 'Hérité, éditable dans l’admin, sans effet sur les '
     'indicateurs.', 'Risque de saisie sans mouvement de caisse.'],
    ['Exports PDF', 'CSV pour le journal ; impression navigateur pour les '
     'fiches.', 'Pas de PDF serveur signé.'],
    ['Statistiques avancées', 'Totaux de base et graphiques Chart.js sur les '
     'trois tableaux de bord.', 'Pas de comparaison prévu/réalisé ni d’export '
     'des séries.'],
    ['Notifications', 'Notification interne ; e-mail fiable uniquement pour '
     'le changement d’adresse.', 'Pas d’envoi métier automatique.'],
    ['Clerk réel', 'Parcours simulé dans les tests.', 'Dépend de clés '
     'externes et d’un environnement connecté.'],
    ['Tests E2E', 'Tests Django uniquement.', 'Pas de test navigateur '
     'automatisé.'],
    ['Présence multi-séances', '`Attendance` unique par inscription et date.',
     'Deux séances le même jour ne peuvent pas avoir deux présences '
     'distinctes.'],
    ['Unicité du cahier de texte', 'Anti-doublon vérifié par le formulaire '
     '(groupe, date, heure de début), sans contrainte d’unicité en base.',
     'Deux saisies strictement simultanées pourraient créer un doublon ; une '
     'contrainte de base reste à ajouter.'],
    ['Brouillon de caisse', 'Un brouillon se saisit (il ne débite rien) mais '
     'aucun écran ne le valide.', 'Il reste à 0 en caisse jusqu’à sa reprise '
     'par l’écran d’opération ou par l’import ; les brouillons sont comptés '
     'avant une réinitialisation.'],
    ['Écritures concurrentes', 'La garde de solde s’appuie sur '
     '`transaction.atomic()` et un verrou de ligne ; SQLite ignore '
     '`select_for_update()`.', 'Sur la base de développement, deux saisies '
     'strictement simultanées restent théoriquement possibles ; sur PostgreSQL '
     '(cible de production), le verrouillage est réel.'],
], widths=[4.2, 7, 5.8], size=8.5, header_size=8.6, first_col_bold=True)

h2('14.2', 'Anomalies de données connues')
bullets([
    ('Trop-perçu.', 'Le dossier `etudiant@univers.academy` / « Les langues '
     'étrangères » (ex-« Anglais B2 », net 75 000 FCFA) porte 135 000 FCFA de '
     'paiements validés, soit 60 000 '
     'FCFA de trop-perçu. À régulariser manuellement ; `audit_finances` le '
     'signale.'),
    ('Solde de caisse négatif — régularisé.', 'Constaté le 01/11/2026 sur '
     '« Mobile Money » : deux sorties du 30/10/2026 (100 000 et 100 FCFA) '
     'avaient été portées sur ce portefeuille alors qu’il ne contenait aucune '
     'recette. Cause analysée avant correction — l’imputation était fausse, '
     'pas l’affichage. Régularisé le 04/11/2026 sur arbitrage de la direction '
     '(« ressaisir sur la Caisse principale ») : sorties annulées et motivées, '
     'ressaisies sur la caisse qui a payé ; la caisse solde à +50 000 FCFA pour '
     'une recette étudiante réellement encaissée dessus. `audit_finances` ne '
     'signale plus aucun solde négatif.'),
    ('Comptes de démonstration.', 'Les comptes `admin@univers.academy`, '
     '`secretaire@…`, `comptable@…`, `formateur@…`, `etudiant@…` et '
     '`accueil@…` ont encore leurs mots de passe par défaut.'),
    ('Compte Clerk privilégié.', '`japhetsamba52@gmail.com` est SUPER_ADMIN et '
     'lié à Clerk ; `audit_privileges` demande une vérification.'),
])

h2('14.3', 'Feuille de route proposée')
add_table(['Priorité', 'Chantier', 'Objectif'], [
    ['P0', 'Sécuriser la production', 'Désactiver les comptes de démo, '
     'renouveler les secrets, activer HTTPS/HSTS, vérifier le compte Clerk '
     'privilégié.'],
    ['P0', 'Régulariser le trop-perçu', 'Remboursement ou annulation tracée '
     'du dossier « Les langues étrangères ».'],
    ['P1', 'Workflow de remboursement', 'Rembourser un paiement en mettant à '
     'jour le dossier et la caisse, avec double audit.'],
    ['P1', 'Fiabiliser les notifications', 'Brancher un backend e-mail réel '
     'et tracer les envois.'],
    ['P2', 'Exports PDF signés', 'Générer les reçus, cahiers de texte et '
     'certificats en PDF.'],
    ['P2', 'Statistiques et pilotage', 'Tableaux de bord analytiques, '
     'graphiques, comparaison prévu/réalisé.'],
    ['P2', 'Workflows RH', 'Missions, maintenance, salaires et masse '
     'salariale.'],
], widths=[2, 5.4, 9.6], size=8.8, header_size=8.8, first_col_bold=True,
    align_center={0})

page_break()

# ===========================================================================
# Annexes
# ===========================================================================
h1('A', 'Glossaire')
add_table(['Terme', 'Définition'],
          [[term, definition] for term, definition in GLOSSARY],
          widths=[4.4, 12.6], size=9, header_size=9, first_col_bold=True)

page_break()

h1('B', 'Catalogue des routes')


def collect_routes():
    routes = []

    def walk(patterns, prefix='', namespace=''):
        for pattern in patterns:
            if hasattr(pattern, 'url_patterns'):
                ns = getattr(pattern, 'namespace', '') or namespace
                walk(pattern.url_patterns, prefix + str(pattern.pattern), ns)
                continue
            name = getattr(pattern, 'name', None)
            if not name:
                continue
            path = prefix + str(pattern.pattern)
            if path.startswith('admin/'):
                continue
            callback = getattr(pattern, 'callback', None)
            view_name = getattr(callback, '__name__', '')
            module = getattr(callback, '__module__', '').replace('core.', '')
            full_name = f'{namespace}:{name}' if namespace else name
            routes.append([path, full_name, f'{module}.{view_name}'])
    walk(get_resolver().url_patterns)
    return routes


route_rows = collect_routes()
add_paragraph(
    f'{len(route_rows)} routes nommées sont exposées par l’application '
    '(hors administration Django). Les routes sont regroupées par préfixe '
    'dans l’ordre de déclaration.',
    size=9.5,
)
add_table(['URL', 'Nom', 'Vue'], route_rows,
          widths=[8.2, 5.4, 3.4], size=7.2, header_size=7.5)

page_break()

h1('C', 'Catalogue des actions d’audit')
add_paragraph(
    'Les actions ci-dessous sont les codes écrits dans `AuditLog.action`. Ils '
    'servent de référence pour les filtres du journal et pour les contrôles '
    'automatisés.'
)
add_table(['Action', 'Domaine', 'Description'],
          [[action, domain, desc] for action, domain, desc in AUDIT_ACTIONS],
          widths=[5, 3.2, 8.8], size=8.4, header_size=8.5,
          first_col_bold=True)

page_break()

h1('D', 'Modèle de données détaillé')
add_paragraph(
    'Cette annexe est générée automatiquement à partir des modèles Django. '
    'Pour chaque modèle sont listés les champs concrets, leur type, leur '
    'libellé métier et leurs contraintes. Les champs `id` sont des UUID '
    'générés à la création.'
)

MODEL_ORDER = []
for _, _, models in DOMAINS:
    for name in models:
        if name not in MODEL_ORDER:
            MODEL_ORDER.append(name)
for model in MODELS:
    if model.__name__ not in MODEL_ORDER:
        MODEL_ORDER.append(model.__name__)

for name in MODEL_ORDER:
    model = MODEL_BY_NAME.get(name)
    if model is None:
        continue
    h2('D.' + str(MODEL_ORDER.index(name) + 1), name)
    add_paragraph(MODEL_DESCRIPTIONS.get(name, ''), size=9.5)
    add_table(['Champ', 'Type', 'Libellé', 'Contraintes'],
              field_rows(model),
              widths=[3.4, 4.8, 4.4, 4.4], size=7.6, header_size=7.8)

page_break()

h1('E', 'Correspondance fiches papier / écrans')

add_paragraph(
    'Cette annexe explicite la traduction des fiches papier dans le modèle de '
    'données. Elle sert de référence pour la formation des utilisateurs et '
    'pour toute évolution des formulaires.'
)

h2('E.1', 'Fiche du formateur (cahier de texte)')
add_table(['Champ papier', 'Champ applicatif', 'Écran / impression', 'Règle'], [
    ['Formateur', '`CourseSession.formateurs`', 'En-tête du cahier de texte',
     'Affectation au groupe ; lecture seule.'],
    ['Filière', '`Course.domain`', 'En-tête', 'Reprise du domaine de la '
     'formation.'],
    ['Classe', '`Course.title` + dates du groupe', 'En-tête',
     'Titre et période du groupe.'],
    ['Dates', '`SessionRecord.date`', 'Colonne « Dates »', 'Obligatoire.'],
    ['Heures', '`SessionRecord.planned_start/end` ou '
     '`actual_start/end`', 'Colonne « Heures »', 'Fin > début ; les heures '
     'réelles priment.'],
    ['Notions enseignées', '`SessionRecord.content_covered`', 'Colonne '
     '« Notions enseignées »', 'Obligatoire dans le cahier de texte.'],
    ['Nombre d’apprenants', '`SessionRecord.attendee_count`', 'Colonne '
     '« Nombre d’apprenants »', 'À défaut, déduit des présences.'],
    ['Observations', '`SessionRecord.notes`', 'Colonne « Observations »',
     'Libre.'],
], widths=[3.4, 5.4, 4.2, 4], size=8.4, header_size=8.4,
    first_col_bold=True)

h2('E.2', 'Fiche de l’étudiant')
add_table(['Champ papier', 'Champ applicatif', 'Écran / impression', 'Règle'], [
    ['Date', '`StudentSessionNote.session_record.date`', 'Fiche de cours',
     'Séance réalisée uniquement.'],
    ['Présence', '`StudentSessionNote.attended`', 'Case « J’étais présent »',
     'Déclaratif, distinct du pointage formateur.'],
    ['Heures suivies', '`followed_start` / `followed_end`', 'Champs horaires',
     'Fin > début.'],
    ['Notions retenues', '`notions_learned`', 'Zone de texte', 'Obligatoire.'],
    ['Difficultés', '`difficulties`', 'Zone de texte', 'Facultatif.'],
    ['Observations', '`observations`', 'Zone de texte', 'Facultatif.'],
], widths=[3.4, 5.4, 4.2, 4], size=8.4, header_size=8.4,
    first_col_bold=True)

h2('E.3', 'Feuille de présence')
add_table(['Champ papier', 'Champ applicatif', 'Écran', 'Règle'], [
    ['Date', '`Attendance.date`', 'Feuille de présence', 'Unique avec '
     'l’inscription.'],
    ['Statut', '`Attendance.status`', 'Présent / Absent / Retard / Excusé',
     'Valeurs contrôlées.'],
    ['Heure d’arrivée', '`arrival_time`', 'Champ heure', 'Utilisé pour un '
     'retard.'],
    ['Motif', '`absence_reason`', 'Champ texte', 'Pour absent ou excusé.'],
    ['Observation', '`note`', 'Champ texte', 'Libre.'],
], widths=[3.4, 5.4, 4.2, 4], size=8.4, header_size=8.4,
    first_col_bold=True)

h2('E.4', 'Reçu de paiement')
add_table(['Champ papier', 'Champ applicatif', 'Écran', 'Règle'], [
    ['Référence', '`Payment.reference`', 'Reçu', 'Unique, générée '
     'automatiquement.'],
    ['Étudiant', '`Enrollment.student`', 'Reçu', 'Propriétaire du dossier.'],
    ['Formation', '`Enrollment.session.course`', 'Reçu', 'Formation inscrite.'],
    ['Montant', '`Payment.amount`', 'Reçu', '≤ reste à payer.'],
    ['Moyen', '`Payment.method`', 'Reçu', 'Espèces, Mobile Money, virement, '
     'autre.'],
    ['Date', '`Payment.paid_at`', 'Reçu', 'Date et heure de l’encaissement.'],
    ['Reste à payer', '`Enrollment.balance_due`', 'Reçu', 'Recalculé après '
     'paiement.'],
], widths=[3.4, 5.4, 4.2, 4], size=8.4, header_size=8.4,
    first_col_bold=True)

page_break()

h1('F', 'Références et fichiers sources')

add_paragraph(
    'Les références ci-dessous permettent de retrouver l’implémentation de '
    'chaque partie du document.'
)
add_table(['Sujet', 'Fichier(s)'], [
    ['Modèles et règles de données', '`core/models.py`, `core/migrations/`'],
    ['Formulaires et validation', '`core/forms.py`'],
    ['Contrôles d’accès', '`core/decorators.py`, `core/middleware.py`'],
    ['Audit et calculs transverses', '`core/utils.py`'],
    ['Identité, dashboards, bourses, audit', '`core/views.py`'],
    ['Accueil et prospects', '`core/views_accueil.py`'],
    ['Scolarité', '`core/views_secretariat.py`'],
    ['Pédagogie, cahier de texte, fiches', '`core/views_pedagogie.py`'],
    ['Comptabilité', '`core/views_comptabilite.py`'],
    ['Supervision financière', '`core/views_supervision.py`'],
    ['Profil et avatar', '`core/views_profile.py`'],
    ['Vignette et carte photo', '`core/templatetags/ui.py`, '
     '`templates/dashboard/_vignette.html`, `_photo.html`'],
    ['Routes', '`core/urls.py`'],
    ['Gabarits', '`templates/public/`, `templates/dashboard/`'],
    ['Commandes', '`core/management/commands/`'],
    ['Tests', '`core/tests/`'],
    ['Validation métier', '`VALIDATION_METIER.md`'],
    ['Générateur de ce document', '`docs/generate_architecture_docx.py`'],
], widths=[5.6, 11.4], size=8.8, header_size=8.8, first_col_bold=True)

add_paragraph(
    'Fin du document. Pour régénérer ce fichier après une évolution du code : '
    'exécuter `docs/generate_architecture_docx.py` depuis la racine du projet.',
    italic=True, size=9, color=GREY, space_after=0,
)

# ===========================================================================
# Sauvegarde
# ===========================================================================
os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
doc.save(OUTPUT)
print(f'Document généré : {OUTPUT}')
print(f'Modèles : {len(MODELS)} — routes : {len(route_rows)} — '
      f'tests de référence : {sum(int(ligne[1]) for ligne in test_rows)}')
