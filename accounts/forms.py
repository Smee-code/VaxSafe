from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm, SetPasswordForm, UserCreationForm

from core.forms import StyledFormMixin

from .models import User


class LoginForm(StyledFormMixin, AuthenticationForm):
    pass


class UserCreateForm(StyledFormMixin, UserCreationForm):
    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'role', 'position', 'contact_number']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['first_name'].required = True
        self.fields['last_name'].required = True


class UserEditForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'role', 'position', 'contact_number', 'is_active']
        labels = {'is_active': 'Account is active'}

    def __init__(self, *args, editor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['first_name'].required = True
        self.fields['last_name'].required = True
        # Stop an administrator from locking themselves out.
        if editor is not None and editor.pk == self.instance.pk:
            self.fields['role'].disabled = True
            self.fields['is_active'].disabled = True
            self.fields['role'].help_text = 'You cannot change your own role.'


class AdminSetPasswordForm(StyledFormMixin, SetPasswordForm):
    pass


class OwnPasswordChangeForm(StyledFormMixin, PasswordChangeForm):
    pass
