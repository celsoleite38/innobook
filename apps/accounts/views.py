from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import User
from .forms import LoginForm, RegisterForm, ProfileForm

from apps.products.models import Ebook, EbookBonus
from apps.products.forms import EbookForm, EbookBonusForm
from apps.payments.models import Order, WithdrawRequest, PlatformConfig
from django.db.models import Sum, Count
from apps.payments.forms import BankDataForm, WithdrawForm
from apps.payments.finance import get_producer_financial, get_producer_sales_by_ebook



@login_required
def producer_dashboard_view(request):
    if not request.user.is_producer():
        messages.error(request, 'Acesso restrito a produtores.')
        return redirect('accounts:dashboard')

    from apps.payments.finance import get_producer_financial
    ebooks    = request.user.ebooks.all().order_by('-created_at')
    financial = get_producer_financial(request.user)

    sales_per_ebook = Order.objects.filter(
        ebook__author=request.user,
        status='paid'
    ).values('ebook__title').annotate(
        total=Count('id'),
        revenue=Sum('producer_amount')
    ).order_by('-total')

    return render(request, 'accounts/producer_dashboard.html', {
        'ebooks'         : ebooks,
        'financial'      : financial,
        'sales_per_ebook': sales_per_ebook,
    })


@login_required
def ebook_create_view(request):
    if not request.user.is_producer():
        return redirect('accounts:dashboard')

    form = EbookForm(request.POST or None, request.FILES or None)
    if request.method == 'POST':
        if form.is_valid():
            ebook        = form.save(commit=False)
            ebook.author = request.user
            ebook.status = Ebook.STATUS_PENDING  # aguarda aprovação do admin
            ebook.save()
            messages.success(request, 'eBook enviado para aprovação!')
            return redirect('accounts:producer')

    return render(request, 'accounts/ebook_form.html', {
        'form' : form,
        'title': 'Novo eBook',
    })


@login_required
def ebook_edit_view(request, pk):
    ebook = get_object_or_404(Ebook, pk=pk, author=request.user)
    form  = EbookForm(
        request.POST  or None,
        request.FILES or None,
        instance=ebook
    )
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            messages.success(request, 'eBook atualizado!')
            return redirect('accounts:producer')

    return render(request, 'accounts/ebook_form.html', {
        'form' : form,
        'title': f'Editar — {ebook.title}',
        'ebook': ebook,
    })


def login_view(request):
    if request.user.is_authenticated:
        return redirect('accounts:dashboard')

    form = LoginForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            email    = form.cleaned_data['email']
            password = form.cleaned_data['password']
            user     = authenticate(request, username=email, password=password)
            if user:
                login(request, user)
                messages.success(request, f'Bem-vindo de volta, {user.first_name or user.username}!')
                return redirect(request.GET.get('next', 'accounts:dashboard'))
            else:
                messages.error(request, 'Email ou senha incorretos.')

    return render(request, 'accounts/login.html', {'form': form})


def logout_view(request):
    logout(request)
    messages.info(request, 'Você saiu da sua conta.')
    return redirect('products:home')


def register_view(request):
    if request.user.is_authenticated:
        return redirect('accounts:dashboard')

    form = RegisterForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, 'Conta criada com sucesso! Bem-vindo ao BookHub!')
            return redirect('accounts:dashboard')

    return render(request, 'accounts/register.html', {'form': form})


@login_required
def dashboard_view(request):
    user = request.user

    # Compras do usuário
    orders = user.orders.filter(status='paid').select_related('ebook')

    # Se for produtor, mostra os próprios ebooks
    my_ebooks = None
    if user.is_producer():
        my_ebooks = user.ebooks.all().order_by('-created_at')

    context = {
        'orders'   : orders,
        'my_ebooks': my_ebooks,
    }
    return render(request, 'accounts/dashboard.html', context)


@login_required
def profile_view(request):
    form = ProfileForm(request.POST or None, request.FILES or None, instance=request.user)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            messages.success(request, 'Perfil atualizado com sucesso!')
            return redirect('accounts:profile')

    return render(request, 'accounts/profile.html', {'form': form})



