from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import F,Q
from django.http import JsonResponse
from django.urls import reverse, reverse_lazy
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import View, TemplateView, CreateView, UpdateView, ListView, DetailView
from django.views.generic.edit import FormMixin
from .forms import CommentForm, CategoryForm, TagForm, PostForm
from .models import Post, Tag, Category
from .templatetags.md_to_html import markdown_to_html
import json

menu = [
    {"name": "Главная", "alias": "main"},
    {"name": "Блог", "alias": "blog"},
    {"name": "О проекте", "alias": "about"},
    {"name": "Добавить пост", "alias": "add_post"}
]


class BlogView(ListView):
    model = Post
    template_name = 'blog_app/blog.html'
    context_object_name = 'posts'
    paginate_by = 4

    def get_queryset(self):
        queryset = Post.objects.prefetch_related('tags', 'comments').select_related('author', 'category').filter(status="published")

        search_query = self.request.GET.get("search", "")
        search_category = self.request.GET.get("search_category")
        search_tag = self.request.GET.get("search_tag")
        search_comments = self.request.GET.get("search_comments")
        if search_query:
            query = Q(title__icontains=search_query) | Q(text__icontains=search_query)

            if search_category:
                query |= Q(category__name__icontains=search_query)

            if search_tag:
                query |= Q(tags__name__icontains=search_query)

            if search_comments:
                query |= Q(comments__text__icontains=search_query)

            queryset = queryset.filter(query)
        return queryset.distinct().order_by("-created_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['menu'] = menu
        context['page_alias'] = 'blog'
        context['breadcrumbs'] = [
            {'name': 'Главная', 'url': reverse('main')},
            {'name': 'Блог'},
        ]
        return context


class PostDetailView(FormMixin, DetailView):
    model = Post
    template_name = 'blog_app/post_detail.html'
    context_object_name = 'post'
    form_class = CommentForm

    def get_success_url(self):
        return reverse('post_by_slug', kwargs={'slug': self.object.slug})

    def get_object(self, queryset=None):
        post = super().get_object(queryset)
        session_key = f'post_{post.id}_viewed'
        if not self.request.session.get(session_key, False):
            Post.objects.filter(id=post.id).update(views=F('views') + 1)
            self.request.session[session_key] = True
            post.refresh_from_db()
        return post
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        comments_list = self.object.comments.filter(status='accepted').order_by('created_at')
        paginator = Paginator(comments_list, 20)
        page_number = self.request.GET.get('page')
        try:
            comments_page = paginator.page(page_number)
        except PageNotAnInteger:
            comments_page = paginator.page(1)
        except EmptyPage:
            comments_page = paginator.page(paginator.num_pages)
        context['comments'] = comments_page
        context['form'] = self.get_form()
        context['menu'] = menu
        # Добавьте breadcrumbs, если они вам нужны:
        context['breadcrumbs'] = [
            {'name': 'Главная', 'url': reverse('main')},
            {'name': 'Блог', 'url': reverse('blog')},
            {'name': self.object.title}
        ]
        return context
    def post(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, 'Для добавления комментария необходимо войти в систему.')
            return redirect('login')

        self.object = self.get_object()
        form = self.get_form()

        if form.is_valid():
            comment = form.save(commit=False)
            comment.post = self.object
            comment.author = request.user
            comment.status = 'unchecked'
            comment.save()
            messages.success(request, 'Ваш комментарий находится на модерации.')
            return redirect(self.get_success_url())
        else:
            return self.form_invalid(form)

class IndexView(TemplateView):
    template_name = 'index.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['menu'] = menu
        context['page_alias'] = 'main'
        return context


class AboutView(View):
    def get(self,request):
        breadcrumbs = [
            {'name': 'Главная', 'url': reverse('main')},
            {'name': 'О проекте'},
        ]
        return render(request, 'about.html', {
            'breadcrumbs': breadcrumbs,
            'menu': menu,
            'page_alias': 'about'
        })

class AddPostView(LoginRequiredMixin, CreateView):
    model = Post
    form_class = PostForm
    template_name = 'blog_app/add_post.html'

    success_url = reverse_lazy('blog')

    def form_valid(self, form):
        # Сохраняем форму с указанием автора
        self.object = form.save(commit=True, author=self.request.user)
        # Добавляем сообщение об успехе
        return super().form_valid(form)

    def form_invalid(self, form):
        print(form.errors)
        return JsonResponse({
            'success': False,
            'message': 'Ошибка в форме',
            'errors': form.errors
        }, status=400)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['menu'] = menu
        return context

class UpdatePostView(LoginRequiredMixin, UpdateView):
    model = Post
    form_class = PostForm
    template_name = 'blog_app/add_post.html'
    success_url = reverse_lazy('blog')
    def get_object(self, queryset=None):
        # Получаем объект поста по slug
        return get_object_or_404(Post, slug=self.kwargs['post_slug'])
    def form_valid(self, form):
        self.object = form.save()
        return super().form_valid(form)

    def form_invalid(self, form):
        return JsonResponse({
            'success': False,
            'message': 'Ошибка в форме',
            'errors': form.errors
        }, status=400)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['menu'] = menu
        return context



class PostsByTagListView(ListView):
    model = Post
    template_name = 'blog_app/blog.html'
    context_object_name = 'posts'
    paginate_by = 4

    def get_queryset(self):
        tag = self.kwargs['tag']
        posts = Post.objects.filter(tags__slug=tag).filter(status='published')
        return posts

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['menu'] = menu
        context['page_alias'] = 'blog'
        return context

class PostsByCategoryListView(ListView):
    model = Post
    template_name = 'blog_app/blog.html'
    context_object_name = 'posts'
    paginate_by = 4

    def get_queryset(self):
        category = self.kwargs['category']
        return Post.objects.select_related('author', 'category')\
                         .prefetch_related('tags', 'comments')\
                         .filter(category__slug=category, status='published')
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['menu'] = menu
        context['page_alias'] = 'blog'
        context['breadcrumbs'] = [
            {'name': 'Главная', 'url': reverse('main')},
            {'name': 'Блог', 'url': reverse('blog')},
            {'name': Category.objects.get(slug=self.kwargs['category']).name}
        ]
        return context

#@csrf_exempt
class PreviewPostView(View):
    http_method_names = ['post']
    def post(self, request, *args, **kwargs):
        data = json.loads(request.body)
        text = data.get("text", "")
        html = markdown_to_html(text)
        return JsonResponse({"html": html})


class AddCategoryView(LoginRequiredMixin,View ):
    def get(self, request):
        context = {
            'menu': menu,
            'form': CategoryForm(),
            "operation_title": 'Добавить категорию',
            'operation_header': 'Добавит новую категорию',
            'submit_button_text': 'Создать',
        }
        return render(request, 'blog_app/category_form.html', context)

    def post(self,request):
        form = CategoryForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, f"Категория '{form.cleaned_data['name']}' успешно добавлена!")
            return redirect('add_category')
        else:
            messages.error(request,'Пожалуйста, исправьте ошибки ниже.')
            return redirect('add_category')

