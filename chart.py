import base64
import io
from collections import OrderedDict

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch

try:
    from scipy.interpolate import CubicSpline
except Exception:  # pragma: no cover
    CubicSpline = None


plt.rcParams["font.sans-serif"] = [
    "Microsoft YaHei",
    "PingFang SC",
    "SimHei",
    "Noto Sans CJK SC",
    "Arial Unicode MS",
    "DejaVu Sans",
]
plt.rcParams["axes.unicode_minus"] = False

SHIPPING_COST = 4
SEGMENT_COLORS = [
    "#DDECF8",
    "#E5F7E2",
    "#FFF1CC",
    "#FFE0D7",
    "#E5D8FF",
    "#D9F3EF",
]


def compute_metrics(config):
    coupons = sorted(config.get("coupons", []), key=lambda item: item["tier"])
    costs = np.arange(int(config["m"]), int(config["n"]) + 1, dtype=float)
    list_prices = costs * float(config["x"]) + float(config["y"])

    discounts = []
    segment_keys = []
    segment_labels = {}
    for list_price in list_prices:
        active_coupon = None
        for coupon in coupons:
            if list_price >= float(coupon["p"]):
                active_coupon = coupon
            else:
                break
        if active_coupon:
            discount = float(active_coupon["q"])
            segment_key = f"tier-{active_coupon['tier']}"
            segment_label = f"第{active_coupon['tier']}档 满{active_coupon['p']:.0f}减{active_coupon['q']:.0f}"
        else:
            discount = 0.0
            segment_key = "tier-0"
            segment_label = "未命中优惠券"
        discounts.append(discount)
        segment_keys.append(segment_key)
        segment_labels[segment_key] = segment_label

    discounts = np.array(discounts, dtype=float)
    actual_payments = list_prices - discounts
    profits = actual_payments - costs - SHIPPING_COST
    profit_rates = np.where(actual_payments > 0, profits / actual_payments * 100, 0)

    segments = []
    start = 0
    for index in range(1, len(costs) + 1):
        if index == len(costs) or segment_keys[index] != segment_keys[start]:
            key = segment_keys[start]
            segments.append(
                {
                    "key": key,
                    "label": segment_labels[key],
                    "start_cost": float(costs[start]),
                    "end_cost": float(costs[index - 1]),
                    "start_index": start,
                    "end_index": index - 1,
                }
            )
            start = index

    return {
        "costs": costs,
        "list_prices": list_prices,
        "discounts": discounts,
        "actual_payments": actual_payments,
        "profits": profits,
        "profit_rates": profit_rates,
        "segments": segments,
        "formula": f"标价 = 成本 × {config['x']} + {config['y']}",
        "shipping_cost": SHIPPING_COST,
    }


def _smooth_series(costs, series):
    if len(costs) < 4 or CubicSpline is None:
        return costs, series
    try:
        dense_costs = np.linspace(costs.min(), costs.max(), len(costs) * 12)
        spline = CubicSpline(costs, series, bc_type="natural")
        return dense_costs, spline(dense_costs)
    except Exception:
        return costs, series


def _annotate_segment(ax, xs, ys, segment, color):
    start = segment["start_index"]
    end = segment["end_index"] + 1
    seg_x = xs[start:end]
    seg_y = ys[start:end]
    if len(seg_x) == 0:
        return

    min_idx = int(np.argmin(seg_y))
    max_idx = int(np.argmax(seg_y))
    markers = OrderedDict(
        [
            ("min", (seg_x[min_idx], seg_y[min_idx])),
            ("max", (seg_x[max_idx], seg_y[max_idx])),
        ]
    )
    for _, (x_pos, y_pos) in markers.items():
        ax.scatter([x_pos], [y_pos], color=color, s=18, zorder=4)
        ax.annotate(
            f"{y_pos:.1f}",
            (x_pos, y_pos),
            textcoords="offset points",
            xytext=(0, 8),
            ha="center",
            fontsize=8,
            color="#334155",
        )


