# -*- coding: utf-8 -*-
"""Génère le mode d'emploi d'Univers Academy (DOCX puis PDF).

Le guide décrit les écrans réellement présents dans le projet, rôle par rôle,
de la connexion à l'encaissement. Il reprend la mise en forme de la note
d'hébergement (mêmes couleurs, mêmes helpers) pour rester cohérent.
"""
import os

from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

TODAY = '3 novembre 2026'
OUT = os.path.join('docs', 'Mode_emploi_Univers_Academy.docx')

INK = RGBColor(0x1E, 0x20, 0x44)
MUTED = RGBColor(0x6D, 0x71, 0x9B)
BRAND = RGBColor(0x46, 0x46, 0xD6)
HEAD_FILL = 'ECEBFE'
ZEBRA_FILL = 'F7F7FE'
WARNING_FILL = 'FDF1DF'
GREEN_FILL = 'E6F8EF'
BLUE_FILL = 'EAF2FF'


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


def cell_text(cell, text, *, bold=False, size=9.0, color=None,
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


def set_widths(table_obj, widths_cm):
    table_obj.autofit = False
    for row in table_obj.rows:
        for index, width in enumerate(widths_cm):
            row.cells[index].width = Cm(width)


def table(headers, rows, widths, *, font=9.0, header_font=8.8,
          zebra=True, align_center=(), fills=None, bold_first=False):
    grid = doc.add_table(rows=1, cols=len(headers))
    grid.style = 'Table Grid'
    grid.alignment = WD_ALIGN_PARAGRAPH.CENTER
    header_row = grid.rows[0]
    tr_pr = header_row._tr.get_or_add_trPr()
    header_flag = OxmlElement('w:tblHeader')
    header_flag.set(qn('w:val'), 'true')
    tr_pr.append(header_flag)
    for index, label in enumerate(headers):
        cell = header_row.cells[index]
        shade(cell, HEAD_FILL)
        cell_text(cell, label, bold=True, size=header_font, color=BRAND,
                  align=WD_ALIGN_PARAGRAPH.CENTER if index in align_center
                  else None)
    for row_index, values in enumerate(rows):
        row = grid.add_row()
        row_tr_pr = row._tr.get_or_add_trPr()
        cant_split = OxmlElement('w:cantSplit')
        row_tr_pr.append(cant_split)
        cells = row.cells
        for index, value in enumerate(values):
            if fills and row_index < len(fills) and fills[row_index]:
                shade(cells[index], fills[row_index])
            elif zebra and row_index % 2 == 1:
                shade(cells[index], ZEBRA_FILL)
            cell_text(
                cells[index], str(value), size=font,
                bold=bold_first and index == 0,
                align=WD_ALIGN_PARAGRAPH.CENTER if index in align_center
                else None,
            )
    set_widths(grid, widths)
    doc.add_paragraph()
    return grid


def bullet(text, bold_prefix=None, *, size=10.2):
    paragraph = doc.add_paragraph(style='List Bullet')
    paragraph.paragraph_format.space_after = Pt(2)
    if bold_prefix:
        run = paragraph.add_run(bold_prefix)
        run.bold = True
        run.font.size = Pt(size)
        run.font.color.rgb = INK
    run = paragraph.add_run(text)
    run.font.size = Pt(size)
    run.font.color.rgb = INK


def step(number, text, bold_prefix=None):
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.left_indent = Cm(0.55)
    paragraph.paragraph_format.first_line_indent = Cm(-0.55)
    paragraph.paragraph_format.space_after = Pt(3)
    run = paragraph.add_run(f'{number}.  ')
    run.bold = True
    run.font.size = Pt(10.2)
    run.font.color.rgb = BRAND
    if bold_prefix:
        run = paragraph.add_run(bold_prefix)
        run.bold = True
        run.font.size = Pt(10.2)
        run.font.color.rgb = INK
    run = paragraph.add_run(text)
    run.font.size = Pt(10.2)
    run.font.color.rgb = INK


def para(text, *, size=10.2, color=INK, space_after=7, italic=False,
         align=None, bold=False):
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.space_after = Pt(space_after)
    if align is not None:
        paragraph.alignment = align
    run = paragraph.add_run(text)
    run.font.size = Pt(size)
    run.font.color.rgb = color
    run.italic = italic
    run.bold = bold
    return paragraph


def h1(number, text, *, new_page=True):
    if new_page:
        doc.add_page_break()
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.space_before = Pt(2)
    paragraph.paragraph_format.space_after = Pt(8)
    run = paragraph.add_run(f'{number}.  {text}' if number else text)
    run.bold = True
    run.font.size = Pt(16)
    run.font.color.rgb = BRAND
    run.font.name = 'Calibri'
    rule = doc.add_paragraph()
    rule.paragraph_format.space_after = Pt(10)
    p_pr = rule._p.get_or_add_pPr()
    p_bdr = OxmlElement('w:pBdr')
    bottom = OxmlElement('w:bottom')
    bottom.set(qn('w:val'), 'single')
    bottom.set(qn('w:sz'), '6')
    bottom.set(qn('w:space'), '1')
    bottom.set(qn('w:color'), 'C9C9F5')
    p_bdr.append(bottom)
    p_pr.append(p_bdr)
    return paragraph


def h2(text):
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.space_before = Pt(11)
    paragraph.paragraph_format.space_after = Pt(4)
    paragraph.paragraph_format.keep_with_next = True
    run = paragraph.add_run(text)
    run.bold = True
    run.font.size = Pt(11.5)
    run.font.color.rgb = INK
    return paragraph


def h3(text):
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.space_before = Pt(7)
    paragraph.paragraph_format.space_after = Pt(3)
    paragraph.paragraph_format.keep_with_next = True
    run = paragraph.add_run(text)
    run.bold = True
    run.font.size = Pt(10.2)
    run.font.color.rgb = BRAND
    return paragraph


def note(text, fill=WARNING_FILL, title=None):
    box = doc.add_table(rows=1, cols=1)
    box.style = 'Table Grid'
    cell = box.rows[0].cells[0]
    shade(cell, fill)
    cell.text = ''
    paragraph = cell.paragraphs[0]
    paragraph.paragraph_format.space_before = Pt(4)
    paragraph.paragraph_format.space_after = Pt(4)
    if title:
        run = paragraph.add_run(f'{title} — ')
        run.bold = True
        run.font.size = Pt(9.6)
        run.font.color.rgb = INK
    run = paragraph.add_run(text)
    run.font.size = Pt(9.6)
    run.font.color.rgb = INK
    set_widths(box, [17.0])
    doc.add_paragraph()


def add_page_number_footer(section):
    paragraph = section.footer.paragraphs[0]
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run('Univers Academy — mode d’emploi · page ')
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
style.font.size = Pt(10.2)
style.font.color.rgb = INK
style.paragraph_format.line_spacing = 1.1

section = doc.sections[0]
section.top_margin = Cm(2.0)
section.bottom_margin = Cm(1.9)
section.left_margin = Cm(2.0)
section.right_margin = Cm(2.0)
add_page_number_footer(section)


# ---- Couverture ------------------------------------------------------------

cover = doc.add_paragraph()
cover.paragraph_format.space_before = Pt(34)
run = cover.add_run('UNIVERS ACADEMY')
run.bold = True
run.font.size = Pt(11)
run.font.color.rgb = MUTED
run.font.name = 'Calibri'

title = doc.add_paragraph()
title.paragraph_format.space_after = Pt(4)
run = title.add_run('Mode d’emploi\nde la plateforme')
run.bold = True
run.font.size = Pt(28)
run.font.color.rgb = BRAND

subtitle = doc.add_paragraph()
subtitle.paragraph_format.space_after = Pt(16)
run = subtitle.add_run(
    'Guide utilisateur par rôle : de la connexion au reçu de paiement'
)
run.font.size = Pt(13)
run.font.color.rgb = MUTED

meta = doc.add_paragraph()
run = meta.add_run(f'Guide utilisateur · {TODAY} · version 1.0')
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
    'Ce guide explique, écran par écran, comment utiliser la plateforme de '
    'gestion d’Univers Academy. Il s’adresse à tous les utilisateurs : '
    'étudiants, formateurs, secrétariat, guichet, comptabilité, direction, '
    'responsable pédagogique, administrateurs. Chaque chapitre suit un '
    'parcours réel, avec les boutons à cliquer, les règles à respecter et les '
    'messages d’erreur les plus fréquents.'
)

para(
    'Les intitulés de menus et de boutons sont ceux de l’application. Les '
    'adresses indiquées sont relatives au nom de domaine de l’académie : '
    'par exemple, « /dashboard/comptabilite/ » correspond à '
    '« https://votre-domaine/dashboard/comptabilite/ ».'
)

note(
    'La plateforme enregistre les données réelles de l’académie. Toute '
    'création, modification, validation ou annulation est conservée dans le '
    'journal d’audit avec l’auteur et l’horodatage. En cas de doute sur une '
    'manipulation, arrêtez-vous et demandez confirmation plutôt que de '
    'corriger « à l’essai ».',
    title='Avant d’utiliser la plateforme',
)

# ---- Sommaire --------------------------------------------------------------

h1('', 'Sommaire', new_page=True)

