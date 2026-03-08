"""
Loader module pro inicializaci SQLite databáze a bezpečné vkládání dat.

Tento modul zajišťuje:
- Vytvoření relačního modelu s tabulkami locations a characters
- Foreign key vazby mezi tabulkami
- Detekci duplicit před vkládáním (kontrola existujících záznamů)
- Idempotentní vkládání pomocí INSERT OR IGNORE
- Transakční bezpečnost s rollback při chybě
- Ošetření SQL injection pomocí parameterized queries
- Detailní logování procesu vkládání

Bezpečnostní opatření:
- Parameterized queries chrání proti SQL injection
- INSERT OR IGNORE zajišťuje idempotenci
- Rollback při chybě zachovává integritu databáze
- Detekce duplicit umožňuje reportování konfliktů
"""

import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Cesta k databázovému souboru
DB_PATH: Path = Path(__file__).parent / "rick_and_morty.db"

# SQL schéma pro vytvoření tabulek
SCHEMA_SQL: str = """
-- Tabulka pro lokace
CREATE TABLE IF NOT EXISTS locations (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT,
    dimension TEXT
);

-- Tabulka pro postavy s foreign key vazbou na lokace
CREATE TABLE IF NOT EXISTS characters (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    species TEXT,
    status TEXT,
    location_id INTEGER,
    FOREIGN KEY (location_id) REFERENCES locations(id)
);

-- Indexy pro zlepšení výkonu dotazů
CREATE INDEX IF NOT EXISTS idx_characters_location_id ON characters(location_id);
CREATE INDEX IF NOT EXISTS idx_locations_name ON locations(name);
CREATE INDEX IF NOT EXISTS idx_characters_name ON characters(name);
"""


@dataclass
class LoadResult:
    """
    Třída pro uchování výsledků načítání dat.

    Umožňuje detailní reportování úspěšných a neúspěšných operací.
    """
    inserted: int = 0
    skipped_duplicates: int = 0
    errors: int = 0
    duplicate_ids: list[int] = field(default_factory=list)


def initialize_database(db_path: Path | None = None) -> sqlite3.Connection:
    """
    Inicializuje SQLite databázi s požadovaným schématem.

    Vytvoří tabulky locations a characters s foreign key vazbami.
    Pokud databáze již existuje, pouze se připojí a ověří schéma.

    Args:
        db_path: Cesta k databázovému souboru. Pokud None, použije se výchozí.

    Returns:
        SQLite connection objekt s povolenými foreign keys.
    """
    path: Path = db_path if db_path is not None else DB_PATH

    logger.info(f"Inicializace databáze: {path.absolute()}")

    try:
        connection: sqlite3.Connection = sqlite3.connect(str(path))
        connection.row_factory = sqlite3.Row

        # Povolení foreign key constraints
        connection.execute("PRAGMA foreign_keys = ON")

        # Vytvoření tabulek
        connection.executescript(SCHEMA_SQL)
        connection.commit()

        # Logování existujících záznamů
        counts: dict[str, int] = get_record_counts(connection)
        if counts["locations"] > 0 or counts["characters"] > 0:
            logger.info(
                f"Databáze již obsahuje data: {counts['locations']} lokací, "
                f"{counts['characters']} postav"
            )

        logger.info(f"Databáze úspěšně inicializována: {path.name}")
        return connection

    except sqlite3.Error as e:
        logger.exception(f"Chyba při inicializaci databáze: {e}")
        raise


