import json
import math
from typing import Dict, List

from ._context import ToolContext
from ._helpers import require_ca_service
from ._registry import tool
from ._returns import align_series, build_return_series


def _pearson(x: List[float], y: List[float]) -> float:
    n = min(len(x), len(y))
    if n < 2:
        return 0.0

    mx = sum(x) / n
    my = sum(y) / n

    cov = sum((a - mx) * (b - my) for a, b in zip(x, y))
    vx = sum((a - mx) ** 2 for a in x)
    vy = sum((b - my) ** 2 for b in y)

    if vx <= 0 or vy <= 0:
        return 0.0
    return cov / math.sqrt(vx * vy)


@tool(
    name="get_correlation_matrix",
    description=(
        "Compute rolling return correlations across a basket of symbols. "
        "Uses corporate-action-adjusted histories and log returns, then "
        "aligns by common trading dates before calculating Pearson "
        "correlation coefficients."
    ),
    parameters={
        "type": "object",
        "properties": {
            "symbols": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of symbols (2-10)",
            },
            "window_days": {
                "type": "integer",
                "description": "Rolling window size in trading days (default 90)",
            },
        },
        "required": ["symbols"],
    },
)
def handle(ctx: ToolContext, args: dict) -> str:
    err = require_ca_service(ctx)
    if err:
        return err

    symbols = [str(s).strip().upper() for s in args.get("symbols", []) if str(s).strip()]
    if len(symbols) < 2:
        return "Error: Need at least 2 symbols"
    if len(symbols) > 10:
        symbols = symbols[:10]

    window_days = int(args.get("window_days", 90))
    if window_days < 10:
        return "Error: window_days must be >= 10"

    # Preserve first appearance order while deduplicating.
    deduped = list(dict.fromkeys(symbols))

    series = {
        symbol: build_return_series(ctx.corporate_actions, ctx.provider, symbol, window_days)
        for symbol in deduped
    }

    matrix: Dict[str, Dict[str, float]] = {}
    points: Dict[str, Dict[str, int]] = {}
    warnings: List[str] = []

    for i, left in enumerate(deduped):
        matrix[left] = {}
        points[left] = {}
        for j, right in enumerate(deduped):
            if i == j:
                matrix[left][right] = 1.0
                points[left][right] = len(series[left].returns)
                continue

            aligned = align_series([series[left], series[right]])
            x = aligned.get(left, [])
            y = aligned.get(right, [])

            n = min(len(x), len(y))
            points[left][right] = n
            if n < 2:
                matrix[left][right] = 0.0
                warnings.append(f"insufficient_overlap: {left}-{right}")
            else:
                matrix[left][right] = round(_pearson(x, y), 4)

    return json.dumps(
        {
            "symbols": deduped,
            "window_days": window_days,
            "method": "pearson_log_returns_adjusted",
            "correlation_matrix": matrix,
            "points_matrix": points,
            "warnings": sorted(set(warnings)),
        },
        indent=2,
    )
