from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from aiohttp import ClientSession, ClientError
from bs4 import BeautifulSoup

from ..const import DEFAULT_MOUNTAIN_REGION
from .region_map import REGION_TO_URL

_LOGGER = logging.getLogger(__name__)


class MountainClient:
    """Odjemalec za ARSO 'Računska napoved višinskih vrednosti' (gorska)."""

    def __init__(self, session: ClientSession, region: str | None = None) -> None:
        self._session = session
        self._region = region or DEFAULT_MOUNTAIN_REGION

    @property
    def source_url(self) -> str:
        return REGION_TO_URL.get(self._region, REGION_TO_URL[DEFAULT_MOUNTAIN_REGION])

    async def fetch_upper_air_html(self) -> dict[str, Any]:
        """Prenese HTML in vrne tudi strukturiran parse (MVP)."""
        url = self.source_url
        try:
            async with self._session.get(url, timeout=30) as resp:
                text = await resp.text()
        except (asyncio.TimeoutError, ClientError) as err:
            _LOGGER.warning("Mountain fetch failed from %s: %s", url, err)
            raise

        now = datetime.now(timezone.utc).isoformat()
        preview = text[:1000]

        parsed: dict[str, Any] = {}
        try:
            parsed = self._parse_upper_air_html(text)
        except Exception as exc:
            _LOGGER.exception("Mountain HTML parse failed: %s", exc)

        return {
            "source_url": url,
            "updated_at_utc": now,
            "raw_html_length": len(text),
            "raw_html_preview": preview,
            "parsed": parsed,  # <-- strukturirani podatki (če je parsing uspel)
        }

    # ----------------- PARSER -----------------

    def _parse_upper_air_html(self, html: str) -> dict[str, Any]:
        """Parsira prvo tabelo z razredom 'meteoSI-table' v strukturiran grid + izbrane variable."""
        soup = BeautifulSoup(html, "html.parser")

        # Najdi naslov/heading (opcionalno)
        title = None
        h2 = soup.find("h2")
        if h2 and h2.get_text(strip=True):
            title = h2.get_text(" ", strip=True)

        table = soup.find("table", class_="meteoSI-table")
        if not table:
            raise ValueError("meteoSI-table not found")

        # Header stolpcev: poskusi prebrati TH iz <thead>
        columns: list[str] = []
        thead = table.find("thead")
        if thead:
            # Včasih so 1–2 header vrstice; poberemo vse TH razen prvega (ime vrstice)
            ths = thead.find_all("th")
            # če je prvi th "meteoSI-header" s colspan, ga lahko preskočimo
            # poberi zadnjih N th-jev, ki niso prazni
            for th in ths:
                txt = th.get_text(" ", strip=True)
                if not txt:
                    continue
                columns.append(txt)
            # pogosto je prvi header celica naslov, zato columns brez prve, če je očitno naslov
            if len(columns) > 1 and "napoved" in columns[0].lower():
                columns = columns[1:]
        # fallback: brez thead — bomo poimenovali generično
        # (natančno ime ur bomo še vedno uporabili iz <tbody> števila celic)

        # Telo tabele
        body_rows = table.find_all("tr")
        parsed_rows: list[dict[str, Any]] = []
        max_cols = 0

        for tr in body_rows:
            cells = tr.find_all(["th", "td"])
            if not cells:
                continue
            # prvi cell je ime vrstice (spremenljivke)
            row_name = cells[0].get_text(" ", strip=True)
            if not row_name:
                continue
            # preostali cell-i so vrednosti
            values_raw = [c.get_text(" ", strip=True) for c in cells[1:]]
            max_cols = max(max_cols, len(values_raw))

            # pretvori v številke kjer gre (črte/pomišljaje -> None)
            def to_num(s: str) -> Optional[float]:
                if not s:
                    return None
                s2 = s.replace(",", ".")
                # odstrani ne-številčne znake na robovih (°C, m, m/s)
                # pusti minus in piko
                import re

                m = re.search(r"-?\d+(\.\d+)?", s2)
                return float(m.group(0)) if m else None

            values_num: list[Optional[float]] = [to_num(v) for v in values_raw]

            parsed_rows.append(
                {
                    "name": row_name,
                    "values": values_num,
                    "raw": values_raw,
                    "unit": self._guess_unit(row_name),
                }
            )

        # če columns ni iz thead, naredi generiko
        if not columns:
            columns = [f"t{idx}" for idx in range(max_cols)]

        # Izlušči nekaj “znanih” spremenljivk (heuristično po imenu)
        vars_out: dict[str, dict[str, Optional[float]]] = {}
        def pick(name_like: list[str]) -> Optional[dict[str, Any]]:
            for r in parsed_rows:
                nm = r["name"].lower()
                if any(token in nm for token in name_like):
                    return r
            return None

        # 0°C izoterma
        r_zero = pick(["0 °c izoterma", "0°c izoterma", "0 c izoterma", "izoterma 0"])
        if r_zero:
            vals = [v for v in r_zero["values"] if isinstance(v, (int, float, float))]
            vars_out["zero_isotherm_m"] = {
                "min": min(vals) if vals else None,
                "max": max(vals) if vals else None,
            }

        # meja sneženja
        r_snow = pick(["meja sneženja", "sneženja"])
        if r_snow:
            vals = [v for v in r_snow["values"] if isinstance(v, (int, float, float))]
            vars_out["snow_line_m"] = {
                "min": min(vals) if vals else None,
                "max": max(vals) if vals else None,
            }

        # T1500 in T2500
        r_t1500 = pick(["t 1500", "t1500"])
        if r_t1500:
            vals = [v for v in r_t1500["values"] if isinstance(v, (int, float, float))]
            vars_out["t_1500_c"] = {
                "min": min(vals) if vals else None,
                "max": max(vals) if vals else None,
            }

        r_t2500 = pick(["t 2500", "t2500"])
        if r_t2500:
            vals = [v for v in r_t2500["values"] if isinstance(v, (int, float, float))]
            vars_out["t_2500_c"] = {
                "min": min(vals) if vals else None,
                "max": max(vals) if vals else None,
            }

        return {
            "title": title,
            "columns": columns,
            "rows": parsed_rows,
            "vars": vars_out,
        }

    @staticmethod
    def _guess_unit(name: str) -> Optional[str]:
        n = name.lower()
        if "°c" in n:
            return "°C"
        if "m/s" in n:
            return "m/s"
        if "km/h" in n:
            return "km/h"
        if " m" in n or n.endswith("m"):
            return "m"
        return None
