using System;
using System.Collections;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Security.Cryptography;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using WotModLauncher;

public static class LauncherUiTests
{
    private static int assertions;
    private static string testRoot;

    [STAThread]
    public static int Main(string[] args)
    {
        try
        {
            testRoot = Environment.GetEnvironmentVariable("WOT_UI_TEST_HOME");
            if (string.IsNullOrEmpty(testRoot) || !Program.LauncherDir.StartsWith(testRoot + Path.DirectorySeparatorChar, StringComparison.Ordinal))
                throw new InvalidOperationException("Run with isolated HOME and XDG_DATA_HOME under WOT_UI_TEST_HOME.");
            Directory.CreateDirectory(testRoot);
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            TestSelectionAndDescriptions();
            TestDeclineOneMod();
            TestEmptyAndLegacyManifest();
            TestLocalUpdate(false);
            TestLocalUpdate(true);
            Console.WriteLine("PASS: " + assertions + " assertions");
            return 0;
        }
        catch (Exception error)
        {
            Console.Error.WriteLine(error);
            return 1;
        }
    }

    private static void Assert(bool value, string message)
    {
        assertions++;
        if (!value) throw new InvalidOperationException(message);
    }

    private static object Field(object target, string name)
    {
        Type type = target.GetType();
        while (type != null)
        {
            FieldInfo field = type.GetField(name, BindingFlags.Instance | BindingFlags.NonPublic);
            if (field != null) return field.GetValue(target);
            type = type.BaseType;
        }
        throw new MissingFieldException(name);
    }

    private static object Call(object target, string name, params object[] args)
    {
        return typeof(UpdateDialogForm).GetMethod(name, BindingFlags.Instance | BindingFlags.NonPublic).Invoke(target, args);
    }

    private sealed class TestDialog : UpdateDialogForm
    {
        public bool DeclineAnswer;
        public PendingModUpdate ConfirmedItem;
        public string UpdateError;

        public TestDialog(string path, List<PendingModUpdate> items) : base(path, "2.4.1.1", items, null) { }
        protected override bool ConfirmDecline(PendingModUpdate item) { ConfirmedItem = item; return DeclineAnswer; }
        protected override void ShowUpdateFailure(string reason) { UpdateError = reason; }
    }

    public sealed class ModFixture : ManifestModEntry
    {
        public string[] readme_features { get; set; }
    }

    private static List<PendingModUpdate> Items()
    {
        string[] ids = { "server_online", "platoon_autostart", "spectator_teammate_hud", "research_button", "openwg_gpu", "appropriate_locker" };
        string[] old = { "1.1.3", "1.0.5", "1.0.11", "1.2.4", null, null };
        List<PendingModUpdate> items = new List<PendingModUpdate>();
        JavaScriptSerializer json = new JavaScriptSerializer();
        for (int i = 0; i < ids.Length; i++)
        {
            ModFixture remote = json.Deserialize<ModFixture>(File.ReadAllText("src/mods/" + ids[i] + "/mod.json"));
            remote.summary = remote.readme_features != null && remote.readme_features.Length > 0 ? remote.readme_features[0] : remote.description;
            items.Add(new PendingModUpdate { Remote = remote, InstalledVersion = old[i], IsNew = i >= 4 });
        }
        return items;
    }

    private static Control Find(Control root, Predicate<Control> match)
    {
        if (match(root)) return root;
        foreach (Control child in root.Controls)
        {
            Control found = Find(child, match);
            if (found != null) return found;
        }
        return null;
    }

    private static void Click(Control control)
    {
        typeof(Control).GetMethod("OnClick", BindingFlags.Instance | BindingFlags.NonPublic)
            .Invoke(control, new object[] { EventArgs.Empty });
        Application.DoEvents();
    }

    private static int CheckedCount(UpdateDialogForm form)
    {
        return ((ICollection)Call(form, "GetChecked")).Count;
    }

    private static void Capture(UpdateDialogForm form, string name)
    {
        string output = Environment.GetEnvironmentVariable("WOT_UI_SCREENSHOTS");
        if (string.IsNullOrEmpty(output)) return;
        Directory.CreateDirectory(output);
        form.Refresh();
        Application.DoEvents();
        using (Bitmap bitmap = new Bitmap(form.ClientSize.Width, form.ClientSize.Height))
        using (Graphics graphics = Graphics.FromImage(bitmap))
        {
            graphics.CopyFromScreen(form.PointToScreen(Point.Empty), Point.Empty, form.ClientSize);
            bitmap.Save(Path.Combine(output, name + ".png"));
        }
    }

