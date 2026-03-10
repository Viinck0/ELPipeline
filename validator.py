"""
Validator module pro kontrolu kvality dat a detekci anomálií.

Tento modul zajišťuje:
- Detekci sémantických anomálií (hodnoty "unknown" v kritických polích)
- Detekci duplicitních záznamů podle ID
- Validaci relačních odkazů (URL na lokace)
- Kontrolu referenční integrity mezi postavami a lokacemi
- Logování varování a informací o nalezených anomáliích
- Filtraci nevalidních záznamů před načtením do databáze

Bezpečnostní opatření:
- Detekce duplicit zabraňuje nekonzistenci dat
- Validace URL chrání před nevalidními foreign key odkazy
"""

import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Hodnoty považované za sémantické anomálie
UNKNOWN_VALUES: frozenset[str] = frozenset({"unknown", "Unknown", "UNKNOWN"})

# Prázdné řetězce jsou také považovány za anomálii, ale pouze v určitých polích
EMPTY_VALUE_FIELDS: frozenset[str] = frozenset({"status", "species", "name"})

# Pole, která by neměla obsahovat "unknown" hodnoty
CRITICAL_FIELDS: frozenset[str] = frozenset({"status", "species", "dimension"})

# Rozšířená pole pro kontrolu anomálií
EXTENDED_CRITICAL_FIELDS: frozenset[str] = frozenset({
    "status", "species", "dimension", "type", "gender", "origin"
})

# Regex pattern pro extrakci ID z URL
URL_ID_PATTERN: re.Pattern[str] = re.compile(r"/(\d+)$")


@dataclass
class ValidationResult:
    """
    Třída pro uchování výsledků validace.

    Umožňuje detailní reportování anomálií a duplicit.
    """
    total_records: int = 0
    valid_records: int = 0
    duplicate_ids: list[int] = field(default_factory=list)
    semantic_anomalies: list[dict[str, Any]] = field(default_factory=list)
    missing_references: list[dict[str, Any]] = field(default_factory=list)
    invalid_records: list[dict[str, Any]] = field(default_factory=list)


def validate_characters(
    characters: list[dict[str, Any]],
    valid_location_ids: set[int] | None = None
) -> list[dict[str, Any]]:
    """
    Validuje seznam postav a detekuje anomálie.

    Kontroluje:
    - Duplicitní ID záznamů
    - Hodnoty "unknown" v polích status, species, gender
    - Validitu location URL odkazů
    - Referenční integritu (zda odkazovaná lokace existuje)

    Args:
        characters: List postav k validaci.
        valid_location_ids: Množina validních ID lokací pro kontrolu integrity.

    Returns:
        List validních postav (včetně těch s anomáliemi, které jsou pouze logovány).
    """
    logger.info(f"Zahájení validace {len(characters)} postav")

    result: ValidationResult = ValidationResult(total_records=len(characters))

    # Detekce duplicitních ID
    id_counts: Counter = Counter(char.get("id") for char in characters if char.get("id"))
    duplicate_ids: list[int] = [id_ for id_, count in id_counts.items() if count > 1]

    if duplicate_ids:
        result.duplicate_ids = duplicate_ids
        logger.warning(
            f"Detekováno {len(duplicate_ids)} duplicitních ID postav: {duplicate_ids[:10]}..."
            if len(duplicate_ids) > 10
            else f"Detekováno {len(duplicate_ids)} duplicitních ID postav: {duplicate_ids}"
        )

    # Odstranění duplicit - ponecháme první výskyt
    seen_ids: set[int] = set()
    unique_characters: list[dict[str, Any]] = []

    for character in characters:
        char_id: int | None = character.get("id")

        if char_id in seen_ids:
            logger.debug(f"Preskočena duplicitní postava ID={char_id}")
            continue

        if char_id is not None:
            seen_ids.add(char_id)
            unique_characters.append(character)

    # Validace každého záznamu
    valid_characters: list[dict[str, Any]] = []
    anomaly_count: int = 0
    missing_location_count: int = 0
    broken_reference_count: int = 0

    for character in unique_characters:
        if not _is_valid_record(character, "character", result):
            continue

        # Kontrola sémantických anomálií
        anomalies: list[str] = _check_semantic_anomalies(character, "character")
        anomaly_count += len(anomalies)

        for anomaly in anomalies:
            logger.warning(f"Postava ID={character.get('id')}: {anomaly}")
            result.semantic_anomalies.append({
                "type": "character",
                "id": character.get("id"),
                "name": character.get("name"),
                "anomaly": anomaly
            })

        # Validace location URL
        location_url: str | None = character.get("location", {}).get("url")
        location_id: int | None = _extract_location_id_from_url(location_url)

        if not _is_valid_location_url(location_url):
            missing_location_count += 1
            logger.info(
                f"Postava ID={character.get('id')} ({character.get('name')}): "
                f"chybějící nebo nevalidní location URL"
            )
            result.missing_references.append({
                "type": "character",
                "id": character.get("id"),
                "name": character.get("name"),
                "issue": "missing_location_url"
            })
        elif valid_location_ids is not None and location_id not in valid_location_ids:
            broken_reference_count += 1
            logger.warning(
                f"Postava ID={character.get('id')} odkazuje na neexistující lokaci ID={location_id}"
            )
            result.missing_references.append({
                "type": "character",
                "id": character.get("id"),
                "name": character.get("name"),
                "issue": "broken_reference",
                "location_id": location_id
            })

        valid_characters.append(character)

    result.valid_records = len(valid_characters)

    logger.info(
        f"Validace postav dokončena: {result.valid_records} validních z {result.total_records}, "
        f"{len(duplicate_ids)} duplicit, {anomaly_count} anomálií, "
        f"{missing_location_count} bez location URL, {broken_reference_count} s broken reference"
    )

    return valid_characters


