from django.contrib import admin
from django.utils.html import format_html
from .models import Recipe, Label

@admin.register(Recipe)
class RecipeAdmin(admin.ModelAdmin):
    list_display = ("title", "duration_minutes", "temperature_celsius")
    search_fields = ("title",)
    prepopulated_fields = {"slug": ("title",)}
    filter_horizontal = ("labels",)
    readonly_fields = ("image_preview",)

    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" width="100" />', obj.image.url)
        return ""
    image_preview.short_description = "Vorschau"

    fieldsets = (
        (None, {
            "fields": ("title", "slug", "image", "image_preview")
        }),
        ("Back-/Kochinformationen", {
            "fields": ("duration_minutes", "temperature_celsius")
        }),
        ("Labels", {
            "fields": ("labels",)
        }),
        ("Zutaten", {
            "fields": ("servings", "ingredients",)
        }),
        ("Beschreibung", {
            "fields": ("steps",)
        }),
    )

@admin.register(Label)
class LabelAdmin(admin.ModelAdmin):
    list_display = ("name", "label_type")
    list_filter = ("label_type",)
    search_fields = ("name",)