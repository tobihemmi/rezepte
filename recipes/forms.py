from django import forms
from .models import Recipe, WeeklyPlanEntry


class RecipeForm(forms.ModelForm):
    class Meta:
        model = Recipe
        fields = [
            "title",
            "servings",
            "image",
            "labels",
            "duration_minutes",
            "working_time",
            "temperature_celsius",
            "ingredients",
            "steps",
            "external_link",
        ]
        widgets = {
            "ingredients": forms.Textarea(attrs={
                "rows": 4,
                "placeholder": "Zutaten durch Zeilenumbruch trennen"
            }),
            "steps": forms.Textarea(attrs={
                "rows": 6,
                "placeholder": "Schritte durch Zeilenumbruch trennen"
            }),
            "labels": forms.CheckboxSelectMultiple(),
        }

class WeeklyPlanEntryCommentForm(forms.ModelForm):
    class Meta:
        model = WeeklyPlanEntry
        fields = ["comment"]
        widgets = {
            "comment": forms.Textarea(attrs={"rows": 2, "placeholder": "Kommentar hinzufügen..."}),
        }