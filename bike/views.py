from asgiref import server
from django.shortcuts import render, redirect, HttpResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from urllib3 import request

import bike
from bike.models import Bike, Booking
from bikerental.models import User
from customer.models import Customer
from django.contrib import messages
import easy_date
from datetime import date
from django.conf import settings
import smtplib
from email.mime.text import MIMEText
import razorpay

# Create your views here.
client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))

@login_required
def bikes_list(request):
    if request.method == 'POST':
        all_bikes = list(Bike.objects.all())
        all_booking = list(Booking.objects.all())

        selected_city = request.POST['selectedcity']

        pickup_date = str(request.POST['pickupDate'])
        dropoff_date = str(request.POST['dropoffDate'])

        #pickup_date = str to date
        pickup = easy_date.convert_from_string(pickup_date, '%Y-%m-%d', '%d-%m-%Y', date)
        dropoff = easy_date.convert_from_string(dropoff_date, '%Y-%m-%d', '%d-%m-%Y', date)

        request.session['pickupDate'] = pickup_date
        request.session['dropoffDate'] = dropoff_date


        selected_bikes=[]

        for b in all_bikes:
            if str(b.bike_location).lower() == str(selected_city).lower() and b.is_confirmed and not b.is_on_halt:
                selected_bikes.append(b)

        temp_bikes = selected_bikes.copy()

        for bike in temp_bikes:
            for booking in all_booking:
                if str(booking.bike.bike_id) == str(bike.bike_id):
                    if pickup <= booking.dropoff_date and dropoff >= booking.pickup_date:
                        print(bike)
                        selected_bikes.remove(bike)

        if len(selected_bikes) != 0:
            return render(request, 'bike/viewbike.html', {'selected_bikes': selected_bikes, 'pickup': pickup, 'dropoff': dropoff, 'selected_city': selected_city})

        return HttpResponse('<h1 class="display-1">No bike available in selected city</h1>')
    return redirect('home')

@login_required
def booking(request):
    if request.method == "POST":
        id = request.POST['book_button']
        bike = Bike.objects.get(bike_id=id)

        loggedin_userid = request.user.id
        customer = User.objects.get(id=loggedin_userid)

        pickup_date = easy_date.convert_from_string(request.session['pickupDate'], '%Y-%m-%d', '%d-%m-%Y', date)
        dropoff_date = easy_date.convert_from_string(request.session['dropoffDate'], '%Y-%m-%d', '%d-%m-%Y', date)

        total_days = (dropoff_date-pickup_date).days + 1
        total_price = int(bike.rent_per_day) * int(total_days)
        return render(request,'bike/booking.html',{'bike': bike, 'customer': customer, 'pickup_date': pickup_date, 'dropoff_date': dropoff_date, 'total_days': total_days, 'total_price': total_price});
    return redirect('home')

def confirm_booking(request):
    if request.method == "POST":
        id = request.POST['confirm_book_button']
        bike = Bike.objects.get(bike_id=id)
        loggedin_userid = request.user.id
        customer = Customer.objects.get(user_id=loggedin_userid)

        if customer.user.profile.driving_license.name == 'default.jpg' and customer.user.profile.id_proof.name == 'default.jpg':
            messages.warning(request, 'Upload your ID proof and driving license before booking ride!')
            return redirect('customer-profile')

        pickup_date = easy_date.convert_from_string(request.session['pickupDate'], '%Y-%m-%d', '%d-%m-%Y',
                                                    date)
        dropoff_date = easy_date.convert_from_string(request.session['dropoffDate'], '%Y-%m-%d', '%d-%m-%Y',
                                                     date)
        total_days = (dropoff_date - pickup_date).days + 1
        total_rent = int(bike.rent_per_day) * int(total_days)

        order_data = {
            "amount": total_rent * 100,
            "currency": "INR",
            "payment_capture": "1"
        }
        razorpay_order = client.order.create(data=order_data)
        context = {
            'order_id': razorpay_order['id'],
            'razorpay_key': settings.RAZORPAY_KEY_ID,
            'amount': total_rent * 100,
            'bike': bike,
            'customer_name': request.user.username,
            'customer_email': request.user.email,
        }
        return render(request, 'bike/razorpay_direct.html', context)
    return redirect('home')


@csrf_exempt  # Razorpay callback requires this
def payment_success(request, bike_id):
    bike = Bike.objects.get(bike_id=bike_id)
    loggedin_userid = request.user.id
    customer = Customer.objects.get(user_id=loggedin_userid)

    # 1. Retrieve details from session
    pickup_date_str = request.session['pickupDate']
    dropoff_date_str = request.session['dropoffDate']
    pickup_date = easy_date.convert_from_string(pickup_date_str, '%Y-%m-%d', '%d-%m-%Y', date)
    dropoff_date = easy_date.convert_from_string(dropoff_date_str, '%Y-%m-%d', '%d-%m-%Y', date)

    total_days = (dropoff_date - pickup_date).days + 1
    total_rent = int(bike.rent_per_day) * int(total_days)

    # 2. Save the Booking
    new_booking = Booking.objects.create(
        bike=bike,
        customer=customer,
        pickup_date=pickup_date_str,
        dropoff_date=dropoff_date_str,
        total_days=int(total_days),
        total_rent=int(total_rent)
    )

    # 3. Your SMTP Email Logic
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD)

        # Email to Customer
        msg_customer = MIMEText(f'Dear {request.user.username}, your booking for {bike.bike_model} is confirmed.')
        msg_customer['Subject'] = 'Booking Confirmed'
        msg_customer['From'] = settings.EMAIL_HOST_USER
        msg_customer['To'] = request.user.email
        server.sendmail(settings.EMAIL_HOST_USER, [request.user.email], msg_customer.as_string())

        # Email to Dealer
        msg_dealer = MIMEText(f'Your bike {bike.bike_model} has been booked.')
        msg_dealer['Subject'] = 'New Booking Received'
        msg_dealer['From'] = settings.EMAIL_HOST_USER
        msg_dealer['To'] = bike.owner.user.email
        server.sendmail(settings.EMAIL_HOST_USER, [bike.owner.user.email], msg_dealer.as_string())

        server.quit()
    except Exception as e:
        print("Email Error:", e)
    

    messages.success(request, 'Payment Successful! Your ride is booked.')
    return redirect('customer-myrides')