def detect_existing_ids(
    connection: sqlite3.Connection,
    table_name: str,
    incoming_ids: set[int]
) -> set[int]:
    """
    Detekuje ID, která již existují v databázi.

    Umožňuje identifikovat duplicity před vkládáním.

    Args:
        connection: SQLite connection objekt.
        table_name: Název tabulky pro kontrolu.
        incoming_ids: Množina ID která budou vkládána.

    Returns:
        Množina ID která již existují v databázi.
    """
    if not incoming_ids:
        return set()

    try:
        cursor: sqlite3.Cursor = connection.cursor()

        # Vytvoření placeholderů pro SQL query
        placeholders: str = ",".join("?" for _ in incoming_ids)
        query: str = f"SELECT id FROM {table_name} WHERE id IN ({placeholders})"

        cursor.execute(query, list(incoming_ids))
        existing_ids: set[int] = {row["id"] for row in cursor.fetchall()}

        if existing_ids:
            logger.info(
                f"Detekováno {len(existing_ids)} existujících záznamů v tabulce '{table_name}': "
                f"{sorted(existing_ids)[:10]}..."
                if len(existing_ids) > 10
                else f"Detekováno {len(existing_ids)} existujících záznamů v tabulce '{table_name}': {sorted(existing_ids)}"
            )

        return existing_ids

    except sqlite3.Error as e:
        logger.error(f"Chyba při detekci existujících ID v tabulce '{table_name}': {e}")
        return set()


def load_locations(
    connection: sqlite3.Connection,
    locations: list[dict[str, Any]]
) -> LoadResult:
    """
    Nahraje lokace do databázové tabulky.

    Detekuje duplicity před vkládáním a reportuje je.
    Používá INSERT OR IGNORE pro idempotentní vkládání.
    Při chybě provede rollback celé transakce.

    Args:
        connection: SQLite connection objekt.
        locations: List lokací k nahrání.

    Returns:
        LoadResult s počty úspěšných a přeskočených záznamů.
    """
    logger.info(f"Nahrávání {len(locations)} lokací do databáze")

    result: LoadResult = LoadResult()
    insert_sql: str = """
        INSERT OR IGNORE INTO locations (id, name, type, dimension)
        VALUES (?, ?, ?, ?)
    """

    try:
        cursor: sqlite3.Cursor = connection.cursor()

        # Detekce existujících ID
        incoming_ids: set[int] = {loc.get("id") for loc in locations if loc.get("id") is not None}
        existing_ids: set[int] = detect_existing_ids(connection, "locations", incoming_ids)
        result.duplicate_ids = list(existing_ids)
        result.skipped_duplicates = len(existing_ids)

        # Vkládání záznamů
        for location in locations:
            try:
                location_id: int = location.get("id")
                name: str = location.get("name", "Unknown")
                loc_type: str | None = location.get("type")
                dimension: str | None = location.get("dimension")

                cursor.execute(insert_sql, (location_id, name, loc_type, dimension))

                if location_id in existing_ids:
                    logger.debug(f"Lokace ID={location_id} již existuje, přeskočeno")
                else:
                    result.inserted += 1

            except (TypeError, ValueError) as e:
                result.errors += 1
                logger.warning(f"Nevalidní data pro lokaci ID={location.get('id')}: {e}")
                continue

        connection.commit()
        logger.info(
            f"Nahrávání lokací dokončeno: {result.inserted} nových, "
            f"{result.skipped_duplicates} duplicit, {result.errors} chyb"
        )

    except sqlite3.Error as e:
        logger.exception(f"Chyba při nahrávání lokací: {e}")
        connection.rollback()
        logger.warning("Proveden rollback transakce pro lokace")
        raise

    return result


