from functools import wraps

from django.contrib import messages
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.tokens import default_token_generator
from django.conf import settings
from django.shortcuts import get_object_or_404, render, redirect
from django.utils.encoding import force_str
from django.utils.html import format_html
from django.utils.http import urlsafe_base64_decode, url_has_allowed_host_and_scheme
from django.urls import reverse
from django.core.paginator import Paginator

from .models import User
from .forms import LoginForm, RegisterForm, ProfileForm
from .security import (
    reset_login_failures,
    record_login_failure,
    requires_two_factor,
    start_two_factor_login,
    send_fresh_otp,
    send_verification_email,
    send_rejection_email,
    verify_otp,
    otp_is_locked,
    record_otp_failure,
    otp_can_resend,
)

from apps.products.models import Ebook, EbookBonus
from apps.products.forms import EbookForm, EbookBonusForm
from apps.payments.models import Order, WithdrawRequest, PlatformConfig
from django.db.models import Sum, Count, Q
from apps.payments.forms import BankDataForm, WithdrawForm
from apps.payments.finance import get_producer_financial, get_producer_sales_by_ebook


def _safe_next(request):
    """Próxima URL segura (evita open redirect)."""
    next_url = (
        request.POST.get('next')
        or request.GET.get('next')
        or 'accounts:dashboard'
    )
    if url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return next_url
    return 'accounts:dashboard'


