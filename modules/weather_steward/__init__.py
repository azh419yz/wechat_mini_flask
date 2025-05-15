from flask import Blueprint, request, jsonify
import requests
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text, MetaData, Table, Column, String, Float, TIMESTAMP, func, Numeric, CHAR, \
    DECIMAL

load_dotenv()

weather_bp = Blueprint('weather', __name__)

# 数据库配置
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '3306')
DB_USER = os.getenv('DB_USER', 'root')
DB_PASSWORD = os.getenv('DB_PASSWORD', '')
DB_NAME = os.getenv('DB_NAME', 'weather_steward')

# 创建数据库连接
db_url = f'mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}'
engine = create_engine(db_url)

# 创建表结构
metadata = MetaData()

# 行政区划表
area_info = Table(
    'area_info',
    metadata,
    Column('district_id', CHAR(6), primary_key=True, comment='行政区唯一代码'),
    Column('province', String(50), nullable=False, comment='省份名称'),
    Column('city', String(50), nullable=False, comment='城市名称'),
    Column('city_geocode', CHAR(6), nullable=False, comment='城市地理编码'),
    Column('district', String(50), nullable=False, comment='区县名称'),
    Column('district_geocode', CHAR(6), nullable=False, comment='区县地理编码'),
    Column('lon', DECIMAL(10, 6), nullable=False, comment='经度'),
    Column('lat', DECIMAL(10, 6), nullable=False, comment='纬度')
)

# 用户信息表
user_info = Table(
    'user_info',
    metadata,
    Column('open_id', String(28), primary_key=True, comment='微信用户唯一标识'),
    Column('nickname', String(50), comment='用户昵称'),
    Column('avatar_url', String(500), comment='用户头像URL'),
    Column('phone_number', String(20), comment='手机号码（加密存储）'),
    Column('country', CHAR(6), comment='所在国家'),
    Column('province', CHAR(6), comment='省份'),
    Column('city', CHAR(6), comment='城市'),
    Column('district', CHAR(6), comment='区县'),
    Column('latitude', DECIMAL(10, 6), comment='纬度'),
    Column('longitude', DECIMAL(10, 6), comment='经度'),
    Column('created_at', TIMESTAMP, server_default=func.now(), comment='创建时间'),
    Column('updated_at', TIMESTAMP, server_default=func.now(), onupdate=func.now(), comment='更新时间')
)

# 如果表不存在则创建
try:
    metadata.create_all(engine)
except Exception as e:
    print(f"Error creating table: {str(e)}")


