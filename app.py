from flask import Flask, request, jsonify, render_template, redirect, url_for, flash
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from models import db, User, Subject, Review
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import datetime
from bs4 import BeautifulSoup
import requests

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your_secret_key')

db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/register', methods=['GET', 'POST'])
def register():
    """Register a new user."""
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        password_hash = generate_password_hash(password)

        # Check if the username or email already exists
        existing_user = User.query.filter_by(username=username).first() or User.query.filter_by(email=email).first()
        if existing_user:
            return jsonify({"error": "Username or Email already exists!"}), 400

        # Create and add the new user to the database
        new_user = User(username=username, email=email, password=password_hash)
        db.session.add(new_user)
        db.session.commit()

        return redirect(url_for('login'))  # Redirect to login page after successful registration

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('home'))
        return render_template('login.html', error="Invalid username or password.")
    return render_template('login.html')

@app.route('/logout', methods=['GET'])
@login_required
def logout():
    """Logout the current user."""
    logout_user()
    return redirect(url_for('login'))

@app.route('/', methods=['GET'])
def home():
    """Home route displaying all subjects with optional filters."""
    # Get filter values from the query parameters (if any)
    filter_period = request.args.get('filter_period')
    filter_credits = request.args.get('filter_credits')
    filter_scqf = request.args.get('filter_scqf')

    # Start with all subjects
    subjects = Subject.query

    # Apply filtering based on period
    if filter_period:
        subjects = subjects.filter(Subject.period == filter_period)

    # Apply filtering based on credits
    if filter_credits:
        subjects = subjects.filter(Subject.credits == filter_credits)

    if filter_scqf:
        subjects = subjects.filter(Subject.scqf == filter_scqf)

    # Fetch the filtered subjects
    subjects = subjects.all()

    # Fetch unique values for period and credits
    unique_periods = db.session.query(Subject.period).distinct().all()
    unique_credits = db.session.query(Subject.credits).distinct().all()
    unique_scqf = db.session.query(Subject.scqf).distinct().all()

    # Format the unique values as a list of strings
    unique_periods = [period[0] for period in unique_periods]
    unique_credits = [credits[0] for credits in unique_credits]
    unique_scqf = [scqf[0] for scqf in unique_scqf]

    return render_template('home.html', 
                           subjects=subjects, 
                           filter_period=filter_period, 
                           filter_credits=filter_credits, 
                           filter_scqf=filter_scqf,
                           unique_periods=unique_periods, 
                           unique_credits=unique_credits,
                           unique_scqf=unique_scqf,
                           logged_in=current_user.is_authenticated,)

@app.route('/subject/<int:subject_id>')
def subject_page(subject_id):
    """Subject details page with reviews and average rating."""
    subject = Subject.query.get_or_404(subject_id)
    reviews = Review.query.filter_by(subject_id=subject_id).all()
    avg_rating = db.session.query(db.func.avg(Review.rating)).filter_by(subject_id=subject_id).scalar() or 0
    return render_template('subject.html', subject=subject, reviews=reviews, avg_rating=round(avg_rating, 2))

@app.route('/add_review/<int:subject_id>', methods=['POST'])
@login_required  # Ensure user is logged in to add a review
def add_review(subject_id):
    """Add a review for a specific subject."""
    data = request.form
    required_fields = ['rating', 'comment']

    # Validate input
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"'{field}' is required."}), 400

    try:
        rating = int(data['rating'])
        comment = data['comment']
    except ValueError:
        return jsonify({"error": "Invalid data types for rating."}), 400

    if not (1 <= rating <= 5):
        return jsonify({"error": "Rating must be between 1 and 5."}), 400

    new_review = Review(
        user_id=current_user.id,  # Get the logged-in user's ID
        subject_id=subject_id,
        rating=rating,
        comment=comment
    )
    db.session.add(new_review)
    db.session.commit()

    flash("Review added successfully!", "success")
    return redirect(url_for('subject_page', subject_id=subject_id))

