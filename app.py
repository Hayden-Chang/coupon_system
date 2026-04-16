import sqlite3
from copy import deepcopy

from flask import Flask, jsonify, render_template, request

from chart import compute_metrics, generate_chart_base64
from database import Database

app = Flask(__name__)
db = Database()

MAX_COST_SPAN = 1000


def success(data=None, status=200):
    return jsonify({"success": True, "data": data}), status


def error(code, message, status=400, details=None):
    payload = {
        "success": False,
        "error": {"code": code, "message": message},
    }
    if details is not None:
        payload["error"]["details"] = details
    return jsonify(payload), status


def get_json_payload():
    payload = request.get_json(silent=True)
    if payload is None:
        raise ValueError("请求体必须是合法的 JSON。")
    return payload


def _coerce_number(value, field_name, as_int=False):
    if value is None or value == "":
        raise ValueError(f"{field_name} 不能为空。")
    try:
        if as_int:
            if isinstance(value, bool):
                raise ValueError
            return int(value)
        return float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} 格式不正确。")


def normalize_coupon(coupon, index):
    if not isinstance(coupon, dict):
        raise ValueError(f"第 {index + 1} 条优惠券格式不正确。")
    normalized = {
        "tier": _coerce_number(coupon.get("tier"), f"第 {index + 1} 条优惠券档位", as_int=True),
        "p": _coerce_number(coupon.get("p"), f"第 {index + 1} 条优惠券满额"),
        "q": _coerce_number(coupon.get("q"), f"第 {index + 1} 条优惠券减额"),
    }
    if "id" in coupon and coupon["id"] is not None:
        normalized["id"] = _coerce_number(coupon.get("id"), "优惠券 ID", as_int=True)
    return normalized


def normalize_config_payload(payload, existing_coupons=None):
    if not isinstance(payload, dict):
        raise ValueError("请求体必须是对象。")
    name = str(payload.get("name", "")).strip()
    config = {
        "name": name,
        "x": _coerce_number(payload.get("x"), "成本倍数 x"),
        "y": _coerce_number(payload.get("y"), "固定加价 y"),
        "m": _coerce_number(payload.get("m"), "成本下限 m", as_int=True),
        "n": _coerce_number(payload.get("n"), "成本上限 n", as_int=True),
    }

    raw_coupons = payload.get("coupons")
    if raw_coupons is None:
        raw_coupons = existing_coupons or []
    if not isinstance(raw_coupons, list):
        raise ValueError("coupons 必须是数组。")
    coupons = [normalize_coupon(coupon, index) for index, coupon in enumerate(raw_coupons)]
    return config, coupons


def validate_config(config, coupons):
    details = {}

    if not config["name"]:
        details["name"] = "配置名称不能为空。"
    elif len(config["name"]) > 50:
        details["name"] = "配置名称不能超过 50 个字符。"

    if config["x"] <= 1:
        details["x"] = "成本倍数 x 必须大于 1。"
    if config["y"] < 0:
        details["y"] = "固定加价 y 不能小于 0。"
    if config["m"] < 1:
        details["m"] = "成本下限 m 必须大于等于 1。"
    if config["n"] < config["m"]:
        details["n"] = "成本上限 n 不能小于成本下限 m。"
    if config["n"] - config["m"] > MAX_COST_SPAN:
        details["n"] = f"成本区间跨度不能超过 {MAX_COST_SPAN}。"

    tiers = set()
    prev_coupon = None
    ordered = sorted(coupons, key=lambda item: item["tier"])
    for coupon in ordered:
        if coupon["tier"] < 1:
            details[f"coupon_{coupon['tier']}_tier"] = f"第 {coupon['tier']} 档的档位必须大于等于 1。"
        if coupon["p"] <= 0:
            details[f"coupon_{coupon['tier']}_p"] = f"第 {coupon['tier']} 档的满额门槛必须大于 0。"
        if coupon["q"] <= 0:
            details[f"coupon_{coupon['tier']}_q"] = f"第 {coupon['tier']} 档的减额必须大于 0。"
        if coupon["tier"] in tiers:
            details[f"coupon_{coupon['tier']}_tier"] = f"第 {coupon['tier']} 档重复了，同一配置内档位不能重复。"
        tiers.add(coupon["tier"])

        if prev_coupon is not None:
            if coupon["p"] <= prev_coupon["p"]:
                details[f"coupon_{coupon['tier']}_p"] = (
                    f"第 {coupon['tier']} 档满额 {coupon['p']:.2f} 必须大于"
                    f"上一档的 {prev_coupon['p']:.2f}。"
                )
            if coupon["q"] <= prev_coupon["q"]:
                details[f"coupon_{coupon['tier']}_q"] = (
                    f"第 {coupon['tier']} 档减额 {coupon['q']:.2f} 必须大于"
                    f"上一档的 {prev_coupon['q']:.2f}。"
                )
        prev_coupon = coupon

    if details:
        return details

    scan_payload = deepcopy(config)
    scan_payload["coupons"] = ordered
    metrics = compute_metrics(scan_payload)
    invalid_indexes = [idx for idx, profit in enumerate(metrics["profits"]) if profit <= 0]
    if invalid_indexes:
        first_index = invalid_indexes[0]
        cost = int(metrics["costs"][first_index])
        list_price = float(metrics["list_prices"][first_index])
        discount = float(metrics["discounts"][first_index])
        actual_payment = float(metrics["actual_payments"][first_index])
        profit = float(metrics["profits"][first_index])
        profit_rate = float(metrics["profit_rates"][first_index])
        active_coupon = "未命中优惠券"
        for coupon in ordered:
            if list_price >= coupon["p"]:
                active_coupon = f"第 {coupon['tier']} 档 满{coupon['p']:.0f}减{coupon['q']:.0f}"
            else:
                break
        details["profit"] = (
            f"成本 {cost} 元时命中“{active_coupon}”，标价 {list_price:.2f} 元，"
            f"优惠 {discount:.2f} 元，实付 {actual_payment:.2f} 元，"
            f"利润 {profit:.2f} 元，利润率 {profit_rate:.2f}%。当前设置会亏损或零利润。"
        )

    return details


