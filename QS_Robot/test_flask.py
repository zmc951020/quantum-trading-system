
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask

app = Flask(__name__)

@app.route('/')
def hello():
    return "Hello QS Robot!"

if __name__ == '__main__':
    print("Starting Flask test server on http://localhost:5002")
    app.run(host='0.0.0.0', port=5002, debug=True, use_reloader=False)
