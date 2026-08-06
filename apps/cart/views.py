from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from apps.products.models import Ebook, FORMAT_DIGITAL, FORMAT_PHYSICAL, FORMAT_COMBO
from apps.payments.models import Order
from .models import Cart, CartItem


def get_or_create_cart(user):
    cart, _ = Cart.objects.get_or_create(user=user)
    return cart


@login_required
def cart_view(request):
    cart  = get_or_create_cart(request.user)
    items = cart.items.select_related('ebook').all()

    # Itens já comprados (por formato)
    paid_items = []
    for item in items:
        if item.ebook.user_owns_format(request.user, item.variant):
            paid_items.append(item.id)

    payable_total = sum(
        item.price for item in items if item.id not in paid_items
    )

    return render(request, 'cart/cart.html', {
        'cart'          : cart,
        'items'         : items,
        'paid_items'    : paid_items,
        'payable_total' : payable_total,
    })


@login_required
def add_to_cart(request, ebook_id):
    ebook = get_object_or_404(Ebook, id=ebook_id, status='published')

    variant = request.GET.get('variant', FORMAT_DIGITAL)
    if variant not in (FORMAT_DIGITAL, FORMAT_PHYSICAL, FORMAT_COMBO):
        variant = FORMAT_DIGITAL

    if variant in (FORMAT_PHYSICAL, FORMAT_COMBO) and not ebook.has_physical():
        messages.warning(request, 'A versão física deste livro está esgotada.')
        return redirect('products:detail', slug=ebook.slug)

    # Já comprou esse formato?
    if ebook.user_owns_format(request.user, variant):
        messages.info(request, 'Você já possui esta versão deste eBook!')
        return redirect('products:detail', slug=ebook.slug)

    cart = get_or_create_cart(request.user)
    item, created = CartItem.objects.get_or_create(
        cart=cart, ebook=ebook, variant=variant
    )

    if created:
        messages.success(
            request,
            f'"{ebook.title}" ({item.get_variant_display()}) adicionado ao carrinho!'
        )
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