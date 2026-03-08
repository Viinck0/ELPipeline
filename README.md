# Rick & Morty EL Pipeline

Extrakční a načítací (Extract & Load) pipeline pro stahování dat z **Rick & Morty API** a jejich ukládání do **SQLite databáze**.

## 📋 Obsah

- [Funkce](#funkce)
- [Architektura](#architektura)
- [Transformační Diagram](#transformační-diagram)
- [Požadavky](#požadavky)
- [Instalace](#instalace)
- [Použití](#použití)
- [Struktura databáze](#struktura-databáze)
- [Konfigurace](#konfigurace)
- [Logování](#logování)
- [Příklady výstupu](#příklady-výstupu)
- [Řešení problémů](#řešení-problémů)
- [Testování](#testování)

---

## 🚀 Funkce

### Extrakce dat
- **Paginace**: Automatické procházení všech stránek API pomocí `while` cyklu
- **Rate Limiting**: Zpoždění 0.2s mezi požadavky na ochranu externího serveru
- **Graceful Degradation**: Uložení extrahovaných dat i při chybě sítě
- **Robustní error handling**: Ošetření timeoutů, výpadků připojení a HTTP chyb

### Validace dat
- **Detekce duplicit**: Identifikace duplicitních ID v extrahovaných datech
- **Sémantické anomálie**: Detekce hodnot "unknown" v kritických polích
- **Validace referencí**: Kontrola platnosti URL odkazů na lokace
- **Referenční integrita**: Ověření, že odkazované lokace existují

### Načítání do databáze
- **Idempotence**: Opakované spuštění nevytváří duplicity (`INSERT OR IGNORE`)
- **Transakční bezpečnost**: Rollback při chybě zachovává integritu databáze
- **Foreign Key vazby**: Relační model s cizími klíči
- **Detekce konfliktů**: Reportování existujících záznamů před vkládáním

### Monitorování a logování
- **Detailní logy**: Každý krok pipeline je podrobně logován
- **Log do souboru**: Perzistentní záznam v `el_pipeline.log`
- **Reporty**: Shrnutí validace, výsledky nahrávání, kontrola integrity
- **Anomálie**: Varování pro podezřelá data

---

## 🏗️ Architektura

```
┌─────────────────────────────────────────────────────────────┐
│                         main.py                              │
│                    (Orchestrátor pipeline)                   │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│   extractor.py  │  │   validator.py  │  │    loader.py    │
│                 │  │                 │  │                 │
│ - API komunikace│  │ - Kontrola kvality│ │ - SQLite DB     │
│ - Paginace      │  │ - Detekce anomálií│ │ - INSERT/UPDATE │
│ - Rate limiting │  │ - Validace URL  │  │ - Transakce     │
│ - Error handling│  │ - Duplikáty     │  │ - FK vazby      │
└─────────────────┘  └─────────────────┘  └─────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │ rick_and_morty.db│
                    │   (SQLite DB)    │
                    └─────────────────┘
```

### Popis modulů

| Soubor | Popis |
|--------|-------|
| `main.py` | Hlavní orchestrátor, koordinuje celý EL proces |
| `extractor.py` | Komunikace s Rick & Morty API, extrakce dat |
| `validator.py` | Kontrola kvality dat, detekce anomálií a duplicit |
| `loader.py` | Inicializace DB, bezpečné vkládání dat |
| `requirements.txt` | Závislosti projektu |

---

## 📊 Transformační Diagram

Tento diagram znázorňuje tok dat od surové extrakce až po business-ready výstupy:

![schema](https://github.com/user-attachments/assets/fa4cd573-13f5-4b2a-99b9-88a2332bb1fb)

"Výše uvedený diagram pokrývá technickou EL a čistící vrstvu. Požadovaný Business-ready output (KPIs a analytické pohledy) je realizován formou předpřipravených analytických dotazů (viz ukázkové dotazy v tomto README), které slouží jako přímý podklad pro vizualizační nástroje (např. Grafana / PowerBI)."

---

## 📦 Požadavky

- **Python**: 3.10 nebo vyšší
- **Knihovny**:
  - `requests` (≥2.31.0) - HTTP komunikace s API

Žádné další externí závislosti nejsou vyžadovány. SQLite je součástí standardní knihovny Pythonu.

---

## 📥 Instalace

### 1. Klonování nebo stažení projektu

```bash
cd c:\Users\Vinci\Desktop\ukol2
```

### 2. Vytvoření virtuálního prostředí (doporučeno)

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux/Mac
python3 -m venv venv
source venv/bin/activate
```

### 3. Instalace závislostí

```bash
pip install -r requirements.txt
```

---

## ▶️ Použití

### Základní spuštění

```bash
python main.py
```

### Spuštění s vlastním logovacím souborem

Upravte `main.py` a změňte cestu k logu:

```python
log_file: Path = Path(__file__).parent / "vlastni_log.log"
```

### Spuštění s jinou úrovní logování

Pro detailnější ladící informace upravte `main.py`:

```python
setup_logging(logging.DEBUG, log_file=log_file)
```

Dostupné úrovně: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`

---

## 🗄️ Struktura databáze

### Tabulka `locations`

| Sloupec | Typ | Popis |
|---------|-----|-------|
| `id` | INTEGER | Primární klíč, ID lokace z API |
| `name` | TEXT | Název lokace (NOT NULL) |
| `type` | TEXT | Typ lokace (např. "Planet", "Dimension") |
| `dimension` | TEXT | Dimenze lokace |

### Tabulka `characters`

| Sloupec | Typ | Popis |
|---------|-----|-------|
| `id` | INTEGER | Primární klíč, ID postavy z API |
| `name` | TEXT | Jméno postavy (NOT NULL) |
| `species` | TEXT | Druh postavy |
| `status` | TEXT | Stav postavy ("Alive", "Dead", "unknown") |
| `location_id` | INTEGER | Foreign Key odkazující na `locations.id` |

### Indexy

Pro optimalizaci dotazů jsou vytvořeny následující indexy:

```sql
CREATE INDEX idx_characters_location_id ON characters(location_id);
CREATE INDEX idx_locations_name ON locations(name);
CREATE INDEX idx_characters_name ON characters(name);
```

### Relační schéma

```
┌─────────────┐         ┌──────────────┐
│  locations  │◄────────│  characters  │
├─────────────┤  1:N    ├──────────────┤
│ id (PK)     │         │ id (PK)      │
│ name        │         │ name         │
│ type        │         │ species      │
│ dimension   │         │ status       │
└─────────────┘         │ location_id  │
                        │ (FK)         │
                        └──────────────┘
```

---

## ⚙️ Konfigurace

### Konstanty v `extractor.py`

```python
BASE_URL: str = "https://rickandmortyapi.com/api"
RATE_LIMIT_DELAY: float = 0.2  # Zpoždění mezi requesty (sekundy)
REQUEST_TIMEOUT: int = 30      # Timeout pro HTTP requesty
```

### Konstanty v `validator.py`

```python
UNKNOWN_VALUES: frozenset[str] = frozenset({"unknown", "Unknown", "UNKNOWN", ""})
CRITICAL_FIELDS: frozenset[str] = frozenset({"status", "species", "dimension"})
EXTENDED_CRITICAL_FIELDS: frozenset[str] = frozenset({
    "status", "species", "dimension", "type", "gender", "origin"
})
```

### Konstanty v `loader.py`

```python
DB_PATH: Path = Path(__file__).parent / "rick_and_morty.db"
```

---

## 📝 Logování

### Formát logů

```
%(asctime)s | %(levelname)-8s | %(name)s | %(message)s
```

**Příklad:**
```
2026-03-08 22:23:40 | INFO     | extractor | Zahájení extrakce entity 'location'
2026-03-08 22:23:48 | WARNING  | validator | Postava ID=7: pole 'status' obsahuje 'unknown' hodnotu
2026-03-08 22:23:48 | INFO     | loader | Nahrávání lokací dokončeno: 126 nových, 0 duplicit
```

### Úrovně logování

| Úroveň | Popis | Kdy se používá |
|--------|-------|----------------|
| `INFO` | Běžné provozní zprávy | Zahájení/ukončení operací, počty záznamů |
| `WARNING` | Potenciální problémy | Anomálie v datech, chybějící reference |
| `ERROR` | Chyby | Selhání requestů, nevalidní data |
| `DEBUG` | Detailní informace | Preskočené duplicity, detaily validace |

### Výstup logů

- **Konzole (stdout)**: Všechny logy v reálném čase
- **Soubor**: `el_pipeline.log` pro perzistentní záznam

---

## 📊 Příklady výstupu

### Úspěšné spuštění

```
============================================================
Zahájení EL pipeline pro Rick & Morty data
============================================================
KROK 1/4: Extrakce dat z Rick & Morty API
------------------------------------------------------------
INFO | extractor | Zahájení kompletní extrakce dat z Rick & Morty API
INFO | extractor | Extrakce 'location' dokončena: celkem 126 záznamů
INFO | extractor | Extrakce 'character' dokončena: celkem 460 záznamů

KROK 2/4: Validace extrahovaných dat
------------------------------------------------------------
INFO | validator | Zahájení validace 126 lokací
WARNING | validator | Lokace ID=2: pole 'dimension' obsahuje 'unknown' hodnotu
INFO | validator | Validace lokací dokončena: 126 validních, 31 anomálií

INFO | validator | Zahájení validace 460 postav
WARNING | validator | Postava ID=7: pole 'status' obsahuje 'unknown' hodnotu
INFO | validator | Validace postav dokončena: 460 validních, 362 anomálií

------------------------------------------------------------
SHRNUTÍ VALIDACE DAT
------------------------------------------------------------
Celkem postav: 460
Celkem lokací: 126
Postavy s 'unknown' status: 61
Postavy s 'unknown' species: 5
Postavy bez location URL: 21
Lokace s 'unknown' dimension: 31
------------------------------------------------------------

KROK 3/4: Načítání dat do SQLite databáze
------------------------------------------------------------
INFO | loader | Detekováno 126 existujících záznamů v tabulce 'locations'
INFO | loader | Nahrávání lokací dokončeno: 0 nových, 126 duplicit, 0 chyb
INFO | loader | Detekováno 460 existujících záznamů v tabulce 'characters'
INFO | loader | Nahrávání postav dokončeno: 0 nových, 460 duplicit, 0 chyb

------------------------------------------------------------
VÝSLEDKY NAHRÁVÁNÍ DO DATABÁZE
------------------------------------------------------------
LOKACE:
  - Nově vloženo: 0
  - Preskočeno (duplicitní): 126
  - Chyby: 0
POSTAVY:
  - Nově vloženo: 0
  - Preskočeno (duplicitní): 460
  - Chyby: 0
------------------------------------------------------------

KROK 4/4: Kontrola integrity databáze
------------------------------------------------------------
INFO | Všechny postavy mají validní odkaz na lokaci
INFO | Duplicitní jména postav (29):
  - 'Beth Smith': 3 výskytů
  - 'Morty': 45 výskytů
  - 'Rick': 67 výskytů
------------------------------------------------------------

============================================================
EL PIPELINE ÚSPĚŠNĚ DOKONČENA
============================================================
FINÁLNÍ POČTY ZÁZNAMŮ V DATABÁZI:
  - Lokace: 126
  - Postavy: 620
  - Celkem: 746
============================================================
```

### Chybový scénář (výpadek sítě)

```
INFO | extractor | Zahájení extrakce entity 'character'
ERROR | extractor | Chyba připojení pro URL: https://rickandmortyapi.com/api/character?page=5
ERROR | extractor | Extrakce 'character' přerušena - nepodařilo se získat response
INFO | extractor | Extrakce 'character' dokončena: celkem 98 záznamů
WARNING | Pipeline pokračuje s částečně staženými daty (graceful degradation)
```

---

## 🔧 Řešení problémů

### Problém: Chyba připojení k API

**Příčina:** Síťové problémy nebo nedostupnost Rick & Morty API

**Řešení:**
1. Zkontrolujte připojení k internetu
2. Ověřte dostupnost API: https://rickandmortyapi.com/api
3. Zvyšte timeout v `extractor.py`: `REQUEST_TIMEOUT = 60`

### Problém: Databázový soubor je zamčený

**Příčina:** Jiný proces používá databázi

**Řešení:**
1. Zavřete všechny aplikace přistupující k `rick_and_morty.db`
2. Na Windows ukončete Python procesy v Task Manageru
3. Smažte soubor `rick_and_morty.db` pro čistý start

### Problém: Příliš mnoho duplicitních záznamů

**Příčina:** Opakované spuštění bez mazání databáze

**Řešení:**
- Toto je očekávané chování (idempotence)
- Pro čistý start smažte `rick_and_morty.db`
- Nebo použijte `INSERT OR REPLACE` místo `INSERT OR IGNORE` v `loader.py`

### Problém: Rate limiting od API

**Příčina:** Příliš rychlé požadavky

**Řešení:**
1. Zvyšte `RATE_LIMIT_DELAY` v `extractor.py` na 0.5 nebo více
2. Implementujte exponenciální backoff pro opakované pokusy

### Problém: Nevalidní JSON response

**Příčina:** API vrací neočekávaný formát

**Řešení:**
1. Zkontrolujte logy pro detaily chyby
2. Ověřte, že API není v maintenance módu
3. Pipeline automaticky uloží data extrahovaná do chyby

---

## 🧪 Testování

### Manuální testování

```bash
# 1. Čistý start
rm rick_and_morty.db

# 2. Spuštění pipeline
python main.py

# 3. Ověření databáze
sqlite3 rick_and_morty.db "SELECT COUNT(*) FROM locations;"
sqlite3 rick_and_morty.db "SELECT COUNT(*) FROM characters;"

# 4. Kontrola integrity
sqlite3 rick_and_morty.db "PRAGMA integrity_check;"
```

### Ukázkové dotazy

```sql
-- Top 10 nejčastějších jmen postav
SELECT name, COUNT(*) as count
FROM characters
GROUP BY name
ORDER BY count DESC
LIMIT 10;

-- Postavy bez lokace
SELECT c.name, c.species
FROM characters c
WHERE c.location_id IS NULL;

-- Lokace s nejvíce postavami
SELECT l.name, COUNT(c.id) as character_count
FROM locations l
LEFT JOIN characters c ON l.id = c.location_id
GROUP BY l.id
ORDER BY character_count DESC
LIMIT 10;

-- Postavy s 'unknown' statusem
SELECT name, species, status
FROM characters
WHERE status = 'unknown' OR status IS NULL;
```

---

## ✅ Compliance se Zadáním

Tato sekce explicitně odpovídá na požadavky zadaní:

| Požadavek | Splnění | Detail |
|-----------|---------|--------|
| **1. Výběr API** | ✅ | Rick & Morty API (z approved list) |
| **2. Python script** | ✅ | 4 moduly, ~1400 LOC, type hints |
| **3. Dvě entity** | ✅ | Characters (460+) + Locations (126) |
| **4. Paginace** | ✅ | while cyklus s `next` kontrolou |
| **5. Local storage** | ✅ | SQLite s relačním modelem |
| **6. Entry point** | ✅ | `python main.py` |
| **7. Transformační diagram** | ✅ | Viz sekce výše |
| **8. README dokumentace** | ✅ | API, entity, storage decision |

### Rozhodnutí o Storage Formátu

**Proč SQLite?**

| Kritérium | SQLite | Alternativa (CSV/JSON) |
|-----------|--------|------------------------|
| Relační data | ✅ FK vazby | ❌ Žádné vazby |
| Integrita | ✅ ACID | ❌ Manuální kontrola |
| Dotazy | ✅ SQL | ❌ Parsing v kódu |
| Performance | ✅ Indexy | ❌ Full scan |
| Idempotence | ✅ INSERT OR IGNORE | ❌ Manuální deduplikace |

---

## Koncept Enterprise přesah

Záměrně jsem tento skript udržel lehký a čistý pro snadné spuštění a hodnocení. Nicméně vzhledem k tomu, že HECON pracuje v energetice s citlivými daty, připravil jsem i dodatečný koncepční návrh produkční architektury. Detaily naleznete v přiloženém dokumentu Enterprise_Architecture_Concept.md

## 📄 Licence

Tento projekt je vytvořen pro vzdělávací účely k úkolovému zadání od firmy Hecon. Data pocházejí z veřejného Rick & Morty API.
