from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from core.utils import paginate

from .decorators import admin_required
from .forms import AdminSetPasswordForm, OwnPasswordChangeForm, UserCreateForm, UserEditForm
from .models import User


@admin_required
def user_list(request):
    users = User.objects.all()
    q = request.GET.get('q', '').strip()
    role = request.GET.get('role', '')
    status = request.GET.get('status', '')
    if q:
        users = users.filter(
            Q(username__icontains=q) | Q(first_name__icontains=q)
            | Q(last_name__icontains=q) | Q(email__icontains=q)
        )
    if role in User.Role.values:
        users = users.filter(role=role)
    if status == 'active':
        users = users.filter(is_active=True)
    elif status == 'inactive':
        users = users.filter(is_active=False)
    return render(request, 'accounts/user_list.html', {
        'page': paginate(request, users),
        'roles': User.Role.choices,
        'q': q, 'role': role, 'status': status,
    })


@admin_required
def user_create(request):
    form = UserCreateForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        messages.success(request, f'Account for {user} created.')
        return redirect('accounts:user_list')
    return render(request, 'form_page.html', {
        'form': form,
        'title': 'Add user',
        'subtitle': 'Create an account and assign a role.',
        'back_url': reverse('accounts:user_list'),
        'submit_label': 'Create account',
    })


@admin_required
def user_edit(request, pk):
    user = get_object_or_404(User, pk=pk)
    form = UserEditForm(request.POST or None, instance=user, editor=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, f'Account for {user} updated.')
        return redirect('accounts:user_list')
    return render(request, 'form_page.html', {
        'form': form,
        'title': f'Edit {user}',
        'subtitle': f'Username: {user.username}',
        'back_url': reverse('accounts:user_list'),
        'submit_label': 'Save changes',
    })


@admin_required
@require_POST
def user_toggle_active(request, pk):
    user = get_object_or_404(User, pk=pk)
    if user.pk == request.user.pk:
        messages.error(request, 'You cannot deactivate your own account.')
    else:
        user.is_active = not user.is_active
        user.save(update_fields=['is_active'])
        state = 'activated' if user.is_active else 'deactivated'
        messages.success(request, f'Account for {user} {state}.')
    return redirect('accounts:user_list')


@admin_required
def user_reset_password(request, pk):
    user = get_object_or_404(User, pk=pk)
    form = AdminSetPasswordForm(user, request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, f'Password for {user} has been reset. Give the new password to the user directly.')
        return redirect('accounts:user_list')
    return render(request, 'form_page.html', {
        'form': form,
        'title': f'Reset password for {user}',
        'subtitle': 'Set a temporary password. Ask the user to change it after signing in.',
        'back_url': reverse('accounts:user_list'),
        'submit_label': 'Reset password',
    })


@login_required
def password_change(request):
    form = OwnPasswordChangeForm(request.user, request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        update_session_auth_hash(request, user)
        messages.success(request, 'Your password has been changed.')
        return redirect('core:dashboard')
    return render(request, 'form_page.html', {
        'form': form,
        'title': 'Change password',
        'back_url': reverse('core:dashboard'),
        'submit_label': 'Change password',
    })
