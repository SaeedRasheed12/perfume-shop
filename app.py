from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import os
from werkzeug.utils import secure_filename
from functools import wraps
import random
import string

def generate_tracking_code():
    return 'BA' + ''.join(random.choices(string.digits, k=6))

app = Flask(__name__)
app.secret_key = 'YOUR_SUPER_SECRET_KEY_CHANGE_THIS'

# -----------------------------
# 📌 Upload folders
# -----------------------------
UPLOAD_FOLDER = 'static/uploads/'
BANNER_FOLDER = 'static/uploads/banners/'
BACKGROUND_FOLDER = 'static/uploads/backgrounds/'

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(BANNER_FOLDER, exist_ok=True)
os.makedirs(BACKGROUND_FOLDER, exist_ok=True)

# -----------------------------
# 📌 Database Connection
# -----------------------------
def get_db_connection():
    conn = sqlite3.connect('db.sqlite3')
    conn.row_factory = sqlite3.Row
    return conn

# -----------------------------
# 🏠 Homepage
# -----------------------------
@app.route('/')
def index():
    conn = get_db_connection()
    products = conn.execute('SELECT * FROM products').fetchall()
    categories = conn.execute('SELECT * FROM categories').fetchall()
    banner = conn.execute('SELECT * FROM banners ORDER BY id DESC LIMIT 1').fetchone()
    background = conn.execute('SELECT * FROM backgrounds ORDER BY id DESC LIMIT 1').fetchone()
    logo = conn.execute('SELECT * FROM logos ORDER BY id DESC LIMIT 1').fetchone()  # ✅ Fetch logo
    conn.close()
    return render_template(
        'index.html',
        products=products,
        banner=banner,
        background=background,
        categories=categories,
        logo=logo  # ✅ Pass logo to template
    )

# -----------------------------
# 📄 Product Detail
# -----------------------------
@app.route('/product/<int:product_id>')
def product_detail(product_id):
    conn = get_db_connection()
    product = conn.execute('SELECT * FROM products WHERE id = ?', (product_id,)).fetchone()
    conn.close()
    if not product:
        flash('Product not found.')
        return redirect(url_for('index'))
    return render_template('product_detail.html', product=product)

# -----------------------------
# ✅ Cart routes
# -----------------------------
@app.route('/add_to_cart/<int:product_id>')
def add_to_cart(product_id):
    conn = get_db_connection()
    product = conn.execute('SELECT * FROM products WHERE id = ?', (product_id,)).fetchone()
    conn.close()
    if not product:
        flash('Product not found.')
        return redirect(url_for('index'))

    item = {'id': product['id'], 'name': product['name'], 'price': product['price'], 'quantity': 1}
    cart = session.get('cart', [])
    for p in cart:
        if p['id'] == product_id:
            p['quantity'] += 1
            break
    else:
        cart.append(item)
    session['cart'] = cart
    flash(f"Added {product['name']} to cart!")
    return redirect(url_for('cart'))

@app.route('/cart')
def cart():
    cart = session.get('cart', [])
    total = sum(item['price'] * item['quantity'] for item in cart)
    return render_template('cart.html', cart=cart, total=total)

@app.route('/remove_from_cart/<int:product_id>')
def remove_from_cart(product_id):
    cart = session.get('cart', [])
    cart = [item for item in cart if item['id'] != product_id]
    session['cart'] = cart
    flash('Item removed from cart.')
    return redirect(url_for('cart'))

@app.route('/track', methods=['GET', 'POST'])
def track_order():
    order = None

    if request.method == 'POST':
        tracking_code = request.form['tracking_code'].strip()

        conn = get_db_connection()
        order = conn.execute(
            'SELECT * FROM orders WHERE tracking_code = ?', (tracking_code,)
        ).fetchone()
        conn.close()

        if not order:
            flash('Tracking code not found.')

    return render_template('track.html', order=order)

