using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Security.Cryptography;
using System.Windows.Forms;
using System.Web.Script.Serialization;
using WotModLauncher;

public static class LauncherLogicTest
{
    [STAThread]
    public static int Main(string[] args)
    {
        Application.EnableVisualStyles();
        string game = Path.Combine(Path.GetTempPath(), "wot-launcher-test-" + Guid.NewGuid().ToString("N"));
        if (args.Length > 0 && args[0] == "--preview")
        {
            using (var preview = new UpdateDialogForm(game, "2.4.1.1", PreviewUpdates(), null, game))
            {
                preview.Text += " (перевірка)";
                Application.Run(preview);
            }
            return 0;
        }
        string verDir = Path.Combine(game, "mods", "2.4.1.1");
        Directory.CreateDirectory(verDir);
        File.WriteAllText(Path.Combine(verDir, "ua.existing_1.0.0.wotmod"), "x");

        var manifest = new ManifestRoot();
        manifest.mods = new List<ManifestModEntry>();
        manifest.mods.Add(Package("ua.existing", "1.1.0", ""));
        manifest.mods.Add(Package("ua.newmod", "2.0.0", "sub"));
        manifest.mods.Add(Package("UA.NEWMOD", "1.0.0", "sub"));
        manifest.mods.Add(Package("ua.skipped", "1.0.0", "", false));

        var updates = Program.FindPendingUpdates(game, "2.4.1.1", manifest, new List<string> { "ua.skipped" });
        if (updates.Count != 2)
            throw new Exception("expected 2 updates, got " + updates.Count);

        PendingModUpdate existing = updates.Find(delegate(PendingModUpdate u) { return u.Remote.id == "ua.existing"; });
        if (existing == null || existing.IsNew || existing.InstalledVersion != "1.0.0")
            throw new Exception("existing mod update not detected");

        PendingModUpdate added = updates.Find(delegate(PendingModUpdate u) { return u.Remote.id == "ua.newmod"; });
        if (added == null || !added.IsNew || added.Remote.version != "2.0.0" || added.LocalFilePath != Path.Combine(verDir, "sub", "ua.newmod_2.0.0.wotmod"))
            throw new Exception("missing mod was not scheduled for install");

        if (updates.Find(delegate(PendingModUpdate u) { return u.Remote.id == "ua.skipped"; }) != null)
            throw new Exception("skipped mod was scheduled");

        var defaults = new ManifestRoot();
        defaults.mods = new List<ManifestModEntry>();
        defaults.mods.Add(Package("ua.default", "1.0.0", ""));
        defaults.mods.Add(Package("ua.optional", "1.0.0", "", false));
        var defaultUpdates = Program.FindPendingUpdates(game, "2.4.1.1", defaults, null);
        if (defaultUpdates.Count != 1 || defaultUpdates[0].Remote.id != "ua.default")
            throw new Exception("default-checked filter failed");

        Program.DisableMods(game, "2.4.1.1");
        string disabled = Path.Combine(game, "mods", "2.4.1.1.disabled");
        if (Directory.Exists(verDir) || !File.Exists(Path.Combine(disabled, "ua.existing_1.0.0.wotmod")))
            throw new Exception("mods were not disabled");

        Directory.CreateDirectory(verDir);
        File.WriteAllText(Path.Combine(verDir, "ua.new_1.0.0.wotmod"), "y");
        Program.RestoreDisabledMods(game);
        if (Directory.Exists(disabled))
            throw new Exception("disabled mods folder still exists");
        if (!File.Exists(Path.Combine(verDir, "ua.existing_1.0.0.wotmod")) ||
            !File.Exists(Path.Combine(verDir, "ua.new_1.0.0.wotmod")))
            throw new Exception("mods were not merged back");

        TestGroupsAndDecline(game, verDir);
        TestRemovalAndReturn(Path.Combine(game, "removal"));
        TestCatalogInstall(Path.Combine(game, "restore-install"));
        TestLayout(game, args.Length == 2 && args[0] == "--capture" ? args[1] : null);
        Console.WriteLine("LAUNCHER LOGIC TEST PASSED");
        return 0;
    }

