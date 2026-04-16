# 阶梯满减优惠券管理系统

![CI](https://github.com/Hayden-Chang/coupon_system/actions/workflows/ci.yml/badge.svg)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)

一个基于 `Flask + SQLite + Matplotlib` 的小型工具，用来管理电商商品的定价配置与阶梯满减优惠券，并通过图表分析利润、利润率、实际支付金额和优惠金额变化。

## 项目简介

这个项目面向网店/电商定价场景，核心目标是：

- 通过统一公式给商品定价：`标价 = 成本 × x + y`
- 为不同价格区间设计阶梯满减券：`满 P 减 Q`
- 自动校验整段成本区间内的利润是否始终大于 0
- 生成图表帮助观察优惠策略对利润和成交价的影响

项目提供单页 Web 界面和一组 REST API，数据保存在本地 `SQLite` 数据库中。

## 功能特性

- 配置管理：新增、查看、修改、删除定价配置
- 优惠券管理：为每套配置维护多档满减券
- 自动校验：阻止保存会导致亏损或零利润的配置
- 图表分析：生成 2×2 分析图表
- 本地持久化：使用 `SQLite` 自动建表、自动存储
- 单页前端：直接在浏览器操作，无需额外前端工程
- GitHub Actions：已配置基础 CI 冒烟检查

## 技术栈

- 后端：`Python`、`Flask`
- 数据库：`SQLite`
- 图表：`Matplotlib`、`NumPy`、`SciPy`
- 前端：`HTML`、`CSS`、原生 `JavaScript`

## 项目结构

```text
coupon_system/
├── app.py                   # Flask 主程序与 API 路由
├── database.py              # SQLite 数据库封装
├── chart.py                 # 图表生成与指标计算
├── requirements.txt         # Python 依赖
├── design_doc.md            # 需求说明文档
├── LICENSE                  # MIT 开源许可证
├── tests/
│   └── test_api.py          # API 接口测试
├── templates/
│   └── index.html           # 前端单页
└── .github/workflows/
    └── ci.yml               # GitHub Actions CI
```

## 安装与启动

### 1. 克隆项目

```bash
git clone https://github.com/Hayden-Chang/coupon_system.git
cd coupon_system
```

### 2. 创建虚拟环境

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows PowerShell 可使用：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 启动项目

```bash
python app.py
```

启动后访问：

- `http://127.0.0.1:5000`
- 或 `http://localhost:5000`

## 核心业务规则

系统会在保存配置或优惠券时执行校验，主要包括：

- 配置名称不能为空，且不能重复
- `x` 必须大于 `1`
- `y` 不能小于 `0`
- 成本区间 `m ~ n` 必须合法，且跨度不能过大
- 同一配置下优惠券档位 `tier` 不能重复
- 更高档位的 `p` 和 `q` 必须严格递增
- 任意成本点命中优惠后，利润必须始终大于 `0`

利润计算逻辑如下：

```text
标价 = 成本 × x + y
实际支付 = 标价 - 优惠金额
利润 = 实际支付 - 成本 - 运费
利润率 = 利润 / 实际支付 × 100%
```

当前代码中固定运费为 `4` 元。

## 图表说明

图表接口会生成一张 2×2 的综合图片，包含：

- 利润曲线
- 利润率曲线
- 用户实际支付曲线
- 优惠金额曲线

图表还会：

- 按命中的优惠券档位标出不同背景色块
- 标注每段区间内的极值点
- 返回摘要数据，如最低利润、最高利润、折扣区间等

## API 概览

### 配置接口

- `GET /api/configs`：获取配置列表
- `POST /api/configs`：创建配置
- `GET /api/configs/<id>`：获取配置详情
- `PUT /api/configs/<id>`：更新配置
- `DELETE /api/configs/<id>`：删除配置

### 优惠券接口

- `POST /api/configs/<id>/coupons`：新增单条优惠券
- `PUT /api/coupons/<id>`：更新单条优惠券
- `DELETE /api/coupons/<id>`：删除单条优惠券

### 图表接口

- `GET /api/configs/<id>/chart`：生成图表并返回 Base64 图片

## 示例：创建一套配置

```bash
curl -X POST http://127.0.0.1:5000/api/configs \
  -H "Content-Type: application/json" \
  -d '{
    "name": "春季主推款",
    "x": 2,
    "y": 34,
    "m": 15,
    "n": 100,
    "coupons": [
      {"tier": 1, "p": 50, "q": 5},
      {"tier": 2, "p": 80, "q": 10},
      {"tier": 3, "p": 120, "q": 15}
    ]
  }'
```

## CI 与测试

仓库已配置 GitHub Actions 工作流：`.github/workflows/ci.yml`

当前 CI 会执行：

- 安装依赖
- 编译检查 Python 文件
- 运行 `tests/test_api.py` 中的接口测试

本地也可以手动执行测试：

```bash
python -m unittest discover -s tests -p 'test_*.py'
```

触发时机：

- 推送到 `main`
- 发起 Pull Request

## 相关文件

- 需求文档：`design_doc.md`
- 后端入口：`app.py`
- 图表逻辑：`chart.py`
- 数据库封装：`database.py`
- 前端页面：`templates/index.html`

## 后续可扩展方向

- 增加更细粒度的异常与边界测试
- 支持导出配置和图表
- 支持多种运费策略
- 增加 Docker 部署文件
- 增加 API 文档页或 Swagger

## License

本项目采用 `MIT` 许可证，详见 `LICENSE`。
