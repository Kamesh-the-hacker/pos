from flask import Flask, render_template, request, redirect, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Product, Sale, SaleItem
from datetime import datetime, date
from sqlalchemy import func
from openpyxl import Workbook
from flask import send_file
import io

app = Flask(__name__)
app.secret_key = "secretkey"

# DATABASE
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

# INIT DB
with app.app_context():
    db.create_all()

    if not User.query.filter_by(username="admin").first():
        db.session.add(User(username="admin", password=generate_password_hash("123"), role="admin"))
        db.session.add(User(username="staff", password=generate_password_hash("123"), role="staff"))
        db.session.commit()

# LOGIN
@app.route("/", methods=["GET","POST"])
def login():

    if request.method == "POST":

        user = User.query.filter_by(username=request.form["username"]).first()

        if user and check_password_hash(user.password, request.form["password"]):

            session["role"] = user.role

            user_agent = request.headers.get('User-Agent')

            # 🔥 MOBILE STAFF → STOCK PAGE
            if user.role == "staff" and "Mobile" in user_agent:
                return redirect("/staff_stock")

            # 🔥 DESKTOP STAFF → BILLING
            if user.role == "staff":
                return redirect("/billing")

            # 🔥 ADMIN
            return redirect("/admin")

    return render_template("login.html")

# ---------------- SAVE BILL (FINAL FIXED) ----------------
@app.route("/save_bill", methods=["POST"])
def save_bill():

    data = request.json.get("bill", {})
    payment = request.json.get("payment", "Cash")

    # ❌ If empty cart
    if not data:
        return jsonify({"error": "No items in bill ❌"})

    try:
        # 🔥 STEP 1: Create Sale first
        sale = Sale(
            total=0,
            payment=payment,
            date=datetime.now()
        )

        db.session.add(sale)
        db.session.commit()   # 🔥 Needed to get ID

        # 🔥 STEP 2: Generate invoice (UNIQUE)
        sale.invoice_no = f"INV{sale.id:05d}"

        total = 0

        # 🔥 STEP 3: Loop items
        for name, item in data.items():

            qty = int(item["qty"])
            price = float(item["price"])

            product = Product.query.filter_by(name=name).first()

            if product:
                if product.stock < qty:
                    db.session.rollback()
                    return jsonify({"error": f"{name} stock insufficient ❌"})

                product.stock -= qty

            subtotal = qty * price
            total += subtotal

            db.session.add(SaleItem(
                sale_id=sale.id,
                product_name=name,
                qty=qty,
                price=price
            ))

        # 🔥 STEP 4: Update total
        sale.total = total

        db.session.commit()

        return jsonify({
            "status": "ok",
            "invoice": sale.invoice_no
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)})
    
