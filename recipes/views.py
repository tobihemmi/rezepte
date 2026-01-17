from django.db.models import F, Q, Case, When, Value, IntegerField
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse_lazy, reverse
from django.views import generic, View
from django.views.generic import CreateView, DeleteView, TemplateView
import random

from .models import Recipe, Label, WeeklyPlan, WeeklyPlanEntry
from .forms import RecipeForm
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import redirect_to_login


from datetime import date, timedelta, datetime


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


class RecipeCreateView(LoginRequiredMixin, CreateView):
    model = Recipe
    form_class = RecipeForm
    template_name = "recipes/recipe_create.html"


class RecipeDeleteView(LoginRequiredMixin, DeleteView):
    model = Recipe
    success_url = reverse_lazy("recipes:index")
    template_name = "recipes/recipe_confirm_delete.html"
    slug_field = "slug"
    slug_url_kwarg = "slug"


class RecipeUpdateView(LoginRequiredMixin, View):
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
            qs = qs.order_by("cooked_count")
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
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        self.object = self.get_object()

        # === Cooked / Undo Cooked ===
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

        # === Rezept zum Wochenplan hinzufügen ===
        elif "add_to_plan" in request.POST:
            # Datum aus Formular
            new_date_str = request.POST.get("date")
            try:
                new_date = datetime.strptime(new_date_str, "%Y-%m-%d").date()
            except (ValueError, TypeError):
                new_date = date.today()

            # Montag der Woche
            week_monday = new_date - timedelta(days=new_date.weekday())
            plan, _ = WeeklyPlan.objects.get_or_create(week_start=week_monday)

            # Eintrag erstellen, falls nicht schon vorhanden
            WeeklyPlanEntry.objects.get_or_create(plan=plan, recipe=self.object, date=new_date)

            # Redirect auf Wochenplan mit der Woche des ausgewählten Tages
            return redirect(f"{reverse('recipes:weekly_plan')}?start_date={week_monday.strftime('%Y-%m-%d')}")


        return redirect(self.object.get_absolute_url())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        recipe = self.object
        context = super().get_context_data(**kwargs)

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

        # === Zusätzlicher Kontext für Wochenplanung ===
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        week_dates = [week_start + timedelta(days=i) for i in range(7)]

        context.update({
            "recipe": recipe,
            "base_servings": base_servings,
            "current_servings": current_servings,
            "ingredients_list": ing_list,
            "steps_list": st_list,
            "today": today,
            "week_dates": week_dates,  # für den Datepicker oder Button
        })
        return context



class RecipeCookView(generic.DetailView):
    model = Recipe
    template_name = "recipes/recipe_cook.html"
    slug_field = "slug"
    slug_url_kwarg = "slug"

    def post(self, request, *args, **kwargs):
        if "cooked" in request.POST and not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        self.object = self.get_object()
        if "cooked" in request.POST and request.user.is_authenticated:
            self.object.cooked_count = F("cooked_count") + 1
            self.object.save(update_fields=["cooked_count"])
        elif "back" in request.POST:
            pass
        return redirect(self.object.get_absolute_url())

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

    def post(self, request, *args, **kwargs):
        if "add_to_plan" in request.POST:
            # Rezept zum Wochenplan hinzufügen
            recipe_id = request.POST.get("recipe_id")  # Rezept ID aus dem Formular
            new_date_str = request.POST.get("date")
            try:
                new_date = datetime.strptime(new_date_str, "%Y-%m-%d").date()
            except (ValueError, TypeError):
                new_date = date.today()

            # Montag der Woche
            week_monday = new_date - timedelta(days=new_date.weekday())
            plan, _ = WeeklyPlan.objects.get_or_create(week_start=week_monday)

            # Rezept in den Plan einfügen
            try:
                recipe = get_object_or_404(Recipe, id=recipe_id)
                WeeklyPlanEntry.objects.get_or_create(plan=plan, recipe=recipe, date=new_date)
            except Recipe.DoesNotExist:
                # Fallback, falls das Rezept nicht gefunden wurde
                return redirect("recipes:random")  # Redirect zur Zufalls-Rezept-Seite

            # Redirect zum Wochenplan mit der Woche des ausgewählten Tages
            return redirect(f"{reverse('recipes:weekly_plan')}?start_date={week_monday.strftime('%Y-%m-%d')}")

        # Rückfall für die GET-Anfrage: Ein zufälliges Rezept anzeigen
        return self.get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Filter-Parameter aus der URL
        query = self.request.GET.get("q")
        max_duration = self.request.GET.get("max_duration")
        max_working_duration = self.request.GET.get("max_working_duration")

        qs = Recipe.objects.all()

        # Filter anwenden, wenn Parameter gesetzt sind
        if query:
            qs = qs.filter(
                Q(title__icontains=query) | 
                Q(ingredients__icontains=query)
            ).distinct()
        
        if max_duration:
            try:
                qs = qs.filter(duration_minutes__lte=int(max_duration))
            except ValueError:
                pass

        if max_working_duration:
            try:
                qs = qs.filter(working_time__lte=int(max_working_duration))
            except ValueError:
                pass

        # Konvertiere QuerySet in Liste
        recipes = list(qs)  # Konvertiert das QuerySet in eine Liste

        # Debugging-Ausgabe
        print(f"Gefundene Rezepte: {len(recipes)}")

        if recipes:  # Prüfen, ob Rezepte vorhanden sind
            context["recipe"] = random.choice(recipes)  # Ein zufälliges Rezept aus der Liste auswählen
        else:
            context["recipe"] = None  # Keine Rezepte vorhanden

        context["days"] = DAYS
        return context





