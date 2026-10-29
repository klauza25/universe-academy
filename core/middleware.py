from django.shortcuts import redirect
from .models import AccountStatus

PUBLIC_PATHS = [
    '/',
    '/login/',
    '/logout/',
    '/register/',
    '/demande-acces/',
    '/bourses/',
    '/bourses/candidature/',
    '/bourses/suivi/',
    '/pending-approval/',
    '/access-denied/',
    '/clerk/',
]


class AccountStatusMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and not request.user.is_superuser:
            path = request.path

            is_public = False
            for p in PUBLIC_PATHS:
                if p == '/':
                    if path == '/':
                        is_public = True
                        break
                elif path.startswith(p):
                    is_public = True
                    break

            is_static = path.startswith('/static/') or path.startswith('/media/')
            is_admin = path.startswith('/admin/')
            is_documents = path.startswith('/documents/')

            if not is_public and not is_static and not is_admin and not is_documents:
                if request.user.account_status == AccountStatus.PENDING_APPROVAL:
                    return redirect('core:pending-approval')
                elif request.user.account_status in (
                    AccountStatus.SUSPENDED,
                    AccountStatus.DISABLED,
                    AccountStatus.REJECTED
                ):
                    return redirect('core:access-denied')

        return self.get_response(request)