@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    cart = session.get('cart', [])
    subtotal = sum(item['price'] * item['quantity'] for item in cart)
    discount_amount = 0
    coupon_code = ''
    delivery_fee = 0  # default

    if request.method == 'POST':
        if not cart:
            flash('Your cart is empty!')
            return redirect(url_for('cart'))

        name = request.form['name']
        address = request.form['address']
        phone = request.form['phone']
        coupon_code = request.form.get('coupon_code', '').strip().upper()

        conn = get_db_connection()
        # ✅ Pull delivery fee from settings if it exists
        delivery_row = conn.execute("SELECT value FROM settings WHERE key = 'delivery_fee'").fetchone()
        delivery_fee = float(delivery_row['value']) if delivery_row else 0

        if coupon_code:
            coupon = conn.execute(
                'SELECT * FROM coupons WHERE code = ?', (coupon_code,)
            ).fetchone()

            if coupon:
                if coupon['type'] == 'percentage':
                    discount_amount = subtotal * (coupon['discount'] / 100)
                    flash(f"Coupon applied! You saved {coupon['discount']}% off.")
                elif coupon['type'] == 'fixed':
                    discount_amount = coupon['discount']
                    flash(f"Coupon applied! You saved PKR {discount_amount:.2f}.")
                elif coupon['type'] == 'free_delivery':
                    delivery_fee = 0
                    flash("Coupon applied! Free delivery activated.")
                else:
                    flash('Unknown coupon type.')
            else:
                conn.close()
                flash('Invalid coupon code! Please try again.')
                return redirect(url_for('checkout'))

        conn.close()

        final_total = max(0, subtotal + delivery_fee - discount_amount)

        tracking_code = generate_tracking_code()

        conn = get_db_connection()
        # ✅ Save coupon, discount, tracking code
        conn.execute(
            '''
            INSERT INTO orders (name, address, phone, tracking_code, coupon_code, discount)
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
            (name, address, phone, tracking_code, coupon_code, discount_amount)
        )
        order_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]

        for item in cart:
            conn.execute(
                'INSERT INTO order_items (order_id, product_id, quantity) VALUES (?, ?, ?)',
                (order_id, item['id'], item['quantity'])
            )

        conn.commit()
        conn.close()

        session.pop('cart', None)

        return redirect(url_for('invoice', order_id=order_id))

    # GET request: show checkout page
    return render_template(
        'checkout.html',
        subtotal=subtotal,
        discount=discount_amount,
        delivery_fee=delivery_fee,
        total=subtotal + delivery_fee - discount_amount
    )

@app.route('/thankyou')
def thankyou():
    tracking_code = request.args.get('tracking_code')
    return render_template('thankyou.html', tracking_code=tracking_code)

# -----------------------------
# ✉️ Static pages
# -----------------------------
@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')

# -----------------------------
# ✅ Admin login
# -----------------------------
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_logged_in'):
            flash('Please login as admin.')
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        if request.form['username'] == 'admin' and request.form['password'] == '12345':
            session['admin_logged_in'] = True
            flash('Logged in successfully.')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid credentials.')
    return render_template('admin_login.html')

@app.route('/know-your-perfume')
def know_your_perfume():
    conn = get_db_connection()
    image = conn.execute('SELECT * FROM know_your_perfume ORDER BY id DESC LIMIT 1').fetchone()
    conn.close()
    return render_template('know_your_perfume.html', know_your_perfume=image)

@app.route('/admin/upload_know_your_perfume', methods=['POST'])
@login_required
def upload_know_your_perfume():
    file = request.files['know_your_perfume_image']
    if file and file.filename:
        filename = secure_filename(file.filename)
        file.save(os.path.join('static/uploads', filename))

        conn = get_db_connection()
        conn.execute('DELETE FROM know_your_perfume')  # keep only one
        conn.execute('INSERT INTO know_your_perfume (filename) VALUES (?)', (filename,))
        conn.commit()
        conn.close()

        flash('Know Your Perfume guide image uploaded.')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/update_delivery_fee', methods=['POST'])
@login_required
def set_delivery_fee():  # <-- ✅ different name, same endpoint URL
    fee = request.form['delivery_fee']
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    conn.execute('''
        INSERT INTO settings (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value
    ''', ('delivery_fee', fee))
    conn.commit()
    conn.close()
    flash(f'Delivery fee updated to PKR {fee}')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    conn = get_db_connection()

    products = conn.execute('SELECT * FROM products').fetchall()
    banner = conn.execute('SELECT * FROM banners ORDER BY id DESC LIMIT 1').fetchone()
    background = conn.execute('SELECT * FROM backgrounds ORDER BY id DESC LIMIT 1').fetchone()
    categories = conn.execute('SELECT * FROM categories').fetchall()

    # ✅ Fetch current delivery fee
    fee_row = conn.execute("SELECT value FROM settings WHERE key = 'delivery_fee'").fetchone()
    delivery_fee = float(fee_row['value']) if fee_row else 0

    # ✅ Fetch current Top Banner announcement text
    banner_row = conn.execute("SELECT value FROM settings WHERE key = 'top_banner'").fetchone()
    top_banner = banner_row['value'] if banner_row else ''

    # ✅ Fetch Know Your Perfume image
    know_your_perfume = conn.execute(
        'SELECT * FROM know_your_perfume ORDER BY id DESC LIMIT 1'
    ).fetchone()

    conn.close()

    return render_template(
        'admin_dashboard.html',
        products=products,
        banner=banner,
        background=background,
        categories=categories,
        delivery_fee=delivery_fee,             # ✅ Delivery fee
        know_your_perfume=know_your_perfume,   # ✅ Guide image
        top_banner=top_banner                  # ✅ New! Top Banner text
    )

@app.route('/admin/add_coupon', methods=['POST'])
@login_required
def add_coupon():
    code = request.form['code'].strip().upper()
    discount = float(request.form['discount'])
    type_ = request.form['type']
    description = request.form.get('description')

    conn = get_db_connection()
    conn.execute(
        'INSERT INTO coupons (code, discount, type, description) VALUES (?, ?, ?, ?)',
        (code, discount, type_, description)
    )
    conn.commit()
    conn.close()

    flash('Coupon added successfully.')
    return redirect(url_for('admin_dashboard'))

# -----------------------------
# ➕ Add Product
# -----------------------------
@app.route('/admin/add', methods=['POST'])
@login_required
def add_product():
    name = request.form['name']
    description = request.form['description']
    price = float(request.form['price'])
    category_id = int(request.form['category_id'])
    image_file = request.files['image']
    filename = secure_filename(image_file.filename)
    image_file.save(os.path.join(UPLOAD_FOLDER, filename))

    conn = get_db_connection()
    conn.execute('''
        INSERT INTO products (name, description, price, image, category_id)
        VALUES (?, ?, ?, ?, ?)
    ''', (name, description, price, filename, category_id))
    conn.commit()
    conn.close()
    flash('Product added.')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/update_delivery_fee', methods=['POST'])
@login_required
def update_delivery_fee():
    new_fee = request.form['delivery_fee']
    conn = get_db_connection()
    conn.execute('''
        INSERT INTO settings (key, value)
        VALUES ('delivery_fee', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
    ''', (new_fee,))
    conn.commit()
    conn.close()
    flash('Delivery fee updated!')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete/<int:product_id>')
@login_required
def delete_product(product_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM products WHERE id = ?', (product_id,))
    conn.commit()
    conn.close()
    flash('Product deleted.')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete_order/<int:order_id>')
@login_required
def delete_order(order_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM orders WHERE id = ?', (order_id,))
    conn.execute('DELETE FROM order_items WHERE order_id = ?', (order_id,))
    conn.commit()
    conn.close()
    flash(f'Order #{order_id} deleted.')
    return redirect(url_for('admin_orders'))

@app.route('/update_order_status/<int:order_id>', methods=['POST'])
def update_order_status(order_id):
    new_status = request.form['status']

    conn = get_db_connection()
    conn.execute(
        'UPDATE orders SET status = ? WHERE id = ?',
        (new_status, order_id)
    )
    conn.commit()
    conn.close()

    flash('Order status updated.')
    return redirect(url_for('admin_orders'))
# -----------------------------
# 📸 Upload Banner Image/Video
# -----------------------------
@app.route('/admin/upload_banner', methods=['POST'])
@login_required
def upload_banner():
    banner_file = request.files.get('banner')
    video_file = request.files.get('banner_video')

    filename = None
    video_filename = None

    if banner_file and banner_file.filename:
        filename = secure_filename(banner_file.filename)
        banner_file.save(os.path.join(BANNER_FOLDER, filename))

    if video_file and video_file.filename:
        video_filename = secure_filename(video_file.filename)
        video_file.save(os.path.join(BANNER_FOLDER, video_filename))

    conn = get_db_connection()
    conn.execute('DELETE FROM banners')
    conn.execute('INSERT INTO banners (filename, video) VALUES (?, ?)', (filename, video_filename))
    conn.commit()
    conn.close()

    flash('Hero banner updated.')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/categories')
@login_required
def admin_categories():
    conn = get_db_connection()
    categories = conn.execute('SELECT * FROM categories').fetchall()
    conn.close()
    return render_template('admin_categories.html', categories=categories)

@app.route('/category/<int:category_id>')
def view_category(category_id):
    conn = get_db_connection()

    # ✅ Get the requested category
    category = conn.execute(
        'SELECT * FROM categories WHERE id = ?', (category_id,)
    ).fetchone()

    if not category:
        conn.close()
        flash('Category not found.')
        return redirect(url_for('index'))

    # ✅ Get all products for this category
    products = conn.execute(
        'SELECT * FROM products WHERE category_id = ?', (category_id,)
    ).fetchall()

    # ✅ Also get all categories for sidebar/nav
    categories = conn.execute('SELECT * FROM categories').fetchall()

    # ✅ Fetch banner and background for layout
    banner = conn.execute(
        'SELECT * FROM banners ORDER BY id DESC LIMIT 1'
    ).fetchone()

    background = conn.execute(
        'SELECT * FROM backgrounds ORDER BY id DESC LIMIT 1'
    ).fetchone()

    conn.close()

    # ✅ Render category.html with all needed context
    return render_template(
        'category.html',
        category=category,
        products=products,
        categories=categories,
        banner=banner,
        background=background
    )


@app.route('/admin/add_category', methods=['POST'])
@login_required
def add_category():
    name = request.form['name']
    conn = get_db_connection()
    conn.execute('INSERT INTO categories (name) VALUES (?)', (name,))
    conn.commit()
    conn.close()
    flash('Category added.')
    return redirect(url_for('admin_categories'))

@app.route('/admin/delete_category/<int:category_id>')
@login_required
def delete_category(category_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM categories WHERE id = ?', (category_id,))
    conn.commit()
    conn.close()
    flash('Category deleted.')
    return redirect(url_for('admin_categories'))

@app.route('/admin/update_product/<int:product_id>', methods=['GET', 'POST'])
@login_required
def update_product(product_id):
    conn = get_db_connection()
    product = conn.execute('SELECT * FROM products WHERE id = ?', (product_id,)).fetchone()

    if request.method == 'POST':
        name = request.form['name']
        description = request.form['description']
        price = request.form['price']

        conn.execute('UPDATE products SET name = ?, description = ?, price = ? WHERE id = ?',
                     (name, description, price, product_id))
        conn.commit()
        conn.close()

        flash('Product updated successfully!')
        return redirect(url_for('admin_dashboard'))

    conn.close()
    return render_template('admin_update_product.html', product=product)

# ✅ Add to Wishlist
@app.route('/add_to_wishlist/<int:product_id>')
def add_to_wishlist(product_id):
    if 'wishlist' not in session:
        session['wishlist'] = []
    if product_id not in session['wishlist']:
        session['wishlist'].append(product_id)
        flash('Product added to wishlist!')
    else:
        flash('Product already in wishlist.')
    return redirect(url_for('index'))

# ✅ Remove from Wishlist
@app.route('/remove_from_wishlist/<int:product_id>')
def remove_from_wishlist(product_id):
    if 'wishlist' in session and product_id in session['wishlist']:
        session['wishlist'].remove(product_id)
        flash('Product removed from wishlist.')
    return redirect(url_for('view_wishlist'))

# ✅ View Wishlist Page
@app.route('/wishlist')
def view_wishlist():
    if 'wishlist' not in session or not session['wishlist']:
        return render_template('wishlist.html', products=[])

    conn = get_db_connection()
    placeholders = ','.join(['?'] * len(session['wishlist']))
    query = f'SELECT * FROM products WHERE id IN ({placeholders})'
    products = conn.execute(query, session['wishlist']).fetchall()
    conn.close()

    return render_template('wishlist.html', products=products)

@app.route('/admin/orders')
@login_required
def admin_orders():
    conn = get_db_connection()

    # ✅ Correct: must call fetchall() with ()
    orders = conn.execute('SELECT * FROM orders ORDER BY id DESC').fetchall()

    orders_with_items = []
    for order in orders:
        # ✅ Always call fetchall()
        items = conn.execute(
            '''
            SELECT oi.quantity, p.name, p.price
            FROM order_items oi
            JOIN products p ON oi.product_id = p.id
            WHERE oi.order_id = ?
            ''',
            (order['id'],)
        ).fetchall()

        # ✅ Build dict
        orders_with_items.append({
            'order': order,
            'items': items
        })

    conn.close()
    return render_template('admin_orders.html', orders=orders_with_items)

@app.route('/admin/upload_background', methods=['POST'])
@login_required
def upload_background():
    bg_file = request.files['background']
    filename = secure_filename(bg_file.filename)
    bg_file.save(os.path.join(BACKGROUND_FOLDER, filename))

    conn = get_db_connection()
    conn.execute('DELETE FROM backgrounds')
    conn.execute('INSERT INTO backgrounds (filename) VALUES (?)', (filename,))
    conn.commit()
    conn.close()

    flash('Background updated.')
    return redirect(url_for('admin_dashboard'))

@app.route('/fragrance-quiz', methods=['GET', 'POST'])
def fragrance_quiz():
    if request.method == 'POST':
        # Get answers
        note = request.form.get('note')
        time = request.form.get('time')

        conn = get_db_connection()
        # Example query: you can match more fields
        product = conn.execute('''
            SELECT * FROM products 
            WHERE description LIKE ? OR description LIKE ?
            LIMIT 1
        ''', (f'%{note}%', f'%{time}%')).fetchone()
        conn.close()

        return render_template('quiz_result.html', product=product)

    return render_template('fragrance_quiz.html')

@app.route('/admin/update_top_banner', methods=['POST'])
@login_required
def update_top_banner():
    text = request.form['banner_text']
    conn = get_db_connection()
    conn.execute(
        '''
        INSERT INTO settings (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value
        ''', ('top_banner', text)
    )
    conn.commit()
    conn.close()
    flash('Top banner updated successfully!')
    return redirect(url_for('admin_dashboard'))

@app.route('/invoice/<int:order_id>')
def invoice(order_id):
    conn = get_db_connection()

    # ✅ Get order details
    order = conn.execute('SELECT * FROM orders WHERE id = ?', (order_id,)).fetchone()

    # ✅ Get ordered items
    items = conn.execute('''
        SELECT oi.quantity, p.name, p.price
        FROM order_items oi
        JOIN products p ON oi.product_id = p.id
        WHERE oi.order_id = ?
    ''', (order_id,)).fetchall()

    # ✅ Calculate subtotal
    subtotal = sum(item['price'] * item['quantity'] for item in items)

    # ✅ Get delivery fee (unless coupon disables it)
    delivery_fee = 0
    if order['coupon_code'] and order['coupon_code'].upper() == 'FREEDELIVERY':
        delivery_fee = 0
    else:
        settings_row = conn.execute("SELECT value FROM settings WHERE key = 'delivery_fee'").fetchone()
        delivery_fee = float(settings_row['value']) if settings_row else 0

    # ✅ Final total: subtotal + delivery - discount
    final_total = max(0, subtotal + delivery_fee - order['discount'])

    conn.close()

    return render_template(
        'invoice.html',
        order=order,
        items=items,
        subtotal=subtotal,
        delivery_fee=delivery_fee,
        final_total=final_total
    )

@app.route('/admin/upload_logo', methods=['POST'])
@login_required
def upload_logo():
    logo_file = request.files['logo']
    filename = secure_filename(logo_file.filename)
    LOGO_FOLDER = 'static/uploads/logos/'
    os.makedirs(LOGO_FOLDER, exist_ok=True)
    logo_file.save(os.path.join(LOGO_FOLDER, filename))

    conn = get_db_connection()
    conn.execute('DELETE FROM logos')
    conn.execute('INSERT INTO logos (filename) VALUES (?)', (filename,))
    conn.commit()
    conn.close()

    flash('Shop logo uploaded.')
    return redirect(url_for('admin_dashboard'))

# -----------------------------
# ⚙️ Initialize Database
# -----------------------------
def init_db():
    if not os.path.exists('db.sqlite3'):
        conn = get_db_connection()

        # ✅ PRODUCTS table
        conn.execute('''
            CREATE TABLE products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                description TEXT,
                price REAL,
                image TEXT,
                category_id INTEGER
            )
        ''')

        # ✅ ORDERS table with STATUS, TRACKING CODE, COUPON CODE, DISCOUNT
        conn.execute('''
            CREATE TABLE orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                address TEXT,
                phone TEXT,
                status TEXT DEFAULT 'Pending',
                tracking_code TEXT,
                coupon_code TEXT,
                discount REAL DEFAULT 0
            )
        ''')

        # ✅ ORDER ITEMS table
        conn.execute('''
            CREATE TABLE order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER,
                product_id INTEGER,
                quantity INTEGER
            )
        ''')

        # ✅ BANNERS table (image & optional video)
        conn.execute('''
            CREATE TABLE banners (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT,
                video TEXT
            )
        ''')

        # ✅ CATEGORIES table
        conn.execute('''
            CREATE TABLE categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL
            )
        ''')

        # ✅ BACKGROUNDS table
        conn.execute('''
            CREATE TABLE backgrounds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT
            )
        ''')

        # ✅ LOGOS table for shop logo
        conn.execute('''
            CREATE TABLE logos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT
            )
        ''')

        # ✅ COUPONS table
        conn.execute('''
            CREATE TABLE coupons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                discount REAL NOT NULL,
                type TEXT CHECK(type IN ('percentage', 'fixed', 'free_delivery')),
                description TEXT
            )
        ''')

        # ✅ SETTINGS table for delivery fee & banner text
        conn.execute('''
            CREATE TABLE settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE NOT NULL,
                value TEXT
            )
        ''')

        # ✅ KNOW YOUR PERFUME table
        conn.execute('''
            CREATE TABLE know_your_perfume (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL
            )
        ''')

        # ✅ Insert default delivery fee
        conn.execute(
            'INSERT INTO settings (key, value) VALUES (?, ?)',
            ('delivery_fee', '300')
        )

        # ✅ Insert default Top Banner text
        conn.execute(
            'INSERT INTO settings (key, value) VALUES (?, ?)',
            ('top_banner', '15 Days Hassle-Free Return | Free Shipping on Orders Above PKR 3,000')
        )

        conn.commit()
        conn.close()
        print("✅ Database initialized with all tables, delivery fee & top banner settings!")


# ✅ Context processor for Top Banner (add this above init_db, once)
@app.context_processor
def inject_settings():
    conn = get_db_connection()
    banner_row = conn.execute(
        "SELECT value FROM settings WHERE key = 'top_banner'"
    ).fetchone()
    conn.close()
    return dict(top_banner=banner_row['value'] if banner_row else '')


# ✅ App runner for Replit/Fly.io/Render
if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=8080)