NUM_WEEKS = 1  # Anzahl der Wochen, die angezeigt werden

@login_required
def weekly_plan_view(request):
    """
    Zeigt mehrere Wochen des Wochenplans an, montags startend.
    Bestehende Einträge werden automatisch den richtigen Wochen zugeordnet.
    """
    # === 1. Datum der aktuellen Ansicht bestimmen ===
    start_date_str = request.GET.get("start_date")
    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        except ValueError:
            start_date = date.today()
    else:
        start_date = date.today()

    # Montag der ersten angezeigten Woche
    first_monday = start_date - timedelta(days=start_date.weekday())

    # === 2. Aktion verarbeiten (add, comment, move, remove, clear) ===
    params = request.GET.copy()
    action = params.get("action")
    entry_id = params.get("entry_id")
    recipe_id = params.get("recipe_id")
    new_date_str = params.get("date")

    if action == "add" and recipe_id and new_date_str:
        recipe = get_object_or_404(Recipe, id=recipe_id)
        try:
            entry_date = datetime.strptime(new_date_str, "%Y-%m-%d").date()
        except ValueError:
            entry_date = date.today()
        week_monday = entry_date - timedelta(days=entry_date.weekday())
        plan, _ = WeeklyPlan.objects.get_or_create(week_start=week_monday)
        WeeklyPlanEntry.objects.create(plan=plan, recipe=recipe, date=entry_date)

        for key in ["action", "recipe_id", "date", "entry_id"]:
            params.pop(key, None)
        return redirect(f"{reverse('recipes:weekly_plan')}?{params.urlencode()}")

    elif action == "comment" and entry_id:
        entry = get_object_or_404(WeeklyPlanEntry, id=entry_id)
        entry.comment = params.get("comment", "").strip()
        entry.save()
        for key in ["action", "entry_id", "comment"]:
            params.pop(key, None)
        return redirect(f"{reverse('recipes:weekly_plan')}?{params.urlencode()}")

    elif action == "move" and entry_id and new_date_str:
        entry = get_object_or_404(WeeklyPlanEntry, id=entry_id)
        try:
            new_date = datetime.strptime(new_date_str, "%Y-%m-%d").date()
        except ValueError:
            new_date = entry.date

        start_date_redirect = params.get("start_date", None)  # von Hidden Input
        # Plan für das neue Datum erstellen falls nötig
        week_monday = new_date - timedelta(days=new_date.weekday())
        plan, _ = WeeklyPlan.objects.get_or_create(week_start=week_monday)
        entry.plan = plan
        entry.date = new_date
        entry.save()
        
        # Redirect: die aktuell angezeigte Woche behalten
        for key in ["action", "entry_id", "date", "recipe_id"]:
            params.pop(key, None)
        if start_date_redirect:
            params["start_date"] = start_date_redirect

        return redirect(f"{reverse('recipes:weekly_plan')}?{params.urlencode()}")


    elif action == "remove" and entry_id:
        entry = get_object_or_404(WeeklyPlanEntry, id=entry_id)
        entry.delete()
        for key in ["action", "entry_id", "date", "recipe_id"]:
            params.pop(key, None)
        return redirect(f"{reverse('recipes:weekly_plan')}?{params.urlencode()}")

    elif action == "clear":
        WeeklyPlanEntry.objects.all().delete()
        for key in ["action", "recipe_id", "date", "entry_id"]:
            params.pop(key, None)
        return redirect(f"{reverse('recipes:weekly_plan')}?{params.urlencode()}")

    # === 3. Bestehende Einträge automatisch den Wochen zuordnen ===
    for entry in WeeklyPlanEntry.objects.all():
        week_monday = entry.date - timedelta(days=entry.date.weekday())
        if entry.plan is None or entry.plan.week_start != week_monday:
            plan, _ = WeeklyPlan.objects.get_or_create(week_start=week_monday)
            entry.plan = plan
            entry.save()

    # === 4. Wochen für die Ansicht vorbereiten ===
    weeks = []
    for w in range(NUM_WEEKS):
        week_monday = first_monday + timedelta(weeks=w)
        week_dates = [week_monday + timedelta(days=i) for i in range(7)]
        plan, _ = WeeklyPlan.objects.get_or_create(week_start=week_monday)
        day_entries_list = [(d, plan.entries.filter(date=d)) for d in week_dates]
        weeks.append({
            "week_start": week_monday,
            "week_dates": week_dates,
            "day_entries_list": day_entries_list
        })

    # === 5. Navigation ===
    prev_week = first_monday - timedelta(days=7)
    next_week = first_monday + timedelta(days=7 * NUM_WEEKS)

    today = date.today()

    context = {
        "recipes": Recipe.objects.all(),
        "weeks": weeks,
        "prev_week": prev_week,
        "next_week": next_week,
        "today": today,  # <-- neu
    }
    return render(request, "recipes/weekly_plan.html", context)
