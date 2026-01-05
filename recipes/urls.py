from django.urls import path

from . import views

app_name="recipes"

urlpatterns = [
    path("", views.IndexView.as_view(), name="index"),
    path("add/", views.RecipeCreateView.as_view(), name='create'),
    path("random/", views.RandomRecipeView.as_view(), name="random"),
    path("<slug:slug>/delete/", views.RecipeDeleteView.as_view(), name="delete"),
    path('<slug:slug>/edit/', views.RecipeUpdateView.as_view(), name='update'),
    path("<slug:slug>/", views.DetailView.as_view(), name="detail"),
    path("<slug:slug>/cook/", views.RecipeCookView.as_view(), name="cook"),

]
