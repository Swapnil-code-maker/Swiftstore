from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
import math
import requests
import os
import smtplib
import secrets
import time
from datetime import datetime
from datetime import date

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart






# -------------------- APP INIT --------------------
app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = "static/uploads"
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")

# -------------------- DATABASE CONFIG --------------------
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)

# -------------------- GLOBAL CACHE --------------------
reverse_geocode_cache = {}
# -------------------- EMAIL SERVICE --------------------
def send_email(to_email, subject, html_body):

    sender_email = "swiftstore.noreply.official@gmail.com"
    sender_password = os.environ.get("SWIFTSTORE_EMAIL_PASSWORD")

    print("DEBUG PASSWORD:", sender_password)

    if not sender_password:
        print("❌ EMAIL PASSWORD NOT SET")
        return

    msg = MIMEMultipart("alternative")
    msg["From"] = sender_email
    msg["To"] = to_email
    msg["Subject"] = subject

    msg.attach(MIMEText(html_body, "html"))

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.send_message(msg)
        server.quit()
        print("📧 Email sent successfully!")
    except Exception as e:
        print("Email error:", e)


def generate_otp():
    return str(secrets.randbelow(900000) + 100000)



# -------------------- DISTANCE FUNCTION --------------------
def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371  # km

    lat1 = math.radians(lat1)
    lon1 = math.radians(lon1)
    lat2 = math.radians(lat2)
    lon2 = math.radians(lon2)

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

    return R * c

def calculate_eta(distance_km, avg_speed_kmph=30):
    if distance_km is None:
        return None
    hours = distance_km / avg_speed_kmph
    minutes = int(hours * 60)
    return minutes


# -------------------- REVERSE GEOCODING --------------------
def get_address_from_coordinates(lat, lon):
    key = f"{round(lat, 4)}_{round(lon, 4)}"

    if key in reverse_geocode_cache:
        return reverse_geocode_cache[key]

    try:
        url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json"
        response = requests.get(
            url,
            headers={"User-Agent": "swiftstore-app"},
            timeout=5
        )
        data = response.json()
        address = data.get("display_name", "Address not found")
    except:
        address = "Address lookup failed"

    reverse_geocode_cache[key] = address
    return address

# -------------------- MODELS --------------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(50), nullable=False)

    company_name = db.Column(db.String(150))
    address = db.Column(db.String(300))
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)

    # Delivery specific
    full_name = db.Column(db.String(150))
    phone = db.Column(db.String(20))
    vehicle_type = db.Column(db.String(50))
    vehicle_number = db.Column(db.String(50))
    national_id = db.Column(db.String(200))
    is_verified = db.Column(db.Boolean, default=False)

    # Product relationship
    products = db.relationship("Product", backref="vendor", lazy=True)

    # Ledger relationship
    vendorledger_set = db.relationship(
        "VendorLedger",
        backref="vendor",
        lazy=True
    )



# -------------------- ORDER STATE MACHINE --------------------

ORDER_TRANSITIONS = {
    "placed": ["assigned", "cancelled"],
    "assigned": ["picked_up"],
    "picked_up": ["out_for_delivery"],
    "out_for_delivery": ["delivered"],
    "delivered": [],
    "cancelled": []
}
def can_transition(current_status, new_status):
    return new_status in ORDER_TRANSITIONS.get(current_status, [])



class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    price = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(100), nullable=False)
    image = db.Column(db.String(500), nullable=False)
    stock = db.Column(db.Integer, default=0)

    vendor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)


class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    delivery_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    total_price = db.Column(db.Float)
    status = db.Column(db.String(50), default="placed")

    customer_lat = db.Column(db.Float)
    customer_lon = db.Column(db.Float)

    delivery_otp = db.Column(db.String(6))
    otp_created_at = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

    items = db.relationship("OrderItem", backref="order", lazy=True)


class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    vendor_id = db.Column(
        db.Integer,
        db.ForeignKey('user.id'),
        nullable=False,
        index=True
    )

    quantity = db.Column(db.Integer, nullable=False)
    price_at_purchase = db.Column(db.Float, nullable=False)
    commission_rate = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(50), default="pending")

    product = db.relationship("Product")
    vendor = db.relationship("User", foreign_keys=[vendor_id])