def load_characters(
    connection: sqlite3.Connection,
    characters: list[dict[str, Any]]
) -> LoadResult:
    """
    Nahraje postavy do databázové tabulky.

    Extrahuje location_id z URL odkazu. Pokud URL chybí, uloží NULL.
    Detekuje duplicity před vkládáním a reportuje je.
    Používá INSERT OR IGNORE pro idempotentní vkládání.
    Při chybě provede rollback celé transakce.

    Args:
        connection: SQLite connection objekt.
        characters: List postav k nahrání.

    Returns:
        LoadResult s počty úspěšných a přeskočených záznamů.
    """
    logger.info(f"Nahrávání {len(characters)} postav do databáze")

    result: LoadResult = LoadResult()
    insert_sql: str = """
        INSERT OR IGNORE INTO characters (id, name, species, status, location_id)
        VALUES (?, ?, ?, ?, ?)
    """

    null_location_count: int = 0

    try:
        cursor: sqlite3.Cursor = connection.cursor()

        # Detekce existujících ID
        incoming_ids: set[int] = {
            char.get("id") for char in characters if char.get("id") is not None
        }
        existing_ids: set[int] = detect_existing_ids(connection, "characters", incoming_ids)
        result.duplicate_ids = list(existing_ids)
        result.skipped_duplicates = len(existing_ids)

        # Vkládání záznamů
        for character in characters:
            try:
                char_id: int = character.get("id")
                name: str = character.get("name", "Unknown")
                species: str | None = character.get("species")
                status: str | None = character.get("status")

                # Extrakce location_id z URL
                location_url: str | None = character.get("location", {}).get("url")
                location_id: int | None = _extract_location_id(location_url)

                if location_id is None:
                    null_location_count += 1

                cursor.execute(insert_sql, (char_id, name, species, status, location_id))

                if char_id in existing_ids:
                    logger.debug(f"Postava ID={char_id} již existuje, přeskočeno")
                else:
                    result.inserted += 1

            except (TypeError, ValueError) as e:
                result.errors += 1
                logger.warning(f"Nevalidní data pro postavu ID={character.get('id')}: {e}")
                continue

        connection.commit()
        logger.info(
            f"Nahrávání postav dokončeno: {result.inserted} nových, "
            f"{result.skipped_duplicates} duplicit, {result.errors} chyb, "
            f"{null_location_count} bez validní lokace"
        )

    except sqlite3.Error as e:
        logger.exception(f"Chyba při nahrávání postav: {e}")
        connection.rollback()
        logger.warning("Proveden rollback transakce pro postavy")
        raise

    return result


def load_all_data(
    connection: sqlite3.Connection,
    data: dict[str, list[dict[str, Any]]]
) -> dict[str, LoadResult]:
    """
    Nahraje všechna validovaná data do databáze.

    Nejprve nahraje lokace (kvůli foreign key vazbě), poté postavy.

    Args:
        connection: SQLite connection objekt.
        data: Dictionary s klíči 'characters' a 'locations'.

    Returns:
        Dictionary s výsledky nahrání pro každou entitu.
    """
    logger.info("Zahájení nahrávání všech dat do databáze")

    locations: list[dict[str, Any]] = data.get("locations", [])
    characters: list[dict[str, Any]] = data.get("characters", [])

    # Nejprve nahrajeme lokace (kvůli FK vazbě)
    locations_result: LoadResult = load_locations(connection, locations)

    # Poté nahrajeme postavy
    characters_result: LoadResult = load_characters(connection, characters)

    logger.info(
        f"Nahrávání dat dokončeno: "
        f"{locations_result.inserted} nových lokací ({locations_result.skipped_duplicates} duplicit), "
        f"{characters_result.inserted} nových postav ({characters_result.skipped_duplicates} duplicit)"
    )

    return {
        "locations": locations_result,
        "characters": characters_result
    }


def _extract_location_id(url: str | None) -> int | None:
    """
    Extrahuje integer ID z location URL.

    Např. "https://rickandmortyapi.com/api/location/3" -> 3
    Pokud URL chybí nebo je nevalidní, vrací None.

    Args:
        url: URL odkaz na lokaci.

    Returns:
        Integer ID pokud je URL validní, None jinak.
    """
    if url is None or url == "":
        return None

    if not isinstance(url, str):
        return None

    # Očekávaný formát: https://rickandmortyapi.com/api/location/{id}
    prefix: str = "https://rickandmortyapi.com/api/location/"
    if not url.startswith(prefix):
        logger.debug(f"Neznámý formát location URL: {url}")
        return None

    # Extrakce ID z konce URL
    id_part: str = url[len(prefix):]

    try:
        return int(id_part)
    except ValueError:
        logger.warning(f"Nevalidní ID v location URL: {url}")
        return None


