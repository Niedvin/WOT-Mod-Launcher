# WOT Mod Launcher — модпак Niedvin для World of Tanks (EU)

Репозиторій автооновлення модпаку **WoT Modpack by Niedvin** для клієнта World of Tanks EU.
Усі файли збірки живуть у [Releases](https://github.com/Niedvin/WOT-Mod-Launcher/releases) — звідки лаунчер і завантажує оновлення.

## Як працює автооновлення

Лаунчер `WotModLauncher.exe` (встановлюється інсталятором модпаку у `%LOCALAPPDATA%\WotModpack`) при кожному запуску гри:

1. завантажує [manifest.json останнього релізу](https://github.com/Niedvin/WOT-Mod-Launcher/releases/latest/download/manifest.json) у фоні, поки лаунчер перевіряє теку гри (ліміт 6 с);
2. звіряє версії встановлених `.wotmod` з маніфестом (ідентифікатор і версія з `meta.xml` / назви файлу), доставляє відсутні моди з маніфесту та пропускає ID зі списку `skip_mods` у `launcher.json` і зі списку відхилених `%LOCALAPPDATA%\WotModpack\declined.json`;
3. якщо оновлень немає — одразу запускає Wargaming launcher (`wgc_api.exe --open`), без вікна;
4. якщо оновлення є — показує вікно, яке можна розтягувати: оновлення і нові моди йдуть двома колонками, оновлення лаунчера — окремим рядком зверху, кожен мод можна позначити або зняти окремо; «Без модів» тимчасово перейменовує теку модів поточної версії, і наступний запуск лаунчера повертає її назад;
5. кнопка «Більше не пропонувати» назавжди приховує вибрані моди: вони більше не встановлюються, не оновлюються і не пропонуються; повернути мод можна, видаливши `%LOCALAPPDATA%\WotModpack\declined.json`;
6. спершу завантажує й перевіряє всі вибрані пакети (SHA-256, розмір, `meta.xml`), і лише потім замінює файли; перед заміною створює бекап у `<гра>\.backups\launcher\`, при збої відновлює старі файли у зворотному порядку; записи маніфесту без `sha256` або з небезпечним `file`/`subdir` відкидаються;
7. після запуску гри лаунчер тихо, без вікон, завантажує власне оновлення у фоні та підміняє свій exe; наступний запуск іде вже з новою версією. Якщо підмінити файл не вдалося, новий exe застосовується під час наступного старту;
8. переносить моди в нову папку версії гри після патчу клієнта.

## Склад модпаку (реліз 2026.11.11.1, клієнт 2.4.1.1)

| Мод | Версія |
|---|---|
| Smart Server | 1.1.3 |
| Squad+ | 1.0.4 |
| Velet Penetration | 1.0.2 |
| ModsSettings API (Izeberg) | 1.7.1 |
| ModsList API (Poliroid) | 1.8.0 |
| OpenWG Core & Fixes (3 пакети) | 1.9.0 / 1.1.0 / 1.2.2 |
| Spectator+ | 1.0.12 |
| Background FPS Limiter | 1.0.5 |
| Quick Research | 1.2.5 |
| GPU Boost: Anti-Lag 2 + XeSS (опційно, OpenWG 2.8.3) | 2.8.3.0000 |
| Appropriate Locker | 1.2.2 |

## Завантаження

Остання збірка: [releases/latest](https://github.com/Niedvin/WOT-Mod-Launcher/releases/latest)

- `WoT_Modpack_by_Niedvin_Setup.exe` — один саморозпаковний файл: запустіть, нічого розпаковувати не треба.
- `WoT_Modpack_by_Niedvin.zip` — архів з `Installer.exe`, лаунчером і модами.

## Пакети на вимогу

Інсталятор важить ~1.2 МБ: важкі пакети GPU Boost (`net.openwg.common`, `net.openwg.gpu.upscaler`, `net.openwg.gpu.upscaler.xess`, разом ~167 МБ) у дистрибутив не входять.

- Завантажуються з GitHub лише тоді, коли в інсталяторі позначено мод **GPU Boost**; без позначки не качається нічого.
- Кожен файл звіряється за SHA-256, копія кешується в `%LOCALAPPDATA%\WotModpack\payload_cache` і повторно не завантажується.
- Версія береться з `manifest.json` останнього релізу; якщо мережі немає, решта модів встановлюється, а GPU Boost пропускається з повідомленням у лозі.
- Ті самі `.wotmod` лежать у релізі окремими ассетами, тож лаунчер автооновлення працює з ними без змін.

## Схема manifest.json

```json
{
  "schema": 1,
  "pack_version": "2026.11.11",
  "game_version": "2.4.1.1",
  "launcher": { "version": "1.4.3.2", "url": ".../WotModLauncher.exe", "sha256": "..." },
  "mods": [
    { "id": "server_online", "title": "Smart Server",
      "version": "1.1.3", "file": "ua.server_online_autoconnect_1.1.3.wotmod",
      "subdir": "", "url": ".../ua.server_online_autoconnect_1.1.3.wotmod",
      "sha256": "...", "size": 22265, "changes": "короткий опис змін" }
  ]
}
```

Поля `url` і `sha256` обов'язкові: запис без них, з `file`/`subdir` поза текою модів або з некоректним ID лаунчер пропускає.

## Вихідний код

| Файл | Призначення |
|---|---|
| `src/WotModLauncher.cs` | лаунчер автооновлення (C# .NET Framework 4.5+, WinForms + GDI+, без зовнішніх залежностей, збірка `csc.exe`) |
| `src/Installer.cs` | інсталятор модпаку (вибір модів, бекапи, встановлення лаунчера, вибіркове видалення) |
| `src/publish_release.py` | генерація `manifest.json` та папки ассетів `build/release_assets/` для нового релізу |

Новий реліз: тег `pack-YYYY.MM.DD`, ассети — усе з `build/release_assets/` (усі `.wotmod`, `WotModLauncher.exe`, `manifest.json`, `WoT_Modpack_by_Niedvin.zip`).

Версія лаунчера в `manifest.json` береться з `AssemblyFileVersion` зібраного exe. Перед кожним релізом піднімайте `AssemblyFileVersion` і `AssemblyVersion` у `src/WotModLauncher.cs`, інакше встановлені лаунчери не побачать нову версію.

Автор: **Niedvin** (2026)

## Development

Source for all 7 Niedvin mods, native focus helper, build scripts and research artwork is included under `src/mods/` and `src/build/`. See [build instructions](docs/BUILD.md) and [research design validation](docs/research-button-design-qa.md).

## Додавання нового мода

Кожен мод описується одним `src/mods/<id>/mod.json`: id, тека в інсталяторі, назва, версія, опис, файли для staging, список старих версій і спосіб збірки (`pyc`, `script`, `prebuilt` або `none`). `build_mods.py`, `stage_mods.py`, інсталятор і `manifest.json` читають ці файли автоматично — окремі списки модів редагувати не треба.

Щоб додати мод: створіть `src/mods/<id>/mod.json`, покладіть джерела або вкажіть готовий `.wotmod`, виконайте `python scratch/build_mods.py` і `python scratch/stage_mods.py`, потім зробіть реліз. Новий мод з'явиться у списку інсталятора та в оновленнях лаунчера.
