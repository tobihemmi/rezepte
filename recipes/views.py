from django.db.models import F, Q, Case, When, Value, IntegerField
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse_lazy, reverse
from django.views import generic, View
from django.views.generic import CreateView, DeleteView, TemplateView
from datetime import date
import random

from .models import Recipe, Label, WeeklyPlan, WeeklyPlanEntry
from .forms import RecipeForm

DAYS = ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag']

def filter_recipes(qs, params):
    # 🔎 Suche
    query = params.get("q")
    if query:
        qs = qs.filter(
            Q(title__icontains=query) |
            Q(ingredients__icontains=query)
        ).distinct()

    # ⏱ Dauer
    max_duration = params.get("max_duration")
    if max_duration:
        try:
            qs = qs.filter(duration_minutes__lte=int(max_duration))
        except ValueError:
            pass

    max_working = params.get("max_working_duration")
    if max_working:
        try:
            qs = qs.filter(working_time__lte=int(max_working))
        except ValueError:
            pass

    # 🏷 Labels
    category_ids = params.getlist("category_labels")
    event_ids = params.getlist("event_labels")

    if category_ids:
        qs = qs.filter(labels__id__in=category_ids, labels__label_type="category")

    if event_ids:
        qs = qs.filter(labels__id__in=event_ids, labels__label_type="event")

    return qs.distinct()


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
        qs = Recipe.objects.prefetch_related("labels")
        qs = filter_recipes(qs, self.request.GET)

        sort_param = self.request.GET.get("sort", "title")
        if sort_param == "duration":
            qs = qs.order_by("duration_minutes")
        elif sort_param == "cooked":
            qs = qs.order_by("-cooked_count")
        else:
            qs = qs.order_by("title")

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["labels_category"] = Label.objects.filter(label_type="category")
        context["labels_event"] = Label.objects.filter(label_type="event")

        # ausgewählte Labels
        selected_categories = self.request.GET.getlist("category_labels")
        selected_events = self.request.GET.getlist("event_labels")

        context["selected_categories"] = list(map(int, selected_categories))
        context["selected_events"] = list(map(int, selected_events))

        context["result_count"] = self.object_list.count()

        # ✅ FILTER STATUS (wichtig!)
        context["filters_active"] = any([
            self.request.GET.get("q"),
            self.request.GET.get("max_duration"),
            self.request.GET.get("max_working_duration"),
            selected_categories,
            selected_events,
        ])

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

        try:
            ing_list = [line.strip() for line in recipe.ingredients.splitlines() if line.strip()]
        except BaseException:
            ing_list = []
        try:
            st_list = [line.strip() for line in recipe.steps.splitlines() if line.strip()]
        except BaseException:
            st_list = []

        context.update({
            "recipe": recipe,
            "base_servings": base_servings,
            "current_servings": current_servings,
            "ingredients_list": ing_list,
            "steps_list": st_list,
            "days": DAYS,
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
class RandomRecipeView(View):

    def get(self, request, *args, **kwargs):
        qs = Recipe.objects.all()
        qs = filter_recipes(qs, request.GET)

        if not qs.exists():
            return redirect("recipes:index")

        recipe = qs.order_by("?").first()

        return redirect("recipes:randon", slug=recipe.slug)


class RandomRecipeView(TemplateView):
    template_name = "recipes/recipe_random.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        index_view = IndexView()
        index_view.request = self.request
        qs = index_view.get_queryset()

        context["recipe"] = random.choice(list(qs)) if qs.exists() else None
        context["days"] = DAYS
        return context
    
def weekly_plan_view(request):
    week_start = date(2000, 1, 1)
    plan, _ = WeeklyPlan.objects.get_or_create(week_start=week_start)

    # GET-Parameter kopieren, um sie beim Redirect weiterzugeben
    params = request.GET.copy()

    action = params.get("action")
    recipe_id = params.get("recipe_id")
    day = params.get("day")

    if action == "add" and recipe_id and day in DAYS:
        recipe = get_object_or_404(Recipe, id=recipe_id)
        WeeklyPlanEntry.objects.create(plan=plan, day=day, recipe=recipe)

        # Entferne Aktions-Parameter, damit die URL sauber bleibt
        for key in ["recipe_id", "action", "day", "entry_id"]:
            params.pop(key, None)

        return redirect(f"{reverse('recipes:weekly_plan')}?{params.urlencode()}")

    elif action == "comment":
        entry_id = params.get("entry_id")
        comment_text = params.get("comment", "").strip()
        if entry_id:
            entry = get_object_or_404(WeeklyPlanEntry, id=entry_id)
            entry.comment = comment_text
            entry.save()

            for key in ["action", "entry_id", "comment"]:
                params.pop(key, None)

            return redirect(f"{reverse('recipes:weekly_plan')}?{params.urlencode()}")

    elif action == "move":
        entry_id = params.get("entry_id")
        new_day = params.get("day")
        if entry_id and new_day in DAYS:
            entry = get_object_or_404(WeeklyPlanEntry, id=entry_id)
            entry.day = new_day
            entry.save()

            # Filter behalten
            for key in ["action", "entry_id", "day", "recipe_id"]:
                params.pop(key, None)

            return redirect(f"{reverse('recipes:weekly_plan')}?{params.urlencode()}")

    elif action == "remove":
        entry_id = params.get("entry_id")
        if entry_id:
            entry = get_object_or_404(WeeklyPlanEntry, id=entry_id)
            entry.delete()

            # Filter behalten
            for key in ["action", "entry_id", "day", "recipe_id"]:
                params.pop(key, None)

            return redirect(f"{reverse('recipes:weekly_plan')}?{params.urlencode()}")
    elif action == "clear":
        # Alle Einträge des aktuellen Wochenplans löschen
        plan.entries.all().delete()

        # Filter behalten
        for key in ["action", "recipe_id", "day", "entry_id"]:
            params.pop(key, None)

        return redirect(f"{reverse('recipes:weekly_plan')}?{params.urlencode()}")

    # Tagesweise Einträge als Liste von Tupeln (Tag, Einträge)
    day_entries_list = [(day_name, plan.entries.filter(day=day_name)) for day_name in DAYS]

    context = {
        "plan": plan,
        "day_entries_list": day_entries_list,
        "recipes": Recipe.objects.all(),
        "days": DAYS,  # wichtig für das Dropdown in der Vorlage
    }
    return render(request, "recipes/weekly_plan.html", context)


