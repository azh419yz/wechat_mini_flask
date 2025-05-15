from flask import Flask
from modules.weather_steward import weather_bp
from modules.hello import hello_bp

app = Flask(__name__)

# 注册蓝图
app.register_blueprint(weather_bp, url_prefix='/api/weather')
app.register_blueprint(hello_bp, url_prefix='/api/hello')

if __name__ == '__main__':
    app.run(debug=True)