def summarize_validation_details(details, fallback_message):
    if not details:
        return fallback_message
    ordered_messages = []
    seen = set()
    for message in details.values():
        if message not in seen:
            ordered_messages.append(message)
            seen.add(message)
    if len(ordered_messages) == 1:
        return ordered_messages[0]
    return "；".join(ordered_messages)


def fetch_config_or_404(config_id):
    config = db.get_config(config_id)
    if not config:
        return None, error("CONFIG_NOT_FOUND", "配置不存在。", 404)
    return config, None


def fetch_coupon_or_404(coupon_id):
    coupon = db.get_coupon(coupon_id)
    if not coupon:
        return None, error("COUPON_NOT_FOUND", "优惠券不存在。", 404)
    return coupon, None


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/configs", methods=["GET"])
def list_configs():
    return success(db.list_configs())


@app.route("/api/configs", methods=["POST"])
def create_config():
    try:
        payload = get_json_payload()
        config, coupons = normalize_config_payload(payload)
        details = validate_config(config, coupons)
        if details:
            code = "PROFIT_CONSTRAINT_VIOLATION" if "profit" in details else "VALIDATION_ERROR"
            status = 422 if code == "PROFIT_CONSTRAINT_VIOLATION" else 400
            return error(code, summarize_validation_details(details, "配置校验失败。"), status, details)
        config_id = db.create_config(config, sorted(coupons, key=lambda item: item["tier"]))
        return success({"id": config_id}, 201)
    except ValueError as exc:
        return error("VALIDATION_ERROR", str(exc), 400)
    except sqlite3.IntegrityError as exc:
        if "configs.name" in str(exc):
            return error("CONFIG_NAME_CONFLICT", "配置名称已存在。", 409)
        return error("DATABASE_CONFLICT", "数据写入冲突。", 409)
    except Exception:
        return error("INTERNAL_ERROR", "创建配置失败。", 500)


@app.route("/api/configs/<int:config_id>", methods=["GET"])
def get_config(config_id):
    config, err = fetch_config_or_404(config_id)
    if err:
        return err
    return success(config)


@app.route("/api/configs/<int:config_id>", methods=["PUT"])
def update_config(config_id):
    current, err = fetch_config_or_404(config_id)
    if err:
        return err
    try:
        payload = get_json_payload()
        existing_coupons = current.get("coupons", [])
        config, coupons = normalize_config_payload(payload, existing_coupons=existing_coupons)
        details = validate_config(config, coupons)
        if details:
            code = "PROFIT_CONSTRAINT_VIOLATION" if "profit" in details else "VALIDATION_ERROR"
            status = 422 if code == "PROFIT_CONSTRAINT_VIOLATION" else 400
            return error(code, summarize_validation_details(details, "配置校验失败。"), status, details)
        updated = db.update_config(config_id, config, sorted(coupons, key=lambda item: item["tier"]))
        if not updated:
            return error("CONFIG_NOT_FOUND", "配置不存在。", 404)
        return success({"id": config_id})
    except ValueError as exc:
        return error("VALIDATION_ERROR", str(exc), 400)
    except sqlite3.IntegrityError as exc:
        if "configs.name" in str(exc):
            return error("CONFIG_NAME_CONFLICT", "配置名称已存在。", 409)
        return error("DATABASE_CONFLICT", "数据写入冲突。", 409)
    except Exception:
        return error("INTERNAL_ERROR", "更新配置失败。", 500)


