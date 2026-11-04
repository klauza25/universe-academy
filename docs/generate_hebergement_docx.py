# -*- coding: utf-8 -*-
"""Génère la note d'hébergement d'Univers Academy (DOCX puis PDF).

Le document reprend les contraintes réelles du projet (Django 5.1, Clerk,
media locaux, PostgreSQL prêt via DATABASE_URL) et compare quatre scénarios
d'hébergement, avec une recommandation chiffrée.
"""
import os

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

TODAY = '3 novembre 2026'
OUT = os.path.join('docs', 'Hebergement_Univers_Academy.docx')

INK = RGBColor(0x1E, 0x20, 0x44)
MUTED = RGBColor(0x6D, 0x71, 0x9B)
BRAND = RGBColor(0x46, 0x46, 0xD6)
HEAD_FILL = 'ECEBFE'
ZEBRA_FILL = 'F7F7FE'
WARNING_FILL = 'FDF1DF'
GREEN_FILL = 'E6F8EF'


# ---------------------------------------------------------------------------
# Helpers de mise en forme
# ---------------------------------------------------------------------------

def shade(cell, hex_color):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), hex_color)
    tc_pr.append(shd)


def cell_text(cell, text, *, bold=False, size=9.2, color=None,
              align=None, italic=False):
    cell.text = ''
    paragraph = cell.paragraphs[0]
    if align is not None:
        paragraph.alignment = align
    run = paragraph.add_run(text)
    run.bold = bold
    run.italic = italic
    run.font.size = Pt(size)
    run.font.name = 'Calibri'
    if color is not None:
        run.font.color.rgb = color
    cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER


def set_widths(table, widths_cm):
    table.autofit = False
    for row in table.rows:
        for index, width in enumerate(widths_cm):
            row.cells[index].width = Cm(width)


def table(headers, rows, widths, *, font=9.2, header_font=9.0,
          zebra=True, align_center=(), fills=None):
    grid = doc.add_table(rows=1, cols=len(headers))
    grid.style = 'Table Grid'
    grid.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for index, label in enumerate(headers):
        cell = grid.rows[0].cells[index]
        shade(cell, HEAD_FILL)
        cell_text(cell, label, bold=True, size=header_font,
                  color=BRAND,
                  align=WD_ALIGN_PARAGRAPH.CENTER if index in align_center
                  else None)
    for row_index, values in enumerate(rows):
        cells = grid.add_row().cells
        for index, value in enumerate(values):
            if fills and row_index < len(fills) and fills[row_index]:
                shade(cells[index], fills[row_index])
            elif zebra and row_index % 2 == 1:
                shade(cells[index], ZEBRA_FILL)
            cell_text(
                cells[index], str(value), size=font,
                align=WD_ALIGN_PARAGRAPH.CENTER if index in align_center
                else None,
            )
    set_widths(grid, widths)
    doc.add_paragraph()
    return grid


def bullet(text, bold_prefix=None):
    paragraph = doc.add_paragraph(style='List Bullet')
    paragraph.paragraph_format.space_after = Pt(3)
    if bold_prefix:
        run = paragraph.add_run(bold_prefix)
        run.bold = True
        run.font.size = Pt(10.5)
        run.font.color.rgb = INK
    run = paragraph.add_run(text)
    run.font.size = Pt(10.5)
    run.font.color.rgb = INK


def para(text, *, size=10.5, color=INK, space_after=8, italic=False,
         align=None):
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.space_after = Pt(space_after)
    if align is not None:
        paragraph.alignment = align
    run = paragraph.add_run(text)
    run.font.size = Pt(size)
    run.font.color.rgb = color
    run.italic = italic
    return paragraph


def h1(number, text):
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.space_before = Pt(18)
    paragraph.paragraph_format.space_after = Pt(8)
    run = paragraph.add_run(f'{number}.  {text}' if number else text)
    run.bold = True
    run.font.size = Pt(15)
    run.font.color.rgb = BRAND
    run.font.name = 'Calibri'
    return paragraph


def h2(text):
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.space_before = Pt(10)
    paragraph.paragraph_format.space_after = Pt(4)
    run = paragraph.add_run(text)
    run.bold = True
    run.font.size = Pt(11.5)
    run.font.color.rgb = INK
    return paragraph


def note(text, fill=WARNING_FILL):
    box = doc.add_table(rows=1, cols=1)
    box.style = 'Table Grid'
    cell = box.rows[0].cells[0]
    shade(cell, fill)
    cell.text = ''
    paragraph = cell.paragraphs[0]
    paragraph.paragraph_format.space_before = Pt(4)
    paragraph.paragraph_format.space_after = Pt(4)
    run = paragraph.add_run(text)
    run.font.size = Pt(9.8)
    run.font.color.rgb = INK
    set_widths(box, [17.0])
    doc.add_paragraph()