    private static void TestRemovalAndReturn(string game)
    {
        string verDir = Path.Combine(game, "mods", "2.4.1.1");
        var packages = PreviewUpdates();
        var gpuPackages = packages.Where(item => ModOffer.DeclineGroup(item.Remote) == "openwg-group:gpu").ToList();
        string gpuDirectory = Path.Combine(verDir, "net.openwg");
        Directory.CreateDirectory(gpuDirectory);
        string upscaler = Path.Combine(gpuDirectory, "net.openwg.gpu.upscaler_1.0.0.wotmod");
        string older = Path.Combine(gpuDirectory, "net.openwg.gpu.upscaler_0.9.0.wotmod");
        string xess = Path.Combine(gpuDirectory, gpuPackages[1].Remote.file);
        string unrelated = Path.Combine(gpuDirectory, "unrelated_1.0.0.wotmod");
        foreach (string path in new[] { upscaler, older, xess, unrelated }) File.WriteAllText(path, Path.GetFileName(path));
        var optional = Package("ua.optional", "1.0.0", "", false);
        var manifest = new ManifestRoot { mods = packages.Select(item => item.Remote).Concat(new[] { optional }).ToList() };
        string settings = Path.Combine(game, "removal.json");
        var catalog = Program.ScanModCatalog(game, "2.4.1.1", manifest);
        var gpu = ModOffer.Create(catalog).Single(offer => offer.Title == "GPU Boost");
        string unwritable = Path.Combine(game, "reserved.json");
        Directory.CreateDirectory(unwritable);
        bool rolledBack = false;
        try { Program.RemoveModOffer(game, "2.4.1.1", unwritable, gpu); }
        catch (IOException) { rolledBack = new[] { upscaler, older, xess }.All(File.Exists); }
        if (!rolledBack) throw new Exception("a failed preference write did not restore the removed files");
        Program.RemoveModOffer(game, "2.4.1.1", settings, gpu);
        if (new[] { upscaler, older, xess }.Any(File.Exists) || !File.Exists(unrelated))
            throw new Exception("removal did not match the installed group and all of its versions");
        if (Directory.GetFiles(Path.Combine(game, ".backups", "launcher"), "*.wotmod", SearchOption.AllDirectories).Length != 3)
            throw new Exception("mod removal left no recoverable archive");

        var preferences = new JavaScriptSerializer().Deserialize<List<string>>(File.ReadAllText(settings));
        string migrated = Path.Combine(game, "mods", "2.5.0.0");
        string legacy = Path.Combine(game, "mods", "2.3.0.0");
        Directory.CreateDirectory(legacy);
        File.WriteAllText(Path.Combine(legacy, Path.GetFileName(upscaler)), "historical");
        File.WriteAllText(Path.Combine(legacy, Path.GetFileName(unrelated)), "untouched");
        File.WriteAllText(Path.Combine(verDir, Path.GetFileName(upscaler)), "historical");
        File.WriteAllText(Path.Combine(verDir, Path.GetFileName(unrelated)), "untouched");
        Program.SyncVersionFolderIfEmpty(game, "2.5.0.0", preferences);
        if (Directory.GetFiles(migrated, Path.GetFileName(upscaler), SearchOption.AllDirectories).Length != 0 ||
            !File.Exists(Path.Combine(migrated, Path.GetFileName(unrelated))))
            throw new Exception("a dismissed mod was migrated into a newer game version");
        File.Delete(Path.Combine(verDir, Path.GetFileName(upscaler)));
        if (Program.FindPendingUpdates(game, "2.4.1.1", manifest, null, preferences)
            .Any(item => ModOffer.DeclineGroup(item.Remote) == "openwg-group:gpu"))
            throw new Exception("a declined mod was proposed on the next launch");
        var missing = Program.ScanModCatalog(game, "2.4.1.1", manifest).Where(item => item.IsNew).ToList();
        if (!missing.Any(item => item.Remote.id == optional.id) || !gpu.Packages.All(item => missing.Any(candidate => candidate.Remote.id == item.Remote.id)))
            throw new Exception("the catalog omitted an optional or removed mod");

        File.WriteAllText(upscaler, "restored");
        Program.RememberAddedMods(settings, gpu.Packages.Where(item => item.Remote.id == "net.openwg.gpu.upscaler"));
        preferences = new JavaScriptSerializer().Deserialize<List<string>>(File.ReadAllText(settings));
        var skip = new List<string> { "net.openwg.gpu.upscaler" };
        if (!Program.FindPendingUpdates(game, "2.4.1.1", manifest, skip, preferences)
            .Any(item => item.LocalFilePath == upscaler && !item.IsNew))
            throw new Exception("an explicitly re-added mod still did not receive updates");
        var offers = Program.FindPendingUpdates(game, "2.4.1.1", manifest, null, preferences);
        if (offers.Any(item => item.Remote.id == "net.openwg.gpu.upscaler.xess"))
            throw new Exception("restoring only the upscaler re-proposed the still-declined XeSS package");
        File.Delete(upscaler);
        if (!Program.FindPendingUpdates(game, "2.4.1.1", manifest, null, preferences)
            .Any(item => item.Remote.id == "net.openwg.gpu.upscaler" && item.IsNew))
            throw new Exception("an explicitly restored package was not offered after its file was removed");
        Program.RememberDeclinedMods(settings, ModOffer.Create(Program.ScanModCatalog(game, "2.4.1.1", manifest))
            .Single(offer => offer.Title == "GPU Boost"));
        preferences = Program.LoadDeclinedMods(settings);
        if (preferences.Contains("enabled:net.openwg.gpu.upscaler") ||
            Program.FindPendingUpdates(game, "2.4.1.1", manifest, null, preferences)
                .Any(item => ModOffer.DeclineGroup(item.Remote) == "openwg-group:gpu"))
            throw new Exception("declining a restored new mod did not clear its enabled preference");
    }

