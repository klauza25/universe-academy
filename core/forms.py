from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.validators import FileExtensionValidator
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from . import caisse
from .models import (
    User, ScholarshipApplication, ScholarshipDocument,
    Destination, Course, CourseSession, Enrollment,
    Payment, Attendance, AccessEvent, AccountStatus, RoleKey,
    REQUESTABLE_ROLE_CHOICES, MOIS, ROLES_DISSOUS,
    Contact, Visit, VisitReason, Prospect, ProspectFollowUp,
    Module, Lesson, SessionRecord, Resource, ResourceFeedback, StudentDocument,
    CashAccount, CashTransaction, CashClosure, TransactionCategory,
    StudentSessionNote,
)

# Styles partagés pour les formulaires publics (cohérents avec la page de connexion)
INPUT_CLASS = (
    'w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm '
    'text-slate-900 placeholder-slate-400 shadow-sm transition '
    'focus:border-slate-400 focus:outline-none focus:ring-2 focus:ring-slate-900/10'
)
FILE_CLASS = (
    'block w-full rounded-lg border border-slate-300 bg-white text-sm text-slate-600 '
    'file:mr-3 file:cursor-pointer file:border-0 file:bg-slate-100 file:px-3 file:py-2.5 '  # i18n-exempt: classes utilitaires Tailwind, jamais affichées
    'file:text-sm file:font-medium file:text-slate-700 hover:file:bg-slate-200 '  # i18n-exempt: classes utilitaires Tailwind, jamais affichées
    'focus:outline-none focus:ring-2 focus:ring-slate-900/10'
)


def enrollable_sessions():
    """Groupes ouverts à l'inscription (planifiés ou en cours)."""
    return CourseSession.objects.filter(
        status__in=[CourseSession.Status.PLANNED, CourseSession.Status.ACTIVE],
    ).select_related('course').order_by('course__title', 'starts_at')


class LoginForm(forms.Form):
    identifier = forms.CharField(
        label=_("Identifiant"),
        widget=forms.TextInput(attrs={
            'class': INPUT_CLASS,
            'placeholder': _('Email ou code interne')
        })
    )
    password = forms.CharField(
        label=_("Mot de passe"),
        widget=forms.PasswordInput(attrs={
            'class': INPUT_CLASS,
            'placeholder': '••••••••'
        })
    )


class RegisterForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput(attrs={
        'class': INPUT_CLASS,
        'placeholder': _('Minimum 8 caractères')
    }))
    password_confirm = forms.CharField(
        label=_("Confirmer le mot de passe"),
        widget=forms.PasswordInput(attrs={
            'class': INPUT_CLASS,
            'placeholder': '••••••••'
        })
    )
    requested_role = forms.ChoiceField(
        label=_("Rôle demandé"),
        choices=[('', _('-- Choisir un rôle --'))] + REQUESTABLE_ROLE_CHOICES,
        widget=forms.Select(attrs={'class': INPUT_CLASS}),
        help_text=_("Votre demande sera examinée : aucun accès n'est accordé avant validation."),
    )

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email']
        widgets = {
            'first_name': forms.TextInput(attrs={
                'class': INPUT_CLASS, 'placeholder': _('Prénom')
            }),
            'last_name': forms.TextInput(attrs={
                'class': INPUT_CLASS, 'placeholder': _('Nom')
            }),
            'email': forms.EmailInput(attrs={
                'class': INPUT_CLASS, 'placeholder': _('email@exemple.com')
            }),
        }

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('password') != cleaned.get('password_confirm'):
            raise forms.ValidationError(_("Les mots de passe ne correspondent pas."))
        return cleaned


class UserCreateForm(forms.ModelForm):
    role = forms.ChoiceField(
        choices=[('', _('-- Choisir un rôle --'))] + [
            (key, label) for key, label in RoleKey.choices
            if key not in ('SUPER_ADMIN', 'ADMIN') and key not in ROLES_DISSOUS
        ],
        label=_("Rôle"),
        help_text=_("Les rôles SUPER_ADMIN et ADMIN s'attribuent ensuite depuis la fiche utilisateur, par un super administrateur."),
    )
    session = forms.ModelChoiceField(
        label=_("Formation / groupe"),
        queryset=enrollable_sessions(),
        required=False,
        empty_label=_("-- Choisir un groupe --"),
        help_text=_("Obligatoire pour un étudiant : le compte est inscrit dès sa création."),
        widget=forms.Select(attrs={'class': 'w-full p-2 border rounded'}),
    )
    password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={'class': 'w-full p-2 border rounded'}),
        help_text=_("Laisser vide pour envoyer une invitation par email")
    )

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'phone']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'w-full p-2 border rounded'}),
            'last_name': forms.TextInput(attrs={'class': 'w-full p-2 border rounded'}),
            'email': forms.EmailInput(attrs={'class': 'w-full p-2 border rounded'}),
            'phone': forms.TextInput(attrs={'class': 'w-full p-2 border rounded'}),
        }

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('role') == RoleKey.ETUDIANT and not cleaned.get('session'):
            self.add_error(
                'session',
                _("Un compte étudiant doit être inscrit à un groupe."),
            )
        return cleaned


class AccessApprovalForm(forms.Form):
    """Groupe choisi lors de la validation d'une demande d'accès."""

    session = forms.ModelChoiceField(
        label=_("Formation / groupe"),
        queryset=enrollable_sessions(),
        required=False,
        empty_label=_("-- Choisir un groupe --"),
        widget=forms.Select(attrs={'class': 'w-full p-2 border rounded'}),
    )


class UserEditForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'phone',
                   'account_status']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'w-full p-2 border rounded'}),
            'last_name': forms.TextInput(attrs={'class': 'w-full p-2 border rounded'}),
            'email': forms.EmailInput(attrs={'class': 'w-full p-2 border rounded'}),
            'phone': forms.TextInput(attrs={'class': 'w-full p-2 border rounded'}),
            'account_status': forms.Select(attrs={'class': 'w-full p-2 border rounded'}),
        }


class ScholarshipApplicationForm(forms.ModelForm):
    class Meta:
        model = ScholarshipApplication
        fields = [
            'last_name', 'first_name', 'email', 'phone',
            'destination', 'program', 'study_domain'
        ]
        widgets = {
            'last_name': forms.TextInput(attrs={
                'class': INPUT_CLASS,
                'placeholder': _('Nom')
            }),
            'first_name': forms.TextInput(attrs={
                'class': INPUT_CLASS,
                'placeholder': _('Prénom')
            }),
            'email': forms.EmailInput(attrs={
                'class': INPUT_CLASS,
                'placeholder': _('email@exemple.com')
            }),
            'phone': forms.TextInput(attrs={
                'class': INPUT_CLASS,
                'placeholder': '+242 06 XXX XX XX'
            }),
            'destination': forms.Select(attrs={'class': INPUT_CLASS}),
            'program': forms.TextInput(attrs={
                'class': INPUT_CLASS,
                'placeholder': _('Ex: Licence, Master')
            }),
            'study_domain': forms.TextInput(attrs={
                'class': INPUT_CLASS,
                'placeholder': _('Ex: Informatique, Médecine')
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['destination'].queryset = Destination.objects.filter(active=True)


class ScholarshipDocumentForm(forms.Form):
    identity_doc = forms.FileField(
        label=_("Pièce d'identité"),
        validators=[FileExtensionValidator(['pdf', 'jpg', 'jpeg', 'png'])],
        widget=forms.ClearableFileInput(attrs={
            'class': FILE_CLASS, 'accept': '.pdf,.jpg,.jpeg,.png'
        })
    )
    diplomas = forms.FileField(
        label=_("Diplômes"),
        required=False,
        validators=[FileExtensionValidator(['pdf', 'jpg', 'jpeg', 'png'])],
        widget=forms.ClearableFileInput(attrs={
            'class': FILE_CLASS, 'accept': '.pdf,.jpg,.jpeg,.png'
        })
    )
    transcripts = forms.FileField(
        label=_("Relevés de notes"),
        required=False,
        validators=[FileExtensionValidator(['pdf', 'jpg', 'jpeg', 'png'])],
        widget=forms.ClearableFileInput(attrs={
            'class': FILE_CLASS, 'accept': '.pdf,.jpg,.jpeg,.png'
        })
    )
    photo = forms.ImageField(
        label=_("Photo d'identité"),
        validators=[FileExtensionValidator(['jpg', 'jpeg', 'png'])],
        widget=forms.ClearableFileInput(attrs={
            'class': FILE_CLASS, 'accept': '.jpg,.jpeg,.png'
        })
    )
    motivation_letter = forms.FileField(
        label=_("Lettre de motivation"),
        validators=[FileExtensionValidator(['pdf', 'doc', 'docx'])],
        widget=forms.ClearableFileInput(attrs={
            'class': FILE_CLASS, 'accept': '.pdf,.doc,.docx'
        })
    )


class AccessEventForm(forms.ModelForm):
    class Meta:
        model = AccessEvent
        fields = ['person', 'visitor_label', 'event_type', 'reason']
        widgets = {
            'person': forms.Select(attrs={'class': 'w-full p-2 border rounded'}),
            'visitor_label': forms.TextInput(attrs={
                'class': 'w-full p-2 border rounded',
                'placeholder': _('Nom du visiteur (si pas inscrit)')
            }),
            'event_type': forms.Select(attrs={'class': 'w-full p-2 border rounded'}),
            'reason': forms.TextInput(attrs={
                'class': 'w-full p-2 border rounded',
                'placeholder': _('Motif (optionnel)')
            }),
        }


# ===========================================================================
# Profil utilisateur
# ===========================================================================


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'display_name', 'phone', 'address']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'last_name': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'display_name': forms.TextInput(attrs={
                'class': INPUT_CLASS,
                'placeholder': _("Nom affiché dans l'interface"),
            }),
            'phone': forms.TextInput(attrs={
                'class': INPUT_CLASS, 'placeholder': '+242 06 XXX XX XX'
            }),
            'address': forms.Textarea(attrs={'class': INPUT_CLASS, 'rows': 3}),
        }


class AvatarForm(forms.Form):
    avatar = forms.ImageField(
        label=_("Photo de profil"),
        widget=forms.ClearableFileInput(attrs={'class': FILE_CLASS, 'accept': 'image/*'}),
    )

    def clean_avatar(self):
        image = self.cleaned_data['avatar']
        if image.size > 2 * 1024 * 1024:
            raise forms.ValidationError(_("L'image ne doit pas dépasser 2 Mo."))
        return image


class AccessRequestCompletionForm(forms.ModelForm):
    """Complète le profil et le rôle demandé d'un compte en attente (Clerk)."""

    requested_role = forms.ChoiceField(
        label=_("Rôle demandé"),
        choices=[('', _('-- Choisir un rôle --'))] + REQUESTABLE_ROLE_CHOICES,
        widget=forms.Select(attrs={'class': INPUT_CLASS}),
        help_text=_("Votre demande sera examinée : aucun accès n'est accordé avant validation."),
    )

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'phone']
        widgets = {
            'first_name': forms.TextInput(attrs={
                'class': INPUT_CLASS, 'placeholder': _('Prénom')
            }),
            'last_name': forms.TextInput(attrs={
                'class': INPUT_CLASS, 'placeholder': _('Nom')
            }),
            'phone': forms.TextInput(attrs={
                'class': INPUT_CLASS, 'placeholder': '+242 06 XXX XX XX'
            }),
        }


