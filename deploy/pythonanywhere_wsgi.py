"""Point d'entrée WSGI pour PythonAnywhere (projet academy / univers_academy).

PythonAnywhere exécute l'application à travers un fichier WSGI que l'onglet
« Web » désigne. Celui-ci ajoute le dossier du projet au ``sys.path`` puis
délègue à l'application Django habituelle — le chemin du projet est calculé
depuis le dossier personnel du compte, il fonctionne donc quel que soit
l'identifiant PythonAnywhere.

Dans l'onglet « Web », réglez :
  - « WSGI configuration file » : /home/VOTRE-COMPTE/academy/deploy/pythonanywhere_wsgi.py
  - « Virtualenv » : /home/VOTRE-COMPTE/.virtualenvs/academy
  - « Working directory » : /home/VOTRE-COMPTE/academy
"""

import os
import sys
from pathlib import Path

BASE = Path.home() / 'academy'
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

os.environ['DJANGO_SETTINGS_MODULE'] = 'univers_academy.settings'

from django.core.wsgi import get_wsgi_application  # noqa: E402

application = get_wsgi_application()
