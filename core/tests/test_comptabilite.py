"""Tests de la comptabilité : journal, caisses, clôtures et paiements."""
import datetime as dt
import importlib
from datetime import timedelta

from django.apps import apps
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.urls import reverse
from django.utils import timezone

from core import caisse
from core.forms import CashTransactionForm
from core.models import (
    CashAccount, CashClosure, CashTransaction, Enrollment, Expense, Payment,
    RoleKey, TransactionCategory,
)
from core.views_comptabilite import account_balance

from .base import BusinessTestBase


class AccountingTestBase(BusinessTestBase):
    def setUp(self):
        self.client = self.client_for(self.assistant)

    def make_tx(self, tx_type=CashTransaction.Type.IN, amount=10000,
                account=None, destination=None, status=CashTransaction.Status.VALIDATED,
                occurred_at=None, label='Opération de test', **kwargs):
        if tx_type == CashTransaction.Type.IN:
            category = self.income_category
        elif tx_type == CashTransaction.Type.OUT:
            category = self.expense_category
        else:
            category = self.transfer_category
        return CashTransaction.objects.create(
            tx_type=tx_type,
            category=kwargs.pop('category', category),
            label=label,
            amount=amount,
            occurred_at=occurred_at or timezone.now(),
            account=account or self.cash,
            destination_account=destination,
            method=Payment.Method.CASH,
            status=status,
            created_by=self.assistant,
            **kwargs,
        )

    def tx_payload(self, **overrides):
        payload = {
            'tx_type': CashTransaction.Type.IN,
            'category': self.income_category.pk,
            'label': 'Recette diverse',
            'description': 'Encaissement de test',
            'amount': '25000',
            'occurred_at': self.local_datetime(),
            'method': Payment.Method.CASH,
            'account': self.cash.pk,
            'destination_account': '',
            'counterparty': 'Client test',
            'status': CashTransaction.Status.VALIDATED,
            'note': '',
            # Une sortie qui consomme le solde se confirme avant d'être posée :
            # la plupart des scénarios laissent l'agent cocher la case.
            'confirme': 'on',
        }
        payload.update(overrides)
        return payload

    def payment_payload(self, **overrides):
        payload = {
            'enrollment': self.enrollment.pk,
            'amount': '30000',
            'method': Payment.Method.CASH,
            'account': self.cash.pk,
            'paid_at': self.local_datetime(),
            'motif': Payment.Motif.OTHER,
            'note': '',
        }
        payload.update(overrides)
        return payload

    def mois_payload(self, **overrides):
        """La grille des mois : un mois coché = une ligne = un paiement."""
        payload = {
            'annee': str(self.today.year),
            'enrollment': self.enrollment.pk,
            'method': Payment.Method.CASH,
            'account': self.cash.pk,
            'note': '',
        }
        payload.update(overrides)
        return payload


