"""
Hlavní orchestrátor pro EL (Extract & Load) pipeline.

Tento modul koordinuje celý proces:
1. Inicializace loggingu
2. Extrakce dat z Rick & Morty API
3. Validace extrahovaných dat s detekcí anomálií a duplicit
4. Načtení dat do SQLite databáze s detekcí duplicit
5. Reportování výsledků včetně anomálií a duplicit

Tento soubor slouží jako entry point pro spuštění celého EL procesu.
"""

import logging
import sys
from pathlib import Path
from typing import Any

from extractor import extract_all_data
from loader import (
    LoadResult,
    close_connection,
    detect_duplicate_names,
    detect_orphaned_characters,
    get_record_counts,
    initialize_database,
    load_all_data,
)
from validator import get_validation_summary, validate_all_data

# Konfigurace loggingu
LOG_FORMAT: str = (
    "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
)
LOG_DATE_FORMAT: str = "%Y-%m-%d %H:%M:%S"


def setup_logging(log_level: int = logging.INFO, log_file: Path | None = None) -> None:
    """
    Nastaví konfiguraci loggingu pro celou aplikaci.

    Logování je směrováno na stdout s definovaným formátem.
    Volitelně lze přidat i file handler pro perzistentní logy.

    Args:
        log_level: Úroveň loggingu (výchozí INFO).
        log_file: Cesta k souboru pro uložení logů (volitelné).
    """
    # Vytvoření loggeru
    root_logger: logging.Logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Vyčištění existujících handlerů
    root_logger.handlers.clear()

    # Formátování
    formatter: logging.Formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)

    # Console handler
    console_handler: logging.StreamHandler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler (volitelný)
    if log_file is not None:
        try:
            file_handler: logging.FileHandler = logging.FileHandler(
                str(log_file), encoding="utf-8"
            )
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)
            logging.getLogger(__name__).info(f"Logování do souboru: {log_file}")
        except (IOError, OSError) as e:
            logging.getLogger(__name__).warning(f"Nelze vytvořit log soubor {log_file}: {e}")

    logger: logging.Logger = logging.getLogger(__name__)
    logger.info("Logging inicializován s úrovní %s", logging.getLevelName(log_level))


def _check_data_completeness(summary: dict[str, Any]) -> None:
    """
    Kontroluje, zda byla extrahována očekávaná data.

    Args:
        summary: Dictionary se shrnutím validace.
    """
    logger: logging.Logger = logging.getLogger(__name__)
    
    expected_characters: int = 800  # Approximální očekávaný počet
    expected_locations: int = 125
    
    actual_characters: int = summary['total_characters']
    actual_locations: int = summary['total_locations']
    
    character_completeness: float = actual_characters / expected_characters if expected_characters > 0 else 0
    location_completeness: float = actual_locations / expected_locations if expected_locations > 0 else 0
    
    logger.info(f"Completeness: Characters {character_completeness:.1%} ({actual_characters}/{expected_characters}), Locations {location_completeness:.1%} ({actual_locations}/{expected_locations})")
    
    if character_completeness < 0.8:
        logger.warning(f"Nízká completeness postav: {actual_characters}/{expected_characters} ({character_completeness:.1%})")
    if location_completeness < 0.8:
        logger.warning(f"Nízká completeness lokací: {actual_locations}/{expected_locations} ({location_completeness:.1%})")


