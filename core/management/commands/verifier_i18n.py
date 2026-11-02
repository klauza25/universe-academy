"""Portique « pas de mélange » : le français qui reste non balisé."""

from pathlib import Path

import polib
from django.conf import settings
from django.core.management.base import BaseCommand

from core import i18n_tools


def couper(releves, maxi):
    return releves if maxi <= 0 else releves[:maxi]


class Command(BaseCommand):
    help = ("Liste les littéraux français non balisés et les msgid sans "
            "traduction anglaise. Code de sortie 1 tant qu'il reste du travail.")

    def add_arguments(self, parser):
        parser.add_argument('--maxi', type=int, default=8,
                            help='Lignes remontées par fichier (0 = tout).')
        parser.add_argument('--sans-catalogue', action='store_true',
                            help='Ignorer la vérification des msgid.')
        parser.add_argument('--langue', default='en')

    def handle(self, *args, **options):
        i18n_tools.sortie_utf8()
        total = self._baliser(options)
        if not options['sans_catalogue']:
            total += self._catalogue(options['langue'])

        if total:
            self.returncode = 1
            self.stdout.write(self.style.ERROR(
                f'\n{total} point(s) restant(s) pour un rendu sans mélange.'))
        else:
            self.stdout.write(self.style.SUCCESS(
                'Interface entièrement balisée et traduite.'))

    def _baliser(self, options) -> int:
        total = 0
        fichiers = [(c, False) for c in i18n_tools.gabarits()]
        fichiers += [(c, True) for c in i18n_tools.sources_python()]
        for chemin, python in fichiers:
            source = chemin.read_text(encoding='utf-8')
            releves = i18n_tools.litteraux_francophone(source, python=python)
            if not releves:
                continue
            total += len(releves)
            relative = chemin.relative_to(Path(settings.BASE_DIR))
            self.stdout.write(f'\n{relative} — {len(releves)}')
            for ligne, extrait in couper(releves, options['maxi']):
                self.stdout.write(f'  :{ligne}  {extrait}')
        return total

    def _catalogue(self, langue: str) -> int:
        chemin_po = (Path(settings.LOCALE_PATHS[0]) / langue
                     / 'LC_MESSAGES' / 'django.po')
        if not chemin_po.exists():
            self.stdout.write(self.style.WARNING(
                f'\ncatalogue {chemin_po} absent : lancer compiler_traductions.'))
            return 0
        manquant = [e.msgid for e in polib.pofile(str(chemin_po)) if not e.msgstr]
        if manquant:
            self.stdout.write(self.style.WARNING(
                f'\n{len(manquant)} msgid sans traduction {langue} :'))
            for msgid in couper(manquant, 25):
                self.stdout.write(f'  {msgid[:80]}')
        return len(manquant)