    private static void TestCatalogInstall(string game)
    {
        Directory.CreateDirectory(game);
        string prefs = Path.Combine(game, "declined.json");
        var entry = Package("ua.install_from_catalog", "1.0.0", "", false);
        string archive = Path.Combine(game, entry.file);
        using (var zip = ZipFile.Open(archive, ZipArchiveMode.Create))
        using (var meta = new StreamWriter(zip.CreateEntry("meta.xml").Open()))
            meta.Write("<root><id>" + entry.id + "</id></root>");
        using (var hash = SHA256.Create())
        using (var stream = File.OpenRead(archive))
            entry.sha256 = BitConverter.ToString(hash.ComputeHash(stream)).Replace("-", "");
        entry.size = new FileInfo(archive).Length;
        entry.url = archive;
        var manifest = new ManifestRoot { mods = new List<ManifestModEntry> { entry } };
        var catalog = Program.ScanModCatalog(game, "2.4.1.1", manifest);
        Program.AddDeclinedMods(prefs, new[] { ModOffer.NewOfferId(entry) });
        using (var form = new UpdateDialogForm(game, "2.4.1.1", new List<PendingModUpdate>(), null, game, catalog))
        {
            form.StartPosition = FormStartPosition.Manual;
            form.Location = new Point(-3000, -3000);
            form.Shown += (s, e) =>
            {
                using (var dialog = form.CreateCatalogDialog())
                {
                    dialog.StartPosition = FormStartPosition.Manual;
                    dialog.Location = form.Location;
                    dialog.Show(form);
                    ((Button)dialog.AcceptButton).PerformClick();
                }
                ((Button)form.AcceptButton).PerformClick();
            };
            Application.Run(form);
        }
        if (!File.Exists(catalog[0].LocalFilePath) || !Program.VerifySha256(catalog[0].LocalFilePath, entry.sha256))
            throw new Exception("the catalog did not install the package with the normal installer");
        var choices = Program.LoadDeclinedMods(prefs);
        if (choices.Contains(ModOffer.NewOfferId(entry)) || !choices.Contains("enabled:" + entry.id))
            throw new Exception("the successful install did not persist the restored preference");
    }

