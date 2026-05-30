from django.urls import path
from . import views

urlpatterns = [
    path('bikeslist/', views.bikes_list, name="bikes-list"),
    path('booking/', views.booking, name="bike-booking"),
    path('confirm-booking/', views.confirm_booking, name='bike-confirmbooking'),
    path('payment-success/<int:bike_id>/', views.payment_success, name='payment-success'),
]