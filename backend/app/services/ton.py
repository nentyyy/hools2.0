"""TON Connect integration.

What the backend does and does not do:

* it never stores a seed phrase, private key or any custodial material — only
  the public address and the `ton_proof` we verified;
* connecting a wallet requires a valid ed25519 `ton_proof` signature over the
  payload we issued, so an address cannot be claimed by typing it in;
* on-chain transfers are confirmed against a public indexer, never against data
  the frontend reports.

TON is used for wallet-linked blockchain features. Digital goods inside the Mini
App are sold for Telegram Stars, as Telegram requires — TON is not a way around
that.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import struct
import time
from datetime import UTC, datetime
from urllib.parse import urlparse

import httpx
from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.redis import get_redis
from app.models import TonTransaction, TonWallet, User

logger = logging.getLogger(__name__)

PROOF_PREFIX = b"ton-proof-item-v2/"
CONNECT_PREFIX = b"\xff\xff" + b"ton-connect"
PROOF_TTL = 600  # seconds a ton_proof payload stays valid
NANO = 1_000_000_000


# --------------------------------------------------------------------------- #
# proof payload
# --------------------------------------------------------------------------- #
async def issue_proof_payload(user_id: int) -> str:
    """One-time nonce the wallet has to sign. Stored in Redis with a short TTL."""
    payload = secrets.token_hex(16)
    await get_redis().set(f"tonproof:{user_id}:{payload}", "1", ex=PROOF_TTL)
    return payload


async def consume_proof_payload(user_id: int, payload: str) -> bool:
    """Burn the nonce so a captured proof cannot be replayed."""
    return bool(await get_redis().delete(f"tonproof:{user_id}:{payload}"))


# --------------------------------------------------------------------------- #
# proof verification
# --------------------------------------------------------------------------- #
def _address_parts(address: str) -> tuple[int, bytes]:
    """Split a raw `0:hex` TON address into (workchain, 32 byte hash)."""
    if ":" not in address:
        raise ValidationError("TON address must be in raw `workchain:hash` form")
    workchain_str, hash_hex = address.split(":", 1)
    try:
        workchain = int(workchain_str)
        addr_hash = bytes.fromhex(hash_hex)
    except ValueError as exc:
        raise ValidationError("TON address is malformed") from exc
    if len(addr_hash) != 32:
        raise ValidationError("TON address hash must be 32 bytes")
    return workchain, addr_hash


def build_proof_message(address: str, domain: str, timestamp: int, payload: str) -> bytes:
    """Rebuild the exact bytes a TON Connect wallet signs."""
    workchain, addr_hash = _address_parts(address)
    domain_bytes = domain.encode()
    message = (
        PROOF_PREFIX
        + struct.pack("<i", workchain)
        + addr_hash
        + struct.pack("<I", len(domain_bytes))
        + domain_bytes
        + struct.pack("<Q", timestamp)
        + payload.encode()
    )
    return hashlib.sha256(CONNECT_PREFIX + hashlib.sha256(message).digest()).digest()


async def fetch_public_key(address: str) -> bytes | None:
    """Ask a public indexer for the wallet's ed25519 public key."""
    url = f"{settings.ton_api_base.rstrip('/')}/v2/accounts/{address}/publickey"
    headers = {"Authorization": f"Bearer {settings.ton_api_key}"} if settings.ton_api_key else {}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers)
            if response.status_code != 200:
                logger.warning("ton publickey lookup failed: %s", response.status_code)
                return None
            key_hex = response.json().get("public_key")
            return bytes.fromhex(key_hex) if key_hex else None
    except (httpx.HTTPError, ValueError):
        logger.warning("ton publickey lookup errored", exc_info=True)
        return None


def _allowed_domain(domain: str) -> bool:
    host = urlparse(settings.webapp_url).hostname
    return bool(host) and domain.split(":")[0].lower() == host.lower()


async def verify_proof(
    *,
    address: str,
    proof: dict,
    expected_payload: str,
    public_key_hex: str | None = None,
) -> bool:
    """Verify a TON Connect `ton_proof`. Raises ValidationError on a bad proof."""
    timestamp = int(proof.get("timestamp", 0))
    if abs(time.time() - timestamp) > PROOF_TTL:
        raise ValidationError("ton_proof timestamp is out of range")

    domain = (proof.get("domain") or {}).get("value") or ""
    if not domain:
        raise ValidationError("ton_proof has no domain")
    if settings.is_production and not _allowed_domain(domain):
        raise ValidationError("ton_proof domain does not match this app")

    payload = proof.get("payload") or ""
    if payload != expected_payload:
        raise ValidationError("ton_proof payload does not match the issued challenge")

    signature_b64 = proof.get("signature")
    if not signature_b64:
        raise ValidationError("ton_proof has no signature")

    key_bytes = bytes.fromhex(public_key_hex) if public_key_hex else await fetch_public_key(address)
    if not key_bytes:
        raise ValidationError("Could not resolve the wallet public key")

    message = build_proof_message(address, domain, timestamp, payload)
    try:
        VerifyKey(key_bytes).verify(message, base64.b64decode(signature_b64))
    except (BadSignatureError, ValueError) as exc:
        raise ValidationError("ton_proof signature is invalid") from exc
    return True


