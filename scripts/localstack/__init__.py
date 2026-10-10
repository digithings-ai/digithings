"""Local self-host stack bring-up and health gate (S7, DIG-2775).

Plan: the ``plan`` document on DIG-2758, sections 3 and 6.

This package owns exactly one thing: driving the local stack and proving it is
healthy. It deliberately owns no contract format, no proxy config, no compose
file and no seed data -- those belong to the S1/S3/S4/S5/S6 slices.

Modules
-------
``contracts``  the service catalogue, built-in defaults plus optional
               feature-detection of ``config/contract/``.
``preflight``  host capability checks (tools, disk).
``health``     the health gate itself: probes, verdicts, exit status.
``render``     JSON and table rendering shared by every entry point.
``orchestrate``the ``dt up`` / ``down`` / ``status`` / ``seed`` / ``reset``
               command plans.
"""

__all__ = [
    "contracts",
    "health",
    "orchestrate",
    "preflight",
    "render",
]