table(
    ['Chapitre', 'Ce que vous y trouverez'],
    [
        ['1. Avant de commencer', 'Prérequis, vocabulaire et logique générale.'],
        ['2. Se connecter', 'Les deux moyens de connexion, la déconnexion, les comptes bloqués.'],
        ['3. Créer un compte ou demander un accès', 'Inscription publique, demande d’accès et décision.'],
        ['4. Comprendre l’espace de travail', 'Menus, tableau de bord, profil, notifications.'],
        ['5. Qui fait quoi', 'Matrice des rôles et séparation des pouvoirs.'],
        ['6. Parcours étudiant', 'Cours, ressources, présences, fiches de cours, paiements.'],
        ['7. Parcours formateur', 'Groupes, séances, cahier de texte, présences, progression.'],
        ['8. Parcours secrétariat', 'Étudiants, inscriptions, documents, dossiers.'],
        ['9. Accueil et guichet', 'Visites, prospects, relances, ouverture de dossier.'],
        ['10. Comptabilité et encaissement', 'Journal, caisses, clôtures, paiements, reçus.'],
        ['11. Direction', 'Pilotage, validation des inscriptions, contrôle.'],
        ['12. Responsable pédagogique', 'Programmes, groupes, suivi et demandes d’accès.'],
        ['13. Administration et super administration', 'Utilisateurs, rôles, permissions, audit, bourses.'],
        ['14. Bourses', 'Candidature publique, suivi et instruction du dossier.'],
        ['15. Documents et impressions', 'Reçus, cahier de texte, feuilles de suivi.'],
        ['16. Messages fréquents', 'Comprendre une erreur et la corriger.'],
        ['17. Bonnes pratiques et sécurité', 'Réflexes à garder au quotidien.'],
        ['Annexes A à D', 'Matrice des écrans, adresses, checklists, glossaire.'],
    ],
    [6.2, 10.8],
    font=9.3, header_font=9.0, bold_first=True,
)


# ===========================================================================
# 1. Avant de commencer
# ===========================================================================

h1('1', 'Avant de commencer')

para(
    'La plateforme couvre l’ensemble du cycle d’un apprenant : accueil, '
    'inscription, encaissement, pédagogie, présences, documents et pilotage. '
    'Elle fonctionne dans un navigateur récent (Chrome, Edge, Firefox ou '
    'Safari), sans installation. Les écrans s’adaptent au téléphone, mais les '
    'tableaux de gestion se lisent mieux sur un ordinateur.'
)

h2('1.1 Ce qu’il faut avoir')

bullet('un navigateur à jour et une connexion Internet stable ;', 'Matériel : ')
bullet('les identifiants remis par l’administration (adresse e-mail ou '
       'identifiant interne, plus mot de passe) ;', 'Accès : ')
bullet('pour un étudiant, son groupe et sa formation doivent être créés '
       'avant sa première connexion ;', 'Dossier : ')
bullet('pour la caisse, un navigateur sur ordinateur et une imprimante pour '
       'les reçus.', 'Encaissement : ')

h2('1.2 Le vocabulaire de la plateforme')

table(
    ['Terme', 'Ce qu’il désigne dans l’application'],
    [
        ['Formation / cours', 'Le programme enseigné : anglais, bureautique, etc.'],
        ['Filière / domaine', 'La famille de la formation (langues, informatique…).'],
        ['Groupe (session)', 'Une classe concrète : une formation, une période, des horaires et des formateurs.'],
        ['Séance', 'Un cours daté, avec ses horaires prévus et réels, son contenu et son compte rendu.'],
        ['Inscription (dossier)', 'Le lien entre un étudiant et un groupe, avec un tarif, une remise et un net à payer.'],
        ['Net dû', 'Tarif moins remise : le montant total que l’étudiant doit pour ce dossier.'],
        ['Reste à payer', 'Net dû moins les paiements validés. C’est le plafond encaissable.'],
        ['Encaissement', 'Un paiement étudiant, rattaché à une inscription et à une caisse.'],
        ['Caisse / compte', 'Le contenant physique ou mobile qui reçoit ou verse l’argent.'],
        ['Clôture', 'Le contrôle de fin de journée : solde théorique comparé au montant compté.'],
        ['Visite', 'Le passage d’une personne à l’accueil, avant ou sans inscription.'],
        ['Prospect', 'Un contact intéressé, suivi avec des relances jusqu’à l’inscription.'],
        ['Rôle', 'Le métier de l’utilisateur : il détermine les menus et les actions autorisées.'],
        ['Permission', 'Le droit fin accordé à un rôle (lire les étudiants, écrire en finance…).'],
    ],
    [4.4, 12.6],
    bold_first=True,
)

note(
    'Un même mot peut avoir deux sens dans le langage courant. Ici, '
    '« inscription » désigne toujours le dossier financier et pédagogique '
    'd’un étudiant dans un groupe, pas l’action de créer un compte.',
    fill=BLUE_FILL, title='Précision',
)

h2('1.3 La règle d’or : chaque rôle voit ce qui le concerne')

para(
    'Les menus ne sont pas identiques d’un utilisateur à l’autre. Un '
    'formateur ne voit que ses groupes ; un étudiant ne voit que son dossier ; '
    'la direction voit l’ensemble ; l’administrateur consulte tout mais ne '
    'saisit pas les actes métier. Le contrôle est fait côté serveur : cacher '
    'un bouton ne suffit pas, et une adresse tapée à la main est refusée si '
    'le rôle n’est pas autorisé.'
)


# ===========================================================================
# 2. Se connecter
# ===========================================================================

h1('2', 'Se connecter')

para(
    'La page d’accueil publique présente l’académie et trois actions : '
    '« Se connecter », « Créer un compte » et « Candidater à une bourse '
    'd’études ». Toutes les connexions passent par la même adresse : '
    '/login/.'
)

h2('2.1 Les étapes')

step(1, 'Ouvrez l’adresse de l’académie, puis cliquez sur « Se connecter ».')
step(2, 'Saisissez votre identifiant : adresse e-mail ou code interne '
        '(par exemple UA-ETU-0001).')
step(3, 'Saisissez votre mot de passe.')
step(4, 'Cliquez sur « Se connecter ». Vous arrivez directement sur le '
        'tableau de bord correspondant à votre rôle.')

para(
    'La page propose deux moyens de connexion, sur le même écran : le '
    'formulaire interne (e-mail ou code interne + mot de passe) et, lorsque '
    'le service Clerk est activé, un bouton de connexion sécurisée Google ou '
    'e-mail. Les deux mènent au même compte : utilisez toujours le même moyen '
    'pour éviter de créer un doublon.'
)

note(
    'Ne partagez jamais votre mot de passe et ne laissez pas une session '
    'ouverte sur un poste partagé. Le nom affiché en haut à droite et le '
    'journal d’audit rattachent chaque action à votre compte.',
    title='Sécurité',
)

h2('2.2 Se déconnecter')

para(
    'Ouvrez le menu de votre compte, en bas de la barre latérale, puis '
    'cliquez sur « Déconnexion ». Sur un poste partagé (accueil, guichet, '
    'secrétariat), déconnectez-vous systématiquement avant de quitter la '
    'place.'
)

h2('2.3 Comptes en attente, refusés ou bloqués')

table(
    ['Situation', 'Ce que vous voyez', 'Que faire'],
    [
        ['Compte créé mais pas encore approuvé',
         'Redirection vers « En attente d’approbation ».',
         'Attendez la décision. Si l’écran le propose, complétez la demande d’accès (rôle souhaité).'],
        ['Compte désactivé, suspendu ou refusé',
         'Page « Accès refusé ».',
         'Contactez l’administration : seul un super administrateur peut réactiver le compte.'],
        ['Mot de passe oublié',
         'Message « Identifiant ou mot de passe incorrect ».',
         'Aucun écran public de réinitialisation n’est disponible : demandez à l’administration de recréer ou de rétablir votre accès.'],
        ['Identifiant inconnu',
         'Message « Identifiant ou mot de passe incorrect ».',
         'Vérifiez l’adresse e-mail exacte ou demandez votre code interne (UA-…).'],
        ['Session expirée',
         'Retour à la page de connexion.',
         'Reconnectez-vous ; aucune donnée n’est perdue.'],
    ],
    [4.4, 5.2, 7.4],
    font=8.8, header_font=8.8, bold_first=True,
)


# ===========================================================================
# 3. Créer un compte / demander un accès
# ===========================================================================

h1('3', 'Créer un compte ou demander un accès')

para(
    'Deux chemins existent : l’inscription publique, qui crée une demande, '
    'et la création directe par un super administrateur. Dans les deux cas, '
    'un compte n’ouvre l’espace de travail qu’après attribution d’un rôle.'
)

h2('3.1 L’inscription publique')

step(1, 'Depuis l’accueil, cliquez sur « Créer un compte ».')
step(2, 'Renseignez prénom, nom, adresse e-mail, rôle demandé, mot de passe '
        'et confirmation.')
step(3, 'Cliquez sur « Envoyer ma demande ».')
step(4, 'Le compte est créé avec le statut « En attente d’approbation ». '
        'Aucun accès aux données n’est accordé à ce stade.')

para(
    'Le rôle choisi est une demande, jamais un droit immédiat. La demande '
    'est examinée par un super administrateur ou par le responsable '
    'pédagogique, dans la limite de son périmètre. Un étudiant doit être '
    'rattaché à un groupe : la validation crée son inscription.'
)

h2('3.2 La demande d’accès complémentaire (comptes Clerk)')