    private static ManifestModEntry Package(string id, string version, string directory, bool defaultChecked = true)
    {
        return new ManifestModEntry {
            id = id, version = version, file = id + "_" + version + ".wotmod", subdir = directory,
            default_checked = defaultChecked, url = "https://example.test/" + id, sha256 = new string('a', 64)
        };
    }

    private static List<PendingModUpdate> PreviewUpdates()
    {
        var bui = Package("ua.bui_customizer", "1.0.4", "");
        bui.title = "BUI Customizer";
        bui.changes = "Покращено видимість ручок і підписів у меню.";
        var core = Package("net.openwg.fix.battleresultsreplays", "1.1.0", "net.openwg");
        core.title = "OpenWG Core & Fixes (" + core.id + ")";
        core.changes = "Оновлення виправлень післябойових результатів, реплеїв та GameFace.";
        var upscaler = Package("net.openwg.gpu.upscaler", "2.8.3", "net.openwg");
        var xess = Package("net.openwg.gpu.upscaler.xess", "2.8.3", "net.openwg");
        foreach (var item in new[] { upscaler, xess })
        {
            item.title = "GPU Boost (Anti-Lag + XeSS) (" + item.id + ")";
            item.changes = "Додано підтримку Anti-Lag 2 та XeSS.\r\n\r\n" +
                "Пакети можна вибрати окремо. Зміни застосуються після наступного запуску гри.";
        }
        return new List<PendingModUpdate> {
            new PendingModUpdate { Remote = bui, InstalledVersion = "1.0.3" },
            new PendingModUpdate { Remote = core, IsNew = true },
            new PendingModUpdate { Remote = upscaler, IsNew = true },
            new PendingModUpdate { Remote = xess, IsNew = true }
        };
    }

    private static void TestGroupsAndDecline(string game, string verDir)
    {
        var packages = PreviewUpdates();
        var offers = ModOffer.Create(packages);
        var gpu = offers.Single(offer => offer.Packages.Count == 2);
        if (offers.Count != 3 || gpu.Selected.Count != 0 || gpu.Description() != gpu.Packages[0].Remote.changes)
            throw new Exception("the grouped new offer was duplicated or selected by default");

        string declinedPath = Path.Combine(game, "declined.json");
        Program.AddDeclinedMods(declinedPath, new[] { "previous.choice" });
        Program.AddDeclinedMods(declinedPath, gpu.DeclineIds());
        var declined = new JavaScriptSerializer().Deserialize<List<string>>(File.ReadAllText(declinedPath));
        if (!declined.SequenceEqual(new[] { "previous.choice", "new:openwg-group:gpu" }))
            throw new Exception("the preference was not scoped to the new offer");

        string net = Path.Combine(verDir, "net.openwg");
        Directory.CreateDirectory(net);
        File.WriteAllText(Path.Combine(verDir, "ua.bui_customizer_1.0.3.wotmod"), "x");
        var manifest = new ManifestRoot { mods = packages.Select(item => item.Remote).ToList() };
        var remaining = Program.FindPendingUpdates(game, "2.4.1.1", manifest, null, declined);
        if (remaining.Count != 2 || !remaining.Any(item => item.Remote.id == "ua.bui_customizer" && !item.IsNew))
            throw new Exception("declining GPU Boost changed an unrelated offer");

        File.WriteAllText(Path.Combine(net, "net.openwg.gpu.upscaler_2.8.2.wotmod"), "x");
        remaining = Program.FindPendingUpdates(game, "2.4.1.1", manifest, null, declined);
        if (remaining.Count != 3 || !remaining.Any(item => item.Remote.id == "net.openwg.gpu.upscaler" && !item.IsNew))
            throw new Exception("a new-offer preference blocked an installed mod update");
    }

