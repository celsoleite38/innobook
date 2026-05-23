from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import User
from .forms import LoginForm, RegisterForm, ProfileForm

from apps.products.models import Ebook
from apps.products.forms import EbookForm
from apps.payments.models import Order
from django.db.models import Sum, Count

@login_required
def producer_dashboard_view(request):
    if not request.user.is_producer():
        messages.error(request, 'Acesso restrito a produtores.')
        return redirect('accounts:dashboard')

    ebooks = request.user.ebooks.all().order_by('-created_at')

    # Estatísticas de vendas
    stats = Order.objects.filter(
        ebook__author=request.user,
        status='paid'
    ).aggregate(
        total_orders  = Count('id'),
        total_revenue = Sum('producer_amount'),
    )

    # Vendas por eBook
    sales_per_ebook = Order.objects.filter(
        ebook__author=request.user,
        status='paid'
    ).values(
        'ebook__title'
    ).annotate(
        total=Count('id'),
        revenue=Sum('producer_amount')
    ).order_by('-total')

    return render(request, 'accounts/producer_dashboard.html', {
        'ebooks'          : ebooks,
        'stats'           : stats,
        'sales_per_ebook' : sales_per_ebook,
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