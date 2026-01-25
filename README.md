# PA by wuu

![Visitors](https://api.visitorbadge.io/api/visitors?path=Easonoi%2FOI-Tag-Search&label=visitors&countColor=%23263759)
![JavaScript](https://img.shields.io/badge/JavaScript-F7DF1E?logo=javascript&logoColor=black)
![MIT License](https://img.shields.io/badge/License-MIT-green.svg)

基于标签的OI题目查询系统.

## 功能
- 支持标签+关键词搜索，提供 `all/any` 匹配模式
- 基于 JSON 的数据存储（`data/problems.json`）
- 数据源可改
- 各平台通用
- 通过 `config.json` 或环境变量配置

## 快速开始
1. 安装依赖：
```bash
pip install -r requirements.txt
```

2. 启动服务器：
```bash
python app.py
```

3. 访问：
- http://127.0.0.1:5907/
- （或配置的 `app.base_path`）
