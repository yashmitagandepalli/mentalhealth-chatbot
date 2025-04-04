from flask import Flask, request, jsonify, render_template, session, redirect, url_for,flash
import sqlite3
import os
import google.generativeai as genai
from dotenv import load_dotenv
from flask_cors import CORS  # Import CORS to handle Cross-Origin requests
import re
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash


# Load environment variables
load_dotenv()

# Get API key
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("❌ GEMINI_API_KEY is missing! Check your .env file.")

# Initialize Gemini API
genai.configure(api_key=api_key)

# Initialize Flask app
app = Flask(__name__, template_folder="templates", static_folder="static")

# Enable CORS for all routes
CORS(app, resources={r"/*": {"origins": "*"}})

# Set Flask secret key
secret_key = os.getenv("SECRET_KEY")  
if not secret_key:
    raise ValueError("❌ SECRET_KEY is missing! Check your .env file.")

app.secret_key = secret_key  

def init_db():
    """Initialize the database and create necessary tables."""
    conn = sqlite3.connect("chatbot.db")  # Connect to the SQLite database
    cursor = conn.cursor()

    # Create the 'users' table if it doesn't already exist
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)

    #Create the 'chats' table with a foreign key referencing the 'users' table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            guest_id TEXT,
            message TEXT NOT NULL,
            reply TEXT NOT NULL,
            timestamp TEXT NOT NULL,  
            FOREIGN KEY(user_id) REFERENCES users(id) 
        )
    """)

    conn.commit()  # Commit the changes to the database
    conn.close()  # Close the connection to the database

# Call the init_db function to initialize the database
init_db()
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/signup.html", methods=["GET", "POST"])
def signup():
    print("✅ Signup route accessed!")  # Debugging

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        
        print(f"🔹 Received Signup Request: {username}, {password}")  # Debugging

        conn = sqlite3.connect("chatbot.db")
        cursor = conn.cursor()
        
        try:
            cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
            conn.commit()
            print("✅ User added successfully!")  # Debugging

            return redirect(url_for("login"))  # Make sure a login route exists

        except sqlite3.IntegrityError:
            print("❌ Username already exists!")  # Debugging
            return "❌ Username already exists!"
        finally:
            conn.close()
    
    return render_template("signup.html")




@app.route("/login.html", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        
        conn = sqlite3.connect("chatbot.db")
        cursor = conn.cursor()
        
        # Check the provided username against the database
        cursor.execute("SELECT id, password FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        conn.close()
        
        if user:
            user_id, stored_password = user
            
            # Directly compare the entered password with the stored password
            if stored_password == password:
                session["user_id"] = user_id
                return redirect(url_for("chatbot_response"))  # Redirect to the chat page
            else:
                return "❌ Invalid password!"
        else:
            return "❌ Invalid credentials!"
    
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("user_id", None)
    session.pop("guest_id", None)
    return redirect(url_for("home"))

@app.route("/chat", methods=["GET", "POST"])
def chat():
    if "guest_id" not in session:
        session["guest_id"] = os.urandom(8).hex()

    guest_id = session["guest_id"]

    if "chat_history" not in session:
        session["chat_history"] = []

    # Fetch chat history from the database
    try:
        with sqlite3.connect("chatbot.db") as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT message, reply FROM chats WHERE guest_id = ?", (guest_id,))
            db_chat_history = [{"message": row[0], "reply": row[1]} for row in cursor.fetchall()]
    except Exception as e:
        print(f"Database error: {str(e)}")
        return jsonify({"error": "Database error occurred"}), 500

    # Merge chat history (session + database)
    combined_chat_history = db_chat_history + session["chat_history"]

    if request.method == "POST":
        user_input = request.json.get("message")
        if not user_input:
            return jsonify({"error": "❌ Message is required"}), 400

        try:
            prompt = f"""
            **User Query:** {user_input}

            ### **Response Guidelines:**  
            - **For greetings (e.g., "Hello", "Hey", "Hi") → Keep it short & natural.** Example:  
              - _User:_ Hello  
              - _AI:_ Hey there! 😊 How's your day going?  
            - **For advice or queries → Give structured, friendly responses with warmth.**  
            - Talk **like a friend**—engaging, supportive, and relatable.  
            - Use **short, clear paragraphs**, no bullet points unless the topic needs it.  
            - Add **relevant emojis** for warmth and expressiveness in your response.
            - behave like a best friend.
            - Structurise your responses based on user's questions.
            - Do not forget to add emojis to enhance your responses.
            - Do not use point wise responses which contain numbers. Conversions should be natural and friendly.
            - Conversion flow should be very simple and friendly. Do not use "**" etc.
            - Use a clear format so that it can be read easily.
            - Do not generate bot like responses. Please behave like a human and best friend.

            **Now, respond appropriately based on the input.**  
            """

            # Call to the generative model
            model = genai.GenerativeModel("gemini-1.5-pro")
            response = model.generate_content(prompt)

            # Check response format and handle appropriately
            if not hasattr(response, "text"):
                print(f"Unexpected response format: {response}")
                reply = str(response)
            else:
                reply = response.text

            # Append the chat to session history
            session["chat_history"].append({"message": user_input, "reply": reply})

            # Limit session chat history size to 50 to prevent memory issues
            if len(session["chat_history"]) > 50:
                session["chat_history"] = session["chat_history"][-50:]

            # Save chat history in the database
            try:
                with sqlite3.connect("chatbot.db") as conn:
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO chats (guest_id, message, reply) VALUES (?, ?, ?)",
                                   (guest_id, user_input, reply))
                    conn.commit()
            except sqlite3.DatabaseError as db_err:
                print(f"Database insert error: {db_err}")
                return jsonify({"error": "Failed to store chat in database"}), 500

            # Return the combined chat history as JSON
            return jsonify({"reply": reply, "chat_history": combined_chat_history})

        except Exception as e:
            # Log error for debugging
            print(f"Error occurred: {str(e)}")
            return jsonify({"error": f"An error occurred: {str(e)}"}), 500

    # Render chat page with combined chat history
    return render_template("chat.html", chat_history=combined_chat_history)
@app.route("/api/chat-history", methods=["GET"])
def api_chat_history():
    if "guest_id" not in session:
        session["guest_id"] = os.urandom(8).hex()

    guest_id = session["guest_id"]

    # Fetch chat history from the database
    try:
        with sqlite3.connect("chatbot.db") as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT message, reply FROM chats WHERE guest_id = ?", (guest_id,))
            db_chat_history = [{"message": row[0], "reply": row[1]} for row in cursor.fetchall()]
    except Exception as e:
        print(f"Database error: {str(e)}")
        return jsonify({"error": "Database error occurred"}), 500

    # Send the full chat history for the chat history bar
    return jsonify({
        "full_chat_history": db_chat_history + session.get("chat_history", [])  # Full history for the chat history bar
    })


@app.route("/chatbot", methods=["GET", "POST"])
def chatbot_response():
    # Handling GET request (just displaying the chat interface)
    if request.method == "GET":
        return render_template("chatbot.html")

    # Handling POST request (processing the chatbot response)
    if request.method == "POST":
        # Retrieve user input and session data
        user_input = request.json.get("message")
        user_id = session.get("user_id")  # Get the logged-in user's ID from the session
        print(f"Received message: {user_input}")  # Log the received message

        if not user_id:
            return jsonify({"error": "❌ User is not logged in."}), 400  # Ensure only logged-in users can chat

        try:
            # Fetching available AI models (if needed)
            available_models = model.list_models()  # If supported by the API client
            print("Available models:", available_models)  # Log the models available
        except Exception as e:
            print("Error fetching available models:", str(e))

        if not user_input:
            return jsonify({"error": "❌ Message is required"}), 400

        try:
            # Generate a structured prompt based on the user's input
            prompt = f"""
            **User Query:** {user_input}

            ### **Response Guidelines:**  
            - **For greetings (e.g., "Hello", "Hey", "Hi") → Keep it short & natural.** Example:  
              - _User:_ Hello  
              - _AI:_ Hey there! 😊 How's your day going?  
            - **For advice or queries → Give structured, friendly responses with warmth.**  
            - Talk **like a friend**—engaging, supportive, and relatable.  
            - Use **short, clear paragraphs**, no bullet points unless the topic needs it.  
            - Add **relevant emojis** for warmth and expressiveness in your response.
            - Behave like a best friend.
            - Structure your responses based on the user's questions.
            - Do not forget to add emojis to enhance your responses.
            - Do not use point-wise responses that contain numbers. Conversions should be natural and friendly.
            - The conversation flow should be very simple and friendly. Avoid using "**" and similar formatting.
            - Use emojis in between responses.
            - Use a clear format so that it is easy to read.
            - Do not generate bot-like responses. Please behave like a human and a best friend.
            **Now, respond appropriately based on the input.**
            """

            # Log the prompt to check what is being sent to the AI
            print(f"Prompt being sent to AI: {prompt}")

            # Generate response from AI model
            model = genai.GenerativeModel("gemini-1.5-pro")
            response = model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.9,
                    "top_p": 0.95,
                    "max_output_tokens": 300
                }
            )

            # Log the response from AI to check if it's valid
            print(f"Response from AI: {response}")

            if not response or not hasattr(response, "text"):
                raise ValueError("AI response is invalid")

            reply = response.text if hasattr(response, "text") else str(response)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Save the chat in the database
            with sqlite3.connect("chatbot.db") as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO chats (user_id, message, reply, timestamp) 
                    VALUES (?, ?, ?, ?)
                """, (user_id, user_input, reply, timestamp))
                conn.commit()

            # Process the reply and return a structured response
            points = [point.strip() for point in reply.split("-") if point.strip()]
            return jsonify({"reply": points})

        except Exception as e:
            # Log the error
            print(f"Error: {str(e)}")
            return jsonify({"error": f"An error occurred: {str(e)}"}), 500


