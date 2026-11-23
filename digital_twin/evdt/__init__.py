"""EV-DT: a power-electronics-centred national digital twin for electric-vehicle
policy assessment across underdeveloped, developing and developed economies.

The package is organised as a layered digital twin:

    environment  ->  physical asset models  ->  network model  ->  analytics
    (weather,        (power electronics,       (radial          (metrics,
     solar,           battery, vehicle,         distribution     economics,
     price)           charger)                  feeder)          emissions)

with a policy engine that maps discrete policy levers onto the parameters of
those models, and an orchestration engine that propagates the coupled system
over a multi-year horizon at hourly resolution.

All modules depend only on numpy / scipy / pandas / scikit-learn so that the
whole study can be reproduced from a clean Python installation.
"""

__version__ = "1.0.0"
__all__ = [
    "config", "powerelectronics", "battery", "mobility", "charging", "grid",
    "environment", "economics", "policy", "metrics", "engine", "uncertainty",
    "optimization", "learning", "scenarios",
]