@app.route("/api/configs/<int:config_id>", methods=["DELETE"])
def delete_config(config_id):
    deleted = db.delete_config(config_id)
    if not deleted:
        return error("CONFIG_NOT_FOUND", "配置不存在。", 404)
    return success({"id": config_id})


@app.route("/api/configs/<int:config_id>/coupons", methods=["POST"])
def add_coupon(config_id):
    current, err = fetch_config_or_404(config_id)
    if err:
        return err
    try:
        payload = get_json_payload()
        coupon = normalize_coupon(payload, 0)
        coupons = current.get("coupons", []) + [coupon]
        config_payload = {key: current[key] for key in ["name", "x", "y", "m", "n"]}
        details = validate_config(config_payload, coupons)
        if details:
            code = "PROFIT_CONSTRAINT_VIOLATION" if "profit" in details else "VALIDATION_ERROR"
            status = 422 if code == "PROFIT_CONSTRAINT_VIOLATION" else 400
            return error(code, summarize_validation_details(details, "优惠券校验失败。"), status, details)
        coupon_id = db.add_coupon(config_id, coupon)
        return success({"id": coupon_id}, 201)
    except ValueError as exc:
        return error("VALIDATION_ERROR", str(exc), 400)
    except sqlite3.IntegrityError:
        return error("COUPON_TIER_CONFLICT", "优惠券档位重复。", 409)
    except Exception:
        return error("INTERNAL_ERROR", "新增优惠券失败。", 500)


@app.route("/api/coupons/<int:coupon_id>", methods=["PUT"])
def update_coupon(coupon_id):
    current_coupon, err = fetch_coupon_or_404(coupon_id)
    if err:
        return err

    config, err = fetch_config_or_404(current_coupon["config_id"])
    if err:
        return err

    try:
        payload = get_json_payload()
        coupon = normalize_coupon(payload, 0)
        coupons = []
        for item in config.get("coupons", []):
            if item["id"] == coupon_id:
                updated_coupon = {
                    "id": coupon_id,
                    "tier": coupon["tier"],
                    "p": coupon["p"],
                    "q": coupon["q"],
                }
                coupons.append(updated_coupon)
            else:
                coupons.append(item)

        config_payload = {key: config[key] for key in ["name", "x", "y", "m", "n"]}
        details = validate_config(config_payload, coupons)
        if details:
            code = "PROFIT_CONSTRAINT_VIOLATION" if "profit" in details else "VALIDATION_ERROR"
            status = 422 if code == "PROFIT_CONSTRAINT_VIOLATION" else 400
            return error(code, summarize_validation_details(details, "优惠券校验失败。"), status, details)
        updated = db.update_coupon(coupon_id, coupon)
        if not updated:
            return error("COUPON_NOT_FOUND", "优惠券不存在。", 404)
        return success({"id": coupon_id})
    except ValueError as exc:
        return error("VALIDATION_ERROR", str(exc), 400)
    except sqlite3.IntegrityError:
        return error("COUPON_TIER_CONFLICT", "优惠券档位重复。", 409)
    except Exception:
        return error("INTERNAL_ERROR", "更新优惠券失败。", 500)


@app.route("/api/coupons/<int:coupon_id>", methods=["DELETE"])
def delete_coupon(coupon_id):
    coupon, err = fetch_coupon_or_404(coupon_id)
    if err:
        return err
    deleted = db.delete_coupon(coupon_id)
    if not deleted:
        return error("COUPON_NOT_FOUND", "优惠券不存在。", 404)
    return success({"id": coupon["id"], "config_id": coupon["config_id"]})


@app.route("/api/configs/<int:config_id>/chart", methods=["GET"])
def get_chart(config_id):
    config, err = fetch_config_or_404(config_id)
    if err:
        return err
    try:
        image_base64, summary = generate_chart_base64(config)
        return success({"image_base64": image_base64, "summary": summary})
    except Exception:
        return error("INTERNAL_ERROR", "生成图表失败。", 500)


if __name__ == "__main__":
    app.run(debug=True)
