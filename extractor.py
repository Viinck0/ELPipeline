"""
Extractor module pro komunikaci s Rick & Morty API.

Tento modul zajišťuje bezpečnou extrakci dat s ošetřením:
- Paginace pomocí while cyklu s kontrolou 'next' klíče
- Rate limiting (0.2s delay) pro ochranu externího serveru
- Robustní error handling s graceful degradation
- Validace JSON response (kontrola 'results' klíče)
"""

import logging
import time
from typing import Any

import requests
from requests.exceptions import RequestException, Timeout, ConnectionError, HTTPError

logger = logging.getLogger(__name__)

# Konfigurace API
BASE_URL: str = "https://rickandmortyapi.com/api"
RATE_LIMIT_DELAY: float = 0.2
REQUEST_TIMEOUT: int = 15  # Snížený timeout pro rychlejší detekci chyb
MAX_RETRIES: int = 3  # Maximální počet pokusů o request


def fetch_paginated_data(endpoint: str) -> list[dict[str, Any]]:
    """
    Stáhne všechna data z paginovaného API endpointu.

    Používá while cyklus, který bezpečně končí, když 'next' je None.
    Implementuje rate limiting a robustní error handling.

    Args:
        endpoint: Název API endpointu (např. 'character', 'location').

    Returns:
        List všech stažených záznamů z daného endpointu.
    """
    url: str = f"{BASE_URL}/{endpoint}"
    all_results: list[dict[str, Any]] = []
    page: int = 1

    logger.info(f"Zahájení extrakce entity '{endpoint}' z URL: {url}")

    try:
        while url is not None:
            response: requests.Response = _make_request(url)

            if response is None:
                logger.error(f"Extrakce '{endpoint}' přerušena - nepodařilo se získat response")
                break

            data: dict[str, Any] = _validate_response(response, endpoint, page)

            if data is None:
                logger.error(f"Extrakce '{endpoint}' přerušena - nevalidní response")
                break

            results: list[dict[str, Any]] = data.get("results", [])
            all_results.extend(results)

            logger.debug(f"Stránka {page}: staženo {len(results)} záznamů")

            # Získání URL další stránky
            info: dict[str, Any] | None = data.get("info")
            if info is None:
                logger.warning(f"Chybějící 'info' blok v response pro '{endpoint}'")
                break

            next_url: str | None = info.get("next")
            if next_url is None:
                logger.info(f"Dosaženo konce paginace pro '{endpoint}' po {page} stránkách")
                break

            url = next_url
            page += 1

            # Rate limiting - ochrana externího serveru
            time.sleep(RATE_LIMIT_DELAY)

    except Exception as e:
        logger.exception(f"Neočekávaná chyba během extrakce '{endpoint}': {e}")
        # Graceful degradation - vrátíme data stažená do tohoto bodu

    logger.info(f"Extrakce '{endpoint}' dokončena: celkem {len(all_results)} záznamů")
    return all_results


def _make_request(url: str) -> requests.Response | None:
    """
    Provede HTTP GET request s robustním error handlingem a retry logikou.

    Ošetřuje síťové výpadky, timeouty a HTTP chyby.
    Implementuje retry mechanismus pro dočasné chyby.

    Args:
        url: Cílová URL pro HTTP request.

    Returns:
        Response objekt při úspěchu, None při chybě.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response: requests.Response = requests.get(
                url=url,
                timeout=REQUEST_TIMEOUT,
                headers={"User-Agent": "RickMorty-EL-Pipeline/1.0"}
            )
            response.raise_for_status()
            return response

        except Timeout:
            logger.warning(f"Timeout (pokusek {attempt}/{MAX_RETRIES}) pro URL: {url}")
            if attempt == MAX_RETRIES:
                logger.error(f"Request timeout pro URL: {url} (timeout={REQUEST_TIMEOUT}s)")
                return None

        except ConnectionError as e:
            logger.warning(f"Chyba připojení (pokusek {attempt}/{MAX_RETRIES}) pro URL: {url} - {e}")
            if attempt == MAX_RETRIES:
                logger.error(f"Chyba připojení pro URL: {url} - {e}")
                return None

        except HTTPError as e:
            status_code: int = e.response.status_code if e.response else 0
            # 429 Too Many Requests - retry s delším zpožděním
            if status_code == 429 and attempt < MAX_RETRIES:
                retry_delay: float = RATE_LIMIT_DELAY * (2 ** attempt)
                logger.warning(f"Rate limit (429), čekám {retry_delay}s před dalším pokusem")
                time.sleep(retry_delay)
                continue
            logger.error(f"HTTP chyba {status_code} pro URL: {url}")
            return None

        except RequestException as e:
            logger.warning(f"Obecná chyba requestu (pokusek {attempt}/{MAX_RETRIES}) pro URL: {url} - {e}")
            if attempt == MAX_RETRIES:
                logger.error(f"Obecná chyba requestu pro URL: {url} - {e}")
                return None

    return None


def _validate_response(response: requests.Response, endpoint: str, page: int) -> dict[str, Any] | None:
    """
    Validuje JSON response z API.

    Kontroluje přítomnost požadovaného 'results' klíče.
    Při nevalidní response loguje chybu a vrací None.

    Args:
        response: HTTP response objekt.
        endpoint: Název endpointu pro logování.
        page: Číslo stránky pro logování.

    Returns:
        Parsovaná JSON data při úspěchu, None při chybě.
    """
    try:
        data: dict[str, Any] = response.json()
    except ValueError as e:
        logger.error(f"Nevalidní JSON na stránce {page} pro '{endpoint}': {e}")
        return None

    if "results" not in data:
        logger.error(f"Chybějící 'results' klíč v response na stránce {page} pro '{endpoint}'")
        logger.debug(f"Response keys: {list(data.keys()) if isinstance(data, dict) else 'N/A'}")
        return None

    return data


def extract_characters() -> list[dict[str, Any]]:
    """
    Extrahuje všechny postavy z Rick & Morty API.

    Returns:
        List všech postav s jejich atributy.
    """
    return fetch_paginated_data("character")


def extract_locations() -> list[dict[str, Any]]:
    """
    Extrahuje všechny lokace z Rick & Morty API.

    Returns:
        List všech lokací s jejich atributy.
    """
    return fetch_paginated_data("location")


def extract_all_data() -> dict[str, list[dict[str, Any]]]:
    """
    Extrahuje všechny entity (Characters a Locations) z API.

    Returns:
        Dictionary s klíči 'characters' a 'locations' obsahující stažená data.
    """
    logger.info("Zahájení kompletní extrakce dat z Rick & Morty API")

    locations: list[dict[str, Any]] = extract_locations()
    characters: list[dict[str, Any]] = extract_characters()

    logger.info(
        f"Kompletní extrakce dokončena: {len(characters)} postav, {len(locations)} lokací"
    )

    return {
        "characters": characters,
        "locations": locations
    }
