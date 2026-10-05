from django.urls import path

from . import views

app_name = 'inventory'

urlpatterns = [
    path('', views.stock_list, name='stock_list'),
    path('receive/', views.stock_receive, name='stock_receive'),
    path('adjust/', views.stock_adjust, name='stock_adjust'),
    path('lots/<int:pk>/', views.lot_detail, name='lot_detail'),
    path('usage/', views.movement_list, name='movement_list'),
    path('temperature/', views.temperature_list, name='temperature_list'),
    path('temperature/new/', views.temperature_create, name='temperature_create'),
]