para(
    'Un utilisateur qui se connecte avec Clerk sans dossier complet est '
    'redirigé vers « Demande d’accès » (/demande-acces/). Il y choisit son '
    'rôle et enregistre. La demande apparaît ensuite dans la file de '
    'validation, avec le même contrôle que l’inscription publique.'
)

h2('3.3 La décision d’approbation')

para(
    'La file « Demandes d’accès » est accessible au super administrateur et '
    'au responsable pédagogique. Elle se filtre par statut : toutes, en '
    'attente, approuvées, refusées.'
)

table(
    ['Décision', 'Effet dans l’application'],
    [
        ['Approuver', 'Le rôle choisi est attribué, le compte devient actif et l’utilisateur peut se connecter.'],
        ['Approuver un étudiant', 'Le groupe est obligatoire si l’étudiant n’a pas déjà une inscription ; l’inscription est créée automatiquement et le compte activé.'],
        ['Refuser', 'La demande est close, le compte reste inactif ; une note de décision peut être ajoutée.'],
    ],
    [4.4, 12.6],
    bold_first=True,
)

note(
    'Vous ne pouvez pas traiter votre propre demande d’accès : le serveur '
    'refuse l’opération. Un rôle hors du périmètre de l’approbateur doit être '
    'validé par un super administrateur.',
)

h2('3.4 La création directe par le super administrateur')

para(
    'Dans « Utilisateurs » → « Nouvel utilisateur », le super administrateur '
    'crée un compte en choisissant le rôle, éventuellement un groupe pour un '
    'étudiant, et soit un mot de passe, soit une invitation par e-mail. Le '
    'compte est immédiatement utilisable lorsque le mot de passe est fourni.'
)


# ===========================================================================
# 4. Comprendre l’espace de travail
# ===========================================================================

h1('4', 'Comprendre l’espace de travail')

para(
    'Après connexion, l’adresse /dashboard/ redirige automatiquement vers le '
    'tableau de bord du rôle. L’interface est la même pour tous, mais les '
    'menus et les boutons changent selon les droits.'
)

h2('4.1 Les zones de l’écran')

table(
    ['Zone', 'Rôle dans la navigation'],
    [
        ['Barre latérale', 'Le menu de votre métier. Le lien de la page courante est surligné.'],
        ['En-tête', 'Le titre de la page, le bouton « Site public », la cloche de notifications et le menu du compte.'],
        ['Bandeau d’accueil', 'Le rappel de votre espace et les raccourcis propres au rôle.'],
        ['Zone principale', 'Les indicateurs, les listes filtrables et les formulaires.'],
    ],
    [4.8, 12.2],
    bold_first=True,
)

h2('4.2 Le tableau de bord')

para(
    'Chaque tableau de bord affiche d’abord des indicateurs (effectifs, '
    'soldes, heures, dossiers en attente), puis les actions du jour. Les '
    'cartes et les lignes sont cliquables lorsqu’elles mènent à un détail. '
    'Un tableau vide n’est pas une erreur : il indique simplement qu’aucune '
    'donnée ne correspond au filtre ou à la période.'
)

h2('4.3 Les notifications')

para(
    'La cloche de l’en-tête signale les éléments à traiter : inscriptions en '
    'attente de validation, demandes d’accès, candidatures de bourse, '
    'écritures de caisse en brouillon et séances planifiées à saisir. Le '
    'bouton « Tout marquer comme lu » ferme le compteur. Les notifications ne '
    'remplacent pas les listes : elles attirent l’attention, mais le travail '
    'se fait dans les écrans correspondants.'
)

h2('4.4 Le profil')

para(
    'Le menu du compte → « Mon profil » permet de changer sa photo, ses '
    'informations personnelles et son adresse e-mail. Un changement d’adresse '
    'n’est appliqué qu’après clic sur le lien de confirmation envoyé à la '
    'nouvelle adresse. L’identifiant interne et le rôle ne se modifient pas '
    'depuis cette page : ils relèvent de l’administration.'
)

note(
    'Si l’e-mail de confirmation n’arrive pas, vérifiez les indésirables puis '
    'contactez l’administration. Tant que le lien n’est pas cliqué, l’ancienne '
    'adresse reste celle du compte.',
    fill=BLUE_FILL, title='Changement d’adresse',
)

h2('4.5 Rechercher et filtrer')

para(
    'Les principales listes (étudiants, journal, audit, cahier de texte) '
    'disposent d’un champ de recherche et de filtres. Le bouton « Filtrer » '
    'applique les critères ; lorsqu’il est présent, « Réinitialiser » les '
    'efface. Les listes longues sont paginées : vérifiez le nombre de pages '
    'avant de conclure qu’un élément est absent.'
)


# ===========================================================================
# 5. Qui fait quoi
# ===========================================================================

h1('5', 'Qui fait quoi')

para(
    'Huit rôles sont actifs. Deux anciens rôles, COMPTABLE et ACCUEIL, sont '
    'conservés dans l’historique mais ne sont plus attribuables : leurs '
    'missions ont été reprises par la comptabilité, le secrétariat et '
    'l’assistant administratif.'
)

table(
    ['Rôle', 'Mission principale', 'Peut écrire', 'Ne peut pas'],
    [
        ['SUPER_ADMIN', 'Administration complète, rôles, permissions, audit, décision de bourse.',
         'Partout', 'Modifier ses propres rôles ; désactiver le dernier super administrateur actif.'],
        ['ADMIN', 'Contrôle transversal de tous les modules.',
         'Aucune écriture métier', 'Gérer les rôles ou les permissions.'],
        ['DIRECTION', 'Pilotage, validation des inscriptions, encaissement, contrôle.',
         'Étudiants, inscriptions, pédagogie, finance, accueil', 'Gérer les comptes et les rôles.'],
        ['ASSISTANT_ADMIN', 'Accueil, visites, prospects, dossiers étudiants, guichet.',
         'Étudiants, inscriptions, finance, accueil', 'Pédagogie (séances, cahier de texte).'],
        ['SECRETAIRE', 'Dossiers étudiants, inscriptions, documents, accueil.',
         'Étudiants, inscriptions, finance, accueil', 'Créer des groupes ou des séances.'],
        ['RESP_PEDA', 'Programmes, groupes, séances, ressources, suivi pédagogique.',
         'Pédagogie, validation d’inscriptions, demandes d’accès de son équipe', 'Gérer les rôles administratifs.'],
        ['FORMATEUR', 'Ses groupes, ses séances, le cahier de texte et les présences.',
         'Pédagogie de ses groupes', 'Voir les groupes des autres, la caisse.'],
        ['ETUDIANT', 'Son parcours : cours, ressources, présences, fiches.',
         'Ses fiches de cours', 'Voir un autre dossier.'],
    ],
    [3.0, 6.2, 4.2, 3.6],
    font=8.5, header_font=8.5, bold_first=True,
)

h2('5.1 ADMIN et SUPER_ADMIN : deux niveaux distincts')

para(
    'L’ADMIN voit tous les modules et peut consulter les données, y compris '
    'le journal d’audit et les demandes d’accès. En revanche, les écritures '
    'métier (créer un étudiant, encaisser, saisir une séance) lui sont '
    'refusées : c’est un rôle de contrôle, pas d’exécution. Le SUPER_ADMIN '
    'dispose de tout, y compris l’attribution des rôles, la matrice des '
    'permissions et la décision finale sur les bourses.'
)

para(
    'Cette séparation est volontaire : elle empêche qu’un administrateur '
    'technique puisse modifier seul les données financières ou pédagogiques. '
    'Les actes sensibles sont réservés au super administrateur et tracés dans '
    'l’audit.'
)

h2('5.2 Les rôles dissous')

para(
    'COMPTABLE et ACCUEIL n’apparaissent plus dans les choix d’attribution. '
    'Les utilisateurs qui les portaient historiquement gardent leurs traces '
    '(paiements, visites, audit) ; pour leur donner accès, attribuez-leur '
    'ASSISTANT_ADMIN ou SECRETAIRE selon leur poste réel.'
)


# ===========================================================================
# 6. Parcours étudiant
# ===========================================================================

h1('6', 'Parcours étudiant')

para(
    'L’étudiant accède à un espace personnel en lecture, sauf pour ses fiches '
    'de cours. Il ne voit jamais les données d’un autre étudiant.'
)

h2('6.1 Le tableau de bord')

para(
    'L’écran « Mon espace » affiche : le nombre de formations, le solde '
    'restant, les présences et les absences, puis les blocs « Mes '
    'formations », « Mes paiements », « Dernières présences », « Ressources '
    'récentes » et « Prochaines séances ». Le total dû et le total payé sont '
    'rappelés en bas de page.'
)

h2('6.2 Consulter ses cours et ressources')

para(
    'Menu « Mes cours & ressources » : chaque support publié par un formateur '
    'peut être lu en ligne ou téléchargé. Un bouton de retour permet de '
    'signaler un problème ou de laisser un commentaire au formateur.'
)

h2('6.3 Consulter ses présences')

para(
    'Menu « Mes présences » : l’historique affiche la date, la formation et le '
    'statut (présent, en retard, absent, excusé), avec le motif lorsqu’il a '
    'été saisi. Une absence contestée se signale au secrétariat, qui vérifie '
    'la feuille de séance.'
)

h2('6.4 Remplir ses fiches de cours')

para(
    'Menu « Mes fiches de cours ». Pour chaque séance réalisée, l’étudiant '
    'peut enregistrer ce qu’il a retenu. C’est un espace de suivi personnel, '
    'consultable par le formateur.'
)