@weather_bp.route('/login', methods=['GET'])
def login():
    code = request.args.get('code')
    if not code:
        return jsonify({'error': 'Missing code parameter'}), 400

    app_id = os.getenv('WECHAT_WEATHER_APPID')
    secret = os.getenv('WECHAT_WEATHER_SECRET')

    if not app_id or not secret:
        return jsonify({'error': 'Missing WeChat configuration'}), 500

    url = f'https://api.weixin.qq.com/sns/jscode2session'
    params = {
        'appid': app_id,
        'secret': secret,
        'js_code': code,
        'grant_type': 'authorization_code'
    }

    try:
        # 调用微信登录接口
        response = requests.get(url, params=params)
        data = response.json()

        if 'errcode' in data and data['errcode'] != 0:
            return jsonify({
                'error': 'WeChat login failed',
                'errcode': data['errcode'],
                'errmsg': data['errmsg']
            }), 400

        openid = data.get('openid')
        if not openid:
            return jsonify({'error': 'Failed to get openid'}), 500

        # 查询用户信息
        with engine.connect() as conn:
            # 先查询用户是否存在
            query = text('SELECT country, province, city, district FROM user_info WHERE open_id = :openid')
            result = conn.execute(query, {'openid': openid}).fetchone()

            if not result:
                # 用户不存在，创建新用户
                insert_query = text('INSERT INTO user_info (open_id) VALUES (:openid)')
                conn.execute(insert_query, {'openid': openid})
                conn.commit()

                location = {
                    'country': None,
                    'province': None,
                    'city': None,
                    'district': None
                }
            else:
                location = {
                    'country': result[0],
                    'province': result[1],
                    'city': result[2],
                    'district': result[3]
                }

        return jsonify({
            'openid': openid,
            'country': location.get('country'),
            'province': location.get('province'),
            'city': location.get('city'),
            'district': location.get('district')
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@weather_bp.route('/location', methods=['GET'])
def set_location_by_coordinates():
    openid = request.args.get('openid')
    lat = request.args.get('lat')
    lng = request.args.get('lng')
    if not lat or not lng:
        return jsonify({'error': 'Missing lat or lng parameter'}), 400

    ak = os.getenv('BAIDU_MAP_AK')
    if not ak:
        return jsonify({'error': 'Missing Baidu Map AK configuration'}), 500

    url = f'https://api.map.baidu.com/reverse_geocoding/v3/'
    params = {
        'ak': ak,
        'output': 'json',
        'coordtype': 'gcj02ll',
        'location': f'{lat},{lng}',
        'language': 'zh-CN'
    }

    try:
        response = requests.get(url, params=params)
        data = response.json()

        # 检查百度地图API返回状态
        if data.get('status') != 0:
            return jsonify({
                'error': 'Baidu Map API error',
                'status': data.get('status'),
                'message': data.get('message', 'Unknown error')
            }), 500

        # 提取所需的地理信息
        address_component = data.get('result', {}).get('addressComponent', {})
        # 检查国家代码是否为0（是否是中国）
        country_code = address_component.get('country_code')
        if country_code != 0:
            return jsonify({'error': 'This country is not supported at this time'}), 500
        #  获取行政区划代码
        adcode = address_component.get('adcode')
        if not adcode:
            return jsonify({'error': 'Failed to get adcode'}), 500

        with engine.connect() as conn:
            # 根据行政区划代码查询所在省市县信息
            query = text('select * from area_info where district_geocode = :adcode')
            result = conn.execute(query, {'adcode': adcode}).fetchone()
            if not result:
                return jsonify({'error': 'Failed to get city info'}), 500
            # 修改用户的地理位置信息
            query = text('update user_info set country = 0, province = :province, city = :city, district = :district '
                         'where open_id = :openid')
            params = {
                'province': result[3],
                'city': result[3],
                'district': result[5],
                'openid': openid
            }
            conn.execute(query, params)
            conn.commit()
            return jsonify({
                'country': 0,
                'province': result[3],
                'city': result[3],
                'district': result[5],
            }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@weather_bp.route('/location', methods=['POST'])
def update_location():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Missing request body'}), 400

    openid = data.get('openid')
    country = data.get('country')
    province = data.get('province')
    city = data.get('city')
    district = data.get('district')

    if not openid:
        return jsonify({'error': 'Missing open_id parameter'}), 400

    try:
        with engine.connect() as conn:
            # 构建更新语句
            update_fields = []
            params = {'open_id': openid}

            if country is not None:
                update_fields.append('country = :country')
                params['country'] = country
            if province is not None:
                update_fields.append('province = :province')
                params['province'] = province
            if city is not None:
                update_fields.append('city = :city')
                params['city'] = city
            if district is not None:
                update_fields.append('district = :district')
                params['district'] = district

            if not update_fields:
                return jsonify({'error': 'No fields to update'}), 400

            # 执行更新
            query = text(f"UPDATE user_info SET {', '.join(update_fields)} WHERE open_id = :open_id")

            result = conn.execute(query, params)
            conn.commit()

            if result.rowcount == 0:
                return jsonify({'error': 'User not found'}), 404

            return jsonify({
                'message': 'Location updated successfully',
                'open_id': openid,
                'updated_fields': {
                    'country': country,
                    'province': province,
                    'city': city,
                    'district': district
                }
            })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@weather_bp.route('/weather', methods=['GET'])
def get_weather():
    district = request.args.get('district')
    if not district:
        return jsonify({'error': 'Missing city or district parameter'}), 400

    ak = os.getenv('BAIDU_MAP_AK')
    if not ak:
        return jsonify({'error': 'Missing Baidu Map AK configuration'}), 500

    url = f'https://api.map.baidu.com/weather/v1/'
    params = {
        'ak': ak,
        'district_id': district,
        'data_type': 'all'
    }

    try:
        response = requests.get(url, params=params)
        data = response.json()

        # 检查百度地图API返回状态
        if data.get('status') != 0:
            return jsonify({
                'error': 'Baidu Map API error',
                'status': data.get('status'),
                'message': data.get('message', 'Unknown error')
            }), 500

        # 提取所需的天气信息
        forecasts = data.get('result', {}).get('forecasts', {})
        return jsonify(forecasts)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@weather_bp.route('/area/provinces', methods=['GET'])
def get_provinces():
    try:
        with engine.connect() as conn:
            query = text('SELECT MIN(district_id) as code, province as name FROM area_info GROUP BY province')
            result = conn.execute(query).fetchall()
            provinces = [{"code": row[0], "name": row[1]} for row in result]
            return jsonify(provinces)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@weather_bp.route('/area/cities', methods=['GET'])
def get_cities():
    province = request.args.get('province')
    if not province:
        return jsonify({'error': 'Missing province parameter'}), 400

    try:
        with engine.connect() as conn:
            query = text('SELECT district_id as code, city as name FROM area_info '
                         'WHERE province = :province GROUP BY city')
            result = conn.execute(query, {"province": province}).fetchall()
            cities = [{"code": row[0], "name": row[1]} for row in result]
            return jsonify(cities)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@weather_bp.route('/area/districts', methods=['GET'])
def get_districts():
    city_geocode = request.args.get('city_geocode')
    if not city_geocode:
        return jsonify({'error': 'Missing city_geocode parameter'}), 400

    try:
        with engine.connect() as conn:
            query = text('SELECT district_id as code, district as name FROM area_info '
                         'WHERE city_geocode = :city_geocode')
            result = conn.execute(query, {"city_geocode": city_geocode}).fetchall()
            districts = [{"code": row[0], "name": row[1]} for row in result]
            return jsonify(districts)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@weather_bp.route('/area/location_name', methods=['GET'])
def get_location_name():
    city = request.args.get('city')
    district = request.args.get('district')
    try:
        with engine.connect() as conn:
            query = text('select province, city, district from area_info '
                         'where city_geocode = :city and district_geocode = :district')
            result = conn.execute(query, {'city': city, 'district': district}).fetchone()
            if result is None:
                return jsonify({'error': 'no such location'}), 404
            return jsonify({'province': result[0], 'city': result[1], 'district': result[2]})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
