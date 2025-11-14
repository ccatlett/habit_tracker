from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import date, timedelta

app = Flask(__name__)

# --- Database Configuration ---
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///habit_tracker.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config['SECRET_KEY'] = 'my_super_secret_string_12345'
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = False

db = SQLAlchemy(app)


# --- Models ---
class Habit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(250))
    created_at = db.Column(db.Date, default=date.today)

    completions = db.relationship("Completion", backref="habit", cascade="all, delete-orphan")
    time_of_day = db.Column(db.String(2), nullable=False, default='☀️')  # day

    def __repr__(self):
        return f"<Habit {self.name}>"


class Completion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    habit_id = db.Column(db.Integer, db.ForeignKey('habit.id'))
    date = db.Column(db.Date)
    completed = db.Column(db.Boolean, default=False)

    # Freeze habit info at time of creation
    name = db.Column(db.String)
    description = db.Column(db.String)
    time_of_day = db.Column(db.String)

    def __repr__(self):
        return f"<Completion {self.habit_id} on {self.date}: {self.completed}>"


# --- Routes ---
@app.route('/')
def index():
    time_order = {'⛅️': 0, '☀️': 1, '🌇': 2, '🌠': 3}
    habits = Habit.query.all()
    habits.sort(key=lambda h: (time_order.get(h.time_of_day, 4), h.name.lower()))
    
    today = date.today()
    start_of_week = today - timedelta(days=today.weekday())  # Monday
    week_dates = [start_of_week + timedelta(days=i) for i in range(7)]

    completions = Completion.query.all()
    completed_map = {(c.habit_id, c.date): True for c in completions}

    # Calculate weekly progress
    habit_progress = {}
    for habit in habits:
        completed_days = sum(1 for d in week_dates if completed_map.get((habit.id, d)))
        habit_progress[habit.id] = completed_days / 7  # fraction 0-1

    # --- Compute last week's progress ---
    last_week_dates = [d - timedelta(days=7) for d in week_dates]

    last_week_progress = {}
    for habit in habits:
        completed_days_last = sum(
            1 for d in last_week_dates if completed_map.get((habit.id, d))
        )
        last_week_progress[habit.id] = completed_days_last / 7

    # --- Compute trend icon ---
    trend_icon = {}
    for habit in habits:
        curr = habit_progress[habit.id]
        last = last_week_progress[habit.id]

        if curr > last:
            trend_icon[habit.id] = "📈"   # improved
        elif curr < last:
            trend_icon[habit.id] = "📉"   # worse
        else:
            trend_icon[habit.id] = "➖"   # flat

    return render_template(
        'index.html',
        habits=habits,
        week_dates=week_dates,
        completed_map=completed_map,
        habit_progress=habit_progress,
        trend_icon=trend_icon
    )


@app.route('/toggle', methods=['POST'])
def toggle_completion():
    habit_id = int(request.form['habit_id'])
    day = date.fromisoformat(request.form['day'])

    # Lookup the habit in the database
    habit = Habit.query.get(habit_id)

    # Now you have all the info to freeze
    name = habit.name
    description = habit.description
    time_of_day = habit.time_of_day

    existing = Completion.query.filter_by(habit_id=habit_id, date=day).first()
    if existing:
        db.session.delete(existing)
    else:
        new_completion = Completion(
        habit_id=habit_id,
        date=day,
        completed=True,
        name=name,
        description=description,
        time_of_day=time_of_day)
        db.session.add(new_completion)
    db.session.commit()

    return redirect(url_for('index'))

@app.route('/reset_week', methods=['POST'])
def reset_week():
    today = date.today()
    start_of_week = today - timedelta(days=today.weekday())
    end_of_week = start_of_week + timedelta(days=6)

    completions = Completion.query.filter(
        Completion.date.between(start_of_week, end_of_week)
    ).all()
    for c in completions:
        db.session.delete(c)
    db.session.commit()

    return redirect(url_for('index'))

@app.route('/add_habit', methods=['POST'])
def add_habit():
    name = request.form['name']
    description = request.form.get('description', '')
    time_of_day = request.form.get('time_of_day', '⛅️')
    new_habit = Habit(name=name, description=description, time_of_day=time_of_day)
    db.session.add(new_habit)
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/delete_habit/<int:habit_id>', methods=['POST'])
def delete_habit(habit_id):
    habit = Habit.query.get_or_404(habit_id)
    Completion.query.filter_by(habit_id=habit.id).delete()
    db.session.delete(habit)
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/edit_habit/<int:habit_id>', methods=['GET', 'POST'])
def edit_habit(habit_id):
    habit = Habit.query.get_or_404(habit_id)
    if request.method == 'POST':
        habit.name = request.form['name']
        habit.description = request.form['description']
        habit.time_of_day = request.form['time_of_day']
        db.session.commit()
        return redirect(url_for('index'))  # After edit, re-render table
    return render_template('edit_habit.html', habit=habit)


@app.route('/update_time_of_day/<int:habit_id>', methods=['POST'])
def update_time_of_day(habit_id):
    habit = Habit.query.get_or_404(habit_id)
    habit.time_of_day = request.form['time_of_day']
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/admin')
def admin_panel():
    habits = Habit.query.order_by(Habit.id).all()
    completions = Completion.query.order_by(Completion.id).all()
    return render_template('admin.html', habits=habits, completions=completions)



# --- Initialize Database ---
with app.app_context():
    db.create_all()


if __name__ == "__main__":
     app.run(host='127.0.0.1', port=8000, debug=False)