@app.route("/get_chats", methods=["GET"])
def get_chats():
    user_id = session.get("user_id")  # Get the logged-in user's ID from the session

    if not user_id:
        return jsonify({"error": "❌ User is not logged in."}), 400

    try:
        # Query chats for the logged-in user only
        with sqlite3.connect("chatbot.db") as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT message, reply, timestamp FROM chats WHERE user_id = ? ORDER BY timestamp DESC", (user_id,))
            chats = cursor.fetchall()

        chat_history = []
        for chat in chats:
            chat_history.append({
                "message": chat[0],
                "reply": chat[1],
                "timestamp": chat[2]
            })

        return jsonify({"chat_history": chat_history})

    except Exception as e:
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500


@app.route("/check_login", methods=["GET"])
def check_login():
    if "user_id" in session:
        return jsonify({"logged_in": True})
    else:
        return jsonify({"logged_in": False})
@app.route("/save_message", methods=["POST"])
def save_message():
    user_message = request.json.get("message")
    bot_reply = request.json.get("reply")

    # Get user_id from session or other authentication mechanism
    user_id = session.get("user_id")
    
    if not user_id:
        return jsonify({"error": "User not logged in"}), 400

    try:
        # Store the user message and bot reply in the database
        with sqlite3.connect("chatbot.db") as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO chats (user_id, message, reply, timestamp) VALUES (?, ?, ?, ?)", 
                           (user_id, user_message, bot_reply, datetime.now()))
            conn.commit()
        
        return jsonify({"status": "success"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