step(1, 'Ouvrez « Mes fiches de cours », puis choisissez la séance à '
        'documenter (filtres par recherche, formation ou état).')
step(2, 'Renseignez « Notions retenues » (obligatoire), les difficultés et '
        'les observations.')
step(3, 'Indiquez si vous étiez présent et, si besoin, les heures suivies.')
step(4, 'Enregistrez. La fiche apparaît ensuite dans la feuille de suivi.')

para(
    'Le bouton « Feuille de suivi » produit un document imprimable au format '
    'papier de l’académie : en-tête Formateur / Filière / Classe, puis '
    'colonnes Dates, Heures suivies, Notions retenues, Présence et '
    'Observations. Il reprend toutes les fiches remplies pour la formation.'
)

h2('6.5 Suivre ses paiements')

para(
    'Le tableau de bord affiche le net dû, le total payé et le solde restant. '
    'Le détail des paiements figure dans « Mes paiements ». Le reçu officiel '
    'est remis par le guichet au moment de l’encaissement ; en cas d’écart, '
    'signalez-le au secrétariat avec la date et le montant.'
)

note(
    'Un paiement partiel ne solde pas le dossier. Le solde restant est '
    'recalculé après chaque règlement, et c’est ce montant qui sert de '
    'plafond au guichet.',
    fill=GREEN_FILL, title='À retenir',
)


# ===========================================================================
# 7. Parcours formateur
# ===========================================================================

h1('7', 'Parcours formateur')

para(
    'Le formateur travaille sur les groupes qui lui sont attribués. Il '
    'planifie les séances, tient le cahier de texte, saisit les présences et '
    'publie des ressources.'
)

h2('7.1 Le tableau de bord')

para(
    '« Vos sessions de formation » résume les sessions, les heures réalisées '
    'et restantes, les inscriptions actives et les comptes rendus validés. Il '
    'affiche le planning du jour, les prochaines séances, les absences '
    'récentes et la liste des groupes, avec deux raccourcis : « Planifier une '
    'séance » et « Saisie rapide » (présences).'
)

h2('7.2 Créer une séance')

step(1, 'Menu « Séances » → « Planifier une séance », ou depuis un groupe.')
step(2, 'Choisissez la date, les heures prévues et, si besoin, les heures '
        'réelles.')
step(3, 'Sélectionnez le module et la leçon, puis renseignez le sujet et les '
        'objectifs.')
step(4, 'Complétez le contenu traité, le contenu restant, les exercices, les '
        'difficultés et les notes.')
step(5, 'Choisissez le statut : planifiée, réalisée, annulée ou reportée, '
        'puis enregistrez.')

table(
    ['Contrôle', 'Règle appliquée'],
    [
        ['Heures', 'L’heure de fin doit être postérieure à l’heure de début.'],
        ['Doublon', 'Une même séance (même groupe, même date, même heure de début) ne peut pas être créée deux fois.'],
        ['Contenu', 'Le contenu traité est obligatoire pour une séance réalisée.'],
    ],
    [3.4, 13.6],
    bold_first=True,
)

h2('7.3 Tenir le cahier de texte')

para(
    'Le cahier de texte est la version numérique du cahier papier. Une ligne '
    'par séance : date, heures, notions enseignées, nombre d’apprenants et '
    'observations.'
)

step(1, 'Menu « Cahier de texte » : la liste des groupes s’affiche avec la '
        'période, les formateurs et le nombre de séances.')
step(2, 'Cliquez sur « Ouvrir » pour un groupe.')
step(3, 'Dépliez « Ajouter la séance du jour » et remplissez la fiche : '
        'date, heure de début et de fin, notions enseignées, nombre '
        'd’apprenants, observations.')
step(4, 'Enregistrez. La ligne est ajoutée au cahier et au compte rendu de '
        'séance.')
step(5, 'Utilisez « Imprimer » pour produire la feuille A4 officielle.')

para(
    'La feuille imprimée reprend l’en-tête Formateur / Filière / Classe et '
    'les colonnes Dates, Heures, Notions enseignées, Nombre d’apprenants et '
    'Observations, avec un total d’apprenants en bas de tableau.'
)

h2('7.4 Saisir les présences')

step(1, 'Ouvrez la séance concernée, puis « Présences ».')
step(2, 'Pour chaque étudiant inscrit, choisissez le statut : présent, en '
        'retard, absent ou excusé.')
step(3, 'Ajoutez l’heure d’arrivée et le motif lorsque nécessaire.')
step(4, 'Enregistrez. L’historique est consultable dans « Présences ».')

note(
    'Seules les inscriptions actives ou terminées apparaissent sur la feuille '
    'de présence. Un étudiant sans inscription ne peut pas être pointé : '
    'signalez-le au secrétariat.',
)

h2('7.5 Publier une ressource')

para(
    'Menu « Ressources » → « Nouvelle ressource » : titre, description, '
    'fichier et groupe destinataire. La ressource devient visible par les '
    'étudiants du groupe et par les formateurs. Un retour peut être laissé '
    'par les étudiants ; il est consultable dans la fiche de la ressource.'
)

h2('7.6 Suivre la progression')

para(
    'Menu « Progression » : heures planifiées, réalisées et restantes par '
    'groupe, avec le nombre de séances et le taux d’avancement. C’est '
    'l’indicateur à utiliser pour ajuster le programme avant la fin de la '
    'période.'
)

h2('7.7 Programmes')

para(
    'Menu « Programmes » : le formateur consulte les modules et les leçons de '
    'ses formations et peut les compléter. La création d’un groupe, en '
    'revanche, est réservée au responsable pédagogique et à la direction.'
)


# ===========================================================================
# 8. Parcours secrétariat
# ===========================================================================

h1('8', 'Parcours secrétariat')

para(
    'Le secrétariat tient le dossier étudiant de bout en bout : identité, '
    'inscription, documents, tarif et remise. Il ne crée ni les groupes ni les '
    'séances.'
)

h2('8.1 La liste des étudiants')

para(
    'Menu « Étudiants » : la liste est paginée par 20. Elle se filtre par '
    'recherche (nom, prénom, e-mail, code interne), par statut de compte et '
    'par formation. Chaque ligne ouvre la fiche de l’étudiant.'
)

h2('8.2 Créer un étudiant')

step(1, 'Menu « Nouvel étudiant » (ou depuis un prospect, le formulaire est '
        'prérempli).')
step(2, 'Renseignez l’identité : prénom, nom, e-mail, téléphone, adresse, '
        'date de naissance.')
step(3, 'Choisissez le groupe d’inscription : il est obligatoire.')
step(4, 'Complétez le tarif, la remise éventuelle, la date de début et le '
        'plan de paiement.')
step(5, 'Choisissez le statut de l’inscription, puis enregistrez.')

table(
    ['Statut choisi pour l’inscription', 'Statut du compte créé'],
    [
        ['Active', 'Compte actif : l’étudiant peut se connecter immédiatement.'],
        ['En attente, terminée, suspendue ou annulée', 'Compte en attente d’approbation.'],
    ],
    [6.4, 10.6],
    bold_first=True,
)

note(
    'Un étudiant ne peut pas avoir deux inscriptions identiques dans le même '
    'groupe. Le contrôle est fait à l’enregistrement ; en cas de refus, '
    'vérifiez le dossier existant avant de créer une nouvelle ligne.',
)

h2('8.3 La fiche étudiant')

para(
    'La fiche regroupe six blocs : informations, formations et inscriptions, '
    'paiements, documents administratifs, dernières présences et historique '
    'd’audit. Les indicateurs du haut affichent le total dû, le total payé, le '
    'solde restant et le nombre de pièces au dossier.'
)

bullet('« Modifier la fiche » change l’identité et les coordonnées ;',
       'Actions : ')
bullet('« Nouvelle inscription » ouvre un dossier supplémentaire ;',
       'Inscription : ')
bullet('« Ajouter le document » accepte PDF, JPG, PNG, DOC et DOCX ;',
       'Documents : ')
bullet('« Reçu » ouvre le justificatif d’un paiement.', 'Paiements : ')

h2('8.4 Créer ou modifier une inscription')

para(
    'Le formulaire d’inscription contient l’étudiant, le groupe, le statut, '
    'la date de début, le tarif, la remise, le plan de paiement et les notes. '
    'Le net dû est calculé automatiquement (tarif moins remise). La remise ne '
    'peut pas dépasser le tarif.'
)

para(
    'La fiche d’inscription affiche le tarif, la remise, le net dû, le solde '
    'restant, le statut de paiement (soldé, partiel, impayé) et l’historique '
    'des modifications. C’est le dossier de référence pour l’encaissement.'
)

h2('8.5 Les inscriptions créées au guichet')

para(
    'Une inscription ouverte depuis l’écran d’encaissement est toujours créée '
    'au statut « En attente ». Elle ne peut pas être encaissée avant '
    'validation. La fiche affiche une bannière et le bouton « Valider '
    'l’inscription ».'
)

para(
    'La validation est ouverte à la direction, au super administrateur, à '
    'l’assistant administratif et au responsable pédagogique. L’ADMIN '
    'consulte mais ne valide pas. Valider un dossier dont le compte étudiant '
    'est encore en attente approuve aussi ce compte.'
)

note(
    'Le circuit est volontaire : le guichet ouvre le dossier, la direction '
    'ou la pédagogie le valide, puis la caisse encaisse. Cela empêche qu’un '
    'dossier incomplet soit payé avant contrôle.',
    fill=BLUE_FILL, title='Pourquoi une validation ?',
)

