"""Provides all routes for the Social Insecurity application.

This file contains the routes for the application. It is imported by the social_insecurity package.
It also contains the SQL queries used for communicating with the database.
"""

from pathlib import Path
import bleach
import bcrypt
from flask import current_app as app
from flask import flash, redirect, render_template, request, send_from_directory, url_for, session
from flask_login import login_required, login_user, logout_user, current_user

from social_insecurity import sqlite

#import bcrypt
from social_insecurity.database import get_user_by_username
from social_insecurity.forms import CommentsForm, FriendsForm, IndexForm, LoginForm, PostForm, ProfileForm


@app.route("/", methods=["GET", "POST"])
@app.route("/index", methods=["GET", "POST"])
def index():
    """Provides the index page for the application.

    It reads the composite IndexForm and based on which form was submitted,
    it either logs the user in or registers a new user.

    If no form was submitted, it simply renders the index page.
    """
    index_form = IndexForm()
    register_form = index_form.register
    login_form = index_form.login
    if login_form.is_submitted() and login_form.validate_on_submit():
        username = login_form.username.data
        
        password = login_form.password.data
        user = get_user_by_username(sqlite, username)  # Retrieve user by username

        if user and bcrypt.checkpw(password.encode(), user.password.encode()):  # Password validation
            login_user(user)
            return redirect(url_for("stream", username=username))
        else:
            flash("Invalid username or password", category="danger")
            return redirect(url_for("index"))
    

    # Registration logic
    elif register_form.is_submitted() and register_form.submit.data:
        sanitized_first_name = bleach.clean(register_form.first_name.data)
        sanitized_last_name = bleach.clean(register_form.last_name.data)
        sanitized_username = bleach.clean(register_form.username.data)
        hashed_password = bcrypt.hashpw(register_form.password.data.encode(), bcrypt.gensalt())
        insert_user = f"""
            INSERT INTO Users (username, first_name, last_name, password)
            VALUES ('{sanitized_username}', '{sanitized_first_name}', '{sanitized_last_name}', '{hashed_password.decode()}');
        """
        sqlite.query(insert_user)
        flash("User successfully created!", category="success")
        return redirect(url_for("index"))

    return render_template("index.html.j2", title="Welcome", form=index_form)

    
@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", category="info")
    return redirect(url_for("index"))


@app.route("/stream", methods=["GET", "POST"])
@login_required
def stream():#removed username: str
    """Provides the stream page for the application.

    If a form was submitted, it reads the form data and inserts a new post into the database.

    Otherwise, it reads the username from the URL and displays all posts from the user and their friends.
    """
    post_form = PostForm()
    username = current_user.username #added
    get_user = f"""
        SELECT *
        FROM Users
        WHERE username = '{username}';
        """
    user = sqlite.query(get_user, one=True)

    if post_form.is_submitted():
        if post_form.image.data:
            path = Path(app.instance_path) / app.config["UPLOADS_FOLDER_PATH"] / post_form.image.data.filename
            post_form.image.data.save(path)
        sanitized_content = bleach.clean(post_form.content.data)
        insert_post = f"""
            INSERT INTO Posts (u_id, content, image, creation_time)
            VALUES ({user["id"]}, '{sanitized_content}', '{post_form.image.data.filename}', CURRENT_TIMESTAMP);
            """
        sqlite.query(insert_post)
        return redirect(url_for("stream", username=username))

    get_posts = f"""
         SELECT p.*, u.*, (SELECT COUNT(*) FROM Comments WHERE p_id = p.id) AS cc
         FROM Posts AS p JOIN Users AS u ON u.id = p.u_id
         WHERE p.u_id IN (SELECT u_id FROM Friends WHERE f_id = {user["id"]}) OR p.u_id IN (SELECT f_id FROM Friends WHERE u_id = {user["id"]}) OR p.u_id = {user["id"]}
         ORDER BY p.creation_time DESC;
        """
    posts = sqlite.query(get_posts)
    return render_template("stream.html.j2", title="Stream", username=username, form=post_form, posts=posts)


@app.route("/comments/<int:post_id>", methods=["GET", "POST"])

