from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import os
from werkzeug.utils import secure_filename
from functools import wraps

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

@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    cart = session.get('cart', [])
    if not cart:
        flash('Your cart is empty.')
        return redirect(url_for('index'))
    if request.method == 'POST':
        name = request.form['name']
        address = request.form['address']
        phone = request.form['phone']

        conn = get_db_connection()
        conn.execute('INSERT INTO orders (name, address, phone) VALUES (?, ?, ?)', (name, address, phone))
        order_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
        for item in cart:
            conn.execute('INSERT INTO order_items (order_id, product_id, quantity) VALUES (?, ?, ?)',
                         (order_id, item['id'], item['quantity']))
        conn.commit()
        conn.close()

        session.pop('cart', None)
        flash('Order placed successfully!')
        return redirect(url_for('thankyou'))

    total = sum(item['price'] * item['quantity'] for item in cart)
    return render_template('checkout.html', cart=cart, total=total)

@app.route('/thankyou')
def thankyou():
    return render_template('thankyou.html')

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

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    conn = get_db_connection()
    products = conn.execute('SELECT * FROM products').fetchall()
    banner = conn.execute('SELECT * FROM banners ORDER BY id DESC LIMIT 1').fetchone()
    background = conn.execute('SELECT * FROM backgrounds ORDER BY id DESC LIMIT 1').fetchone()
    categories = conn.execute('SELECT * FROM categories').fetchall()
    conn.close()
    return render_template('admin_dashboard.html', products=products, banner=banner, background=background, categories=categories)

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

@app.route('/admin/update_order_status/<int:order_id>', methods=['POST'])
@login_required
def update_order_status(order_id):
    new_status = request.form['status']
    conn = get_db_connection()
    conn.execute('UPDATE orders SET status = ? WHERE id = ?', (new_status, order_id))
    conn.commit()
    conn.close()
    flash(f'Order #{order_id} status updated to {new_status}.')
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
    category = conn.execute('SELECT * FROM categories WHERE id = ?', (category_id,)).fetchone()
    if not category:
        flash('Category not found.')
        return redirect(url_for('index'))

    products = conn.execute('SELECT * FROM products WHERE category_id = ?', (category_id,)).fetchall()
    categories = conn.execute('SELECT * FROM categories').fetchall()
    banner = conn.execute('SELECT * FROM banners ORDER BY id DESC LIMIT 1').fetchone()
    background = conn.execute('SELECT * FROM backgrounds ORDER BY id DESC LIMIT 1').fetchone()
    conn.close()
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

        # ✅ ORDERS table with STATUS for tracking
        conn.execute('''
            CREATE TABLE orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                address TEXT,
                phone TEXT,
                status TEXT DEFAULT 'Pending'
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

        conn.commit()
        conn.close()
        print("✅ Database initialized with status tracking for orders!")
        
if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)
