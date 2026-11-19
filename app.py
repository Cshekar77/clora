import os, uuid, datetime as dt
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, 'static', 'uploads')
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get('SECRET_KEY', 'change-me-in-production'),
    SQLALCHEMY_DATABASE_URI='sqlite:///' + os.path.join(BASE_DIR, 'clora.db'),
    SQLALCHEMY_TRACK_MODIFICATIONS=False, MAX_CONTENT_LENGTH=8 * 1024 * 1024)
db = SQLAlchemy(app)

BRAND, CURRENCY = 'Clora and Co', '$'
CATEGORIES = ['Men', 'Women', 'Kids', 'Accessories']
STATUSES = ['Pending', 'Processing', 'Shipped', 'Out for Delivery', 'Delivered', 'Cancelled']
TRACK = STATUSES[:5]
ALLOWED = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg'}


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    phone = db.Column(db.String(30), default='')
    address = db.Column(db.Text, default='')
    is_admin = db.Column(db.Boolean, default=False)


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(30), nullable=False)
    description = db.Column(db.Text, default='')
    price = db.Column(db.Float, nullable=False)
    old_price = db.Column(db.Float)
    stock = db.Column(db.Integer, default=0)
    sizes = db.Column(db.String(120), default='S,M,L,XL')
    colors = db.Column(db.String(120), default='Black')
    image = db.Column(db.String(200), default='')
    featured = db.Column(db.Boolean, default=False)
    created = db.Column(db.DateTime, default=dt.datetime.utcnow)

    @property
    def size_list(self): return [s.strip() for s in self.sizes.split(',') if s.strip()]
    @property
    def color_list(self): return [s.strip() for s in self.colors.split(',') if s.strip()]
    @property
    def discount(self):
        return round((1 - self.price / self.old_price) * 100) if self.old_price and self.old_price > self.price else 0


