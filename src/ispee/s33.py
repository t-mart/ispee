"""Scraper for the Arris S33 modem info page"""
from __future__ import annotations

import hmac
import time
from collections.abc import Iterable
from typing import Optional

import httpx
from attrs import define, field, frozen
from yarl import URL

from ispee.console import CONSOLE
from ispee.exception import ModemScrapeError

CLIENT = httpx.AsyncClient(
    verify=False,  # s33 uses self-signed cert. gross.
    timeout=30.0,  # these reads are awfully slow sometimes
)


@frozen(kw_only=True)
class DownstreamChannel:
    """Data for a downstream channel."""

    channel_select: int
    lock_status: str
    channel_type: str
    channel_id: int
    frequency_hz: int
    power_dbmv: float
    snr_db: float
    corrected_codewords_total: int
    uncorrectable_codewords_total: int

    @classmethod
    def parse_response(cls, response: str) -> Iterable[DownstreamChannel]:
        """
        Parse the funny-looking format from a GetCustomerStatusDownstreamChannelInfo
        request.
        """
        # this ordering comes from a comment in https://<host>/js/connectionstatus.js:
        # - Channel Select (orders the list on the page?)
        # - Lock Status
        # - Channel Type (aka modulation)
        # - Channel ID
        # - Frequency
        # - Power Level (aka power)
        # - SNR Level (aka SNR/MER)
        # - Corrected Codewords
        # - Unerroreds Codewords

        for encoded_channel in response.split("|+|"):
            (
                channel_select,
                lock_status,
                channel_type,
                channel_id,
                frequency_hz,
                power_dbmv,
                snr_db,
                corrected_codewords_total,
                uncorrectable_codewords_total,
                _,  # they put a marker at end, so there'll be an extra item
            ) = encoded_channel.split("^")

            yield DownstreamChannel(
                channel_select=int(channel_select),
                lock_status=lock_status,
                channel_type=channel_type,
                channel_id=int(channel_id),
                frequency_hz=int(frequency_hz),
                power_dbmv=float(power_dbmv),
                snr_db=float(snr_db),
                corrected_codewords_total=int(corrected_codewords_total),
                uncorrectable_codewords_total=int(uncorrectable_codewords_total),
            )


@frozen(kw_only=True)
class UpstreamChannel:
    """Data for an upstream channel."""

    channel_select: int
    lock_status: str
    channel_type: str
    channel_id: int
    symbols_per_sec: int
    frequency_hz: int
    power_dbmv: float

    @classmethod
    def parse_response(cls, response: str) -> Iterable[UpstreamChannel]:
        """
        Parse the funny-looking format from a GetCustomerStatusUpstreamChannelInfo
        request.
        """
        # this ordering comes from a comment in https://<host>/js/connectionstatus.js:
        # - Channel Select (orders the list on the page?)
        # - Lock Status
        # - Channel Type (aka US channel Type)
        # - Channel ID
        # - Symbol Rate/Width (there's a comment saying unit is "Ksym/sec")
        # - Frequency
        # - Power Level

        for encoded_channel in response.split("|+|"):
            (
                channel_select,
                lock_status,
                channel_type,
                channel_id,
                symbols_per_sec,
                frequency_hz,
                power_dbmv,
                _,  # they put a marker at end, so there'll be an extra item
            ) = encoded_channel.split("^")

            yield UpstreamChannel(
                channel_select=int(channel_select),
                lock_status=lock_status,
                channel_type=channel_type,
                channel_id=int(channel_id),
                symbols_per_sec=int(symbols_per_sec),
                frequency_hz=int(frequency_hz),
                power_dbmv=float(power_dbmv),
            )


@frozen
class _LoginChallengeParameters:
    public_key: str
    uid: str
    challenge_msg: str


