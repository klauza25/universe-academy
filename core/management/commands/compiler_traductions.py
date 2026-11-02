"""Extrait les msgid balisés et les compile en .mo, sans binaires gettext."""

from pathlib import Path

import polib
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core import i18n_tools


class Command(BaseCommand):
    help = ("Récupère tous les msgid {% trans %}/gettext_lazy() du projet, "
            "met à jour le catalogue .po et le compile en .mo.")

    def add_arguments(self, parser):
        parser.add_argument('--langue', default='en')
        parser.add_argument('--verifier', action='store_true',
                            help="Ne rien écrire, signaler seulement les écarts.")

    def handle(self, *args, **options):
        i18n_tools.sortie_utf8()
        langue = options['langue']
        dossier = Path(settings.LOCALE_PATHS[0]) / langue / 'LC_MESSAGES'
        chemin_po = dossier / 'django.po'
        chemin_mo = dossier / 'django.mo'

        msgids = set()
        for chemin in i18n_tools.gabarits():
            msgids.update(self._msgid_fichier(chemin.read_text(encoding='utf-8')))
        for chemin in i18n_tools.sources_python():
            msgids.update(self._msgid_fichier(
                chemin.read_text(encoding='utf-8'), python=True))

        catalogue = self._charger(chemin_po, langue)
        self._fusionner_fragments(catalogue, dossier)
        existants = {e.msgid for e in catalogue}
        ajoutés = sorted(msgids - existants)
        retirés = sorted(existants - msgids)

        for msgid in ajoutés:
            catalogue.append(polib.POEntry(msgid=msgid, msgstr=''))
        for msgid in retirés:
            catalogue.remove(next(e for e in catalogue if e.msgid == msgid))

        manquant = [e.msgid for e in catalogue if not e.msgstr and e.msgid in msgids]

        if options['verifier']:
            self.stdout.write(self.style.WARNING(
                f'{len(ajoutés)} msgid à ajouter, {len(retirés)} devenus inutiles, '
                f'{len(manquant)} sans traduction.'))
            return

        dossier.mkdir(parents=True, exist_ok=True)
        catalogue.save(str(chemin_po))
        catalogue.save_as_mofile(str(chemin_mo))

        self.stdout.write(self.style.SUCCESS(
            f'{chemin_mo.name} compilé : {len(catalogue)} msgid, '
            f'{len(ajoutés)} ajoutés, {len(manquant)} sans traduction.'))
        if retirés:
            self.stdout.write(self.style.NOTICE(
                f'{len(retirés)} msgid retirés (plus balisés nulle part).'))

    @staticmethod
    def _fusionner_fragments(catalogue, dossier: Path) -> int:
        """Applique les msgstr rédigés dans locale/<lang>/LC_MESSAGES/fragments/*.po.

        Chaque zone peut livrer son fragment sans que deux personnes n'écrivent
        dans le même django.po.
        """
        appliqués = 0
        dossier_frag = dossier / 'fragments'
        if not dossier_frag.exists():
            return appliqués
        for chemin in sorted(dossier_frag.glob('*.po')):
            for entree in polib.pofile(str(chemin)):
                if not entree.msgstr:
                    continue
                cible = catalogue.find(entree.msgid)
                if cible is None:
                    catalogue.append(polib.POEntry(
                        msgid=entree.msgid, msgstr=entree.msgstr))
                elif not cible.msgstr:
                    cible.msgstr = entree.msgstr
                appliqués += 1
        return appliqués

    @staticmethod
    def _msgid_fichier(source, python=False):
        msgids, _ = i18n_tools.extraire(source, python=python)
        return [m for m in msgids if m]

    @staticmethod
    def _charger(chemin_po: Path, langue: str) -> polib.POFile:
        # Le header porte le charset : sans lui Django décode mal les msgstr
        # accentués à la lecture du .mo.
        metadonnees = {
            'Project-Id-Version': 'Univers Academy',
            'Report-Msgid-Bugs-To': '',
            'MIME-Version': '1.0',
            'Content-Type': 'text/plain; charset=UTF-8',
            'Content-Transfer-Encoding': '8bit',
            'Language': langue,
            'Plural-Forms': 'nplurals=2; plural=(n != 1);',
        }
        if chemin_po.exists():
            catalogue = polib.pofile(str(chemin_po))
            catalogue.metadata.update(metadonnees)
            return catalogue
        catalogue = polib.POFile()
        catalogue.metadata = metadonnees
        return catalogue