def report_validation_summary(summary: dict[str, Any]) -> None:
    """
    Vypíše shrnutí validace dat včetně detekovaných anomálií.

    Args:
        summary: Dictionary se shrnutím validace.
    """
    logger: logging.Logger = logging.getLogger(__name__)

    logger.info("-" * 60)
    logger.info("SHRNUTÍ VALIDACE DAT")
    logger.info("-" * 60)
    logger.info(f"Celkem postav: {summary['total_characters']}")
    logger.info(f"Celkem lokací: {summary['total_locations']}")
    logger.info(f"Postavy s 'unknown' status: {summary['characters_with_unknown_status']}")
    logger.info(f"Postavy s 'unknown' species: {summary['characters_with_unknown_species']}")
    logger.info(f"Postavy bez location URL: {summary['characters_without_location']}")
    logger.info(f"Lokace s 'unknown' dimension: {summary['locations_with_unknown_dimension']}")
    logger.info("-" * 60)

    # Kontrola completeness dat
    _check_data_completeness(summary)

    # Varování pokud je vysoký počet anomálií
    if summary['characters_with_unknown_status'] > 50:
        logger.warning(
            f"Vysoký počet postav s 'unknown' status: "
            f"{summary['characters_with_unknown_status']} ({summary['characters_with_unknown_status'] * 100 // max(summary['total_characters'], 1)}%)"
        )
    if summary['locations_with_unknown_dimension'] > 20:
        logger.warning(
            f"Vysoký počet lokací s 'unknown' dimension: "
            f"{summary['locations_with_unknown_dimension']} ({summary['locations_with_unknown_dimension'] * 100 // max(summary['total_locations'], 1)}%)"
        )


def report_load_results(
    locations_result: LoadResult,
    characters_result: LoadResult
) -> None:
    """
    Vypíše výsledky nahrávání dat do databáze.

    Args:
        locations_result: Výsledek nahrávání lokací.
        characters_result: Výsledek nahrávání postav.
    """
    logger: logging.Logger = logging.getLogger(__name__)

    logger.info("-" * 60)
    logger.info("VÝSLEDKY NAHRÁVÁNÍ DO DATABÁZE")
    logger.info("-" * 60)

    logger.info("LOKACE:")
    logger.info(f"  - Nově vloženo: {locations_result.inserted}")
    logger.info(f"  - Preskočeno (duplicitní): {locations_result.skipped_duplicates}")
    logger.info(f"  - Chyby: {locations_result.errors}")
    if locations_result.duplicate_ids:
        logger.info(
            f"  - Duplicitní ID: {locations_result.duplicate_ids[:10]}..."
            if len(locations_result.duplicate_ids) > 10
            else f"  - Duplicitní ID: {locations_result.duplicate_ids}"
        )

    logger.info("POSTAVY:")
    logger.info(f"  - Nově vloženo: {characters_result.inserted}")
    logger.info(f"  - Preskočeno (duplicitní): {characters_result.skipped_duplicates}")
    logger.info(f"  - Chyby: {characters_result.errors}")
    if characters_result.duplicate_ids:
        logger.info(
            f"  - Duplicitní ID: {characters_result.duplicate_ids[:10]}..."
            if len(characters_result.duplicate_ids) > 10
            else f"  - Duplicitní ID: {characters_result.duplicate_ids}"
        )

    logger.info("-" * 60)


def report_database_integrity(connection: Any) -> None:
    """
    Vypíše report o integritě databáze.

    Detekuje orphaned records a duplicity podle jména.

    Args:
        connection: SQLite connection objekt.
    """
    logger: logging.Logger = logging.getLogger(__name__)

    logger.info("-" * 60)
    logger.info("KONTROLA INTEGRITY DATABÁZE")
    logger.info("-" * 60)

    # Detekce postav s neexistující lokací
    orphaned: list[dict[str, Any]] = detect_orphaned_characters(connection)
    if orphaned:
        logger.warning(f"Detekováno {len(orphaned)} postav s neexistující lokací:")
        for record in orphaned[:5]:
            logger.warning(f"  - Postava ID={record['id']} ({record['name']}): location_id={record['location_id']}")
        if len(orphaned) > 5:
            logger.warning(f"  ... a dalších {len(orphaned) - 5}")
    else:
        logger.info("Všechny postavy mají validní odkaz na lokaci")

    # Detekce duplicitních jmen
    duplicates: dict[str, list[dict[str, Any]]] = detect_duplicate_names(connection)

    if duplicates["locations"]:
        logger.info(f"Duplicitní jména lokací ({len(duplicates['locations'])}):")
        for dup in duplicates["locations"][:5]:
            logger.info(f"  - '{dup['name']}': {dup['count']} výskytů")
    else:
        logger.info("Žádná duplicitní jména lokací")

    if duplicates["characters"]:
        logger.info(f"Duplicitní jména postav ({len(duplicates['characters'])}):")
        for dup in duplicates["characters"][:5]:
            logger.info(f"  - '{dup['name']}': {dup['count']} výskytů")
    else:
        logger.info("Žádná duplicitní jména postav")

    logger.info("-" * 60)


