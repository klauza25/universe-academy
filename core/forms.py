from django import forms
from django.core.validators import FileExtensionValidator
from django.db.models import Q
from .models import (
    User, ScholarshipApplication, ScholarshipDocument,
    Destination, Course, CourseSession, Enrollment,
    Payment, Attendance, AccessEvent, AccountStatus, RoleKey,
    REQUESTABLE_ROLE_CHOICES,
    Contact, Visit, VisitReason, Prospect, ProspectFollowUp,
    Module, Lesson, SessionRecord, Resource, StudentDocument,
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
    'file:mr-3 file:cursor-pointer file:border-0 file:bg-slate-100 file:px-3 file:py-2.5 '
    'file:text-sm file:font-medium file:text-slate-700 hover:file:bg-slate-200 '
    'focus:outline-none focus:ring-2 focus:ring-slate-900/10'
)


class LoginForm(forms.Form):
    identifier = forms.CharField(
        label="Identifiant",
        widget=forms.TextInput(attrs={
            'class': INPUT_CLASS,
            'placeholder': 'Email ou code interne'
        })
    )
    password = forms.CharField(
        label="Mot de passe",
        widget=forms.PasswordInput(attrs={
            'class': INPUT_CLASS,
            'placeholder': '••••••••'
        })
    )


class RegisterForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput(attrs={
        'class': INPUT_CLASS,
        'placeholder': 'Minimum 8 caractères'
    }))
    password_confirm = forms.CharField(
        label="Confirmer le mot de passe",
        widget=forms.PasswordInput(attrs={
            'class': INPUT_CLASS,
            'placeholder': '••••••••'
        })
    )
    requested_role = forms.ChoiceField(
        label="Rôle demandé",
        choices=[('', '-- Choisir un rôle --')] + REQUESTABLE_ROLE_CHOICES,
        widget=forms.Select(attrs={'class': INPUT_CLASS}),
        help_text="Votre demande sera examinée : aucun accès n'est accordé avant validation.",
    )

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email']
        widgets = {
            'first_name': forms.TextInput(attrs={
                'class': INPUT_CLASS, 'placeholder': 'Prénom'
            }),
            'last_name': forms.TextInput(attrs={
                'class': INPUT_CLASS, 'placeholder': 'Nom'
            }),
            'email': forms.EmailInput(attrs={
                'class': INPUT_CLASS, 'placeholder': 'email@exemple.com'
            }),
        }

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('password') != cleaned.get('password_confirm'):
            raise forms.ValidationError("Les mots de passe ne correspondent pas.")
        return cleaned


