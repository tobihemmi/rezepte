import random
from collections import defaultdict
from datetime import date, datetime, timedelta

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import redirect_to_login
from django.db.models import F, Q
from django.db.models.functions import Greatest
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views import generic
from django.views.generic import CreateView, DeleteView, TemplateView, UpdateView

from .forms import RecipeForm
from .models import Label, Recipe, WeeklyPlan, WeeklyPlanEntry


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def parse_date(value):
    """'YYYY-MM-DD' -> date, sonst None."""
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def to_int(value):
    """String -> int, sonst None."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def int_list(values):
    """Liste von Strings -> nur gültige ints (verhindert 500er bei ?x=abc)."""
    return [int(v) for v in values if v.isdigit()]


def split_lines(text):
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


def join_lines(values):
    return "\n".join(v.strip() for v in values if v.strip())


def monday_of(d):
    return d - timedelta(days=d.weekday())


def add_recipe_to_plan(recipe, entry_date):
    """Legt einen Plan-Eintrag an (falls noch nicht vorhanden). Gemeinsam genutzt
    von DetailView, RandomRecipeView und weekly_plan_view."""
    plan, _ = WeeklyPlan.objects.get_or_create(week_start=monday_of(entry_date))
    WeeklyPlanEntry.objects.get_or_create(plan=plan, recipe=recipe, date=entry_date)


def redirect_to_plan(start_date=None):
    url = reverse("recipes:weekly_plan")
    if start_date:
        url += f"?start_date={start_date:%Y-%m-%d}"
    return redirect(url)


def filter_recipes(qs, params):
    query = params.get("q")
    if query:
        qs = qs.filter(Q(title__icontains=query) | Q(ingredients__icontains=query))

    max_duration = to_int(params.get("max_duration"))
    if max_duration is not None:
        qs = qs.filter(duration_minutes__lte=max_duration)

    max_working = to_int(params.get("max_working_duration"))
    if max_working is not None:
        qs = qs.filter(working_time__lte=max_working)

    category_ids = int_list(params.getlist("category_labels"))
    event_ids = int_list(params.getlist("event_labels"))

    if category_ids:
        qs = qs.filter(labels__id__in=category_ids, labels__label_type="category")
    if event_ids:
        qs = qs.filter(labels__id__in=event_ids, labels__label_type="event")

    # Nur ein distinct() am Ende, nur die Joins (Labels) erzeugen Duplikate
    return qs.distinct()


# ---------------------------------------------------------------------------
# Mixins
# ---------------------------------------------------------------------------

class RecipeTextMixin:
    """Portionen, Zutaten- und Schrittlisten für Detail- und Koch-Ansicht."""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        recipe = self.object

        base = recipe.servings or 1
        current = to_int(self.request.GET.get("servings")) or base
        if current < 1:
            current = base

        context.update({
            "base_servings": base,
            "current_servings": current,
            "ingredients_list": split_lines(recipe.ingredients),
            "steps_list": split_lines(recipe.steps),
        })
        return context


class IngredientsStepsFormMixin:
    """Setzt Zutaten/Schritte aus den dynamischen Formularfeldern zusammen."""

    def form_valid(self, form):
        recipe = form.save(commit=False)
        recipe.ingredients = join_lines(self.request.POST.getlist("ingredients"))
        recipe.steps = join_lines(self.request.POST.getlist("steps"))
        recipe.save()
        form.save_m2m()
        return redirect(recipe.get_absolute_url())


# ---------------------------------------------------------------------------
# Rezept CRUD
# ---------------------------------------------------------------------------

class RecipeCreateView(LoginRequiredMixin, CreateView):
    model = Recipe
    form_class = RecipeForm
    template_name = "recipes/recipe_create.html"


class RecipeUpdateView(LoginRequiredMixin, IngredientsStepsFormMixin, UpdateView):
    model = Recipe
    form_class = RecipeForm
    template_name = "recipes/recipe_update.html"
    context_object_name = "recipe"  # Template erwartet "recipe"


class RecipeDeleteView(LoginRequiredMixin, DeleteView):
    model = Recipe
    success_url = reverse_lazy("recipes:index")
    template_name = "recipes/recipe_confirm_delete.html"


# ---------------------------------------------------------------------------
# Rezeptliste
# ---------------------------------------------------------------------------

class IndexView(generic.ListView):
    model = Recipe
    template_name = "recipes/index.html"
    context_object_name = "latest_recipe_list"
    paginate_by = 1000  # Template braucht dafür Seitennavigation (page_obj)

    SORT_FIELDS = {
        "title": "title",
        "duration": "duration_minutes",
        "cooked": "cooked_count",
    }

    def get_queryset(self):
        # Lange Textfelder werden in der Liste nicht gebraucht.
        # Achtung: Zeigt das Template sie an, wieder entfernen (sonst Nachlade-Queries).
        qs = Recipe.objects.prefetch_related("labels").defer("steps", "ingredients")
        qs = filter_recipes(qs, self.request.GET)

        sort_field = self.SORT_FIELDS.get(self.request.GET.get("sort"), "title")
        # "title" als zweites Kriterium -> stabile Reihenfolge beim Blättern
        return qs.order_by(sort_field, "title")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        params = self.request.GET

        selected_categories = int_list(params.getlist("category_labels"))
        selected_events = int_list(params.getlist("event_labels"))

        labels = list(Label.objects.filter(label_type__in=["category", "event"]))
        context["labels_category"] = [l for l in labels if l.label_type == "category"]
        context["labels_event"] = [l for l in labels if l.label_type == "event"]
        context["selected_categories"] = selected_categories
        context["selected_events"] = selected_events

        # Count kommt vom Paginator, keine zusätzliche COUNT-Query
        context["result_count"] = context["paginator"].count

        context["filters_active"] = any([
            params.get("q"),
            params.get("max_duration"),
            params.get("max_working_duration"),
            selected_categories,
            selected_events,
        ])

        # Für Paginierungs-Links: aktuelle Filter ohne "page"
        query = params.copy()
        query.pop("page", None)
        context["querystring"] = query.urlencode()
        return context


# ---------------------------------------------------------------------------
# Detail / Kochen / Zufall
# ---------------------------------------------------------------------------

class DetailView(RecipeTextMixin, generic.DetailView):
    model = Recipe
    template_name = "recipes/recipe_detail.html"

    def post(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        self.object = recipe = self.get_object()

        if "cooked" in request.POST:
            Recipe.objects.filter(pk=recipe.pk).update(cooked_count=F("cooked_count") + 1)

        elif "undo_cooked" in request.POST:
            Recipe.objects.filter(pk=recipe.pk).update(
                cooked_count=Greatest(F("cooked_count") - 1, 0)
            )

        elif "add_to_plan" in request.POST:
            entry_date = parse_date(request.POST.get("date")) or date.today()
            add_recipe_to_plan(recipe, entry_date)
            return redirect_to_plan(monday_of(entry_date))

        return redirect(recipe.get_absolute_url())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = date.today()
        week_start = monday_of(today)
        context.update({
            "today": today,
            "week_dates": [week_start + timedelta(days=i) for i in range(7)],
        })
        return context


class RecipeCookView(RecipeTextMixin, generic.DetailView):
    model = Recipe
    template_name = "recipes/recipe_cook.html"

    def post(self, request, *args, **kwargs):
        recipe = self.get_object()
        if "cooked" in request.POST:
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            Recipe.objects.filter(pk=recipe.pk).update(cooked_count=F("cooked_count") + 1)
        return redirect(recipe.get_absolute_url())


class RandomRecipeView(TemplateView):
    template_name = "recipes/recipe_random.html"

    def post(self, request, *args, **kwargs):
        if "add_to_plan" in request.POST:
            recipe = get_object_or_404(Recipe, pk=to_int(request.POST.get("recipe_id")))
            entry_date = parse_date(request.POST.get("date")) or date.today()
            add_recipe_to_plan(recipe, entry_date)
            return redirect_to_plan(monday_of(entry_date))
        return self.get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Nur IDs laden, dann genau ein Rezept holen
        ids = list(
            filter_recipes(Recipe.objects.all(), self.request.GET)
            .values_list("id", flat=True)
        )
        context["recipe"] = (
            Recipe.objects.prefetch_related("labels").filter(pk=random.choice(ids)).first()
            if ids else None
        )
        return context


# ---------------------------------------------------------------------------
# Wochenplan
# ---------------------------------------------------------------------------

def _handle_plan_action(request):
    """Verarbeitet alle Änderungen am Wochenplan. Nur per POST erreichbar."""
    post = request.POST
    action = post.get("action")
    entry_id = to_int(post.get("entry_id"))
    start_date = parse_date(post.get("start_date"))

    if action == "add":
        recipe = get_object_or_404(Recipe, pk=to_int(post.get("recipe_id")))
        entry_date = parse_date(post.get("date")) or date.today()
        add_recipe_to_plan(recipe, entry_date)

    elif action == "comment":
        entry = get_object_or_404(WeeklyPlanEntry, pk=entry_id)
        entry.comment = post.get("comment", "").strip()
        entry.save(update_fields=["comment"])

    elif action == "move":
        entry = get_object_or_404(WeeklyPlanEntry, pk=entry_id)
        new_date = parse_date(post.get("date"))
        if new_date:
            entry.date = new_date
            entry.plan, _ = WeeklyPlan.objects.get_or_create(week_start=monday_of(new_date))
            entry.save(update_fields=["date", "plan"])

    elif action == "remove":
        get_object_or_404(WeeklyPlanEntry, pk=entry_id).delete()

    elif action == "clear":
        WeeklyPlanEntry.objects.all().delete()

    return redirect_to_plan(start_date)


@login_required
def weekly_plan_view(request):
    """Zeigt 7 Tage ab start_date. Änderungen laufen ausschließlich per POST."""
    if request.method == "POST":
        return _handle_plan_action(request)

    today = date.today()
    start_date = parse_date(request.GET.get("start_date")) or today
    week_dates = [start_date + timedelta(days=i) for i in range(7)]

    # Eine einzige Query für die ganze Woche (inkl. Rezept)
    entries = (
        WeeklyPlanEntry.objects
        .filter(date__range=(week_dates[0], week_dates[-1]))
        .select_related("recipe")
        .order_by("date", "id")
    )
    by_day = defaultdict(list)
    for entry in entries:
        by_day[entry.date].append(entry)

    weeks = [{
        "week_start": start_date,
        "week_dates": week_dates,
        "day_entries_list": [(d, by_day[d]) for d in week_dates],
    }]

    context = {
        "recipes": Recipe.objects.only("id", "title").order_by("title"),
        "weeks": weeks,
        "start_date": start_date,
        "prev_week": start_date - timedelta(days=7),
        "next_week": start_date + timedelta(days=7),
        "today": today,
    }
    from django.shortcuts import render
    return render(request, "recipes/weekly_plan.html", context)
