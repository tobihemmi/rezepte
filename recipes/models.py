from django.db import models
from django.urls import reverse
from django.utils.text import slugify
# Create your models here.

class Recipe(models.Model):
    title = models.CharField(
        max_length=200,
        help_text="Titel"
        )
    slug = models.SlugField(
        unique=True,
        blank=True
        )
    servings =models.PositiveIntegerField(
        help_text="Portionen"
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
        help_text="Zutaten"
    )
    steps = models.CharField(
        help_text="Anleitung"
    )
   
    cooked_count = models.PositiveIntegerField(
        default=0,
        help_text="So oft wurde das Rezept schon gekocht"
    )

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