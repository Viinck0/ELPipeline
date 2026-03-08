# Secure EL Pipeline – Rick & Morty API

**Bezpečný ETL/EL pipeline pro stahování, ukládání a reportování dat z Rick & Morty API**

---

## 📋 Obsah

1. [Úvod](#úvod)
2. [Architektura systému](#architektura-systému)
3. [Instalace](#instalace)
4. [Použití](#použití)
5. [Administrátorská kontrola](#administrátorská-kontrola)
6. [Bezpečnostní opatření](#bezpečnostní-opatření)
7. [Technická dokumentace](#technická-dokumentace)
8. [Řešení problémů](#řešení-problémů)

---

## 📖 Úvod

Tato aplikace implementuje **bezpečný EL (Extract-Load) pipeline** pro stahování dat z veřejného [Rick & Morty API](https://rickandmortyapi.com/). Pipeline je navržen s důrazem na **bezpečnost dat**, **auditovatelnost** a **GDPR compliance**.

### Hlavní funkce

- ✅ **Extrakce dat** z Rick & Morty API (lokace a postavy)
- ✅ **Šifrování databáze** na úrovni aplikace (AES-256-GCM)
- ✅ **Audit logging** s neměnným záznamem všech operací
- ✅ **Bezpečné ukládání hesel** pomocí Windows Credential Manager
- ✅ **CSV export** s ochranou proti CSV injection
- ✅ **Detekce anomálií** při validaci dat
- ✅ **Komplexní reporty** o průběhu pipeline

### Proč tato aplikace?

Tento projekt slouží jako **referenční implementace** bezpečného zpracování dat s ohledem na:
- **CRIT-001**: Šifrování dat v klidu (at-rest encryption)
- **HIGH-002**: Neměnný audit trail
- **HIGH-003**: Ochrana osobních údajů (PII)
- **GDPR Article 32**: Bezpečnost zpracování

---

## 🏗️ Architektura systému

```
┌─────────────────────────────────────────────────────────────────┐
│                    SECURE EL PIPELINE                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐                                               │
│  │AUTHENTICATION│                                               │
│  │ (RBAC/Login) │                                               │
│  └─────────────┘                                               │
│         │                                                       │
│         ▼                                                       │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐         │
│  │  EXTRACTOR  │───▶│  VALIDATOR  │───▶│   LOADER    │         │
│  │   (API)     │    │  (Anomaly)  │    │  (Encrypt)  │         │
│  └─────────────┘    └─────────────┘    └─────────────┘         │
│         │                  │                  │                 │
│         │                  │                  ▼                 │
│         │                  │         ┌─────────────┐           │
│         │                  │         │   SQLite    │           │
│         │                  │         │  (Encrypted)│           │
│         │                  │         └─────────────┘           │
│         │                  │                  │                 │
│         ▼                  ▼                  ▼                 │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐         │
│  │    AUDIT    │    │   REPORT    │    │   EXPORT    │         │
│  │   LOGGER    │    │  GENERATOR  │    │    (CSV)    │         │
│  └─────────────┘    └─────────────┘    └─────────────┘         │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Moduly aplikace a jejich podrobné funkce

Tato aplikace se skládá z několika specializovaných modulů. Každý modul má striktně definovanou odpovědnost (Single Responsibility Principle):

| Modul | Popis a funkce |
|-------|----------------|
| `main.py` | **Orchestrátor:** Řídí celý proces. Autentizuje uživatele, ověřuje oprávnění a na základě role volí režim (např. spouští standardní stahování nebo speciální *Auditor mode* pro bezpečný export). |
| `extractor.py` | **Stahování dat:** Komunikuje s Rick & Morty API, řeší stránkování, limity a výpadky pomocí retry logiky. |
| `validator.py` | **Ověřování dat:** Kontroluje integritu dat a detekuje anomálie (např. chybějící vazby, neplatné typy, neočekávané hodnoty). |
| `loader.py` | **Ukládání:** Odpovídá za správu databáze SQLite a zajišťuje její šifrování na aplikační úrovni před fyzickým uložením na disk. |
| `audit_logger.py` | **Logování:** Zajišťuje uložení nezměnitelného auditu všech významných operací. Každý záznam využívá *Hash chaining* k detekci manipulace. |
| `report_generator.py` | **Exporty a reporty:** Generuje textové reporty o průběhu, ale také obsahuje funkce pro dešifrovaný export CSV souborů pro auditory. |
| `authentication.py` | **Autentizace:** Řídí přihlášení uživatele interaktivní výzvou. Ověřuje hesla přes uložené hodnoty, trackuje a uplatňuje časové zámky proti *brute-force*. |
| `security_config.py`| **Konfigurace a RBAC:** Definuje role (`ADMIN`, `OPERATOR`, `AUDITOR`, `GUEST`) a jim příslušná omezení a klíčová bezpečnostní nastavení (např. zámek 60s pro prezentační účely). |
| `database_encryption.py`| **Šifrování (AES-256-GCM):** Poskytuje transparentní šifrovací vrstvu pro textová data zapisovaná do SQLite pomocí balíčku `cryptography`. |
| `secrets_manager.py`| **Keyring:** Zajišťuje, aby hlavní hesla a šifrovací klíče nezůstaly v kódu, ale ukládaly se bezpečně do lokálního správce hesel (Windows Credential Manager). |

---

## 👥 Možnosti přihlášení a role (RBAC)

Aplikace využívá **Role-Based Access Control (RBAC)** k omezení přístupu. Při prvním spuštění se vygeneruje vaše aktuální uživatelské jméno a je vám přidělena role administrátora. K dispozici jsou tyto 4 role:

1. **ADMIN (Administrátor)**
   - **Oprávnění:** Plný přístup. Může spouštět pipeline, číst i zapisovat data, nahlížet do auditu a dokonce spravovat základní bezpečnostní prvky.
2. **OPERATOR (Operátor)**
   - **Oprávnění:** Provozní přístup. Jeho úkolem je spouštět proces extrakce a zpracování dat, ale nesmí zasahovat do nastavení nebo mazat klíče.
3. **AUDITOR (Auditor)**
   - **Oprávnění:** Read-only pro vyšetřování a bezpečnostní dohled.
   - **Speciální funkce "Auditor Mode":** Pokud se uživatel přihlásí jako Auditor, `main.py` aplikaci okamžitě přepne do speciálního režimu. V tomto režimu nedochází k přístupu k síti (žádné volání API) ani k zápisu nových dat. Aplikace místo toho *pouze* bezpečně přečte `rick_and_morty_encrypted.db` a `audit_log_encrypted.db` a automaticky vylistuje dešifrované reporty a CSV do adresáře `Report/secure_exports`.
4. **GUEST (Host)**
   - **Oprávnění:** Nejnižší úroveň. Slouží jako fallback (nouzová varianta), nesmí pracovat s citlivými daty ani spouštět pipeline.

> [!TIP]
> **Study Mode:** Pro studijní účely je detekce Brute-Force (heslový útok) nastavena tak, že vás aplikace udrží při životě 4 pokusy. Jakmile zadáte špatné heslo počtvrté, bude tento "podezřelý přístup" zaznamenán do auditu a účet bude na **1 minutu zamčen**. Pokusy se z řetězce neodmazávají v průběhu uzamčené minuty ani při restartu okna terminálu.

---

## 📦 Instalace

### Požadavky

- **Python**: 3.10 – 3.14 (testováno na Python 3.14)
- **OS**: Windows 10/11, Linux, macOS
- **Paměť**: Minimálně 512 MB RAM
- **Disk**: 100 MB volného místa

### Krok 1: Klonování repository

### Krok 2: Instalace závislostí

```powershell
pip install -r requirements.txt
```

**Poznámka k závislostem:**

| Balíček | Účel |
|---------|------|
| `requests` | HTTP komunikace s API |
| `cryptography` | Šifrování (AES-256-GCM) |
| `keyring` | Integrace s OS keyringem |
| `pywin32` | Windows Credential Manager |
| `python-dotenv` | Načítání .env souborů |
| `pytest` | Testovací framework |
| `pytest-cov` | Měření pokrytí kódu testy |
| `bandit` | Bezpečnostní skenování kódu |
| `pip-audit` | Audit bezpečnosti závislostí |
| `safety` | Kontrola zranitelných závislostí |
| `flake8` | Linter pro kontrolu kvality |
| `mypy` | Statická typová kontrola |

### Krok 3: Konfigurace prostředí

Vytvořte soubor `.env` v kořenovém adresáři:

```powershell
notepad .env
```

Obsah souboru `.env`:
```
DB_NAME=rick_and_morty_encrypted.db
API_BASE_URL=https://rickandmortyapi.com/api
API_TIMEOUT=30
LOG_LEVEL=INFO
ENABLE_AUDIT=true
```

### Krok 4: První spuštění

```powershell
python main.py
```

Při prvním spuštění budete vyzváni k:
1. **Zadání uživatelského jména** (pro audit log)
2. **Zadání hesla** (uloženo v Windows Credential Manager)
3. **Generování šifrovacího klíče** (automaticky)

---

## 🚀 Použití

### Spuštění main.py v roli ADMIN

```powershell
python main.py
```

Pipeline provede:
1. Kontrolu závislostí
2. Autentizaci uživatele (Admin práva)
3. Stažení dat z API (lokace + postavy)
4. Validaci dat a detekci anomálií
5. Uložení do šifrované databáze
6. Generování reportů
7. Export do CSV

### Spuštění main.py v roli OPERATOR

Vhodné pro pravidelné stahování dat bez nutnosti administrátorských zásahů.

```powershell
python main.py
```

Pipeline provede:
1. Kontrolu závislostí
2. Autentizaci uživatele (Operator role)
3. Standardní proces stahování dat z Rick & Morty API
4. Validaci a zápis do šifrované databáze
5. Generování provozních logů a základních reportů

### Spuštění main.py v roli AUDITOR

Speciální režim "Auditor Mode" pro bezpečný export a kontrolu dat bez zásahu do databáze.

```powershell
python main.py
```

V tomto režimu aplikace provede:
1. Kontrolu závislostí a přihlášení uživatele (Auditor role)
2. **Přeskočení síťové komunikace** (stahování z API se nekoná)
3. **Automatický export dat** ze šifrované databáze i audit logu
4. Vytvoření dešifrovaných CSV souborů v adresáři `Report/secure_exports`
5. Zápis o auditní kontrole do nezměnitelného logu

### Samostatné operace (Rozšířené jednořádkové příkazy)

> [!WARNING]
> **Důležité upozornění:** Tyto příkazy vyžadují, aby byla nejprve alespoň jednou úspěšně spuštěna hlavní pipeline (pro vygenerování databáze, klíčů a inicializaci). Příkazy byly **ověřeny a otestovány** na platformě Windows pro spolehlivou funkčnost.

#### 1. Rychlý export dešifrovaných dat API do CSV (Locations & Characters)
Tento příkaz rovnou načte šifrovanou databázi, propojí klíče a do adresáře reportů uloží dvě odemčené dešifrované tabulky z API do CSV.

```powershell
python -c "from loader import init_database, export_locations_to_csv, export_characters_to_csv, close_database; from security_config import DefaultPaths; conn = init_database(); export_locations_to_csv(conn, DefaultPaths.REPORT_DIR / 'locations.csv'); export_characters_to_csv(conn, DefaultPaths.REPORT_DIR / 'characters.csv'); close_database(conn)"
```

#### 2. Zobrazení posledních 10 kroků auditu rovnou do terminálu
Pomáhá pro bleskové sledování toho, kdo zrovna do sytému vstoupil a s jakým výsledkem. Hodnoty `outcome` a `event_type` se nahrávají standardní cestou a poskytnou záchytné detektory aktivit.

```powershell
python -c "from audit_logger import get_audit_logger; logger = get_audit_logger(); entries = logger.get_entries(limit=10); [print(f'{e[\"id\"]}: {e[\"event_type\"]} - {e[\"outcome\"]}') for e in entries]"
```

#### 3. Bezpečný export celého Audit logu do CSV (Dešifrováno komerčními správci)
Kompletní generátor sloupcového výpisu všech zaznamenaných aktivit s celou architektonickou signaturou, vytaženou z Hashchain okruhů. Získáte dešifrované znění o uzamčení, IP a uživatelích vytahaných k ručním filtrům.

```powershell
python -c "from audit_logger import get_audit_logger; from security_config import DefaultPaths; import csv; logger = get_audit_logger(); entries = logger.get_entries(limit=10000); DefaultPaths.EXPORT_DIR.mkdir(parents=True, exist_ok=True); csv_path = DefaultPaths.EXPORT_DIR / 'audit_log_export.csv'; f = open(csv_path, 'w', newline='', encoding='utf-8'); w = csv.DictWriter(f, fieldnames=['id', 'timestamp', 'event_category', 'event_type', 'priority', 'user_identity', 'user_role', 'action', 'resource', 'resource_type', 'outcome', 'details', 'ip_address', 'session_id', 'signature', 'previous_hash', 'entry_hash']); w.writeheader(); w.writerows(entries); f.close(); print(f'Exportováno {len(entries)} záznamů do {csv_path}')"
```

Alternativou je nyní přepracovaný skript vytvořený uvnitř operativních modulů jako "Auditor Mode", kde stejného výsledků dosáhnete spuštěním main skriptu jako Role `auditor`. Aplikace totiž vykryje plně dešifrovanou audit stopu do složky exportů.

#### 4. Krypto-ověření integrity audit logu pomocí signatur z Hash-Chains
Jediný rychlý způsob, jak zjistit s 100% jistotou, že do historického vývoje záznamů nikdo cizí ani na vteřinu programově nezasáhnul (žádný manuální UPDATE či DELETE).

```powershell
python -c "from audit_logger import get_audit_logger; logger = get_audit_logger(); valid, msg = logger.verify_integrity(); print(f'Integrita: {valid} - {msg}')"
```

---

## 🔐 Administrátorská kontrola

### Správa šifrovacích klíčů

#### 5. Rychlá kontrola statusu aplikačního šifrování
Tato kontrola vytiskne reálný JSON souhrn nastavení `AES-256-GCM`.

```powershell
python -c "from loader import get_encryption_status; import json; print(json.dumps(get_encryption_status(), indent=2))"
```

#### 6. Generování statistik základních čítačů pro databázi šifrovanou na úrovni aplikace
I bez dešifrování dat lze bezpečně spočítat tabulky, pokud klíč na moment aktivujeme s prázdnou sadou vrácených dešifrovaných klíčů.

```powershell
python -c "import sqlite3; from security_config import DefaultPaths; conn = sqlite3.connect(str(DefaultPaths.ENCRYPTED_DB)); cur = conn.cursor(); cur.execute('SELECT COUNT(*) FROM locations'); print(f'Lokace: {cur.fetchone()[0]}'); cur.execute('SELECT COUNT(*) FROM characters'); print(f'Postavy: {cur.fetchone()[0]}'); cur.execute('SELECT COUNT(*) FROM audit_log'); print(f'Audit záznamů: {cur.fetchone()[0]}')"
```

#### 7. Šnečí export Json logu auditu na analýzy (alternativa CSV)

```powershell
python -c "from audit_logger import get_audit_logger; from security_config import DefaultPaths; import json; logger = get_audit_logger(); entries = logger.get_entries(limit=10000); DefaultPaths.EXPORT_DIR.mkdir(parents=True, exist_ok=True); json_path = DefaultPaths.EXPORT_DIR / 'audit_export.json'; open(json_path, 'w', encoding='utf-8').write(json.dumps(entries, indent=2, ensure_ascii=False)); print(f'Audit log exportován do {json_path}')"
```

#### Dešifrování databáze pro auditora (kontrola integrity)

**Poznámka:** První dešifrování může trvat několik minut kvůli PBKDF2 key derivation.

**Rychlá kontrola (pouze náhled prvních 5 záznamů na obrazovku):**

```powershell
python -c "from secrets_manager import get_encryption_key_manager; from database_encryption import get_database_encryptor; import sqlite3; from security_config import DefaultPaths; km = get_encryption_key_manager(); key = km.get_encryption_key(); enc = get_database_encryptor(key); conn = sqlite3.connect(str(DefaultPaths.ENCRYPTED_DB)); cur = conn.cursor(); cur.execute('SELECT id, name, type, dimension FROM locations ORDER BY id LIMIT 5'); print('=== LOCATIONS (desifrovano) ==='); [print('ID=' + str(r[0]) + ': ' + enc.decrypt(r[1]) + ' | ' + (enc.decrypt(r[2]) if r[2] else '') + ' | ' + (enc.decrypt(r[3]) if r[3] else '')) for r in cur.fetchall()]; cur.execute('SELECT id, name, species, status FROM characters ORDER BY id LIMIT 5'); print('=== CHARACTERS (desifrovano) ==='); [print('ID=' + str(r[0]) + ': ' + enc.decrypt(r[1]) + ' | ' + (enc.decrypt(r[2]) if r[2] else '') + ' | ' + (enc.decrypt(r[3]) if r[3] else '')) for r in cur.fetchall()]"
```

**Kompletní dešifrování celé databáze (vytvoří CSV soubory):**

```powershell
python audit_decrypt_full.py
```

**Výstup:**
```
============================================================
AUDIT DECRYPT - Kompletní dešifrování databáze
============================================================

Načítání šifrovacího klíče... OK
Inicializace dešifrovacího modulu... OK
Připojení k databázi... OK

------------------------------------------------------------
Dešifrování databáze:
------------------------------------------------------------
Dešifrování locations... dokončeno (126 záznamů)
  → Report\secure_exports\audit_locations_full.csv
Dešifrování characters... dokončeno (826 záznamů)
  → Report\secure_exports\audit_characters_full.csv

============================================================
AUDIT DECRYPT DOKONČEN
============================================================

Celkem dešifrováno záznamů:
  - Locations:   126
  - Characters:  826

Dešifrovaná data uložena v:
  c:\Users\Vinci\Desktop\ukol\Report\secure_exports

⚠️ UPOZORNĚNÍ: Tyto soubory obsahují NEŠIFROVANÁ data!
   Zacházejte s nimi jako s citlivými informacemi.
```

**Vytvořené soubory:**
- `Report/secure_exports/audit_locations_full.csv` – všechny lokace (dešifrováno)
- `Report/secure_exports/audit_characters_full.csv` – všechny postavy (dešifrováno)

### Bezpečnostní audit

#### Kontrola integrity souborů

```powershell
python -c "from file_security import get_file_permissions_manager; from security_config import DefaultPaths; sec = get_file_permissions_manager(); [print(f'{f.name}: {\"OK\" if sec.verify_permissions(f)[0] else sec.verify_permissions(f)[1]}') for f in [DefaultPaths.ENCRYPTED_DB, DefaultPaths.AUDIT_DB]]"
```

#### Skenování bezpečnosti kódu

```powershell
python -m bandit -r . -ll -x __pycache__,.git,Report
```

**Vysvětlení:**
- `python -m bandit` - Spuštění bandit přes Python (řeší PATH problémy na Windows)
- `-r .` - Rekurzivní skenování aktuálního adresáře
- `-ll` - Zobrazení Low, Medium a High severity issues
- `-x __pycache__,.git,Report` - Vyloučení složek které nemusí být relevantní

#### Audit závislostí

```powershell
python -m pip_audit -r requirements.txt
python -m safety scan
```

---

## 🛡️ Bezpečnostní opatření

### 1. Šifrování dat

**Proč AES-256-GCM?**

- **Autentizované šifrování**: GCM režim poskytuje integritu i důvěrnost
- **256bitový klíč**: Odolné vůči brute-force útokům
- **Náhodný salt + nonce**: Každé šifrování je unikátní
- **PBKDF2**: Bezpečné odvození klíče s 10 000 iteracemi

**Formát uložených dat:**
```
[16B salt] [12B nonce] [ciphertext] [16B authentication tag]
```

### 2. Správa hesel

**Proč Windows Credential Manager?**

- **OS-native integrace**: Hesla nejsou uložena v souborech
- **Šifrování DPAPI**: Windows chrání uložená hesla
- **Žádné hard-coded credentials**: Všechna tajemství jsou mimo kód

**Alternativy pro jiné OS:**
- **Linux**: GNOME Keyring / KWallet
- **macOS**: Keychain

### 3. Audit logging

**Proč neměnný audit log?**

- **Hash chain**: Každý záznam obsahuje hash předchozího
- **Detekce manipulace**: Jakákoli změna je detekována
- **Blockchain princip**: Podobné jako blockchain pro audit trail

**Ukládané události:**
- Přihlášení/odhlášení uživatele
- Extrakce dat z API
- Validace a detekce anomálií
- Zápis do databáze
- Export dat

### 4. Ochrana proti CSV Injection

**Proč je to důležité?**

CSV injection umožňuje útočníkovi spustit libovolné příkazy při otevření CSV v Excelu.

**Ochrana:**
- Prefixování nebezpečných znaků (`=`, `+`, `-`, `@`) apostrofem
- Sanitace všech exportovaných hodnot

### 5. File Permissions

**Proč restriktivní oprávnění?**

- **Windows**: NTFS ACL pouze pro vlastníka (R,W)
- **Linux/macOS**: chmod 600 (pouze vlastník čte/zapisuje)

---

## 📚 Technická dokumentace

### Návrhová rozhodnutí

#### 1. Aplikační šifrování místo SQLCipher

**Důvod:**
- `pysqlcipher3` není dostupné pro Python 3.14+ na Windows
- `sqlean-py` selhává při kompilaci na Windows s MSVC

**Výhody aplikačního šifrování:**
- ✅ Plná kompatibilita s Python 3.14+
- ✅ Nezávislost na C extension
- ✅ Stejná úroveň bezpečnosti (AES-256)
- ✅ Přenositelnost mezi platformami

**Nevýhody:**
- ❌ Nelze použít SQL dotazy nad šifrovanými poli
- ❌ Větší velikost dat (base64 overhead ~33%)

#### 2. Hash chain pro audit log

**Důvod:**
- Detekce jakékoli manipulace s audit logem
- Neměnnost záznamů (immutable ledger)

**Implementace:**
```python
entry_hash = SHA256(timestamp | category | type | user | action | outcome | previous_hash)
```

#### 3. Separace audit databáze

**Důvod:**
- Oddělení provozních dat od auditních
- Nezávislé šifrovací klíče
- Lepší výkon (žádné blokování při audit operacích)

#### 4. PBKDF2 s 10 000 iteracemi

**Důvod:**
- Odolnost vůči brute-force útokům
- Vyvážený výkon pro hromadné šifrování/dat
- Master klíč je 256-bitový, takže nižší počet iterací je stále bezpečný

### Schéma databáze

#### Tabulka `locations`

| Sloupec | Typ | Šifrováno | Popis |
|---------|-----|-----------|-------|
| id | INTEGER | ❌ | Primární klíč |
| name | TEXT | ✅ | Název lokace |
| type | TEXT | ✅ | Typ lokace |
| dimension | TEXT | ✅ | Dimenze |
| created_at | TEXT | ❌ | Čas vytvoření |
| updated_at | TEXT | ❌ | Čas aktualizace |

#### Tabulka `characters`

| Sloupec | Typ | Šifrováno | Popis |
|---------|-----|-----------|-------|
| id | INTEGER | ❌ | Primární klíč |
| name | TEXT | ✅ | Jméno postavy |
| species | TEXT | ✅ | Druh |
| status | TEXT | ✅ | Status (živý/mrtvý) |
| location_id | INTEGER | ❌ | FK na locations |
| created_at | TEXT | ❌ | Čas vytvoření |
| updated_at | TEXT | ❌ | Čas aktualizace |

#### Tabulka `audit_log`

| Sloupec | Typ | Šifrováno | Popis |
|---------|-----|-----------|-------|
| id | INTEGER | ❌ | Primární klíč |
| timestamp | TEXT | ❌ | Čas události |
| event_category | TEXT | ❌ | Kategorie |
| event_type | TEXT | ❌ | Typ události |
| priority | TEXT | ❌ | Priorita |
| user_identity | TEXT | ✅ | Identita uživatele |
| user_role | TEXT | ✅ | Role uživatele |
| action | TEXT | ❌ | Akce |
| resource_type | TEXT | ❌ | Typ zdroje |
| resource | TEXT | ✅ | Ovlivněný zdroj |
| outcome | TEXT | ❌ | Výsledek |
| details | TEXT | ✅ | Detaily |
| ip_address | TEXT | ✅ | IP adresa |
| session_id | TEXT | ✅ | ID relace |
| signature | TEXT | ❌ | Podpis záznamu |
| previous_hash | TEXT | ❌ | Hash předchozího |
| entry_hash | TEXT | ❌ | Hash záznamu |

---

## 🔧 Řešení problémů

### Časté chyby

#### 1. "EOF when reading a line"

**Příčina:** Interaktivní zadání hesla selže při neinteraktivním spuštění

**Řešení:**
```powershell
python main.py
```

#### 2. "Failed to retrieve encryption key"

**Příčina:** Windows Credential Manager nemá uložené heslo

**Řešení:**
```powershell
python -c "from secrets_manager import get_encryption_key_manager; km = get_encryption_key_manager(); km.delete_key()"
python main.py
```

#### 3. "Database is locked"

**Příčina:** Jiný proces drží databázový soubor

**Řešení:**
```powershell
taskkill /F /IM python.exe
```

#### 4. "Decryption failed"

**Příčina:** Špatný šifrovací klíč nebo poškozená data

**Řešení:**
```powershell
python -c "from audit_logger import get_audit_logger; logger = get_audit_logger(); valid, msg = logger.verify_integrity(); print(msg)"
```

### Log soubory

Logy a auditní záznamy jsou ukládány odlišně podle svého účelu:
- **Aplikační logy**: `Report/logs/pipeline.log` – Hlavní log pipeline (průběh, chyby).
- **Bezpečnostní audit log**: Ukládán **výhradně do šifrované databáze** (`Report/audit_log_encrypted.db`), nikoliv do běžného textového souboru.

---

## 📊 Příklady výstupů

### Příklad reportu

```
================================================================================
EL PIPELINE REPORT - Rick & Morty API
================================================================================

ČASOVÉ ÚDAJE
----------------------------------------
  Start:           2026-03-07 10:00:00
  Konec:           2026-03-07 10:00:15
  Doba běhu:       15.23 sekund

SHRNUTÍ EXTRAKCE (API)
----------------------------------------
  Staženo Locations:    126
  Staženo Characters:   671
  Celkem z API:         797

SHRNUTÍ NAČÍTÁNÍ (DB)
----------------------------------------
  Vloženo Locations:    126 (nových záznamů)
  Vloženo Characters:   671 (nových záznamů)
  Celkem vloženo:       797

AKTUÁLNÍ STAV DATABÁZE
----------------------------------------
  Celkem Locations:     126
  Celkem Characters:    671
  Characters s lokací:  423 (63.0%)
  Unikátních lokací:    97

BEZPEČNOSTNÍ STATUS
----------------------------------------
  Šifrování:          ENABLED (AES-256-GCM)
  Audit logging:      ENABLED
  File permissions:   SECURE
```

### Příklad CSV exportu

```csv
id,name,species,status,location_id,location_name
1,Rick Sanchez,Human,Alive,1,Schwifty World
2,Morty Smith,Human,Alive,1,Schwifty World
```

---

## 📝 Licence

Tento projekt je určen pro vzdělávací účely v rámci úkolového zadání od firmy Hecon.

---

*Poslední aktualizace: 8. března 2026*
