from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from apps.products.models import Ebook
from apps.payments.models import Order
from .models import Cart, CartItem


def get_or_create_cart(user):
    cart, _ = Cart.objects.get_or_create(user=user)
    return cart


@login_required
def cart_view(request):
    cart  = get_or_create_cart(request.user)
    items = cart.items.select_related('ebook').all()

    # Filtra itens já comprados
    paid_ebook_ids = request.user.orders.filter(
        status='paid'
    ).values_list('ebook_id', flat=True)

    return render(request, 'cart/cart.html', {
        'cart'          : cart,
        'items'         : items,
        'paid_ebook_ids': list(paid_ebook_ids),
    })


@login_required
def add_to_cart(request, ebook_id):
    ebook = get_object_or_404(Ebook, id=ebook_id, status='published')

    # Já comprou?
    if request.user.orders.filter(ebook=ebook, status='paid').exists():
        messages.info(request, 'Você já possui este eBook!')
        return redirect('products:detail', slug=ebook.slug)

    cart = get_or_create_cart(request.user)
    item, created = CartItem.objects.get_or_create(cart=cart, ebook=ebook)

    if created:
        messages.success(request, f'"{ebook.title}" adicionado ao carrinho!')
    else:
        messages.info(request, f'"{ebook.title}" já está no seu carrinho.')

    # AJAX
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'count': cart.count, 'created': created})

    return redirect('cart:cart')


@login_required
def remove_from_cart(request, item_id):
    item = get_object_or_404(CartItem, id=item_id, cart__user=request.user)
    item.delete()
    messages.success(request, 'Item removido do carrinho.')
    return redirect('cart:cart')


@login_required
def cart_count(request):
    """Retorna contagem do carrinho via AJAX."""
    if request.user.is_authenticated:
        cart = get_or_create_cart(request.user)
        return JsonResponse({'count': cart.count})
    return JsonResponse({'count': 0})