h2('8.6 Les documents administratifs')

para(
    'Les pièces (identité, diplôme, relevé de notes, photo, certificat, '
    'autre) sont ajoutées depuis la fiche étudiant. Le téléchargement est '
    'contrôlé : l’étudiant ne peut ouvrir que ses propres pièces, le '
    'secrétariat, la direction et l’administration voient celles de tous. '
    'Chaque accès est journalisé.'
)

h2('8.7 Prospects et visites')

para(
    'Le secrétariat peut consulter les prospects et les visites, suivre les '
    'relances et ouvrir un dossier depuis un prospect. La création d’une '
    'visite et la transformation en prospect se font à l’accueil.'
)


# ===========================================================================
# 9. Accueil et guichet
# ===========================================================================

h1('9', 'Accueil et guichet')

para(
    'L’accueil enregistre les passages, qualifie les contacts et ouvre les '
    'premiers dossiers. C’est le point de départ du parcours d’un nouvel '
    'apprenant.'
)

h2('9.1 Le tableau de bord')

para(
    'Il affiche les visites du jour, les relances à effectuer, le formulaire '
    'de nouveau passage, les derniers prospects et les événements d’accès '
    'récents. C’est l’écran d’ouverture de la journée.'
)

h2('9.2 Enregistrer une visite')

step(1, 'Menu « Visites » → « Nouvelle visite ».')
step(2, 'Identifiez le visiteur (nom, prénom, téléphone, e-mail) et choisissez '
        'le motif.')
step(3, 'Enregistrez l’heure d’arrivée.')
step(4, 'Au départ, ouvrez la fiche et cliquez sur « Enregistrer le départ ».')
step(5, 'Si la personne est intéressée, cliquez sur « Créer un prospect » '
        'pour poursuivre le suivi.')

h2('9.3 Suivre un prospect')

para(
    'La fiche prospect centralise les coordonnées, la formation visée, la '
    'source et les relances. Chaque relance est datée avec son résultat. Le '
    'bouton « Convertir en étudiant » ouvre le formulaire prérempli avec les '
    'coordonnées du prospect.'
)

h2('9.4 Le parcours guichet complet')

table(
    ['Étape', 'Écran', 'Résultat'],
    [
        ['1. Visite', 'Accueil → Visites', 'Le passage est enregistré.'],
        ['2. Prospect', 'Accueil → Prospects', 'Le contact est qualifié et suivi.'],
        ['3. Étudiant', 'Secrétariat → Nouvel étudiant', 'Le compte et le dossier sont créés.'],
        ['4. Inscription', 'Encaissement → Inscrire un étudiant', 'Le dossier est créé au statut « En attente ».'],
        ['5. Validation', 'Fiche inscription → Valider', 'Le dossier devient encaissable.'],
        ['6. Paiement', 'Comptabilité → Paiement étudiant', 'Un reçu et une opération de caisse sont créés.'],
    ],
    [3.2, 6.4, 7.4],
    bold_first=True,
)

note(
    'Ne sautez pas l’étape de validation : une inscription au guichet reste '
    '« En attente » et le formulaire d’encaissement la refuse explicitement.',
)

h2('9.5 Les motifs de visite')

para(
    'Depuis « Motifs », l’accueil, le secrétariat ou la direction peut '
    'activer ou désactiver un motif. Un motif désactivé n’est plus proposé '
    'aux nouveaux passages, mais reste lisible sur les visites passées.'
)


# ===========================================================================
# 10. Comptabilité et encaissement
# ===========================================================================

h1('10', 'Comptabilité et encaissement')

para(
    'La comptabilité enregistre les mouvements de caisse et les paiements '
    'étudiants. Chaque euro ou franc qui entre ou sort doit être rattaché à '
    'une caisse et à une opération tracée.'
)

h2('10.1 Le tableau de bord')

para(
    'Il affiche les caisses avec leur solde, les opérations récentes et les '
    'paiements étudiants récents. Les soldes négatifs doivent être expliqués '
    'avant la clôture : ils signalent souvent une sortie saisie sur la '
    'mauvaise caisse.'
)

h2('10.2 Le journal comptable')

para(
    'Menu « Journal comptable » : la liste des opérations se filtre par '
    'recherche, type, caisse, statut et période. Chaque ligne ouvre le détail '
    'avec l’auteur, la date, le montant, la catégorie et les pièces liées. '
    'L’annulation est possible avec un motif obligatoire ; l’opération reste '
    'dans le journal avec le statut « Annulée ».'
)

h2('10.3 Enregistrer une opération')

step(1, 'Menu « Nouvelle opération ».')
step(2, 'Choisissez le type : entrée, sortie ou transfert.')
step(3, 'Sélectionnez la caisse, la catégorie, le montant et la date.')
step(4, 'Ajoutez un libellé et, si disponible, un justificatif.')
step(5, 'Enregistrez, puis vérifiez le nouveau solde.')

para(
    'Un transfert déplace de l’argent d’une caisse vers une autre. Il est '
    'neutre au niveau global : il ne crée ni produit ni charge. Les entrées '
    'et sorties, elles, modifient le résultat.'
)

h2('10.4 Les caisses et les clôtures')

para(
    '« Caisses & comptes » liste les caisses actives, leur solde d’ouverture '
    'et leur solde courant. « Clôtures » permet de contrôler une journée : '
    'solde théorique, montant réellement compté, écart et commentaire. Une '
    'caisse ne peut être clôturée qu’une fois par date.'
)

note(
    'Un écart de caisse ne se corrige pas en créant une opération fictive. '
    'Il se documente dans la clôture, puis se régularise par une opération '
    'réelle et justifiée.',
)

h2('10.5 Encaisser un paiement étudiant')

para(
    'Menu « Paiement étudiant ». Le parcours se fait dans l’ordre : étudiant, '
    'puis inscription, puis montant.'
)

step(1, 'Choisissez l’étudiant. La liste ne contient que les comptes '
        'étudiants actifs.')
step(2, 'Choisissez l’inscription à encaisser. Les dossiers annulés, en '
        'attente de validation ou d’un autre étudiant sont exclus ; chaque '
        'ligne rappelle le reste à payer.')
step(3, 'Saisissez le montant. Il ne peut pas dépasser le reste à payer ; '
        'le message sous le champ rappelle le plafond.')
step(4, 'Choisissez le moyen (espèces, Mobile Money, virement, autre), la '
        'caisse, la date et l’heure.')
step(5, 'Précisez le motif : mensualité (avec le mois et l’année), frais '
        'd’inscription ou autre paiement.')
step(6, 'Enregistrez. Un reçu est généré et une opération de caisse est '
        'créée.')

table(
    ['Règle', 'Conséquence dans l’écran'],
    [
        ['Dossier soldé', 'Le formulaire affiche « Dossier soldé » et refuse tout montant.'],
        ['Montant trop élevé', 'Message « Le montant dépasse le reste à payer (X FCFA). »'],
        ['Dossier en attente', 'Message « L’inscription de cet étudiant est en attente de validation… »'],
        ['Aucune inscription', 'Message invitant à créer le dossier dans le panneau « Inscrire un étudiant ».'],
        ['Mois déjà réglé', 'Message indiquant le mois, l’année et la référence du paiement existant.'],
        ['Double clic', 'Un paiement identique (même dossier, même montant, même minute) est refusé.'],
    ],
    [5.0, 12.0],
    font=8.8, header_font=8.8, bold_first=True,
)

h2('10.6 Inscrire un étudiant depuis la caisse')

para(
    'Le panneau « Inscrire un étudiant » évite de changer d’écran lorsqu’un '
    'étudiant se présente au guichet sans dossier. L’inscription créée prend '
    'le statut « En attente » et doit être validée avant tout encaissement. '
    'L’opération est auditée avec la source « guichet ».'
)

h2('10.7 Les paiements par mois')

para(
    '« Paiements par mois » affiche une grille de douze mois pour un dossier. '
    'Cochez les mois réglés, ajustez les montants si nécessaire : un paiement '
    'est créé par mois coché. Les frais d’inscription apparaissent une seule '
    'fois par dossier, et un « mois libre » permet d’encaisser un montant hors '
    'grille. Le total coché est rappelé en haut de la grille.'
)

para(
    'En bas de page, la section « Comptes étudiants sans inscription » liste '
    'les comptes actifs qui n’ont encore aucun dossier, avec un bouton '
    '« Inscrire » pour ouvrir le dossier manquant.'
)

h2('10.8 Le reçu')

para(
    'Chaque paiement produit un reçu imprimable : référence, date, étudiant, '
    'formation, inscription, motif, mois réglé, moyen, caisse, encaisseur, '
    'montant, net dû, total payé et reste à payer. Le reçu est accessible '
    'depuis la fiche étudiant, la fiche d’inscription et le journal.'
)

note(
    'Un paiement partiel ne solde pas le dossier. Le reste à payer est '
    'recalculé après chaque règlement et sert de plafond au paiement suivant.',
    fill=GREEN_FILL, title='Règle de caisse',
)

h2('10.9 Les cinq règles à ne jamais enfreindre')

bullet('encaisser uniquement une inscription validée ;', '1. ')
bullet('ne jamais dépasser le reste à payer ;', '2. ')
bullet('ne jamais saisir un paiement pour « régulariser » sans pièce ;', '3. ')
bullet('annuler avec un motif, jamais supprimer ;', '4. ')
bullet('compter la caisse et clôturer chaque jour.', '5. ')


