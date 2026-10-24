# WOT Mod Launcher — модпак Niedvin для World of Tanks (EU)

Репозиторій автооновлення модпаку **WoT Modpack by Niedvin** для клієнта World of Tanks EU.
Усі файли збірки живуть у [Releases](https://github.com/Niedvin/WOT-Mod-Launcher/releases) — звідки лаунчер і завантажує оновлення.

## Як працює автооновлення

Лаунчер `WotModLauncher.exe` (встановлюється інсталятором модпаку у `%LOCALAPPDATA%\WotModpack`) при кожному запуску гри:

1. завантажує [manifest.json останнього релізу](https://github.com/Niedvin/WOT-Mod-Launcher/releases/latest/download/manifest.json) (таймаут 4 с);
2. звіряє версії встановлених `.wotmod` з маніфестом (ідентифікатор і версія з `meta.xml` / назви файлу);
3. якщо оновлень немає або немає інтернету — одразу запускає `WorldOfTanks.exe`, без зайвих вікон;
4. якщо оновлення є — показує вікно зі списком змін та кнопками «Оновити і грати» / «Грати без оновлення»;
5. кожен пакет перевіряється за SHA-256, розміром і `meta.xml` (`<id>`); перед заміною створюється бекап у `<гра>\.backups\launcher\`, при збої старі файли відновлюються;
6. лаунчер також вміє оновлювати сам себе та переносити моди в нову папку версії гри після патчу клієнта.

## Склад модпаку (реліз 2026.10.24, клієнт 2.4.1.0)

| Мод | Версія |
|---|---|
| Server Online & Autoconnect | 1.1.1 |
| Platoon Autostart & Modern UI | 1.0.1 |
| Armor Flashlight Brightness | 1.0.1 |
| ModsSettings API (Izeberg) | 1.7.1 |
| ModsList API (Poliroid) | 1.8.0 |
| OpenWG Core & Fixes (4 пакети) | 2.1.2 / 1.8.1 / 1.0.5 / 1.2.2 |
| Spectator Teammate HUD | 1.0.5 |
| Background FPS Limiter | 1.0.0 |

## Завантаження

Остання збірка: [releases/latest](https://github.com/Niedvin/WOT-Mod-Launcher/releases/latest) —
`WoT_Modpack_by_Niedvin.zip` (інсталятор + лаунчер + моди + README). Розархівуйте у будь-яку теку і запустіть `Installer.exe`.

## Схема manifest.json

```json
{
  "schema": 1,
  "pack_version": "2026.10.24",
  "game_version": "2.4.1.0",
  "launcher": { "version": "1.0.0", "url": ".../WotModLauncher.exe", "sha256": "..." },
  "mods": [
    { "id": "ua.server_online_autoconnect", "title": "Server Online & Autoconnect",
      "version": "1.1.1", "file": "ua.server_online_autoconnect_1.1.1.wotmod",
      "subdir": "", "url": ".../ua.server_online_autoconnect_1.1.1.wotmod",
      "sha256": "...", "size": 22265, "changes": "короткий опис змін" }
  ]
}
```

## Вихідний код

| Файл | Призначення |
|---|---|
| `src/WotModLauncher.cs` | лаунчер автооновлення (C# .NET Framework 4.0, WinForms + GDI+, без зовнішніх залежностей, збірка `csc.exe`) |
| `src/Installer.cs` | інсталятор модпаку (вибір модів, бекапи, встановлення лаунчера, вибіркове видалення) |
| `src/publish_release.py` | генерація `manifest.json` та папки ассетів `build/release_assets/` для нового релізу |

Новий реліз: тег `pack-YYYY.MM.DD`, ассети — усе з `build/release_assets/` (усі `.wotmod`, `WotModLauncher.exe`, `manifest.json`, `WoT_Modpack_by_Niedvin.zip`).

Автор: **Niedvin** (2026)