class EmailChangeForm(forms.Form):
    new_email = forms.EmailField(
        label=_("Nouvelle adresse e-mail"),
        widget=forms.EmailInput(attrs={'class': INPUT_CLASS}),
    )
    password = forms.CharField(
        label=_("Mot de passe actuel"),
        widget=forms.PasswordInput(attrs={'class': INPUT_CLASS}),
        required=False,
    )

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        # Un compte sorti d'un classeur ou lié à Clerk n'a pas de mot de passe
        # local : le réclamer boucherait l'écran pour ces personnes là. La
        # confirmation par lien envoyé à la nouvelle adresse reste la preuve.
        self.fields['password'].required = bool(
            user and user.has_usable_password())

    def clean_new_email(self):
        email = self.cleaned_data['new_email'].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(_("Cette adresse est déjà utilisée."))
        return email

    def clean_password(self):
        password = self.cleaned_data['password']
        if self.user and self.user.has_usable_password():
            if not password or not self.user.check_password(password):
                raise forms.ValidationError(_("Mot de passe incorrect."))
        return password


class PasswordChangeForm(forms.Form):
    """Changement du mot de passe par la personne elle-même.

    Le mot de passe actuel n'est exigé que lorsque le compte en possède un :
    une fiche ouverte depuis les classeurs, ou un compte arrivé par Clerk,
    arrive sans mot de passe local. Demander ce qui n'existe pas rendrait
    un écran inutilisable pour ces comptes, qui ont justement besoin d'en
    poser un.
    """

    current_password = forms.CharField(
        label=_("Mot de passe actuel"),
        widget=forms.PasswordInput(attrs={
            'class': INPUT_CLASS, 'autocomplete': 'current-password'}),
        required=False,
    )
    new_password = forms.CharField(
        label=_("Nouveau mot de passe"),
        help_text=_("Minimum 8 caractères, ni trop simple, ni numérique seul."),
        widget=forms.PasswordInput(attrs={
            'class': INPUT_CLASS, 'autocomplete': 'new-password'},
            render_value=True),
    )
    new_password_confirm = forms.CharField(
        label=_("Confirmer le nouveau mot de passe"),
        widget=forms.PasswordInput(attrs={
            'class': INPUT_CLASS, 'autocomplete': 'new-password'}),
    )

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        self.fields['current_password'].required = bool(
            user and user.has_usable_password())

    def clean_current_password(self):
        password = self.cleaned_data['current_password']
        if self.user and self.user.has_usable_password():
            if not password or not self.user.check_password(password):
                raise forms.ValidationError(_("Mot de passe actuel incorrect."))
        return password

    def clean_new_password(self):
        password = self.cleaned_data['new_password']
        validate_password(password, self.user)
        return password

    def clean(self):
        cleaned = super().clean()
        nouveau = cleaned.get('new_password')
        if nouveau and nouveau != cleaned.get('new_password_confirm'):
            self.add_error(
                'new_password_confirm',
                _("Les deux mots de passe ne correspondent pas."),
            )
        return cleaned


# ===========================================================================
# Accueil : visites et prospects
# ===========================================================================