class Banner(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    subtitle = db.Column(db.String(250), default='')
    button_text = db.Column(db.String(40), default='Shop Now')
    link = db.Column(db.String(200), default='/shop')
    image = db.Column(db.String(200), default='')
    active = db.Column(db.Boolean, default=True)
    position = db.Column(db.Integer, default=0)


class Wish(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'))


class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    user = db.relationship('User')
    total = db.Column(db.Float)
    status = db.Column(db.String(30), default='Pending')
    name = db.Column(db.String(80)); phone = db.Column(db.String(30)); address = db.Column(db.Text)
    payment = db.Column(db.String(30))
    created = db.Column(db.DateTime, default=dt.datetime.utcnow)
    items = db.relationship('OrderItem', backref='order', cascade='all, delete-orphan')


class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'))
    product_id = db.Column(db.Integer)
    name = db.Column(db.String(120)); image = db.Column(db.String(200))
    size = db.Column(db.String(20)); color = db.Column(db.String(30))
    price = db.Column(db.Float); qty = db.Column(db.Integer)


# ---------- helpers ----------
def current_user():
    uid = session.get('uid')
    return db.session.get(User, uid) if uid else None


def login_required(f):
    @wraps(f)
    def w(*a, **k):
        if not current_user():
            flash('Please sign in to continue.', 'warning')
            return redirect(url_for('login', next=request.path))
        return f(*a, **k)
    return w


def admin_required(f):
    @wraps(f)
    def w(*a, **k):
        u = current_user()
        if not u or not u.is_admin:
            flash('Admin access required.', 'danger')
            return redirect(url_for('login', next=request.path))
        return f(*a, **k)
    return w


def save_image(file):
    if not file or not file.filename:
        return None
    ext = os.path.splitext(secure_filename(file.filename))[1].lower()
    if ext not in ALLOWED:
        flash('Unsupported image type.', 'danger'); return None
    name = uuid.uuid4().hex + ext
    file.save(os.path.join(UPLOAD_DIR, name))
    return name


def remove_image(name):
    if name and not name.startswith('seed_'):
        try: os.remove(os.path.join(UPLOAD_DIR, name))
        except OSError: pass


def get_cart():
    items, total = [], 0
    for key, qty in session.get('cart', {}).items():
        pid, size, color = key.split('|')
        p = db.session.get(Product, int(pid))
        if p:
            items.append(dict(key=key, p=p, size=size, color=color, qty=qty, sub=p.price * qty))
            total += p.price * qty
    return items, total


@app.context_processor
def inject():
    u = current_user()
    wish = {w.product_id for w in Wish.query.filter_by(user_id=u.id)} if u else set()
    return dict(user=u, BRAND=BRAND, CUR=CURRENCY, CATEGORIES=CATEGORIES, STATUSES=STATUSES, TRACK=TRACK,
                wish_ids=wish, cart_count=sum(session.get('cart', {}).values()))


# ---------- storefront ----------
@app.route('/')
def index():
    banners = Banner.query.filter_by(active=True).order_by(Banner.position).all()
    featured = Product.query.filter_by(featured=True).limit(8).all()
    newest = Product.query.order_by(Product.created.desc(), Product.id.desc()).limit(8).all()
    deals = Product.query.filter(Product.old_price.isnot(None)).limit(4).all()
    return render_template('index.html', banners=banners, featured=featured, newest=newest, deals=deals)


@app.route('/shop')
def shop():
    cat, q, sort = request.args.get('category', ''), request.args.get('q', '').strip(), request.args.get('sort', '')
    qs = Product.query
    if cat: qs = qs.filter_by(category=cat)
    if q: qs = qs.filter(db.or_(Product.name.ilike(f'%{q}%'), Product.description.ilike(f'%{q}%')))
    mn, mx = request.args.get('min', type=float), request.args.get('max', type=float)
    if mn is not None: qs = qs.filter(Product.price >= mn)
    if mx is not None: qs = qs.filter(Product.price <= mx)
    order = {'low': Product.price.asc(), 'high': Product.price.desc()}.get(sort, Product.id.desc())
    return render_template('shop.html', products=qs.order_by(order).all(), cat=cat, q=q, sort=sort)


@app.route('/product/<int:pid>')
def product(pid):
    p = db.get_or_404(Product, pid)
    related = Product.query.filter(Product.category == p.category, Product.id != p.id).limit(4).all()
    return render_template('product.html', p=p, related=related)


@app.route('/cart')
def cart():
    items, total = get_cart()
    return render_template('cart.html', items=items, total=total)


@app.post('/cart/add')
def cart_add():
    p = db.get_or_404(Product, request.form.get('pid', type=int))
    size = request.form.get('size') or (p.size_list[0] if p.size_list else 'One Size')
    color = request.form.get('color') or (p.color_list[0] if p.color_list else 'Default')
    qty = max(1, request.form.get('qty', 1, type=int))
    key = f'{p.id}|{size}|{color}'
    c = session.get('cart', {})
    c[key] = min(c.get(key, 0) + qty, max(p.stock, 1))
    session['cart'] = c
    flash(f'Added "{p.name}" to your cart.', 'success')
    return redirect(request.referrer or url_for('cart')) if request.form.get('stay') else redirect(url_for('cart'))


@app.post('/cart/update')
def cart_update():
    c = session.get('cart', {})
    key, qty = request.form['key'], request.form.get('qty', type=int)
    if key in c:
        if qty and qty > 0: c[key] = qty
        else: c.pop(key)
    session['cart'] = c
    return redirect(url_for('cart'))


@app.route('/wishlist')
@login_required
def wishlist():
    ids = [w.product_id for w in Wish.query.filter_by(user_id=current_user().id)]
    return render_template('wishlist.html', products=Product.query.filter(Product.id.in_(ids)).all() if ids else [])


@app.post('/wishlist/toggle/<int:pid>')
@login_required
def wish_toggle(pid):
    w = Wish.query.filter_by(user_id=current_user().id, product_id=pid).first()
    if w: db.session.delete(w)
    else: db.session.add(Wish(user_id=current_user().id, product_id=pid))
    db.session.commit()
    return redirect(request.referrer or url_for('wishlist'))


@app.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    items, total = get_cart()
    if not items:
        flash('Your cart is empty.', 'warning'); return redirect(url_for('shop'))
    u = current_user()
    if request.method == 'POST':
        for i in items:
            if i['qty'] > i['p'].stock:
                flash(f'Only {i["p"].stock} left of "{i["p"].name}".', 'danger'); return redirect(url_for('cart'))
        o = Order(user_id=u.id, total=total, name=request.form['name'], phone=request.form['phone'],
                  address=request.form['address'], payment=request.form.get('payment', 'Cash on Delivery'))
        for i in items:
            p = i['p']; p.stock -= i['qty']
            o.items.append(OrderItem(product_id=p.id, name=p.name, image=p.image, size=i['size'],
                                     color=i['color'], price=p.price, qty=i['qty']))
        db.session.add(o); db.session.commit()
        session.pop('cart', None)
        flash(f'Order #{o.id} placed successfully. Thank you!', 'success')
        return redirect(url_for('order_detail', oid=o.id))
    return render_template('checkout.html', items=items, total=total)


# ---------- auth & customer dashboard ----------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u = User.query.filter_by(email=request.form['email'].lower().strip()).first()
        if u and check_password_hash(u.password_hash, request.form['password']):
            session['uid'] = u.id
            nxt = request.args.get('next', '')
            if u.is_admin and not nxt: return redirect(url_for('admin_home'))
            return redirect(nxt if nxt.startswith('/') and not nxt.startswith('//') else url_for('index'))
        flash('Invalid email or password.', 'danger')
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email'].lower().strip()
        if len(request.form['password']) < 6:
            flash('Password must be at least 6 characters.', 'danger')
        elif User.query.filter_by(email=email).first():
            flash('That email is already registered.', 'danger')
        else:
            u = User(name=request.form['name'], email=email, password_hash=generate_password_hash(request.form['password']))
            db.session.add(u); db.session.commit(); session['uid'] = u.id
            flash('Welcome to Clora and Co!', 'success'); return redirect(url_for('index'))
    return render_template('register.html')


@app.route('/logout')
def logout():
    session.pop('uid', None); flash('Signed out.', 'info')
    return redirect(url_for('index'))


@app.route('/dashboard')
@login_required
def dashboard():
    orders = Order.query.filter_by(user_id=current_user().id).order_by(Order.id.desc()).all()
    return render_template('dashboard.html', orders=orders)


@app.post('/profile')
@login_required
def profile():
    u = current_user()
    u.name, u.phone, u.address = request.form['name'], request.form.get('phone', ''), request.form.get('address', '')
    if request.form.get('password'):
        if len(request.form['password']) < 6: flash('Password too short.', 'danger'); return redirect(url_for('dashboard'))
        u.password_hash = generate_password_hash(request.form['password'])
    db.session.commit(); flash('Profile updated.', 'success')
    return redirect(url_for('dashboard'))


@app.route('/order/<int:oid>')
@login_required
def order_detail(oid):
    o = db.get_or_404(Order, oid)
    if o.user_id != current_user().id and not current_user().is_admin: abort(403)
    return render_template('order.html', o=o)


# ---------- admin ----------
@app.route('/admin')
@admin_required
def admin_home():
    stats = dict(products=Product.query.count(), orders=Order.query.count(), customers=User.query.filter_by(is_admin=False).count(),
                 revenue=db.session.query(db.func.coalesce(db.func.sum(Order.total), 0)).filter(Order.status != 'Cancelled').scalar(),
                 low=Product.query.filter(Product.stock < 5).count())
    return render_template('admin/home.html', stats=stats, products=Product.query.order_by(Product.id.desc()).all(),
                           orders=Order.query.order_by(Order.id.desc()).limit(5).all())


def fill_product(p):
    f = request.form
    p.name, p.category, p.description = f['name'], f['category'], f.get('description', '')
    p.price, p.stock = float(f['price']), int(f.get('stock') or 0)
    p.old_price = float(f['old_price']) if f.get('old_price') else None
    p.sizes, p.colors, p.featured = f.get('sizes', ''), f.get('colors', ''), bool(f.get('featured'))
    img = save_image(request.files.get('image'))
    if img: remove_image(p.image); p.image = img


@app.route('/admin/product/new', methods=['GET', 'POST'])
@app.route('/admin/product/<int:pid>/edit', methods=['GET', 'POST'])
@admin_required
def admin_product(pid=None):
    p = db.get_or_404(Product, pid) if pid else Product()
    if request.method == 'POST':
        fill_product(p)
        db.session.add(p); db.session.commit(); flash('Product saved.', 'success')
        return redirect(url_for('admin_home'))
    return render_template('admin/product_form.html', p=p)


@app.post('/admin/product/<int:pid>/delete')
@admin_required
def admin_product_delete(pid):
    p = db.get_or_404(Product, pid); remove_image(p.image)
    Wish.query.filter_by(product_id=pid).delete(); db.session.delete(p); db.session.commit()
    flash('Product deleted.', 'info'); return redirect(url_for('admin_home'))


@app.route('/admin/orders')
@admin_required
def admin_orders():
    return render_template('admin/orders.html', orders=Order.query.order_by(Order.id.desc()).all())


@app.post('/admin/orders/<int:oid>/status')
@admin_required
def admin_order_status(oid):
    o = db.get_or_404(Order, oid); new = request.form['status']
    if new == 'Cancelled' and o.status != 'Cancelled':
        for i in o.items:
            p = db.session.get(Product, i.product_id)
            if p: p.stock += i.qty
    o.status = new; db.session.commit(); flash(f'Order #{oid} set to {new}.', 'success')
    return redirect(url_for('admin_orders'))


@app.route('/admin/banners')
@admin_required
def admin_banners():
    edit = db.session.get(Banner, request.args.get('edit', type=int)) if request.args.get('edit') else None
    return render_template('admin/banners.html', banners=Banner.query.order_by(Banner.position).all(), edit=edit)


@app.post('/admin/banners/save')
@admin_required
def admin_banner_save():
    f = request.form
    b = db.session.get(Banner, int(f['id'])) if f.get('id') else Banner()
    b.title, b.subtitle, b.button_text, b.link = f['title'], f.get('subtitle', ''), f.get('button_text', 'Shop Now'), f.get('link', '/shop')
    b.position, b.active = int(f.get('position') or 0), bool(f.get('active'))
    img = save_image(request.files.get('image'))
    if img: remove_image(b.image); b.image = img
    db.session.add(b); db.session.commit(); flash('Banner saved.', 'success')
    return redirect(url_for('admin_banners'))


@app.post('/admin/banners/<int:bid>/delete')
@admin_required
def admin_banner_delete(bid):
    b = db.get_or_404(Banner, bid); remove_image(b.image); db.session.delete(b); db.session.commit()
    flash('Banner deleted.', 'info'); return redirect(url_for('admin_banners'))


# ---------- seed ----------
def svg(name, text, c1, c2, w=600, h=750):
    t = text.replace('&', '&amp;')
    open(os.path.join(UPLOAD_DIR, name), 'w', encoding='utf-8').write(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="{c1}"/><stop offset="1" stop-color="{c2}"/></linearGradient></defs>'
        f'<rect width="{w}" height="{h}" fill="url(#g)"/><g fill="none" stroke="#f5ecd9" stroke-width="{w/200}" opacity=".8" '
        f'transform="translate({w/2},{h*.38})"><path d="M0-{h*.1}c{w*.03}-{h*.05} {w*.09}-{h*.02} {w*.06} {h*.03}-{w*.03} {h*.03}-{w*.06} {h*.03}-{w*.06} {h*.07}"/>'
        f'<path d="M0 {h*.0}L-{w*.3} {h*.12}H{w*.3}Z"/></g><text x="50%" y="{h*.72}" text-anchor="middle" fill="#f5ecd9" '
        f'font-family="Georgia,serif" font-size="{w*.06}">{t}</text></svg>')


def seed():
    if User.query.first(): return
    db.session.add_all([
        User(name='Store Admin', email='admin@cloraandco.com', password_hash=generate_password_hash('Admin@123'), is_admin=True),
        User(name='Jane Customer', email='customer@example.com', password_hash=generate_password_hash('Customer@123'),
             phone='555-0100', address='12 Market Street, Springfield')])
    pal = {'Men': ('#1f2a44', '#0b0f1a'), 'Women': ('#7a2e4d', '#2a0f1c'), 'Kids': ('#2f7d6d', '#0f2a25'), 'Accessories': ('#8a6a2f', '#2a200c')}
    S, K, A = 'S,M,L,XL', '2-3Y,4-5Y,6-7Y,8-9Y', 'One Size'
    data = [
        ('Classic Oxford Shirt', 'Men', 49, 69, 40, S, 'White,Sky Blue', 'Crisp cotton Oxford shirt with a tailored fit.', 1),
        ('Slim Fit Chinos', 'Men', 59, None, 35, '30,32,34,36', 'Khaki,Navy,Olive', 'Stretch cotton chinos for all-day comfort.', 1),
        ('Wool Blend Overcoat', 'Men', 189, 249, 12, S, 'Charcoal,Camel', 'Timeless double-breasted overcoat for winter.', 1),
        ('Essential Crew Tee', 'Men', 19, None, 100, S, 'Black,White,Grey', 'Soft combed-cotton tee, a wardrobe staple.', 0),
        ('Silk Wrap Dress', 'Women', 129, 169, 18, 'XS,S,M,L', 'Emerald,Burgundy,Black', 'Flowing wrap dress in luxurious silk.', 1),
        ('High-Rise Denim Jeans', 'Women', 79, None, 45, '26,28,30,32', 'Indigo,Light Wash', 'Flattering high-rise jeans with stretch.', 1),
        ('Cashmere Knit Sweater', 'Women', 149, 199, 15, 'XS,S,M,L', 'Cream,Rose,Grey', 'Ultra-soft cashmere crewneck sweater.', 1),
        ('Pleated Midi Skirt', 'Women', 64, None, 30, 'XS,S,M,L', 'Black,Sage', 'Elegant pleated skirt that moves beautifully.', 0),
        ('Linen Summer Blouse', 'Women', 54, 72, 28, 'XS,S,M,L', 'White,Sand', 'Breathable linen blouse for warm days.', 0),
        ('Kids Hoodie', 'Kids', 34, None, 50, K, 'Red,Navy,Grey', 'Cosy fleece hoodie built for play.', 1),
        ('Kids Denim Jacket', 'Kids', 44, 58, 22, K, 'Blue', 'Durable denim jacket with soft lining.', 0),
        ('Kids Graphic Tee Pack', 'Kids', 24, None, 60, K, 'Assorted', 'Pack of three fun graphic tees.', 0),
        ('Leather Belt', 'Accessories', 35, None, 60, A, 'Black,Brown', 'Full-grain leather belt with brushed buckle.', 0),
        ('Silk Scarf', 'Accessories', 42, 55, 40, A, 'Gold,Navy', 'Hand-rolled silk scarf with a lustrous finish.', 1),
        ('Classic Aviator Sunglasses', 'Accessories', 89, None, 25, A, 'Gold,Silver', 'UV400 aviators with polarised lenses.', 1),
        ('Leather Tote Bag', 'Accessories', 159, 210, 3, A, 'Tan,Black', 'Spacious tote in soft pebbled leather.', 0)]
    for n, c, pr, old, st, sz, col, d, fe in data:
        fn = f'seed_p{len(n)}{abs(hash(n)) % 999}.svg'
        fn = 'seed_' + ''.join(ch for ch in n.lower() if ch.isalnum()) + '.svg'
        svg(fn, n, *pal[c])
        db.session.add(Product(name=n, category=c, price=pr, old_price=old, stock=st, sizes=sz, colors=col, description=d, featured=bool(fe), image=fn))
    for i, (t, s, l, c1, c2) in enumerate([
        ('The Winter Collection', 'Refined layers and timeless coats. Up to 30% off selected styles.', '/shop?category=Men', '#1f2a44', '#05070d'),
        ('New Season Women\'s Edit', 'Silk, linen and cashmere in this season\'s palette.', '/shop?category=Women', '#7a2e4d', '#12050b'),
        ('Mega Sale: Accessories', 'Scarves, bags and shades from $35. While stocks last.', '/shop?category=Accessories', '#8a6a2f', '#120d03')]):
        fn = f'seed_banner{i}.svg'; svg(fn, '', c1, c2, 1600, 560)
        db.session.add(Banner(title=t, subtitle=s, link=l, image=fn, position=i))
    db.session.commit()


with app.app_context():
    db.create_all()
    seed()

if __name__ == '__main__':
    app.run(debug=True)