@login_required
def bonus_create_view(request, ebook_pk):
    ebook = get_object_or_404(Ebook, pk=ebook_pk, author=request.user)
    form  = EbookBonusForm(request.POST or None, request.FILES or None)

    if request.method == 'POST':
        if form.is_valid():
            bonus       = form.save(commit=False)
            bonus.ebook = ebook
            bonus.save()
            messages.success(request, f'Bônus "{bonus.title}" adicionado!')
            return redirect('accounts:ebook_bonuses', pk=ebook_pk)

    return render(request, 'accounts/bonus_form.html', {
        'form' : form,
        'ebook': ebook,
        'title': 'Novo Bônus',
    })


@login_required
def bonus_list_view(request, pk):
    ebook   = get_object_or_404(Ebook, pk=pk, author=request.user)
    bonuses = ebook.bonuses.all()
    return render(request, 'accounts/bonus_list.html', {
        'ebook'  : ebook,
        'bonuses': bonuses,
    })


@login_required
def bonus_delete_view(request, pk):
    bonus = get_object_or_404(EbookBonus, pk=pk, ebook__author=request.user)
    ebook_pk = bonus.ebook.pk
    bonus.delete()
    messages.success(request, 'Bônus removido.')
    return redirect('accounts:ebook_bonuses', pk=ebook_pk)





@login_required
def financial_view(request):
    """Painel financeiro completo do produtor."""
    if not request.user.is_producer():
        return redirect('accounts:dashboard')

    financial  = get_producer_financial(request.user)
    sales      = get_producer_sales_by_ebook(request.user)
    withdraws  = request.user.withdraw_requests.all().order_by('-created_at')[:10]

    # Form de dados bancários
    try:
        bank_data = request.user.bank_data
    except Exception:
        bank_data = None

    bank_form = BankDataForm(
        request.POST or None,
        instance=bank_data
    )

    if request.method == 'POST' and 'save_bank' in request.POST:
        if bank_form.is_valid():
            bd          = bank_form.save(commit=False)
            bd.producer = request.user
            bd.save()
            messages.success(request, 'Dados PIX salvos com sucesso!')
            return redirect('accounts:financial')

    return render(request, 'accounts/financial.html', {
        'financial' : financial,
        'sales'     : sales,
        'withdraws' : withdraws,
        'bank_form' : bank_form,
        'bank_data' : bank_data,
    })


@login_required
def withdraw_request_view(request):
    """Solicitar saque."""
    if not request.user.is_producer():
        return redirect('accounts:dashboard')

    financial = get_producer_financial(request.user)

    if not financial['can_withdraw']:
        messages.warning(
            request,
            f'Saldo insuficiente. Mínimo para saque: R$ {financial["min_withdraw"]}'
        )
        return redirect('accounts:financial')

    try:
        bank_data = request.user.bank_data
    except Exception:
        messages.warning(request, 'Cadastre sua chave PIX antes de solicitar um saque.')
        return redirect('accounts:financial')

    form = WithdrawForm(request.POST or None)

    if request.method == 'POST':
        if form.is_valid():
            amount = form.cleaned_data['amount']

            if amount > financial['available']:
                messages.error(request, f'Valor maior que o saldo disponível (R$ {financial["available"]}).')
                return redirect('accounts:withdraw')

            if amount < financial['min_withdraw']:
                messages.error(request, f'Valor mínimo para saque é R$ {financial["min_withdraw"]}.')
                return redirect('accounts:withdraw')

            WithdrawRequest.objects.create(
                producer = request.user,
                amount   = amount,
                pix_key  = bank_data.pix_key,
                pix_type = bank_data.pix_type,
                pix_holder= bank_data.full_name,
                status   = WithdrawRequest.STATUS_PENDING,
            )
            messages.success(
                request,
                f'Saque de R$ {amount} solicitado! '
                f'Você receberá em sua chave PIX em até 5 dias úteis.'
            )
            return redirect('accounts:financial')

    return render(request, 'accounts/withdraw.html', {
        'form'     : form,
        'financial': financial,
        'bank_data': bank_data,
    })