def generate_chart_base64(config):
    metrics = compute_metrics(config)
    costs = metrics["costs"]
    profits = metrics["profits"]
    profit_rates = metrics["profit_rates"]
    actual_payments = metrics["actual_payments"]
    discounts = metrics["discounts"]
    segments = metrics["segments"]

    dense_costs, dense_profits = _smooth_series(costs, profits)
    _, dense_profit_rates = _smooth_series(costs, profit_rates)
    _, dense_actual_payments = _smooth_series(costs, actual_payments)

    fig, axes = plt.subplots(2, 2, figsize=(16, 11), dpi=140)
    axes = axes.flatten()

    chart_specs = [
        ("利润曲线", dense_costs, dense_profits, costs, profits, "#0F766E", "利润（元）"),
        ("利润率曲线", dense_costs, dense_profit_rates, costs, profit_rates, "#2563EB", "利润率（%）"),
        ("用户实际支付曲线", dense_costs, dense_actual_payments, costs, actual_payments, "#EA580C", "实际支付（元）"),
        ("优惠金额曲线", costs, discounts, costs, discounts, "#9333EA", "优惠金额（元）"),
    ]

    legend_items = []
    color_map = {}

    for idx, segment in enumerate(segments):
        color_map[segment["key"]] = SEGMENT_COLORS[idx % len(SEGMENT_COLORS)]
        legend_items.append(Patch(facecolor=color_map[segment["key"]], edgecolor="none", label=segment["label"]))

    for ax, (title, line_x, line_y, raw_x, raw_y, color, ylabel) in zip(axes, chart_specs):
        for segment in segments:
            segment_color = color_map[segment["key"]]
            ax.axvspan(
                segment["start_cost"],
                segment["end_cost"] + 0.99,
                color=segment_color,
                alpha=0.42,
                zorder=0,
            )

        if "优惠金额" in title:
            ax.step(line_x, line_y, where="post", color=color, linewidth=2.6, zorder=3)
        else:
            ax.plot(line_x, line_y, color=color, linewidth=2.6, zorder=3)
            ax.scatter(raw_x, raw_y, color=color, s=9, alpha=0.45, zorder=4)

        for segment in segments:
            _annotate_segment(ax, raw_x, raw_y, segment, color)

        ax.set_title(title, fontsize=13, fontweight="bold", color="#0F172A")
        ax.set_xlabel("商品成本（元）", fontsize=10)
        ax.set_ylabel(ylabel, fontsize=10)
        ax.grid(True, linestyle="--", linewidth=0.7, alpha=0.28)
        ax.set_facecolor("#FFFFFF")

    min_profit = float(np.min(profits))
    max_profit = float(np.max(profits))
    discount_ratios = np.where(metrics["list_prices"] > 0, actual_payments / metrics["list_prices"], 1)

    fig.suptitle(
        (
            f"{config['name']} | {metrics['formula']} | 成本区间 {config['m']}~{config['n']} 元\n"
            f"最低利润 {min_profit:.2f} 元，最高利润 {max_profit:.2f} 元，折后区间 {discount_ratios.min() * 10:.2f}~{discount_ratios.max() * 10:.2f} 折"
        ),
        fontsize=16,
        fontweight="bold",
        color="#0F172A",
        y=0.985,
    )

    fig.legend(
        handles=legend_items,
        loc="lower center",
        ncol=2,
        fontsize=9,
        frameon=False,
        bbox_to_anchor=(0.5, 0.02),
    )
    fig.tight_layout(rect=(0.02, 0.07, 0.98, 0.92))

    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buffer.getvalue()).decode("utf-8"), {
        "formula": metrics["formula"],
        "cost_range": [int(config["m"]), int(config["n"])],
        "min_profit": min_profit,
        "max_profit": max_profit,
        "min_profit_rate": float(np.min(profit_rates)),
        "max_profit_rate": float(np.max(profit_rates)),
        "min_discount_ratio": float(discount_ratios.min()),
        "max_discount_ratio": float(discount_ratios.max()),
    }
