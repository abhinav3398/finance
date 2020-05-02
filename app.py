import os
from tempfile import mkdtemp

from flask import (Flask, flash, jsonify, redirect, render_template, request,
                   session)
from flask_session import Session
from helpers import apology, login_required, lookup, usd
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from werkzeug.exceptions import (HTTPException, InternalServerError,
                                 default_exceptions)
from werkzeug.security import check_password_hash, generate_password_hash

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure SQLAlchemy Library to use SQLite database
# Set up database
engine = create_engine("sqlite:///finance.db")
db = scoped_session(sessionmaker(bind=engine))

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    # get user id
    user_id = db.execute("SELECT id FROM users WHERE id = :id", {"id": session["user_id"]}).fetchone()[0]
    user_cash = db.execute("SELECT cash FROM users WHERE id = :id", {"id": user_id}).fetchone()[0]
    # make table containing stock information of the user from database
    table = db.execute("SELECT stock, stock_name, SUM(shares), price FROM master_balance_sheet WHERE user_id = :user_id GROUP BY stock", {"user_id" : user_id}).fetchall()

    # create an empty table which can be displayed
    disp_table = []
    spent_cash = 0
    for rows in table:
        # get the prices of the stocks
        try:
            price = lookup(rows[0])["price"]
        except TypeError:
            return apology("server error!fsefes", 400)
        stock_share_price = rows[2]*price
        spent_cash += stock_share_price
        rows = list(rows)
        rows.append(usd(stock_share_price))
        rows[-2] = usd(price)
        if rows[2] != 0:
            # update the displaying table
            disp_table.append(rows)

    return render_template("index.html",table = disp_table, user_cash = usd(user_cash), total = usd(user_cash + spent_cash))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    user_id = db.execute("SELECT id FROM users WHERE id = :id", {"id": session["user_id"]}).fetchone()[0]

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # check if user has provided symbol and shares
        if not request.form.get("symbol") or not request.form.get("shares"):
            return apology("invalid/symbol or shares.", 400)
        else:
            try:
                # get stock info if the stock symbol is correct or throw ValueError
                stock = lookup(request.form.get("symbol"))
                shares = int(request.form.get("shares"))
                if stock == None or shares == None or stock == "" or shares == "" or shares <= 0:
                    return apology("enter valid stock symbol and shares which can be bought.", 400)
                else:
                    stock_name = stock["name"]
                    stock_price = stock["price"]
                    stock_symbol = stock["symbol"]
                    # get user cash
                    user_cash = db.execute("SELECT cash FROM users WHERE id = :id", {"id": session["user_id"]}).fetchone()[0]

                    if (user_cash < shares*stock_price):
                        return apology("enter valid shares which can be bought.", 400)

                    # create and update balance sheet(table)
                    db.execute("CREATE TABLE IF NOT EXISTS master_balance_sheet (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, stock VARCHAR NOT NULL, stock_name VARCHAR NOT NULL, shares INTEGER NOT NULL, price INTEGER NOT NULL, time DATETIME DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (user_id) REFERENCES users (id))")
                    db.execute("INSERT INTO master_balance_sheet (user_id, stock, stock_name, shares, price) VALUES (:user_id, :stock, :stock_name, :shares, :price)", {"user_id": user_id, "stock": stock_symbol, "stock_name": stock_name, "shares": shares, "price": stock_price})
                    # update users table
                    user_cash -= stock_price*shares
                    db.execute("UPDATE users SET cash = :user_cash WHERE id = :id", {"user_cash": user_cash, "id": user_id})
                    # update the database
                    db.commit()
                    return redirect("/")
            except ValueError:
                return apology("enter numerical value in shares", 400)
    else:
        return render_template("buy.html")


@app.route("/check", methods=["GET"])
def check():
    """Return true if username available, else false, in JSON format"""
    username = request.args.get("username")
    users = db.execute("SELECT username FROM users").fetchall()
    if username:
        if len(username) >= 1:
            for user in users:
                if user[0] == username:
                    return jsonify(False)
            return jsonify(True)
        else:
            return jsonify(False)
    else:
        return jsonify(False)