class VisitForm(forms.ModelForm):
    first_name = forms.CharField(label=_("Prénom"), max_length=100,
                                 widget=forms.TextInput(attrs={'class': INPUT_CLASS}))
    last_name = forms.CharField(label=_("Nom"), max_length=100,
                                widget=forms.TextInput(attrs={'class': INPUT_CLASS}))
    phone = forms.CharField(label=_("Téléphone"), max_length=30,
                            widget=forms.TextInput(attrs={
                                'class': INPUT_CLASS, 'placeholder': '+242 06 XXX XX XX'}))
    secondary_phone = forms.CharField(label=_("Téléphone secondaire"), required=False,
                                      max_length=30,
                                      widget=forms.TextInput(attrs={'class': INPUT_CLASS}))
    email = forms.EmailField(label=_("Email"), required=False,
                             widget=forms.EmailInput(attrs={'class': INPUT_CLASS}))

    class Meta:
        model = Visit
        fields = [
            'visitor_type', 'reason', 'request_description', 'host_service',
            'host_person', 'arrival_at', 'departure_at', 'status', 'notes',
        ]
        widgets = {
            'visitor_type': forms.Select(attrs={'class': INPUT_CLASS}),
            'reason': forms.Select(attrs={'class': INPUT_CLASS}),
            'request_description': forms.Textarea(attrs={'class': INPUT_CLASS, 'rows': 3}),
            'host_service': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'host_person': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'arrival_at': forms.DateTimeInput(
                attrs={'class': INPUT_CLASS, 'type': 'datetime-local'},
                format='%Y-%m-%dT%H:%M',
            ),
            'departure_at': forms.DateTimeInput(
                attrs={'class': INPUT_CLASS, 'type': 'datetime-local'},
                format='%Y-%m-%dT%H:%M',
            ),
            'status': forms.Select(attrs={'class': INPUT_CLASS}),
            'notes': forms.Textarea(attrs={'class': INPUT_CLASS, 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['reason'].queryset = VisitReason.objects.filter(active=True)
        self.fields['arrival_at'].input_formats = ['%Y-%m-%dT%H:%M']
        self.fields['departure_at'].input_formats = ['%Y-%m-%dT%H:%M']
        if not self.instance._state.adding:
            contact = self.instance.contact
            self.fields['first_name'].initial = contact.first_name
            self.fields['last_name'].initial = contact.last_name
            self.fields['phone'].initial = contact.phone
            self.fields['secondary_phone'].initial = contact.secondary_phone
            self.fields['email'].initial = contact.email

    def clean(self):
        cleaned = super().clean()
        arrival = cleaned.get('arrival_at')
        departure = cleaned.get('departure_at')
        if arrival and departure and departure < arrival:
            self.add_error('departure_at',
                           _("Le départ ne peut pas précéder l'arrivée."))
        if not cleaned.get('status') or cleaned.get('status') == Visit.Status.WAITING:
            pass
        return cleaned

    def _resolve_contact(self):
        data = self.cleaned_data
        phone = (data.get('phone') or '').strip()
        email = (data.get('email') or '').strip().lower()
        if not self.instance._state.adding:
            return self.instance.contact
        query = Q(phone=phone)
        if email:
            query |= Q(email__iexact=email)
        return Contact.objects.filter(query).order_by('created_at').first()

    def save(self, commit=True):
        visit = super().save(commit=False)
        contact = self._resolve_contact()
        if contact is None:
            contact = Contact()
        contact.first_name = self.cleaned_data['first_name'].strip()
        contact.last_name = self.cleaned_data['last_name'].strip()
        contact.phone = self.cleaned_data['phone'].strip()
        contact.secondary_phone = self.cleaned_data.get('secondary_phone', '').strip()
        contact.email = self.cleaned_data.get('email', '').strip()
        contact.save()
        visit.contact = contact
        if commit:
            visit.save()
        return visit


class VisitReasonForm(forms.ModelForm):
    class Meta:
        model = VisitReason
        fields = ['label', 'order', 'active']
        widgets = {
            'label': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'order': forms.NumberInput(attrs={'class': INPUT_CLASS, 'min': 0}),
        }


class ProspectForm(forms.ModelForm):
    first_name = forms.CharField(label=_("Prénom"), max_length=100,
                                 widget=forms.TextInput(attrs={'class': INPUT_CLASS}))
    last_name = forms.CharField(label=_("Nom"), max_length=100,
                                widget=forms.TextInput(attrs={'class': INPUT_CLASS}))
    phone = forms.CharField(label=_("Téléphone principal"), max_length=30,
                            widget=forms.TextInput(attrs={'class': INPUT_CLASS}))
    secondary_phone = forms.CharField(label=_("Téléphone secondaire"), required=False,
                                      max_length=30,
                                      widget=forms.TextInput(attrs={'class': INPUT_CLASS}))
    email = forms.EmailField(label=_("Email"), required=False,
                             widget=forms.EmailInput(attrs={'class': INPUT_CLASS}))

    class Meta:
        model = Prospect
        fields = [
            'course', 'domain', 'level', 'language_program', 'desired_start',
            'preferred_contact', 'source', 'first_contact_at', 'interest_reason',
            'comments', 'status', 'next_follow_up',
        ]
        widgets = {
            'course': forms.Select(attrs={'class': INPUT_CLASS}),
            'domain': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'level': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'language_program': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'desired_start': forms.TextInput(attrs={
                'class': INPUT_CLASS, 'placeholder': _('Ex: janvier 2027')}),
            'preferred_contact': forms.Select(attrs={'class': INPUT_CLASS}),
            'source': forms.Select(attrs={'class': INPUT_CLASS}),
            'first_contact_at': forms.DateInput(
                attrs={'class': INPUT_CLASS, 'type': 'date'}, format='%Y-%m-%d'),
            'interest_reason': forms.Textarea(attrs={'class': INPUT_CLASS, 'rows': 2}),
            'comments': forms.Textarea(attrs={'class': INPUT_CLASS, 'rows': 2}),
            'status': forms.Select(attrs={'class': INPUT_CLASS}),
            'next_follow_up': forms.DateInput(
                attrs={'class': INPUT_CLASS, 'type': 'date'}, format='%Y-%m-%d'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['course'].queryset = Course.objects.filter(active=True)
        self.fields['first_contact_at'].input_formats = ['%Y-%m-%d']
        self.fields['next_follow_up'].input_formats = ['%Y-%m-%d']
        if not self.instance._state.adding:
            contact = self.instance.contact
            self.fields['first_name'].initial = contact.first_name
            self.fields['last_name'].initial = contact.last_name
            self.fields['phone'].initial = contact.phone
            self.fields['secondary_phone'].initial = contact.secondary_phone
            self.fields['email'].initial = contact.email

    def _resolve_contact(self):
        if not self.instance._state.adding:
            return self.instance.contact
        phone = (self.cleaned_data.get('phone') or '').strip()
        email = (self.cleaned_data.get('email') or '').strip().lower()
        query = Q(phone=phone)
        if email:
            query |= Q(email__iexact=email)
        return Contact.objects.filter(query).order_by('created_at').first()

    def save(self, commit=True):
        prospect = super().save(commit=False)
        contact = self._resolve_contact()
        if contact is None:
            contact = Contact()
        contact.first_name = self.cleaned_data['first_name'].strip()
        contact.last_name = self.cleaned_data['last_name'].strip()
        contact.phone = self.cleaned_data['phone'].strip()
        contact.secondary_phone = self.cleaned_data.get('secondary_phone', '').strip()
        contact.email = self.cleaned_data.get('email', '').strip()
        contact.save()
        prospect.contact = contact
        if commit:
            prospect.save()
        return prospect


class ProspectFollowUpForm(forms.ModelForm):
    class Meta:
        model = ProspectFollowUp
        fields = [
            'occurred_at', 'contact_type', 'phone_used', 'summary', 'info_given',
            'course', 'outcome', 'next_action', 'next_follow_up',
        ]
        widgets = {
            'occurred_at': forms.DateTimeInput(
                attrs={'class': INPUT_CLASS, 'type': 'datetime-local'},
                format='%Y-%m-%dT%H:%M'),
            'contact_type': forms.Select(attrs={'class': INPUT_CLASS}),
            'phone_used': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'summary': forms.Textarea(attrs={'class': INPUT_CLASS, 'rows': 3}),
            'info_given': forms.Textarea(attrs={'class': INPUT_CLASS, 'rows': 2}),
            'course': forms.Select(attrs={'class': INPUT_CLASS}),
            'outcome': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'next_action': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'next_follow_up': forms.DateInput(
                attrs={'class': INPUT_CLASS, 'type': 'date'}, format='%Y-%m-%d'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['course'].queryset = Course.objects.filter(active=True)
        self.fields['occurred_at'].input_formats = ['%Y-%m-%dT%H:%M']
        self.fields['next_follow_up'].input_formats = ['%Y-%m-%d']


# ===========================================================================
# Secrétariat : étudiants, inscriptions, documents
# ===========================================================================


class StudentForm(forms.ModelForm):
    password = forms.CharField(
        label=_("Mot de passe initial"), required=False,
        help_text=_("Laisser vide pour créer un compte sans mot de passe (invitation)."),
        widget=forms.PasswordInput(attrs={'class': INPUT_CLASS,
                                          'placeholder': _('Minimum 8 caractères')}),
    )

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'phone', 'address', 'birth_date']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'last_name': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'email': forms.EmailInput(attrs={'class': INPUT_CLASS}),
            'phone': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'address': forms.Textarea(attrs={'class': INPUT_CLASS, 'rows': 2}),
            'birth_date': forms.DateInput(
                attrs={'class': INPUT_CLASS, 'type': 'date'}, format='%Y-%m-%d'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['birth_date'].input_formats = ['%Y-%m-%d']

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        qs = User.objects.filter(email__iexact=email)
        if not self.instance._state.adding:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(_("Un compte utilise déjà cette adresse."))
        return email

    def clean_password(self):
        password = self.cleaned_data.get('password')
        if password:
            from django.contrib.auth.password_validation import validate_password
            validate_password(password, self.instance)
        return password


class StudentEditForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'phone', 'address', 'birth_date']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'last_name': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'phone': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'address': forms.Textarea(attrs={'class': INPUT_CLASS, 'rows': 2}),
            'birth_date': forms.DateInput(
                attrs={'class': INPUT_CLASS, 'type': 'date'}, format='%Y-%m-%d'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['birth_date'].input_formats = ['%Y-%m-%d']


class EnrollmentForm(forms.ModelForm):
    class Meta:
        model = Enrollment
        fields = [
            'student', 'session', 'status', 'start_date', 'tariff_amount',
            'discount_amount', 'payment_plan', 'notes',
        ]
        widgets = {
            'student': forms.Select(attrs={'class': INPUT_CLASS}),
            'session': forms.Select(attrs={'class': INPUT_CLASS}),
            'status': forms.Select(attrs={'class': INPUT_CLASS}),
            'start_date': forms.DateInput(
                attrs={'class': INPUT_CLASS, 'type': 'date'}, format='%Y-%m-%d'),
            'tariff_amount': forms.NumberInput(attrs={'class': INPUT_CLASS, 'min': 0}),
            'discount_amount': forms.NumberInput(attrs={'class': INPUT_CLASS, 'min': 0}),
            'payment_plan': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'notes': forms.Textarea(attrs={'class': INPUT_CLASS, 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['student'].queryset = User.objects.filter(
            roles__key=RoleKey.ETUDIANT
        ).distinct()
        self.fields['start_date'].input_formats = ['%Y-%m-%d']
        self.fields['session'].queryset = CourseSession.objects.select_related(
            'course'
        )

    def clean(self):
        cleaned = super().clean()
        tariff = cleaned.get('tariff_amount') or 0
        discount = cleaned.get('discount_amount') or 0
        if discount > tariff:
            self.add_error('discount_amount', _("La remise ne peut pas dépasser le tarif."))
        cleaned['net_amount'] = max(tariff - discount, 0)
        return cleaned

    def save(self, commit=True):
        enrollment = super().save(commit=False)
        if not enrollment.tariff_amount:
            enrollment.tariff_amount = enrollment.session.course.fee_amount
        enrollment.net_amount = max(
            (enrollment.tariff_amount or 0) - (enrollment.discount_amount or 0), 0
        )
        if commit:
            enrollment.save()
        return enrollment


class NewEnrollmentForm(forms.Form):
    """Inscription créée en même temps que le compte étudiant."""

    session = forms.ModelChoiceField(
        label=_("Formation / groupe"),
        queryset=CourseSession.objects.none(),
        widget=forms.Select(attrs={'class': INPUT_CLASS}),
    )
    status = forms.ChoiceField(
        label=_("Statut de l'inscription"),
        choices=Enrollment.Status.choices,
        initial=Enrollment.Status.ACTIVE,
        widget=forms.Select(attrs={'class': INPUT_CLASS}),
    )
    start_date = forms.DateField(
        label=_("Date de début"),
        required=False,
        widget=forms.DateInput(attrs={'class': INPUT_CLASS, 'type': 'date'},
                               format='%Y-%m-%d'),
    )
    tariff_amount = forms.IntegerField(
        label=_("Frais de formation prévus (FCFA)"),
        required=False, min_value=0,
        widget=forms.NumberInput(attrs={'class': INPUT_CLASS, 'min': 0}),
    )
    discount_amount = forms.IntegerField(
        label=_("Remise (FCFA)"),
        required=False, min_value=0, initial=0,
        widget=forms.NumberInput(attrs={'class': INPUT_CLASS, 'min': 0}),
    )
    payment_plan = forms.CharField(
        label=_("Modalités de paiement"),
        required=False,
        widget=forms.TextInput(attrs={
            'class': INPUT_CLASS,
            'placeholder': _("Ex: 2 versements — 50 % à l'inscription"),
        }),
    )
    notes = forms.CharField(
        label=_("Observations"),
        required=False,
        widget=forms.Textarea(attrs={'class': INPUT_CLASS, 'rows': 2}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['session'].queryset = CourseSession.objects.select_related(
            'course'
        ).order_by('-starts_at')
        self.fields['start_date'].input_formats = ['%Y-%m-%d']

    def clean(self):
        cleaned = super().clean()
        session = cleaned.get('session')
        tariff = cleaned.get('tariff_amount')
        discount = cleaned.get('discount_amount') or 0
        if tariff in (None, '') and session:
            tariff = session.course.fee_amount
        cleaned['tariff_amount'] = tariff or 0
        if discount > cleaned['tariff_amount']:
            self.add_error('discount_amount',
                           _("La remise ne peut pas dépasser le tarif."))
        return cleaned

    @property
    def net_amount(self):
        if not self.is_valid():
            return 0
        return max(
            self.cleaned_data['tariff_amount'] -
            (self.cleaned_data.get('discount_amount') or 0), 0
        )


class StudentDocumentForm(forms.ModelForm):
    class Meta:
        model = StudentDocument
        fields = ['doc_type', 'file']
        widgets = {
            'doc_type': forms.Select(attrs={'class': INPUT_CLASS}),
            'file': forms.ClearableFileInput(attrs={'class': FILE_CLASS}),
        }


# ===========================================================================
# Pédagogie : modules, séances, ressources
# ===========================================================================


class ModuleForm(forms.ModelForm):
    class Meta:
        model = Module
        fields = ['course', 'title', 'description', 'order', 'planned_hours']
        widgets = {
            'course': forms.Select(attrs={'class': INPUT_CLASS}),
            'title': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'description': forms.Textarea(attrs={'class': INPUT_CLASS, 'rows': 2}),
            'order': forms.NumberInput(attrs={'class': INPUT_CLASS, 'min': 0}),
            'planned_hours': forms.NumberInput(attrs={'class': INPUT_CLASS, 'min': 0}),
        }


class LessonForm(forms.ModelForm):
    class Meta:
        model = Lesson
        fields = ['module', 'title', 'objectives', 'order', 'planned_hours']
        widgets = {
            'module': forms.Select(attrs={'class': INPUT_CLASS}),
            'title': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'objectives': forms.Textarea(attrs={'class': INPUT_CLASS, 'rows': 2}),
            'order': forms.NumberInput(attrs={'class': INPUT_CLASS, 'min': 0}),
            'planned_hours': forms.NumberInput(attrs={'class': INPUT_CLASS, 'min': 0}),
        }


class CourseSessionForm(forms.ModelForm):
    """Groupe de formation : période, capacité et formateurs affectés."""

    class Meta:
        model = CourseSession
        fields = [
            'course', 'starts_at', 'ends_at', 'schedule', 'capacity',
            'status', 'formateurs',
        ]
        labels = {
            'course': _("Formation"),
            'starts_at': _("Date de début"),
            'ends_at': _("Date de fin"),
            'schedule': _("Horaires"),
            'capacity': _("Capacité"),
            'status': _("Statut"),
            'formateurs': _("Formateurs"),
        }
        widgets = {
            'course': forms.Select(attrs={'class': INPUT_CLASS}),
            'starts_at': forms.DateInput(
                attrs={'class': INPUT_CLASS, 'type': 'date'}, format='%Y-%m-%d'),
            'ends_at': forms.DateInput(
                attrs={'class': INPUT_CLASS, 'type': 'date'}, format='%Y-%m-%d'),
            'schedule': forms.TextInput(
                attrs={'class': INPUT_CLASS, 'placeholder': _('Ex: Lun-Ven 13h-15h')}),
            'capacity': forms.NumberInput(attrs={'class': INPUT_CLASS, 'min': 1}),
            'status': forms.Select(attrs={'class': INPUT_CLASS}),
            'formateurs': forms.SelectMultiple(attrs={'class': INPUT_CLASS, 'size': 6}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ('starts_at', 'ends_at'):
            self.fields[name].input_formats = ['%Y-%m-%d']
        self.fields['course'].queryset = Course.objects.filter(active=True)
        self.fields['formateurs'].queryset = User.objects.filter(
            roles__key=RoleKey.FORMATEUR
        ).distinct().order_by('first_name', 'last_name', 'email')
        self.fields['formateurs'].help_text = _(
            "Maintenez Ctrl (ou Cmd) pour sélectionner plusieurs formateurs.")

    def clean(self):
        cleaned = super().clean()
        starts_at = cleaned.get('starts_at')
        ends_at = cleaned.get('ends_at')
        if starts_at and ends_at and ends_at < starts_at:
            self.add_error(
                'ends_at', _("La date de fin doit suivre la date de début.")
            )
        return cleaned


class SessionRecordForm(forms.ModelForm):
    class Meta:
        model = SessionRecord
        fields = [
            'date', 'planned_start', 'planned_end', 'actual_start', 'actual_end',
            'module', 'lesson', 'topic', 'objectives', 'content_covered',
            'content_remaining', 'next_content', 'exercises_done',
            'difficulties', 'notes', 'status',
        ]
        widgets = {
            'date': forms.DateInput(
                attrs={'class': INPUT_CLASS, 'type': 'date'}, format='%Y-%m-%d'),
            'planned_start': forms.TimeInput(
                attrs={'class': INPUT_CLASS, 'type': 'time'}, format='%H:%M'),
            'planned_end': forms.TimeInput(
                attrs={'class': INPUT_CLASS, 'type': 'time'}, format='%H:%M'),
            'actual_start': forms.TimeInput(
                attrs={'class': INPUT_CLASS, 'type': 'time'}, format='%H:%M'),
            'actual_end': forms.TimeInput(
                attrs={'class': INPUT_CLASS, 'type': 'time'}, format='%H:%M'),
            'module': forms.Select(attrs={'class': INPUT_CLASS}),
            'lesson': forms.Select(attrs={'class': INPUT_CLASS}),
            'topic': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'objectives': forms.Textarea(attrs={'class': INPUT_CLASS, 'rows': 2}),
            'content_covered': forms.Textarea(attrs={'class': INPUT_CLASS, 'rows': 2}),
            'content_remaining': forms.Textarea(attrs={'class': INPUT_CLASS, 'rows': 2}),
            'next_content': forms.Textarea(attrs={'class': INPUT_CLASS, 'rows': 2}),
            'exercises_done': forms.Textarea(attrs={'class': INPUT_CLASS, 'rows': 2}),
            'difficulties': forms.Textarea(attrs={'class': INPUT_CLASS, 'rows': 2}),
            'notes': forms.Textarea(attrs={'class': INPUT_CLASS, 'rows': 2}),
            'status': forms.Select(attrs={'class': INPUT_CLASS}),
        }

    def __init__(self, *args, session=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.session = session or getattr(self.instance, 'session', None)
        self.fields['date'].input_formats = ['%Y-%m-%d']
        for name in ('planned_start', 'planned_end', 'actual_start', 'actual_end'):
            self.fields[name].input_formats = ['%H:%M']
        if self.session:
            self.fields['module'].queryset = Module.objects.filter(
                course=self.session.course
            )
        module_id = (
            self.data.get('module')
            or getattr(self.instance, 'module_id', None)
        )
        lessons = Lesson.objects.all()
        if module_id:
            lessons = lessons.filter(module_id=module_id)
        self.fields['lesson'].queryset = lessons.select_related('module')

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get('planned_start'), cleaned.get('planned_end')
        if start and end and end <= start:
            self.add_error('planned_end', _("L'heure de fin doit suivre le début."))
        a_start, a_end = cleaned.get('actual_start'), cleaned.get('actual_end')
        if a_start and a_end and a_end <= a_start:
            self.add_error('actual_end', _("L'heure de fin doit suivre le début."))
        status = cleaned.get('status')
        if status == SessionRecord.Status.COMPLETED and not a_start:
            self.add_error('actual_start',
                           _("Renseignez l'heure réelle de début pour une séance réalisée."))
        module = cleaned.get('module')
        lesson = cleaned.get('lesson')
        if module and lesson and lesson.module_id != module.id:
            self.add_error('lesson', _("Cette leçon n'appartient pas au module choisi."))
        return cleaned


class TextbookEntryForm(forms.ModelForm):
    """Ligne du cahier de texte : les colonnes de la fiche papier du formateur.

    Reprend exactement : date, heures, notions enseignées, nombre d'apprenants
    et observations.
    """

    class Meta:
        model = SessionRecord
        fields = [
            'date', 'planned_start', 'planned_end', 'content_covered',
            'attendee_count', 'notes', 'status',
        ]
        labels = {
            'date': _("Date"),
            'planned_start': _("Heure de début"),
            'planned_end': _("Heure de fin"),
            'content_covered': _("Notions enseignées"),
            'attendee_count': _("Nombre d'apprenants"),
            'notes': _("Observations"),
            'status': _("Statut de la séance"),
        }
        widgets = {
            'date': forms.DateInput(
                attrs={'class': INPUT_CLASS, 'type': 'date'}, format='%Y-%m-%d'),
            'planned_start': forms.TimeInput(
                attrs={'class': INPUT_CLASS, 'type': 'time'}, format='%H:%M'),
            'planned_end': forms.TimeInput(
                attrs={'class': INPUT_CLASS, 'type': 'time'}, format='%H:%M'),
            'content_covered': forms.Textarea(
                attrs={'class': INPUT_CLASS, 'rows': 3,
                       'placeholder': _("Ex : les composants d'un ordinateur")},
            ),
            'attendee_count': forms.NumberInput(
                attrs={'class': INPUT_CLASS, 'min': 0}),
            'notes': forms.Textarea(
                attrs={'class': INPUT_CLASS, 'rows': 2,
                       'placeholder': _('Observations, matériel, incident…')},
            ),
            'status': forms.Select(attrs={'class': INPUT_CLASS}),
        }

    def __init__(self, *args, session=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.session = session or getattr(self.instance, 'session', None)
        self.fields['date'].input_formats = ['%Y-%m-%d']
        for name in ('planned_start', 'planned_end'):
            self.fields[name].input_formats = ['%H:%M']
        self.fields['content_covered'].required = True

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get('planned_start')
        end = cleaned.get('planned_end')
        if start and end and end <= start:
            self.add_error('planned_end', _("L'heure de fin doit suivre le début."))

        record_date = cleaned.get('date')
        if self.session and record_date and start:
            duplicates = SessionRecord.objects.filter(
                session=self.session, date=record_date, planned_start=start,
            )
            if self.instance and self.instance.pk:
                duplicates = duplicates.exclude(pk=self.instance.pk)
            if duplicates.exists():
                raise forms.ValidationError(
                    _("Une séance est déjà enregistrée à cette date et à cette heure pour ce groupe.")
                )
        return cleaned


class StudentSessionNoteForm(forms.ModelForm):
    """Fiche de cours de l'apprenant (après chaque séance)."""

    class Meta:
        model = StudentSessionNote
        fields = [
            'notions_learned', 'difficulties', 'observations',
            'attended', 'followed_start', 'followed_end',
        ]
        labels = {
            'notions_learned': _("Notions retenues"),
            'difficulties': _("Difficultés rencontrées"),
            'observations': _("Observations"),
            'attended': _("J'étais présent à cette séance"),
            'followed_start': _("Heure de début suivie"),
            'followed_end': _("Heure de fin suivie"),
        }
        widgets = {
            'notions_learned': forms.Textarea(
                attrs={'class': INPUT_CLASS, 'rows': 3,
                       'placeholder': _("Ce que j'ai appris pendant cette séance")},
            ),
            'difficulties': forms.Textarea(
                attrs={'class': INPUT_CLASS, 'rows': 2,
                       'placeholder': _("Ce que je n'ai pas compris")},
            ),
            'observations': forms.Textarea(
                attrs={'class': INPUT_CLASS, 'rows': 2,
                       'placeholder': _('Remarque, question pour le formateur…')},
            ),
            'attended': forms.CheckboxInput(attrs={'class': 'ua-check'}),
            'followed_start': forms.TimeInput(
                attrs={'class': INPUT_CLASS, 'type': 'time'}, format='%H:%M'),
            'followed_end': forms.TimeInput(
                attrs={'class': INPUT_CLASS, 'type': 'time'}, format='%H:%M'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['notions_learned'].required = True
        for name in ('followed_start', 'followed_end'):
            self.fields[name].input_formats = ['%H:%M']

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get('followed_start')
        end = cleaned.get('followed_end')
        if start and end and end <= start:
            raise forms.ValidationError(
                _("L'heure de fin suivie doit être après l'heure de début.")
            )
        return cleaned


class ResourceForm(forms.ModelForm):
    class Meta:
        model = Resource
        fields = [
            'title', 'description', 'course', 'module', 'lesson', 'session',
            'kind', 'file', 'html_content', 'due_date', 'status',
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'description': forms.Textarea(attrs={'class': INPUT_CLASS, 'rows': 2}),
            'course': forms.Select(attrs={'class': INPUT_CLASS}),
            'module': forms.Select(attrs={'class': INPUT_CLASS}),
            'lesson': forms.Select(attrs={'class': INPUT_CLASS}),
            'session': forms.Select(attrs={'class': INPUT_CLASS}),
            'kind': forms.Select(attrs={'class': INPUT_CLASS}),
            'file': forms.ClearableFileInput(
                attrs={'class': FILE_CLASS,
                       'accept': '.pdf,.doc,.docx,.html,.htm,.ppt,.pptx,.xls,.xlsx,.zip'}),
            'html_content': forms.Textarea(attrs={'class': INPUT_CLASS, 'rows': 6}),
            'due_date': forms.DateTimeInput(
                attrs={'class': INPUT_CLASS, 'type': 'datetime-local'},
                format='%Y-%m-%dT%H:%M'),
            'status': forms.Select(attrs={'class': INPUT_CLASS}),
        }

    def __init__(self, *args, **kwargs):
        course = kwargs.pop('course', None)
        super().__init__(*args, **kwargs)
        self.fields['due_date'].input_formats = ['%Y-%m-%dT%H:%M']
        if course:
            self.fields['course'].queryset = Course.objects.filter(id=course.id)
            self.fields['session'].queryset = CourseSession.objects.filter(course=course)
            self.fields['module'].queryset = Module.objects.filter(course=course)
        self.fields['lesson'].queryset = Lesson.objects.select_related('module')

    def clean(self):
        cleaned = super().clean()
        file = cleaned.get('file')
        html = cleaned.get('html_content')
        if not file and not (html or '').strip():
            raise forms.ValidationError(
                _("Joignez un fichier ou saisissez un contenu HTML.")
            )
        if file and file.size > 10 * 1024 * 1024:
            self.add_error('file', _("Le fichier ne doit pas dépasser 10 Mo."))
        module = cleaned.get('module')
        lesson = cleaned.get('lesson')
        if module and lesson and lesson.module_id != module.id:
            self.add_error('lesson', _("Cette leçon n'appartient pas au module choisi."))
        return cleaned


class ResourceFeedbackForm(forms.ModelForm):
    """Retour de l'étudiant sur une ressource publiée."""

    rating = forms.ChoiceField(
        label=_("Ma note"),
        choices=[('', _('— Sans note —'))] + [(str(i), f"{i} / 5") for i in range(1, 6)],
        required=False,
        widget=forms.Select(attrs={'class': INPUT_CLASS}),
    )

    class Meta:
        model = ResourceFeedback
        fields = ['rating', 'comment']
        labels = {
            'comment': _("Mon retour"),
        }
        widgets = {
            'comment': forms.Textarea(
                attrs={'class': INPUT_CLASS, 'rows': 4,
                       'placeholder': _("Ce que j'ai compris, ce qui m'a aidé, mes questions au formateur…")},
            ),
        }

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get('rating') and not (cleaned.get('comment') or '').strip():
            raise forms.ValidationError(
                _("Donnez une note ou écrivez un retour.")
            )
        return cleaned


# ===========================================================================
# Comptabilité
# ===========================================================================


def porte_avertissement(form, compte, sortie):
    """Une sortie qui assèche la caisse ne se pose pas sans un second geste.

    Le service de caisse juge le plancher de solde — lui seul refuse l'écriture.
    Ici, l'écran montre ce que la sortie consomme et demande à l'agent de le
    reconnaître avant de valider. Une sortie que le service refuserait déjà n'est
    pas avertie mais refusée : `avertissement` ne dit rien au-delà du disponible,
    sans quoi l'écran tiendrait deux discours sur le même argent. Un import ou une
    commande ne passe pas par cette case : la garde du modèle reste la vraie loi.
    """
    form.avertissement_sortie = (
        caisse.avertissement(compte, sortie=sortie) if compte else None
    )
    if form.avertissement_sortie and not form.cleaned_data.get('confirme'):
        form.add_error('confirme', _(
            'Cochez la case pour valider cette sortie malgré l’avertissement.'
        ))


class CashTransactionForm(forms.ModelForm):
    # Le service de caisse nomme le refus, l'écran choisit où le montrer.
    CHAMP_DU_REFUS = {
        'solde_insuffisant': 'amount',
        'compte_archive': 'account',
        'date_future': 'occurred_at',
        'periode_cloturee': 'occurred_at',
    }

    class Meta:
        model = CashTransaction
        fields = [
            'tx_type', 'category', 'label', 'description', 'amount', 'occurred_at',
            'method', 'account', 'destination_account', 'counterparty', 'receipt',
            'status', 'note',
        ]
        widgets = {
            'tx_type': forms.Select(attrs={'class': INPUT_CLASS}),
            'category': forms.Select(attrs={'class': INPUT_CLASS}),
            'label': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'description': forms.Textarea(attrs={'class': INPUT_CLASS, 'rows': 2}),
            'amount': forms.NumberInput(attrs={'class': INPUT_CLASS, 'min': 1}),
            'occurred_at': forms.DateTimeInput(
                attrs={'class': INPUT_CLASS, 'type': 'datetime-local'},
                format='%Y-%m-%dT%H:%M'),
            'method': forms.Select(attrs={'class': INPUT_CLASS}),
            'account': forms.Select(attrs={'class': INPUT_CLASS}),
            'destination_account': forms.Select(attrs={'class': INPUT_CLASS}),
            'counterparty': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'receipt': forms.ClearableFileInput(
                attrs={'class': FILE_CLASS, 'accept': '.pdf,.jpg,.jpeg,.png'}),
            'status': forms.Select(attrs={'class': INPUT_CLASS}),
            'note': forms.Textarea(attrs={'class': INPUT_CLASS, 'rows': 2}),
        }

    confirme = forms.BooleanField(
        label=_('Je confirme cette sortie malgré l’avertissement sur le solde disponible.'),
        required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.avertissement_sortie = None
        self.fields['account'].queryset = CashAccount.objects.filter(active=True)
        self.fields['destination_account'].queryset = CashAccount.objects.filter(active=True)
        # Le disponible se lit au moment où la caisse se choisit : l'agent ne
        # découvre pas l'assèchement après avoir validé.
        self.fields['account'].label_from_instance = self._libelle_de_caisse
        # Une caisse fermée n'a plus sa place dans la liste : le refus se dit en
        # français plutôt qu'en « select a valid choice ».
        for clee in ('account', 'destination_account'):
            self.fields[clee].error_messages['invalid_choice'] = _(
                'Compte introuvable ou fermé : choisissez une caisse encore ouverte.'
            )
        self.fields['occurred_at'].input_formats = ['%Y-%m-%dT%H:%M']
        tx_type = self.data.get('tx_type') or getattr(self.instance, 'tx_type', None)
        categories = TransactionCategory.objects.filter(active=True)
        if tx_type:
            categories = categories.filter(direction=tx_type)
        self.fields['category'].queryset = categories
        self.fields['destination_account'].required = False

    @staticmethod
    def _libelle_de_caisse(compte):
        disponible = f'{compte.disponible():,}'.replace(',', ' ')
        return _('%(nom)s — disponible %(disponible)s %(devise)s') % {
            'nom': compte.name, 'disponible': disponible, 'devise': compte.currency}

    def clean(self):
        cleaned = super().clean()
        tx_type = cleaned.get('tx_type')
        account = cleaned.get('account')
        destination = cleaned.get('destination_account')
        category = cleaned.get('category')
        if tx_type == CashTransaction.Type.TRANSFER:
            if not destination:
                self.add_error('destination_account',
                               _("Choisissez le compte destinataire."))
            elif destination == account:
                self.add_error('destination_account',
                               _("Le compte destinataire doit être différent."))
        elif destination:
            cleaned['destination_account'] = None
        if category and tx_type and category.direction != tx_type:
            self.add_error('category', _("Cette catégorie ne correspond pas au type."))
        if not self._controle_solde(cleaned):
            porte_avertissement(
                self, cleaned.get('account'),
                caisse.sortie_prevue(sens=tx_type,
                                     montant=cleaned.get('amount') or 0,
                                     statut=cleaned.get('status')))
        return cleaned

    def _controle_solde(self, cleaned):
        """Le verdict du service de caisse, rendu champ par champ.

        Une écriture validée ne mènera jamais une caisse sous son plancher, ne
        se date pas après aujourd'hui et ne revient pas sur une période déjà
        clôturée. Ces lois vivent dans ``core.caisse`` ; l'écran les lit au lieu
        de les recalculer, sans quoi le formulaire et l'enregistrement
        finiraient par se contredire sur le même argent.

        ``True`` quand le verdict refuse déjà l'écriture : l'avertissement sur le
        disponible n'a plus rien à dire sur une sortie déjà rejetée.
        """
        sortie = caisse.sortie_prevue(sens=cleaned.get('tx_type'),
                                      montant=cleaned.get('amount') or 0,
                                      statut=cleaned.get('status'))
        ignorees = [self.instance.pk] if self.instance.pk else []
        survenu = cleaned.get('occurred_at')
        for champ, compte, debit in (
            ('account', cleaned.get('account'), sortie),
            ('destination_account', cleaned.get('destination_account'), 0),
        ):
            if not compte:
                continue
            try:
                caisse.juger(compte, sortie=debit, survenu=survenu,
                             nature=self.instance.nature, ignorees=ignorees)
            except forms.ValidationError as refus:
                self.add_error(self.CHAMP_DU_REFUS.get(refus.code),
                               refus.messages[0])
                return True
        return False


class CashAccountForm(forms.ModelForm):
    class Meta:
        model = CashAccount
        fields = ['name', 'kind', 'currency', 'opening_balance', 'description', 'active']
        labels = {
            'name': _('Nom du compte'),
            'kind': _('Type de compte'),
            'currency': _('Devise'),
            'opening_balance': _('Solde d’ouverture'),
            'description': _('Description'),
            'active': _('Compte actif'),
        }
        widgets = {
            'name': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'kind': forms.Select(attrs={'class': INPUT_CLASS}),
            'currency': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'opening_balance': forms.NumberInput(attrs={'class': INPUT_CLASS}),
            'description': forms.Textarea(attrs={'class': INPUT_CLASS, 'rows': 2}),
        }


class CashAccountAdminForm(forms.ModelForm):
    """Administrer un compte existant : état, découvert, compte de remplacement.

    Le nom et le solde d'ouverture ne sont pas de la partie. Le nom sert de clé
    aux reprises du journal écrites dans la commande d'import ; l'ouverture
    d'une caisse qui a déjà des écritures ne se réécrit pas, elle se régularise
    par une écriture d'ajustement — sinon plus aucun journal ne représente
    l'argent réellement encaissé.
    """
    etat = forms.ChoiceField(
        label=_('État du compte'), choices=CashAccount.Status.choices,
        widget=forms.Select(attrs={'class': INPUT_CLASS}))

    class Meta:
        model = CashAccount
        fields = ['kind', 'currency', 'description', 'overdraft_limit',
                  'etat', 'replaced_by']
        labels = {
            'kind': _('Type de compte'),
            'currency': _('Devise'),
            'description': _('Description'),
            'overdraft_limit': _('Découvert autorisé'),
            'replaced_by': _('Compte de remplacement'),
        }
        widgets = {
            'kind': forms.Select(attrs={'class': INPUT_CLASS}),
            'currency': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'description': forms.Textarea(attrs={'class': INPUT_CLASS, 'rows': 3}),
            'overdraft_limit': forms.NumberInput(
                attrs={'class': INPUT_CLASS, 'min': 0}),
            'replaced_by': forms.Select(attrs={'class': INPUT_CLASS}),
        }

    def __init__(self, *args, utilisateur=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.utilisateur = utilisateur
        self.fields['replaced_by'].required = False
        self.fields['replaced_by'].empty_label = _('— aucun —')
        self.fields['replaced_by'].queryset = CashAccount.objects.exclude(
            pk=self.instance.pk)
        self.initial.setdefault('etat', self.instance.status)

    def clean_overdraft_limit(self):
        plafond = self.cleaned_data['overdraft_limit']
        if plafond > self.instance.overdraft_limit and not (
                self.utilisateur and
                self.utilisateur.has_role(RoleKey.SUPER_ADMIN)):
            raise forms.ValidationError(_(
                'Lever un découvert exceptionnel est réservé au super administrateur : le découvert reste interdit par défaut.'
            ))
        return plafond

    def clean_currency(self):
        devise = self.cleaned_data['currency']
        if devise != self.instance.currency and self.instance.transactions.exists():
            raise forms.ValidationError(_(
                "La devise d'un compte qui a déjà des écritures ne change pas : ouvrez un second compte et archivez le premier."
            ))
        return devise

    def clean(self):
        cleaned = super().clean()
        # Archiver une caisse encore pleine ou chargée de brouillons laisse des
        # sommes sans destination : le compte de remplacement répond à cela.
        if cleaned.get('etat') == CashAccount.Status.ARCHIVED:
            brouillons = CashTransaction.objects.filter(
                account=self.instance,
                status=CashTransaction.Status.DRAFT,
            ).exists()
            if (brouillons or self.instance.balance) and not cleaned.get('replaced_by'):
                self.add_error('replaced_by', _(
                    'Cette caisse a encore un solde ou des brouillons : désignez le compte qui les reprend.'
                ))
        return cleaned

    def save(self, commit=True):
        compte = super().save(commit=False)
        etat = self.cleaned_data['etat']
        compte.active = etat == CashAccount.Status.ACTIVE
        compte.archived_at = (self.instance.archived_at or timezone.now()
                              if etat == CashAccount.Status.ARCHIVED else None)
        if commit:
            compte.save()
        return compte


class CashAdjustForm(forms.Form):
    """Ajustement de solde : un montant, un sens, un motif — rien d'autre.

    Le champ reste volontairement étroit : ce qui se règle ici n'est ni une
    recette ni une charge, mais la correction assumée d'un solde. La date, elle,
    reste celle du jour — un ajustement antidaté réécrirait une période déjà
    jugée par une clôture.
    """
    SENS = [
        (CashTransaction.Type.IN, _('Relever le solde')),
        (CashTransaction.Type.OUT, _('Baisser le solde')),
    ]
    montant = forms.IntegerField(
        label=_('Montant'), min_value=1,
        error_messages={
            'required': _('Indiquez le montant de l’ajustement.'),
            'min_value': _('Un ajustement porte un montant non nul.'),
        },
        widget=forms.NumberInput(attrs={'class': INPUT_CLASS, 'min': 1}))
    sens = forms.ChoiceField(
        label=_('Sens de l’ajustement'), choices=SENS,
        widget=forms.Select(attrs={'class': INPUT_CLASS}))
    motif = forms.CharField(
        label=_('Motif de l’ajustement'),
        error_messages={'required': _('Un motif est obligatoire pour ajuster un solde.')},
        widget=forms.Textarea(attrs={'class': INPUT_CLASS, 'rows': 2}))
    confirme = forms.BooleanField(
        label=_('Je confirme cette baisse de solde malgré l’avertissement.'),
        required=False)

    def __init__(self, *args, compte, **kwargs):
        super().__init__(*args, **kwargs)
        self.compte = compte
        self.avertissement_sortie = None

    def clean(self):
        cleaned = super().clean()
        porte_avertissement(
            self, self.compte,
            cleaned['montant'] if (
                cleaned.get('sens') == CashTransaction.Type.OUT) else 0)
        return cleaned


class CashResetForm(forms.Form):
    """Remise à zéro d'une caisse : confirmation explicite et motif obligatoire."""
    motif = forms.CharField(
        label=_('Motif de la réinitialisation'),
        error_messages={'required': _('Un motif est obligatoire pour réinitialiser une caisse.')},
        widget=forms.Textarea(attrs={'class': INPUT_CLASS, 'rows': 2}))
    confirme = forms.BooleanField(
        label=_("Je confirme : le solde sera ramené à zéro par une écriture de régularisation, et l’historique restera consultable."),
        required=True,
        error_messages={'required': _('La réinitialisation d’une caisse demande une confirmation explicite.')})


class CashCorrectionForm(forms.Form):
    """Rectifier une écriture enregistrée : le chiffre bouge, la ligne reste.

    Le compte, le sens et le statut ne se touchent pas ici. Une écriture mise
    sur la mauvaise caisse s'annule et se ressaisit à côté : les deux lignes
    demeurent visibles et reliées, et le journal continue de raconter ce qui
    est réellement sorti. Le motif, lui, est obligatoire — une correction sans
    raison n'est pas une correction.
    """
    montant = forms.IntegerField(
        label=_('Montant'), min_value=1,
        error_messages={
            'required': _('Indiquez le montant corrigé.'),
            'min_value': _('Une écriture porte un montant non nul.'),
        },
        widget=forms.NumberInput(attrs={'class': INPUT_CLASS, 'min': 1}))
    categorie = forms.ModelChoiceField(
        label=_('Catégorie'), required=False,
        queryset=TransactionCategory.objects.none(),
        widget=forms.Select(attrs={'class': INPUT_CLASS}))
    libelle = forms.CharField(
        label=_('Libellé'), max_length=200,
        widget=forms.TextInput(attrs={'class': INPUT_CLASS}))
    survenu = forms.DateTimeField(
        label=_('Date effective'), input_formats=['%Y-%m-%dT%H:%M'],
        error_messages={'invalid': _('La date doit être au format jj/mm/aaaa hh:mm.')},
        widget=forms.DateTimeInput(
            attrs={'class': INPUT_CLASS, 'type': 'datetime-local'},
            format='%Y-%m-%dT%H:%M'))
    motif = forms.CharField(
        label=_('Motif de la correction'),
        error_messages={'required': _('Un motif est obligatoire pour corriger une écriture.')},
        widget=forms.Textarea(attrs={'class': INPUT_CLASS, 'rows': 3}))

    def __init__(self, *args, ecriture, **kwargs):
        super().__init__(*args, **kwargs)
        self.ecriture = ecriture
        self.fields['categorie'].queryset = TransactionCategory.objects.filter(
            active=True, direction=ecriture.tx_type)
        if not self.is_bound:
            self.initial.update({
                'montant': ecriture.amount,
                'categorie': ecriture.category_id,
                'libelle': ecriture.label,
                'survenu': timezone.localtime(ecriture.occurred_at)
                                 .strftime('%Y-%m-%dT%H:%M'),
            })


class TransactionCategoryForm(forms.ModelForm):
    """Catégorie nouvelle : un nom et le sens des montants qu'elle range."""

    class Meta:
        model = TransactionCategory
        fields = ['name', 'direction']
        labels = {
            'name': _('Nom de la catégorie'),
            'direction': _('Sens des montants'),
        }
        widgets = {
            'name': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'direction': forms.Select(attrs={'class': INPUT_CLASS}),
        }


class TransactionCategoryAdminForm(forms.ModelForm):
    """Régler une catégorie existante : le nom s'édite, le sens reste fixé.

    Le sens — entrée, sortie, transfert — est ce qui range les écritures déjà
    écrites. Le changer après coup ferait basculer des lignes d'un côté du
    journal à l'autre sans aucune trace. Une catégorie qui ne sert plus ne se
    supprime pas non plus : elle se désactive, et ses écritures restent.
    """

    class Meta:
        model = TransactionCategory
        fields = ['name', 'active']
        labels = {
            'name': _('Nom de la catégorie'),
            'active': _('Catégorie active'),
        }
        widgets = {
            'name': forms.TextInput(attrs={'class': INPUT_CLASS}),
        }


class CashClosureForm(forms.ModelForm):
    class Meta:
        model = CashClosure
        fields = ['account', 'date', 'counted_amount', 'note']
        widgets = {
            'account': forms.Select(attrs={'class': INPUT_CLASS}),
            'date': forms.DateInput(
                attrs={'class': INPUT_CLASS, 'type': 'date'}, format='%Y-%m-%d'),
            'counted_amount': forms.NumberInput(attrs={'class': INPUT_CLASS, 'min': 0}),
            'note': forms.Textarea(attrs={'class': INPUT_CLASS, 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['account'].queryset = CashAccount.objects.filter(active=True)
        self.fields['date'].input_formats = ['%Y-%m-%d']


# Statuts d'inscription réellement encaissables. Une inscription créée au
# guichet reste « En attente » tant que la direction ne l'a pas validée : elle
# ne doit donc pas apparaître dans la liste des dossiers à encaisser.
PAYABLE_ENROLLMENT_STATUSES = (
    Enrollment.Status.ACTIVE,
    Enrollment.Status.COMPLETED,
)


def mois_deja_regle(enrollment, annee, numero):
    """Le paiement qui a déjà réglé ce mois, ``None`` si le mois est libre."""
    if not (enrollment and annee and numero):
        return None
    return Payment.objects.filter(
        enrollment=enrollment, period_year=int(annee), period_month=int(numero),
    ).exclude(
        status__in=[Payment.Status.CANCELLED, Payment.Status.REFUNDED]
    ).first()


def mensualite_attendue(enrollment):
    """La mensualité que la formation pratique : le net dû réparti sur sa durée.

    Le catalogue ne stocke pas de tarif mensuel séparé, seulement un total et une
    durée ; les classeurs énoncent le loyer exactement ainsi. La remise consentie
    sur le dossier est donc respectée sans rien inventer.
    """
    cours = enrollment.session.course
    du = enrollment.net_amount or cours.fee_amount
    duree = max(cours.duration_months or 0, 1)
    return max(round(du / duree), 1)


class EnrollmentSelect(forms.Select):
    """Liste d'inscriptions enrichie du reste à payer de chaque dossier."""

    def create_option(self, name, value, label, selected, index,
                      subindex=None, attrs=None):
        option = super().create_option(
            name, value, label, selected, index, subindex=subindex, attrs=attrs
        )
        instance = getattr(value, 'instance', None)
        if instance is not None:
            option['attrs']['data-balance'] = instance.balance_due
        return option


class EnrollmentChoiceField(forms.ModelChoiceField):
    """Inscription dont le libellé rappelle l'étudiant et le reste à payer."""

    def label_from_instance(self, obj):
        course = obj.session.course.title
        if obj.net_amount <= 0:
            state = _("montant net à définir")
        elif obj.balance_due <= 0:
            state = _("soldé")
        else:
            state = _("reste %(amount)s FCFA") % {'amount': obj.balance_due}
        return f"{obj.student.display_label} — {course} ({state})"


class StudentPaymentForm(forms.Form):
    student = forms.ModelChoiceField(
        label=_("Étudiant"),
        queryset=User.objects.none(),
        required=False,
        empty_label=_("— Choisir un étudiant —"),
        widget=forms.Select(attrs={'class': INPUT_CLASS}),
        help_text=_("La liste des inscriptions se filtre sur l'étudiant choisi. Un étudiant absent de cette liste n'a pas encore de compte actif."),
    )
    enrollment = EnrollmentChoiceField(
        label=_("Inscription à encaisser"),
        queryset=Enrollment.objects.none(),
        empty_label=_("— Choisir un dossier —"),
        widget=EnrollmentSelect(attrs={'class': INPUT_CLASS}),
        error_messages={
            'required': _("Choisissez l'inscription à encaisser."),
            'invalid_choice': _("Cette inscription n'est pas encaissable : elle est annulée, en attente de validation ou n'appartient pas à l'étudiant sélectionné."),
        },
    )
    amount = forms.IntegerField(
        label=_("Montant encaissé"),
        min_value=1,
        widget=forms.NumberInput(attrs={'class': INPUT_CLASS, 'min': 1}),
    )
    method = forms.ChoiceField(
        label=_("Moyen de paiement"),
        choices=Payment.Method.choices,
        widget=forms.Select(attrs={'class': INPUT_CLASS}),
    )
    account = forms.ModelChoiceField(
        label=_("Caisse / compte destinataire"),
        queryset=CashAccount.objects.none(),
        widget=forms.Select(attrs={'class': INPUT_CLASS}),
    )
    paid_at = forms.DateTimeField(
        label=_("Date et heure du paiement"),
        widget=forms.DateTimeInput(
            attrs={'class': INPUT_CLASS, 'type': 'datetime-local'},
            format='%Y-%m-%dT%H:%M'),
    )
    note = forms.CharField(
        label=_("Observations"), required=False,
        widget=forms.Textarea(attrs={'class': INPUT_CLASS, 'rows': 2}),
    )
    motif = forms.ChoiceField(
        label=_("Motif du paiement"),
        choices=Payment.Motif.choices,
        initial=Payment.Motif.OTHER,
        widget=forms.Select(attrs={'class': INPUT_CLASS}),
        help_text=_("Mensualité : le paiement règle un mois précis. Frais d'inscription : versement unique à l'entrée en formation."),
    )
    period_month = forms.ChoiceField(
        label=_("Mois réglé"), required=False, choices=[('', _("— Aucun —"))] + list(MOIS),
        widget=forms.Select(attrs={'class': INPUT_CLASS}),
    )
    period_year = forms.IntegerField(
        label=_("Année du mois réglé"), required=False,
        min_value=2000, max_value=2100, initial=timezone.localdate().year,
        widget=forms.NumberInput(attrs={'class': INPUT_CLASS}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['student'].queryset = (
            User.objects.filter(
                roles__key=RoleKey.ETUDIANT,
                account_status=AccountStatus.ACTIVE,
            ).distinct().order_by('last_name', 'first_name')
        )
        enrollments = (
            Enrollment.objects.select_related('student', 'session__course')
            .filter(status__in=PAYABLE_ENROLLMENT_STATUSES)
            .order_by('student__last_name', 'session__course__title')
        )
        if self.is_bound:
            student_id = self.data.get('student') or ''
        else:
            student_id = self.initial.get('student') or ''
        if student_id:
            enrollments = enrollments.filter(student_id=student_id)
        self.fields['enrollment'].queryset = enrollments
        self.fields['enrollment'].help_text = _(
            "Chaque ligne rappelle l'étudiant, la formation et le reste à payer.")
        if student_id and not enrollments.exists():
            dossiers = Enrollment.objects.filter(student_id=student_id)
            self.fields['enrollment'].help_text = (
                _("Aucune inscription pour cet étudiant : elle se crée au secrétariat avant tout encaissement.")
                if not dossiers.exists() else
                _("Ce dossier n'est pas encore encaissable : le secrétariat l'a créé, il attend une validation.")
            )
        self.fields['account'].queryset = CashAccount.objects.filter(active=True)
        self.fields['paid_at'].input_formats = ['%Y-%m-%dT%H:%M']

    def clean_paid_at(self):
        """L'encaissement ne se date pas plus tard que le jour de la saisie.

        Une date future ferait entrer dans les états de caisse un argent qui n'a
        pas été reçu. Le mois couvert se lit déjà dans la période réglée, qui peut
        donc rester future sans que la recette le soit.
        """
        instant = self.cleaned_data['paid_at']
        if instant > timezone.localtime():
            raise forms.ValidationError(
                _("Le paiement ne peut pas être daté après aujourd'hui (%(jour)s).")
                % {'jour': timezone.localdate().strftime('%d/%m/%Y')},
            )
        return instant

    def clean(self):
        cleaned = super().clean()
        student = cleaned.get('student')
        enrollment = cleaned.get('enrollment')
        amount = cleaned.get('amount') or 0

        if enrollment and student and enrollment.student_id != student.id:
            self.add_error(
                'enrollment',
                _("Cette inscription n'appartient pas à l'étudiant sélectionné."),
            )

        if student and not enrollment and 'enrollment' not in self.errors:
            if student.enrollments.filter(
                status=Enrollment.Status.PENDING
            ).exists():
                self.add_error(
                    'enrollment',
                    _("L'inscription de cet étudiant est en attente de validation : elle ne peut pas encore être encaissée."),
                )
            elif not student.enrollments.exclude(
                status=Enrollment.Status.CANCELLED
            ).exists():
                self.add_error(
                    'enrollment',
                    _("Cet étudiant n'a pas encore d'inscription. Créez-la dans le panneau « Inscrire un étudiant », puis faites-la valider avant l'encaissement."),
                )

        if enrollment:
            # Compatibilité : un ancien formulaire peut ne pas transmettre
            # l'étudiant ; l'inscription suffit alors à l'identifier.
            if not cleaned.get('student'):
                cleaned['student'] = enrollment.student
            if enrollment.net_amount <= 0:
                self.add_error(
                    'amount',
                    _("Le montant net du dossier n'est pas défini : complétez l'inscription avant d'encaisser."),
                )
            elif amount > enrollment.balance_due:
                if enrollment.balance_due <= 0:
                    self.add_error(
                        'amount',
                        _("Ce dossier est soldé : aucun montant ne reste à encaisser."),
                    )
                else:
                    self.add_error(
                        'amount',
                        _("Le montant dépasse le reste à payer (%(montant)s FCFA).") % {'montant': enrollment.balance_due},
                    )

        cleaned.update(self._controle_periode(enrollment))
        return cleaned

    def _controle_periode(self, enrollment):
        """Le mois réglé n'existe que pour une mensualité, et jamais deux fois."""
        motif = self.cleaned_data.get('motif')
        if motif != Payment.Motif.MONTHLY:
            return {'period_month': None, 'period_year': None}

        numero = self.cleaned_data.get('period_month')
        annee = self.cleaned_data.get('period_year') or timezone.localdate().year
        if not numero:
            self.add_error('period_month',
                           _("Précisez le mois que cette mensualité règle."))
            return {'period_year': annee}

        numero = int(numero)
        regle = mois_deja_regle(enrollment, annee, numero)
        if regle:
            self.add_error(
                'period_month',
                _("Le mois de %(mois)s %(annee)s est déjà réglé (%(ref)s).") % {
                    'mois': dict(MOIS)[numero], 'annee': annee,
                    'ref': regle.reference},
            )
        return {'period_month': numero, 'period_year': annee}


class PaymentMonthsForm(forms.Form):
    """La grille des douze mois : un paiement par mois coché, jamais deux sur le même.

    Les lignes de mois ne sont pas des champs déclarés — elles sont portées par
    le tableau, donc cochés ``mois`` et montants ``montant_<mois>`` arrivent en
    vrac. Le contrôle est fait ici : un mois déjà réglé, un montant oublié ou
    une grille qui dépasserait le reste à payer ne passent pas.
    """

    annee = forms.IntegerField(
        label=_("Année réglée"), min_value=2000, max_value=2100,
        initial=timezone.localdate().year,
        widget=forms.NumberInput(attrs={'class': INPUT_CLASS}),
    )
    student = forms.ModelChoiceField(
        label=_("Étudiant"), queryset=User.objects.none(), required=False,
        empty_label=_("— Choisir un étudiant —"),
        widget=forms.Select(attrs={'class': INPUT_CLASS}),
    )
    enrollment = EnrollmentChoiceField(
        label=_("Dossier de l'étudiant"), queryset=Enrollment.objects.none(),
        widget=EnrollmentSelect(attrs={'class': INPUT_CLASS}),
        error_messages={'required': _("Choisissez le dossier à encaisser.")},
    )
    method = forms.ChoiceField(
        label=_("Moyen de paiement"), choices=Payment.Method.choices,
        widget=forms.Select(attrs={'class': INPUT_CLASS}),
    )
    account = forms.ModelChoiceField(
        label=_("Caisse / compte destinataire"), queryset=CashAccount.objects.none(),
        widget=forms.Select(attrs={'class': INPUT_CLASS}),
    )
    note = forms.CharField(
        label=_("Observations"), required=False,
        widget=forms.Textarea(attrs={'class': INPUT_CLASS, 'rows': 2}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.lignes = []
        self.fields['student'].queryset = (
            User.objects.filter(
                roles__key=RoleKey.ETUDIANT,
                account_status=AccountStatus.ACTIVE,
            ).distinct().order_by('last_name', 'first_name')
        )
        dossiers = (
            Enrollment.objects.select_related('student', 'session__course')
            .filter(status__in=PAYABLE_ENROLLMENT_STATUSES)
            .order_by('student__last_name', 'session__course__title')
        )
        etudiant = (self.data.get('student') if self.is_bound
                    else (self.initial or {}).get('student'))
        if etudiant:
            dossiers = dossiers.filter(student_id=etudiant)
        self.fields['enrollment'].queryset = dossiers
        self.fields['account'].queryset = CashAccount.objects.filter(active=True)

    def clean(self):
        cleaned = super().clean()
        dossier = cleaned.get('enrollment')
        annee = cleaned.get('annee')
        lignes = []

        for numero, libelle in MOIS:
            if str(numero) not in self.data.getlist('mois'):
                continue
            montant = self._montant(f'montant_{numero}')  # i18n-exempt: nom du champ de saisie
            if montant is None:
                self.add_error(
                    None,
                    _("%(mois)s : indiquez le montant encaissé.") % {'mois': libelle},
                )
                continue
            regle = mois_deja_regle(dossier, annee, numero)
            if regle:
                self.add_error(
                    None,
                    _("%(mois)s %(annee)s est déjà réglé (%(ref)s).") % {
                        'mois': libelle, 'annee': annee, 'ref': regle.reference},
                )
                continue
            lignes.append({'mois': numero, 'libelle': libelle, 'montant': montant,
                           'motif': Payment.Motif.MONTHLY, 'annee': annee})

        if 'frais' in self.data:
            montant = self._montant('montant_frais')
            if montant is None:
                self.add_error(None, _("Frais d'inscription : indiquez le montant encaissé."))
            elif dossier and dossier.payments.filter(
                    motif=Payment.Motif.ENROLLMENT).exclude(
                status__in=[Payment.Status.CANCELLED,
                            Payment.Status.REFUNDED]).exists():
                self.add_error(None, _("Les frais d'inscription de ce dossier sont déjà encaissés."))
            else:
                lignes.append({'mois': None, 'libelle': _("Frais d'inscription"),
                               'montant': montant,
                               'motif': Payment.Motif.ENROLLMENT, 'annee': None})

        if not lignes and not self.errors:
            self.add_error(None, _("Cochez au moins un mois à encaisser."))

        total = sum(ligne['montant'] for ligne in lignes)
        if dossier and total and total > dossier.balance_due:
            self.add_error(
                None,
                _("Le total dépasse le reste à payer (%(montant)s FCFA).") % {
                    'montant': dossier.balance_due},
            )

        cleaned['lignes'] = lignes
        self.lignes = lignes
        return cleaned

    def _montant(self, nom):
        """Le montant saisi, ``None`` s'il manque ou n'est pas un nombre positif."""
        brut = (self.data.get(nom) or '').strip().replace(' ', '')
        if not brut.isdigit():
            return None
        montant = int(brut)
        return montant if montant > 0 else None


class CounterEnrollmentForm(forms.Form):
    """Inscription créée au guichet : elle reste en attente de validation.

    Le comptable et le secrétariat peuvent ouvrir le dossier d'un étudiant
    encore inconnu ; la direction valide ensuite l'inscription, et seulement
    à ce moment le dossier devient encaissable.
    """

    student = forms.ModelChoiceField(
        label=_("Étudiant"),
        queryset=User.objects.none(),
        widget=forms.Select(attrs={'class': INPUT_CLASS}),
    )
    session = forms.ModelChoiceField(
        label=_("Formation / groupe"),
        queryset=enrollable_sessions(),
        widget=forms.Select(attrs={'class': INPUT_CLASS}),
    )
    start_date = forms.DateField(
        label=_("Date de début"),
        required=False,
        widget=forms.DateInput(
            attrs={'class': INPUT_CLASS, 'type': 'date'}, format='%Y-%m-%d'),
    )
    tariff_amount = forms.IntegerField(
        label=_("Tarif appliqué (FCFA)"),
        min_value=0,
        required=False,
        widget=forms.NumberInput(attrs={'class': INPUT_CLASS, 'min': 0}),
        help_text=_("Laisser vide pour reprendre le tarif catalogue du groupe."),
    )
    discount_amount = forms.IntegerField(
        label=_("Remise (FCFA)"),
        min_value=0,
        required=False,
        initial=0,
        widget=forms.NumberInput(attrs={'class': INPUT_CLASS, 'min': 0}),
    )
    payment_plan = forms.CharField(
        label=_("Modalités de paiement"),
        required=False,
        max_length=200,
        widget=forms.TextInput(attrs={'class': INPUT_CLASS}),
    )
    notes = forms.CharField(
        label=_("Observations"),
        required=False,
        widget=forms.Textarea(attrs={'class': INPUT_CLASS, 'rows': 2}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['student'].queryset = (
            User.objects.filter(roles__key=RoleKey.ETUDIANT)
            .distinct().order_by('last_name', 'first_name')
        )
        self.fields['start_date'].input_formats = ['%Y-%m-%d']

    def clean(self):
        cleaned = super().clean()
        student = cleaned.get('student')
        session = cleaned.get('session')
        tariff = cleaned.get('tariff_amount')
        discount = cleaned.get('discount_amount') or 0

        if tariff is None and session is not None:
            tariff = session.course.fee_amount
            cleaned['tariff_amount'] = tariff
        tariff = tariff or 0
        if discount > tariff:
            self.add_error(
                'discount_amount', _("La remise ne peut pas dépasser le tarif.")
            )
        if student and session and Enrollment.objects.filter(
            student=student, session=session
        ).exists():
            self.add_error(
                'session',
                _("Cet étudiant est déjà inscrit à cette formation."),
            )
        cleaned['net_amount'] = max(tariff - discount, 0)
        return cleaned

    def save(self, user):
        data = self.cleaned_data
        return Enrollment.objects.create(
            student=data['student'],
            session=data['session'],
            status=Enrollment.Status.PENDING,
            start_date=data['start_date'],
            tariff_amount=data['tariff_amount'] or data['session'].course.fee_amount,
            discount_amount=data['discount_amount'] or 0,
            net_amount=data['net_amount'],
            payment_plan=data['payment_plan'],
            notes=data['notes'],
            registered_by=user,
        )

