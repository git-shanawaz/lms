from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from datetime import datetime
import sys
import os

app = Flask(__name__)
from werkzeug.utils import secure_filename

UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///library.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'dev-key-for-project'

db = SQLAlchemy(app)
migrate = Migrate(app, db)

# ---------- Models ----------
# Admin user for authentication
class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

class BookRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    roll_no = db.Column(db.String(50), nullable=False)
    student_class = db.Column(db.String(50))
    email = db.Column(db.String(120))
    book_id = db.Column(db.Integer, db.ForeignKey('book.id'))
    status = db.Column(db.String(20), default='Pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    book = db.relationship('Book', backref='requests')

class Book(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    author = db.Column(db.String(200), nullable=False)
    image_filename = db.Column(db.String(200)) 
    isbn = db.Column(db.String(50), unique=True, nullable=True)
    copies_total = db.Column(db.Integer, nullable=False, default=1)
    copies_available = db.Column(db.Integer, nullable=False, default=1)

    def __repr__(self):
        return f'<Book {self.title}>'

class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    student_class = db.Column(db.String(50))
    roll_no = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(200), nullable=True)

    def __repr__(self):
        return f'<Student {self.name}>'

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey('book.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    issue_date = db.Column(db.DateTime, default=datetime.utcnow)
    return_date = db.Column(db.DateTime, nullable=True)

    book = db.relationship('Book', backref=db.backref('transactions', lazy=True))
    student = db.relationship('Student', backref=db.backref('transactions', lazy=True))

    def __repr__(self):
        return f'<Transaction book={self.book_id} student={self.student_id}>'

# ---------- Helper functions ----------

def create_database():
    with app.app_context():
        if not os.path.exists('library.db'):
            db.create_all()
            print('Initialized database.')
        else:
            print('Database already exists.')

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ---------- Routes ----------
from flask import session

# ---------- Authentication ----------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        admin = Admin.query.filter_by(
            username=username,
            password=password
        ).first()

        if admin:
            session['admin'] = admin.username
            flash('Logged in successfully.', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid credentials.', 'danger')

    # IMPORTANT: render login page on GET
    return render_template('login.html')

# ---------- Routes ----------

@app.route('/')
def index():
    # Check if librarian is logged in
    if 'admin' in session:
        # Dashboard view
        request_count = BookRequest.query.filter_by(status='Pending').count()
        book_count = Book.query.count()
        student_count = Student.query.count()
        transaction_count = Transaction.query.count()
        return render_template(
            'index.html',
            logged_in=True,
            request_count=request_count,
            book_count=book_count,
            student_count=student_count,
            transaction_count=transaction_count
        )

    # Guest / user view — show books for request
    q = request.args.get('q', '')
    if q:
        books = Book.query.filter(
            Book.title.ilike(f'%{q}%') |
            Book.author.ilike(f'%{q}%')
        ).all()
    else:
        books = Book.query.order_by(Book.title).all()

    return render_template('index.html', logged_in=False, books=books, q=q)

# Requests
@app.route('/request', methods=['POST', 'GET'])
def request_books():
    from flask import flash

    if request.method == 'POST':
        book_ids = request.form.getlist('book_ids')

        if not book_ids:
            flash('Select at least one book.', 'danger')
            return redirect(url_for('index'))

        # If books selected → move to request form page
        return render_template('request_form.html', book_ids=book_ids)

    return redirect(url_for('index'))

@app.route('/request/submit', methods=['POST'])
def submit_request():
    book_ids = request.form.getlist('book_ids')

    for book_id in book_ids:
        r = BookRequest(
            name=request.form['name'],
            roll_no=request.form['roll_no'],
            student_class=request.form['student_class'],
            email=request.form['email'],
            book_id=int(book_id)
        )
        db.session.add(r)

    db.session.commit()
    flash('Request submitted successfully.', 'success')
    return redirect(url_for('index'))

@app.route('/requests', methods=['GET', 'POST'])
@login_required
def requests():
    if request.method == 'POST':
        ids = request.form.getlist('request_ids')
        for rid in ids:
            req = BookRequest.query.get(int(rid))
            book = Book.query.get(req.book_id)

            if book.copies_available > 0:
                student = Student.query.filter_by(roll_no=req.roll_no).first()
                if not student:
                    student = Student(
                        name=req.name,
                        roll_no=req.roll_no,
                        email=req.email,
                        student_class=req.student_class
                    )
                    db.session.add(student)
                    db.session.commit()

                    book.copies_available -= 1
                req.status = 'Approved'

        t = Transaction(book_id=book.id, student_id=student.id)
        db.session.add(t)

        db.session.commit()
        flash('Selected requests approved.', 'success')
        return redirect(url_for('requests'))

    requests = BookRequest.query.filter_by(status='Pending').all()
    return render_template('requests.html', requests=requests)


# Books
@app.route('/books')
@login_required
def books():
    books = Book.query.order_by(Book.title).all()
    return render_template('books.html', books=books)
@app.route('/books/add', methods=['GET', 'POST'])
@login_required
def add_book():
    if request.method == 'POST':
        title = request.form['title'].strip()
        author = request.form['author'].strip()
        isbn = request.form['isbn'].strip() or None
        copies = int(request.form.get('copies', 1))

        image = request.files.get('image')
        filename = None

        if image and image.filename != '':
            filename = secure_filename(image.filename)
            image.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

        if not title or not author:
            flash('Title and author are required.', 'danger')
            return redirect(url_for('add_book'))

        book = Book(
            title=title,
            author=author,
            isbn=isbn,
            copies_total=copies,
            copies_available=copies,
            image_filename=filename  # NEW
        )

        db.session.add(book)
        db.session.commit()

        flash('Book added successfully.', 'success')
        return redirect(url_for('books'))

    return render_template('add_book.html')

@app.route('/books/<int:book_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_book(book_id):
    book = Book.query.get_or_404(book_id)

    if request.method == 'POST':
        book.title = request.form['title'].strip()
        book.author = request.form['author'].strip()
        book.isbn = request.form['isbn'].strip() or None

        new_total = int(request.form['copies'])
        diff = new_total - book.copies_total
        book.copies_total = new_total
        book.copies_available = max(0, book.copies_available + diff)

        # Handle new image upload
        image = request.files.get('image')
        if image and image.filename != '':
            filename = secure_filename(image.filename)
            image.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            book.image_filename = filename

        db.session.commit()
        flash('Book updated.', 'success')
        return redirect(url_for('books'))

    return render_template('edit_book.html', book=book)

@app.route('/books/<int:book_id>/delete', methods=['POST'])
def delete_book(book_id):
    book = Book.query.get_or_404(book_id)
    # prevent deleting if copies are issued
    issued = Transaction.query.filter_by(book_id=book.id, return_date=None).count()
    if issued > 0:
        flash('Cannot delete book while copies are issued.', 'danger')
        return redirect(url_for('books'))
    db.session.delete(book)
    db.session.commit()
    flash('Book deleted.', 'success')
    return redirect(url_for('books'))

# Students
@app.route('/students')
@login_required
def students():
    q = request.args.get('q', '')

    if q:
        students = Student.query.filter(
            (Student.name.ilike(f'%{q}%')) |
            (Student.roll_no.ilike(f'%{q}%'))
        ).all()
    else:
        students = Student.query.order_by(Student.name).all()

    return render_template('students.html', students=students, q=q)


@app.route('/students/add', methods=['GET', 'POST'])
@login_required
def add_student():
    if request.method == 'POST':
        name = request.form['name'].strip()
        roll_no = request.form['roll_no'].strip()
        email = request.form['email'].strip() or None
        student_class = request.form['student_class'].strip() or None  # new field

        if not name or not roll_no:
            flash('Name and roll number required.', 'danger')
            return redirect(url_for('add_student'))

        if Student.query.filter_by(roll_no=roll_no).first():
            flash('Roll number already exists.', 'danger')
            return redirect(url_for('add_student'))

        student = Student(
            name=name,
            roll_no=roll_no,
            email=email,
            student_class=student_class   # include it here
        )

        db.session.add(student)
        db.session.commit()
        flash('Student added.', 'success')
        return redirect(url_for('students'))

    return render_template('add_student.html')


@app.route('/students/<int:student_id>/delete', methods=['POST'])
@login_required
def delete_student(student_id):
    student = Student.query.get_or_404(student_id)
    # prevent deleting if student has issued books
    issued = Transaction.query.filter_by(student_id=student.id, return_date=None).count()
    if issued > 0:
        flash('Cannot delete student with issued books.', 'danger')
        return redirect(url_for('students'))
    db.session.delete(student)
    db.session.commit()
    flash('Student deleted.', 'success')
    return redirect(url_for('students'))

# Issue / Return
@app.route('/transactions', methods=['GET'])
@login_required
def transactions():
    trans = Transaction.query.order_by(Transaction.issue_date.desc()).all()
    return render_template('transactions.html', transactions=trans)

@app.route('/issue', methods=['GET', 'POST'])
@login_required
def issue_return():
    if request.method == 'POST':
        book_id = int(request.form['book_id'])
        student_id = int(request.form['student_id'])
        action = request.form['action']  # 'issue' or 'return'
        book = Book.query.get_or_404(book_id)
        student = Student.query.get_or_404(student_id)

        if action == 'issue':
            if book.copies_available < 1:
                flash('No copies available to issue.', 'danger')
            else:
                book.copies_available -= 1
                t = Transaction(book_id=book.id, student_id=student.id)
                db.session.add(t)
                db.session.commit()
                flash(f'Issued "{book.title}" to {student.name}.', 'success')
        else:  # return
            trans = Transaction.query.filter_by(
                book_id=book.id, student_id=student.id, return_date=None
            ).first()
            if not trans:
                flash('No active issue record found for this book and student.', 'danger')
            else:
                trans.return_date = datetime.utcnow()
                book.copies_available += 1
                db.session.commit()
                flash(f'Book "{book.title}" returned by {student.name}.', 'success')

        return redirect(url_for('issue_return'))

    # GET request — handle optional search filters
    book_q = request.args.get('book_q', '')
    student_q = request.args.get('student_q', '')

    books = Book.query
    if book_q:
        books = books.filter(
            (Book.title.ilike(f'%{book_q}%')) | (Book.author.ilike(f'%{book_q}%'))
        )
    books = books.order_by(Book.title).all()

    students = Student.query
    if student_q:
        students = students.filter(
            (Student.name.ilike(f'%{student_q}%')) | (Student.roll_no.ilike(f'%{student_q}%'))
        )
    students = students.order_by(Student.name).all()

    return render_template(
        'issue_return.html',
        books=books,
        students=students,
        book_q=book_q,
        student_q=student_q
    )

#Logout Route
@app.route('/logout')
def logout():
    session.pop('admin', None)
    flash('Logged out.', 'info')
    return redirect(url_for('login'))
# ---------- CLI command ----------
if __name__ == '__main__':
    # create default admin if not exists
    with app.app_context():
        db.create_all()
        if not Admin.query.first():
            db.session.add(Admin(username='admin', password='admin123'))
            db.session.commit()
            print('Default admin created: admin / admin123')

    app.run(debug=True)

    # small helper: `python app.py initdb` to create DB
    if len(sys.argv) > 1 and sys.argv[1] == 'initdb':
        create_database()
        sys.exit(0)
    # create db if not exists when running normally
    create_database()
    app.run(debug=True)