def validate_locations(locations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Validuje seznam lokací a detekuje anomálie.

    Kontroluje:
    - Duplicitní ID záznamů
    - Hodnoty "unknown" v polích dimension, type
    - Prázdné nebo nevalidní názvy

    Args:
        locations: List lokací k validaci.

    Returns:
        List validních lokací (včetně těch s anomáliemi, které jsou pouze logovány).
    """
    logger.info(f"Zahájení validace {len(locations)} lokací")

    result: ValidationResult = ValidationResult(total_records=len(locations))

    # Detekce duplicitních ID
    id_counts: Counter = Counter(loc.get("id") for loc in locations if loc.get("id"))
    duplicate_ids: list[int] = [id_ for id_, count in id_counts.items() if count > 1]

    if duplicate_ids:
        result.duplicate_ids = duplicate_ids
        logger.warning(
            f"Detekováno {len(duplicate_ids)} duplicitních ID lokací: {duplicate_ids[:10]}..."
            if len(duplicate_ids) > 10
            else f"Detekováno {len(duplicate_ids)} duplicitních ID lokací: {duplicate_ids}"
        )

    # Odstranění duplicit - ponecháme první výskyt
    seen_ids: set[int] = set()
    unique_locations: list[dict[str, Any]] = []

    for location in locations:
        loc_id: int | None = location.get("id")

        if loc_id in seen_ids:
            logger.debug(f"Preskočena duplicitní lokace ID={loc_id}")
            continue

        if loc_id is not None:
            seen_ids.add(loc_id)
            unique_locations.append(location)

    # Validace každého záznamu
    valid_locations: list[dict[str, Any]] = []
    anomaly_count: int = 0

    for location in unique_locations:
        if not _is_valid_record(location, "location", result):
            continue

        # Kontrola sémantických anomálií
        anomalies: list[str] = _check_semantic_anomalies(location, "location")
        anomaly_count += len(anomalies)

        for anomaly in anomalies:
            logger.warning(f"Lokace ID={location.get('id')}: {anomaly}")
            result.semantic_anomalies.append({
                "type": "location",
                "id": location.get("id"),
                "name": location.get("name"),
                "anomaly": anomaly
            })

        valid_locations.append(location)

    result.valid_records = len(valid_locations)

    logger.info(
        f"Validace lokací dokončena: {result.valid_records} validních z {result.total_records}, "
        f"{len(duplicate_ids)} duplicit, {anomaly_count} anomálií"
    )

    return valid_locations


def validate_all_data(data: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    """
    Validuje všechna extrahovaná data s kontrolou referenční integrity.

    Nejprve validuje lokace, poté postavy s kontrolou odkazů na lokace.

    Args:
        data: Dictionary s klíči 'characters' a 'locations'.

    Returns:
        Dictionary s validovanými daty.
    """
    logger.info("Zahájení kompletní validace dat")

    characters: list[dict[str, Any]] = data.get("characters", [])
    locations: list[dict[str, Any]] = data.get("locations", [])

    # Nejprve validujeme lokace abychom získali množinu validních ID
    validated_locations: list[dict[str, Any]] = validate_locations(locations)
    valid_location_ids: set[int] = {
        loc.get("id") for loc in validated_locations if loc.get("id") is not None
    }

    logger.info(f"Množina validních ID lokací: {len(valid_location_ids)} záznamů")

    # Poté validujeme postavy s kontrolou referenční integrity
    validated_characters: list[dict[str, Any]] = validate_characters(
        characters, valid_location_ids
    )

    logger.info("Kompletní validace dat dokončena")

    return {
        "characters": validated_characters,
        "locations": validated_locations
    }


def _is_valid_record(
    record: dict[str, Any],
    record_type: str,
    result: ValidationResult | None = None
) -> bool:
    """
    Kontroluje, zda záznam má požadovaná pole.

    Args:
        record: Záznam k validaci.
        record_type: Typ záznamu pro logování.
        result: ValidationResult objekt pro trackování invalidních záznamů.

    Returns:
        True pokud je záznam validní, False jinak.
    """
    if not isinstance(record, dict):
        logger.error(f"Nevalidní typ záznamu {record_type}: očekáván dict, dostán {type(record)}")
        if result is not None:
            result.invalid_records.append({
                "type": record_type,
                "error": f"invalid_type: {type(record)}",
                "record": str(record)[:100]
            })
        return False

    if "id" not in record:
        logger.error(f"Záznam {record_type} chybí povinné pole 'id': {record}")
        if result is not None:
            result.invalid_records.append({
                "type": record_type,
                "error": "missing_id",
                "record": str(record)[:100]
            })
        return False

    if "name" not in record:
        logger.warning(f"Záznam {record_type} ID={record.get('id')} chybí pole 'name'")

    return True


def _check_semantic_anomalies(record: dict[str, Any], record_type: str) -> list[str]:
    """
    Detekuje sémantické anomálie v kritických polích záznamu.

    Hledá hodnoty "unknown" v polích jako status, species, dimension.
    Kontroluje také prázdné řetězce v kritických polích a podezřelé hodnoty.

    Args:
        record: Záznam ke kontrole.
        record_type: Typ záznamu pro logování.

    Returns:
        List nalezených anomálií.
    """
    anomalies: list[str] = []

    # Výběr polí pro kontrolu podle typu záznamu
    fields_to_check: frozenset[str] = (
        EXTENDED_CRITICAL_FIELDS if record_type == "character" else CRITICAL_FIELDS
    )

    for field in fields_to_check:
        value: Any = record.get(field)

        if value is None:
            continue

        if not isinstance(value, str):
            # Pro location je field v některých případech objekt s 'location' klíčem
            continue

        # Kontrola na "unknown" hodnoty (nepoužíváme pro type a gender - tam je "" běžné)
        if value.lower() in {v.lower() for v in UNKNOWN_VALUES}:
            anomalies.append(f"pole '{field}' obsahuje 'unknown' hodnotu")

        # Kontrola prázdného řetězce pouze v kritických polích (status, species, name)
        if value == "" and field in EMPTY_VALUE_FIELDS:
            anomalies.append(f"pole '{field}' je prázdné")

        # Kontrola na podezřelé hodnoty (příliš dlouhé, speciální znaky)
        if len(value) > 500:
            anomalies.append(f"pole '{field}' má podezřele dlouhou hodnotu ({len(value)} znaků)")

    return anomalies


def _is_valid_location_url(url: str | None) -> bool:
    """
    Validuje URL odkaz na lokaci.

    Kontroluje, zda URL není prázdná a má očekávaný formát.

    Args:
        url: URL k validaci.

    Returns:
        True pokud je URL validní, False jinak.
    """
    if url is None or url == "":
        return False

    if not isinstance(url, str):
        return False

    # Kontrola formátu URL
    if not url.startswith("https://rickandmortyapi.com/api/location/"):
        logger.debug(f"Neznámý formát location URL: {url}")
        return False

    # Kontrola, že URL končí číslem
    match: re.Match[str] | None = URL_ID_PATTERN.search(url)
    if match is None:
        logger.debug(f"Location URL neobsahuje validní ID: {url}")
        return False

    return True


def _extract_location_id_from_url(url: str | None) -> int | None:
    """
    Extrahuje integer ID z location URL.

    Např. "https://rickandmortyapi.com/api/location/3" -> 3

    Args:
        url: URL odkaz na lokaci.

    Returns:
        Integer ID pokud je URL validní, None jinak.
    """
    if not _is_valid_location_url(url):
        return None

    match: re.Match[str] | None = URL_ID_PATTERN.search(url)
    if match is None:
        return None

    try:
        return int(match.group(1))
    except ValueError:
        logger.warning(f"Nevalidní ID v URL: {url}")
        return None


def get_validation_summary(data: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """
    Poskytne shrnutí validace dat.

    Args:
        data: Validovaná data.

    Returns:
        Dictionary se shrnutím statistik validace.
    """
    characters: list[dict[str, Any]] = data.get("characters", [])
    locations: list[dict[str, Any]] = data.get("locations", [])

    return {
        "total_characters": len(characters),
        "total_locations": len(locations),
        "characters_with_unknown_status": sum(
            1 for c in characters if c.get("status", "").lower() in {v.lower() for v in UNKNOWN_VALUES}
        ),
        "characters_with_unknown_species": sum(
            1 for c in characters if c.get("species", "").lower() in {v.lower() for v in UNKNOWN_VALUES}
        ),
        "characters_without_location": sum(
            1 for c in characters if not c.get("location", {}).get("url")
        ),
        "locations_with_unknown_dimension": sum(
            1 for l in locations if l.get("dimension", "").lower() in {v.lower() for v in UNKNOWN_VALUES}
        )
    }