@app.route('/feed')
def feed():
    # Most Reviewed Subjects
    most_reviewed = db.session.query(
        Subject.id,  # Include subject ID
        Subject.name,
        db.func.count(Review.id).label('review_count')
    ).join(Review).group_by(Subject.id).order_by(db.desc('review_count')).limit(5).all()

    # Highest Rated Subjects
    highest_rated = db.session.query(
        Subject.id,  # Include subject ID
        Subject.name,
        db.func.avg(Review.rating).label('avg_rating')
    ).join(Review).group_by(Subject.id).order_by(db.desc('avg_rating')).limit(5).all()

    return render_template('feed.html', 
                          most_reviewed=most_reviewed, 
                          highest_rated=highest_rated, 
                          logged_in=current_user.is_authenticated)

def extract_subject_details(url):
    """Fetch and parse course details from the University of Edinburgh DRPS course page."""
    details = {
        'title': '',
        'course_code': '',
        'school': '',
        'college': '',
        'summary': '',
        'course_description': '',
        'assessment': '',
        'learning_outcomes': '',
        'total_hours': '',
        'prerequisites': '',
        'prohibited_combinations': '',
        'course_organizer': '',
        'course_url': '',
        'keywords': '',
    }

    try:
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')

        # Extract Course Title and Code
        title_tag = soup.find('h1', class_='sitspagetitle')
        if title_tag:
            title_text = title_tag.get_text(strip=True)
            if '(' in title_text and ')' in title_text:
                details['title'] = title_text.split('(')[0].strip()
                details['course_code'] = title_text.split('(')[-1].strip(')')

        # Extract School and College from "Course Outline"
        for row in soup.select('table.sitstablegrid caption'):
            if "Course Outline" in row.get_text():
                table = row.find_parent('table')
                if table:
                    rows = table.find_all('tr')
                    for tr in rows:
                        cells = tr.find_all('td')
                        if len(cells) >= 4:  # Ensure we have both columns
                            label_1 = cells[0].get_text(strip=True)
                            value_1 = cells[1].get_text(strip=True)
                            label_2 = cells[2].get_text(strip=True)
                            value_2 = cells[3].get_text(strip=True)
                            
                            if "School" in label_1:
                                details['school'] = value_1
                            if "College" in label_2:
                                details['college'] = value_2

        # Extract Summary and Course Description
        for row in soup.select('table.sitstablegrid caption'):
            if "Course Outline" in row.get_text():
                table = row.find_parent('table')
                if table:
                    rows = table.find_all('tr')
                    for tr in rows:
                        cells = tr.find_all('td')
                        if len(cells) >= 2:
                            label = cells[0].get_text(strip=True)
                            value = cells[1].get_text(" ", strip=True)
                            if "Summary" in label:
                                details['summary'] = value
                            elif "Course description" in label:
                                details['course_description'] = value

        # Extract Prerequisites (Fixing the issue)
        for row in soup.select('table.sitstablegrid caption'):
            if "Entry Requirements" in row.get_text():
                table = row.find_parent('table')
                if table:
                    rows = table.find_all('tr')
                    for tr in rows:
                        cells = tr.find_all('td')
                        if len(cells) >= 2:
                            label = cells[0].get_text(strip=True)
                            if "Pre-requisites" in label:
                                prereq_links = []
                                for link in cells[1].find_all('a'):
                                    prereq_links.append(f"{link.get_text(strip=True)}")
                                details['prerequisites'] = "; ".join(prereq_links)

                            if "Prohibited Combinations" in label:
                                prohibited_links = []
                                for link in cells[1].find_all('a'):
                                    prohibited_links.append(f"{link.get_text(strip=True)}")
                                details['prohibited_combinations'] = "; ".join(prohibited_links)

        # Extract Learning Outcomes
        for row in soup.select('table.sitstablegrid caption'):
            if "Learning Outcomes" in row.get_text():
                table = row.find_parent('table')
                if table:
                    outcome_list = table.find('ol')
                    if outcome_list:
                        details['learning_outcomes'] = " ".join(li.get_text(strip=True) for li in outcome_list.find_all('li'))

        # Extract Assessment Details
        for row in soup.select('table.sitstablegrid caption'):
            if "Assessment" in row.get_text():
                table = row.find_parent('table')
                if table:
                    assessment_data = table.find('td', colspan="14")
                    if assessment_data:
                        details['assessment'] = assessment_data.get_text(" ", strip=True)

        # Extract Total Learning Hours
        for row in soup.select('table.sitstablegrid caption'):
            if "Course Delivery Information" in row.get_text():
                table = row.find_parent('table')
                if table:
                    rows = table.find_all('tr')
                    for tr in rows:
                        if "Total Hours" in tr.get_text():
                            details['total_hours'] = tr.find_all('td')[1].get_text(strip=True)

        # Extract Course URL
        for row in soup.select('table.sitstablegrid caption'):
            if "Additional Information" in row.get_text():
                table = row.find_parent('table')
                if table:
                    rows = table.find_all('tr')
                    for tr in rows:
                        cells = tr.find_all('td')
                        if len(cells) >= 2:
                            label = cells[0].get_text(strip=True)
                            value = cells[1].get_text(strip=True)
                            if "Course URL" in label:
                                details['course_url'] = value

        # Extract Keywords
        for row in soup.select('table.sitstablegrid caption'):
            if "Additional Information" in row.get_text():
                table = row.find_parent('table')
                if table:
                    rows = table.find_all('tr')
                    for tr in rows:
                        cells = tr.find_all('td')
                        if len(cells) >= 2:
                            label = cells[0].get_text(strip=True)
                            value = cells[1].get_text(strip=True)
                            if "Keywords" in label:
                                details['keywords'] = value

        # Extract Course Organizer
        for row in soup.select('table.sitstablegrid caption'):
            if "Contacts" in row.get_text():
                table = row.find_parent('table')
                if table:
                    rows = table.find_all('tr')
                    for tr in rows:
                        cells = tr.find_all('td')
                        if len(cells) >= 2:
                            label = cells[0].get_text(strip=True)
                            value = cells[1].get_text(strip=True)
                            if "Course organiser" in label:
                                details['course_organizer'] = value.split("Tel:")[0].strip()

        return details

    except requests.RequestException as e:
        print(f"Error fetching URL {url}: {e}")
        return details

    """Fetch and parse course details from the University of Edinburgh DRPS course page."""
    details = {
        'title': '',
        'course_code': '',
        'school': '',
        'college': '',
        'summary': '',
        'course_description': '',
        'assessment': '',
        'learning_outcomes': '',
        'total_hours': '',
        'prerequisites': '',
        'prohibited_combinations': '',
        'course_organizer': '',
        'course_url': '',
        'keywords': '',
    }

    try:
        response = requests.get(url)
        response.raise_for_status()  # Raise an error for bad responses
        soup = BeautifulSoup(response.content, 'html.parser')

        # Extract Course Title and Code
        title_tag = soup.find('h1', class_='sitspagetitle')
        if title_tag:
            title_text = title_tag.get_text(strip=True)
            if '(' in title_text and ')' in title_text:
                details['title'] = title_text.split('(')[0].strip()
                details['course_code'] = title_text.split('(')[-1].strip(')')

        # Extract School and College
        for row in soup.select('table.sitstablegrid caption'):
            if "Course Outline" in row.get_text():
                table = row.find_parent('table')
                if table:
                    rows = table.find_all('tr')
                    for tr in rows:
                        cells = tr.find_all('td')
                        if len(cells) >= 2:
                            label = cells[0].get_text(strip=True)
                            value = cells[1].get_text(strip=True)
                            if "School" in label:
                                details['school'] = value
                            elif "College" in label:
                                details['college'] = value

        # Extract Summary and Course Description
        for row in soup.select('table.sitstablegrid caption'):
            if "Course Outline" in row.get_text():
                table = row.find_parent('table')
                if table:
                    rows = table.find_all('tr')
                    for tr in rows:
                        cells = tr.find_all('td')
                        if len(cells) >= 2:
                            label = cells[0].get_text(strip=True)
                            value = cells[1].get_text(" ", strip=True)
                            if "Summary" in label:
                                details['summary'] = value
                            elif "Course description" in label:
                                details['course_description'] = value

        # Extract Prerequisites and Prohibited Combinations
        for row in soup.select('table.sitstablegrid caption'):
            if "Entry Requirements" in row.get_text():
                table = row.find_parent('table')
                if table:
                    rows = table.find_all('tr')
                    for tr in rows:
                        cells = tr.find_all('td')
                        if len(cells) >= 2:
                            label = cells[0].get_text(strip=True)
                            value = cells[1].get_text(" ", strip=True)
                            if "Pre-requisites" in label:
                                details['prerequisites'] = value
                            elif "Prohibited Combinations" in label:
                                details['prohibited_combinations'] = value

        # Extract Learning Outcomes
        for row in soup.select('table.sitstablegrid caption'):
            if "Learning Outcomes" in row.get_text():
                table = row.find_parent('table')
                if table:
                    outcome_list = table.find('ol')
                    if outcome_list:
                        details['learning_outcomes'] = " ".join(li.get_text(strip=True) for li in outcome_list.find_all('li'))

        # Extract Assessment Details
        for row in soup.select('table.sitstablegrid caption'):
            if "Assessment" in row.get_text():
                table = row.find_parent('table')
                if table:
                    assessment_data = table.find('td', colspan="14")
                    if assessment_data:
                        details['assessment'] = assessment_data.get_text(" ", strip=True)

        # Extract Total Learning Hours
        for row in soup.select('table.sitstablegrid caption'):
            if "Course Delivery Information" in row.get_text():
                table = row.find_parent('table')
                if table:
                    rows = table.find_all('tr')
                    for tr in rows:
                        if "Total Hours" in tr.get_text():
                            details['total_hours'] = tr.find_all('td')[1].get_text(strip=True)

        # Extract Course URL
        for row in soup.select('table.sitstablegrid caption'):
            if "Additional Information" in row.get_text():
                table = row.find_parent('table')
                if table:
                    rows = table.find_all('tr')
                    for tr in rows:
                        cells = tr.find_all('td')
                        if len(cells) >= 2:
                            label = cells[0].get_text(strip=True)
                            value = cells[1].get_text(strip=True)
                            if "Course URL" in label:
                                details['course_url'] = value

        # Extract Keywords
        for row in soup.select('table.sitstablegrid caption'):
            if "Additional Information" in row.get_text():
                table = row.find_parent('table')
                if table:
                    rows = table.find_all('tr')
                    for tr in rows:
                        cells = tr.find_all('td')
                        if len(cells) >= 2:
                            label = cells[0].get_text(strip=True)
                            value = cells[1].get_text(strip=True)
                            if "Keywords" in label:
                                details['keywords'] = value

        # Extract Course Organizer
        for row in soup.select('table.sitstablegrid caption'):
            if "Contacts" in row.get_text():
                table = row.find_parent('table')
                if table:
                    rows = table.find_all('tr')
                    for tr in rows:
                        cells = tr.find_all('td')
                        if len(cells) >= 2:
                            label = cells[0].get_text(strip=True)
                            value = cells[1].get_text(strip=True)
                            if "Course organiser" in label:
                                details['course_organizer'] = value.split("Tel:")[0].strip()

        return details

    except requests.RequestException as e:
        print(f"Error fetching URL {url}: {e}")
        return details

    
