from django.urls import path
from . import views

urlpatterns = [
    path('search/', views.search_view, name='search'),
    path('search/saved/', views.saved_search_list, name='saved_searches'),
    path('search/saved/<slug:slug>/', views.saved_search_detail, name='saved_search_detail'),
    path('search/saved/<int:pk>/delete/', views.delete_saved_search, name='delete_saved_search'),
    path('search/saved/<int:pk>/set-default/', views.set_default_search, name='set_default_search'),
    path('search/history/clear/', views.clear_search_history, name='clear_search_history'),
    path('search/debug/', views.debug_database, name='debug_database'),
]