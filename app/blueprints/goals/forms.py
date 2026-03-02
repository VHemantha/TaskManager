from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, SubmitField
from wtforms.fields import DateTimeLocalField
from wtforms.validators import DataRequired, Optional, Length
from app.models.goal import GOAL_ON_TRACK, GOAL_AT_RISK, GOAL_OFF_TRACK, GOAL_ACHIEVED


class GoalForm(FlaskForm):
    name = StringField('Goal Name', validators=[DataRequired(), Length(max=300)])
    description = TextAreaField('Description', validators=[Optional()])
    owner_id = SelectField('Owner', coerce=int, validators=[DataRequired()])
    team_id = SelectField('Team', coerce=int, validators=[Optional()])
    target_date = DateTimeLocalField('Target Date', format='%Y-%m-%dT%H:%M',
                                     validators=[Optional()])
    status = SelectField('Status', choices=[
        (GOAL_ON_TRACK,  'On Track'),
        (GOAL_AT_RISK,   'At Risk'),
        (GOAL_OFF_TRACK, 'Off Track'),
        (GOAL_ACHIEVED,  'Achieved'),
    ])
    submit = SubmitField('Save Goal')
