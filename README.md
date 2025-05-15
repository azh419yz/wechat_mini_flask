# Mini Flask Backend

这是一个基于 Flask 的 Web 后端服务，为微信小程序和公众号提供 API 接口。

## 项目结构

```
.
├── app.py              # 主应用文件
├── requirements.txt    # 项目依赖
├── .env               # 环境变量配置（需要自行创建）
└── modules/           # 模块目录
    ├── weather_steward/  # 天气管家模块
    └── hello/           # Hello 模块
```

## 安装和运行

1. 安装依赖：
```bash
pip install -r requirements.txt
```

2. 配置环境变量：
- 复制 `.env.example` 为 `.env`
- 在 `.env` 文件中填入微信小程序的 AppID 和 Secret

3. 运行应用：
```bash
python app.py
```

## API 接口

### 微信小程序登录
- 路径：`/api/weather/login`
- 方法：GET
- 参数：
  - code: 小程序登录时获取的 code
- 返回：微信登录接口返回的数据 