# ===========================================================================
# 11. Direction
# ===========================================================================

h1('11', 'Direction')

para(
    'La direction pilote l’activité et contrôle les dossiers sensibles. Elle '
    'valide les inscriptions ouvertes au guichet et peut encaisser.'
)

h2('11.1 Le tableau de bord')

para(
    'Il présente les indicateurs du mois, la file « Inscriptions en attente '
    'de validation », les soldes des caisses, les effectifs par session '
    'active, les derniers paiements et les opérations récentes.'
)

h2('11.2 Valider une inscription')

step(1, 'Repérez le dossier dans la file du tableau de bord ou dans la fiche '
        'de l’inscription.')
step(2, 'Vérifiez l’étudiant, le groupe, le tarif, la remise et le net dû.')
step(3, 'Cliquez sur « Valider l’inscription ».')
step(4, 'Le dossier passe au statut « Active » ; s’il était en attente, le '
        'compte étudiant est approuvé dans le même geste.')
step(5, 'Le dossier peut maintenant être encaissé.')

note(
    'Si le dossier est incomplet, ne validez pas : demandez la correction au '
    'secrétariat. Une validation se trace dans l’audit et ne se « défait » '
    'pas par simple clic.',
)

h2('11.3 Contrôler')

para(
    'La direction consulte le journal comptable, les caisses, les étudiants, '
    'les visites, les prospects, la vue direction et le journal d’audit. Elle '
    'peut encaisser un paiement et suivre les bourses en lecture. La gestion '
    'des comptes et des rôles reste réservée au super administrateur.'
)


# ===========================================================================
# 12. Responsable pédagogique
# ===========================================================================

h1('12', 'Responsable pédagogique')

para(
    'Le responsable pédagogique construit l’offre et suit l’exécution : '
    'programmes, groupes, séances, ressources, progression et encadrement des '
    'formateurs.'
)

h2('12.1 Programmes, modules et leçons')

para(
    'Menu « Programmes » : chaque formation regroupe des modules, eux-mêmes '
    'découpés en leçons. Le responsable crée et modifie modules et leçons ; '
    'les formateurs peuvent compléter les programmes de leurs formations.'
)

h2('12.2 Groupes')

para(
    'Menu « Groupes » → « Nouveau groupe » : formation, dates de début et de '
    'fin, horaires, capacité, statut et formateurs affectés. Le groupe est la '
    'clé de tout le reste : inscriptions, séances, présences et cahier de '
    'texte s’y rattachent.'
)

h2('12.3 Séances, présence et cahier de texte')

para(
    'Le responsable voit toutes les séances de son périmètre, peut les créer, '
    'les modifier et consulter les feuilles de présence. Il tient également '
    'le cahier de texte et suit la progression par groupe.'
)

h2('12.4 Demandes d’accès')

para(
    'Le responsable pédagogique instruit les demandes d’accès de son '
    'périmètre : formateurs et étudiants notamment. Il ne peut pas attribuer '
    'les rôles administratifs ou financiers ; une demande hors périmètre est '
    'renvoyée au super administrateur.'
)


# ===========================================================================
# 13. Administration
# ===========================================================================

h1('13', 'Administration et super administration')

para(
    'L’administration gère les comptes, les rôles et la traçabilité. Le '
    'super administrateur dispose de tous les droits ; l’administrateur '
    'consulte et contrôle, sans écrire dans le métier.'
)

h2('13.1 Les utilisateurs')

para(
    'Menu « Utilisateurs » : recherche, filtre par rôle et par statut, liste '
    'paginée. La fiche utilisateur regroupe l’identité, la photo, les rôles, '
    'le statut du compte et l’historique.'
)

table(
    ['Action', 'Où', 'Qui'],
    [
        ['Créer un utilisateur', 'Utilisateurs → Nouvel utilisateur', 'SUPER_ADMIN'],
        ['Modifier l’identité', 'Fiche → Modifier', 'SUPER_ADMIN'],
        ['Changer la photo', 'Fiche → Photo', 'SUPER_ADMIN'],
        ['Attribuer ou retirer un rôle', 'Fiche → Rôles et accès', 'SUPER_ADMIN'],
        ['Activer, suspendre, désactiver, refuser', 'Fiche → Statut', 'SUPER_ADMIN'],
        ['Consulter la fiche et l’audit', 'Utilisateurs', 'SUPER_ADMIN, ADMIN'],
    ],
    [5.2, 6.8, 5.0],
    font=8.8, header_font=8.8, bold_first=True,
)

note(
    'Garde-fous : un administrateur ne peut pas modifier les rôles depuis '
    'l’écran ADMIN, personne ne peut modifier ses propres rôles, et le dernier '
    'super administrateur actif ne peut pas être désactivé.',
)

h2('13.2 La matrice des permissions')

para(
    'Menu « Permissions » (super administrateur uniquement) : tableau des '
    'rôles et des permissions, en lecture. Les droits réellement appliqués '
    'sont ceux du code et de la base ; la matrice sert à vérifier qui peut '
    'lire ou écrire quoi.'
)

table(
    ['Permission', 'Portée'],
    [
        ['users.read', 'Consulter les comptes et les rôles.'],
        ['students.read / students.write', 'Lire ou modifier les dossiers étudiants.'],
        ['formations.read / formations.write', 'Lire ou modifier programmes, groupes et séances.'],
        ['attendance.read / attendance.write', 'Lire ou saisir les présences.'],
        ['finance.read / finance.write', 'Consulter ou enregistrer les opérations et paiements.'],
        ['scholarship.read', 'Consulter les candidatures de bourse.'],
        ['access_events.read / access_events.write', 'Lire ou enregistrer les événements d’accès.'],
        ['certificates.issue', 'Émettre les attestations.'],
    ],
    [6.2, 10.8],
    font=8.8, header_font=8.8, bold_first=True,
)

h2('13.3 Les demandes d’accès')

para(
    'La file se filtre par statut. Une demande en attente peut être approuvée '
    'avec le rôle définitif et, pour un étudiant, le groupe. Une demande déjà '
    'traitée ne peut pas être rejouée. L’approbation et le refus sont '
    'audités avec leur auteur ; la note de décision reste attachée à la '
    'demande.'
)

h2('13.4 Le journal d’audit')

para(
    'Menu « Journal d’audit » : chaque ligne indique la date, l’acteur, '
    'l’action, l’entité, les valeurs avant/après et l’adresse IP. Les filtres '
    'portent sur la recherche, l’action, l’entité, l’acteur et la période. '
    'Le détail « Voir les valeurs » affiche les changements.'
)

para(
    'Le journal est la preuve de ce qui s’est passé : création et modification '
    'd’étudiants, inscriptions, paiements, annulations, présences, rôles, '
    'statuts de compte, accès aux fichiers, exports et décisions de bourse. '
    'Il ne se modifie pas depuis l’interface.'
)

h2('13.5 La supervision financière')

para(
    'Réservée au super administrateur, elle consolide les opérations validées '
    'sur une période, avec les totaux d’entrées, de sorties et le net. Le '
    'bouton d’export CSV produit un fichier reprenant les opérations filtrées, '
    'dans la limite de 5 000 lignes ; l’export est lui-même audité.'
)

h2('13.6 Les bourses')

para(
    'Le super administrateur instruit les candidatures, consulte les pièces '
    'et change le statut avec une note interne. L’ADMIN peut consulter, mais '
    'la décision est réservée au super administrateur.'
)


# ===========================================================================
# 14. Bourses
# ===========================================================================

h1('14', 'Bourses')

para(
    'Le parcours bourse est public : il ne demande pas de compte. Il sert à '
    'recueillir une candidature et à la suivre, pas à encaisser un paiement.'
)

h2('14.1 Déposer une candidature')

step(1, 'Depuis l’accueil, cliquez sur « Candidater à une bourse d’études ».')
step(2, 'Renseignez l’identité : nom, prénom, e-mail, téléphone.')
step(3, 'Précisez le projet : destination, programme visé, domaine d’études.')
step(4, 'Joignez les pièces : pièce d’identité, photo et lettre de '
        'motivation sont obligatoires ; diplômes et relevés sont facultatifs.')
step(5, 'Cliquez sur « Soumettre ma candidature ».')
step(6, 'Notez la référence et le jeton de suivi affichés sur la confirmation.')

note(
    'Formats acceptés : PDF, JPG ou PNG, 10 Mo maximum par fichier. Un fichier '
    'trop volumineux est refusé avec un message nommant le fichier concerné.',
)

h2('14.2 Suivre une candidature')

para(
    'Page « Suivi de candidature » : saisissez la référence et le jeton reçus '
    'à la soumission. Le statut et la note de décision s’affichent. Sans les '
    'deux informations, aucune recherche n’est possible.'
)

h2('14.3 Instruire une candidature')

para(
    'Côté administration, « Bourses » liste les candidatures avec la '
    'référence, le candidat, la destination, le statut et la date. La fiche '
    'permet d’ouvrir les documents et de changer le statut : soumise, en '
    'cours d’examen, documents demandés, approuvée, rejetée ou retirée.'
)

