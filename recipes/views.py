from django.db.models import F
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse_lazy
from django.views import generic, View
from django.views.generic import CreateView, DeleteView, TemplateView
import random

from .models import Recipe, Label
from .forms import RecipeForm


class RecipeCreateView(CreateView):
    model = Recipe
    form_class = RecipeForm
    template_name = "recipes/recipe_create.html"

class RecipeDeleteView(DeleteView):
    model = Recipe
    success_url = reverse_lazy("recipes:index")
    template_name = "recipes/recipe_confirm_delete.html"
    slug_field = "slug"
    slug_url_kwarg = "slug"


class RecipeUpdateView(View):
    template_name = "recipes/recipe_update.html"

    def get(self, request, slug):
        recipe = get_object_or_404(Recipe, slug=slug)
        form = RecipeForm(instance=recipe)
        return render(request, "recipes/recipe_update.html", {"form": form, "recipe": recipe})

    def post(self, request, slug):
        recipe = get_object_or_404(Recipe, slug=slug)
        form = RecipeForm(request.POST, request.FILES, instance=recipe)
        if form.is_valid():
            recipe = form.save(commit=False)

            # Zutaten & Schritte zusammensetzen
            ingredients = request.POST.getlist('ingredients')
            steps = request.POST.getlist('steps')

            recipe.ingredients = "\n".join([i.strip() for i in ingredients if i.strip()])
            recipe.steps = "\n".join([s.strip() for s in steps if s.strip()])

            recipe.save()
            form.save_m2m()
            return redirect(recipe.get_absolute_url())

        return render(request, "recipes/recipe_update.html", {"form": form, "recipe": recipe})

class IndexView(generic.ListView):
    model = Recipe
    template_name = "recipes/index.html"
    context_object_name = "latest_recipe_list"

    def get_queryset(self):
        qs = super().get_queryset().prefetch_related(
            "labels"
        )

        # 🔎 Suchbegriff
        query = self.request.GET.get("q")
        if query:
            qs = qs.filter(
                Q(title__icontains=query) |
                Q(ingredients__icontains=query)
            ).distinct()

        # ⏱ Dauerfilter
        max_duration = self.request.GET.get("max_duration")
        if max_duration:
            try:
                max_minutes = int(max_duration)
                qs = qs.filter(duration_minutes__lte=max_minutes)
            except ValueError:
                pass
        max_working_duration = self.request.GET.get("max_working_duration")
        if max_working_duration:
            try:
                max_working_minutes = int(max_working_duration)
                qs = qs.filter(working_time__lte=max_working_minutes)
            except ValueError:
                pass

        # 🏷 Labels: AND zwischen Kategorie & Event
        category_ids = self.request.GET.getlist("category_labels")
        event_ids = self.request.GET.getlist("event_labels")

        if category_ids:
            qs = qs.filter(labels__id__in=category_ids, labels__label_type="category").distinct()
        if event_ids:
            qs = qs.filter(labels__id__in=event_ids, labels__label_type="event").distinct()

         # **Sortierung nach Parameter**
        sort_param = self.request.GET.get("sort", "title")  # Default = Alphabet
        if sort_param == "duration":
            qs = qs.order_by("duration_minutes")
        else:
            qs = qs.order_by("title")

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["labels_category"] = Label.objects.filter(label_type="category")
        context["labels_event"] = Label.objects.filter(label_type="event")

        # ausgewählte Labels
        context["selected_categories"] = list(map(int, self.request.GET.getlist("category_labels")))
        context["selected_events"] = list(map(int, self.request.GET.getlist("event_labels")))

        context["result_count"] = self.object_list.count()

        return context


class DetailView(generic.DetailView):
    model = Recipe
    template_name = "recipes/recipe_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        recipe = self.object

        # 🔢 gewünschte Portionen aus URL
        try:
            target_servings = int(self.request.GET.get("servings", recipe.servings))
            if target_servings < 1:
                target_servings = recipe.servings
        except (TypeError, ValueError):
            target_servings = recipe.servings

        factor = target_servings / recipe.servings

        ingredients_list = []

        for line in recipe.ingredients.splitlines():
            line = line.strip()
            if not line:
                continue

            parts = line.split(" ", 2)

            # Erwartetes Format: "MENGE EINHEIT ZUTAT"
            try:
                amount = float(parts[0].replace(",", "."))
                new_amount = round(amount * factor, 2)
                ingredients_list.append(
                    f"{new_amount:g} {' '.join(parts[1:])}"
                )
            except (ValueError, IndexError):
                # z.B. "Salz nach Geschmack"
                ingredients_list.append(line)

        # Zutaten aufsplitten
        context["ingredients_list"] = [
            line.strip()
            for line in self.object.ingredients.splitlines()
            if line.strip()
        ]
        
        # Schritte aufsplitten
        context["steps_list"] = [
            line.strip()
            for line in self.object.steps.splitlines()
            if line.strip()
        ]

        context["current_servings"] = target_servings
        context["base_servings"] = recipe.servings

        return context


class RandomRecipeView(TemplateView):
    template_name = "recipes/recipe_random.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        index_view = IndexView()
        index_view.request = self.request
        qs = index_view.get_queryset()

        context["recipe"] = random.choice(list(qs)) if qs.exists() else None
        return context