class VendorLedger(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    vendor_id = db.Column(
        db.Integer,
        db.ForeignKey('user.id'),
        nullable=False
    )

    order_id = db.Column(db.Integer, nullable=False)

    gross_amount = db.Column(db.Float, nullable=False)
    commission = db.Column(db.Float, nullable=False)
    pg_fee = db.Column(db.Float, nullable=False)
    delivery_deduction = db.Column(db.Float, default=0)
    net_amount = db.Column(db.Float, nullable=False)

    status = db.Column(db.String(50), default="pending")  
    # pending → not paid
    # settled → paid to vendor

    created_at = db.Column(db.DateTime, default=datetime.utcnow)



class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.String(255), nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class DailyRevenue(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    revenue_date = db.Column(db.Date, unique=True, nullable=False)
    total_amount = db.Column(db.Float, default=0.0)

class Complaint(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=True)
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(50), default="open")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    customer = db.relationship("User")
    order = db.relationship("Order")

class Rating(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    delivery_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    rating = db.Column(db.Integer, nullable=False)  # 1 to 5
    feedback = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    order = db.relationship("Order")
    customer = db.relationship("User", foreign_keys=[customer_id])
    delivery = db.relationship("User", foreign_keys=[delivery_id])


def assign_delivery_agent(order):

    if order.customer_lat is None or order.customer_lon is None:
        return False

    deliveries = User.query.filter(
        User.role == "delivery",
        User.is_verified == True,
        User.latitude.isnot(None),
        User.longitude.isnot(None)
    ).all()

    if not deliveries:
        return False

    best_agent = None
    best_score = float("inf")

    # ------------------------------
    # PRE-CALCULATE DISTANCES ONCE
    # ------------------------------
    agent_data = []

    for agent in deliveries:

        distance = calculate_distance(
            agent.latitude,
            agent.longitude,
            order.customer_lat,
            order.customer_lon
        )

        active_orders_count = Order.query.filter(
            Order.delivery_id == agent.id,
            Order.status.in_(["assigned", "picked_up", "out_for_delivery"])
        ).count()

        # Skip overloaded agents
        if active_orders_count >= 2:
            continue

        # Get average rating (default 5 if no rating yet)
        avg_rating = db.session.query(
            db.func.avg(Rating.rating)
        ).filter_by(delivery_id=agent.id).scalar() or 5

        agent_data.append({
            "agent": agent,
            "distance": distance,
            "active_orders": active_orders_count,
            "rating": avg_rating
        })

    if not agent_data:
        return False

    # ------------------------------
    # NORMALIZATION VALUES
    # ------------------------------
    max_distance = max(a["distance"] for a in agent_data) or 1
    max_workload = 2
    max_rating = 5

    # ------------------------------
    # SCORE CALCULATION
    # ------------------------------
    for data in agent_data:

        normalized_distance = data["distance"] / max_distance
        workload_penalty = data["active_orders"] / max_workload
        rating_bonus = (max_rating - data["rating"]) / max_rating

        score = (
            0.6 * normalized_distance +
            0.25 * workload_penalty +
            0.15 * rating_bonus
        )

        if score < best_score:
            best_score = score
            best_agent = data["agent"]

    if not best_agent:
        return False

    # ------------------------------
    # ASSIGN DELIVERY
    # ------------------------------
    order.delivery_id = best_agent.id
    order.status = "assigned"
    db.session.commit()

    # ------------------------------
    # 📧 SEND EMAIL TO DELIVERY AGENT
    # ------------------------------
    html = build_email_template(
        "New Delivery Assigned 🚚",
        f"""
        Hi {best_agent.full_name},<br><br>
        You have been assigned a new delivery.<br><br>
        <strong>Order ID:</strong> #{order.id}<br>
        <strong>Total Amount:</strong> ₹{order.total_price}<br><br>
        Please login to your dashboard to view details.
        """
    )

    send_email(
        best_agent.email,
        "New Delivery Assigned - SwiftStore",
        html
    )

    return True





def build_email_template(title, message):

    return f"""
    <html>
    <body style="font-family: Arial, sans-serif; background-color:#f4f6f9; padding:20px;">
        <div style="max-width:600px;margin:auto;background:white;padding:30px;border-radius:10px;box-shadow:0 4px 12px rgba(0,0,0,0.1);">

            <div style="text-align:center;">
                <img src="https://image.similarpng.com/file/similarpng/very-thumbnail/2021/09/Online-shopping-logo-design-template-on-transparent-background-PNG.png"
                     width="80">
                <h2 style="color:#1e293b;margin-top:10px;">SwiftStore</h2>
            </div>

            <h3 style="color:#111827;">{title}</h3>

            <p style="color:#374151;font-size:15px;line-height:1.6;">
                {message}
            </p>

            <hr style="margin:30px 0;">

            <p style="font-size:12px;color:#9ca3af;text-align:center;">
                This is an automated message from SwiftStore.<br>
                Please do not reply directly to this email.
            </p>

        </div>
    </body>
    </html>
    """

# -------------------- COMMISSION ENGINE --------------------

def calculate_vendor_payout(order_item):
    gross = order_item.price_at_purchase * order_item.quantity

    commission = gross * order_item.commission_rate

    pg_rate = 0.02  # 2% payment gateway
    pg_fee = gross * pg_rate

    net = gross - commission - pg_fee

    return {
        "gross": gross,
        "commission": commission,
        "pg_fee": pg_fee,
        "net": net
    }



# -------------------- HOME --------------------
@app.route("/")
def entry():
    return render_template("entry.html")

# -------------------- CUSTOMER LOGIN --------------------
@app.route("/customer-login", methods=["GET", "POST"])
def customer_login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        user = User.query.filter_by(email=email, role="customer").first()

        if user and bcrypt.check_password_hash(user.password, password):
            session["user_id"] = user.id
            session["role"] = user.role
            return redirect(url_for("customer_dashboard"))

        flash("Invalid credentials!")
        return redirect(url_for("customer_login"))

    return render_template("customer_login.html")



@app.route("/submit-complaint", methods=["POST"])
def submit_complaint():

    if "user_id" not in session or session.get("role") != "customer":
        return redirect(url_for("customer_login"))

    order_id = request.form.get("order_id")
    message = request.form.get("message")

    if not message or len(message.strip()) < 5:
        flash("Complaint message too short.")
        return redirect(url_for("my_orders"))

    order = Order.query.get_or_404(order_id)

    # 🔒 Security check
    if order.customer_id != session["user_id"]:
        return "Unauthorized", 403

    complaint = Complaint(
        customer_id=session["user_id"],
        order_id=order.id,
        message=message.strip()
    )

    db.session.add(complaint)
    db.session.commit()

    flash("Complaint submitted successfully.")
    return redirect(url_for("my_orders"))



@app.route("/close-complaint/<int:id>", methods=["POST"])
def close_complaint(id):

    if "user_id" not in session or session.get("role") != "admin":
        return redirect(url_for("admin_login"))

    complaint = Complaint.query.get_or_404(id)
    complaint.status = "closed"
    db.session.commit()

    return redirect(url_for("admin_dashboard"))


# -------------------- ADMIN LOGIN --------------------
@app.route("/admin-login", methods=["GET", "POST"])
def admin_login():

    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        # 🔒 Whitelisted admin emails
        ALLOWED_ADMINS = ["swiftstore.noreply.official@gmail.com", "admin@swift.com"]


        if email not in ALLOWED_ADMINS:
            return "Access Denied", 403

        user = User.query.filter_by(email=email, role="admin").first()

        if user and bcrypt.check_password_hash(user.password, password):
            session["user_id"] = user.id
            session["role"] = user.role
            return redirect(url_for("admin_dashboard"))

        flash("Invalid admin credentials!")
        return redirect(url_for("admin_login"))

    return render_template("admin_login.html")


# -------------------- CUSTOMER DASHBOARD --------------------
from sqlalchemy import asc, desc

@app.route("/customer-dashboard")
def customer_dashboard():

    if "user_id" not in session or session.get("role") != "customer":
        return redirect(url_for("customer_login"))

    customer = User.query.get(session["user_id"])

    # 🔎 GET FILTER PARAMS
    selected_vendor_id = request.args.get("vendor_id", type=int)
    search_query = request.args.get("search", type=str)
    sort_by = request.args.get("sort", type=str)
    page = request.args.get("page", 1, type=int)

    # 🏗 Base Query
    query = Product.query

    # ---------------- Vendor Filter ----------------
    if selected_vendor_id:
        vendor_exists = User.query.filter_by(
            id=selected_vendor_id,
            role="vendor"
        ).first()

        if vendor_exists:
            query = query.filter_by(vendor_id=selected_vendor_id)
        else:
            query = query.filter(False)

    # ---------------- Search ----------------
    if search_query:
        query = query.filter(
            Product.name.ilike(f"%{search_query}%")
        )

    # ---------------- Sorting ----------------
    if sort_by == "price_low":
        query = query.order_by(asc(Product.price))
    elif sort_by == "price_high":
        query = query.order_by(desc(Product.price))

    # ---------------- Pagination ----------------
    per_page = 8
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    products = pagination.items

    vendors = User.query.filter_by(role="vendor").all()

    enriched_products = []

    for product in products:
        vendor = product.vendor

        if (
            customer.latitude is not None and
            customer.longitude is not None and
            vendor.latitude is not None and
            vendor.longitude is not None
        ):
            distance = calculate_distance(
                customer.latitude,
                customer.longitude,
                vendor.latitude,
                vendor.longitude
            )
        else:
            distance = None

        enriched_products.append({
            "id": product.id,
            "name": product.name,
            "price": product.price,
            "category": product.category,
            "image": product.image,
            "vendor_name": vendor.company_name or "Unknown Shop",
            "vendor_id": product.vendor_id,
            "distance": round(distance, 2) if distance else None,
            "stock": product.stock
        })

    # Distance sorting (after enrichment)
    if sort_by == "distance":
        enriched_products.sort(
            key=lambda x: x["distance"] if x["distance"] is not None else 9999
        )

    # 🔔 Fetch unread notifications for this customer
    notifications = Notification.query.filter_by(
        user_id=session["user_id"],
        is_read=False
    ).order_by(Notification.created_at.desc()).all()

    # Mark notifications as read
    for note in notifications:
        note.is_read = True

    db.session.commit()

    return render_template(
        "swift_store.html",
        products=enriched_products,
        vendors=vendors,
        customer=customer,
        selected_vendor_id=selected_vendor_id,
        search_query=search_query,
        sort_by=sort_by,
        pagination=pagination,
        notifications=notifications
    )




# -------------------- DELIVERY DASHBOARD --------------------

@app.route("/delivery-dashboard")
def delivery_dashboard():

    if "user_id" not in session or session.get("role") != "delivery":
        return redirect(url_for("delivery_login"))

    delivery = User.query.get(session["user_id"])

    if not delivery or not delivery.is_verified:
        return render_template("verification_pending.html")

    active_order = Order.query.filter(
        Order.delivery_id == delivery.id,
        Order.status.in_(["assigned", "picked_up", "out_for_delivery"])
    ).first()

    completed_orders = Order.query.filter_by(
        delivery_id=delivery.id,
        status="delivered"
    ).all()
    # ⭐ Calculate rating stats
    ratings = Rating.query.filter_by(delivery_id=delivery.id).all()

    total_ratings = len(ratings)
    avg_rating = round(
     sum(r.rating for r in ratings) / total_ratings,
     2
) if total_ratings > 0 else 0

    earnings = sum(
    25 + (order.total_price * 0.03)
    for order in completed_orders
)


    active_enriched = None

    if active_order:

        if (
            delivery.latitude is not None and
            delivery.longitude is not None and
            active_order.customer_lat is not None and
            active_order.customer_lon is not None
        ):
            distance = calculate_distance(
                delivery.latitude,
                delivery.longitude,
                active_order.customer_lat,
                active_order.customer_lon
            )
            distance = round(distance, 2)
            eta = calculate_eta(distance)
        else:
            distance = None
            eta = None

        active_enriched = {
            "order": active_order,
            "distance": distance,
            "eta": eta
        }

    return render_template(
    "delivery_dashboard.html",
    active_order=active_enriched,
    completed_orders=completed_orders,
    earnings=round(earnings, 2),
    avg_rating=avg_rating,
    total_ratings=total_ratings
)



@app.route("/admin-dashboard")
def admin_dashboard():

    if "user_id" not in session or session.get("role") != "admin":
        return redirect(url_for("admin_login"))

    # ---------------- DELIVERY ----------------
    pending_deliveries = User.query.filter_by(
        role="delivery",
        is_verified=False
    ).order_by(User.id.desc()).all()

    verified_deliveries = User.query.filter_by(
        role="delivery",
        is_verified=True
    ).order_by(User.id.desc()).all()

    # ---------------- USERS BY ROLE ----------------
    customers = User.query.filter_by(role="customer") \
        .order_by(User.id.desc()).all()

    vendors = User.query.filter_by(role="vendor") \
        .order_by(User.id.desc()).all()

    delivery_partners = User.query.filter_by(role="delivery") \
        .order_by(User.id.desc()).all()

    admins = User.query.filter_by(role="admin") \
        .order_by(User.id.desc()).all()

    # ---------------- ORDERS ----------------
    orders = Order.query.order_by(
        Order.created_at.desc()
    ).all()

    # ---------------- COMPLAINTS ----------------
    complaints = Complaint.query.order_by(
        Complaint.created_at.desc()
    ).all()

    # ---------------- STATS ----------------
    total_users = User.query.count()
    total_orders = Order.query.count()
    total_vendors = User.query.filter_by(role="vendor").count()
    total_customers = User.query.filter_by(role="customer").count()
    total_delivery = User.query.filter_by(role="delivery").count()

    total_revenue = db.session.query(
    db.func.sum(Order.total_price)
    ).filter(
    Order.status == "delivered"
    ).scalar() or 0
  

    # ---------------- DAILY REVENUE ----------------
    revenue_history = DailyRevenue.query.order_by(
    DailyRevenue.revenue_date.asc()
    ).all()

    # Prepare data for Chart.js
    revenue_dates = [str(day.revenue_date) for day in revenue_history]
    revenue_amounts = [day.total_amount for day in revenue_history]


    today = date.today()
    today_revenue = DailyRevenue.query.filter_by(
        revenue_date=today
    ).first()

    today_amount = today_revenue.total_amount if today_revenue else 0
    print("DATES:", revenue_dates)
    print("AMOUNTS:", revenue_amounts)
    return render_template(
        "admin_dashboard.html",

        # ORDERS & COMPLAINTS
        orders=orders,
        complaints=complaints,

        # DELIVERY
        pending_deliveries=pending_deliveries,
        verified_deliveries=verified_deliveries,
        delivery_partners=delivery_partners,

        # USERS BY ROLE
        customers=customers,
        vendors=vendors,
        admins=admins,

        # STATS
        total_users=total_users,
        total_orders=total_orders,
        total_vendors=total_vendors,
        total_customers=total_customers,
        total_delivery=total_delivery,
        total_revenue=round(total_revenue, 2),
        revenue_dates=revenue_dates,
        revenue_amounts=revenue_amounts,


        # REVENUE
        revenue_history=revenue_history,
        today_amount=round(today_amount, 2)

        

    )






# -------------------- APPROVE DELIVERY --------------------
@app.route("/approve-delivery/<int:user_id>", methods=["POST"])
def approve_delivery(user_id):

    if "user_id" not in session or session.get("role") != "admin":
        return redirect(url_for("admin_login"))

    delivery = User.query.get_or_404(user_id)

    if delivery.role != "delivery":
        return "Invalid user", 400

    delivery.is_verified = True
    db.session.commit()

    html = build_email_template(
    "You're Approved 🚚",
    f"""
    Hi {delivery.full_name},<br><br>
    Congratulations! 🎉<br><br>
    Your delivery partner account has been approved.<br><br>
    You can now login and start accepting deliveries.
    """
)

    send_email(
    delivery.email,
    "Delivery Partner Approved - SwiftStore",
    html
)


    return redirect(url_for("admin_dashboard"))


# -------------------- CANCEL ORDER --------------------
@app.route("/cancel-order/<int:order_id>", methods=["POST"])
def cancel_order(order_id):

    if "user_id" not in session or session.get("role") != "customer":
        return redirect(url_for("customer_login"))

    order = Order.query.get_or_404(order_id)

    # Security: Only order owner can cancel
    if order.customer_id != session["user_id"]:
        return "Unauthorized", 403

    # Allow cancel only before delivery is assigned
    if order.status in ["assigned", "out_for_delivery", "delivered"]:
        return "Order cannot be cancelled now", 400

    order.status = "cancelled"

    involved_vendors = set()

    # Cancel all order items + restore stock
    for item in order.items:
        item.status = "cancelled"

        product = Product.query.get(item.product_id)
        if product:
            product.stock += item.quantity

        involved_vendors.add(item.vendor_id)

    db.session.commit()

    # 🔔 Notify each vendor
    for vendor_id in involved_vendors:
        vendor = User.query.get(vendor_id)

        # Dashboard notification
        notification = Notification(
            user_id=vendor.id,
            message=f"Order #{order.id} was cancelled by customer."
        )
        db.session.add(notification)

        # 📧 Email notification
        html = build_email_template(
            "Order Cancelled ❌",
            f"""
            Hello {vendor.company_name},<br><br>
            Order <strong>#{order.id}</strong> has been cancelled by the customer.<br><br>
            Stock has been automatically restored.
            """
        )

        send_email(vendor.email, "Order Cancelled - SwiftStore", html)

    db.session.commit()

    return redirect(url_for("my_orders"))

# -------------------- PICKUP ORDER --------------------
@app.route("/pickup-order/<int:order_id>", methods=["POST"])
def pickup_order(order_id):

    if "user_id" not in session or session.get("role") != "delivery":
        return redirect(url_for("delivery_login"))

    order = Order.query.get_or_404(order_id)

    if order.delivery_id != session["user_id"]:
        return "Unauthorized", 403

    if not can_transition(order.status, "picked_up"):
     return "Invalid transition", 400

    order.status = "picked_up"
    db.session.commit()

    return redirect(url_for("delivery_dashboard"))
# -------------------- START DELIVERY --------------------

@app.route("/start-delivery/<int:order_id>", methods=["POST"])
def start_delivery(order_id):

    if "user_id" not in session or session.get("role") != "delivery":
        return redirect(url_for("delivery_login"))

    order = Order.query.get_or_404(order_id)

    if order.delivery_id != session["user_id"]:
        return "Unauthorized", 403

    if not can_transition(order.status, "out_for_delivery"):
     return "Invalid transition", 400


    order.status = "out_for_delivery"
    from datetime import datetime

    otp = generate_otp()
    order.delivery_otp = otp
    order.otp_created_at = datetime.utcnow()
    db.session.commit()

    customer = User.query.get(order.customer_id)

    html = build_email_template(
    "Delivery OTP 🔐",
    f"""
    Hi {customer.full_name or "Customer"},<br><br>
    Your delivery OTP for order <strong>#{order.id}</strong> is:<br><br>
    <h2 style="letter-spacing:3px;">{otp}</h2>
    <br>
    Please share this OTP with the delivery partner upon receiving your order.
    """
)

    send_email(customer.email, "Your Delivery OTP - SwiftStore", html)

    db.session.commit()

    return redirect(url_for("delivery_dashboard"))




# -------------------- VERIFY DELIVERY (OTP REQUIRED) --------------------
@app.route("/verify-delivery/<int:order_id>", methods=["POST"])
def verify_delivery(order_id):

    if "user_id" not in session or session.get("role") != "delivery":
        return redirect(url_for("delivery_login"))

    order = Order.query.get_or_404(order_id)

    # 🔒 Security: Only assigned delivery agent
    if order.delivery_id != session["user_id"]:
        return "Unauthorized", 403

    # 🔒 Only allow if order is out_for_delivery
    if order.status != "out_for_delivery":
        return "Invalid status", 400

    entered_otp = request.form.get("otp")

    if not entered_otp:
        flash("OTP required!", "error")
        return redirect(url_for("delivery_dashboard"))

    if not order.delivery_otp:
        flash("No OTP found for this order!", "error")
        return redirect(url_for("delivery_dashboard"))

    if order.delivery_otp != entered_otp:
        flash("Invalid OTP!", "error")
        return redirect(url_for("delivery_dashboard"))

    from datetime import datetime, timedelta

    if not order.otp_created_at or datetime.utcnow() - order.otp_created_at > timedelta(minutes=10):
        flash("OTP expired!", "error")
        return redirect(url_for("delivery_dashboard"))

    # ✅ MARK ORDER DELIVERED
    order.status = "delivered"

    # ---------------- CREATE LEDGER ENTRIES (FIXED LOOP) ----------------
    for item in order.items:

        payout = calculate_vendor_payout(item)

        ledger_entry = VendorLedger(
            vendor_id=item.vendor_id,
            order_id=order.id,
            gross_amount=payout["gross"],
            commission=payout["commission"],
            pg_fee=payout["pg_fee"],
            delivery_deduction=0,
            net_amount=payout["net"],
            status="pending"
        )

        db.session.add(ledger_entry)

    # 🔐 Clear OTP
    order.delivery_otp = None
    order.otp_created_at = None

    # ---------------- DAILY REVENUE UPDATE ----------------
    today = date.today()

    daily = DailyRevenue.query.filter_by(revenue_date=today).first()

    if not daily:
        daily = DailyRevenue(
            revenue_date=today,
            total_amount=order.total_price
        )
        db.session.add(daily)
    else:
        daily.total_amount += order.total_price

    # 🔔 Create dashboard notification
    notification = Notification(
        user_id=order.customer_id,
        message=f"Your order #{order.id} has been delivered successfully!"
    )

    db.session.add(notification)

    # 💾 Single commit at end (clean & atomic)
    db.session.commit()

    # 📧 Send confirmation email
    customer = User.query.get(order.customer_id)

    html = build_email_template(
        "Order Delivered Successfully 📦",
        f"""
        Hi {customer.full_name or "Customer"},<br><br>
        Your order <strong>#{order.id}</strong> has been delivered successfully.<br><br>
        Thank you for choosing SwiftStore ❤️
        """
    )

    send_email(
        customer.email,
        "Order Delivered - SwiftStore",
        html
    )

    return redirect(url_for("delivery_dashboard"))



# -------------------- DELIVERY LOGIN --------------------
@app.route("/delivery-login", methods=["GET", "POST"])
def delivery_login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        user = User.query.filter_by(email=email, role="delivery").first()

        if user and bcrypt.check_password_hash(user.password, password):
            session["user_id"] = user.id
            session["role"] = user.role
            return redirect(url_for("delivery_dashboard"))

        flash("Invalid credentials!")
        return redirect(url_for("delivery_login"))

    return render_template("delivery_login.html")

# -------------------- UPDATE DELIVERY LOCATION --------------------
@app.route("/update-delivery-location", methods=["POST"])
def update_delivery_location():

    if "user_id" not in session or session.get("role") != "delivery":
        return jsonify({"error": "Unauthorized"}), 403

    delivery = User.query.get(session["user_id"])
    data = request.get_json()

    if not data or "latitude" not in data or "longitude" not in data:
        return jsonify({"error": "Invalid data"}), 400

    delivery.latitude = data["latitude"]
    delivery.longitude = data["longitude"]

    db.session.commit()

    return jsonify({"success": True})


# -------------------- GET ACTIVE ORDER DATA --------------------
@app.route("/get-active-order-data")
def get_active_order_data():

    if "user_id" not in session or session.get("role") != "delivery":
        return jsonify({"error": "Unauthorized"}), 403

    delivery = User.query.get(session["user_id"])

    active_order = Order.query.filter(
        Order.delivery_id == delivery.id,
        Order.status.in_(["assigned", "picked_up", "out_for_delivery"])
    ).first()

    if not active_order:
        return jsonify({"active": False})

    if (
        delivery.latitude is not None and
        delivery.longitude is not None and
        active_order.customer_lat is not None and
        active_order.customer_lon is not None
    ):
        distance = calculate_distance(
            delivery.latitude,
            delivery.longitude,
            active_order.customer_lat,
            active_order.customer_lon
        )
        eta = calculate_eta(distance)
    else:
        distance = None
        eta = None

    return jsonify({
        "active": True,
        "distance": round(distance, 2) if distance else None,
        "eta": eta
    })



@app.route("/order-location-data/<int:order_id>")
def order_location_data(order_id):

    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 403

    order = Order.query.get_or_404(order_id)
    user = User.query.get(session["user_id"])

    # 🔒 Customer restriction
    if user.role == "customer" and order.customer_id != user.id:
        return jsonify({"error": "Forbidden"}), 403

    # 🔒 Delivery restriction
    if user.role == "delivery" and order.delivery_id != user.id:
        return jsonify({"error": "Forbidden"}), 403

    # 🔥 MULTI-VENDOR LOGIC
    order_items = OrderItem.query.filter_by(order_id=order.id).all()

    vendor_ids = set(item.vendor_id for item in order_items)

    vendors_data = []
    for vid in vendor_ids:
        vendor = User.query.get(vid)
        if vendor and vendor.latitude and vendor.longitude:
            vendors_data.append({
                "lat": vendor.latitude,
                "lon": vendor.longitude,
                "name": vendor.company_name
            })

    delivery = User.query.get(order.delivery_id) if order.delivery_id else None

    return jsonify({
        "customer": {
            "lat": order.customer_lat,
            "lon": order.customer_lon
        },
        "delivery": {
            "lat": delivery.latitude if delivery else None,
            "lon": delivery.longitude if delivery else None
        },
        "vendors": vendors_data,
        "status": order.status
    })






# -------------------- SAVE CUSTOMER LOCATION --------------------
@app.route("/save-customer-location", methods=["POST"])
def save_customer_location():
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 403

    customer = User.query.get(session["user_id"])
    data = request.get_json()

    customer.latitude = data["latitude"]
    customer.longitude = data["longitude"]
    customer.address = get_address_from_coordinates(
        customer.latitude,
        customer.longitude
    )

    db.session.commit()
    return jsonify({"success": True})

# -------------------- VENDOR LOGIN --------------------
@app.route("/vendor-login", methods=["GET", "POST"])
def vendor_login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        user = User.query.filter_by(email=email, role="vendor").first()

        if user and bcrypt.check_password_hash(user.password, password):
            session["user_id"] = user.id
            session["role"] = user.role
            return redirect(url_for("vendor_dashboard"))

        flash("Invalid credentials!")
        return redirect(url_for("vendor_login"))

    return render_template("vendor_login.html")

# -------------------- VENDOR DASHBOARD --------------------
@app.route("/vendor-dashboard", methods=["GET", "POST"])
def vendor_dashboard():

    if "user_id" not in session or session.get("role") != "vendor":
        return redirect(url_for("vendor_login"))

    vendor = User.query.get(session["user_id"])

    # ---------------- ADD PRODUCT ----------------
    if request.method == "POST":
        new_product = Product(
            name=request.form["name"],
            price=float(request.form["price"]),
            category=request.form["category"],
            image=request.form["image"],
            stock=int(request.form["stock"]),
            vendor_id=vendor.id
        )

        db.session.add(new_product)
        db.session.commit()
        return redirect(url_for("vendor_dashboard"))

    # ---------------- PRODUCTS ----------------
    products = Product.query.filter_by(vendor_id=vendor.id).all()

    # ---------------- ORDERS ----------------
    orders = (
        db.session.query(Order, OrderItem.status)
        .join(OrderItem)
        .filter(OrderItem.vendor_id == vendor.id)
        .order_by(Order.created_at.desc())
        .all()
    )

    from sqlalchemy import func
    from datetime import datetime, timedelta

    # ---------------- GROSS REVENUE ----------------
    gross_revenue = db.session.query(
        func.sum(VendorLedger.gross_amount)
    ).filter(
        VendorLedger.vendor_id == vendor.id
    ).scalar() or 0

    # ---------------- PLATFORM COMMISSION ----------------
    platform_commission = db.session.query(
        func.sum(VendorLedger.commission)
    ).filter(
        VendorLedger.vendor_id == vendor.id
    ).scalar() or 0

    # ---------------- TOTAL NET EARNINGS ----------------
    vendor_net_earnings = db.session.query(
        func.sum(VendorLedger.net_amount)
    ).filter(
        VendorLedger.vendor_id == vendor.id
    ).scalar() or 0

    # ---------------- PENDING SETTLEMENT ----------------
    pending_amount = db.session.query(
        func.sum(VendorLedger.net_amount)
    ).filter(
        VendorLedger.vendor_id == vendor.id,
        VendorLedger.status == "pending"
    ).scalar() or 0

    # ---------------- SETTLED AMOUNT ----------------
    settled_amount = db.session.query(
        func.sum(VendorLedger.net_amount)
    ).filter(
        VendorLedger.vendor_id == vendor.id,
        VendorLedger.status == "settled"
    ).scalar() or 0

    # ---------------- WEEKLY EARNINGS ----------------
    from datetime import datetime, timedelta

    today = datetime.utcnow()

    start_of_week = today - timedelta(days=today.weekday())
    start_of_week = start_of_week.replace(
    hour=0,
    minute=0,
    second=0,
    microsecond=0
)

    weekly_earnings = db.session.query(
    func.sum(VendorLedger.net_amount)
).filter(
    VendorLedger.vendor_id == vendor.id,
    VendorLedger.created_at >= start_of_week
).scalar() or 0

    # ---------------- MONTHLY REVENUE ----------------
    monthly_revenue = db.session.query(
        func.strftime("%Y-%m", VendorLedger.created_at).label("month"),
        func.sum(VendorLedger.net_amount).label("revenue")
    ).filter(
        VendorLedger.vendor_id == vendor.id
    ).group_by(
        func.strftime("%Y-%m", VendorLedger.created_at)
    ).order_by(
        func.strftime("%Y-%m", VendorLedger.created_at)
    ).all()

    return render_template(
        "vendor_dashboard.html",
        products=products,
        vendor=vendor,
        orders=orders,
        gross_revenue=round(gross_revenue, 2),
        platform_commission=round(platform_commission, 2),
        vendor_net_earnings=round(vendor_net_earnings, 2),
        monthly_revenue=monthly_revenue,
        pending_amount=round(pending_amount, 2),
        settled_amount=round(settled_amount, 2),
        weekly_earnings=round(weekly_earnings, 2),
        commission_rate=5
    )

# -------------------- SETTLE VENDOR PAYOUT --------------------
@app.route("/settle-vendor/<int:vendor_id>", methods=["POST"])
def settle_vendor(vendor_id):

    if "user_id" not in session or session.get("role") != "admin":
        return redirect(url_for("admin_login"))

    # Get all pending ledger entries for this vendor
    pending_entries = VendorLedger.query.filter_by(
        vendor_id=vendor_id,
        status="pending"
    ).all()

    if not pending_entries:
        flash("No pending amount to settle.", "warning")
        return redirect(url_for("admin_dashboard"))

    total_settled = 0

    for entry in pending_entries:
        total_settled += entry.net_amount
        entry.status = "settled"

    db.session.commit()

    flash(f"₹{round(total_settled,2)} settled successfully.", "success")

    return redirect(url_for("admin_dashboard"))




# -------------------- SAVE VENDOR LOCATION --------------------
@app.route("/save-vendor-location", methods=["POST"])
def save_vendor_location():
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 403

    vendor = User.query.get(session["user_id"])
    data = request.get_json()

    vendor.latitude = data["latitude"]
    vendor.longitude = data["longitude"]
    vendor.address = get_address_from_coordinates(
        vendor.latitude,
        vendor.longitude
    )

    db.session.commit()
    return jsonify({"success": True})

# -------------------- NEARBY VENDORS --------------------
@app.route("/nearby-vendors")
def nearby_vendors():

    if "user_id" not in session or session.get("role") != "customer":
        return redirect(url_for("customer_login"))

    customer = User.query.get(session["user_id"])

    if customer.latitude is None or customer.longitude is None:
        flash("Please allow location access first.")
        return redirect(url_for("customer_dashboard"))

    vendors = User.query.filter_by(role="vendor").all()
    nearby_list = []

    for vendor in vendors:
        if vendor.latitude is not None and vendor.longitude is not None:
            distance = calculate_distance(
                customer.latitude,
                customer.longitude,
                vendor.latitude,
                vendor.longitude
            )

            if distance <= 5:
                nearby_list.append({
                    "company_name": vendor.company_name,
                    "address": vendor.address,
                    "latitude": vendor.latitude,
                    "longitude": vendor.longitude,
                    "distance": round(distance, 2)
                })

    nearby_list.sort(key=lambda x: x["distance"])

    return render_template("nearby_vendors.html", vendors=nearby_list)


# -------------------- Create Order (Multi-Vendor Supported) --------------------
@app.route("/create-order", methods=["POST"])
def create_order():

    if "user_id" not in session or session.get("role") != "customer":
        return jsonify({"error": "Unauthorized"}), 403

    data = request.get_json()
    items = data["items"]

    customer = User.query.get(session["user_id"])

    new_order = Order(
        customer_id=customer.id,
        customer_lat=customer.latitude,
        customer_lon=customer.longitude,
        status="placed",
        total_price=0
    )

    db.session.add(new_order)
    db.session.flush()

    total_price = 0
    involved_vendors = set()

    for item in items:
        product = Product.query.get(item["product_id"])
        quantity = item["quantity"]

        if product.stock < quantity:
            db.session.rollback()
            return jsonify({"error": "Insufficient stock"}), 400

        product.stock -= quantity
        total_price += product.price * quantity

        involved_vendors.add(product.vendor_id)

        commission_rate = 0.05

        order_item = OrderItem(
        order_id=new_order.id,
        product_id=product.id,
        vendor_id=product.vendor_id,
        quantity=quantity,
        price_at_purchase=product.price,
        commission_rate=commission_rate
)


        db.session.add(order_item)

    new_order.total_price = total_price
    db.session.commit()

    # 🔔 Notify each vendor separately
    for vendor_id in involved_vendors:
        vendor = User.query.get(vendor_id)

        html = build_email_template(
            "New Order Received 🛒",
            f"""
            Hello {vendor.company_name},<br><br>
            You have items in Order <strong>#{new_order.id}</strong>.<br><br>
            Please login to prepare your items.
            """
        )

        send_email(vendor.email, "New Order - SwiftStore", html)


    # 📧 Send confirmation email to customer (NEW - nothing removed)
    customer_html = build_email_template(
        "Order Placed Successfully 🛒",
        f"""
        Hi {customer.full_name or "Customer"},<br><br>
        Your order <strong>#{new_order.id}</strong> has been placed successfully.<br><br>
        Vendors are reviewing your items and will approve shortly.<br><br>
        Thank you for choosing SwiftStore ❤️
        """
    )

    send_email(
        customer.email,
        "Order Placed - SwiftStore",
        customer_html
    )


    # 🔔 Create notification for customer (ONLY ONCE)
    notification = Notification(
        user_id=customer.id,
        message=f"Your order #{new_order.id} has been placed successfully!"
    )

    db.session.add(notification)
    db.session.commit()
    
    return jsonify({"success": True})





@app.route("/approve-order/<int:order_id>", methods=["POST"])
def approve_order(order_id):

    if "user_id" not in session or session.get("role") != "vendor":
        return redirect(url_for("vendor_login"))

    vendor_id = session["user_id"]
    order = Order.query.get_or_404(order_id)

    # 🚫 Block only if fully cancelled or delivered
    if order.status in ["cancelled", "delivered"]:
        return "Order already completed", 400

    # 🔐 Get this vendor's items
    vendor_items = OrderItem.query.filter_by(
        order_id=order.id,
        vendor_id=vendor_id
    ).all()

    if not vendor_items:
        return "Unauthorized", 403

    # 🚫 Prevent double approval
    already_approved = all(item.status == "approved" for item in vendor_items)
    if already_approved:
        return redirect(url_for("vendor_dashboard"))

    # ✅ Mark only this vendor's items as approved
    for item in vendor_items:
        if item.status == "pending":
            item.status = "approved"

    db.session.commit()

    # 🔎 Re-check item states AFTER updating
    pending_exists = OrderItem.query.filter_by(
        order_id=order.id,
        status="pending"
    ).first()

    approved_exists = OrderItem.query.filter_by(
        order_id=order.id,
        status="approved"
    ).first()

    rejected_exists = OrderItem.query.filter_by(
        order_id=order.id,
        status="rejected"
    ).first()

    # ❌ If ANY rejected → whole order rejected
    if rejected_exists:
        order.status = "rejected"
        db.session.commit()

    # ✅ If no pending AND no rejected → fully approved
    elif not pending_exists:
        order.status = "approved"

        # 🚚 Assign delivery if not already assigned
        if not order.delivery_id:
            assigned = assign_delivery_agent(order)
            if not assigned:
                return "No delivery agents available", 400

            # 📧 Notify customer
            customer = User.query.get(order.customer_id)

            html = build_email_template(
                "Your Order is Being Prepared 🚀",
                f"""
                Hi {customer.email},<br><br>
                All vendors have approved your order <strong>#{order.id}</strong>.<br><br>
                A delivery partner has been assigned and will pick up your items soon.
                """
            )

            send_email(customer.email, "Order Approved - SwiftStore", html)

        db.session.commit()

    return redirect(url_for("vendor_dashboard"))







@app.route("/reject-order/<int:order_id>", methods=["POST"])
def reject_order(order_id):

    if "user_id" not in session or session.get("role") != "vendor":
        return redirect(url_for("vendor_login"))

    vendor_id = session["user_id"]
    order = Order.query.get_or_404(order_id)

    # 🚫 Block if already delivered or cancelled
    if order.status in ["cancelled", "delivered"]:
        return "Order already completed", 400

    # 🔐 Get this vendor's items
    vendor_items = OrderItem.query.filter_by(
        order_id=order.id,
        vendor_id=vendor_id
    ).all()

    if not vendor_items:
        return "Unauthorized", 403

    # 🚫 Prevent double rejection
    already_rejected = all(item.status == "rejected" for item in vendor_items)
    if already_rejected:
        return redirect(url_for("vendor_dashboard"))

    # 🔄 Restore stock + mark only this vendor items rejected
    for item in vendor_items:
        if item.status != "rejected":
            product = Product.query.get(item.product_id)
            if product:
                product.stock += item.quantity
            item.status = "rejected"

    db.session.commit()

    # 🔎 Check remaining active items
    remaining_active = OrderItem.query.filter(
        OrderItem.order_id == order.id,
        OrderItem.status.in_(["pending", "approved"])
    ).first()

    # ❌ If NO items left → cancel full order
    if not remaining_active:
        order.status = "cancelled"
        db.session.commit()

        customer = User.query.get(order.customer_id)

        html = build_email_template(
            "Order Cancelled ❌",
            f"""
            Hi {customer.email},<br><br>
            All vendors rejected your order <strong>#{order.id}</strong>.<br><br>
            Your order has been cancelled.
            """
        )

        send_email(customer.email, "Order Cancelled - SwiftStore", html)

    else:
        # 🔔 Partial rejection email
        customer = User.query.get(order.customer_id)

        html = build_email_template(
            "Some Items Unavailable ⚠️",
            f"""
            Hi {customer.email},<br><br>
            Some items from your order <strong>#{order.id}</strong> were unavailable.<br><br>
            Other vendors are still processing remaining items.
            Please Cancel the order and Plan your order accordingly.
            """
        )

        send_email(customer.email, "Partial Order Update - SwiftStore", html)

    return redirect(url_for("vendor_dashboard"))




# -------------------- Delete product --------------------
@app.route("/delete-product/<int:product_id>", methods=["POST"])
def delete_product(product_id):

    if "user_id" not in session or session.get("role") != "vendor":
        return redirect(url_for("vendor_login"))

    product = Product.query.get_or_404(product_id)

    # Security: vendor can delete only their own product
    if product.vendor_id != session["user_id"]:
        return "Unauthorized", 403

    db.session.delete(product)
    db.session.commit()

    return redirect(url_for("vendor_dashboard"))

# -------------------- update product --------------------
@app.route("/update-stock/<int:product_id>", methods=["POST"])
def update_stock(product_id):

    if "user_id" not in session or session.get("role") != "vendor":
        return redirect(url_for("vendor_login"))

    product = Product.query.get_or_404(product_id)

    if product.vendor_id != session["user_id"]:
        return "Unauthorized", 403

    new_stock = int(request.form["stock"])

    if new_stock < 0:
        new_stock = 0

    product.stock = new_stock
    db.session.commit()

    return redirect(url_for("vendor_dashboard"))




# -------------------- LOGOUT --------------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("entry"))


# -------------------- REGISTER --------------------
@app.route("/register/<role>", methods=["GET", "POST"])
def register(role):

    # 🚫 BLOCK ADMIN REGISTRATION COMPLETELY
    if role == "admin":
        return "Access Denied", 403

    # 🔥 DELIVERY REGISTRATION
    if role == "delivery":

        if request.method == "POST":

            email = request.form["email"]
            password = request.form["password"]

            existing_user = User.query.filter_by(email=email).first()
            if existing_user:
                flash("Email already registered!")
                return redirect(url_for("delivery_login"))

            # Handle file upload
            file = request.files.get("national_id")
            filename = None

            if file and file.filename:
                filename = file.filename
                upload_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
                file.save(upload_path)

            hashed_password = bcrypt.generate_password_hash(password).decode("utf-8")

            new_user = User(
                email=email,
                password=hashed_password,
                role="delivery",
                full_name=request.form["full_name"],
                phone=request.form["phone"],
                vehicle_type=request.form["vehicle_type"],
                vehicle_number=request.form["vehicle_number"],
                national_id=filename,
                is_verified=False
            )

            db.session.add(new_user)
            db.session.commit()

            flash("Registration successful! Await verification.")
            return redirect(url_for("delivery_login"))

        return render_template("delivery_register.html")

    # 🔥 CUSTOMER & VENDOR REGISTRATION
    if request.method == "POST":

        email = request.form["email"]
        password = request.form["password"]

        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash("Email already registered!")
            return redirect(url_for(f"{role}_login"))

        hashed_password = bcrypt.generate_password_hash(password).decode("utf-8")

        new_user = User(
        email=email,
        password=hashed_password,
        role=role,
        full_name=request.form.get("full_name"),
        company_name=request.form.get("company_name"),
        address=request.form.get("address")
)


        db.session.add(new_user)
        db.session.commit()

        flash("Account created successfully! Please login.")
        return redirect(url_for(f"{role}_login"))

    return render_template("register.html", role=role)



@app.route("/get-products")
def get_products():

    products = Product.query.all()

    return jsonify([
        {
            "id": p.id,
            "stock": p.stock
        } for p in products
    ])

@app.route("/my-orders")
def my_orders():
    if "user_id" not in session or session.get("role") != "customer":
        return redirect(url_for("customer_login"))

    orders = Order.query.filter_by(
        customer_id=session["user_id"]
    ).order_by(Order.created_at.desc()).all()

    return render_template("customer_orders.html", orders=orders)

# -------------------- TRACK ORDER --------------------
@app.route("/track-order/<int:order_id>")
def track_order(order_id):

    if "user_id" not in session or session.get("role") != "customer":
        return redirect(url_for("customer_login"))

    order = Order.query.get_or_404(order_id)

    if order.customer_id != session["user_id"]:
        return "Unauthorized", 403

    delivery = User.query.get(order.delivery_id) if order.delivery_id else None

    # ✅ NEW: Get all vendors involved in this order
    vendor_ids = {item.vendor_id for item in order.items}
    vendors = User.query.filter(User.id.in_(vendor_ids)).all()

    return render_template(
        "track_order.html",
        order=order,
        delivery=delivery,
        vendors=vendors   # 🔥 pass list instead of single vendor
    )


@app.route("/reply-complaint/<int:id>", methods=["GET", "POST"])
def reply_complaint(id):

    if "user_id" not in session or session.get("role") != "admin":
        return redirect(url_for("admin_login"))

    complaint = Complaint.query.get_or_404(id)
    customer = User.query.get(complaint.customer_id)

    if request.method == "POST":

        reply_message = request.form.get("reply_message")

        if not reply_message or len(reply_message.strip()) < 5:
            flash("Reply message too short.")
            return redirect(url_for("reply_complaint", id=id))

        # 📧 Send email to customer
        html = build_email_template(
            "Regarding Your Complaint - SwiftStore",
            f"""
            Hello {customer.full_name or customer.email},<br><br>
            We have reviewed your complaint regarding Order <strong>#{complaint.order_id}</strong>.<br><br>
            <strong>Our Response:</strong><br>
            {reply_message}<br><br>
            Thank you for bringing this to our attention.
            """
        )

        send_email(customer.email, "Complaint Response - SwiftStore", html)

        complaint.status = "closed"
        db.session.commit()

        flash("Reply sent and complaint closed successfully.")

        return redirect(url_for("admin_dashboard"))  # ✅ FIXED

    return render_template("reply_complaint.html", complaint=complaint, customer=customer)

@app.route("/rate-order/<int:order_id>", methods=["POST"])
def rate_order(order_id):

    if "user_id" not in session or session.get("role") != "customer":
        return redirect(url_for("customer_login"))

    order = Order.query.get_or_404(order_id)

    if order.customer_id != session["user_id"]:
        return "Unauthorized", 403

    if order.status != "delivered":
        return "Order not delivered yet", 400

    existing = Rating.query.filter_by(order_id=order.id).first()
    if existing:
        return "Already rated", 400

    rating_value = int(request.form.get("rating"))
    feedback = request.form.get("feedback")

    if rating_value < 1 or rating_value > 5:
        return "Invalid rating", 400

    new_rating = Rating(
        order_id=order.id,
        customer_id=session["user_id"],
        delivery_id=order.delivery_id,
        rating=rating_value,
        feedback=feedback
    )

    db.session.add(new_rating)
    db.session.commit()

    return redirect(url_for("my_orders"))

@app.route("/submit-rating/<int:order_id>", methods=["POST"])
def submit_rating(order_id):

    if "user_id" not in session or session.get("role") != "customer":
        return redirect(url_for("customer_login"))

    order = Order.query.get_or_404(order_id)

    if order.customer_id != session["user_id"]:
        return "Unauthorized", 403

    if order.status != "delivered":
        return "Rating not allowed", 400

    rating_value = int(request.form.get("rating"))

    if rating_value < 1 or rating_value > 5:
        return "Invalid rating", 400

    existing = Rating.query.filter_by(
        order_id=order.id,
        customer_id=session["user_id"]
    ).first()

    if existing:
        return "Already rated", 400

    new_rating = Rating(
        order_id=order.id,
        customer_id=session["user_id"],
        delivery_id=order.delivery_id,
        rating=rating_value
    )

    db.session.add(new_rating)
    db.session.commit()

    flash("Thank you for your rating!")
    return redirect(url_for("my_orders"))

@app.route("/resend-otp/<int:order_id>", methods=["POST"])
def resend_otp(order_id):

    if "user_id" not in session or session.get("role") != "delivery":
        return redirect(url_for("delivery_login"))

    order = Order.query.get_or_404(order_id)

    if order.delivery_id != session["user_id"]:
        return "Unauthorized", 403

    if order.status != "out_for_delivery":
        return "Invalid status", 400

    # 🔐 Generate new OTP
    new_otp = generate_otp()

    from datetime import datetime
    order.delivery_otp = new_otp
    order.otp_created_at = datetime.utcnow()
    db.session.commit()

    # 📧 Send new OTP to customer
    customer = User.query.get(order.customer_id)

    html = build_email_template(
        "New Delivery OTP 🔐",
        f"""
        Hi {customer.full_name or "Customer"},<br><br>
        Your NEW delivery OTP for order <strong>#{order.id}</strong> is:<br><br>
        <h2 style="letter-spacing:3px;">{new_otp}</h2>
        <br>
        Please share this OTP with the delivery partner.
        """
    )

    send_email(
        customer.email,
        "New Delivery OTP - SwiftStore",
        html
    )

    flash("New OTP sent successfully!", "success")

    return redirect(url_for("delivery_dashboard"))




# -------------------- RUN --------------------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()

        admin_email = "swiftstore.noreply.official@gmail.com"
        admin_password = "admin123"

        admin_user = User.query.filter_by(email=admin_email).first()

        if admin_user:
            admin_user.password = bcrypt.generate_password_hash(admin_password).decode("utf-8")
            admin_user.role = "admin"  # 🔥 force role just in case
            print("🔁 Admin password updated!")
        else:
            admin_user = User(
                email=admin_email,
                password=bcrypt.generate_password_hash(admin_password).decode("utf-8"),
                role="admin"
            )
            db.session.add(admin_user)
            print("✅ Admin created!")

        db.session.commit()

    app.run(debug=True)

