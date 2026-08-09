"""Tests voor _geplande_maaltijden_rond in app/routes.py.

"Opnieuw" mag geen gerecht kiezen dat elders in dezelfde planning staat. Welke
dagen bij die planning horen weten we niet uit de database: er is geen
plan-id, alleen losse dagen. We lopen daarom vanaf de dag naar buiten zolang er
dagen aansluiten, want dat is precies wat de datepicker heeft aangemaakt.
"""

import pytest

from app import routes


@pytest.fixture
def dagen(monkeypatch):
    """Vervangt get_days_between door een vaste dagplanning."""

    def _setup(rijen):
        def _tussen(group_id, start, eind):
            return [r for r in rijen if start <= r["day_date"] <= eind]

        monkeypatch.setattr(routes, "get_days_between", _tussen)

    return _setup


def _dag(datum, meal_id=None):
    return {"day_date": datum, "cook": 1 if meal_id else 0, "meal_id": meal_id}


def test_aaneengesloten_reeks_telt_volledig_mee(dagen):
    dagen([_dag(f"2026-08-{d:02d}", f"custom_{d}") for d in range(3, 10)])

    gevonden = routes._geplande_maaltijden_rond(1, "2026-08-06")

    assert sorted(gevonden) == sorted(f"custom_{d}" for d in range(3, 10) if d != 6)


def test_de_dag_zelf_telt_niet_mee(dagen):
    dagen([_dag("2026-08-03", "custom_1"), _dag("2026-08-04", "custom_2")])

    assert routes._geplande_maaltijden_rond(1, "2026-08-04") == ["custom_1"]


def test_een_gat_begrenst_de_planning(dagen):
    """Twee losse periodes zijn twee planningen; de andere telt niet mee."""
    dagen([
        _dag("2026-08-03", "custom_1"),
        _dag("2026-08-04", "custom_2"),
        # 5 augustus ontbreekt
        _dag("2026-08-06", "custom_3"),
        _dag("2026-08-07", "custom_4"),
    ])

    gevonden = routes._geplande_maaltijden_rond(1, "2026-08-07")

    assert sorted(gevonden) == ["custom_3"]


def test_rustdag_zonder_gerecht_breekt_de_reeks_niet(dagen):
    """Een dag waarop je niet kookt hoort nog steeds bij dezelfde planning."""
    dagen([
        _dag("2026-08-03", "custom_1"),
        _dag("2026-08-04"),  # niet koken
        _dag("2026-08-05", "custom_2"),
    ])

    assert sorted(routes._geplande_maaltijden_rond(1, "2026-08-05")) == ["custom_1"]


def test_dag_zonder_planning_geeft_lege_lijst(dagen):
    dagen([])
    assert routes._geplande_maaltijden_rond(1, "2026-08-05") == []


def test_losse_dag_zonder_buren(dagen):
    dagen([_dag("2026-08-05", "custom_1")])
    assert routes._geplande_maaltijden_rond(1, "2026-08-05") == []
