"""DataUpdateCoordinator for ESB Meter: fetches data and pushes to HA statistics."""
from __future__ import annotations

import csv
import datetime
import json
import logging
import re
from io import StringIO
from typing import Any

import requests
from bs4 import BeautifulSoup
import pytz

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
)
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_MPRN, DEFAULT_SCAN_INTERVAL_HOURS, DOMAIN, STATISTIC_ID, STATISTIC_NAME

_LOGGER = logging.getLogger(__name__)

_TZ_DUBLIN = pytz.timezone("Europe/Dublin")
_DATE_FMT = "%d-%m-%Y %H:%M"


def _parse_local_dt(local_time: str) -> datetime.datetime:
    """Parse an Irish local time string to a UTC-aware datetime."""
    dt = datetime.datetime.strptime(local_time, _DATE_FMT)
    return _TZ_DUBLIN.localize(dt).astimezone(pytz.utc)


def _create_session(username: str, password: str) -> requests.Session:
    """Log in to ESB Networks and return an authenticated session.

    Raises UpdateFailed on any login error.
    """
    s = requests.Session()
    s.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_3) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/104.0.0.0 Safari/537.36"
        ),
    })

    _LOGGER.debug("Fetching ESB login page")
    login_page = s.get("https://myaccount.esbnetworks.ie/", allow_redirects=True)
    result = re.findall(r"(?<=var SETTINGS = )\S*;", login_page.text)
    if not result:
        _LOGGER.error("Could not find SETTINGS variable on ESB login page. Page status: %s", login_page.status_code)
        raise UpdateFailed("Could not find SETTINGS on ESB login page")

    try:
        settings = json.loads(result[0][:-1])
    except json.JSONDecodeError as err:
        _LOGGER.error("Failed to parse SETTINGS JSON: %s", err)
        raise UpdateFailed(f"Failed to parse ESB login settings: {err}") from err

    _LOGGER.debug("Submitting credentials")
    s.post(
        "https://login.esbnetworks.ie/esbntwkscustportalprdb2c01.onmicrosoft.com"
        "/B2C_1A_signup_signin/SelfAsserted"
        f"?tx={settings['transId']}&p=B2C_1A_signup_signin",
        data={
            "signInName": username,
            "password": password,
            "request_type": "RESPONSE",
        },
        headers={"x-csrf-token": settings["csrf"]},
        allow_redirects=False,
    )

    _LOGGER.debug("Confirming login")
    confirm_login = s.get(
        "https://login.esbnetworks.ie/esbntwkscustportalprdb2c01.onmicrosoft.com"
        "/B2C_1A_signup_signin/api/CombinedSigninAndSignup/confirmed",
        params={
            "rememberMe": False,
            "csrf_token": settings["csrf"],
            "tx": settings["transId"],
            "p": "B2C_1A_signup_signin",
        },
    )

    soup = BeautifulSoup(confirm_login.content, "html.parser")
    form = soup.find("form", {"id": "auto"})
    if form is None:
        _LOGGER.error(
            "Login failed: no redirect form found in response (status %s). "
            "Credentials may be incorrect.",
            confirm_login.status_code,
        )
        raise UpdateFailed("Login failed: check your ESB username and password.")

    s.post(
        form["action"],
        allow_redirects=False,
        data={
            "state": form.find("input", {"name": "state"})["value"],
            "client_info": form.find("input", {"name": "client_info"})["value"],
            "code": form.find("input", {"name": "code"})["value"],
        },
    )

    _LOGGER.debug("ESB login successful")
    return s


def validate_credentials(username: str, password: str) -> None:
    """Lightweight credential check — just logs in, no data download.

    Raises UpdateFailed if login fails.
    """
    _create_session(username, password)


def _fetch_esb_data(username: str, password: str, mprn: str) -> list[dict[str, Any]]:
    """Log in and download the full HDF CSV data for the given MPRN."""
    s = _create_session(username, password)

    today = datetime.date.today().strftime("%Y-%m-%d")
    _LOGGER.debug("Downloading HDF data for MPRN %s", mprn)
    data = s.get(
        f"https://myaccount.esbnetworks.ie/DataHub/DownloadHdf"
        f"?mprn={mprn}&startDate={today}"
    )
    if not data.ok:
        _LOGGER.error("HDF download failed: HTTP %s", data.status_code)
        raise UpdateFailed(f"Failed to download HDF data: HTTP {data.status_code}")

    reader = csv.DictReader(StringIO(data.content.decode("utf-8")))
    records = list(reader)
    _LOGGER.debug("Downloaded %d records from ESB", len(records))
    return records


class EsbMeterCoordinator(DataUpdateCoordinator):
    """Coordinator that fetches ESB data and injects it into HA statistics."""

    def __init__(self, hass: HomeAssistant, entry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=datetime.timedelta(hours=DEFAULT_SCAN_INTERVAL_HOURS),
        )
        self._username: str = entry.data[CONF_USERNAME]
        self._password: str = entry.data[CONF_PASSWORD]
        self._mprn: str = entry.data[CONF_MPRN]
        self.latest_reading: float | None = None

    async def _async_update_data(self) -> None:
        try:
            records = await self.hass.async_add_executor_job(
                _fetch_esb_data, self._username, self._password, self._mprn
            )
        except UpdateFailed:
            raise
        except Exception as err:
            _LOGGER.exception("Unexpected error fetching ESB data")
            raise UpdateFailed(f"Unexpected error: {err}") from err

        await self._async_push_statistics(records)

    async def _async_push_statistics(self, records: list[dict[str, Any]]) -> None:
        """Convert records to HA StatisticData and push via async_add_external_statistics."""

        last_stats = await get_instance(self.hass).async_add_executor_job(
            get_last_statistics, self.hass, 1, STATISTIC_ID, True, {"sum"}
        )
        last_ts: datetime.datetime | None = None
        if last_stats and STATISTIC_ID in last_stats:
            last_ts = datetime.datetime.fromtimestamp(
                last_stats[STATISTIC_ID][0]["start"], tz=datetime.timezone.utc
            )

        stat_data: list[StatisticData] = []
        latest_value: float | None = None

        for record in records:
            try:
                dt = _parse_local_dt(record["Read Date and End Time"])
                value_kw = float(record["Read Value"])
            except (KeyError, ValueError):
                continue

            # ESB data is in kW over a 30-min window; convert to kWh
            value_kwh = value_kw * 0.5

            if latest_value is None:
                latest_value = value_kwh

            if last_ts is not None and dt <= last_ts:
                continue

            stat_data.append(StatisticData(start=dt, state=value_kwh, sum=None))

        if latest_value is not None:
            self.latest_reading = latest_value

        if not stat_data:
            _LOGGER.debug("No new ESB statistics to push")
            return

        metadata = StatisticMetaData(
            has_mean=False,
            has_sum=True,
            name=STATISTIC_NAME,
            source=DOMAIN,
            statistic_id=STATISTIC_ID,
            unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        )

        async_add_external_statistics(self.hass, metadata, stat_data)
        _LOGGER.info("Pushed %d new ESB statistics to HA", len(stat_data))
