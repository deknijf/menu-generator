"""Tests voor de login-throttle.

Deze raken wél de database, maar via een tijdelijk bestand: db.DB_PATH wordt
omgezet naar een tmp_path zodat data/app.db ongemoeid blijft.
"""

import pytest

from app import db


@pytest.fixture
def tijdelijke_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db()
    return db


def test_schone_lei_telt_nul(tijdelijke_db):
    assert tijdelijke_db.count_recent_failed_logins("1.2.3.4") == 0


def test_mislukte_pogingen_worden_geteld(tijdelijke_db):
    for _ in range(3):
        tijdelijke_db.record_failed_login("1.2.3.4")
    assert tijdelijke_db.count_recent_failed_logins("1.2.3.4") == 3


def test_pogingen_worden_per_identifier_bijgehouden(tijdelijke_db):
    tijdelijke_db.record_failed_login("1.2.3.4")
    tijdelijke_db.record_failed_login("5.6.7.8")
    tijdelijke_db.record_failed_login("5.6.7.8")
    assert tijdelijke_db.count_recent_failed_logins("1.2.3.4") == 1
    assert tijdelijke_db.count_recent_failed_logins("5.6.7.8") == 2


def test_throttle_slaat_pas_aan_op_de_limiet(tijdelijke_db):
    identifier = "1.2.3.4"
    for _ in range(db.LOGIN_MAX_ATTEMPTS - 1):
        tijdelijke_db.record_failed_login(identifier)
    assert tijdelijke_db.login_is_throttled([identifier]) is False

    tijdelijke_db.record_failed_login(identifier)
    assert tijdelijke_db.login_is_throttled([identifier]) is True


def test_geslaagde_login_wist_de_teller(tijdelijke_db):
    identifier = "1.2.3.4"
    for _ in range(db.LOGIN_MAX_ATTEMPTS):
        tijdelijke_db.record_failed_login(identifier)
    assert tijdelijke_db.login_is_throttled([identifier]) is True

    tijdelijke_db.clear_failed_logins(identifier)
    assert tijdelijke_db.count_recent_failed_logins(identifier) == 0
    assert tijdelijke_db.login_is_throttled([identifier]) is False


def test_throttle_kijkt_naar_elke_identifier(tijdelijke_db):
    """IP en e-mail worden apart geteld; één van beide over de limiet volstaat."""
    for _ in range(db.LOGIN_MAX_ATTEMPTS):
        tijdelijke_db.record_failed_login("email:iemand@example.com")
    assert tijdelijke_db.login_is_throttled(["9.9.9.9", "email:iemand@example.com"]) is True


def test_lege_identifiers_worden_genegeerd(tijdelijke_db):
    tijdelijke_db.record_failed_login("")
    tijdelijke_db.record_failed_login(None)
    assert tijdelijke_db.count_recent_failed_logins("") == 0
    assert tijdelijke_db.login_is_throttled(["", None]) is False


def test_oude_pogingen_tellen_niet_mee(tijdelijke_db):
    """Pogingen buiten het venster van 15 minuten vervallen."""
    conn = tijdelijke_db.get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO login_attempts (identifier, attempted_at) VALUES (?, datetime('now', '-30 minutes'))",
        ("1.2.3.4",),
    )
    conn.commit()
    conn.close()

    assert tijdelijke_db.count_recent_failed_logins("1.2.3.4") == 0
