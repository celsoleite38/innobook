from django import forms
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.forms import PasswordResetForm as _PasswordResetForm

from .models import User
from .validators import cpf_somente_digitos


class PasswordResetForm(_PasswordResetForm):
    """Busca o usuário pelo campo EMAIL (o sistema loga por e-mail)."""

    def get_users(self, email):
        return User.objects.filter(email__iexact=email, is_active=True)


class LoginForm(forms.Form):
    email = forms.EmailField(
        label='Email',
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'seu@email.com',
            'autofocus': True,
        })
    )
    password = forms.CharField(
        label='Senha',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': '••••••••',
        })
    )


class RegisterForm(forms.ModelForm):
    password1 = forms.CharField(
        label='Senha',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': '••••••••',
        }),
        validators=[validate_password]
    )
    password2 = forms.CharField(
        label='Confirme a senha',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': '••••••••',
        })
    )

    class Meta:
        model  = User
        fields = ['first_name', 'last_name', 'cpf', 'email']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'João'}),
            'last_name' : forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Silva'}),
            'cpf'       : forms.TextInput(attrs={'class': 'form-control', 'placeholder': '000.000.000-00'}),
            'email'     : forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'seu@email.com'}),
        }

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get('password1')
        p2 = cleaned.get('password2')
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError('As senhas não coincidem.')
        return cleaned

    def clean_cpf(self):
        cpf = self.cleaned_data.get('cpf') or ''
        return cpf_somente_digitos(cpf) or None

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError('Este email já está cadastrado.')
        return email

    @staticmethod
    def _gerar_username(email):
        """Gera username único a partir do e-mail (ex.: joao.silva@gmail.com -> joao.silva)."""
        import re
        from django.utils.text import slugify
        base = slugify(email.split('@')[0]).replace('-', '_')[:150] or 'usuario'
        username = base
        sufixo = 1
        while User.objects.filter(username=username).exists():
            username = f'{base[:140]}_{sufixo}'
            sufixo += 1
        return username

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        user.email    = self.cleaned_data['email']
        user.username = self._gerar_username(self.cleaned_data['email'])
        user.role     = User.BUYER  # todo mundo nasce comprador; produtor requer aprovação
        user.email_verified = False
        if commit:
            user.save()
        return user


class ProfileForm(forms.ModelForm):
    class Meta:
        model  = User
        fields = ['first_name', 'last_name', 'email', 'cpf', 'bio', 'avatar', 'two_factor_enabled']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name' : forms.TextInput(attrs={'class': 'form-control'}),
            'email'     : forms.EmailInput(attrs={'class': 'form-control'}),
            'cpf'       : forms.TextInput(attrs={'class': 'form-control'}),
            'bio'       : forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'avatar'    : forms.FileInput(attrs={'class': 'form-control'}),
            'two_factor_enabled': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean_cpf(self):
        cpf = self.cleaned_data.get('cpf') or ''
        return cpf_somente_digitos(cpf) or None
