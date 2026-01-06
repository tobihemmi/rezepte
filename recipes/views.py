from django.db.models import F, Q, Case, When, Value, IntegerField
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse_lazy
from django.views import generic, View
from django.views.generic import CreateView, DeleteView, TemplateView
from django.utils import timezone
import random

from .models import Recipe, Label, WeeklyPlan, WeeklyPlanEntry
from .forms import RecipeForm

DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

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
        elif sort_param =="cooked":
            qs = qs.order_by("-cooked_count") #meistgekocht zuerst
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
    slug_field = "slug"
    slug_url_kwarg = "slug"

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        if "cooked" in request.POST:
            self.object.cooked_count = F("cooked_count") + 1
            self.object.save(update_fields=["cooked_count"])
        elif "undo_cooked" in request.POST:
            self.object.cooked_count = Case(
                When(cooked_count__gt=0, then=F("cooked_count") - 1),
                default=Value(0),
                output_field=IntegerField(),
            )
            self.object.save(update_fields=["cooked_count"])
        return redirect(self.object.get_absolute_url())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        recipe = self.object

        # Basisportionen
        base_servings = recipe.servings or 1

        # User-angepasste Portionen via GET oder Standard
        try:
            current_servings = int(self.request.GET.get("servings", base_servings))
            if current_servings < 1:
                current_servings = base_servings
        except (TypeError, ValueError):
            current_servings = base_servings

        context.update({
            "recipe": recipe,
            "base_servings": base_servings,
            "current_servings": current_servings,
            "ingredients_list": [line.strip() for line in recipe.ingredients.splitlines() if line.strip()],
            "steps_list": [line.strip() for line in recipe.steps.splitlines() if line.strip()],
            "days": ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'],  # NEU
        })
        return context


class RecipeCookView(generic.DetailView):
    model = Recipe
    template_name = "recipes/recipe_cook.html"
    slug_field = "slug"
    slug_url_kwarg = "slug"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        recipe = self.object

        base_servings = recipe.servings or 1

        # Gewünschte Portionen aus URL
        try:
            current_servings = int(self.request.GET.get("servings", base_servings))
            if current_servings < 1:
                current_servings = base_servings
        except (TypeError, ValueError):
            current_servings = base_servings

        # Zutaten unverändert übergeben → JS skaliert
        context.update({
            "recipe": recipe,
            "base_servings": base_servings,
            "current_servings": current_servings,
            "ingredients_list": [line.strip() for line in recipe.ingredients.splitlines() if line.strip()],
            "steps_list": [line.strip() for line in recipe.steps.splitlines() if line.strip()],
        })
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
    
def weekly_plan_view(request):
    # Immer der aktuelle Wochenplan
    week_start = timezone.now().date()
    plan, _ = WeeklyPlan.objects.get_or_create(week_start=week_start)

    # Aktionen: Rezept hinzufügen oder entfernen
    action = request.GET.get("action")
    recipe_id = request.GET.get("recipe_id")
    day = request.GET.get("day")

    if action == "add" and recipe_id and day in DAYS:
        recipe = get_object_or_404(Recipe, id=recipe_id)
        WeeklyPlanEntry.objects.create(plan=plan, day=day, recipe=recipe)
        return redirect("recipes:weekly_plan")

    if action == "remove":
        entry_id = request.GET.get("entry_id")
        if entry_id:
            entry = get_object_or_404(WeeklyPlanEntry, id=entry_id)
            entry.delete()
            return redirect("recipes:weekly_plan")

    # Erstelle Liste von Tupeln (Tag, Einträge), weil Templates keine [] für Dict unterstützen
    day_entries_list = [(day_name, plan.entries.filter(day=day_name)) for day_name in DAYS]

    context = {
        "plan": plan,
        "day_entries_list": day_entries_list,
        "recipes": Recipe.objects.all(),  # für Dropdown
    }
    return render(request, "recipes/weekly_plan.html", context)

