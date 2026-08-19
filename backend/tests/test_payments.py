import pytest

from app.services import telegram
from tests.conftest import auth_header, authenticate

pytestmark = pytest.mark.asyncio

INTERNAL = {"X-Internal-Token": "test-internal"}


@pytest.fixture(autouse=True)
def fake_telegram(monkeypatch):
    """Never touch the real Bot API from the test suite."""
    calls: list[tuple[str, dict]] = []

    async def fake_call(method: str, payload: dict | None = None, **kwargs):
        calls.append((method, payload or {}))
        if method == "createInvoiceLink":
            return "https://t.me/invoice/test-link"
        if method in {"refundStarPayment", "sendMessage"}:
            return True
        return {}

    monkeypatch.setattr(telegram, "call", fake_call)
    return calls


async def test_stars_top_up_credits_only_after_confirmation(client, fake_telegram):
    auth = await authenticate(client, 8001)
    headers = auth_header(auth["token"])

    invoice = await client.post("/api/payments/stars/create", json={"package": "gg_100"}, headers=headers)
    assert invoice.status_code == 200, invoice.text
    body = invoice.json()
    assert body["stars"] == 50 and body["gg"] == 100
    assert body["invoice_link"] == "https://t.me/invoice/test-link"

    # Creating the invoice must not have moved the balance.
    assert (await client.get("/api/balance", headers=headers)).json()["balance"] == 1000

    confirmed = await client.post(
        "/api/payments/stars/webhook",
        json={
            "telegram_id": 8001,
            "payload": body["payload"],
            "telegram_payment_charge_id": "charge_8001",
            "total_amount": 50,
            "currency": "XTR",
        },
        headers=INTERNAL,
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["credited"] is True
    assert (await client.get("/api/balance", headers=headers)).json()["balance"] == 1100

    history = (await client.get("/api/transactions?type=stars_topup", headers=headers)).json()
    assert history["total"] == 1
    assert history["items"][0]["amount"] == 100


async def test_replayed_payment_update_does_not_credit_twice(client, fake_telegram):
    auth = await authenticate(client, 8002)
    headers = auth_header(auth["token"])
    payload = (
        await client.post("/api/payments/stars/create", json={"package": "gg_550"}, headers=headers)
    ).json()["payload"]

    update = {
        "telegram_id": 8002,
        "payload": payload,
        "telegram_payment_charge_id": "charge_8002",
        "total_amount": 250,
        "currency": "XTR",
    }
    first = await client.post("/api/payments/stars/webhook", json=update, headers=INTERNAL)
    second = await client.post("/api/payments/stars/webhook", json=update, headers=INTERNAL)

    assert first.json()["credited"] is True
    assert second.json()["credited"] is False
    assert (await client.get("/api/balance", headers=headers)).json()["balance"] == 1550


async def test_webhook_requires_the_internal_token(client, fake_telegram):
    response = await client.post(
        "/api/payments/stars/webhook",
        json={
            "telegram_id": 8003,
            "payload": "gg:1:whatever",
            "telegram_payment_charge_id": "x",
            "total_amount": 50,
        },
    )
    assert response.status_code == 401


async def test_precheckout_rejects_a_tampered_amount(client, fake_telegram):
    auth = await authenticate(client, 8004)
    headers = auth_header(auth["token"])
    payload = (
        await client.post("/api/payments/stars/create", json={"package": "gg_100"}, headers=headers)
    ).json()["payload"]

    ok = await client.post(
        "/api/payments/stars/precheckout",
        json={"telegram_id": 8004, "payload": payload, "total_amount": 50, "currency": "XTR"},
        headers=INTERNAL,
    )
    assert ok.json()["ok"] is True

    tampered = await client.post(
        "/api/payments/stars/precheckout",
        json={"telegram_id": 8004, "payload": payload, "total_amount": 1, "currency": "XTR"},
        headers=INTERNAL,
    )
    assert tampered.json()["ok"] is False
    assert "mismatch" in tampered.json()["error_message"].lower()


async def test_payment_of_another_user_is_rejected(client, fake_telegram):
    auth = await authenticate(client, 8005)
    headers = auth_header(auth["token"])
    payload = (
        await client.post("/api/payments/stars/create", json={"package": "gg_100"}, headers=headers)
    ).json()["payload"]

    response = await client.post(
        "/api/payments/stars/webhook",
        json={
            "telegram_id": 9999,
            "payload": payload,
            "telegram_payment_charge_id": "charge_hijack",
            "total_amount": 50,
        },
        headers=INTERNAL,
    )
    assert response.status_code == 409


async def test_admin_refund_returns_stars_and_claws_back_gg(client, fake_telegram):
    auth = await authenticate(client, 8006)
    headers = auth_header(auth["token"])
    invoice = (
        await client.post("/api/payments/stars/create", json={"package": "gg_100"}, headers=headers)
    ).json()

    await client.post(
        "/api/payments/stars/webhook",
        json={
            "telegram_id": 8006,
            "payload": invoice["payload"],
            "telegram_payment_charge_id": "charge_8006",
            "total_amount": 50,
        },
        headers=INTERNAL,
    )
    assert (await client.get("/api/balance", headers=headers)).json()["balance"] == 1100

    admin = await authenticate(client, 1001, username="admin")
    refund = await client.post(
        "/api/payments/stars/refund",
        json={"payment_id": invoice["payment_id"], "reason": "user request"},
        headers=auth_header(admin["token"]),
    )
    assert refund.status_code == 200, refund.text
    assert refund.json()["status"] == "refunded"
    assert (
        "refundStarPayment",
        {"user_id": 8006, "telegram_payment_charge_id": "charge_8006"},
    ) in fake_telegram
    assert (await client.get("/api/balance", headers=headers)).json()["balance"] == 1000


async def test_refund_requires_admin(client, fake_telegram):
    auth = await authenticate(client, 8007)
    response = await client.post(
        "/api/payments/stars/refund", json={"payment_id": 1}, headers=auth_header(auth["token"])
    )
    assert response.status_code == 403


async def test_packages_are_priced_in_stars(client, fake_telegram):
    auth = await authenticate(client, 8008)
    packages = (await client.get("/api/payments/packages", headers=auth_header(auth["token"]))).json()
    assert packages and all(p["currency"] == "XTR" for p in packages)
    assert all(p["total_gg"] == p["gg"] + p["bonus_gg"] for p in packages)