table(
    ['Statut', 'Signification'],
    [
        ['Soumise', 'La candidature vient d’être déposée.'],
        ['En cours d’examen', 'Le dossier est en instruction.'],
        ['Documents demandés', 'Une pièce manque ou doit être précisée.'],
        ['Approuvée', 'La bourse est accordée.'],
        ['Rejetée', 'La candidature est refusée ; la note interne explique pourquoi.'],
        ['Retirée', 'Le candidat a retiré sa demande.'],
    ],
    [4.8, 12.2],
    bold_first=True,
)


# ===========================================================================
# 15. Documents et impressions
# ===========================================================================

h1('15', 'Documents et impressions')

para(
    'Les documents produits par la plateforme reprennent la présentation '
    'papier de l’académie. Ils s’impriment depuis le navigateur (Ctrl+P) ou '
    'le bouton « Imprimer » de l’écran.'
)

table(
    ['Document', 'Où le trouver', 'Contenu principal'],
    [
        ['Reçu de paiement', 'Paiement, fiche étudiant, fiche inscription, journal',
         'Référence, étudiant, formation, motif, mois, moyen, caisse, montant, net, payé, reste.'],
        ['Cahier de texte', 'Pédagogie → Cahier de texte → Imprimer',
         'Formateur, filière, classe ; dates, heures, notions, nombre d’apprenants, observations.'],
        ['Feuille de suivi de l’apprenant', 'Étudiant → Mes fiches → Feuille de suivi',
         'Apprenant, filière, classe, formateur ; dates, heures suivies, notions, présence, observations.'],
        ['Fiche étudiant (écran)', 'Secrétariat → Étudiants → fiche',
         'Identité, inscriptions, paiements, documents, présences ; impression navigateur.'],
        ['Export financier CSV', 'Super administration → Supervision financière',
         'Opérations filtrées, pour tableur ou archivage.'],
    ],
    [4.4, 6.4, 6.2],
    font=8.6, header_font=8.6, bold_first=True,
)

h2('15.1 Imprimer sans perdre la mise en page')

bullet('utilisez le bouton « Imprimer » de l’écran, pas le menu du '
       'navigateur, lorsque les deux existent ;', 'Bouton : ')
bullet('choisissez le format A4 et l’orientation indiquée par l’aperçu ;',
       'Format : ')
bullet('désactivez les en-têtes et pieds de page du navigateur pour éviter '
       'les doublons ;', 'Options : ')
bullet('vérifiez que les accents et les montants FCFA sont lisibles sur '
       'l’aperçu.', 'Contrôle : ')

note(
    'Le reçu et le cahier de texte sont des documents officiels. Une '
    'impression doit correspondre à une opération réellement enregistrée : ne '
    'modifiez jamais un montant sur le papier pour le faire coïncider avec '
    'la caisse.',
)


# ===========================================================================
# 16. Messages fréquents
# ===========================================================================

h1('16', 'Messages fréquents')

para(
    'Les messages ci-dessous sont ceux que l’application affiche réellement. '
    'Ils indiquent presque toujours une règle de gestion, pas une panne.'
)

table(
    ['Message', 'Cause', 'Action'],
    [
        ['« Identifiant ou mot de passe incorrect. »',
         'Identifiant inconnu ou mot de passe erroné.',
         'Vérifiez la casse et l’adresse exacte ; contactez l’administration si le doute persiste.'],
        ['« Votre compte est désactivé ou suspendu. »',
         'Le compte n’est plus actif.',
         'Demandez la réactivation à un super administrateur.'],
        ['Page « En attente d’approbation »',
         'La demande n’a pas encore été traitée.',
         'Attendez la décision ou complétez la demande d’accès.'],
        ['« Accès refusé. »',
         'Le rôle ne permet pas cet écran.',
         'Utilisez le menu de votre métier ; ne forcez pas l’adresse.'],
        ['« Cette inscription n’est pas encaissable : elle est annulée, en attente de validation ou n’appartient pas à l’étudiant sélectionné. »',
         'Dossier non validé, annulé, ou mauvais étudiant.',
         'Vérifiez le dossier et l’étudiant ; faites valider l’inscription si nécessaire.'],
        ['« L’inscription de cet étudiant est en attente de validation : elle ne peut pas encore être encaissée. »',
         'Dossier créé au guichet, non validé.',
         'Faites valider le dossier par la direction ou la pédagogie.'],
        ['« Cet étudiant n’a pas encore d’inscription. Créez-la dans le panneau “Inscrire un étudiant”… »',
         'Compte actif sans dossier.',
         'Ouvrez le panneau d’inscription, puis faites valider le dossier.'],
        ['« Le montant dépasse le reste à payer (X FCFA). »',
         'Le montant saisi excède le solde du dossier.',
         'Corrigez le montant ; le reste exact est rappelé dans le message.'],
        ['« Ce dossier est soldé : aucun montant ne reste à encaisser. »',
         'Le net dû est déjà couvert.',
         'N’encaissez rien ; vérifiez le journal si le client conteste.'],
        ['« Le mois de … est déjà réglé (référence). »',
         'Une mensualité existe déjà pour ce mois.',
         'Consultez le reçu existant ; choisissez un autre mois si besoin.'],
        ['« Un paiement identique vient d’être enregistré. Vérifiez le journal avant de réessayer. »',
         'Double clic ou double soumission.',
         'Actualisez le journal ; ne relancez pas l’encaissement.'],
        ['« Un compte étudiant doit être inscrit à un groupe : choisissez la formation / le groupe avant d’approuver. »',
         'Approbation d’un étudiant sans groupe.',
         'Sélectionnez le groupe dans la demande d’accès.'],
        ['« Rôle hors de votre périmètre : un super administrateur doit statuer. »',
         'Le rôle demandé dépasse les droits de l’approbateur.',
         'Transmettez la demande au super administrateur.'],
        ['« Cette demande a déjà été traitée. »',
         'Deux personnes ont ouvert la même demande.',
         'Actualisez la liste ; ne rejouez pas la décision.'],
        ['« Vous ne pouvez pas traiter votre propre demande d’accès. »',
         'Auto-approbation.',
         'Faites traiter la demande par un autre responsable.'],
        ['« La date de fin doit suivre la date de début. » / « L’heure de fin doit suivre le début. »',
         'Incohérence de dates ou d’heures.',
         'Corrigez la période ou l’horaire.'],
        ['« Une séance est déjà enregistrée à cette date et à cette heure pour ce groupe. »',
         'Doublon de séance.',
         'Ouvrez la séance existante au lieu d’en créer une seconde.'],
        ['« Cette caisse est déjà clôturée pour cette date. »',
         'Une clôture existe déjà.',
         'Consultez la clôture existante ; ne la dupliquez pas.'],
        ['« Un motif est obligatoire pour annuler. »',
         'Annulation d’opération sans justification.',
         'Saisissez le motif réel de l’annulation.'],
        ['« Le fichier … est trop volumineux (max 10 Mo). »',
         'Pièce jointe trop lourde.',
         'Compressez ou photographiez le document en qualité moyenne.'],
        ['« Aucune candidature trouvée avec ces informations. »',
         'Référence ou jeton erroné.',
         'Vérifiez la confirmation de candidature ; les deux valeurs sont sensibles à la casse.'],
    ],
    [8.2, 4.4, 4.4],
    font=8.1, header_font=8.3, bold_first=True,
)


# ===========================================================================
# 17. Bonnes pratiques
# ===========================================================================

h1('17', 'Bonnes pratiques et sécurité')

h2('17.1 Au quotidien')

bullet('un compte par personne, jamais de compte partagé ;',
       'Comptes : ')
bullet('verrouillez la session dès que vous quittez le poste, surtout à '
       'l’accueil et à la caisse ;', 'Poste partagé : ')
bullet('saisissez les opérations le jour même, avec la pièce sous les yeux ;',
       'Saisie : ')
bullet('vérifiez le reste à payer avant chaque encaissement ;',
       'Caisse : ')
bullet('contrôlez la caisse et clôturez chaque soir ;',
       'Clôture : ')
bullet('ne corrigez pas une erreur en créant une opération inverse non '
       'justifiée.', 'Correction : ')

h2('17.2 Données personnelles')

para(
    'La plateforme contient des données d’identité, des coordonnées, des '
    'pièces justificatives et des informations financières. Elles ne se '
    'communiquent qu’aux personnes dont le rôle le justifie. Les documents '
    'téléchargés depuis la plateforme doivent être stockés dans un dossier '
    'professionnel, pas sur un espace personnel ou une messagerie grand '
    'public.'
)

h2('17.3 Traçabilité')

para(
    'Chaque action importante est auditée : auteur, date, entité, valeurs '
    'avant et après. En cas de litige, le journal d’audit permet de '
    'reconstituer l’historique. C’est pourquoi il faut toujours agir avec son '
    'propre compte et ne jamais « prêter » ses identifiants.'
)

h2('17.4 Sauvegardes et incidents')

para(
    'Les sauvegardes relèvent de l’administrateur technique. Si un écran '
    'affiche une erreur inattendue, notez l’heure, l’action en cours et le '
    'message, puis signalez-le sans réessayer en boucle. Ne supprimez jamais '
    'une donnée pour « voir si cela débloque » : l’audit conserve la trace de '
    'la suppression.'
)

note(
    'Les mots de passe de démonstration fournis avec la version de test '
    'doivent être changés avant la mise en production. Un compte '
    'administrateur avec un mot de passe par défaut est le premier risque '
    'd’une plateforme en ligne.',
    title='Avant la mise en production',
)


# ===========================================================================
# Annexes
# ===========================================================================