def comments(post_id: int):
    """Provides the comments page for the application.

    If a form was submitted, it reads the form data and inserts a new comment into the database.

    Otherwise, it reads the username and post id from the URL and displays all comments for the post.
    """
    comments_form = CommentsForm()
    username = current_user.username #added
    get_user = f"""
        SELECT *
        FROM Users
        WHERE username = '{username}';
        """
    user = sqlite.query(get_user, one=True)

    if comments_form.is_submitted():
        sanitized_comment = bleach.clean(comments_form.comment.data)
        insert_comment = f"""
            INSERT INTO Comments (p_id, u_id, comment, creation_time)
            VALUES ({post_id}, {user["id"]}, '{sanitized_comment}', CURRENT_TIMESTAMP);
            """
        sqlite.query(insert_comment)

    get_post = f"""
        SELECT *
        FROM Posts AS p JOIN Users AS u ON p.u_id = u.id
        WHERE p.id = {post_id};
        """
    get_comments = f"""
        SELECT DISTINCT *
        FROM Comments AS c JOIN Users AS u ON c.u_id = u.id
        WHERE c.p_id={post_id}
        ORDER BY c.creation_time DESC;
        """
    post = sqlite.query(get_post, one=True)
    comments = sqlite.query(get_comments)
    return render_template(
        "comments.html.j2", title="Comments", username=username, form=comments_form, post=post, comments=comments
    )


@app.route("/friends", methods=["GET", "POST"])
@login_required
def friends():
    """Provides the friends page for the application.

    If a form was submitted, it reads the form data and inserts a new friend into the database.

    Otherwise, it reads the username from the URL and displays all friends of the user.
    """
    friends_form = FriendsForm()
    username = current_user.username #added
    get_user = f"""
        SELECT *
        FROM Users
        WHERE username = '{username}';
        """
    user = sqlite.query(get_user, one=True)

    if friends_form.is_submitted():
        get_friend = f"""
            SELECT *
            FROM Users
            WHERE username = '{friends_form.username.data}';
            """
        friend = sqlite.query(get_friend, one=True)
        get_friends = f"""
            SELECT f_id
            FROM Friends
            WHERE u_id = {user["id"]};
            """
        friends = sqlite.query(get_friends)

        if friend is None:
            flash("User does not exist!", category="warning")
        elif friend["id"] == user["id"]:
            flash("You cannot be friends with yourself!", category="warning")
        elif friend["id"] in [friend["f_id"] for friend in friends]:
            flash("You are already friends with this user!", category="warning")
        else:
            insert_friend = f"""
                INSERT INTO Friends (u_id, f_id)
                VALUES ({user["id"]}, {friend["id"]});
                """
            sqlite.query(insert_friend)
            flash("Friend successfully added!", category="success")

    get_friends = f"""
        SELECT *
        FROM Friends AS f JOIN Users as u ON f.f_id = u.id
        WHERE f.u_id = {user["id"]} AND f.f_id != {user["id"]};
        """
    friends = sqlite.query(get_friends)
    return render_template("friends.html.j2", title="Friends", username=username, friends=friends, form=friends_form)


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    """Provides the profile page for the application.

    If a form was submitted, it reads the form data and updates the user's profile in the database.

    Otherwise, it reads the username from the URL and displays the user's profile.
    """
    profile_form = ProfileForm()
    username = current_user.username #added
    get_user = f"""
        SELECT *
        FROM Users
        WHERE username = '{username}';
        """
    user = sqlite.query(get_user, one=True)

    if profile_form.is_submitted():
        sanitized_education = bleach.clean(profile_form.education.data)
        sanitized_employment = bleach.clean(profile_form.employment.data)
        sanitized_music = bleach.clean(profile_form.music.data)
        sanitized_movie = bleach.clean(profile_form.movie.data)
        sanitized_nationality = bleach.clean(profile_form.nationality.data)
        update_profile = f"""
            UPDATE Users
            SET education='{sanitized_education}', employment='{sanitized_employment}',
                music='{sanitized_music}', movie='{sanitized_movie}',
                nationality='{sanitized_nationality}', birthday='{profile_form.birthday.data}'
            WHERE username='{username}';
            """
        sqlite.query(update_profile)
        return redirect(url_for("profile", username=username))

    return render_template("profile.html.j2", title="Profile", username=username, user=user, form=profile_form)


@app.route("/uploads/<string:filename>")
@login_required
def uploads(filename):
    """Provides an endpoint for serving uploaded files."""
    return send_from_directory(Path(app.instance_path) / app.config["UPLOADS_FOLDER_PATH"], filename)