def get_record_counts(connection: sqlite3.Connection) -> dict[str, int]:
    """
    Získá počty záznamů v jednotlivých tabulkách.

    Args:
        connection: SQLite connection objekt.

    Returns:
        Dictionary s počty záznamů pro každou tabulku.
    """
    try:
        cursor: sqlite3.Cursor = connection.cursor()

        cursor.execute("SELECT COUNT(*) FROM locations")
        locations_count: int = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM characters")
        characters_count: int = cursor.fetchone()[0]

        return {
            "locations": locations_count,
            "characters": characters_count
        }

    except sqlite3.Error as e:
        logger.exception(f"Chyba při získávání počtů záznamů: {e}")
        return {"locations": 0, "characters": 0}


def detect_orphaned_characters(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    """
    Detekuje postavy s odkazem na neexistující lokaci.

    Identifikuje problémy s referenční integritou.

    Args:
        connection: SQLite connection objekt.

    Returns:
        List postav s neexistující lokací.
    """
    try:
        cursor: sqlite3.Cursor = connection.cursor()

        query: str = """
            SELECT c.id, c.name, c.location_id
            FROM characters c
            LEFT JOIN locations l ON c.location_id = l.id
            WHERE c.location_id IS NOT NULL AND l.id IS NULL
        """

        cursor.execute(query)
        orphaned: list[dict[str, Any]] = [
            {"id": row["id"], "name": row["name"], "location_id": row["location_id"]}
            for row in cursor.fetchall()
        ]

        if orphaned:
            logger.warning(f"Detekováno {len(orphaned)} postav s neexistující lokací")

        return orphaned

    except sqlite3.Error as e:
        logger.exception(f"Chyba při detekci orphaned characters: {e}")
        return []


def detect_duplicate_names(connection: sqlite3.Connection) -> dict[str, list[dict[str, Any]]]:
    """
    Detekuje duplicity podle jména (nikoliv podle ID).

    Umožňuje identifikovat potenciální problémy s daty.

    Args:
        connection: SQLite connection objekt.

    Returns:
        Dictionary s duplicitními jmény pro každou tabulku.
    """
    try:
        cursor: sqlite3.Cursor = connection.cursor()
        duplicates: dict[str, list[dict[str, Any]]] = {"locations": [], "characters": []}

        # Detekce duplicitních jmen lokací
        cursor.execute("""
            SELECT name, COUNT(*) as cnt
            FROM locations
            GROUP BY name
            HAVING cnt > 1
        """)
        duplicates["locations"] = [
            {"name": row["name"], "count": row["cnt"]}
            for row in cursor.fetchall()
        ]

        # Detekce duplicitních jmen postav
        cursor.execute("""
            SELECT name, COUNT(*) as cnt
            FROM characters
            GROUP BY name
            HAVING cnt > 1
        """)
        duplicates["characters"] = [
            {"name": row["name"], "count": row["cnt"]}
            for row in cursor.fetchall()
        ]

        total_duplicates: int = (
            len(duplicates["locations"]) + len(duplicates["characters"])
        )
        if total_duplicates > 0:
            logger.info(
                f"Detekováno {len(duplicates['locations'])} duplicitních jmen lokací "
                f"a {len(duplicates['characters'])} duplicitních jmen postav"
            )

        return duplicates

    except sqlite3.Error as e:
        logger.exception(f"Chyba při detekci duplicitních jmen: {e}")
        return {"locations": [], "characters": []}


def close_connection(connection: sqlite3.Connection) -> None:
    """
    Bezpečně uzavře SQLite connection.

    Args:
        connection: SQLite connection objekt k uzavření.
    """
    try:
        connection.close()
        logger.info("Databázové připojení uzavřeno")
    except sqlite3.Error as e:
        logger.warning(f"Chyba při uzavírání připojení: {e}")