@app.route('/add_subjects_from_html', methods=['POST'])
def add_subjects_from_html():
    """Extract subjects from the uploaded HTML file and add them to the database."""
    uploaded_file = request.files['file']
    if not uploaded_file:
        return jsonify({"error": "No file uploaded."}), 400

    soup = BeautifulSoup(uploaded_file.read(), 'html.parser')
    subjects_to_add = []

    # Find all SCQF level sections
    scqf_levels = soup.find_all('h3', class_='scqf_level')

    for scqf_level in scqf_levels:
        scqf_text = scqf_level.get_text(strip=True)
        scqf = scqf_text.split('(')[0].replace('SCQF Level', '').strip()  # Extract SCQF level number
        
        # Find the table following the SCQF level heading
        table = scqf_level.find_next('table')
        rows = table.find_all('tr')

        # Process each row in the table (skip the header row)
        for row in rows[1:]:
            columns = row.find_all('td')
            
            if len(columns) >= 5:
                code = columns[0].get_text(strip=True)
                availability = columns[1].get_text(strip=True)
                name = columns[2].get_text(strip=True)
                period = columns[3].get_text(strip=True)
                credits = columns[4].get_text(strip=True)

                try:
                    credits = int(credits)
                    # Construct the URL for the individual course page
                    course_url = f"http://www.drps.ed.ac.uk/24-25/dpt/cx{code.lower()}.htm"
                    # Fetch additional details from the individual course page
                    details = extract_subject_details(course_url)

                    subjects_to_add.append({
                        "name": name,
                        "code": code,
                        "period": period,
                        "credits": credits,
                        "scqf": scqf,
                        "availability": availability,
                        "school": details.get('school', ''),
                        "college": details.get('college', ''),
                        "summary": details.get('summary', ''),
                        "assessment": details.get('assessment', ''),
                        "learning_outcomes": details.get('learning_outcomes', ''),
                        "total_hours": details.get('total_hours', ''),
                        "prerequisites": details.get('prerequisites', ''),
                        "prohibited_combinations": details.get('prohibited_combinations', ''),
                        "additional_costs": details.get('additional_costs', ''),
                        "course_organizer": details.get('course_organizer', ''),
                        "url": course_url
                    })
                except ValueError:
                    # Skip if credits cannot be converted to an integer
                    continue

    # Add subjects to the database
    for subject in subjects_to_add:
        existing_subject = Subject.query.filter_by(code=subject["code"]).first()
        if not existing_subject:
            new_subject = Subject(
                name=subject["name"],
                code=subject["code"],
                period=subject["period"],
                credits=subject["credits"],
                scqf=subject["scqf"],
                availability=subject["availability"],
                school=subject["school"],
                college=subject["college"],
                summary=subject["summary"],
                assessment=subject["assessment"],
                learning_outcomes=subject["learning_outcomes"],
                total_hours=subject["total_hours"],
                prerequisites=subject["prerequisites"],
                prohibited_combinations=subject["prohibited_combinations"],
                additional_costs=subject["additional_costs"],
                course_organizer=subject["course_organizer"],
                url=subject["url"],
                created_at=datetime.now()
            )
            db.session.add(new_subject)

    db.session.commit()
    return jsonify({"message": f"{len(subjects_to_add)} subjects added successfully!"})

@app.route('/search_suggestions')
def search_suggestions():
    query = request.args.get('q', '')
    if query:
        subjects = Subject.query.filter(Subject.name.ilike(f'%{query}%')).limit(10).all()
        suggestions = [{'id': subject.id, 'name': subject.name} for subject in subjects]
        return jsonify(suggestions)
    return jsonify([])

if __name__ == '__main__':
    if not os.path.exists('templates'):
        os.makedirs('templates')
    with app.app_context():
        db.create_all()

    app.run(debug=True)