class UserCreateForm(forms.ModelForm):
    role = forms.ChoiceField(
        choices=[('', '-- Choisir un rôle --')] + [
            (key, label) for key, label in RoleKey.choices
            if key not in ('SUPER_ADMIN', 'ADMIN')
        ],
        label="Rôle",
        help_text=(
            "Les rôles SUPER_ADMIN et ADMIN s'attribuent ensuite depuis la "
            "fiche utilisateur, par un super administrateur."
        ),
    )
    password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={'class': 'w-full p-2 border rounded'}),
        help_text="Laisser vide pour envoyer une invitation par email"
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
                'placeholder': 'Nom'
            }),
            'first_name': forms.TextInput(attrs={
                'class': INPUT_CLASS,
                'placeholder': 'Prénom'
            }),
            'email': forms.EmailInput(attrs={
                'class': INPUT_CLASS,
                'placeholder': 'email@exemple.com'
            }),
            'phone': forms.TextInput(attrs={
                'class': INPUT_CLASS,
                'placeholder': '+242 06 XXX XX XX'
            }),
            'destination': forms.Select(attrs={'class': INPUT_CLASS}),
            'program': forms.TextInput(attrs={
                'class': INPUT_CLASS,
                'placeholder': 'Ex: Licence, Master'
            }),
            'study_domain': forms.TextInput(attrs={
                'class': INPUT_CLASS,
                'placeholder': 'Ex: Informatique, Médecine'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['destination'].queryset = Destination.objects.filter(active=True)


class ScholarshipDocumentForm(forms.Form):
    identity_doc = forms.FileField(
        label="Pièce d'identité",
        validators=[FileExtensionValidator(['pdf', 'jpg', 'jpeg', 'png'])],
        widget=forms.ClearableFileInput(attrs={
            'class': FILE_CLASS, 'accept': '.pdf,.jpg,.jpeg,.png'
        })
    )
    diplomas = forms.FileField(
        label="Diplômes",
        required=False,
        validators=[FileExtensionValidator(['pdf', 'jpg', 'jpeg', 'png'])],
        widget=forms.ClearableFileInput(attrs={
            'class': FILE_CLASS, 'accept': '.pdf,.jpg,.jpeg,.png'
        })
    )
    transcripts = forms.FileField(
        label="Relevés de notes",
        required=False,
        validators=[FileExtensionValidator(['pdf', 'jpg', 'jpeg', 'png'])],
        widget=forms.ClearableFileInput(attrs={
            'class': FILE_CLASS, 'accept': '.pdf,.jpg,.jpeg,.png'
        })
    )
    photo = forms.ImageField(
        label="Photo d'identité",
        validators=[FileExtensionValidator(['jpg', 'jpeg', 'png'])],
        widget=forms.ClearableFileInput(attrs={
            'class': FILE_CLASS, 'accept': '.jpg,.jpeg,.png'
        })
    )
    motivation_letter = forms.FileField(
        label="Lettre de motivation",
        validators=[FileExtensionValidator(['pdf', 'doc', 'docx'])],
        widget=forms.ClearableFileInput(attrs={
            'class': FILE_CLASS, 'accept': '.pdf,.doc,.docx'
        })
    )


class AttendanceForm(forms.Form):
    date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'p-2 border rounded'})
    )


class AccessEventForm(forms.ModelForm):
    class Meta:
        model = AccessEvent
        fields = ['person', 'visitor_label', 'event_type', 'reason']
        widgets = {
            'person': forms.Select(attrs={'class': 'w-full p-2 border rounded'}),
            'visitor_label': forms.TextInput(attrs={
                'class': 'w-full p-2 border rounded',
                'placeholder': 'Nom du visiteur (si pas inscrit)'
            }),
            'event_type': forms.Select(attrs={'class': 'w-full p-2 border rounded'}),
            'reason': forms.TextInput(attrs={
                'class': 'w-full p-2 border rounded',
                'placeholder': 'Motif (optionnel)'
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
                'placeholder': "Nom affiché dans l'interface",
            }),
            'phone': forms.TextInput(attrs={
                'class': INPUT_CLASS, 'placeholder': '+242 06 XXX XX XX'
            }),
            'address': forms.Textarea(attrs={'class': INPUT_CLASS, 'rows': 3}),
        }


class AvatarForm(forms.Form):
    avatar = forms.ImageField(
        label="Photo de profil",
        widget=forms.ClearableFileInput(attrs={'class': FILE_CLASS, 'accept': 'image/*'}),
    )

    def clean_avatar(self):
        image = self.cleaned_data['avatar']
        if image.size > 2 * 1024 * 1024:
            raise forms.ValidationError("L'image ne doit pas dépasser 2 Mo.")
        return image


class AccessRequestCompletionForm(forms.ModelForm):
    """Complète le profil et le rôle demandé d'un compte en attente (Clerk)."""

    requested_role = forms.ChoiceField(
        label="Rôle demandé",
        choices=[('', '-- Choisir un rôle --')] + REQUESTABLE_ROLE_CHOICES,
        widget=forms.Select(attrs={'class': INPUT_CLASS}),
        help_text="Votre demande sera examinée : aucun accès n'est accordé avant validation.",
    )

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'phone']
        widgets = {
            'first_name': forms.TextInput(attrs={
                'class': INPUT_CLASS, 'placeholder': 'Prénom'
            }),
            'last_name': forms.TextInput(attrs={
                'class': INPUT_CLASS, 'placeholder': 'Nom'
            }),
            'phone': forms.TextInput(attrs={
                'class': INPUT_CLASS, 'placeholder': '+242 06 XXX XX XX'
            }),
        }