def monospace(lines):
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.space_before = Pt(4)
    paragraph.paragraph_format.space_after = Pt(10)
    paragraph.paragraph_format.left_indent = Cm(0.4)
    for index, line in enumerate(lines):
        run = paragraph.add_run(line)
        run.font.name = 'Consolas'
        run.font.size = Pt(8.8)
        run.font.color.rgb = INK
        if index < len(lines) - 1:
            run.add_break()


def add_page_number_footer(section):
    paragraph = section.footer.paragraphs[0]
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run('Univers Academy — note d’hébergement · page ')
    run.font.size = Pt(8)
    run.font.color.rgb = MUTED
    field = OxmlElement('w:fldSimple')
    field.set(qn('w:instr'), 'PAGE')
    paragraph._p.append(field)


# ---------------------------------------------------------------------------
# Document
# ---------------------------------------------------------------------------

doc = Document()

style = doc.styles['Normal']
style.font.name = 'Calibri'
style.font.size = Pt(10.5)
style.font.color.rgb = INK
style.paragraph_format.line_spacing = 1.08

section = doc.sections[0]
section.top_margin = Cm(2.0)
section.bottom_margin = Cm(1.9)
section.left_margin = Cm(2.0)
section.right_margin = Cm(2.0)
add_page_number_footer(section)


# ---- Couverture légère -----------------------------------------------------

cover = doc.add_paragraph()
cover.paragraph_format.space_before = Pt(40)
run = cover.add_run('UNIVERS ACADEMY')
run.bold = True
run.font.size = Pt(11)
run.font.color.rgb = MUTED
run.font.name = 'Calibri'

title = doc.add_paragraph()
title.paragraph_format.space_after = Pt(4)
run = title.add_run('Hébergement de la plateforme')
run.bold = True
run.font.size = Pt(26)
run.font.color.rgb = BRAND

subtitle = doc.add_paragraph()
subtitle.paragraph_format.space_after = Pt(18)
run = subtitle.add_run(
    'Solutions comparées, recommandation chiffrée et mise en production'
)
run.font.size = Pt(13)
run.font.color.rgb = MUTED

meta = doc.add_paragraph()
run = meta.add_run(f'Note technique · {TODAY} · version 1.0')
run.font.size = Pt(9.5)
run.font.color.rgb = MUTED

rule = doc.add_paragraph()
rule.paragraph_format.space_after = Pt(14)
p_pr = rule._p.get_or_add_pPr()
p_bdr = OxmlElement('w:pBdr')
bottom = OxmlElement('w:bottom')
bottom.set(qn('w:val'), 'single')
bottom.set(qn('w:sz'), '8')
bottom.set(qn('w:space'), '1')
bottom.set(qn('w:color'), '4646D6')
p_bdr.append(bottom)
p_pr.append(p_bdr)

para(
    'Cette note compare quatre familles d’hébergement pour la plateforme '
    'de gestion d’Univers Academy, en tenant compte du code réel du projet : '
    'Django 5.1, PostgreSQL déjà préparé, fichiers media locaux, '
    'authentification Clerk et un volume d’utilisation de petite structure. '
    'Elle se termine par une recommandation, un budget et une liste de '
    'contrôles à passer avant l’ouverture au public.'
)


# ---- 1. Contraintes --------------------------------------------------------

h1('1', 'Contraintes techniques du projet')

para(
    'Le choix d’hébergement ne peut pas être générique : quatre '
    'caractéristiques du dépôt imposent des exigences précises.'
)

table(
    ['Élément du projet', 'Exigence d’hébergement'],
    [
        ['Django 5.1 / Python 3.13',
         'Serveur WSGI (gunicorn) derrière un reverse proxy HTTPS ; '
         'aucun mode « fichier statique » suffisant.'],
        ['`dj-database-url` et `psycopg2-binary` déjà présents',
         'PostgreSQL activable par simple variable `DATABASE_URL`, sans '
         'modification de code.'],
        ['Media locaux : avatars, documents jusqu’à 10 Mo',
         'Disque persistant **obligatoire**, ou stockage objet S3. '
         'Un disque éphémère perd les fichiers à chaque déploiement.'],
        ['Clerk (Google et e-mail / mot de passe)',
         'HTTPS, domaine public et origines autorisées ; les clés '
         'publishable et secrète passent par l’environnement.'],
        ['E-mails transactionnels',
         'SMTP réel (Brevo, Resend, Mailgun) : le backend console du '
         'développement n’envoie rien.'],
    ],
    [6.4, 10.6],
)

note(
    'À éviter absolument : les offres gratuites à disque éphémère '
    '(Render gratuit, essai Railway, Heroku Eco sans disque). La base '
    'SQLite `db.sqlite3` et le dossier `media/` seraient perdus à chaque '
    'redéploiement ou redémarrage.'
)