@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    # get user id
    user_id = db.execute("SELECT id FROM users WHERE id = :id", {"id": session["user_id"]}).fetchone()[0]

    # make table containing stock information of the user from database
    table = db.execute("SELECT stock, shares, price, time FROM master_balance_sheet WHERE user_id = :user_id", {"user_id" : user_id}).fetchall()

    # create an empty table which can be displayed
    disp_table = []
    for rows in table:
        # get the prices of the stocks
        price = usd(rows[2])
        rows = list(rows)
        # update the displaying table
        disp_table.append(rows)
    return render_template("history.html",table = disp_table)


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    user_id = db.execute("SELECT id FROM users WHERE id = :id", {"id": session["user_id"]}).fetchone()[0]

    # get information of the user from database
    table = db.execute("SELECT stock, stock_name, SUM(shares), price FROM master_balance_sheet WHERE user_id = :user_id GROUP BY stock", {"user_id" : user_id}).fetchall()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # check if user has provided symbol and shares
        if not request.form.get("symbol") or not request.form.get("shares"):
            return apology("invalid/symbol or shares.", 400)
        else:
            try:
                # get stock info if the stock symbol is correct or throw ValueError
                stock = lookup(request.form.get("symbol"))
                shares = int(request.form.get("shares"))
                if stock == None or shares == None or stock == "" or shares == "":
                    return apology("enter valid stock symbol and shares which can be sold.", 400)
                else:
                    stock_name = stock["name"]
                    stock_price = stock["price"]
                    stock_symbol = stock["symbol"]
                    # get user cash
                    user_cash = db.execute("SELECT cash FROM users WHERE id = :id", {"id": user_id}).fetchone()[0]

                    for row in table:
                        if stock_name == row[1] and shares <= row[2]:
                            # update balance sheet(table)
                            db.execute("INSERT INTO master_balance_sheet (user_id, stock, stock_name, shares, price) VALUES (:user_id, :stock, :stock_name, :shares, :price)", {"user_id": user_id, "stock": stock_symbol, "stock_name": stock_name, "shares": -shares, "price": stock_price})
                            # update users table
                            user_cash += stock_price*shares
                            db.execute("UPDATE users SET cash = :user_cash WHERE id = :id", {"user_cash": user_cash, "id": user_id})
                            # update the database
                            db.commit()
                            return redirect("/")
                    return apology("enter valid stock that you have and stock shares which can be sold.", 400)
            except ValueError:
                return apology("enter numerical value in shares", 400)
    else:
        stock_table = []
        for row in table:
            if row[2] != 0:
                stock_table.append(row[0])
        return render_template("sell.html", stock_table=stock_table)
    # return apology("TODO")


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username", {"username": request.form.get("username")}).fetchall()

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # check if user has provided symbol
        if not request.form.get("symbol"):
            return apology("missing symbol", 400)
        else:
            try:
                message = lookup(request.form.get("symbol"))
                money = usd(message["price"])
                return render_template("quoted.html", company=message["name"], price=money, symbol=message["symbol"])
            except TypeError:
                return apology("missing symbol", 400)
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username and password was submitted
        if not request.form.get("username") or not request.form.get("password"):
            return apology("must provide username and password", 400)

        # Ensure password was confirmed
        elif not request.form.get("confirmation"):
            return apology("must confirm the password", 400)

        username = request.form.get("username")
        password1 = request.form.get("password")
        password2 = request.form.get("confirmation")

        # check authenticity of username and uniqueness of password
        # Query database for username
        rows = db.execute("SELECT username FROM users").fetchall()

        # Ensure username doesn't exists and password is correct
        if password1 != password2:
            return apology("existing username and/or password missmatch. Try again!", 400)
        for row in rows:
            if row[0] == username:
                return apology("existing username and/or password missmatch. Try again!", 400)

        # check length of password1
        if len(password1) <= 7 or len(password1) >= 63:
            return apology("password is too short or too long", 400)

        # ensure password is unique
        uppercase = 0
        lowercase = 0
        number = 0
        special_char = 0
        for c in password1:
            if c.isalpha():
                if c.isupper():
                    uppercase += 1
                elif c.lower():
                    lowercase += 1
            elif c.isdigit():
                number += 1
            else:
                special_char += 1
        lower_pass = password1.lower()
        if set(password1) == set(username) or uppercase == 0 or lowercase == 0 or number == 0 or special_char == 0:
            return apology("password is not unique.", 403)

        # insert new user in the database
        hashed_pass = generate_password_hash(password1)
        db.execute("INSERT INTO users (username, hash) VALUES (:username, :hash)", {"username": username, "hash": hashed_pass})
        db.commit()

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