class EmailChangeForm(forms.Form):
    new_email = forms.EmailField(
        label="Nouvelle adresse e-mail",
        widget=forms.EmailInput(attrs={'class': INPUT_CLASS}),
    )
    password = forms.CharField(
        label="Mot de passe actuel",
        widget=forms.PasswordInput(attrs={'class': INPUT_CLASS}),
    )

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_new_email(self):
        email = self.cleaned_data['new_email'].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Cette adresse est déjà utilisée.")
        return email

    def clean_password(self):
        password = self.cleaned_data['password']
        if self.user and not self.user.check_password(password):
            raise forms.ValidationError("Mot de passe incorrect.")
        return password


# ===========================================================================
# Accueil : visites et prospects
# ===========================================================================


class VisitForm(forms.ModelForm):
    first_name = forms.CharField(label="Prénom", max_length=100,
                                 widget=forms.TextInput(attrs={'class': INPUT_CLASS}))
    last_name = forms.CharField(label="Nom", max_length=100,
                                widget=forms.TextInput(attrs={'class': INPUT_CLASS}))
    phone = forms.CharField(label="Téléphone", max_length=30,
                            widget=forms.TextInput(attrs={
                                'class': INPUT_CLASS, 'placeholder': '+242 06 XXX XX XX'}))
    secondary_phone = forms.CharField(label="Téléphone secondaire", required=False,
                                      max_length=30,
                                      widget=forms.TextInput(attrs={'class': INPUT_CLASS}))
    email = forms.EmailField(label="Email", required=False,
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
                           "Le départ ne peut pas précéder l'arrivée.")
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
    first_name = forms.CharField(label="Prénom", max_length=100,
                                 widget=forms.TextInput(attrs={'class': INPUT_CLASS}))
    last_name = forms.CharField(label="Nom", max_length=100,
                                widget=forms.TextInput(attrs={'class': INPUT_CLASS}))
    phone = forms.CharField(label="Téléphone principal", max_length=30,
                            widget=forms.TextInput(attrs={'class': INPUT_CLASS}))
    secondary_phone = forms.CharField(label="Téléphone secondaire", required=False,
                                      max_length=30,
                                      widget=forms.TextInput(attrs={'class': INPUT_CLASS}))
    email = forms.EmailField(label="Email", required=False,
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
                'class': INPUT_CLASS, 'placeholder': 'Ex: janvier 2027'}),
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
        label="Mot de passe initial", required=False,
        help_text="Laisser vide pour créer un compte sans mot de passe (invitation).",
        widget=forms.PasswordInput(attrs={'class': INPUT_CLASS,
                                          'placeholder': 'Minimum 8 caractères'}),
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
            raise forms.ValidationError("Un compte utilise déjà cette adresse.")
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
            self.add_error('discount_amount', "La remise ne peut pas dépasser le tarif.")
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
        label="Formation / groupe",
        queryset=CourseSession.objects.none(),
        widget=forms.Select(attrs={'class': INPUT_CLASS}),
    )
    status = forms.ChoiceField(
        label="Statut de l'inscription",
        choices=Enrollment.Status.choices,
        initial=Enrollment.Status.ACTIVE,
        widget=forms.Select(attrs={'class': INPUT_CLASS}),
    )
    start_date = forms.DateField(
        label="Date de début",
        required=False,
        widget=forms.DateInput(attrs={'class': INPUT_CLASS, 'type': 'date'},
                               format='%Y-%m-%d'),
    )
    tariff_amount = forms.IntegerField(
        label="Frais de formation prévus (FCFA)",
        required=False, min_value=0,
        widget=forms.NumberInput(attrs={'class': INPUT_CLASS, 'min': 0}),
    )
    discount_amount = forms.IntegerField(
        label="Remise (FCFA)",
        required=False, min_value=0, initial=0,
        widget=forms.NumberInput(attrs={'class': INPUT_CLASS, 'min': 0}),
    )
    payment_plan = forms.CharField(
        label="Modalités de paiement",
        required=False,
        widget=forms.TextInput(attrs={
            'class': INPUT_CLASS,
            'placeholder': "Ex: 2 versements — 50 % à l'inscription",
        }),
    )
    notes = forms.CharField(
        label="Observations",
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
                           "La remise ne peut pas dépasser le tarif.")
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
            'course': 'Formation',
            'starts_at': 'Date de début',
            'ends_at': 'Date de fin',
            'schedule': 'Horaires',
            'capacity': 'Capacité',
            'status': 'Statut',
            'formateurs': 'Formateurs',
        }
        widgets = {
            'course': forms.Select(attrs={'class': INPUT_CLASS}),
            'starts_at': forms.DateInput(
                attrs={'class': INPUT_CLASS, 'type': 'date'}, format='%Y-%m-%d'),
            'ends_at': forms.DateInput(
                attrs={'class': INPUT_CLASS, 'type': 'date'}, format='%Y-%m-%d'),
            'schedule': forms.TextInput(
                attrs={'class': INPUT_CLASS, 'placeholder': 'Ex: Lun-Ven 13h-15h'}),
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
        self.fields['formateurs'].help_text = (
            "Maintenez Ctrl (ou Cmd) pour sélectionner plusieurs formateurs."
        )

    def clean(self):
        cleaned = super().clean()
        starts_at = cleaned.get('starts_at')
        ends_at = cleaned.get('ends_at')
        if starts_at and ends_at and ends_at < starts_at:
            self.add_error(
                'ends_at', "La date de fin doit suivre la date de début."
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
            self.add_error('planned_end', "L'heure de fin doit suivre le début.")
        a_start, a_end = cleaned.get('actual_start'), cleaned.get('actual_end')
        if a_start and a_end and a_end <= a_start:
            self.add_error('actual_end', "L'heure de fin doit suivre le début.")
        status = cleaned.get('status')
        if status == SessionRecord.Status.COMPLETED and not a_start:
            self.add_error('actual_start',
                           "Renseignez l'heure réelle de début pour une séance réalisée.")
        module = cleaned.get('module')
        lesson = cleaned.get('lesson')
        if module and lesson and lesson.module_id != module.id:
            self.add_error('lesson', "Cette leçon n'appartient pas au module choisi.")
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
            'date': 'Date',
            'planned_start': 'Heure de début',
            'planned_end': 'Heure de fin',
            'content_covered': 'Notions enseignées',
            'attendee_count': "Nombre d'apprenants",
            'notes': 'Observations',
            'status': 'Statut de la séance',
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
                       'placeholder': "Ex : les composants d'un ordinateur"},
            ),
            'attendee_count': forms.NumberInput(
                attrs={'class': INPUT_CLASS, 'min': 0}),
            'notes': forms.Textarea(
                attrs={'class': INPUT_CLASS, 'rows': 2,
                       'placeholder': 'Observations, matériel, incident…'},
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
            self.add_error('planned_end', "L'heure de fin doit suivre le début.")

        record_date = cleaned.get('date')
        if self.session and record_date and start:
            duplicates = SessionRecord.objects.filter(
                session=self.session, date=record_date, planned_start=start,
            )
            if self.instance and self.instance.pk:
                duplicates = duplicates.exclude(pk=self.instance.pk)
            if duplicates.exists():
                raise forms.ValidationError(
                    "Une séance est déjà enregistrée à cette date et à cette "
                    "heure pour ce groupe."
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
            'notions_learned': 'Notions retenues',
            'difficulties': 'Difficultés rencontrées',
            'observations': 'Observations',
            'attended': "J'étais présent à cette séance",
            'followed_start': 'Heure de début suivie',
            'followed_end': 'Heure de fin suivie',
        }
        widgets = {
            'notions_learned': forms.Textarea(
                attrs={'class': INPUT_CLASS, 'rows': 3,
                       'placeholder': "Ce que j'ai appris pendant cette séance"},
            ),
            'difficulties': forms.Textarea(
                attrs={'class': INPUT_CLASS, 'rows': 2,
                       'placeholder': "Ce que je n'ai pas compris"},
            ),
            'observations': forms.Textarea(
                attrs={'class': INPUT_CLASS, 'rows': 2,
                       'placeholder': 'Remarque, question pour le formateur…'},
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
                "L'heure de fin suivie doit être après l'heure de début."
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
                "Joignez un fichier ou saisissez un contenu HTML."
            )
        if file and file.size > 10 * 1024 * 1024:
            self.add_error('file', "Le fichier ne doit pas dépasser 10 Mo.")
        module = cleaned.get('module')
        lesson = cleaned.get('lesson')
        if module and lesson and lesson.module_id != module.id:
            self.add_error('lesson', "Cette leçon n'appartient pas au module choisi.")
        return cleaned


# ===========================================================================
# Comptabilité
# ===========================================================================


class CashTransactionForm(forms.ModelForm):
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['account'].queryset = CashAccount.objects.filter(active=True)
        self.fields['destination_account'].queryset = CashAccount.objects.filter(active=True)
        self.fields['occurred_at'].input_formats = ['%Y-%m-%dT%H:%M']
        tx_type = self.data.get('tx_type') or getattr(self.instance, 'tx_type', None)
        categories = TransactionCategory.objects.filter(active=True)
        if tx_type:
            categories = categories.filter(direction=tx_type)
        self.fields['category'].queryset = categories
        self.fields['destination_account'].required = False

    def clean(self):
        cleaned = super().clean()
        tx_type = cleaned.get('tx_type')
        account = cleaned.get('account')
        destination = cleaned.get('destination_account')
        category = cleaned.get('category')
        if tx_type == CashTransaction.Type.TRANSFER:
            if not destination:
                self.add_error('destination_account',
                               "Choisissez le compte destinataire.")
            elif destination == account:
                self.add_error('destination_account',
                               "Le compte destinataire doit être différent.")
        elif destination:
            cleaned['destination_account'] = None
        if category and tx_type and category.direction != tx_type:
            self.add_error('category', "Cette catégorie ne correspond pas au type.")
        return cleaned


class CashAccountForm(forms.ModelForm):
    class Meta:
        model = CashAccount
        fields = ['name', 'kind', 'currency', 'opening_balance', 'active']
        widgets = {
            'name': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'kind': forms.Select(attrs={'class': INPUT_CLASS}),
            'currency': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'opening_balance': forms.NumberInput(attrs={'class': INPUT_CLASS}),
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


class StudentPaymentForm(forms.Form):
    enrollment = forms.ModelChoiceField(
        label="Inscription",
        queryset=Enrollment.objects.none(),
        widget=forms.Select(attrs={'class': INPUT_CLASS}),
    )
    amount = forms.IntegerField(
        label="Montant encaissé",
        min_value=1,
        widget=forms.NumberInput(attrs={'class': INPUT_CLASS, 'min': 1}),
    )
    method = forms.ChoiceField(
        label="Moyen de paiement",
        choices=Payment.Method.choices,
        widget=forms.Select(attrs={'class': INPUT_CLASS}),
    )
    account = forms.ModelChoiceField(
        label="Caisse / compte destinataire",
        queryset=CashAccount.objects.none(),
        widget=forms.Select(attrs={'class': INPUT_CLASS}),
    )
    paid_at = forms.DateTimeField(
        label="Date et heure du paiement",
        widget=forms.DateTimeInput(
            attrs={'class': INPUT_CLASS, 'type': 'datetime-local'},
            format='%Y-%m-%dT%H:%M'),
    )
    note = forms.CharField(
        label="Observations", required=False,
        widget=forms.Textarea(attrs={'class': INPUT_CLASS, 'rows': 2}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['enrollment'].queryset = (
            Enrollment.objects.select_related('student', 'session__course')
            .exclude(status=Enrollment.Status.CANCELLED)
            .order_by('student__last_name')
        )
        self.fields['account'].queryset = CashAccount.objects.filter(active=True)
        self.fields['paid_at'].input_formats = ['%Y-%m-%dT%H:%M']

    def clean(self):
        cleaned = super().clean()
        enrollment = cleaned.get('enrollment')
        amount = cleaned.get('amount') or 0
        if enrollment and enrollment.net_amount:
            if amount > enrollment.balance_due:
                self.add_error(
                    'amount',
                    f"Le montant dépasse le reste à payer "
                    f"({enrollment.balance_due} FCFA)."
                )
        return cleaned

