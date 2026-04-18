"""DigiKey scope matching."""

from digikey.scopes import scope_grants_required


def test_star_grants_all():
    assert scope_grants_required(["*"], ["digigraph:chat", "digiquant:backtest"])


def test_exact_scope():
    assert scope_grants_required(["digigraph:chat"], ["digigraph:chat"])
    assert not scope_grants_required(["digigraph:chat"], ["digiquant:backtest"])


def test_prefix_wildcard():
    assert scope_grants_required(["digigraph:*"], ["digigraph:chat", "digigraph:workflow"])
    assert not scope_grants_required(["digigraph:*"], ["digiquant:backtest"])


def test_run_pipeline_dual():
    req = ["digiquant:backtest", "digiquant:optimize"]
    assert scope_grants_required(["*"], req)
    assert scope_grants_required(["digiquant:backtest", "digiquant:optimize"], req)
    assert not scope_grants_required(["digiquant:backtest"], req)
