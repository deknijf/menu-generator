"""De maaltijdenlijst-API laat de bereiding weg, tenzij erom gevraagd wordt.

De bereiding was ruim de helft van de zwaarste call bij het opstarten, en de
lijst gebruikt ze nergens. De test draait tegen een tijdelijke database, zoals
test_auth.py, zodat data/app.db ongemoeid blijft.
"""

import pytest

from app import create_app, db

EMAIL = "lijst@example.com"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    app = create_app()
    app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)
    db.upsert_auth_user(email=EMAIL, name="Lijst", password="x", is_admin=False)
    db.create_custom_meal(
        EMAIL,
        {
            "name": "Stoofvlees met frieten",
            "ingredients": [{"name": "rundvlees", "quantity": 500, "unit": "g"}],
            "preparation": ["Stoof het vlees twee uur.", "Bak de frieten."],
        },
    )
    with app.test_client() as test_client:
        with test_client.session_transaction() as sess:
            sess["user"] = {"email": EMAIL, "name": "Lijst"}
        yield test_client


def test_lijst_laat_bereiding_weg(client):
    items = client.get("/api/custom-meals").get_json()["items"]
    assert len(items) == 1
    assert "preparation" not in items[0]
    # Ingredienten blijven: daar zoekt de frontend op, en de boodschappenlijst
    # gebruikt ze voor de zoekfunctie.
    assert items[0]["ingredients"][0]["name"] == "rundvlees"


def test_lijst_geeft_bereiding_op_verzoek(client):
    items = client.get("/api/custom-meals?include_preparation=1").get_json()["items"]
    assert items[0]["preparation"] == ["Stoof het vlees twee uur.", "Bak de frieten."]


def test_lijst_zonder_sessie_geeft_401(client):
    with client.session_transaction() as sess:
        sess.clear()
    assert client.get("/api/custom-meals").status_code == 401
