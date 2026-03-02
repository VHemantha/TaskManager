from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, TextAreaField, SelectField, SelectMultipleField, \
    FloatField, DateTimeLocalField, SubmitField, HiddenField
from wtforms.validators import DataRequired, Optional, Length, NumberRange


class TaskForm(FlaskForm):
    title = StringField('Task Title', validators=[DataRequired(), Length(3, 300)])
    description = TextAreaField('Description', validators=[Optional()])
    category_id = SelectField('Category', coerce=int, validators=[Optional()])
    client_id = SelectField('Client', coerce=int, validators=[Optional()])
    assignees = SelectMultipleField('Assign To', coerce=int, validators=[Optional()])
    priority = SelectField('Priority', choices=[
        ('urgent', 'Urgent'), ('high', 'High'), ('medium', 'Medium'), ('low', 'Low')
    ], default='medium')
    due_date = DateTimeLocalField('Due Date', format='%Y-%m-%dT%H:%M', validators=[Optional()])
    estimated_hours = FloatField('Estimated Hours', validators=[Optional(), NumberRange(min=0)])
    tags = StringField('Tags (comma separated)', validators=[Optional(), Length(max=500)])
    submit = SubmitField('Save Task')


class StatusUpdateForm(FlaskForm):
    new_status = HiddenField('New Status', validators=[DataRequired()])
    notes = TextAreaField('Notes (optional)', validators=[Optional(), Length(max=500)])
    submit = SubmitField('Update Status')


class CommentForm(FlaskForm):
    message = TextAreaField('Comment', validators=[DataRequired(), Length(1, 5000)])
    submit = SubmitField('Post Comment')


class AttachmentForm(FlaskForm):
    file = FileField('Attach File', validators=[
        FileAllowed(['pdf', 'xlsx', 'xls', 'docx', 'doc', 'png', 'jpg', 'jpeg', 'zip', 'csv', 'txt'],
                    'Allowed: PDF, Excel, Word, Images, ZIP, CSV, TXT')
    ])
    submit = SubmitField('Upload')


class TimeLogForm(FlaskForm):
    hours = FloatField('Hours Worked', validators=[DataRequired(), NumberRange(min=0.1, max=24)])
    description = StringField('Description', validators=[Optional(), Length(max=300)])
    submit = SubmitField('Log Time')


class TaskFilterForm(FlaskForm):
    status = SelectField('Status', choices=[('', 'All Statuses')], validators=[Optional()])
    priority = SelectField('Priority', choices=[('', 'All Priorities')], validators=[Optional()])
    assignee_id = SelectField('Assignee', coerce=int, choices=[(0, 'All Members')], validators=[Optional()])
    client_id = SelectField('Client', coerce=int, choices=[(0, 'All Clients')], validators=[Optional()])
    search = StringField('Search', validators=[Optional(), Length(max=100)])
    submit = SubmitField('Filter')
