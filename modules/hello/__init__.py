from flask import Blueprint

hello_bp = Blueprint('hello', __name__)

@hello_bp.route('/', methods=['GET'])
def hello():
    return {'message': 'Hello World!'} 