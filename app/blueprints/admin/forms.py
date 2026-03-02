from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, BooleanField, SubmitField, TextAreaField, PasswordField
from wtforms.validators import DataRequired, Regexp, Length, Optional, ValidationError
from app.models.user import ALL_ROLES, ROLE_LABELS

_email = Regexp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', message='Enter a valid email address.')


class UserForm(FlaskForm):
    name = StringField('Full Name', validators=[DataRequired(), Length(2, 120)])
    email = StringField('Email', validators=[DataRequired(), _email])
    role = SelectField('Role', choices=[(r, ROLE_LABELS[r]) for r in ALL_ROLES], validators=[DataRequired()])
    team_id = SelectField('Team', coerce=int, validators=[Optional()])
    phone = StringField('Phone', validators=[Optional(), Length(max=20)])
    is_active = BooleanField('Active', default=True)
    password = PasswordField('Password (leave blank to keep unchanged)', validators=[Optional(), Length(0, 128)])
    submit = SubmitField('Save User')


class TeamForm(FlaskForm):
    name = StringField('Team Name', validators=[DataRequired(), Length(2, 100)])
    description = TextAreaField('Description', validators=[Optional(), Length(max=500)])
    leader_id = SelectField('Team Leader', coerce=int, validators=[Optional()])
    submit = SubmitField('Save Team')


class ClientForm(FlaskForm):
    name = StringField('Client Name', validators=[DataRequired(), Length(2, 200)])
    code = StringField('Client Code', validators=[DataRequired(), Length(2, 50)])
    contact_person = StringField('Contact Person', validators=[Optional(), Length(max=120)])
    email = StringField('Email', validators=[Optional(), _email])
    phone = StringField('Phone', validators=[Optional(), Length(max=20)])
    address = TextAreaField('Address', validators=[Optional(), Length(max=500)])
    gstin = StringField('GSTIN', validators=[Optional(), Length(max=20)])
    is_active = BooleanField('Active', default=True)
    submit = SubmitField('Save Client')


class TaskCategoryForm(FlaskForm):
    name = StringField('Category Name', validators=[DataRequired(), Length(2, 50)])
    description = StringField('Description', validators=[Optional(), Length(max=200)])
    color_code = StringField('Color', validators=[DataRequired()], default='#6c757d')
    submit = SubmitField('Save Category')