class JournalTests(AccountingTestBase):
    def test_journal_lists_validated_operations(self):
        incoming = self.make_tx(label='Entrée A')
        outgoing = self.make_tx(
            tx_type=CashTransaction.Type.OUT, amount=4000, label='Sortie B')
        response = self.client.get(reverse('core:dashboard:journal'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {tx.pk for tx in response.context['page'].object_list},
            {incoming.pk, outgoing.pk},
        )

    def test_journal_filters_by_type_and_search(self):
        incoming = self.make_tx(label='Paiement special')
        self.make_tx(
            tx_type=CashTransaction.Type.OUT, amount=4000, label='Achat stylos')
        response = self.client.get(
            reverse('core:dashboard:journal'), {'type': 'OUT'})
        self.assertEqual(
            [tx.label for tx in response.context['page'].object_list],
            ['Achat stylos'],
        )
        response = self.client.get(
            reverse('core:dashboard:journal'), {'q': 'special'})
        self.assertEqual(
            [tx.pk for tx in response.context['page'].object_list],
            [incoming.pk],
        )

    def test_journal_totals_ignore_cancelled_operations(self):
        self.make_tx(amount=10000)
        self.make_tx(
            tx_type=CashTransaction.Type.OUT, amount=3000,
            status=CashTransaction.Status.CANCELLED,
        )
        response = self.client.get(reverse('core:dashboard:journal'))
        self.assertEqual(response.context['totals']['incoming'], 10000)
        self.assertIsNone(response.context['totals']['outgoing'])

    def test_journal_csv_export(self):
        tx = self.make_tx(label='Ligne exportée')
        response = self.client.get(
            reverse('core:dashboard:journal'), {'export': 'csv'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv; charset=utf-8')
        content = response.content.decode('utf-8-sig')
        self.assertIn('Référence', content)
        self.assertIn(tx.reference, content)
        self.assertIn('Ligne exportée', content)
        self.assert_audited('JOURNAL_EXPORT')


class CashTransactionTests(AccountingTestBase):
    def test_create_incoming_transaction(self):
        response = self.client.post(
            reverse('core:dashboard:transaction-create'),
            self.tx_payload(),
        )
        tx = CashTransaction.objects.get(label='Recette diverse')
        self.assertRedirects(
            response,
            reverse('core:dashboard:transaction-detail', args=[tx.pk]),
            fetch_redirect_response=False,
        )
        self.assertEqual(tx.tx_type, CashTransaction.Type.IN)
        self.assertEqual(tx.amount, 25000)
        self.assertEqual(tx.created_by, self.assistant)
        self.assertTrue(tx.reference.startswith('TRX-'))
        self.assertEqual(account_balance(self.cash), 25000)
        self.assert_audited('CASH_TRANSACTION_CREATE', tx.pk)

    def test_transfer_requires_distinct_destination(self):
        response = self.client.post(
            reverse('core:dashboard:transaction-create'),
            self.tx_payload(
                tx_type=CashTransaction.Type.TRANSFER,
                category=self.transfer_category.pk,
                account=self.cash.pk,
                destination_account='',
            ),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(CashTransaction.objects.count(), 0)

        response = self.client.post(
            reverse('core:dashboard:transaction-create'),
            self.tx_payload(
                tx_type=CashTransaction.Type.TRANSFER,
                category=self.transfer_category.pk,
                account=self.cash.pk,
                destination_account=self.cash.pk,
            ),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(CashTransaction.objects.count(), 0)

    def test_category_direction_must_match_type(self):
        response = self.client.post(
            reverse('core:dashboard:transaction-create'),
            self.tx_payload(category=self.expense_category.pk),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(CashTransaction.objects.count(), 0)

    def test_cancellation_requires_a_reason(self):
        tx = self.make_tx()
        url = reverse('core:dashboard:transaction-detail', args=[tx.pk])
        response = self.client.post(url, {'action': 'cancel', 'reason': ''})
        self.assertRedirects(response, url, fetch_redirect_response=False)
        tx.refresh_from_db()
        self.assertEqual(tx.status, CashTransaction.Status.VALIDATED)

        response = self.client.post(
            url, {'action': 'cancel', 'reason': 'Erreur de saisie'})
        self.assertRedirects(response, url, fetch_redirect_response=False)
        tx.refresh_from_db()
        self.assertEqual(tx.status, CashTransaction.Status.CANCELLED)
        self.assertIn('Erreur de saisie', tx.note)
        self.assert_audited('CASH_TRANSACTION_CANCEL', tx.pk)
        self.assertEqual(account_balance(self.cash), 0)


class SoldeDeCaisseJamaisNegatifTests(AccountingTestBase):
    """Une caisse ne peut pas sortir plus d'argent qu'elle n'en a.

    Un solde négatif n'est pas un découvert : c'est une dépense inventée ou une
    recette oubliée. Dès qu'il existe, aucun état de caisse ne représente
    l'argent réellement disponible.
    """

    def test_une_sortie_superieure_au_solde_est_refusee(self):
        self.make_tx(amount=30000, label='Recette')
        page = self.client.post(
            reverse('core:dashboard:transaction-create'),
            self.tx_payload(tx_type=CashTransaction.Type.OUT,
                            category=self.expense_category.pk,
                            amount='50000', label='Sortie trop lourde'),
        )
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'Solde insuffisant')
        self.assertEqual(
            CashTransaction.objects.filter(
                tx_type=CashTransaction.Type.OUT).count(), 0)
        self.assertEqual(account_balance(self.cash), 30000)

    def test_la_sortie_juste_a_equilibre_passe(self):
        self.make_tx(amount=30000, label='Recette')
        response = self.client.post(
            reverse('core:dashboard:transaction-create'),
            self.tx_payload(tx_type=CashTransaction.Type.OUT,
                            category=self.expense_category.pk,
                            amount='30000', label='Sortie à égalité'),
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(account_balance(self.cash), 0)

    def test_un_transfert_ne_vide_pas_la_caisse_source(self):
        self.make_tx(amount=30000, label='Recette')
        page = self.client.post(
            reverse('core:dashboard:transaction-create'),
            self.tx_payload(tx_type=CashTransaction.Type.TRANSFER,
                            category=self.transfer_category.pk,
                            amount='40000', label='Transfert trop lourd',
                            destination_account=self.mobile.pk),
        )
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'Solde insuffisant')
        self.assertEqual(CashTransaction.objects.count(), 1)
        self.assertEqual(account_balance(self.cash), 30000)
        self.assertEqual(account_balance(self.mobile), 0)

    def test_annuler_une_entree_deja_dependue_est_refuse(self):
        entree = self.make_tx(amount=100000, label='Recette')
        self.make_tx(tx_type=CashTransaction.Type.OUT, amount=80000,
                     label='Sortie')
        url = reverse('core:dashboard:transaction-detail', args=[entree.pk])
        page = self.client.post(
            url, {'action': 'cancel', 'reason': 'Erreur de saisie'}, follow=True)
        self.assertContains(page, 'Annulation refusée')
        entree.refresh_from_db()
        self.assertEqual(entree.status, CashTransaction.Status.VALIDATED)
        self.assertEqual(account_balance(self.cash), 20000)

    def test_annuler_une_entree_non_dependue_reste_possible(self):
        entree = self.make_tx(amount=100000, label='Recette')
        url = reverse('core:dashboard:transaction-detail', args=[entree.pk])
        self.client.post(url, {'action': 'cancel', 'reason': 'Doublon'})
        entree.refresh_from_db()
        self.assertEqual(entree.status, CashTransaction.Status.CANCELLED)
        self.assertEqual(account_balance(self.cash), 0)

    def test_un_brouillon_ne_compte_pas_en_caisse(self):
        """Le brouillon reste saisissable ; il n'est validé nulle part sans argent."""
        response = self.client.post(
            reverse('core:dashboard:transaction-create'),
            self.tx_payload(tx_type=CashTransaction.Type.OUT,
                            category=self.expense_category.pk,
                            amount='50000', label='Brouillon attentif',
                            status=CashTransaction.Status.DRAFT),
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(account_balance(self.cash), 0)


class AccountAndBalanceTests(AccountingTestBase):
    def test_account_balances(self):
        self.make_tx(amount=50000)
        self.make_tx(tx_type=CashTransaction.Type.OUT, amount=20000)
        self.make_tx(
            tx_type=CashTransaction.Type.TRANSFER, amount=10000,
            account=self.cash, destination=self.mobile,
        )
        self.assertEqual(account_balance(self.cash), 20000)
        self.assertEqual(account_balance(self.mobile), 10000)

    def test_transfer_is_neutral_globally(self):
        self.make_tx(amount=50000)
        self.make_tx(
            tx_type=CashTransaction.Type.TRANSFER, amount=30000,
            account=self.cash, destination=self.mobile,
        )
        total = account_balance(self.cash) + account_balance(self.mobile)
        self.assertEqual(total, 50000)
        self.assertEqual(account_balance(self.cash), 20000)
        self.assertEqual(account_balance(self.mobile), 30000)

    def test_account_list_creates_account(self):
        response = self.client.get(reverse('core:dashboard:accounts'))
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            reverse('core:dashboard:accounts'),
            {
                'name': 'Caisse secondaire',
                'kind': CashAccount.Kind.CASH,
                'currency': 'XAF',
                'opening_balance': '15000',
                'active': 'on',
            },
        )
        self.assertRedirects(
            response, reverse('core:dashboard:accounts'),
            fetch_redirect_response=False,
        )
        account = CashAccount.objects.get(name='Caisse secondaire')
        self.assertEqual(account.opening_balance, 15000)
        self.assertEqual(account_balance(account), 15000)
        self.assert_audited('CASH_ACCOUNT_CREATE', account.pk)

    def test_account_page_shows_balances(self):
        self.make_tx(amount=12000)
        response = self.client.get(reverse('core:dashboard:accounts'))
        rows = {row['account'].pk: row['balance']
                for row in response.context['rows']}
        self.assertEqual(rows[self.cash.pk], 12000)


class AdministrationCompteTests(AccountingTestBase):
    """Régler un compte sans toucher à son assiette ni à son histoire."""

    def admin_payload(self, **overrides):
        payload = {
            'kind': CashAccount.Kind.CASH,
            'currency': 'XAF',
            'description': 'Caisse du secrétariat',
            'overdraft_limit': '0',
            'etat': CashAccount.Status.ACTIVE,
            'replaced_by': '',
        }
        payload.update(overrides)
        return payload

    def fiche(self, compte=None):
        return reverse('core:dashboard:account-update',
                       args=[(compte or self.cash).pk])

    def test_la_fiche_du_compte_affiche_solde_et_ecritures(self):
        self.make_tx(amount=12000)
        page = self.client.get(self.fiche())
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, self.cash.name)
        self.assertContains(page, '12000')

    def test_le_reglage_du_compte_est_historise(self):
        page = self.client.post(
            self.fiche(), self.admin_payload(description='Caisse du guichet'))
        self.assertRedirects(
            page, reverse('core:dashboard:accounts'),
            fetch_redirect_response=False,
        )
        self.cash.refresh_from_db()
        self.assertEqual(self.cash.description, 'Caisse du guichet')
        entree = self.assert_audited('CASH_ACCOUNT_EDIT', self.cash.pk)
        self.assertEqual(entree.before_summary['description'], '')
        self.assertEqual(entree.after_summary['description'], 'Caisse du guichet')

    def test_le_solde_ouverture_n_est_pas_modifiable_depuis_la_fiche(self):
        avant = self.cash.opening_balance
        self.client.post(
            self.fiche(), self.admin_payload(opening_balance='999999'))
        self.cash.refresh_from_db()
        self.assertEqual(self.cash.opening_balance, avant)

    def test_un_decouvert_exceptionnel_est_reserve_au_super_administrateur(self):
        refuse = self.client.post(
            self.fiche(), self.admin_payload(overdraft_limit='50000'))
        self.assertContains(refuse, 'réservé au super administrateur')
        self.cash.refresh_from_db()
        self.assertEqual(self.cash.overdraft_limit, 0)

        autorise = self.client_for(self.super_admin).post(
            self.fiche(), self.admin_payload(overdraft_limit='50000'))
        self.assertEqual(autorise.status_code, 302)
        self.cash.refresh_from_db()
        self.assertEqual(self.cash.disponible(), 50000)

    def test_archiver_une_caisse_encore_pleine_demande_un_remplacement(self):
        self.make_tx(amount=40000)
        page = self.client.post(
            self.fiche(), self.admin_payload(etat=CashAccount.Status.ARCHIVED))
        self.assertContains(page, 'qui les reprend')
        self.cash.refresh_from_db()
        self.assertTrue(self.cash.active)

    def test_un_compte_archive_refuse_desormais_toute_ecriture(self):
        self.make_tx(amount=40000)
        self.client.post(
            self.fiche(),
            self.admin_payload(etat=CashAccount.Status.ARCHIVED,
                               replaced_by=self.mobile.pk),
        )
        self.cash.refresh_from_db()
        self.assertEqual(self.cash.status, CashAccount.Status.ARCHIVED)
        self.assertEqual(self.cash.replaced_by, self.mobile)

        page = self.client.post(
            reverse('core:dashboard:transaction-create'),
            self.tx_payload(tx_type=CashTransaction.Type.OUT,
                            category=self.expense_category.pk,
                            amount='1000', label='Trop tard'),
        )
        self.assertContains(page, 'Compte introuvable ou fermé')
        self.assertEqual(CashTransaction.objects.filter(label='Trop tard').count(), 0)

        # Le service, lui, ne passe pas par la liste déroulante : le compte
        # archivé lui aussi refuse d'écrire.
        with self.assertRaises(ValidationError) as refus:
            caisse.poster(caisse=self.cash, montant=1000,
                          sens=CashTransaction.Type.OUT, libelle='Forcer le clos',
                          categorie=self.expense_category)
        self.assertIn('est archivé', str(refus.exception))

    def test_la_devise_d_une_caisse_engagee_ne_change_pas(self):
        self.make_tx(amount=5000)
        page = self.client.post(self.fiche(), self.admin_payload(currency='EUR'))
        self.assertContains(page, 'ne change pas')
        self.cash.refresh_from_db()
        self.assertEqual(self.cash.currency, 'XAF')

    def test_un_compte_inactif_sort_des_listes_de_saisie(self):
        self.client.post(
            self.fiche(), self.admin_payload(etat=CashAccount.Status.INACTIVE))
        self.cash.refresh_from_db()
        self.assertFalse(self.cash.active)
        self.assertEqual(self.cash.status, CashAccount.Status.INACTIVE)
        page = self.client.get(reverse('core:dashboard:transaction-create'))
        self.assertNotIn(
            self.cash.pk, [compte.pk for compte
                           in page.context['form'].fields['account'].queryset])


class AjustementSoldeTests(AccountingTestBase):
    """Un solde se corrige par une écriture traçée, jamais par un chiffre réécrit."""

    def url(self, compte=None):
        return reverse('core:dashboard:account-adjust',
                       args=[(compte or self.cash).pk])

    def test_un_ajustement_laisse_sa_ligne_en_caisse_et_dans_l_audit(self):
        self.make_tx(amount=30000)
        page = self.client.post(self.url(), {
            'montant': '5000', 'sens': CashTransaction.Type.IN,
            'motif': 'Écart de comptage',
        })
        self.assertRedirects(
            page, reverse('core:dashboard:account-update', args=[self.cash.pk]),
            fetch_redirect_response=False,
        )
        ajust = CashTransaction.objects.get(
            nature=CashTransaction.Nature.ADJUSTMENT)
        self.assertEqual(ajust.amount, 5000)
        self.assertEqual(ajust.category.name, 'Ajustements de solde')
        self.assertIn('Écart de comptage', ajust.note)
        self.assertEqual(account_balance(self.cash), 35000)
        self.assert_audited('CASH_TRANSACTION_CREATE', ajust.pk)

    def test_un_ajustement_en_baisse_superieur_au_solde_est_refuse(self):
        self.make_tx(amount=10000)
        page = self.client.post(self.url(), {
            'montant': '25000', 'sens': CashTransaction.Type.OUT,
            'motif': 'Perte présumée',
        })
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'Solde insuffisant')
        self.assertEqual(account_balance(self.cash), 10000)

    def test_un_ajustement_sans_motif_ne_sort_pas(self):
        self.make_tx(amount=10000)
        page = self.client.post(self.url(), {
            'montant': '1000', 'sens': CashTransaction.Type.IN, 'motif': '',
        })
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'obligatoire pour ajuster')
        self.assertEqual(
            CashTransaction.objects.filter(
                nature=CashTransaction.Nature.ADJUSTMENT).count(), 0)

    def test_le_decouvert_autorise_par_le_super_admin_liberate_une_sortie(self):
        self.make_tx(amount=10000)
        self.client_for(self.super_admin).post(
            reverse('core:dashboard:account-update', args=[self.cash.pk]),
            {'kind': self.cash.kind, 'currency': 'XAF', 'description': '',
             'overdraft_limit': '5000', 'etat': CashAccount.Status.ACTIVE,
             'replaced_by': ''},
        )
        page = self.client.post(self.url(), {
            'montant': '14000', 'sens': CashTransaction.Type.OUT,
            'motif': 'Remboursement', 'confirme': 'on',
        })
        self.assertEqual(page.status_code, 302)
        self.assertEqual(account_balance(self.cash), -4000)


class AvertissementSortieTests(AccountingTestBase):
    """Le disponible se lit avant la sortie, et une sortie qui assèche la caisse se confirme."""

    def test_une_sortie_vide_la_caisse_sannonce_avant_validation(self):
        self.make_tx(amount=30000, label='Recette')
        page = self.client.post(
            reverse('core:dashboard:transaction-create'),
            self.tx_payload(tx_type=CashTransaction.Type.OUT,
                            category=self.expense_category.pk,
                            amount='30000', label='Sortie totale',
                            confirme=''),
        )
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'consomme 100 % du solde disponible')
        self.assertContains(page, 'Cochez la case')
        self.assertEqual(
            CashTransaction.objects.filter(
                tx_type=CashTransaction.Type.OUT).count(), 0)
        self.assertEqual(account_balance(self.cash), 30000)

    def test_la_case_cochee_laisse_passer_la_meme_sortie(self):
        self.make_tx(amount=30000, label='Recette')
        response = self.client.post(
            reverse('core:dashboard:transaction-create'),
            self.tx_payload(tx_type=CashTransaction.Type.OUT,
                            category=self.expense_category.pk,
                            amount='30000', label='Sortie assumée'),
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(account_balance(self.cash), 0)

    def test_une_sortie_discrete_ne_demande_aucune_confirmation(self):
        self.make_tx(amount=30000, label='Recette')
        response = self.client.post(
            reverse('core:dashboard:transaction-create'),
            self.tx_payload(tx_type=CashTransaction.Type.OUT,
                            category=self.expense_category.pk,
                            amount='3000', label='Achat de fournitures',
                            confirme=''),
        )
        self.assertEqual(response.status_code, 302)

    def test_une_recette_ne_demande_jamais_confirmation(self):
        response = self.client.post(
            reverse('core:dashboard:transaction-create'),
            self.tx_payload(amount='5000', label='Recette diverse',
                            confirme=''),
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(account_balance(self.cash), 5000)

    def test_un_brouillon_de_sortie_ne_declenche_pas_avertissement(self):
        """Tant que rien ne sort, la caisse n'est pas encore engagée."""
        self.make_tx(amount=10000, label='Recette')
        response = self.client.post(
            reverse('core:dashboard:transaction-create'),
            self.tx_payload(tx_type=CashTransaction.Type.OUT,
                            category=self.expense_category.pk,
                            amount='9000', label='Sortie en brouillon',
                            status=CashTransaction.Status.DRAFT,
                            confirme=''),
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(account_balance(self.cash), 10000)

    def test_le_disponible_se_lit_au_moment_de_choisir_la_caisse(self):
        self.make_tx(amount=25000, label='Recette')
        page = self.client.get(reverse('core:dashboard:transaction-create'))
        self.assertContains(page, 'Solde disponible par caisse')
        self.assertContains(page, 'Caisse principale — disponible 25 000 XAF')

    def test_une_caisse_vide_se_signale_aucun_fonds_disponible(self):
        page = self.client.get(reverse('core:dashboard:transaction-create'))
        self.assertContains(page, 'Aucun fonds disponible')

    def test_la_liste_des_comptes_signale_un_solde_epuise(self):
        page = self.client.get(reverse('core:dashboard:accounts'))
        self.assertContains(page, 'Solde épuisé')

    def test_un_ajustement_en_baisse_qui_assèche_le_solde_se_confirme(self):
        self.make_tx(amount=10000, label='Recette')
        url = reverse('core:dashboard:account-adjust', args=[self.cash.pk])
        page = self.client.post(url, {
            'montant': '9000', 'sens': CashTransaction.Type.OUT,
            'motif': 'Rappel d’encaissement',
        })
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'consomme 90 % du solde disponible')
        response = self.client.post(url, {
            'montant': '9000', 'sens': CashTransaction.Type.OUT,
            'motif': 'Rappel d’encaissement', 'confirme': 'on',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(account_balance(self.cash), 1000)


class ReinitialisationCaisseTests(AccountingTestBase):
    """La remise à zéro emporte le solde, pas l'histoire de la caisse."""

    def url(self, compte=None):
        return reverse('core:dashboard:account-reset',
                       args=[(compte or self.cash).pk])

    def test_la_remise_a_zero_ecrit_une_ecriture_contraire_et_ne_rien_efface(self):
        self.make_tx(amount=40000, label='Recette')
        self.make_tx(tx_type=CashTransaction.Type.OUT, amount=15000,
                     label='Sortie')
        avant = CashTransaction.objects.count()
        page = self.client.post(
            self.url(), {'motif': 'Fin de semaine', 'confirme': 'on'})
        self.assertRedirects(
            page, reverse('core:dashboard:account-update', args=[self.cash.pk]),
            fetch_redirect_response=False,
        )
        self.assertEqual(account_balance(self.cash), 0)
        self.assertEqual(CashTransaction.objects.count(), avant + 1)
        tx = CashTransaction.objects.get(nature=CashTransaction.Nature.RESET)
        self.assertEqual(tx.tx_type, CashTransaction.Type.OUT)
        self.assertEqual(tx.amount, 25000)
        self.assertIn('Fin de semaine', tx.note)

    def test_sans_confirmation_la_remise_a_zero_n_aboutit_pas(self):
        self.make_tx(amount=40000)
        page = self.client.post(self.url(), {'motif': 'Fin de semaine'})
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'confirmation')
        self.assertEqual(account_balance(self.cash), 40000)

    def test_une_caisse_deja_a_zero_ne_recoit_aucune_ecriture(self):
        page = self.client.post(
            self.url(), {'motif': 'Rien à rapprocher', 'confirme': 'on'},
            follow=True)
        self.assertContains(page, 'déjà à zéro')
        self.assertEqual(
            CashTransaction.objects.filter(
                nature=CashTransaction.Nature.RESET).count(), 0)

    def test_la_fiche_signale_les_brouillons_avant_la_remise_a_zero(self):
        self.make_tx(amount=8000)
        self.make_tx(amount=3000, status=CashTransaction.Status.DRAFT,
                     label='Brouillon en attente')
        page = self.client.get(self.url())
        self.assertContains(page, 'Brouillons non rapprochés')
        self.assertContains(page, 'Brouillons encore en attente')


class CategorieEcritureTests(AccountingTestBase):
    """Les catégories du journal se règlent, elles ne se suppriment pas."""

    def ecran(self):
        return reverse('core:dashboard:categories')

    def fiche(self, categorie):
        return reverse('core:dashboard:category-update', args=[categorie.pk])

    def test_une_categorie_se_cree_depuis_lecran_et_laisse_sa_trace(self):
        page = self.client.post(self.ecran(), {
            'name': 'Fournitures de bureau',
            'direction': TransactionCategory.Direction.OUT,
        })
        self.assertRedirects(page, self.ecran(), fetch_redirect_response=False)
        categorie = TransactionCategory.objects.get(name='Fournitures de bureau')
        self.assertEqual(categorie.direction, TransactionCategory.Direction.OUT)
        self.assert_audited('TRANSACTION_CATEGORY_CREATE', categorie.pk)

    def test_un_nom_deja_pris_dans_le_meme_sens_est_refuse(self):
        total = TransactionCategory.objects.count()
        page = self.client.post(self.ecran(), {
            'name': self.income_category.name,
            'direction': self.income_category.direction,
        })
        self.assertEqual(page.status_code, 200)
        self.assertEqual(TransactionCategory.objects.count(), total)

    def test_le_reglage_d_une_categorie_garde_l_ancienne_valeur_d_audit(self):
        page = self.client.post(self.fiche(self.income_category), {
            'name': 'Recettes de scolarité', 'active': 'on',
        })
        self.assertRedirects(page, self.ecran(), fetch_redirect_response=False)
        entree = self.assert_audited(
            'TRANSACTION_CATEGORY_EDIT', self.income_category.pk)
        self.assertEqual(entree.before_summary['nom'], self.income_category.name)
        self.assertEqual(entree.after_summary['nom'], 'Recettes de scolarité')

    def test_le_sens_d_une_categorie_ne_se_regle_plus(self):
        self.client.post(self.fiche(self.income_category), {
            'name': self.income_category.name, 'active': 'on',
            'direction': TransactionCategory.Direction.OUT,
        })
        self.income_category.refresh_from_db()
        self.assertEqual(
            self.income_category.direction, TransactionCategory.Direction.IN)

    def test_une_categorie_desactivee_quitte_les_listes_de_saisie(self):
        self.client.post(self.fiche(self.income_category),
                         {'name': self.income_category.name})
        self.income_category.refresh_from_db()
        self.assertFalse(self.income_category.active)
        form = CashTransactionForm()
        self.assertNotIn(
            self.income_category.pk,
            [c.pk for c in form.fields['category'].queryset])

    def test_l_admin_ne_prte_la_caisse_qu_en_consultation(self):
        for modele in (CashAccount, CashTransaction, TransactionCategory,
                       CashClosure):
            enregistre = admin.site._registry[modele]
            self.assertFalse(enregistre.has_add_permission(None), modele.__name__)
            self.assertFalse(enregistre.has_change_permission(None), modele.__name__)
            self.assertFalse(enregistre.has_delete_permission(None), modele.__name__)


class CorrectionEcritureTests(AccountingTestBase):
    """Une écriture se rectifie, elle ne s'efface pas."""

    def fiche(self, tx):
        return reverse('core:dashboard:transaction-edit', args=[tx.pk])

    def payload(self, tx, **over):
        donnees = {
            'montant': str(tx.amount),
            'categorie': str(tx.category_id),
            'libelle': tx.label,
            'survenu': self.local_datetime(),
            'motif': 'Montant mal saisi',
        }
        donnees.update(over)
        return donnees

    def test_une_ecriture_se_corrige_et_garde_sa_trace(self):
        tx = self.make_tx(amount=10000)
        page = self.client.post(self.fiche(tx), self.payload(tx, montant='15000'))
        self.assertRedirects(
            page, reverse('core:dashboard:transaction-detail', args=[tx.pk]),
            fetch_redirect_response=False)
        tx.refresh_from_db()
        self.assertEqual(tx.amount, 15000)
        self.assertIn('Montant mal saisi', tx.note)
        entree = self.assert_audited('CASH_TRANSACTION_EDIT', tx.pk)
        self.assertEqual(entree.before_summary['amount'], 10000)
        self.assertEqual(account_balance(self.cash), 15000)

    def test_une_sortie_corrigee_trop_haute_est_refusee(self):
        self.make_tx(amount=10000, label='Recette')
        sortie = self.make_tx(tx_type=CashTransaction.Type.OUT, amount=8000,
                              label='Sortie')
        page = self.client.post(self.fiche(sortie),
                                self.payload(sortie, montant='20000'))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'Solde insuffisant')
        sortie.refresh_from_db()
        self.assertEqual(sortie.amount, 8000)
        self.assertEqual(account_balance(self.cash), 2000)

    def test_le_compte_et_le_sens_ne_changent_pas(self):
        tx = self.make_tx(amount=10000)
        self.client.post(self.fiche(tx), self.payload(
            tx, account=str(self.mobile.pk), tx_type=CashTransaction.Type.OUT))
        tx.refresh_from_db()
        self.assertEqual(tx.account_id, self.cash.pk)
        self.assertEqual(tx.tx_type, CashTransaction.Type.IN)

    def test_sans_motif_la_correction_n_aboutit_pas(self):
        tx = self.make_tx(amount=10000)
        page = self.client.post(self.fiche(tx), self.payload(tx, motif=''))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'obligatoire pour corriger')
        tx.refresh_from_db()
        self.assertEqual(tx.amount, 10000)

    def test_une_ecriture_annulee_ne_se_corrige_plus(self):
        tx = self.make_tx(amount=10000)
        caisse.annuler(tx, motif='Doublon', agent=self.assistant)
        page = self.client.get(self.fiche(tx), follow=True)
        self.assertRedirects(
            page, reverse('core:dashboard:transaction-detail', args=[tx.pk]))
        self.assertContains(page, 'historique est clos')


class ClosureTests(AccountingTestBase):
    def test_closure_computes_theoretical_balance_and_difference(self):
        self.make_tx(amount=30000)
        response = self.client.post(
            reverse('core:dashboard:closure-create'),
            {
                'account': self.cash.pk,
                'date': self.local_date(),
                'counted_amount': '28000',
                'note': 'Manque 2000',
            },
        )
        self.assertRedirects(
            response, reverse('core:dashboard:closures'),
            fetch_redirect_response=False,
        )
        closure = CashClosure.objects.get(account=self.cash)
        self.assertEqual(closure.opening_balance, 0)
        self.assertEqual(closure.theoretical_balance, 30000)
        self.assertEqual(closure.counted_amount, 28000)
        self.assertEqual(closure.difference, -2000)
        self.assertEqual(closure.closed_by, self.assistant)
        self.assert_audited('CASH_CLOSURE', closure.pk)

    def test_duplicate_closure_is_rejected(self):
        self.make_tx(amount=5000)
        payload = {
            'account': self.cash.pk,
            'date': self.local_date(),
            'counted_amount': '5000',
            'note': '',
        }
        self.client.post(reverse('core:dashboard:closure-create'), payload)
        response = self.client.post(
            reverse('core:dashboard:closure-create'), payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            CashClosure.objects.filter(
                account=self.cash, date=self.today).count(),
            1,
        )

    def test_next_closure_starts_from_previous_counted_amount(self):
        yesterday = self.today - timedelta(days=1)
        self.client.post(
            reverse('core:dashboard:closure-create'),
            {
                'account': self.cash.pk,
                'date': yesterday.strftime('%Y-%m-%d'),
                'counted_amount': '10000',
                'note': '',
            },
        )
        self.make_tx(amount=5000)
        self.client.post(
            reverse('core:dashboard:closure-create'),
            {
                'account': self.cash.pk,
                'date': self.local_date(),
                'counted_amount': '15000',
                'note': '',
            },
        )
        today_closure = CashClosure.objects.get(
            account=self.cash, date=self.today)
        self.assertEqual(today_closure.opening_balance, 10000)
        self.assertEqual(today_closure.theoretical_balance, 15000)
        self.assertEqual(today_closure.difference, 0)


class StudentPaymentTests(AccountingTestBase):
    def test_partial_payment_creates_linked_cash_transaction(self):
        response = self.client.post(
            reverse('core:dashboard:payment-create'), self.payment_payload())
        payment = Payment.objects.get()
        self.assertRedirects(
            response,
            reverse('core:dashboard:payment-receipt', args=[payment.pk]),
            fetch_redirect_response=False,
        )
        self.assertEqual(payment.amount, 30000)
        self.assertEqual(payment.status, Payment.Status.COMPLETED)
        self.assertEqual(payment.recorded_by, self.assistant)
        self.assertIsNotNone(payment.transaction)
        self.assertEqual(payment.transaction.tx_type, CashTransaction.Type.IN)
        self.assertEqual(payment.transaction.amount, 30000)
        self.assertEqual(payment.transaction.account, self.cash)
        self.assertEqual(payment.transaction.status,
                         CashTransaction.Status.VALIDATED)

        enrollment = Enrollment.objects.get(pk=self.enrollment.pk)
        self.assertEqual(enrollment.total_paid, 30000)
        self.assertEqual(enrollment.balance_due, 60000)
        self.assertEqual(enrollment.payment_state, 'PARTIEL')
        self.assert_audited('PAYMENT_CREATE', payment.pk)

    def test_une_date_posterieure_a_ce_jour_est_refusee(self):
        """Rien n'entre en caisse avant le jour où le règlement est saisi."""
        dans_trois_jours = (timezone.localtime()
                            + timedelta(days=3)).strftime('%Y-%m-%dT%H:%M')
        avant = Payment.objects.count()
        caisses = CashTransaction.objects.count()
        page = self.client.post(
            reverse('core:dashboard:payment-create'),
            self.payment_payload(paid_at=dans_trois_jours),
        )
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "ne peut pas être daté après")
        self.assertEqual(Payment.objects.count(), avant)
        self.assertEqual(CashTransaction.objects.count(), caisses)

    def test_full_payment_settles_the_enrollment(self):
        self.client.post(
            reverse('core:dashboard:payment-create'),
            self.payment_payload(paid_at=self.local_datetime(minutes=-10)))
        self.client.post(
            reverse('core:dashboard:payment-create'),
            self.payment_payload(
                amount='60000', paid_at=self.local_datetime(minutes=-5)),
        )
        enrollment = Enrollment.objects.get(pk=self.enrollment.pk)
        self.assertEqual(enrollment.total_paid, 90000)
        self.assertEqual(enrollment.balance_due, 0)
        self.assertEqual(enrollment.payment_state, 'SOLDE')
        self.assertEqual(Payment.objects.count(), 2)

    def test_overpayment_is_rejected(self):
        response = self.client.post(
            reverse('core:dashboard:payment-create'),
            self.payment_payload(amount='100000'),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Payment.objects.count(), 0)
        self.assertEqual(CashTransaction.objects.count(), 0)

    def test_duplicate_submission_is_blocked(self):
        payload = self.payment_payload(amount='10000')
        self.client.post(reverse('core:dashboard:payment-create'), payload)
        response = self.client.post(
            reverse('core:dashboard:payment-create'), payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(CashTransaction.objects.count(), 1)

    def test_second_identical_amount_after_delay_is_allowed(self):
        first = self.payment_payload(
            amount='10000', paid_at=self.local_datetime(minutes=-10))
        second = self.payment_payload(amount='10000')
        self.client.post(reverse('core:dashboard:payment-create'), first)
        self.client.post(reverse('core:dashboard:payment-create'), second)
        self.assertEqual(Payment.objects.count(), 2)

    def test_receipt_access_rules(self):
        self.client.post(
            reverse('core:dashboard:payment-create'), self.payment_payload())
        payment = Payment.objects.get()
        url = reverse('core:dashboard:payment-receipt', args=[payment.pk])

        owner_client = self.client_for(self.etudiant)
        self.assertEqual(owner_client.get(url).status_code, 200)
        self.assertEqual(self.client.get(url).status_code, 200)

        other = self.make_user(RoleKey.ETUDIANT, 'autre-recu@test.local')
        other_client = self.client_for(other)
        self.assertEqual(other_client.get(url).status_code, 403)

        trainer_client = self.client_for(self.formateur)
        self.assertEqual(trainer_client.get(url).status_code, 403)
        self.assert_audited('PAYMENT_RECEIPT', payment.pk)


class AccountingPermissionTests(AccountingTestBase):
    def test_le_journal_reste_reserve_au_poste_finance(self):
        for user in (self.secretaire, self.etudiant):
            client = self.client_for(user)
            response = client.get(reverse('core:dashboard:journal'))
            self.assertEqual(response.status_code, 403)

    def test_l_assistant_administratif_lit_le_journal(self):
        client = self.client_for(self.assistant)
        self.assertEqual(
            client.get(reverse('core:dashboard:journal')).status_code, 200)

    def test_direction_can_read_journal(self):
        client = self.client_for(self.direction)
        self.assertEqual(
            client.get(reverse('core:dashboard:journal')).status_code, 200)

    def test_student_cannot_create_transaction(self):
        client = self.client_for(self.etudiant)
        response = client.get(reverse('core:dashboard:transaction-create'))
        self.assertEqual(response.status_code, 403)


class SingleSourceOfTruthTests(AccountingTestBase):
    """Les soldes et indicateurs ne doivent exister qu'en un seul calcul."""

    def test_account_balance_property_matches_the_shared_helper(self):
        self.make_tx(amount=10000, account=self.cash)
        self.make_tx(amount=4000, account=self.mobile)
        self.make_tx(
            tx_type=CashTransaction.Type.OUT, amount=3000, account=self.cash)
        self.make_tx(
            tx_type=CashTransaction.Type.TRANSFER, amount=2000,
            account=self.cash, destination=self.mobile)

        self.assertEqual(self.cash.balance, 5000)
        self.assertEqual(self.mobile.balance, 6000)
        for account in (self.cash, self.mobile):
            with self.subTest(account=account.name):
                self.assertEqual(account.balance, account_balance(account))
                self.assertEqual(
                    account.totals(),
                    account.movement_totals(),
                )

    def test_balance_at_ignores_movements_after_the_cutoff(self):
        self.make_tx(
            amount=10000, occurred_at=timezone.now() - timedelta(days=2))
        self.make_tx(amount=5000)
        cutoff = self.today - timedelta(days=1)

        self.assertEqual(self.cash.balance_at(cutoff), 10000)
        self.assertEqual(self.cash.balance_at(self.today), 15000)

    def test_comptabilite_dashboard_ignores_unlinked_payment_and_expense(self):
        self.make_tx(amount=10000)
        self.make_tx(tx_type=CashTransaction.Type.OUT, amount=3000)
        Payment.objects.create(
            enrollment=self.enrollment,
            amount=5000,
            method=Payment.Method.CASH,
            status=Payment.Status.COMPLETED,
            recorded_by=self.assistant,
        )
        Expense.objects.create(
            category='Fournitures',
            amount=7000,
            occurred_at=self.today,
            description='Dépense hors caisse',
            created_by=self.assistant,
        )

        response = self.client.get(
            reverse('core:dashboard:comptabilite-dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_revenue_month'], 10000)
        self.assertEqual(response.context['total_expenses_month'], 3000)
        self.assertEqual(response.context['net_month'], 7000)

    def test_direction_dashboard_revenue_comes_from_cash_transactions(self):
        self.make_tx(amount=10000)
        Payment.objects.create(
            enrollment=self.enrollment,
            amount=5000,
            method=Payment.Method.CASH,
            status=Payment.Status.COMPLETED,
            recorded_by=self.assistant,
        )

        client = self.client_for(self.direction)
        response = client.get(reverse('core:dashboard:direction-dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_revenue'], 10000)


class ComptableStudentListTests(BusinessTestBase):
    """La comptable consulte la liste des inscrits, sans écriture."""

    def test_comptable_sees_students_list(self):
        client = self.client_for(self.assistant)
        response = client.get(reverse('core:dashboard:student-list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.etudiant.get_full_name())
        self.assertContains(
            response, reverse('core:dashboard:student-list'))
        self.assertNotContains(
            response, reverse('core:dashboard:student-create'))

    def test_comptable_reads_student_detail_without_write_controls(self):
        client = self.client_for(self.assistant)
        response = client.get(reverse(
            'core:dashboard:student-detail', args=[self.etudiant.id]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(
            response,
            reverse('core:dashboard:student-edit', args=[self.etudiant.id]))
        self.assertNotContains(
            response, reverse('core:dashboard:enrollment-create'))
        self.assertNotContains(
            response,
            reverse('core:dashboard:student-document-upload',
                    args=[self.etudiant.id]))
        self.assertContains(response, 'relève du secrétariat')

    def test_secretary_gets_the_document_form(self):
        response = self.client_for(self.secretaire).get(reverse(
            'core:dashboard:student-detail', args=[self.etudiant.id]))
        self.assertContains(
            response,
            reverse('core:dashboard:student-document-upload',
                    args=[self.etudiant.id]))

    def test_comptable_cannot_write_student_records(self):
        client = self.client_for(self.assistant)
        self.assertEqual(
            client.get(reverse('core:dashboard:student-create')).status_code,
            403,
        )
        self.assertEqual(
            client.post(reverse(
                'core:dashboard:student-edit', args=[self.etudiant.id]),
                {}).status_code,
            403,
        )


class StudentWithoutEnrollmentNoticeTests(BusinessTestBase):
    """Un compte étudiant validé reste visible sur l'écran d'encaissement."""

    def make_silent_student(self, email):
        student = self.make_user(RoleKey.ETUDIANT, email)
        student.first_name = 'Zorro'
        student.last_name = 'Nsimbe'
        student.save(update_fields=['first_name', 'last_name'])
        return student

    def test_the_account_is_listed_on_the_payment_screen(self):
        self.make_silent_student('silent1@test.local')
        page = self.client_for(self.assistant).get(
            reverse('core:dashboard:payment-create'))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'Comptes étudiants sans inscription')
        self.assertContains(page, 'Zorro Nsimbe')
        self.assertContains(page, 'Inscrire')

    def test_a_direction_member_can_enroll_from_that_screen(self):
        student = self.make_silent_student('silent2@test.local')
        page = self.client_for(self.direction).get(
            reverse('core:dashboard:payment-create'))
        self.assertContains(page, 'Inscrire')
        self.assertContains(page, f'?student={student.id}')

    def test_the_comptable_can_also_enroll_from_that_screen(self):
        student = self.make_silent_student('silent3@test.local')
        page = self.client_for(self.assistant).get(
            reverse('core:dashboard:payment-create'))
        self.assertContains(page, f'?student={student.id}#inscription')
        self.assertContains(page, 'Inscrire un étudiant')

    def test_enrolled_student_is_not_listed(self):
        page = self.client_for(self.assistant).get(
            reverse('core:dashboard:payment-create'))
        self.assertNotContains(page, 'Comptes étudiants sans inscription')
        self.assertContains(page, self.etudiant.get_full_name())


class PaymentEnrollmentFlowTests(AccountingTestBase):
    """Étudiant → inscription : création au guichet puis validation.

    La validation est ouverte à la direction, la caisse, la supervision
    pédagogique et au super administrateur ; l'ADMIN et les rôles opérationnels
    (formateur, secrétariat, accueil, étudiant) restent exclus.
    """

    def counter_payload(self, student, **overrides):
        payload = {
            'inscription-student': student.pk,
            'inscription-session': self.session.pk,
            'inscription-start_date': self.local_date(),
            'inscription-tariff_amount': '',
            'inscription-discount_amount': '0',
            'inscription-payment_plan': '',
            'inscription-notes': '',
        }
        payload.update(overrides)
        return payload

    def make_student(self, email='nouveau.guichet@test.local'):
        student = self.make_user(RoleKey.ETUDIANT, email)
        student.first_name = 'Nouveau'
        student.last_name = 'Guichet'
        student.save(update_fields=['first_name', 'last_name'])
        return student

    def test_student_field_lists_every_active_student(self):
        other = self.make_student('autre.actif@test.local')
        page = self.client.get(reverse('core:dashboard:payment-create'))
        self.assertEqual(page.status_code, 200)
        queryset = page.context['form'].fields['student'].queryset
        self.assertIn(self.etudiant, queryset)
        self.assertIn(other, queryset)
        self.assertContains(page, 'Choisir un étudiant')
        self.assertContains(page, self.etudiant.get_full_name())
        self.assertContains(page, 'Nouveau Guichet')

    def test_enrollment_choices_are_filtered_by_student(self):
        other = self.make_student('autre.dossier@test.local')
        page = self.client.get(
            reverse('core:dashboard:payment-create'),
            {'student': other.pk},
        )
        self.assertEqual(page.status_code, 200)
        queryset = page.context['form'].fields['enrollment'].queryset
        self.assertEqual(list(queryset), [])

        page = self.client.get(
            reverse('core:dashboard:payment-create'),
            {'student': self.etudiant.pk},
        )
        self.assertEqual(
            [e.pk for e in page.context['form'].fields['enrollment'].queryset],
            [self.enrollment.pk],
        )

    def test_enrollment_choices_show_the_remaining_balance(self):
        page = self.client.get(reverse('core:dashboard:payment-create'))
        self.assertContains(page, 'reste 90000 FCFA')
        self.assertContains(page, f'data-balance="90000"')

    def test_enrollment_choice_label_names_the_student(self):
        page = self.client.get(reverse('core:dashboard:payment-create'))
        self.assertContains(
            page,
            f'{self.etudiant.display_label} — {self.course.title} '
            f'(reste 90000 FCFA)',
        )

    def test_empty_enrollment_choice_is_explained(self):
        other = self.make_student('sans.dossier@test.local')
        page = self.client.get(
            reverse('core:dashboard:payment-create'),
            {'student': other.pk},
        )
        self.assertContains(page, 'Choisir un dossier')
        self.assertContains(page, 'Aucune inscription pour cet étudiant')

    def test_pending_enrollment_explains_the_validation_wait(self):
        student = self.make_student('en.attente@test.local')
        self.client.post(
            reverse('core:dashboard:payment-create'),
            {'form_kind': 'enroll', **self.counter_payload(student)},
        )
        page = self.client.get(
            reverse('core:dashboard:payment-create'),
            {'student': student.pk},
        )
        self.assertContains(page, 'il attend une validation')

    def test_counter_enrollment_is_created_pending_without_payment(self):
        student = self.make_student()
        response = self.client.post(
            reverse('core:dashboard:payment-create'),
            {'form_kind': 'enroll', **self.counter_payload(student)},
        )
        enrollment = Enrollment.objects.get(student=student)
        self.assertRedirects(
            response,
            f"{reverse('core:dashboard:payment-create')}"
            f"?student={student.pk}",
            fetch_redirect_response=False,
        )
        self.assertEqual(enrollment.status, Enrollment.Status.PENDING)
        self.assertEqual(enrollment.net_amount, self.course.fee_amount)
        self.assertEqual(enrollment.registered_by, self.assistant)
        self.assertEqual(Payment.objects.count(), 0)
        self.assert_audited('ENROLLMENT_CREATE', enrollment.pk)

    def test_counter_enrollment_keeps_the_net_amount_from_tariff(self):
        student = self.make_student()
        self.client.post(
            reverse('core:dashboard:payment-create'),
            {'form_kind': 'enroll', **self.counter_payload(
                student,
                **{'inscription-tariff_amount': '120000',
                   'inscription-discount_amount': '20000'})},
        )
        enrollment = Enrollment.objects.get(student=student)
        self.assertEqual(enrollment.net_amount, 100000)

    def test_a_pending_enrollment_cannot_be_paid(self):
        student = self.make_student()
        self.client.post(
            reverse('core:dashboard:payment-create'),
            {'form_kind': 'enroll', **self.counter_payload(student)},
        )
        enrollment = Enrollment.objects.get(student=student)
        response = self.client.post(
            reverse('core:dashboard:payment-create'),
            self.payment_payload(
                student=student.pk, enrollment=enrollment.pk, amount='10000'),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Payment.objects.count(), 0)
        self.assertEqual(
            Enrollment.objects.get(pk=enrollment.pk).status,
            Enrollment.Status.PENDING,
        )

    def test_direction_validates_the_counter_enrollment(self):
        student = self.make_student()
        self.client.post(
            reverse('core:dashboard:payment-create'),
            {'form_kind': 'enroll', **self.counter_payload(student)},
        )
        enrollment = Enrollment.objects.get(student=student)

        refused = self.client_for(self.formateur).post(reverse(
            'core:dashboard:enrollment-validate', args=[enrollment.pk]))
        self.assertEqual(refused.status_code, 403)
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.status, Enrollment.Status.PENDING)

        response = self.client_for(self.direction).post(reverse(
            'core:dashboard:enrollment-validate', args=[enrollment.pk]))
        self.assertRedirects(
            response,
            reverse('core:dashboard:enrollment-detail', args=[enrollment.pk]),
            fetch_redirect_response=False,
        )
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.status, Enrollment.Status.ACTIVE)
        self.assert_audited('ENROLLMENT_VALIDATE', enrollment.pk)

    def test_super_admin_can_validate_while_admin_stays_read_only(self):
        student = self.make_student('relais.direction@test.local')
        self.client.post(
            reverse('core:dashboard:payment-create'),
            {'form_kind': 'enroll', **self.counter_payload(student)},
        )
        enrollment = Enrollment.objects.get(student=student)
        url = reverse('core:dashboard:enrollment-validate', args=[enrollment.pk])

        self.assertEqual(
            self.client_for(self.admin).post(url).status_code, 403)

        response = self.client_for(self.super_admin).post(url)
        self.assertRedirects(
            response,
            reverse('core:dashboard:enrollment-detail', args=[enrollment.pk]),
            fetch_redirect_response=False,
        )
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.status, Enrollment.Status.ACTIVE)

    def test_comptable_valide_depuis_sa_caisse(self):
        student = self.make_student()
        self.client.post(
            reverse('core:dashboard:payment-create'),
            {'form_kind': 'enroll', **self.counter_payload(student)},
        )
        enrollment = Enrollment.objects.get(student=student)
        url = reverse('core:dashboard:enrollment-validate', args=[enrollment.pk])

        page = self.client.get(reverse('core:dashboard:comptabilite-dashboard'))
        self.assertContains(page, 'Inscriptions en attente de validation')
        self.assertContains(page, url)

        response = self.client.post(url)
        self.assertRedirects(
            response,
            reverse('core:dashboard:enrollment-detail', args=[enrollment.pk]),
            fetch_redirect_response=False,
        )
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.status, Enrollment.Status.ACTIVE)
        self.assert_audited('ENROLLMENT_VALIDATE', enrollment.pk)

    def test_responsable_pedagogique_valide_depuis_son_tableau_de_bord(self):
        student = self.make_student()
        self.client.post(
            reverse('core:dashboard:payment-create'),
            {'form_kind': 'enroll', **self.counter_payload(student)},
        )
        enrollment = Enrollment.objects.get(student=student)
        url = reverse('core:dashboard:enrollment-validate', args=[enrollment.pk])
        peta = self.client_for(self.peda)

        page = peta.get(reverse('core:dashboard:resp-peda-dashboard'))
        self.assertContains(page, 'Inscriptions en attente de validation')
        self.assertContains(page, url)

        response = peta.post(url)
        self.assertRedirects(
            response,
            reverse('core:dashboard:enrollment-detail', args=[enrollment.pk]),
            fetch_redirect_response=False,
        )
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.status, Enrollment.Status.ACTIVE)
        self.assertContains(
            peta.get(reverse(
                'core:dashboard:enrollment-detail', args=[enrollment.pk])),
            'Solde restant',
        )

    def test_panel_de_validation_present_sur_les_tableaux_habilites(self):
        student = self.make_student()
        self.client.post(
            reverse('core:dashboard:payment-create'),
            {'form_kind': 'enroll', **self.counter_payload(student)},
        )
        for user, route in (
            (self.super_admin, 'core:dashboard:super-admin-dashboard'),
            (self.direction, 'core:dashboard:direction-dashboard'),
            (self.assistant, 'core:dashboard:comptabilite-dashboard'),
            (self.peda, 'core:dashboard:resp-peda-dashboard'),
        ):
            page = self.client_for(user).get(reverse(route))
            self.assertEqual(page.status_code, 200, route)
            self.assertContains(page, 'Inscriptions en attente de validation')

    def test_validated_enrollment_becomes_payable(self):
        student = self.make_student()
        self.client.post(
            reverse('core:dashboard:payment-create'),
            {'form_kind': 'enroll', **self.counter_payload(student)},
        )
        enrollment = Enrollment.objects.get(student=student)
        self.client_for(self.direction).post(reverse(
            'core:dashboard:enrollment-validate', args=[enrollment.pk]))

        response = self.client.post(
            reverse('core:dashboard:payment-create'),
            self.payment_payload(
                student=student.pk, enrollment=enrollment.pk, amount='10000'),
        )
        payment = Payment.objects.get()
        self.assertRedirects(
            response,
            reverse('core:dashboard:payment-receipt', args=[payment.pk]),
            fetch_redirect_response=False,
        )
        self.assertEqual(payment.enrollment_id, enrollment.pk)

    def test_enrollment_from_another_student_is_refused(self):
        other = self.make_user(RoleKey.ETUDIANT, 'autre.etudiant@test.local')
        response = self.client.post(
            reverse('core:dashboard:payment-create'),
            self.payment_payload(student=other.pk),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Payment.objects.count(), 0)
        errors = response.context['form'].errors.get('enrollment', [])
        self.assertTrue(
            any('appartient pas' in str(error) for error in errors), errors)

    def test_sold_out_enrollment_has_an_explicit_message(self):
        self.client.post(
            reverse('core:dashboard:payment-create'),
            self.payment_payload(amount='90000',
                                 paid_at=self.local_datetime(minutes=-10)),
        )
        response = self.client.post(
            reverse('core:dashboard:payment-create'),
            self.payment_payload(
                amount='1000', paid_at=self.local_datetime(minutes=-5)),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Payment.objects.count(), 1)
        self.assertContains(response, 'Ce dossier est soldé')

    def test_cancelled_enrollment_is_not_offered(self):
        self.enrollment.status = Enrollment.Status.CANCELLED
        self.enrollment.save(update_fields=['status'])
        page = self.client.get(reverse('core:dashboard:payment-create'))
        self.assertEqual(
            list(page.context['form'].fields['enrollment'].queryset), [])

    def test_pending_enrollment_warning_is_displayed(self):
        student = self.make_student()
        self.client.post(
            reverse('core:dashboard:payment-create'),
            {'form_kind': 'enroll', **self.counter_payload(student)},
        )
        page = self.client.get(
            reverse('core:dashboard:payment-create'),
            {'student': student.pk},
        )
        self.assertContains(page, 'Inscriptions en attente de validation')
        self.assertContains(page, 'en attente de validation')

    def test_direction_dashboard_lists_pending_enrollments(self):
        student = self.make_student('tableau.direction@test.local')
        self.client.post(
            reverse('core:dashboard:payment-create'),
            {'form_kind': 'enroll', **self.counter_payload(student)},
        )
        enrollment = Enrollment.objects.get(student=student)
        page = self.client_for(self.direction).get(
            reverse('core:dashboard:direction-dashboard'))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'Inscriptions en attente de validation')
        self.assertContains(page, enrollment.student.get_full_name())
        self.assertContains(page, reverse(
            'core:dashboard:enrollment-validate', args=[enrollment.pk]))


