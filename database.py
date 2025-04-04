# database.py
import mysql.connector

def get_mysql_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="Heera@2004",
        database="chatbot_db"
    )