h1('', 'Annexe A — Matrice des écrans par rôle')

table(
    ['Écran', 'SUPER_ADMIN', 'ADMIN', 'DIRECTION', 'ASSISTANT', 'SECRETAIRE', 'RESP_PEDA', 'FORMATEUR', 'ETUDIANT'],
    [
        ['Tableau de bord du rôle', '✓', '✓', '✓', '✓', '✓', '✓', '✓', '✓'],
        ['Accueil, visites, prospects', '✓', '✓', '✓', '✓', '✓', '—', '—', '—'],
        ['Étudiants et dossiers', '✓', '✓', '✓', '✓', '✓', 'lecture', '—', '—'],
        ['Inscriptions', '✓', 'lecture', '✓', '✓', '✓', 'lecture', '—', '—'],
        ['Validation d’inscription', '✓', '—', '✓', '✓', '—', '✓', '—', '—'],
        ['Programmes, groupes, séances', '✓', '✓', '✓', '—', 'lecture', '✓', '✓', '—'],
        ['Cahier de texte et présences', '✓', '✓', '✓', '—', 'lecture', '✓', '✓', '—'],
        ['Ressources', '✓', '✓', '✓', '—', 'lecture', '✓', '✓', 'lecture'],
        ['Journal et caisses', '✓', '✓', '✓', '✓', '✓', 'lecture', '—', '—'],
        ['Paiement étudiant', '✓', '—', '✓', '✓', '✓', '—', '—', '—'],
        ['Clôtures', '✓', '✓', '✓', '✓', '✓', '—', '—', '—'],
        ['Journal d’audit', '✓', '✓', '✓', '—', '—', '—', '—', '—'],
        ['Demandes d’accès', '✓', 'lecture', '—', '—', '—', 'périmètre', '—', '—'],
        ['Utilisateurs et rôles', '✓', 'lecture', '—', '—', '—', '—', '—', '—'],
        ['Permissions', '✓', '—', '—', '—', '—', '—', '—', '—'],
        ['Bourses (instruction)', '✓', 'lecture', '—', '—', '—', '—', '—', '—'],
    ],
    [4.4, 1.5, 1.4, 1.6, 1.8, 1.7, 1.8, 1.6, 1.2],
    font=7.9, header_font=7.6, align_center={1, 2, 3, 4, 5, 6, 7, 8},
)

para(
    'Légende : ✓ = accès complet selon le rôle ; « lecture » = consultation '
    'sans écriture métier ; « périmètre » = limité aux rôles de son équipe ; '
    '— = non accessible. Les rôles ADMIN et SUPER_ADMIN sont toujours '
    'autorisés en lecture sur les écrans protégés par un rôle métier.',
    size=8.6, italic=True, color=MUTED,
)


h1('', 'Annexe B — Adresses des écrans')

table(
    ['Écran', 'Adresse relative'],
    [
        ['Accueil public', '/'],
        ['Connexion', '/login/'],
        ['Créer un compte', '/register/'],
        ['Demande d’accès (Clerk)', '/demande-acces/'],
        ['Attente d’approbation', '/pending-approval/'],
        ['Candidature bourse', '/bourses/candidature/'],
        ['Suivi de candidature', '/bourses/suivi/'],
        ['Tableau de bord (aiguillage)', '/dashboard/'],
        ['Mon profil', '/dashboard/profil/'],
        ['Accueil et visites', '/dashboard/accueil/'],
        ['Secrétariat', '/dashboard/secretaire/'],
        ['Étudiants', '/dashboard/secretaire/etudiants/'],
        ['Nouvelle inscription', '/dashboard/secretaire/inscriptions/nouvelle/'],
        ['Pédagogie — cahier de texte', '/dashboard/pedagogie/cahier-de-texte/'],
        ['Pédagogie — séances', '/dashboard/pedagogie/seances/'],
        ['Pédagogie — présences', '/dashboard/pedagogie/presences/'],
        ['Pédagogie — progression', '/dashboard/pedagogie/progression/'],
        ['Comptabilité', '/dashboard/comptabilite/'],
        ['Journal comptable', '/dashboard/comptabilite/journal/'],
        ['Paiement étudiant', '/dashboard/comptabilite/paiement/'],
        ['Paiements par mois', '/dashboard/comptabilite/paiement/mois/'],
        ['Caisses & comptes', '/dashboard/comptabilite/caisses/'],
        ['Clôtures', '/dashboard/comptabilite/clotures/'],
        ['Direction', '/dashboard/direction/'],
        ['Formateur', '/dashboard/formateur/'],
        ['Étudiant', '/dashboard/etudiant/'],
        ['Responsable pédagogique', '/dashboard/responsable-pedagogique/'],
        ['Administration', '/dashboard/admin/'],
        ['Super administration', '/dashboard/super-admin/'],
        ['Utilisateurs', '/dashboard/super-admin/users/'],
        ['Permissions', '/dashboard/super-admin/permissions/'],
        ['Journal d’audit', '/dashboard/super-admin/audit/'],
    ],
    [7.4, 9.6],
    font=8.8, header_font=8.8, bold_first=True,
)


h1('', 'Annexe C — Checklists')

h2('C.1 Ouverture de journée (accueil / caisse)')

bullet('vérifier les soldes des caisses et signaler tout solde négatif ;')
bullet('consulter les visites du jour et les relances à effectuer ;')
bullet('contrôler les inscriptions en attente de validation ;')
bullet('vérifier les paiements de la veille et les reçus manquants.')

h2('C.2 Encaisser un paiement')

bullet('identifier l’étudiant et confirmer le dossier ;')
bullet('vérifier que l’inscription est active (validée) ;')
bullet('lire le net dû et le reste à payer ;')
bullet('saisir un montant inférieur ou égal au reste ;')
bullet('choisir le moyen, la caisse, le motif et le mois ;')
bullet('enregistrer, imprimer le reçu et le remettre ;')
bullet('vérifier le nouveau solde du dossier.')

h2('C.3 Valider une inscription')

bullet('ouvrir la fiche du dossier en attente ;')
bullet('contrôler l’étudiant, le groupe, le tarif, la remise et le net ;')
bullet('vérifier que les pièces obligatoires sont au dossier ;')
bullet('cliquer sur « Valider l’inscription » ;')
bullet('confirmer que le compte étudiant est actif et que le dossier est '
       'encaissable.')

h2('C.4 Clôture de caisse')

bullet('compter physiquement l’espèce et relever le solde Mobile Money ;')
bullet('ouvrir « Clôtures » → « Nouvelle clôture » ;')
bullet('saisir le montant compté et lire l’écart calculé ;')
bullet('documenter tout écart dans le commentaire ;')
bullet('enregistrer et conserver la trace.')

h2('C.5 Fin de mois')

bullet('rapprocher le journal comptable et les soldes de caisses ;')
bullet('contrôler les paiements par mois et les dossiers non soldés ;')
bullet('relancer les prospects en attente ;')
bullet('exporter la supervision financière pour archivage ;')
bullet('vérifier que les sauvegardes sont récentes.')


h1('', 'Annexe D — Glossaire')

table(
    ['Terme', 'Définition'],
    [
        ['Audit', 'Journal horodaté des actions sensibles, avec auteur et valeurs avant/après.'],
        ['Caisse', 'Compte physique ou mobile qui porte les mouvements d’argent.'],
        ['Clôture', 'Contrôle de fin de journée comparant solde théorique et montant compté.'],
        ['Clerk', 'Service de connexion sécurisée (Google ou e-mail) proposé en complément du formulaire interne.'],
        ['Code interne', 'Identifiant lisible attribué par la plateforme (UA-ETU-…, UA-CPT-…).'],
        ['Dossier', 'Synonyme d’inscription : un étudiant dans un groupe, avec son volet financier.'],
        ['Encaissement', 'Paiement d’un étudiant, rattaché à un dossier et à une caisse.'],
        ['FCFA', 'Franc CFA, devise utilisée pour les montants.'],
        ['Groupe', 'Classe concrète rattachée à une formation, avec période et horaires.'],
        ['Net dû', 'Tarif moins remise.'],
        ['Permission', 'Droit fin accordé à un rôle (lire, écrire, exporter).'],
        ['Prospect', 'Contact intéressé, suivi par des relances.'],
        ['Reste à payer', 'Net dû moins paiements validés ; plafond de l’encaissement.'],
        ['Rôle', 'Métier de l’utilisateur, qui détermine ses menus et ses droits.'],
        ['Séance', 'Cours daté avec horaires, contenu et compte rendu.'],
        ['Statut de compte', 'Actif, en attente, suspendu, désactivé, refusé.'],
        ['Transfert', 'Mouvement neutre entre deux caisses, sans impact sur le résultat global.'],
    ],
    [4.4, 12.6],
    font=8.8, header_font=8.8, bold_first=True,
)


# ---- Fin -------------------------------------------------------------------

doc.add_page_break()
para(
    'Ce guide décrit la plateforme telle qu’elle fonctionne aujourd’hui. '
    'Lorsqu’un écran évolue, la logique reste la même : vérifier le rôle, '
    'vérifier le dossier, enregistrer, puis contrôler le résultat dans la '
    'liste ou le journal.',
    italic=True, color=MUTED,
)
para(
    'Univers Academy — Centre de Formation en Langues · Brazzaville',
    size=9, color=MUTED,
)

doc.save(OUT)
print('Document généré :', os.path.abspath(OUT))
