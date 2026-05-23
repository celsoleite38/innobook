from django import forms
from django.contrib.auth.password_validation import validate_password
from .models import User


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
    role = forms.ChoiceField(
        label='Tipo de conta',
        choices=User.ROLE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model  = User
        fields = ['first_name', 'last_name', 'username', 'cpf', 'email', 'role']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'João'}),
            'last_name' : forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Silva'}),
            'username'  : forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'joaosilva'}),
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

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError('Este email já está cadastrado.')
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        user.email    = self.cleaned_data['email']
        user.username = self.cleaned_data['username']
        if commit:
            user.save()
        return user


class ProfileForm(forms.ModelForm):
    class Meta:
        model  = User
        fields = ['first_name', 'last_name', 'email', 'cpf', 'bio', 'avatar']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name' : forms.TextInput(attrs={'class': 'form-control'}),
            'email'     : forms.EmailInput(attrs={'class': 'form-control'}),
            'cpf'       : forms.TextInput(attrs={'class': 'form-control'}),
            'bio'       : forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'avatar'    : forms.FileInput(attrs={'class': 'form-control'}),
        }