    private static void TestSelectionAndDescriptions()
    {
        List<PendingModUpdate> items = Items();
        using (UpdateDialogForm form = new UpdateDialogForm(@"D:\Games\World_of_Tanks_EU", "2.4.1.1", items, null))
        {
            form.ClientSize = new Size(1440, 1000);
            form.Show();
            Application.DoEvents();
            Assert(CheckedCount(form) == 4, "Only installed updates should be checked initially.");
            Label description = (Label)Field(form, "lblDescription");
            Label changes = (Label)Field(form, "lblChanges");
            Assert(description.Text == items[0].Remote.description, "Description must come from metadata, not changes.");
            Assert(changes.Text == items[0].Remote.changes, "Release changes must remain separate.");
            IDictionary rows = (IDictionary)Field(form, "rows");
            Control research = (Control)rows[items[3]];
            Click(Find(research, c => c is Label && c.Text == "Quick Research"));
            Assert(CheckedCount(form) == 4, "Reading a mod must not change its checkbox.");
            Assert(description.Text == items[3].Remote.description, "Clicking a title must show that mod's actual description.");
            Call(form, "SetAllChecked", false);
            Assert(CheckedCount(form) == 0, "Clear all must include updates and new mods.");
            Assert(((Button)Field(form, "btnUpdate")).Text == "Грати", "No selected downloads should mean play only.");
            Call(form, "SetAllChecked", true);
            Assert(CheckedCount(form) == 6, "Select all must include both groups.");
            Call(form, "SetAllChecked", false);
            ((CheckBox)Field(rows[items[0]], "check")).Checked = true;
            ((CheckBox)Field(rows[items[1]], "check")).Checked = true;
            ((CheckBox)Field(rows[items[3]], "check")).Checked = true;
            ((CheckBox)Field(rows[items[4]], "check")).Checked = true;
            Call(form, "SelectItem", items[0]);
            Capture(form, "launcher-desktop");
            foreach (int width in new[] { 1100, 1280, 1440 })
            {
                form.Size = new Size(width, 760);
                Application.DoEvents();
                foreach (string name in new[] { "btnUpdate", "btnSkip", "btnOther" })
                {
                    Control button = (Control)Field(form, name);
                    Point position = form.PointToClient(button.PointToScreen(Point.Empty));
                    Assert(form.ClientRectangle.Contains(new Rectangle(position, button.Size)), name + " clipped at width " + width);
                }
                Assert(description.Height >= description.PreferredHeight, "Description must wrap rather than clip vertically.");
            }
            form.Size = new Size(1100, 680);
            Application.DoEvents();
            Call(form, "SelectItem", items[5]);
            Assert(((Label)Field(form, "lblWarning")).Visible, "Risk note must remain visible for flagged mods.");
            Capture(form, "launcher-minimum-risk");
            Assert(((Panel)Field(form, "modScroll")).VerticalScroll.Visible, "Small windows must scroll mod rows.");
            Assert(((Button)Field(form, "btnUpdate")).Enabled, "Primary action must remain usable in small windows.");
        }
    }

    private static void TestDeclineOneMod()
    {
        List<PendingModUpdate> items = Items();
        using (TestDialog form = new TestDialog(testRoot, items))
        {
            form.Show();
            Application.DoEvents();
            IDictionary rows = (IDictionary)Field(form, "rows");
            Button decline = (Button)Find((Control)rows[items[5]], c => c.Name == "DeclineMod");
            Assert(decline != null && decline.Image != null && decline.Text == "", "Every row needs an icon-only decline button.");
            Call(form, "SetAllChecked", true);
            form.DeclineAnswer = false;
            decline.PerformClick();
            Assert(form.ConfirmedItem == items[5], "Confirmation must name the clicked mod.");
            Assert(rows.Count == 6 && CheckedCount(form) == 6, "Cancelling decline must preserve every selection.");
            Call(form, "SelectItem", items[5]);
            form.DeclineAnswer = true;
            decline.PerformClick();
            Assert(rows.Count == 5 && CheckedCount(form) == 5, "Decline must remove only the clicked row even when all are checked.");
            List<string> declined = Program.LoadDeclinedMods();
            Assert(declined.Count == 1 && declined[0] == items[5].Remote.id, "Only the clicked mod ID may be persisted.");
            Assert(((Label)Field(form, "lblDetailsTitle")).Text == "Smart Server", "Declining the read mod must select an available mod.");
            foreach (PendingModUpdate item in items.GetRange(0, 5)) Call(form, "RemoveItem", item);
            Assert(rows.Count == 0 && ((Label)Field(form, "lblEmpty")).Visible, "Last declined row must leave a usable empty state.");
            Capture(form, "launcher-empty");
        }
    }