# ---- 2. Comparatif ---------------------------------------------------------

h1('2', 'Comparatif des quatre scénarios')

table(
    ['Scénario', 'Exemples', 'Coût / mois', 'Effort', 'Latence Congo',
     'Verdict'],
    [
        ['VPS + Coolify', 'Hetzner CX22, Contabo VPS S, OVH VPS',
         '4 – 7 €', 'Moyen (1 jour)', '100 – 150 ms',
         'Meilleur rapport qualité / prix'],
        ['PaaS managé', 'Render, Railway, Fly.io, DO App Platform',
         '12 – 20 $', 'Faible', '100 – 150 ms', 'Simple, plus coûteux'],
        ['Cloud régional', 'AWS af-south-1 (Le Cap), Azure South Africa North',
         '25 – 60 $', 'Élevé', '60 – 90 ms',
         'Si budget et exigence de latence'],
        ['Django clé en main', 'PythonAnywhere', '5 $', 'Très faible',
         '≈ 150 ms', 'Correct pour démarrer, peu évolutif'],
    ],
    [2.6, 4.4, 2.0, 2.4, 2.4, 3.2],
    font=8.8, header_font=8.8, align_center={2, 3, 4},
)


# ---- 3. Détail des scénarios ----------------------------------------------

h1('3', 'Détail des scénarios')

h2('A. VPS + Coolify — recommandé')
bullet('Hetzner CX22 (2 vCPU, 4 Go, 40 Go SSD) ≈ 4 €/mois, ou Contabo '
       'VPS S (4 vCPU, 8 Go) ≈ 5,50 €/mois.', 'Serveur : ')
bullet('Coolify, PaaS auto-hébergé : déploiement Git, certificats '
       'Let’s Encrypt, PostgreSQL, sauvegardes et journaux, sans gérer '
       'nginx à la main.', 'Déploiement : ')
bullet('Coolify → gunicorn (2 à 3 workers) → PostgreSQL 16 → volume '
       '`media/`. Le tout sur une seule machine, sauvegardée chaque nuit.',
       'Architecture : ')
bullet('données maîtrisées, coût fixe et prévisible, montée en charge '
       'simple (CX32 à 7 €/mois), aucune limite d’offre gratuite.',
       'Avantages : ')
bullet('une journée d’installation initiale et une surveillance minimale '
       '(mises à jour de sécurité, sauvegardes).', 'Contrepartie : ')

h2('B. PaaS managé — sans administrer de serveur')
bullet('Web Service Starter 7 $ + PostgreSQL 6 $ + disque persistant '
       '1 Go (0,25 $/Go).', 'Render : ')
bullet('environ 5 $ de base plus consommation ; volume persistant '
       'disponible.', 'Railway : ')
bullet('machines et volume ; trafic africain possible via la région '
       'de Johannesburg.', 'Fly.io : ')
bullet('`git push` déclenche le déploiement, TLS et sauvegardes gérées ; '
       'coût deux à trois fois supérieur à un VPS équivalent.',
       'Bilan : ')

h2('C. Cloud régional — pour la latence')
bullet('instance `t4g.small` ≈ 12 $ + RDS PostgreSQL ≈ 15 $ ; latence '
       'nettement meilleure depuis Brazzaville (60 à 90 ms).',
       'AWS `af-south-1` (Le Cap) : ')
bullet('équivalent, intéressant si l’organisation dispose déjà d’un '
       'tenant Microsoft 365.', 'Azure South Africa North (Johannesburg) : ')
bullet('à réserver à une phase où la latence gêne réellement les '
       'utilisateurs (saisie du cahier de texte, formulaires).',
       'Quand l’envisager : ')

h2('D. PythonAnywhere — démarrage rapide')
bullet('5 $/mois, SQLite accepté, domaine personnalisé, aucune '
       'administration serveur.', 'Offre : ')
bullet('pas de PostgreSQL managé performant, peu de contrôle, montée '
       'en charge limitée.', 'Limites : ')


# ---- 4. Recommandation -----------------------------------------------------

h1('4', 'Recommandation')

para(
    'Pour une académie de quelques dizaines à quelques centaines '
    'd’utilisateurs, la combinaison la plus équilibrée est un VPS '
    'européen piloté par Coolify, avec PostgreSQL et un volume de media '
    'sauvegardé. Budget cible : 6 à 10 € par mois, domaine compris.'
)

monospace([
    'Cloudflare (DNS + cache + TLS)',
    '            |',
    '   Hetzner CX22 (Coolify)',
    '        |-- conteneur Django (gunicorn, 3 workers)',
    '        |-- PostgreSQL 16 (volume dedie)',
    '        |-- volume /app/media (avatars, documents)',
    '        `-- sauvegarde quotidienne (pg_dump + rsync)',
    '            -> Backblaze B2 ou Cloudflare R2',
])

