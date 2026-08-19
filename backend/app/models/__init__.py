"""SQLAlchemy models. Importing this package registers every table on Base."""

from app.models.base import Base
from app.models.giveaway import Giveaway, GiveawayParticipant
from app.models.inventory import InventoryItem
from app.models.payment import StarPayment
from app.models.pvp import PvPGame, PvPPlayer
from app.models.referral import ReferralBonus
from app.models.seed import GameSeed
from app.models.solo import SoloGame, SoloRound
from app.models.ton import TonTransaction, TonWallet
from app.models.transaction import Transaction
from app.models.user import User

__all__ = [
    "Base",
    "GameSeed",
    "Giveaway",
    "GiveawayParticipant",
    "InventoryItem",
    "PvPGame",
    "PvPPlayer",
    "ReferralBonus",
    "SoloGame",
    "SoloRound",
    "StarPayment",
    "TonTransaction",
    "TonWallet",
    "Transaction",
    "User",
]
