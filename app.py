from flask import Flask, render_template, jsonify
import sqlite3
import json
import os

app = Flask(__name__)

def get_db_connection():
    conn = sqlite3.connect('bot_database.db')
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    """Главная страница с информацией о боте."""
    return render_template('index.html')

@app.route('/teams')
def teams():
    """API для получения всех команд."""
    conn = get_db_connection()
    teams = conn.execute('SELECT * FROM teams').fetchall()
    conn.close()
    
    teams_list = []
    for team in teams:
        members = json.loads(team['members'])
        teams_list.append({
            'id': team['id'],
            'name': team['name'],
            'members': members,
            'created_by': team['created_by'],
            'created_at': team['created_at']
        })
    
    return jsonify(teams_list)

@app.route('/reminders')
def reminders():
    """API для получения всех напоминаний."""
    conn = get_db_connection()
    reminders = conn.execute('SELECT * FROM reminders').fetchall()
    conn.close()
    
    reminders_list = []
    for reminder in reminders:
        reminders_list.append({
            'id': reminder['id'],
            'user_id': reminder['user_id'],
            'reminder_time': reminder['reminder_time'],
            'reminder_text': reminder['reminder_text'],
            'team_name': reminder['team_name'],
            'created_at': reminder['created_at']
        })
    
    return jsonify(reminders_list)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)