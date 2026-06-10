from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

# ---------------- USER ----------------
class User(db.Model):
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(200))
    role = db.Column(db.String(10))


# ---------------- PRODUCT ----------------
class Product(db.Model):
    __tablename__ = "product"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    barcode = db.Column(db.String(50), unique=True, nullable=True)
    price = db.Column(db.Float)
    stock = db.Column(db.Integer)


# ---------------- SALE ----------------
class Sale(db.Model):
    __tablename__ = "sale"

    id = db.Column(db.Integer, primary_key=True)
    invoice_no = db.Column(db.String(20), unique=True)

    total = db.Column(db.Float)

    # 🔥 NEW FIELD (IMPORTANT)
    payment = db.Column(db.String(20), default="Cash")

    date = db.Column(db.DateTime, default=datetime.utcnow)


# ---------------- SALE ITEMS ----------------
class SaleItem(db.Model):
    __tablename__ = "sale_item"

    id = db.Column(db.Integer, primary_key=True)

    sale_id = db.Column(db.Integer)

    product_name = db.Column(db.String(100))
    qty = db.Column(db.Integer)
    price = db.Column(db.Float)