import typing
from dataclasses import dataclass
from base64 import b64decode
from solana.publickey import PublicKey
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Commitment
import borsh_construct as borsh
from anchorpy.coder.accounts import ACCOUNT_DISCRIMINATOR_SIZE
from anchorpy.error import AccountInvalidDiscriminator
from anchorpy.borsh_extension import BorshPubkey
from ..program_id import PROGRAM_ID


class CounterFields(typing.TypedDict):
    authority: PublicKey
    count: int


class CounterJSON(typing.TypedDict):
    authority: str
    count: int


@dataclass
class Counter:
    discriminator: typing.ClassVar = b"\xff\xb0\x04\xf5\xbc\xfd|\x19"
    layout: typing.ClassVar = borsh.CStruct(
        "authority" / BorshPubkey, "count" / borsh.U64
    )
    authority: PublicKey
    count: int

    @classmethod
    async def fetch(
        cls,
        conn: AsyncClient,
        address: PublicKey,
        commitment: typing.Optional[Commitment] = None,
    ) -> typing.Optional["Counter"]:
        resp = await conn.get_account_info(address, commitment=commitment)
        info = resp["result"]["value"]
        if info is None:
            return None
        if info["owner"] != str(PROGRAM_ID):
            raise ValueError("Account does not belong to this program")
        bytes_data = b64decode(info["data"][0])
        return cls.decode(bytes_data)

    @classmethod
    async def fetch_multiple(
        cls,
        conn: AsyncClient,
        addresses: list[typing.Union[PublicKey, str]],
        commitment: typing.Optional[Commitment] = None,
    ) -> typing.List[typing.Optional["Counter"]]:
        resp = await conn.get_multiple_accounts(addresses, commitment=commitment)
        infos = resp["result"]["value"]
        res: typing.List[typing.Optional["Counter"]] = []
        for info in infos:
            if info is None:
                res.append(None)
            if info["owner"] != str(PROGRAM_ID):
                raise ValueError("Account does not belong to this program")
            bytes_data = b64decode(info["data"][0])
            res.append(cls.decode(bytes_data))
        return res

    @classmethod
    def decode(cls, data: bytes) -> "Counter":
        if data[:ACCOUNT_DISCRIMINATOR_SIZE] != cls.discriminator:
            raise AccountInvalidDiscriminator(
                "The discriminator for this account is invalid"
            )
        dec = Counter.layout.parse(data[ACCOUNT_DISCRIMINATOR_SIZE:])
        return cls(
            authority=dec.authority,
            count=dec.count,
        )

    def to_json(self) -> CounterJSON:
        return {
            "authority": str(self.authority),
            "count": self.count,
        }

    @classmethod
    def from_json(cls, obj: CounterJSON) -> "Counter":
        return cls(
            authority=PublicKey(obj["authority"]),
            count=obj["count"],
        )