def run_el_pipeline() -> bool:
    """
    Spustí kompletní EL (Extract & Load) pipeline.

    Provede:
    1. Extrakci dat z Rick & Morty API (Characters, Locations)
    2. Validaci extrahovaných dat s detekcí anomálií a duplicit
    3. Inicializaci SQLite databáze
    4. Načtení validovaných dat do databáze s detekcí duplicit
    5. Kontrolu integrity databáze

    Returns:
        True pokud pipeline proběhla úspěšně, False při chybě.
    """
    logger: logging.Logger = logging.getLogger(__name__)

    logger.info("=" * 60)
    logger.info("Zahájení EL pipeline pro Rick & Morty data")
    logger.info("=" * 60)

    connection = None

    try:
        # Krok 1: Extrakce dat z API
        logger.info("KROK 1/4: Extrakce dat z Rick & Morty API")
        logger.info("-" * 60)
        raw_data: dict[str, list[dict]] = extract_all_data()

        if not raw_data.get("characters") and not raw_data.get("locations"):
            logger.error("Extrakce nevrátila žádná data - pipeline přerušena")
            return False

        # Krok 2: Validace dat
        logger.info("KROK 2/4: Validace extrahovaných dat")
        logger.info("-" * 60)
        validated_data: dict[str, list[dict]] = validate_all_data(raw_data)

        # Report validace
        validation_summary: dict[str, Any] = get_validation_summary(validated_data)
        report_validation_summary(validation_summary)

        # Krok 3: Načtení do databáze
        logger.info("KROK 3/4: Načítání dat do SQLite databáze")
        logger.info("-" * 60)
        connection = initialize_database()

        load_results: dict[str, LoadResult] = load_all_data(connection, validated_data)

        # Report výsledků nahrávání
        report_load_results(
            load_results["locations"],
            load_results["characters"]
        )

        # Krok 4: Kontrola integrity
        logger.info("KROK 4/4: Kontrola integrity databáze")
        logger.info("-" * 60)
        report_database_integrity(connection)

        # Výpis finálních statistik
        final_counts: dict[str, int] = get_record_counts(connection)
        logger.info("=" * 60)
        logger.info("EL PIPELINE ÚSPĚŠNĚ DOKONČENA")
        logger.info("=" * 60)
        logger.info("FINÁLNÍ POČTY ZÁZNAMŮ V DATABÁZI:")
        logger.info(f"  - Lokace: {final_counts['locations']}")
        logger.info(f"  - Postavy: {final_counts['characters']}")
        logger.info(f"  - Celkem: {final_counts['locations'] + final_counts['characters']}")
        logger.info("=" * 60)

        return True

    except Exception as e:
        logger.exception(f"Kritická chyba v EL pipeline: {e}")
        return False

    finally:
        if connection is not None:
            close_connection(connection)


def main() -> int:
    """
    Entry point pro spuštění EL pipeline.

    Nastaví logging, spustí pipeline a vrátí exit code.

    Returns:
        0 při úspěchu, 1 při chybě.
    """
    # Volitelné: uložení logů do souboru
    log_file: Path | None = Path(__file__).parent / "el_pipeline.log"

    setup_logging(logging.INFO, log_file=log_file)

    logger: logging.Logger = logging.getLogger(__name__)
    logger.info(f"Spuštění z adresáře: {Path.cwd()}")
    logger.info(f"Verze Pythonu: {sys.version}")

    success: bool = run_el_pipeline()

    if success:
        logger.info("Script ukončen úspěšně")
        return 0
    else:
        logger.error("Script ukončen s chybou")
        return 1


if __name__ == "__main__":
    exit_code: int = main()
    sys.exit(exit_code)
