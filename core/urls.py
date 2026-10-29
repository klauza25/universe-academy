from django.urls import path, include

from . import (
    views, views_accueil, views_comptabilite, views_pedagogie,
    views_profile, views_secretariat, views_supervision,
)

app_name = 'core'

public_urlpatterns = [
    path('', views.home, name='home'),
    path('login/', views.login_view, name='login'),
    path('clerk/session/', views.clerk_session, name='clerk-session'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register_view, name='register'),
    path('demande-acces/', views.complete_access_request,
         name='complete-access-request'),
    path('pending-approval/', views.pending_approval, name='pending-approval'),
    path('access-denied/', views.access_denied, name='access-denied'),
]

bourses_urlpatterns = [
    path('candidature/', views.scholarship_apply, name='scholarship-apply'),
    path('confirmation/<str:reference>/', views.scholarship_confirmation, name='scholarship-confirmation'),
    path('suivi/', views.scholarship_tracking, name='scholarship-tracking'),
]

dashboard_urlpatterns = [
    path('', views.dashboard_router, name='dashboard-router'),

    # Profil -----------------------------------------------------------------
    path('profil/', views_profile.profile_view, name='profile'),
    path('profil/email/<str:token>/', views_profile.profile_email_confirm,
         name='profile-email-confirm'),

    # Super administrateur ---------------------------------------------------
    path('super-admin/', views.super_admin_dashboard, name='super-admin-dashboard'),
    path('super-admin/users/', views.user_list, name='user-list'),
    path('super-admin/users/create/', views.user_create, name='user-create'),
    path('super-admin/users/<uuid:user_id>/', views.user_detail, name='user-detail'),
    path('super-admin/users/<uuid:user_id>/edit/', views.user_edit, name='user-edit'),
    path('super-admin/users/<uuid:user_id>/roles/', views.user_role_assign, name='user-role-assign'),
    path('super-admin/users/<uuid:user_id>/status/', views.user_status_change, name='user-status-change'),
    path('super-admin/access-requests/', views.access_requests_list, name='access-requests'),
    path('super-admin/access-requests/<uuid:request_id>/', views.access_request_review, name='access-request-review'),
    path('super-admin/audit/', views.audit_log_view, name='audit-log'),
    path('super-admin/finances/', views_supervision.finance_supervision,
         name='finance-supervision'),
    path('super-admin/scholarships/', views.scholarship_review_list, name='scholarship-review-list'),
    path('super-admin/scholarships/<uuid:app_id>/', views.scholarship_review_detail, name='scholarship-review-detail'),
    path('admin/', views.admin_dashboard, name='admin-dashboard'),
    path('direction/', views.direction_dashboard, name='direction-dashboard'),

    # Accueil ----------------------------------------------------------------
    path('accueil/', views.accueil_dashboard, name='accueil-dashboard'),
    path('accueil/visites/', views_accueil.visit_list, name='visit-list'),
    path('accueil/visites/nouvelle/', views_accueil.visit_create, name='visit-create'),
    path('accueil/visites/<uuid:visit_id>/', views_accueil.visit_detail, name='visit-detail'),
    path('accueil/visites/<uuid:visit_id>/depart/', views_accueil.visit_departure, name='visit-departure'),
    path('accueil/visites/<uuid:visit_id>/prospect/', views_accueil.visit_to_prospect, name='visit-to-prospect'),
    path('accueil/prospects/', views_accueil.prospect_list, name='prospect-list'),
    path('accueil/prospects/nouveau/', views_accueil.prospect_create, name='prospect-create'),
    path('accueil/prospects/<uuid:prospect_id>/', views_accueil.prospect_detail, name='prospect-detail'),
    path('accueil/motifs/', views_accueil.visit_reason_list, name='visit-reasons'),
    path('accueil/motifs/<uuid:reason_id>/toggle/', views_accueil.visit_reason_toggle, name='visit-reason-toggle'),
    path('accueil/contacts/recherche/', views_accueil.contact_search, name='contact-search'),

    # Secrétariat ------------------------------------------------------------
    path('secretaire/', views.secretaire_dashboard, name='secretaire-dashboard'),
    path('secretaire/etudiants/', views_secretariat.student_list, name='student-list'),
    path('secretaire/etudiants/nouveau/', views_secretariat.student_create, name='student-create'),
    path('secretaire/etudiants/<uuid:student_id>/', views_secretariat.student_detail, name='student-detail'),
    path('secretaire/etudiants/<uuid:student_id>/modifier/', views_secretariat.student_edit, name='student-edit'),
    path('secretaire/etudiants/<uuid:student_id>/documents/', views_secretariat.student_document_upload, name='student-document-upload'),
    path('secretaire/documents/<uuid:doc_id>/', views_secretariat.student_document_download, name='student-document-download'),
    path('secretaire/inscriptions/nouvelle/', views_secretariat.enrollment_create, name='enrollment-create'),
    path('secretaire/inscriptions/<uuid:enrollment_id>/', views_secretariat.enrollment_detail, name='enrollment-detail'),
    path('secretaire/inscriptions/<uuid:enrollment_id>/modifier/', views_secretariat.enrollment_edit, name='enrollment-edit'),

    # Pédagogie --------------------------------------------------------------
    path('pedagogie/programmes/', views_pedagogie.program_list, name='programs'),
    path('pedagogie/modules/nouveau/', views_pedagogie.module_create, name='module-create'),
    path('pedagogie/modules/<uuid:module_id>/modifier/', views_pedagogie.module_edit, name='module-edit'),
    path('pedagogie/lecons/nouvelle/', views_pedagogie.lesson_create, name='lesson-create'),
    path('pedagogie/lecons/<uuid:lesson_id>/modifier/', views_pedagogie.lesson_edit, name='lesson-edit'),
    path('pedagogie/seances/', views_pedagogie.session_record_list, name='session-records'),
    path('pedagogie/seances/nouvelle/<uuid:session_id>/', views_pedagogie.session_record_create, name='session-record-create'),
    path('pedagogie/seances/<uuid:record_id>/', views_pedagogie.session_record_detail, name='session-record-detail'),
    path('pedagogie/seances/<uuid:record_id>/presences/', views_pedagogie.attendance_sheet, name='session-record-attendance'),
    path('pedagogie/presences/', views_pedagogie.attendance_history, name='attendance-history'),
    path('pedagogie/progression/', views_pedagogie.progression_overview, name='progression'),
    path('pedagogie/ressources/', views_pedagogie.resource_list, name='resources'),
    path('pedagogie/ressources/nouvelle/', views_pedagogie.resource_create, name='resource-create'),
    path('pedagogie/ressources/<uuid:resource_id>/modifier/', views_pedagogie.resource_edit, name='resource-edit'),
    path('pedagogie/ressources/<uuid:resource_id>/telecharger/', views_pedagogie.resource_download, name='resource-download'),
    path('pedagogie/ressources/<uuid:resource_id>/voir/', views_pedagogie.resource_view, name='resource-view'),

    # Comptabilité -----------------------------------------------------------
    path('comptabilite/', views.comptabilite_dashboard, name='comptabilite-dashboard'),
    path('comptabilite/journal/', views_comptabilite.journal, name='journal'),
    path('comptabilite/operations/nouvelle/', views_comptabilite.transaction_create, name='transaction-create'),
    path('comptabilite/operations/<uuid:tx_id>/', views_comptabilite.transaction_detail, name='transaction-detail'),
    path('comptabilite/caisses/', views_comptabilite.account_list, name='accounts'),
    path('comptabilite/clotures/', views_comptabilite.closure_list, name='closures'),
    path('comptabilite/clotures/nouvelle/', views_comptabilite.closure_create, name='closure-create'),
    path('comptabilite/paiement/', views_comptabilite.student_payment_create, name='payment-create'),
    path('comptabilite/recu/<uuid:payment_id>/', views_comptabilite.payment_receipt, name='payment-receipt'),

    # Responsable pédagogique / formateur / étudiant -------------------------
    path('responsable-pedagogique/', views.responsable_pedagogique_dashboard, name='resp-peda-dashboard'),
    path('formateur/', views.formateur_dashboard, name='formateur-dashboard'),
    path('formateur/session/<uuid:session_id>/attendance/', views.formateur_attendance, name='formateur-attendance'),
    path('etudiant/', views.etudiant_dashboard, name='etudiant-dashboard'),
    path('etudiant/ressources/', views_pedagogie.student_resources, name='student-resources'),
    path('etudiant/presences/', views_pedagogie.student_attendance, name='student-attendance'),
]

urlpatterns = [
    *public_urlpatterns,
    path('bourses/', include((bourses_urlpatterns, 'bourses'))),
    path('dashboard/', include((dashboard_urlpatterns, 'dashboard'))),
    path('documents/<uuid:doc_id>/', views.serve_private_file, name='serve-private-file'),
    path('media/avatars/<path:path>', views_profile.serve_avatar, name='avatar'),
]
