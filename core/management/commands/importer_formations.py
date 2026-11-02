"""Vague 1 de l'import : les formations rencontrées dans les classeurs.

Relit ``docs/donnees`` avec les règles de ``analyser_donnees``, retient les intitulés absents
du catalogue et pose une ligne par formation : durée convenue (9 mois),
frais = mensualité réellement pratiquée × durée. Les déclarations sont dans ``core.programme_import``.

    python manage.py importer_formations           # prévisualisation, aucune écriture
    python manage.py importer_formations --ecrire  # après accord de la direction

Aucune ligne existante n'est modifiée : une formation déjà au catalogue est sautée.
"""
from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core import programme_import as programme
from core.models import Course, Enrollment
from .analyser_donnees import Command as Analyseur


class Command(BaseCommand):
    help = ('Crée dans le catalogue les formations vues dans les classeurs de docs/donnees '
            '(tarif lu dans les encaissements, aucune ligne existante modifiée)')

    def add_arguments(self, parser):
        parser.add_argument('--repertoire', default=None, help='Dossier des classeurs')
        parser.add_argument('--duree', type=int, default=programme.DUREE_MOIS,
                            help='Durée en mois appliquée aux nouvelles formations')
        parser.add_argument('--ecrire', action='store_true',
                            help='Écrire en base (sans cette option, simple prévisualisation)')
        parser.add_argument('--corriger', action='store_true',
                            help='Reprendre le tarif des lignes marquées par l\'import, '
                                 'jamais une formation manuelle ni un dossier déjà inscrit')

    def handle(self, *args, **options):
        dossier = Path(options['repertoire'] or Path(settings.BASE_DIR) / 'docs' / 'donnees')
        analyseur = Analyseur()
        analyseur.details = 5
        analyseur.collecter(dossier)
        if analyseur.inaccessibles:
            raise CommandError('Classeur ouvert dans Excel, donc illisible : '
                               f'{", ".join(analyseur.inaccessibles)}. Fermez-le et relancez.')

        observees = analyseur.catalogue
        self._controler(analyseur._appariement(), observees)
        duree = options['duree']
        lignes = sorted(
            ((titre, domaine, programme.mensuel_observee(observees, cle, repli))
             for cle, (titre, domaine, repli) in programme.FORMATIONS.items()),
            key=lambda l: (l[1], l[0]))

        for titre, domaine, mensuel in lignes:
            total = mensuel * duree
            existante = Course.objects.filter(title__iexact=titre).first()
            if existante and not options['corriger']:
                self.stdout.write(self.style.WARNING(
                    f'  ignorée  {titre} — déjà au catalogue '
                    f'({existante.fee_amount:,} FCFA sur {existante.duration_months} mois)'
                    .replace(',', ' ')))
                continue
            if existante:
                if programme.MARQUE not in existante.description:
                    self.stdout.write(self.style.WARNING(
                        f'  non touchée {titre} — ligne antérieure à l\'import, '
                        'sauf accord explicite pour la reprendre'))
                    continue
                dossier = Enrollment.objects.filter(session__course=existante).exists()
                if dossier:
                    self.stdout.write(self.style.WARNING(
                        f'  non touchée {titre} — des inscriptions existent, '
                        'son tarif engagé ne se rejoue pas'))
                    continue
                if (existante.fee_amount, existante.duration_months) == (total, duree):
                    attendu = self._description(mensuel)
                    if existante.description != attendu:
                        if options['ecrire']:
                            existante.description = attendu
                            existante.save(update_fields=['description'])
                        self.stdout.write(f'  description reprise {titre}')
                    self.stdout.write(f'  conforme {titre} | {domaine} | '
                                      f'{mensuel:,} FCFA/mois x {duree} = {total:,} FCFA'
                                      .replace(',', ' '))
                    continue
                self.stdout.write(f'  {"corrigée" if options["ecrire"] else "à corriger"}'
                                  f' {titre} | {domaine} | {mensuel:,} FCFA/mois x {duree} = '
                                  f'{total:,} FCFA (au lieu de {existante.fee_amount:,})'
                                  .replace(',', ' '))
                if options['ecrire']:
                    existante.duration_months = duree
                    existante.fee_amount = total
                    existante.description = self._description(mensuel)
                    existante.save(update_fields=['duration_months', 'fee_amount', 'description'])
                continue
            self.stdout.write(f'  {"écrite " if options["ecrire"] else "à créer"}'
                              f' {titre} | {domaine} | {mensuel:,} FCFA/mois x {duree} = '
                              f'{total:,} FCFA'.replace(',', ' '))
            if options['ecrire']:
                Course.objects.create(
                    title=titre, domain=domaine, duration_months=duree, fee_amount=total,
                    description=self._description(mensuel))

        if options['ecrire']:
            self.stdout.write(self.style.SUCCESS(f'\nCatalogue : {Course.objects.count()} formations.'))
        else:
            self.stdout.write(self.style.WARNING(
                f'\nPrévisualisation : {len(lignes)} formations déclarées, {duree} mois, '
                f'{programme.FRAIS_INSCRIPTION:,} FCFA d\'inscription. Le catalogue n\'a pas de champ '
                'pour les frais d\'inscription : ils seront posés comme un paiement lors de la '
                'vague des inscriptions. Relancez avec --ecrire après validation.'
                .replace(',', ' ')))

    @staticmethod
    def _description(mensuel: int) -> str:
        return (f'Mensualité retenue {programme.MARQUE} : {mensuel} FCFA. '
                f"Frais d'inscription : {programme.FRAIS_INSCRIPTION} FCFA.")

    # ------------------------------------------------------------------
    @staticmethod
    def _controler(appariees: dict, observees: dict) -> None:
        """Portique : tout intitulé observé est déclaré, fondu dans une parente ou écarté — jamais deviné."""
        declarees = (set(programme.FORMATIONS) | set(programme.PROMOTIONS)
                     | set(programme.FUSIONS) | programme.HORS_CATALOGUE)
        absentes = sorted(cle for cle in programme.FORMATIONS if cle not in observees)
        if absentes:
            raise CommandError('Intitulé attendu introuvable dans les classeurs : '
                               + ', '.join(absentes))
        inclassables = sorted(cle for cle, (titre, _n) in appariees.items()
                              if titre is None and cle not in declarees)
        if inclassables:
            raise CommandError('Intitulé sans formation au catalogue et non déclaré à l\'import : '
                               + ', '.join(inclassables)
                               + '. Le déclarer dans core/programme_import.py avant d\'écrire.')