@login_required
def update_category(request, category_slug):
    category_obj = get_object_or_404(Category, slug=category_slug)
    context = {"menu": menu, "catagory": category_obj}

    if request.method == "POST":
        form = CategoryForm(request.POST, instance=category_obj)
        if form.is_valid():
            form.save()
            messages.success(request, f"Категория '{form.cleaned_data['name']}' успешно обновлена.")
            return redirect('posts_by_category', category=category_obj.slug)
        else:
            messages.error(request, "Пожалуйста, исправьте ошибки ниже.")
    else:
        form = CategoryForm(instance=category_obj)

    context.update({
        "form": form,
        "operation_title": "Обновить категорию",
        "operation_header": "Обновить категорию",
        "submit_button_text": "Сохранить",
    })
    return render(request, "blog_app/category_form.html", context)


class UpdateCategoryView(LoginRequiredMixin, UpdateView):
    model = Category
    form_class = CategoryForm
    template_name = "blog_app/category_form.html"

    def get_object(self, queryset=None):
        return get_object_or_404(Category, slug=self.kwargs['category_slug'])

    def get_success_url(self):
        return reverse_lazy('posts_by_category', kwargs={'category': self.object.slug})

    def get_context_data(self, **kwargs):

        context = super().get_context_data(**kwargs)
        context["menu"] = menu
        context["operation_title"] = "Обновить категорию"
        context["operation_header"] = "Обновить категорию"
        context["submit_button_text"] = "Сохранить"
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Категория '{form.cleaned_data['name']}' успешно обновлена.")
        return response

    def form_invalid(self, form):
        messages.error(self.request, "Пожалуйста, исправьте ошибки ниже.")
        return super().form_invalid(form)


class AddTagView(LoginRequiredMixin, CreateView):
    model = Tag
    form_class = TagForm
    template_name = 'blog_app/add_tag.html'
    success_url = reverse_lazy("add_tag")

    def get_context_data(self,**kwargs):
        context = super().get_context_data(**kwargs)
        context['menu'] = menu
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Тег {form.instance.name} успешно добавлен!")
        return response

    def form_invalid(self, form):
        messages.error(self.request, "Ошибка при добавлении тега. Проверьте введенные данные.")
        return super().form_invalid(form)





