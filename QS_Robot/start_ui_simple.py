
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("Loading modules...")

from config.config import config
from llm_manager import llm_manager
from extensions.data_sources import AuroraDataSource

from flask import Flask, render_template, jsonify, request, send_from_directory
from flask_cors import CORS

app = Flask(__name__, static_folder=os.path.join('ui', 'static'), template_folder=os.path.join('ui', 'templates'))
CORS(app)

data_source = AuroraDataSource()
data_source.connect()

print("Flask app initialized!")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        data = request.get_json()
        user_message = data.get('message', '')
        
        system_prompt = "你是量化交易系统QS Robot的智能助手，用简洁、专业的中文回答问题。"
        
        response = llm_manager.simple_chat(user_message, system_prompt)
        return jsonify({"success": True, "response": response})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/system/connect', methods=['POST'])
def connect_system():
    success = data_source.connect()
    return jsonify({"success": success})

@app.route('/api/system/status', methods=['GET'])
def system_status():
    try:
        strategies = data_source.get_data({"type": "strategies"})
        health = data_source.get_data({"type": "health"})
        return jsonify({
            "success": True,
            "data": {
                "connected": data_source.is_connected(),
                "strategies": strategies,
                "health": health,
                "llm_available": llm_manager.active_provider is not None and llm_manager.active_provider.is_available()
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/static/&lt;path:filename&gt;')
def static_files(filename):
    return send_from_directory(os.path.join('ui', 'static'), filename)

if __name__ == '__main__':
    print("=" * 60)
    print("QS Robot 智能助手")
    print("访问地址: http://127.0.0.1:5001")
    print("=" * 60)
    app.run(host='127.0.0.1', port=5001, debug=True, use_reloader=False)