h2('Budget de la solution recommandée')
table(
    ['Poste', 'Choix', 'Coût'],
    [
        ['Serveur', 'Hetzner CX22 (2 vCPU, 4 Go, 40 Go SSD)',
         '≈ 4 €/mois'],
        ['Déploiement', 'Coolify (auto-hébergé, open source)', '0 €'],
        ['Base de données', 'PostgreSQL 16 sur le même serveur', '0 €'],
        ['Media et sauvegardes', 'Volume local + copie R2 ou B2',
         '0 – 1 €/mois'],
        ['DNS et CDN', 'Cloudflare (offre gratuite)', '0 €'],
        ['Nom de domaine', '`.com` ou `.cg`, renouvellement annuel',
         '10 – 15 €/an'],
        ['Total', 'Hors domaine', '6 – 10 €/mois'],
    ],
    [3.6, 10.0, 3.4],
    fills=[None, None, None, None, None, None, GREEN_FILL],
)

para(
    'PostgreSQL est retenu dès la mise en production : SQLite ne gère pas '
    'correctement deux écritures concurrentes, alors que la plateforme '
    'enregistre paiements, présences et cahiers de texte en parallèle. '
    'Le passage se fait par la variable `DATABASE_URL`, déjà prise en '
    'charge par le projet.'
)

note(
    'Si plusieurs instances applicatives sont prévues, remplacer le volume '
    'local par un stockage objet compatible S3 (Cloudflare R2 ou Backblaze '
    'B2) branché via `django-storages`. Le reste de l’architecture ne change '
    'pas.',
    fill=HEAD_FILL,
)


# ---- 5. Mise en production -------------------------------------------------

h1('5', 'Contrôles avant l’ouverture au public')

para(
    'Ces points sont déjà signalés dans `VALIDATION_METIER.md` ; plusieurs '
    'sont bloquants pour une mise en ligne sereine.'
)

table(
    ['#', 'Point', 'Action attendue', 'Criticité'],
    [
        ['1', 'Configuration', '`DEBUG=False`, `SECRET_KEY` et '
         '`ALLOWED_HOSTS` renseignés, `CSRF_TRUSTED_ORIGINS` avec le '
         'domaine HTTPS.', 'Bloquant'],
        ['2', 'Comptes de démonstration', 'Supprimer ou changer les mots '
         'de passe par défaut (`admin@`, `comptable@`, `secretaire@`, etc.).',
         'Bloquant'],
        ['3', 'Compte Clerk privilégié', 'Vérifier l’attribution '
         'SUPER_ADMIN de `japhetsamba52@gmail.com`.', 'Haute'],
        ['4', 'Serveur d’application', 'Ajouter gunicorn et WhiteNoise '
         '(ou nginx) ; lancer `collectstatic` au déploiement.', 'Bloquant'],
        ['5', 'Sauvegardes', 'Sauvegarde quotidienne **et** restauration '
         'testée, pas seulement planifiée.', 'Bloquant'],
        ['6', 'Données financières', 'Régulariser le trop-perçu '
         '« Anglais B2 » (60 000 FCFA) et le solde Mobile Money négatif '
         '(−5 100 FCFA).', 'Haute'],
        ['7', 'Clerk', 'Associer le domaine de production et les origines '
         'autorisées ; vérifier les clés.', 'Bloquant'],
        ['8', 'E-mail', 'Configurer un SMTP réel (Brevo, Resend, '
         'Mailgun) et tester un envoi.', 'Moyenne'],
    ],
    [0.9, 4.2, 9.4, 2.5],
    font=8.8, header_font=8.8, align_center={0, 3},
)


# ---- 6. Prochaines étapes --------------------------------------------------

h1('6', 'Prochaines étapes')

para('Selon le scénario retenu, les livrables suivants peuvent être '
     'préparés dans le dépôt :')
bullet('Dockerfile et `docker-compose.yml` (Django + PostgreSQL) prêts '
       'pour Coolify ;', 'Conteneurisation : ')
bullet('gunicorn, WhiteNoise, `dj-database-url`, stockage S3 ;',
       'Dépendances de production : ')
bullet('sécurité, media, e-mail et Clerk ;',
       '`settings/production.py` : ')
bullet('DNS, certificats, premier déploiement, sauvegardes et '
       'restauration.', 'Guide pas à pas : ')

para(
    'Deux informations suffisent pour trancher : le budget mensuel accepté '
    'et la préférence entre administrer un serveur ou déléguer à une '
    'plateforme clé en main.',
    italic=True, color=MUTED,
)


doc.save(OUT)
print('Document généré :', os.path.abspath(OUT))