def producer_required(view_func):
    """Acesso ao painel de produtor exige: role producer + e-mail verificado + aprovação."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            return redirect(settings.LOGIN_URL + '?next=' + request.path)
        if not user.is_producer():
            messages.error(request, 'Acesso restrito a produtores.')
            return redirect('accounts:dashboard')
        if not user.email_verified:
            messages.warning(
                request,
                'Verifique seu e-mail antes de acessar o painel do escritor.'
            )
            return redirect('accounts:profile')
        if not user.producer_approved:
            messages.warning(
                request,
                'Seu acesso de produtor ainda não foi aprovado pela administração.'
            )
            return redirect('accounts:dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper


@login_required
@producer_required
def producer_dashboard_view(request):
    from apps.payments.finance import get_producer_financial
    config     = PlatformConfig.get()
    ebooks     = request.user.ebooks.all().order_by('-created_at')
    financial  = get_producer_financial(request.user)

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
        'terms_enabled'  : config.terms_enabled,
    })


@login_required
@producer_required
def ebook_create_view(request):
    config = PlatformConfig.get()
    if config.terms_enabled and not request.user.terms_accepted:
        messages.warning(request, format_html(
            'Você precisa aceitar os <a href="{}" class="fw-bold">Termos da Loja</a> antes de publicar.',
            reverse('accounts:profile') + '#aceitar-termos'
        ))
        return redirect(reverse('accounts:profile') + '#aceitar-termos')

    form = EbookForm(request.POST or None, request.FILES or None)
    if request.method == 'POST':
        if form.is_valid():
            ebook        = form.save(commit=False)
            ebook.author = request.user
            if config.terms_enabled and request.user.terms_accepted:
                ebook.status = Ebook.STATUS_PUBLISHED
            else:
                ebook.status = Ebook.STATUS_PENDING
            ebook.save()
            if ebook.status == Ebook.STATUS_PUBLISHED:
                messages.success(request, 'eBook publicado com sucesso!')
            else:
                messages.success(request, 'eBook enviado para aprovação!')
            return redirect('accounts:producer')

    return render(request, 'accounts/ebook_form.html', {
        'form' : form,
        'title': 'Novo eBook',
    })


@login_required
@producer_required
def ebook_edit_view(request, pk):
    config = PlatformConfig.get()
    if config.terms_enabled and not request.user.terms_accepted:
        messages.warning(request, format_html(
            'Você precisa aceitar os <a href="{}" class="fw-bold">Termos da Loja</a> antes de editar.',
            reverse('accounts:profile') + '#aceitar-termos'
        ))
        return redirect(reverse('accounts:profile') + '#aceitar-termos')

    ebook = get_object_or_404(Ebook, pk=pk, author=request.user)
    form  = EbookForm(
        request.POST  or None,
        request.FILES or None,
        instance=ebook
    )
    if request.method == 'POST':
        if form.is_valid():
            ebook = form.save(commit=False)
            if ebook.status == Ebook.STATUS_REJECTED:
                # Reenvio após correção: volta para aprovação (nunca
                # auto-publica um livro que foi rejeitado pela equipe).
                ebook.status = Ebook.STATUS_PENDING
                ebook.rejection_reason = ''
                ebook.save()
                messages.success(
                    request,
                    'eBook atualizado e reenviado para aprovação! '
                    'Você será notificado após a revisão.'
                )
            else:
                if config.terms_enabled and request.user.terms_accepted:
                    ebook.status = Ebook.STATUS_PUBLISHED
                ebook.save()
                messages.success(request, 'eBook atualizado!')
            return redirect('accounts:producer')

    return render(request, 'accounts/ebook_form.html', {
        'form' : form,
        'title': f'Editar — {ebook.title}',
        'ebook': ebook,
    })


@login_required
@producer_required
def producer_book_publish_view(request, pk):
    """Escritor publica diretamente seu ebook (se termos aceitos)."""
    config = PlatformConfig.get()
    if not (config.terms_enabled and request.user.terms_accepted):
        messages.error(request, 'Você não tem permissão para publicar.')
        return redirect('accounts:producer')

    ebook = get_object_or_404(Ebook, pk=pk, author=request.user)
    if ebook.status == Ebook.STATUS_REJECTED:
        messages.error(
            request,
            'Este eBook foi rejeitado pela equipe. Edite-o para corrigir as '
            'pendências e reenvie — ele voltará para aprovação.'
        )
        return redirect('accounts:ebook_edit', pk=ebook.pk)
    ebook.status = Ebook.STATUS_PUBLISHED
    ebook.rejection_reason = ''
    ebook.save(update_fields=['status', 'rejection_reason'])
    messages.success(request, f'"{ebook.title}" foi publicado!')
    return redirect('accounts:producer')


def login_view(request):
    if request.user.is_authenticated:
        return redirect('accounts:dashboard')

    form = LoginForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            email    = form.cleaned_data['email']
            password = form.cleaned_data['password']

            # Bloqueio por força bruta (conta)
            candidate = User.objects.filter(email=email).first()
            if candidate and candidate.is_locked:
                messages.error(
                    request,
                    'Conta temporariamente bloqueada por segurança. '
                    'Tente novamente em alguns minutos.'
                )
                return redirect('accounts:login')

            user = authenticate(request, username=email, password=password)
            if user:
                reset_login_failures(user)
                next_url = _safe_next(request)
                if requires_two_factor(user):
                    try:
                        start_two_factor_login(request, user)
                    except Exception:
                        request.session.pop('otp_user_id', None)
                        request.session.pop('otp_code', None)
                        request.session.pop('otp_expires', None)
                        messages.error(
                            request,
                            'Não foi possível enviar o código por e-mail agora. '
                            'Tente novamente em instantes.'
                        )
                        return redirect('accounts:login')
                    messages.info(
                        request,
                        'Enviamos um código de 6 dígitos para o seu e-mail.'
                    )
                    return redirect(
                        reverse('accounts:two_factor') + '?next=' + next_url
                    )
                login(request, user)
                messages.success(
                    request,
                    f'Bem-vindo de volta, {user.first_name or user.username}!'
                )
                return redirect(next_url)
            else:
                if candidate:
                    record_login_failure(candidate)
                messages.error(request, 'Email ou senha incorretos.')
                return redirect('accounts:login')

    return render(request, 'accounts/login.html', {'form': form})


def two_factor_view(request):
    """Página de entrada do código OTP (login do site ou acesso ao admin)."""
    next_url = _safe_next(request)
    pending_uid = request.session.get('otp_user_id')

    if request.user.is_authenticated and request.session.get('two_factor_verified'):
        return redirect(next_url)

    # Sem usuário pendente e sem usuário logado → não deveria estar aqui
    if not pending_uid and not request.user.is_authenticated:
        return redirect('accounts:login')

    if request.method == 'POST':
        code = request.POST.get('code', '').strip()
        if otp_is_locked(request):
            messages.error(
                request,
                'Muitas tentativas inválidas. '
                'Faça login novamente para receber um novo código.'
            )
        elif pending_uid:
            if verify_otp(request, code):
                user = get_object_or_404(User, pk=pending_uid)
                login(request, user)
                request.session['two_factor_verified'] = True
                request.session.pop('otp_user_id', None)
                return redirect(next_url)
            record_otp_failure(request)
            if otp_is_locked(request):
                messages.error(
                    request,
                    'Muitas tentativas inválidas. '
                    'Faça login novamente para receber um novo código.'
                )
            else:
                messages.error(request, 'Código inválido ou expirado.')
        elif request.user.is_authenticated:
            if verify_otp(request, code):
                request.session['two_factor_verified'] = True
                return redirect(next_url)
            record_otp_failure(request)
            if otp_is_locked(request):
                messages.error(
                    request,
                    'Muitas tentativas inválidas. '
                    'Aguarde alguns minutos e tente novamente.'
                )
            else:
                messages.error(request, 'Código inválido ou expirado.')
    else:
        # Usuário já autenticado (ex.: admin): envia um código novo
        if not pending_uid and request.user.is_authenticated:
            if otp_is_locked(request):
                messages.error(
                    request,
                    'Muitas tentativas inválidas. '
                    'Aguarde alguns minutos e tente novamente.'
                )
            elif otp_can_resend(request):
                send_fresh_otp(request, request.user)
                messages.info(
                    request,
                    'Enviamos um código de 6 dígitos para o seu e-mail.'
                )
            else:
                messages.info(
                    request,
                    'Aguarde um pouco antes de solicitar um novo código.'
                )

    return render(request, 'accounts/two_factor.html', {
        'next_url': next_url,
    })


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
            try:
                send_verification_email(request, user)
            except Exception as e:
                print(f'Erro ao enviar e-mail de verificação: {e}')

            if user.is_writer:
                messages.success(
                    request,
                    'Conta criada como escritor! Enviamos um link de confirmação '
                    'para o seu e-mail. Confirme-o para liberar o acesso.'
                )
            else:
                messages.success(
                    request,
                    'Conta criada! Enviamos um link de confirmação para o seu '
                    'e-mail. Confirme-o para liberar o acesso.'
                )
            return redirect('accounts:login')

    return render(request, 'accounts/register.html', {'form': form})


def verify_email_view(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user and default_token_generator.check_token(user, token):
        user.email_verified = True
        user.save(update_fields=['email_verified'])
        messages.success(request, 'E-mail confirmado com sucesso!')
        return redirect('accounts:login')

    messages.error(request, 'Link de confirmação inválido ou expirado.')
    return redirect('accounts:login')


@login_required
def resend_verification_view(request):
    if request.user.email_verified:
        messages.info(request, 'Seu e-mail já está verificado.')
        return redirect('accounts:dashboard')
    try:
        send_verification_email(request, request.user)
        messages.success(request, 'Link de confirmação reenviado. Confira seu e-mail.')
    except Exception as e:
        messages.error(request, 'Não foi possível enviar o e-mail. Tente novamente.')
        print(f'Erro ao reenviar verificação: {e}')
    return redirect('accounts:dashboard')


@login_required
def request_producer_view(request):
    user = request.user
    if user.is_producer():
        if not user.producer_approved:
            messages.warning(
                request,
                'Sua solicitação de produtor já foi enviada e aguarda aprovação.'
            )
        else:
            messages.info(request, 'Você já é um produtor aprovado.')
        return redirect('accounts:dashboard')

    user.producer_requested = True
    user.save(update_fields=['producer_requested'])
    messages.success(
        request,
        'Solicitação enviada! A administração vai analisar seu acesso de escritor.'
    )
    return redirect('accounts:dashboard')


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
    config = PlatformConfig.get()

    if request.method == 'POST' and 'accept_terms' in request.POST:
        if config.terms_enabled:
            request.user.terms_accepted = True
            request.user.save(update_fields=['terms_accepted'])
            messages.success(request, 'Termos da Loja aceitos com sucesso!')
        return redirect('accounts:profile')

    form = ProfileForm(request.POST or None, request.FILES or None, instance=request.user)
    if request.method == 'POST' and 'accept_terms' not in request.POST:
        if form.is_valid():
            form.save()
            messages.success(request, 'Perfil atualizado com sucesso!')
            return redirect('accounts:profile')

    return render(request, 'accounts/profile.html', {
        'form': form,
        'terms_enabled': config.terms_enabled,
        'store_terms': config.store_terms,
    })


@login_required
@producer_required
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
@producer_required
def bonus_list_view(request, pk):
    ebook   = get_object_or_404(Ebook, pk=pk, author=request.user)
    bonuses = ebook.bonuses.all()
    return render(request, 'accounts/bonus_list.html', {
        'ebook'  : ebook,
        'bonuses': bonuses,
    })


@login_required
@producer_required
def bonus_delete_view(request, pk):
    bonus = get_object_or_404(EbookBonus, pk=pk, ebook__author=request.user)
    ebook_pk = bonus.ebook.pk
    bonus.delete()
    messages.success(request, 'Bônus removido.')
    return redirect('accounts:ebook_bonuses', pk=ebook_pk)


@login_required
@producer_required
def financial_view(request):
    """Painel financeiro completo do produtor."""
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
@producer_required
def withdraw_request_view(request):
    """Solicitar saque."""
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


# ---------------------------------------------------------------------------
# Painel de Administração — Gestão de Usuários
# ---------------------------------------------------------------------------

def staff_or_superuser_required(view_func):
    """Permite acesso a superusuários E staff."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(settings.LOGIN_URL + '?next=' + request.path)
        if not (request.user.is_superuser or request.user.is_staff):
            messages.error(request, 'Acesso restrito ao administrador.')
            return redirect('accounts:dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper


@staff_or_superuser_required
def admin_users_list_view(request):
    """Lista todos os usuários com filtros e busca."""
    status_filter = request.GET.get('status', '')
    role_filter = request.GET.get('role', '')
    search = request.GET.get('q', '')

    users = User.objects.all().order_by('-date_joined')

    if status_filter == 'active':
        users = users.filter(is_active=True)
    elif status_filter == 'inactive':
        users = users.filter(is_active=False)

    if role_filter == 'writer':
        users = users.filter(is_writer=True)
    elif role_filter == 'buyer':
        users = users.filter(is_writer=False)
    elif role_filter == 'pending':
        users = users.filter(producer_requested=True, producer_approved=False)

    if search:
        users = users.filter(
            first_name__icontains=search
        ) | users.filter(
            last_name__icontains=search
        ) | users.filter(
            email__icontains=search
        ) | users.filter(
            cpf__icontains=search
        )

    paginator = Paginator(users, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    stats = {
        'total': User.objects.count(),
        'active': User.objects.filter(is_active=True).count(),
        'writers': User.objects.filter(is_writer=True).count(),
        'pending': User.objects.filter(producer_requested=True, producer_approved=False).count(),
    }

    return render(request, 'admin_panel/users.html', {
        'page_obj': page_obj,
        'stats': stats,
        'search': search,
        'status_filter': status_filter,
        'role_filter': role_filter,
    })


@staff_or_superuser_required
def admin_user_detail_view(request, pk):
    """Detalhes de um usuário específico."""
    user_obj = get_object_or_404(User, pk=pk)
    return render(request, 'admin_panel/user_detail.html', {
        'user_obj': user_obj,
    })


@staff_or_superuser_required
def admin_toggle_access_view(request, pk):
    """Ativa ou desativa o acesso de um usuário."""
    if request.method != 'POST':
        return redirect('accounts:admin_users')

    user_obj = get_object_or_404(User, pk=pk)

    if user_obj.pk == request.user.pk:
        messages.error(request, 'Você não pode desativar sua própria conta.')
        return redirect('accounts:admin_user_detail', pk=pk)

    user_obj.is_active = not user_obj.is_active
    user_obj.save(update_fields=['is_active'])

    status = 'ativado' if user_obj.is_active else 'desativado'
    messages.success(request, f'Acesso de {user_obj.first_name or user_obj.email} {status}.')
    return redirect('accounts:admin_user_detail', pk=pk)


@staff_or_superuser_required
def admin_toggle_writer_view(request, pk):
    """Marca ou desmarca um usuário como escritor."""
    if request.method != 'POST':
        return redirect('accounts:admin_users')

    user_obj = get_object_or_404(User, pk=pk)
    user_obj.is_writer = not user_obj.is_writer
    if user_obj.is_writer:
        user_obj.producer_approved = True
    user_obj.save(update_fields=['is_writer', 'producer_approved'])

    status = 'agora é escritor' if user_obj.is_writer else 'não é mais escritor'
    messages.success(request, f'{user_obj.first_name or user_obj.email} {status}.')
    return redirect('accounts:admin_user_detail', pk=pk)


# ---------------------------------------------------------------------------
# Painel de Administração — Gestão de Livros
# ---------------------------------------------------------------------------

@staff_or_superuser_required
def admin_books_list_view(request):
    status_filter = request.GET.get('status', '')
    search = request.GET.get('q', '')

    ebooks = Ebook.objects.select_related('author').order_by('-created_at')

    if status_filter == 'pending':
        ebooks = ebooks.filter(status='pending')
    elif status_filter == 'published':
        ebooks = ebooks.filter(status='published')
    elif status_filter == 'rejected':
        ebooks = ebooks.filter(status='rejected')
    elif status_filter == 'draft':
        ebooks = ebooks.filter(status='draft')

    if search:
        ebooks = ebooks.filter(
            Q(title__icontains=search)
        ) | ebooks.filter(
            Q(author__first_name__icontains=search)
        ) | ebooks.filter(
            Q(author__last_name__icontains=search)
        ) | ebooks.filter(
            Q(author__email__icontains=search)
        )

    paginator = Paginator(ebooks, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    stats = {
        'total': Ebook.objects.count(),
        'pending': Ebook.objects.filter(status='pending').count(),
        'published': Ebook.objects.filter(status='published').count(),
        'rejected': Ebook.objects.filter(status='rejected').count(),
    }

    return render(request, 'admin_panel/books.html', {
        'page_obj': page_obj,
        'stats': stats,
        'search': search,
        'status_filter': status_filter,
    })


@staff_or_superuser_required
def admin_book_detail_view(request, pk):
    ebook = get_object_or_404(Ebook.objects.select_related('author'), pk=pk)
    return render(request, 'admin_panel/book_detail.html', {
        'ebook': ebook,
    })


@staff_or_superuser_required
def admin_book_approve_view(request, pk):
    if request.method != 'POST':
        return redirect('accounts:admin_books')

    ebook = get_object_or_404(Ebook, pk=pk)
    ebook.status = 'published'
    ebook.rejection_reason = ''
    ebook.save(update_fields=['status', 'rejection_reason'])
    messages.success(request, f'"{ebook.title}" foi aprovado e publicado.')
    return redirect('accounts:admin_book_detail', pk=pk)


@staff_or_superuser_required
def admin_book_reject_view(request, pk):
    if request.method != 'POST':
        return redirect('accounts:admin_books')

    ebook = get_object_or_404(Ebook, pk=pk)
    justificativa = (request.POST.get('justificativa') or '').strip()
    if not justificativa:
        messages.error(
            request,
            'A justificativa é obrigatória para rejeitar um eBook.'
        )
        return redirect('accounts:admin_book_detail', pk=pk)

    ebook.status = 'rejected'
    ebook.rejection_reason = justificativa
    ebook.save(update_fields=['status', 'rejection_reason'])

    try:
        send_rejection_email(request, ebook)
    except Exception:
        messages.warning(
            request,
            'eBook rejeitado, mas houve falha ao enviar o e-mail ao escritor. '
            'Verifique a configuração de SMTP.'
        )

    messages.success(request, f'"{ebook.title}" foi rejeitado.')
    return redirect('accounts:admin_book_detail', pk=pk)