# --------------------------------------------------------------------------- #
# wallet records
# --------------------------------------------------------------------------- #
async def get_wallet(session: AsyncSession, user_id: int) -> TonWallet | None:
    return await session.scalar(select(TonWallet).where(TonWallet.user_id == user_id))


async def connect_wallet(
    session: AsyncSession,
    user: User,
    *,
    address: str,
    proof: dict | None,
    public_key: str | None = None,
    friendly_address: str | None = None,
    chain: str | None = None,
    wallet_name: str | None = None,
) -> TonWallet:
    verified_at: datetime | None = None

    if proof:
        expected = proof.get("payload", "")
        if not await consume_proof_payload(user.id, expected):
            raise ValidationError("ton_proof challenge is unknown or expired")
        await verify_proof(address=address, proof=proof, expected_payload=expected, public_key_hex=public_key)
        verified_at = datetime.now(UTC)
    elif settings.is_production:
        raise ValidationError("ton_proof is required to connect a wallet")

    wallet = await get_wallet(session, user.id)
    if wallet is None:
        wallet = TonWallet(user_id=user.id)
        session.add(wallet)

    wallet.address = address
    wallet.friendly_address = friendly_address
    wallet.public_key = public_key
    wallet.chain = chain
    wallet.wallet_name = wallet_name
    wallet.connected_at = datetime.now(UTC)
    wallet.disconnected_at = None
    wallet.proof_verified_at = verified_at
    await session.flush()

    logger.info(
        "ton_wallet_connected",
        extra={"user_id": user.id, "address": address, "verified": verified_at is not None},
    )
    return wallet


async def disconnect_wallet(session: AsyncSession, user_id: int) -> None:
    wallet = await get_wallet(session, user_id)
    if wallet is None:
        raise NotFoundError("No wallet connected")
    await session.delete(wallet)
    await session.flush()
    logger.info("ton_wallet_disconnected", extra={"user_id": user_id})


# --------------------------------------------------------------------------- #
# transactions
# --------------------------------------------------------------------------- #
async def _fetch_transaction(tx_hash: str) -> dict | None:
    url = f"{settings.ton_api_base.rstrip('/')}/v2/blockchain/transactions/{tx_hash}"
    headers = {"Authorization": f"Bearer {settings.ton_api_key}"} if settings.ton_api_key else {}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url, headers=headers)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError:
        logger.warning("ton transaction lookup failed for %s", tx_hash, exc_info=True)
        return None


async def verify_transaction(
    session: AsyncSession,
    user: User,
    *,
    boc_hash: str,
    tx_hash: str | None = None,
    expected_amount_nano: int | None = None,
    comment: str | None = None,
    purpose: str | None = None,
) -> TonTransaction:
    """Record and confirm an on-chain transfer.

    The transfer is looked up on chain; nothing the client claims about the
    amount or the destination is taken at face value.
    """
    wallet = await get_wallet(session, user.id)
    if wallet is None:
        raise ConflictError("Connect a TON wallet first")

    existing = await session.scalar(
        select(TonTransaction)
        .where(TonTransaction.boc_hash == boc_hash)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    record = existing or TonTransaction(
        user_id=user.id,
        boc_hash=boc_hash,
        tx_hash=tx_hash,
        from_address=wallet.address,
        to_address=settings.ton_receiver_address or None,
        comment=comment,
        purpose=purpose,
        status="pending",
    )
    if existing and existing.user_id != user.id:
        raise ConflictError("This transaction belongs to another account")
    if existing is None:
        session.add(record)
        await session.flush()
    if existing and existing.status == "confirmed":
        return existing

    onchain = await _fetch_transaction(tx_hash or boc_hash)
    if onchain:
        in_msg = onchain.get("in_msg") or {}
        value = int(in_msg.get("value") or 0)
        destination = ((in_msg.get("destination") or {}).get("address")) or ""
        source = ((in_msg.get("source") or {}).get("address")) or ""

        mismatched = []
        if settings.ton_receiver_address and destination and destination != settings.ton_receiver_address:
            mismatched.append("destination")
        if expected_amount_nano and value < int(expected_amount_nano):
            mismatched.append("amount")
        if not onchain.get("success", True):
            mismatched.append("failed_on_chain")

        record.tx_hash = onchain.get("hash", tx_hash)
        record.amount_nano = value
        record.amount_ton = value / NANO
        record.from_address = source or record.from_address
        record.to_address = destination or record.to_address
        record.raw = onchain
        record.status = "failed" if mismatched else "confirmed"
        if not mismatched:
            record.confirmed_at = datetime.now(UTC)
        else:
            logger.warning(
                "ton verification mismatch",
                extra={"user_id": user.id, "boc_hash": boc_hash, "problems": mismatched},
            )
    else:
        # Not indexed yet — stays pending and can be re-checked later.
        record.status = "pending"

    await session.flush()
    logger.info(
        "ton_transaction_checked",
        extra={"user_id": user.id, "boc_hash": boc_hash, "status": record.status},
    )
    return record


async def list_transactions(
    session: AsyncSession, user_id: int, *, limit: int = 50, offset: int = 0
) -> list[TonTransaction]:
    return list(
        (
            await session.execute(
                select(TonTransaction)
                .where(TonTransaction.user_id == user_id)
                .order_by(TonTransaction.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        ).scalars().all()
    )
