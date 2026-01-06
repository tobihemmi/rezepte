from django.db import models
from django.urls import reverse
from django.utils.text import slugify
from django.utils import timezone

# Rezeptmodell
class Recipe(models.Model):
    title = models.CharField(
        max_length=200,
        help_text="Titel"
    )
    slug = models.SlugField(
        unique=True,
        blank=True
    )
    servings = models.PositiveIntegerField(
        help_text="Portionen",
        null=True,
        blank=True,
    )
    image = models.ImageField(
        upload_to='recipes/',
        blank=True,
        null=True,
        help_text="Hauptbild"
    )
    labels = models.ManyToManyField(
        "Label",
        blank=True,
        help_text="Label"
    )
    duration_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Gesamtdauer des Rezepts in Minuten"
    )
    working_time = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Arbeitsdauer des Rezepts in Minuten"
    )
    temperature_celsius = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Back-/Ofentemperatur in °C (Ober-/Unterhitze)"
    )
    ingredients = models.CharField(
        null=True,
        blank=True,
        max_length=1000,  # Du solltest hier eine Länge definieren, falls du lange Zutatenlisten erwartest
        help_text="Zutaten"
    )
    steps = models.CharField(
        null=True,
        blank=True,
        max_length=1000,  # Ebenso für Schritte
        help_text="Anleitung"
    )
    cooked_count = models.PositiveIntegerField(
        default=0,
        help_text="So oft wurde das Rezept schon gekocht"
    )
    external_link = models.URLField(
        blank=True,
        null=True,
        help_text="Fügen Sie einen externen Link hinzu."
    )  # Neues Feld für den externen Link

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title)
            slug = base_slug
            counter = 1
            while Recipe.objects.filter(slug=slug).exists():
                counter += 1
                slug = f"{base_slug}-{counter}"
            self.slug = slug
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("recipes:detail", kwargs={"slug": self.slug})

    def __str__(self):
        return self.title

# Labelmodell
class Label(models.Model):
    EVENT = "event"
    CATEGORY = "category"

    LABEL_TYPES = [
        (EVENT, "Event"),
        (CATEGORY, "Kategorie"),
    ]

    name = models.CharField(max_length=100)
    label_type = models.CharField(max_length=20, choices=LABEL_TYPES)

    def __str__(self):
        return self.name

# Wochenplanmodell
class WeeklyPlan(models.Model):
    week_start = models.DateField(default=timezone.now)

    def __str__(self):
        return f"Wochenplan ab {self.week_start}"

# Wochentage für den Plan
DAY_CHOICES = [
    ('Monday', 'Montag'),
    ('Tuesday', 'Dienstag'),
    ('Wednesday', 'Mittwoch'),
    ('Thursday', 'Donnerstag'),
    ('Friday', 'Freitag'),
    ('Saturday', 'Samstag'),
    ('Sunday', 'Sonntag'),
]

# Modell für die Wochenplaneinträge
class WeeklyPlanEntry(models.Model):
    plan = models.ForeignKey(WeeklyPlan, related_name="entries", on_delete=models.CASCADE)
    day = models.CharField(max_length=10, choices=DAY_CHOICES)
    recipe = models.ForeignKey('Recipe', on_delete=models.CASCADE)

    class Meta:
        ordering = ['day', 'id']  # damit die Einträge in Tagesreihenfolge angezeigt werden

    def __str__(self):
        return f"{self.day}: {self.recipe.title}"
