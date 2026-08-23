"""Metrics package with lazy imports so report tools avoid pygame."""

__all__ = [
    "LinkReadinessResult",
    "LinkReadinessScore",
    "LogSnapshot",
    "RunLogger",
]


def __getattr__(name: str):
    if name in ("LinkReadinessResult", "LinkReadinessScore"):
        from metrics.link_readiness import LinkReadinessResult, LinkReadinessScore

        return {
            "LinkReadinessResult": LinkReadinessResult,
            "LinkReadinessScore": LinkReadinessScore,
        }[name]
    if name in ("LogSnapshot", "RunLogger"):
        from metrics.logger import LogSnapshot, RunLogger

        return {"LogSnapshot": LogSnapshot, "RunLogger": RunLogger}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