@app.route("/export_sales")
def export_sales():

    if session.get("role") != "admin":
        return redirect("/")

    from_date = request.args.get("from_date")
    to_date = request.args.get("to_date")
    payment = request.args.get("payment")

    query = Sale.query

    # 🔥 DATE RANGE
    if from_date and to_date:
        start = datetime.strptime(from_date, "%Y-%m-%d")
        end = datetime.strptime(to_date, "%Y-%m-%d")
        query = query.filter(Sale.date >= start, Sale.date <= end)

    # 🔥 PAYMENT
    if payment and payment != "All":
        query = query.filter(Sale.payment == payment)

    sales = query.order_by(Sale.date.desc()).all()

    # 🔥 EXCEL
    from openpyxl import Workbook
    import io
    from flask import send_file

    wb = Workbook()
    ws = wb.active
    ws.title = "Sales Report"

    ws.append(["Invoice", "Date", "Time", "Total", "Payment"])

    for s in sales:
        ws.append([
            s.invoice_no,
            s.date.strftime("%d-%m-%Y"),
            s.date.strftime("%H:%M"),
            s.total,
            s.payment
        ])

    file = io.BytesIO()
    wb.save(file)
    file.seek(0)

    return send_file(
        file,
        as_attachment=True,
        download_name="sales_report.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
# ADMIN DASHBOARD
@app.route("/admin")
def admin():

    if session.get("role") != "admin":
        return redirect("/")

    today = date.today()
    month = datetime.now().strftime("%m")

    # 🔥 TOTAL TODAY
    total_today = db.session.query(func.sum(Sale.total))\
        .filter(func.date(Sale.date) == today).scalar() or 0

    # 🔥 CASH TODAY
    cash_today = db.session.query(func.sum(Sale.total))\
        .filter(
            func.date(Sale.date) == today,
            Sale.payment == "Cash"
        ).scalar() or 0

    # 🔥 UPI TODAY
    upi_today = db.session.query(func.sum(Sale.total))\
        .filter(
            func.date(Sale.date) == today,
            Sale.payment == "UPI"
        ).scalar() or 0

    # 🔥 MONTHLY SALES
    monthly_sales = db.session.query(func.sum(Sale.total))\
        .filter(func.strftime('%m', Sale.date) == month).scalar() or 0

    return render_template(
        "admin_dashboard.html",
        total_today=total_today,
        cash_today=cash_today,
        upi_today=upi_today,
        monthly_sales=monthly_sales
    )

# PRODUCTS
@app.route("/products")
def products():
    if session.get("role") != "admin":
        return redirect("/")
    return render_template("admin.html", products=Product.query.all())

# ADD PRODUCT
@app.route("/add_product", methods=["POST"])
def add_product():
    if session.get("role") != "admin":
        return redirect("/")

    barcode = request.form["barcode"].strip()

    # 🔥 if empty → keep None
    if barcode == "":
        barcode = None

    # 🔥 check duplicate ONLY if barcode exists
    if barcode and Product.query.filter_by(barcode=barcode).first():
        return "Barcode already exists!"

    product = Product(
        name=request.form["name"],
        barcode=barcode,
        price=float(request.form["price"]),
        stock=int(request.form["stock"])
    )

    db.session.add(product)
    db.session.commit()

    return redirect("/products")

# DELETE PRODUCT
@app.route("/delete/<int:id>")
def delete(id):
    if session.get("role") != "admin":
        return redirect("/")

    product = Product.query.get(id)
    db.session.delete(product)
    db.session.commit()
    return redirect("/products")

# SEARCH PRODUCT
@app.route("/search/<query>")
def search(query):
    product = Product.query.filter(
        (Product.barcode == query) |
        (Product.name.ilike(f"%{query}%"))
    ).first()

    if not product:
        return jsonify({"error":"not found"})

    if product.stock <= 0:
        return jsonify({"error":"Out of Stock ❌"})

    return jsonify({
        "name": product.name,
        "price": product.price,
        "stock": product.stock
    })

# AUTOCOMPLETE
@app.route("/search_suggestions/<query>")
def search_suggestions(query):
    products = Product.query.filter(
        Product.name.ilike(f"%{query}%"),
        Product.stock > 0
    ).limit(10).all()

    return jsonify([{
        "name": p.name,
        "price": p.price,
        "stock": p.stock
    } for p in products])

# SCAN PRODUCT
@app.route("/get_product/<barcode>")
def get_product(barcode):

    barcode = barcode.strip()

    # 🔥 find by barcode
    product = Product.query.filter_by(barcode=barcode).first()

    if not product:
        return jsonify({"error": "Product not found ❌"})

    if product.stock <= 0:
        return jsonify({"error": "Out of stock ❌"})

    return jsonify({
        "name": product.name,
        "price": product.price,
        "stock": product.stock
    })
@app.route("/update_stock", methods=["POST"])
def update_stock():
    if session.get("role") != "admin":
        return redirect("/")

    product_id = request.form["id"]
    change = int(request.form["change"])

    product = Product.query.get(product_id)

    if not product:
        return "Product not found"

    # 🔥 update stock
    product.stock += change

    if product.stock < 0:
        product.stock = 0

    db.session.commit()

    return redirect("/stock")
# BILLING PAGE
@app.route("/billing")
def billing():

    # 🔥 ONLY allow billing role
    if session.get("role") != "staff":
        return "Access denied ❌"

    # 🔥 BLOCK mobile access (optional)
    user_agent = request.headers.get('User-Agent')

    if "Mobile" in user_agent:
        return "Billing not allowed on mobile ❌"

    return render_template("billing.html")

@app.route("/staff_stock")
def staff_stock():

    # 🔥 Only staff allowed
    if session.get("role") != "staff":
        return "Access denied ❌"

    return render_template("staff_stock.html")

@app.route("/sales")
def sales():

    if session.get("role") != "admin":
        return redirect("/")

    from_date = request.args.get("from_date")
    to_date = request.args.get("to_date")
    payment = request.args.get("payment")

    query = Sale.query

    # 🔥 DATE RANGE FILTER
    if from_date and to_date:
        start = datetime.strptime(from_date, "%Y-%m-%d")
        end = datetime.strptime(to_date, "%Y-%m-%d")

        query = query.filter(Sale.date >= start, Sale.date <= end)

    # 🔥 PAYMENT FILTER
    if payment and payment != "All":
        query = query.filter(Sale.payment == payment)

    sales = query.order_by(Sale.date.desc()).all()

    return render_template("sales.html", sales=sales)
@app.route("/sale/<int:id>")
def sale_detail(id):
    if session.get("role") != "admin":
        return redirect("/")

    items = SaleItem.query.filter_by(sale_id=id).all()
    sale = Sale.query.get(id)

    return render_template("sale_detail.html", items=items, sale=sale)
# ---------------- STOCK PAGE ----------------
@app.route("/stock")
def stock():
    if session.get("role") != "admin":
        return redirect("/")
    return render_template("stock.html", products=Product.query.all())


# ---------------- EDIT PRODUCT ----------------
@app.route("/edit_product/<int:id>", methods=["GET", "POST"])
def edit_product(id):

    if session.get("role") != "admin":
        return redirect("/")

    product = Product.query.get(id)

    if not product:
        return "Product not found ❌"

    if request.method == "POST":

        product.name = request.form["name"]
        product.price = float(request.form["price"])
        product.stock = int(request.form["stock"])

        db.session.commit()

        return redirect("/products")

    return render_template("edit_product.html", product=product)

# INVOICE SEARCH
@app.route("/invoice/<invoice_no>")
def get_invoice(invoice_no):

    sale = Sale.query.filter_by(invoice_no=invoice_no).first()

    if not sale:
        return jsonify({"error":"not found"})

    items = SaleItem.query.filter_by(sale_id=sale.id).all()

    return jsonify({
        "invoice": sale.invoice_no,
        "total": sale.total,
        "items": [
            {
                "name": i.product_name,
                "qty": i.qty,
                "price": i.price
            } for i in items
        ]
    })

# USERS
@app.route("/users")
def users():
    if session.get("role") != "admin":
        return redirect("/")
    return render_template("users.html", users=User.query.all())

@app.route("/add_user", methods=["POST"])
def add_user():
    db.session.add(User(
        username=request.form["username"],
        password=generate_password_hash(request.form["password"]),
        role=request.form["role"]
    ))
    db.session.commit()
    return redirect("/users")

# LOGOUT
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# RUN
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