@define
class S33Scraper:
    """A scraper for modem information of the Arris S33, with support for logins."""

    host: str
    password: str
    username: str = field(default="admin")  # AFAIK, this is the only username
    # this is a tuple bc they share the same lifetime. either both are set or neither
    _auth_uid_private_key: Optional[tuple[str, str]] = field(default=None)

    @property
    def _hnap_url(self) -> str:
        """Return the HNAP1 url of the host for this scraper."""
        return str(URL.build(scheme="https", host=self.host, path="/HNAP1/"))

    @staticmethod
    def _arris_hmac(key: bytes, msg: bytes) -> str:
        """HMAC a message with a key in the way the arris s33 does it."""
        return (
            hmac.new(
                key=key,
                msg=msg,
                digestmod="md5",
            )
            .hexdigest()
            .upper()
        )

    def _hnap_auth_header_value(self, soap_action: str) -> str:
        """Return a value to be used for the custom HNAP_AUTH http header."""
        # this method is not contingent on already being logged in. there's a fallback
        # for when we're not logged in.
        if self._auth_uid_private_key is not None:
            _, private_key = self._auth_uid_private_key
        else:
            private_key = "withoutloginkey"

        # wierd... shrug. just following the javascript impl.
        cur_time_millis = str((time.time_ns() // 10**6) % 2_000_000_000_000)

        auth_part = self._arris_hmac(
            private_key.encode("utf-8"),
            (cur_time_millis + soap_action).encode("utf-8"),
        )

        return f"{auth_part} {cur_time_millis}"

    def _build_soap_action_headers(
        self, soap_action: str, with_auth_cookies: bool
    ) -> dict[str, str]:
        """
        Build the time-sensitive headers for a /HNAP1/ request. These should be built
        anew before each request. (I think?)
        """
        # The SOAPACTION is like the API endpoint... it specfies what action we're doing
        # on the server
        #
        # Every request always gets an HNAP_AUTH header, which can be generated even if
        # we're not currently authenticated.
        headers = {
            "Accept": "application/json",
            "SOAPACTION": soap_action,
            "HNAP_AUTH": self._hnap_auth_header_value(soap_action),
        }

        # however, setting the Cookie with uid and PrivateKey can only occur if we've
        # previously logged in.
        if with_auth_cookies:
            if self._auth_uid_private_key is None:
                raise ModemScrapeError(
                    "Cannot add authentication cookie when login has not yet occurred."
                )
            uid, private_key = self._auth_uid_private_key
            headers["Cookie"] = (
                "Secure; Secure; "  # double secure is strange, but how they do it TODO
                f"uid={uid}; "
                f"PrivateKey={private_key}"
            )

        return headers

    async def _request_login_challenge(self) -> _LoginChallengeParameters:
        """
        Do the first part of the login flow, where we post a "request" action which
        provides us with a public key, uid, and challenge, which we'll use later.
        """
        payload = {
            "Login": {
                "Action": "request",
                "Username": self.username,
                "LoginPassword": "",
                "Captcha": "",
                "PrivateLogin": "LoginPassword",
            }
        }
        soap_action = '"http://purenetworks.com/HNAP1/Login"'

        response = await CLIENT.post(  # pylint: disable=no-member
            url=self._hnap_url,
            json=payload,
            headers=self._build_soap_action_headers(
                soap_action=soap_action,
                with_auth_cookies=False,  # we're not auth-ed yet, so no auth cookies
            ),
        )
        if response.status_code != httpx.codes.OK:
            raise ModemScrapeError(
                f"Got {response.status_code} status code when making 1st login request"
            )

        response_obj = response.json()

        return _LoginChallengeParameters(
            public_key=response_obj["LoginResponse"]["PublicKey"],
            # object calls it "Cookie", but its use later calls it "uid"
            uid=response_obj["LoginResponse"]["Cookie"],
            challenge_msg=response_obj["LoginResponse"]["Challenge"],
        )

    async def _submit_hmac_challenge(self, challenge_msg: str) -> None:
        """
        Do the second part of the login flow, where a "login" action is submitted with
        an HMAC-ed a challenge message. Raises a NotAuthenticatedError exception if
        unsuccessful according to server or if the first part (_get_login_challenge) has
        not yet occurred.

        This request/response part doesn't pass any secrets back to the client. It
        appears to only do something server side.
        """
        if self._auth_uid_private_key is None:
            raise ModemScrapeError(
                "Cannot do second part of login flow before first part."
            )
        _, private_key = self._auth_uid_private_key
        login_password = self._arris_hmac(
            key=private_key.encode("utf-8"),
            msg=challenge_msg.encode("utf-8"),
        )
        payload = {
            "Login": {
                "Action": "login",
                "Username": self.username,
                "LoginPassword": login_password,
                "Captcha": "",
                "PrivateLogin": "LoginPassword",
            }
        }
        soap_action = '"http://purenetworks.com/HNAP1/Login"'
        headers = self._build_soap_action_headers(
            soap_action=soap_action, with_auth_cookies=True
        )

        response = await CLIENT.post(  # pylint: disable=no-member
            url=self._hnap_url,
            json=payload,
            headers=headers,
        )
        if response.status_code != httpx.codes.OK:
            raise ModemScrapeError(
                f"Got {response.status_code} status code when making 2nd login request"
            )

        response_obj = response.json()

        login_result = response_obj["LoginResponse"]["LoginResult"]
        if login_result != "OK":
            raise ModemScrapeError(f"Got {login_result} login result (expecting OK)")
        CONSOLE.log("Logged in successfully")

    async def _login(self) -> None:
        """
        Do the two-part login flow. It provides us with credentials that we put into
        headers and cookies, and also authenticates our credentials on the server.

        Btw, we know how to do this from reading https://<host>/js/Login.js
        """
        challenge_params = await self._request_login_challenge()

        private_key = self._arris_hmac(
            key=(challenge_params.public_key + self.password).encode("utf-8"),
            msg=challenge_params.challenge_msg.encode("utf-8"),
        )

        # store these for later use, they'll be part of every subsequent Cookie header
        self._auth_uid_private_key = (challenge_params.uid, private_key)

        await self._submit_hmac_challenge(challenge_params.challenge_msg)

    async def get_channel_info(
        self,
    ) -> tuple[Iterable[DownstreamChannel], Iterable[UpstreamChannel]]:
        """
        Return a two-tuple of a list of downstream channels and a list of upstream
        channels from the modem status page provided by host. Logins will occur if
        needed and cookies indicating that authentication will be persisted.
        """
        payload = {
            "GetMultipleHNAPs": {
                "GetCustomerStatusDownstreamChannelInfo": "",
                "GetCustomerStatusUpstreamChannelInfo": "",
            }
        }
        soap_action = '"http://purenetworks.com/HNAP1/GetMultipleHNAPs"'

        try:
            headers = self._build_soap_action_headers(
                soap_action=soap_action,
                with_auth_cookies=True,
            )
        except ModemScrapeError:
            CONSOLE.log(
                "Trying to make request to authorized endpoint while unauthorized. "
                "(This happens with fresh processes that have never logged in). "
                "Attempting login..."
            )
            await self._login()
            # just retry the method
            return await self.get_channel_info()

        response = await CLIENT.post(  # pylint: disable=no-member
            url=self._hnap_url,
            json=payload,
            headers=headers,
            follow_redirects=True,
        )

        if response.status_code == 404:
            CONSOLE.log(
                "Scrape request returned 404. (Credentials may have expired.) "
                "Attempting login..."
            )
            await self._login()
            # just retry the method
            return await self.get_channel_info()

        if response.status_code != httpx.codes.OK:
            raise ModemScrapeError(
                f"Got {response.status_code} status code when getting channel info"
            )

        response_obj = response.json()

        return (
            list(
                DownstreamChannel.parse_response(
                    response_obj["GetMultipleHNAPsResponse"][
                        "GetCustomerStatusDownstreamChannelInfoResponse"
                    ]["CustomerConnDownstreamChannel"]
                )
            ),
            list(
                UpstreamChannel.parse_response(
                    response_obj["GetMultipleHNAPsResponse"][
                        "GetCustomerStatusUpstreamChannelInfoResponse"
                    ]["CustomerConnUpstreamChannel"]
                )
            ),
        )