    private sealed class BackgroundForm : UpdateDialogForm
    {
        internal BackgroundForm(string game, List<PendingModUpdate> items) : base(game, "2.4.1.1", items, null, game) { }
        protected override bool ShowWithoutActivation { get { return true; } }
    }

    private static IEnumerable<Control> ControlsOf(Control parent)
    {
        foreach (Control child in parent.Controls)
        {
            yield return child;
            foreach (Control nested in ControlsOf(child)) yield return nested;
        }
    }

    private static void TestLayout(string game, string capture)
    {
        var pending = PreviewUpdates();
        using (var form = new BackgroundForm(game, pending))
        {
            form.StartPosition = FormStartPosition.Manual;
            form.Location = new Point(-3000, -3000);
            form.Show();
            Application.DoEvents();
            if (ControlsOf(form).OfType<Button>().Any(button => button.Text == "Без модів"))
                throw new Exception("the launcher still offers its redundant no-mods button");
            var split = ControlsOf(form).OfType<SplitContainer>().Single();
            var grid = ControlsOf(split.Panel1).OfType<DataGridView>().Single();
            var text = ControlsOf(split.Panel2).OfType<TextBox>().Single();
            var decline = ControlsOf(split.Panel2).OfType<Button>().Single();
            if (!grid.Rows.Cast<DataGridViewRow>().Select(row => row.Tag as string).Where(value => value != null)
                .SequenceEqual(new[] { "ОНОВЛЕННЯ", "НОВІ МОДИ" }))
                throw new Exception("the update and new mod headings were not both displayed");
            var updateRow = grid.Rows[1];
            var update = (ModOffer)updateRow.Tag;
            if (!update.HasUpdates || !decline.Visible || !decline.Enabled || decline.BackColor.R <= decline.BackColor.G * 2 ||
                (string)updateRow.Cells["Decline"].Value != "×")
                throw new Exception("the update did not show a red removal action");

            var gpuRow = grid.Rows[3];
            var gpu = (ModOffer)gpuRow.Tag;
            var coreRow = grid.Rows[4];
            var core = (ModOffer)coreRow.Tag;
            grid.CurrentCell = gpuRow.Cells[1];
            Application.DoEvents();
            if (gpu.Packages.Count != 2 || text.Text != gpu.Description() || !text.WordWrap || !decline.Visible || !decline.Enabled)
                throw new Exception("the new mod preview did not show its description and ignore action");
            if (ControlsOf(split.Panel2).Any(control => control.Visible &&
                (control.Text == gpu.Title || control.Text.Contains("2.8.3") || control.Text.StartsWith("Новий"))))
                throw new Exception("the preview repeated metadata from the list");
            if (capture != null)
            {
                using (var bitmap = new Bitmap(form.Width, form.Height))
                {
                    form.DrawToBitmap(bitmap, new Rectangle(Point.Empty, form.Size));
                    bitmap.Save(capture);
                }
            }
            var packages = ControlsOf(split.Panel2).OfType<CheckBox>().Where(box => box.Visible).ToArray();
            if (packages.Length != 2 || packages.Any(box => box.Checked))
                throw new Exception("grouped package choices were not shown correctly");
            packages[0].Checked = true;
            Application.DoEvents();
            if (!object.Equals(gpuRow.Cells[0].Value, CheckState.Indeterminate) || gpu.Selected.Count != 1)
                throw new Exception("partial selection was not reflected in the list");
            grid.CurrentCell = coreRow.Cells[1];
            Application.DoEvents();
            if (text.Text != core.Description() || ControlsOf(split.Panel2).OfType<CheckBox>().Any(box => box.Visible))
                throw new Exception("the preview did not follow the selected mod");
            form.Size = form.MinimumSize;
            Application.DoEvents();
            if (!form.ClientRectangle.Contains(form.RectangleToClient(decline.RectangleToScreen(decline.ClientRectangle))))
                throw new Exception("the per-mod action was clipped at the minimum window size");
            var footerButtons = ControlsOf(form).OfType<Button>().Where(button => button.Visible &&
                (button.Text == "Доступні й відхилені" || button.Text == "Без оновлень" || button.Text == "Оновити й грати")).ToArray();
            if (footerButtons.Length != 3 || footerButtons.Any(button => !form.ClientRectangle.Contains(
                form.RectangleToClient(button.RectangleToScreen(button.ClientRectangle)))) ||
                footerButtons.SelectMany((button, index) => footerButtons.Skip(index + 1)
                    .Select(other => button.RectangleToScreen(button.ClientRectangle).IntersectsWith(other.RectangleToScreen(other.ClientRectangle))))
                    .Any(overlap => overlap))
                throw new Exception("the footer buttons overlapped or were clipped at the minimum window size");
            int before = text.Width;
            split.SplitterDistance += 48;
            Application.DoEvents();
            if (text.Width >= before || text.Text != core.Description())
                throw new Exception("the description did not reflow after changing proportions");
            typeof(DataGridView).GetMethod("OnCellClick", System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic)
                .Invoke(grid, new object[] { new DataGridViewCellEventArgs(grid.Columns["Decline"].Index, gpuRow.Index) });
            Application.DoEvents();
            if (grid.Rows.Cast<DataGridViewRow>().Count(row => row.Tag is ModOffer) != 2 ||
                !grid.Rows.Cast<DataGridViewRow>().Any(row => row.Tag == core) ||
                !grid.Rows.Cast<DataGridViewRow>().Any(row => row.Tag == update))
                throw new Exception("dismissing one new mod changed an unrelated mod row");
            using (var available = form.CreateCatalogDialog())
            {
                available.StartPosition = FormStartPosition.Manual;
                available.Location = new Point(-3000, -3000);
                available.Show(form);
                var mods = ControlsOf(available).OfType<ListBox>().Single();
                if (!mods.Items.Contains("GPU Boost") || !mods.Items.Contains("OpenWG Core & Fixes") || mods.Items.Contains("BUI Customizer"))
                    throw new Exception("available mods omitted dismissed or uninstalled mods, or included an installed mod");
                mods.SelectedItem = "GPU Boost";
                if (capture != null)
                {
                    using (var bitmap = new Bitmap(available.Width, available.Height))
                    {
                        available.DrawToBitmap(bitmap, new Rectangle(Point.Empty, available.Size));
                        bitmap.Save(Path.Combine(Path.GetDirectoryName(capture), "launcher-workshop-catalog.png"));
                    }
                }
                ((Button)available.AcceptButton).PerformClick();
            }
            var queued = grid.Rows.Cast<DataGridViewRow>().Select(row => row.Tag as ModOffer)
                .Single(offer => offer != null && offer.Title == "GPU Boost");
            if (queued.Selected.Count != queued.Packages.Count)
                throw new Exception("the recovery action did not select the dismissed packages for installation");
            form.Close();
            if (!File.Exists(Path.Combine(game, "update-split.txt")))
                throw new Exception("the splitter position was not saved");
        }

        foreach (var item in pending)
            item.Remote.changes = string.Join("\r\n", Enumerable.Repeat(item.Remote.changes, 25));
        using (var form = new BackgroundForm(game, pending))
        {
            form.StartPosition = FormStartPosition.Manual;
            form.Location = new Point(-3000, -3000);
            form.Show();
            Application.DoEvents();
            var text = ControlsOf(form).OfType<TextBox>().Single(box => box.Visible);
            if (text.ScrollBars != ScrollBars.Vertical || text.Text.Length < 1000)
                throw new Exception("long descriptions became truncated or unscrollable");
            var split = ControlsOf(form).OfType<SplitContainer>().Single();
            int saved = int.Parse(File.ReadAllText(Path.Combine(game, "update-split.txt")));
            if (Math.Abs(split.SplitterDistance * 100.0 / split.Width - saved) > 1)
                throw new Exception("the saved proportions were not restored");
        }
    }
}
