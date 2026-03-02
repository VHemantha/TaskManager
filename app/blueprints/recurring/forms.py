from flask_wtf import FlaskForm
from wtforms import (StringField, TextAreaField, SelectField, SelectMultipleField,
                     FloatField, IntegerField, BooleanField, SubmitField, DateTimeLocalField)
from wtforms.validators import DataRequired, Optional, Length, NumberRange


class RecurringTaskForm(FlaskForm):
    title = StringField('Task Title', validators=[DataRequired(), Length(3, 300)])
    description = TextAreaField('Description', validators=[Optional()])
    category_id = SelectField('Category', coerce=int, validators=[Optional()])
    client_id = SelectField('Client', coerce=int, validators=[Optional()])
    assignees = SelectMultipleField('Assign To', coerce=int, validators=[Optional()])
    priority = SelectField('Priority', choices=[
        ('urgent', 'Urgent'), ('high', 'High'), ('medium', 'Medium'), ('low', 'Low')
    ], default='medium')
    estimated_hours = FloatField('Estimated Hours', validators=[Optional(), NumberRange(min=0)])
    frequency = SelectField('Frequency', choices=[
        ('daily', 'Daily'), ('weekly', 'Weekly'), ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'), ('annually', 'Annually'),
    ], default='monthly')
    first_due_date = DateTimeLocalField(
        'First Due Date', format='%Y-%m-%dT%H:%M',
        validators=[DataRequired()],
        description='The due date for the first generated task.',
    )
    lead_days = IntegerField(
        'Lead Days', default=1,
        validators=[Optional(), NumberRange(0, 30)],
        description='Create the task this many days before its due date.',
    )
    is_active = BooleanField('Active', default=True)
    submit = SubmitField('Save Recurring Task')
