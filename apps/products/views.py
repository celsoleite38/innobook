from django.shortcuts import render, get_object_or_404
from .models import Ebook, Category


def home_view(request):
    ebooks     = Ebook.objects.filter(status='published', featured=True)[:8]
    if not ebooks:
        ebooks = Ebook.objects.filter(status='published')[:8]
    categories = Category.objects.all()
    return render(request, 'products/home.html', {
        'ebooks'    : ebooks,
        'categories': categories,
    })


def ebook_list_view(request):
    ebooks     = Ebook.objects.filter(status='published')
    categories = Category.objects.all()

    # Filtro por categoria
    cat_slug = request.GET.get('categoria')
    if cat_slug:
        ebooks = ebooks.filter(category__slug=cat_slug)

    # Filtro por busca
    q = request.GET.get('q')
    if q:
        ebooks = ebooks.filter(title__icontains=q)

    # Ordenação
    order = request.GET.get('order', '-created_at')
    if order in ['price', '-price', '-created_at', 'title']:
        ebooks = ebooks.order_by(order)

    return render(request, 'products/list.html', {
        'ebooks'    : ebooks,
        'categories': categories,
        'q'         : q or '',
        'cat_slug'  : cat_slug or '',
        'order'     : order,
    })


def ebook_detail_view(request, slug):
    ebook = get_object_or_404(Ebook, slug=slug, status='published')

    # Verifica se o usuário já comprou
    already_bought = False
    download_token = None
    if request.user.is_authenticated:
        order = request.user.orders.filter(
            ebook=ebook, status='paid'
        ).first()
        if order:
            already_bought = True
            download_token = order.download_tokens.filter(
                is_active=True
            ).first()

    # Relacionados da mesma categoria
    related = Ebook.objects.filter(
        status='published',
        category=ebook.category
    ).exclude(id=ebook.id)[:4]

    return render(request, 'products/detail.html', {
        'ebook'         : ebook,
        'already_bought': already_bought,
        'download_token': download_token,
        'related'       : related,
    })


def category_view(request, slug):
    category = get_object_or_404(Category, slug=slug)
    ebooks   = Ebook.objects.filter(category=category, status='published')
    return render(request, 'products/category.html', {
        'category': category,
        'ebooks'  : ebooks,
    })