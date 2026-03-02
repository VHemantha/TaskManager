from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, SubmitField
from wtforms.fields import DateTimeLocalField
from wtforms.validators import DataRequired, Optional, Length
from app.models.sprint import SPRINT_PLANNING, SPRINT_ACTIVE, SPRINT_COMPLETED


class SprintForm(FlaskForm):
    name = StringField('Sprint Name', validators=[DataRequired(), Length(max=200)])
    goal = TextAreaField('Sprint Goal', validators=[Optional()])
    team_id = SelectField('Team', coerce=int, validators=[Optional()])
    start_date = DateTimeLocalField('Start Date', format='%Y-%m-%dT%H:%M',
                                    validators=[Optional()])
    end_date = DateTimeLocalField('End Date', format='%Y-%m-%dT%H:%M',
                                  validators=[Optional()])
    status = SelectField('Status', choices=[
        (SPRINT_PLANNING,  'Planning'),
        (SPRINT_ACTIVE,    'Active'),
        (SPRINT_COMPLETED, 'Completed'),
    ])
    submit = SubmitField('Save Sprint')
