from .models import Label # Ersetze Label durch dein tatsächliches Model

def recipe_filters(request):
    # Hier holst du die Daten, die das Modal immer braucht
    return {
        'labels_category': Label.objects.filter(label_type='category'), # Dein Filter-Logik
        'labels_event': Label.objects.filter(label_type='event'),
        # Falls du 'selected_categories' aus der URL brauchst:
        'selected_categories': request.GET.getlist('category_labels'),
        'selected_events': request.GET.getlist('event_labels'),
    }