    private static void TestEmptyAndLegacyManifest()
    {
        using (UpdateDialogForm form = new UpdateDialogForm(testRoot, "2.4.1.1", new List<PendingModUpdate>(), new SelfUpdateState { version = "1.4.4.1" }))
        {
            form.Show();
            Application.DoEvents();
            Assert(((CheckBox)Field(form, "chkLauncher")).Checked, "Standalone launcher updates must remain selectable.");
            Assert(((Button)Field(form, "btnSkip")).Visible, "Launcher-only update must retain the skip action.");
            Assert(!((Panel)Field(form, "reading")).Visible, "Empty mod list must not invite selecting a nonexistent mod.");
            Capture(form, "launcher-self-update");
            ((Button)Field(form, "btnSkip")).PerformClick();
            Assert(!form.ApplyLauncherUpdate, "Skip must not schedule the launcher update.");
        }
        ManifestModEntry legacy = new JavaScriptSerializer().Deserialize<ManifestModEntry>("{\"id\":\"legacy\",\"title\":\"Legacy\",\"version\":\"1.0\",\"changes\":\"Only changes\"}");
        using (UpdateDialogForm form = new UpdateDialogForm(testRoot, "2.4.1.1", new List<PendingModUpdate> { new PendingModUpdate { Remote = legacy, IsNew = true } }, null))
        {
            form.Show();
            Application.DoEvents();
            Assert(((Label)Field(form, "lblDescription")).Text.Contains("відсутній"), "Legacy manifests must not invent a description from changes.");
            Assert(((Label)Field(form, "lblChanges")).Text == "Only changes", "Legacy changes must still be readable.");
            Assert(CheckedCount(form) == 0, "New mods remain opt-in.");
            ((Button)Field(form, "btnOther")).PerformClick();
            ContextMenuStrip menu = (ContextMenuStrip)Field(form, "otherMenu");
            menu.Items[0].PerformClick();
            Assert(form.LaunchWithoutMods, "Other actions must still support launching without mods.");
        }
    }

    private static PendingModUpdate Package(string root, string id, bool isNew)
    {
        string source = Path.Combine(root, id + "_2.0.wotmod");
        using (ZipArchive archive = ZipFile.Open(source, ZipArchiveMode.Create))
        using (StreamWriter writer = new StreamWriter(archive.CreateEntry("meta.xml").Open()))
            writer.Write("<root><id>" + id + "</id><version>2.0</version></root>");
        string hash;
        using (SHA256 sha = SHA256.Create())
            hash = BitConverter.ToString(sha.ComputeHash(File.ReadAllBytes(source))).Replace("-", "").ToLowerInvariant();
        string mods = Path.Combine(root, "game", "mods", "2.4.1.1");
        Directory.CreateDirectory(mods);
        string local = Path.Combine(mods, id + (isNew ? "_2.0" : "_1.0") + ".wotmod");
        if (!isNew) File.WriteAllText(local, "original installed bytes");
        return new PendingModUpdate
        {
            InstalledVersion = isNew ? null : "1.0",
            IsNew = isNew,
            LocalFilePath = local,
            Remote = new ManifestModEntry { id = id, title = id, file = id + "_2.0.wotmod", version = "2.0", url = source, size = new FileInfo(source).Length, sha256 = hash }
        };
    }

    private static void TestLocalUpdate(bool corrupt)
    {
        string root = Path.Combine(testRoot, corrupt ? "failed-update" : "successful-update");
        Directory.CreateDirectory(root);
        PendingModUpdate existing = Package(root, "test.existing", false);
        PendingModUpdate added = Package(root, "test.added", true);
        if (corrupt) added.Remote.sha256 = new string('0', 64);
        using (TestDialog form = new TestDialog(Path.Combine(root, "game"), new List<PendingModUpdate> { existing, added }))
        {
            form.Show();
            Application.DoEvents();
            Call(form, "SetAllChecked", true);
            Action update = () =>
            {
                Call(form, "StartUpdateProcess", new List<PendingModUpdate> { existing, added });
                DateTime deadline = DateTime.UtcNow.AddSeconds(15);
                while (!form.IsDisposed && DateTime.UtcNow < deadline)
                {
                    Application.DoEvents();
                    System.Threading.Thread.Sleep(10);
                }
                Assert(form.IsDisposed, "Local update must finish without launching a game process.");
            };
            update();
            Assert(corrupt == !string.IsNullOrEmpty(form.UpdateError), "Verification errors must reach the error dialog.");
        }
        if (corrupt)
        {
            Assert(File.ReadAllText(existing.LocalFilePath) == "original installed bytes", "Failed verification must preserve the installed file.");
            Assert(!File.Exists(added.LocalFilePath), "Failed verification must not install any new mod.");
            Assert(!File.Exists(Path.Combine(Path.GetDirectoryName(existing.LocalFilePath), existing.Remote.file)), "No partial replacement before all packages verify.");
        }
        else
        {
            Assert(!File.Exists(existing.LocalFilePath), "Successful replacement must remove the old version.");
            Assert(File.Exists(added.LocalFilePath), "Selected new mod must be installed.");
            string[] backups = Directory.GetFiles(Path.Combine(root, "game", ".backups"), "*.wotmod", SearchOption.AllDirectories);
            Assert(backups.Length == 1 && File.ReadAllText(backups[0]) == "original installed bytes", "Backup must contain the original installed bytes.");
        }
    }
}
