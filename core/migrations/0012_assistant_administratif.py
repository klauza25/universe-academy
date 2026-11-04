"""Le poste « Assistant administratif » remplace Accueil et Caisse.

Les deux comptes en service reçoivent le rôle fusionné ; les lignes
``COMPTABLE`` et ``ACCUEIL`` restent en base pour que l'audit, les paiements
encaissés et les demandes d'accès passées gardent leur signature. Le lien est
recréé avec ``assigned_by`` repris de l'ancien lien : la fusion ne perd pas
l'auteur de la nomination.
"""

from django.db import migrations

POSTES_DISSOUS = ('ACCUEIL', 'COMPTABLE')
# Le code interne porte la racine du poste : elle sert à refaire la fusion à
# l'envers, sans table d'union ni donnée inventée.
RACINES = {'UA-CPT': 'COMPTABLE', 'UA-ACC': 'ACCUEIL'}


def fusionne(apps, schema_editor):
    Role = apps.get_model('core', 'Role')
    UserRole = apps.get_model('core', 'UserRole')

    assistant, _ = Role.objects.get_or_create(
        key='ASSISTANT_ADMIN',
        defaults={'label': 'Assistant administratif', 'is_privileged': False},
    )
    for poste in POSTES_DISSOUS:
        ancien = Role.objects.filter(key=poste).first()
        if ancien is None:
            continue
        for lien in UserRole.objects.filter(role=ancien).select_related('user'):
            UserRole.objects.get_or_create(
                user_id=lien.user_id, role=assistant,
                defaults={'assigned_by_id': lien.assigned_by_id},
            )
            lien.delete()


def demele(apps, schema_editor):
    Role = apps.get_model('core', 'Role')
    UserRole = apps.get_model('core', 'UserRole')

    assistant = Role.objects.filter(key='ASSISTANT_ADMIN').first()
    if assistant is None:
        return
    for lien in UserRole.objects.filter(role=assistant).select_related('user'):
        poste = next(
            (cle for racine, cle in RACINES.items()
             if (lien.user.internal_code or '').startswith(racine)), None)
        if poste is None:
            continue
        role = Role.objects.filter(key=poste).first()
        if role is None:
            continue
        UserRole.objects.get_or_create(
            user_id=lien.user_id, role=role,
            defaults={'assigned_by_id': lien.assigned_by_id},
        )
        lien.delete()
    assistant.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0011_reprise_mois_paiements'),
    ]

    operations = [
        migrations.RunPython(fusionne, demele),
    ]
