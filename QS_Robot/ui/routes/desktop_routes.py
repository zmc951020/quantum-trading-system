# -*- coding: utf-8 -*-
"""桌面 API 路由"""
import os
import sys
import subprocess
from flask import request, jsonify, send_from_directory


def register_routes(app):
    @app.route('/api/launch_desktop', methods=['POST'])
    def launch_desktop():
        """启动QS Robot桌面应用"""
        try:
            qs_robot_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            desktop_script = os.path.join(qs_robot_path, 'qs_robot_desktop_v2.py')
            if not os.path.exists(desktop_script):
                return jsonify({"success": False, "error": "桌面应用脚本不存在"}), 404
            subprocess.Popen(
                [sys.executable, desktop_script],
                cwd=qs_robot_path,
                creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == 'win32' else 0
            )
            return jsonify({"success": True, "message": "QS Robot桌面应用已启动", "path": desktop_script})
        except Exception as e:
            import traceback
            return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500

    