class GrilleDesMoisTests(AccountingTestBase):
    """L'encaissement par mois : douze cases à cocher, un paiement par mois réglé.

    Le dossier de test doit 90 000 FCFA sur une formation de 3 mois : la grille
    propose donc 30 000 FCFA par mois, sans que personne n'ait à le re-taper.
    """

    def setUp(self):
        super().setUp()
        self.url = reverse('core:dashboard:payment-months')
        self.annee = self.today.year

    def test_la_grille_propose_la_mensualite_pratiquee_par_le_dossier(self):
        page = self.client.get(self.url, {'enrollment': self.enrollment.pk})
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.context['mensualite'], 30000)
        self.assertEqual(len(page.context['lignes']), 12)
        self.assertContains(page, 'Mensualité de mars')

    def test_deux_mois_coches_font_deux_paiements_et_deux_ecritures(self):
        page = self.client.post(self.url, self.mois_payload(
            mois=['3', '4'], montant_3='30000', montant_4='25000'))
        self.assertEqual(page.status_code, 302)
        regles = Payment.objects.filter(
            motif=Payment.Motif.MONTHLY).order_by('period_month')
        self.assertEqual([p.period_month for p in regles], [3, 4])
        self.assertEqual([p.amount for p in regles], [30000, 25000])
        for paiement in regles:
            self.assertIsNotNone(paiement.transaction)
            self.assertEqual(paiement.paid_at.date(), self.today)
        self.assertEqual(self.enrollment.balance_due, 90000 - 55000)

    def test_un_mois_d_avance_se_date_du_jour_present(self):
        """Régler un mois à venir est une avance, pas un argent déjà entré.

        La grille datait la recette au premier jour du mois coché : cocher
        février de l'année suivante écrivait un encaissement dans le futur.
        """
        page = self.client.post(self.url, self.mois_payload(
            annee=str(self.today.year + 1), mois=['2'], montant_2='30000'))
        self.assertEqual(page.status_code, 302)
        paiement = Payment.objects.get(period_month=2,
                                       period_year=self.today.year + 1)
        self.assertEqual(paiement.paid_at.date(), self.today)
        self.assertEqual(paiement.transaction.occurred_at.date(), self.today)

    def test_un_mois_deja_regle_ne_se_recoche_pas(self):
        self.client.post(self.url, self.mois_payload(mois=['5'], montant_5='30000'))
        avant = Payment.objects.count()
        page = self.client.post(self.url, self.mois_payload(mois=['5'], montant_5='30000'))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'déjà réglé')
        self.assertEqual(Payment.objects.count(), avant)

    def test_le_mois_regle_une_annee_ne_blocque_pas_l_annee_suivante(self):
        self.client.post(self.url, self.mois_payload(
            annee=str(self.annee), mois=['6'], montant_6='30000'))
        page = self.client.post(self.url, self.mois_payload(
            annee=str(self.annee + 1), mois=['6'], montant_6='30000'))
        self.assertEqual(page.status_code, 302)
        self.assertEqual(Payment.objects.filter(period_month=6).count(), 2)

    def test_un_mois_coche_sans_montant_est_refuse(self):
        page = self.client.post(self.url, self.mois_payload(mois=['7']))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'indiquez le montant')
        self.assertEqual(Payment.objects.count(), 0)

    def test_la_grille_ne_peut_pas_encaisser_plus_que_le_reste_du(self):
        page = self.client.post(self.url, self.mois_payload(
            mois=['1', '2'], montant_1='50000', montant_2='50000'))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'dépasse le reste à payer')
        self.assertEqual(Payment.objects.count(), 0)

    def test_les_frais_dinscription_ne_se_payent_quune_fois(self):
        page = self.client.post(self.url, self.mois_payload(
            frais='1', montant_frais='10000'))
        self.assertEqual(page.status_code, 302)
        frais = Payment.objects.get(motif=Payment.Motif.ENROLLMENT)
        self.assertEqual(frais.amount, 10000)
        self.assertIsNone(frais.period_month)

        page = self.client.post(self.url, self.mois_payload(
            frais='1', montant_frais='10000'))
        self.assertContains(page, 'déjà encaissés')
        self.assertEqual(Payment.objects.filter(
            motif=Payment.Motif.ENROLLMENT).count(), 1)

    def test_un_mois_saisi_du_temps_plein_protege_le_mois_suivant(self):
        self.client.post(reverse('core:dashboard:payment-create'),
                         self.payment_payload(amount='30000',
                                              motif=Payment.Motif.MONTHLY,
                                              period_month='9',
                                              period_year=str(self.annee)))
        page = self.client.get(self.url, {'enrollment': self.enrollment.pk})
        self.assertEqual(len(Payment.objects.filter(period_month=9)), 1)
        self.assertContains(page, 'Mensualité de septembre')

        bloque = self.client.post(self.url, self.mois_payload(
            mois=['9'], montant_9='30000'))
        self.assertEqual(Payment.objects.filter(period_month=9).count(), 1)

    def test_la_base_refuse_deux_reglements_du_meme_mois(self):
        Payment.objects.create(
            enrollment=self.enrollment, amount=30000, method=Payment.Method.CASH,
            motif=Payment.Motif.MONTHLY, period_year=self.annee, period_month=11,
            status=Payment.Status.COMPLETED, recorded_by=self.assistant)
        with self.assertRaises(IntegrityError):
            Payment.objects.create(
                enrollment=self.enrollment, amount=30000,
                method=Payment.Method.CASH, motif=Payment.Motif.MONTHLY,
                period_year=self.annee, period_month=11,
                status=Payment.Status.COMPLETED, recorded_by=self.assistant)

    def test_la_reprise_structure_le_mois_deja_encaisse(self):
        """La reprise de l'historique lit le mois là où l'import l'avait écrit."""
        reglee = Payment.objects.create(
            enrollment=self.enrollment, amount=20000, method=Payment.Method.CASH,
            paid_at=timezone.make_aware(dt.datetime(2026, 8, 1, 12)),
            note='Mensualité — août 2026 — classeur')
        entree = Payment.objects.create(
            enrollment=self.enrollment, amount=10000, method=Payment.Method.CASH,
            paid_at=timezone.make_aware(dt.datetime(2026, 3, 5, 12)),
            note="Frais d'inscription — classeur")
        module = importlib.import_module(
            'core.migrations.0011_reprise_mois_paiements')

        module.reprise(apps, None)

        reglee.refresh_from_db()
        self.assertEqual(reglee.motif, Payment.Motif.MONTHLY)
        self.assertEqual((reglee.period_year, reglee.period_month), (2026, 8))
        entree.refresh_from_db()
        self.assertEqual(entree.motif, Payment.Motif.ENROLLMENT)
        self.assertIsNone(entree.period_month)
