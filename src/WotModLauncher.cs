using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Text;
using System.IO;
using System.IO.Compression;
using System.Net;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Forms;

[assembly: AssemblyTitle("WoT Modpack Launcher")]
[assembly: AssemblyDescription("Лаунчер автооновлення модифікацій World of Tanks")]
[assembly: AssemblyCompany("Niedvin")]
[assembly: AssemblyProduct("WoT Modpack by Niedvin")]
[assembly: AssemblyCopyright("Copyright © 2026 Niedvin")]
[assembly: AssemblyFileVersion("1.0.0.0")]
[assembly: AssemblyVersion("1.0.0.0")]

namespace WotModLauncher
{
    public class LauncherConfig
    {
        public string game_path { get; set; }
        public bool hijack_shortcuts { get; set; }
    }

    public class ManifestLauncherInfo
    {
        public string version { get; set; }
        public string url { get; set; }
        public string sha256 { get; set; }
    }

    public class ManifestModEntry
    {
        public string id { get; set; }
        public string title { get; set; }
        public string version { get; set; }
        public string file { get; set; }
        public string subdir { get; set; }
        public string url { get; set; }
        public string sha256 { get; set; }
        public long size { get; set; }
        public string changes { get; set; }
    }

    public class ManifestRoot
    {
        public int schema { get; set; }
        public string pack_version { get; set; }
        public string game_version { get; set; }
        public ManifestLauncherInfo launcher { get; set; }
        public List<ManifestModEntry> mods { get; set; }
    }

    public class PendingModUpdate
    {
        public ManifestModEntry Remote { get; set; }
        public string LocalFilePath { get; set; }
        public string InstalledVersion { get; set; }
        public float HoverProgress;
    }

    public static class Program
    {
        public const string RepoOwner = "Niedvin";
        public const string RepoName = "WOT-Mod-Launcher";
        public const string ManifestUrl = "https://github.com/Niedvin/WOT-Mod-Launcher/releases/latest/download/manifest.json";
        public const string LauncherVersion = "1.0.0";

        public static string LauncherDir
        {
            get { return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "WotModpack"); }
        }

        [STAThread]
        public static int Main(string[] args)
        {
            // .NET 4.0 defaults to TLS 1.0 which GitHub drops — 2026-10-24
            ServicePointManager.SecurityProtocol = (SecurityProtocolType)3072;
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);

            CleanupSelfUpdateOldBinary();

            bool checkOnly = false;
            string argGamePath = null;
            for (int i = 0; i < args.Length; i++)
            {
                if (args[i] == "--check-only") checkOnly = true;
                else if (args[i] == "--game" && i + 1 < args.Length) argGamePath = args[++i];
            }

            if (!checkOnly && IsGameAlreadyRunning())
                return 0;

            LauncherConfig cfg = LoadConfig(argGamePath);
            if (cfg == null || string.IsNullOrEmpty(cfg.game_path) || !Directory.Exists(cfg.game_path))
            {
                if (!checkOnly && !string.IsNullOrEmpty(argGamePath))
                    LaunchGame(argGamePath);
                return 1;
            }

            if (cfg.hijack_shortcuts)
                EnsureShortcutsRedirected(cfg.game_path);

            string gameVer = DetectGameVersion(cfg.game_path);
            if (!string.IsNullOrEmpty(gameVer))
                SyncVersionFolderIfEmpty(cfg.game_path, gameVer);

            ManifestRoot manifest = FetchManifestWithTimeout(4000);
            if (manifest != null)
            {
                TryStageSelfUpdate(manifest.launcher);
                List<PendingModUpdate> updates = FindPendingUpdates(cfg.game_path, gameVer, manifest);
                if (updates.Count > 0)
                {
                    using (var form = new UpdateDialogForm(cfg.game_path, gameVer, updates))
                    {
                        Application.Run(form);
                    }
                }
            }

            if (!checkOnly)
                LaunchGame(cfg.game_path);

            return 0;
        }

        private static void CleanupSelfUpdateOldBinary()
        {
            try
            {
                string exe = Assembly.GetExecutingAssembly().Location;
                string oldFile = exe + ".old";
                if (File.Exists(oldFile)) File.Delete(oldFile);
            }
            catch { }
        }

        private static bool IsGameAlreadyRunning()
        {
            try
            {
                return Process.GetProcessesByName("WorldOfTanks").Length > 0
                    || Process.GetProcessesByName("WorldOfTanks32").Length > 0;
            }
            catch { return false; }
        }

        private static LauncherConfig LoadConfig(string overrideGamePath)
        {
            LauncherConfig cfg = new LauncherConfig { hijack_shortcuts = true };
            try
            {
                string cfgPath = Path.Combine(LauncherDir, "launcher.json");
                if (File.Exists(cfgPath))
                {
                    var ser = new JavaScriptSerializer();
                    cfg = ser.Deserialize<LauncherConfig>(File.ReadAllText(cfgPath, Encoding.UTF8)) ?? cfg;
                }
            }
            catch { }

            if (!string.IsNullOrEmpty(overrideGamePath))
                cfg.game_path = overrideGamePath;

            if (string.IsNullOrEmpty(cfg.game_path) || !Directory.Exists(cfg.game_path))
            {
                string baseDir = AppDomain.CurrentDomain.BaseDirectory.TrimEnd('\\', '/');
                if (File.Exists(Path.Combine(baseDir, "WorldOfTanks.exe")) && File.Exists(Path.Combine(baseDir, "version.xml")))
                    cfg.game_path = baseDir;
            }
            return cfg;
        }

        public static string DetectGameVersion(string gamePath)
        {
            try
            {
                string verXml = Path.Combine(gamePath, "version.xml");
                if (File.Exists(verXml))
                {
                    string content = File.ReadAllText(verXml, Encoding.UTF8);
                    Match m = Regex.Match(content, @"<version>\s*v\.([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)");
                    if (m.Success) return m.Groups[1].Value;
                }
                string modsDir = Path.Combine(gamePath, "mods");
                if (Directory.Exists(modsDir))
                {
                    Version maxV = new Version(0, 0, 0, 0);
                    string best = null;
                    foreach (string dir in Directory.GetDirectories(modsDir))
                    {
                        string name = Path.GetFileName(dir);
                        if (Regex.IsMatch(name, @"^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$"))
                        {
                            Version v;
                            if (Version.TryParse(name, out v) && v > maxV)
                            {
                                maxV = v;
                                best = name;
                            }
                        }
                    }
                    if (best != null) return best;
                }
            }
            catch { }
            return null;
        }

        public static void SyncVersionFolderIfEmpty(string gamePath, string activeVer)
        {
            try
            {
                string modsRoot = Path.Combine(gamePath, "mods");
                if (!Directory.Exists(modsRoot)) return;
                string targetDir = Path.Combine(modsRoot, activeVer);
                if (Directory.Exists(targetDir) && Directory.GetFiles(targetDir, "*.wotmod", SearchOption.AllDirectories).Length > 0)
                    return;

                Version bestV = new Version(0, 0, 0, 0);
                string sourceDir = null;
                foreach (string d in Directory.GetDirectories(modsRoot))
                {
                    string name = Path.GetFileName(d);
                    if (name == activeVer || !Regex.IsMatch(name, @"^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$")) continue;
                    if (Directory.GetFiles(d, "*.wotmod", SearchOption.AllDirectories).Length == 0) continue;
                    Version v;
                    if (Version.TryParse(name, out v) && v > bestV)
                    {
                        bestV = v;
                        sourceDir = d;
                    }
                }
                if (sourceDir == null) return;

                foreach (string file in Directory.GetFiles(sourceDir, "*", SearchOption.AllDirectories))
                {
                    string rel = file.Substring(sourceDir.Length).TrimStart('\\', '/');
                    string dst = Path.Combine(targetDir, rel);
                    Directory.CreateDirectory(Path.GetDirectoryName(dst));
                    File.Copy(file, dst, true);
                }
            }
            catch { }
        }

        private static ManifestRoot FetchManifestWithTimeout(int timeoutMs)
        {
            try
            {
                HttpWebRequest req = (HttpWebRequest)WebRequest.Create(ManifestUrl + "?t=" + Environment.TickCount);
                req.UserAgent = "WotModLauncher/" + LauncherVersion;
                req.Timeout = timeoutMs;
                req.ReadWriteTimeout = timeoutMs;
                req.AllowAutoRedirect = true;
                using (HttpWebResponse resp = (HttpWebResponse)req.GetResponse())
                using (Stream s = resp.GetResponseStream())
                using (StreamReader sr = new StreamReader(s, Encoding.UTF8))
                {
                    string json = sr.ReadToEnd();
                    var ser = new JavaScriptSerializer();
                    return ser.Deserialize<ManifestRoot>(json);
                }
            }
            catch
            {
                return null;
            }
        }

        private static void TryStageSelfUpdate(ManifestLauncherInfo info)
        {
            if (info == null || string.IsNullOrEmpty(info.version) || string.IsNullOrEmpty(info.url))
                return;
            try
            {
                Version curV = ParseVer(LauncherVersion);
                Version remV = ParseVer(info.version);
                if (curV == null || remV == null || remV <= curV) return;

                string exe = Assembly.GetExecutingAssembly().Location;
                string tmp = exe + ".new";
                HttpWebRequest req = (HttpWebRequest)WebRequest.Create(info.url);
                req.UserAgent = "WotModLauncher/" + LauncherVersion;
                req.Timeout = 8000;
                req.ReadWriteTimeout = 8000;
                using (HttpWebResponse resp = (HttpWebResponse)req.GetResponse())
                using (Stream s = resp.GetResponseStream())
                using (FileStream fs = File.Create(tmp))
                {
                    s.CopyTo(fs);
                }
                if (!string.IsNullOrEmpty(info.sha256) && !VerifySha256(tmp, info.sha256))
                {
                    File.Delete(tmp);
                    return;
                }
                string oldPath = exe + ".old";
                if (File.Exists(oldPath)) File.Delete(oldPath);
                File.Move(exe, oldPath);
                File.Move(tmp, exe);
            }
            catch { }
        }

        public static List<PendingModUpdate> FindPendingUpdates(string gamePath, string gameVer, ManifestRoot manifest)
        {
            var result = new List<PendingModUpdate>();
            if (manifest == null || manifest.mods == null || string.IsNullOrEmpty(gameVer))
                return result;

            string verRoot = Path.Combine(gamePath, "mods", gameVer);
            if (!Directory.Exists(verRoot)) return result;

            foreach (ManifestModEntry entry in manifest.mods)
            {
                if (entry == null || string.IsNullOrEmpty(entry.id) || string.IsNullOrEmpty(entry.version))
                    continue;

                string searchDir = string.IsNullOrEmpty(entry.subdir)
                    ? verRoot
                    : Path.Combine(verRoot, entry.subdir.Replace('/', Path.DirectorySeparatorChar));

                if (!Directory.Exists(searchDir)) continue;

                string rx = "^" + Regex.Escape(entry.id) + @"_([0-9]+(?:\.[0-9]+)*)\.wotmod$";
                string foundFile = null;
                Version foundVer = null;

                foreach (string f in Directory.GetFiles(searchDir, entry.id + "_*.wotmod", SearchOption.TopDirectoryOnly))
                {
                    string name = Path.GetFileName(f);
                    Match m = Regex.Match(name, rx, RegexOptions.IgnoreCase);
                    if (m.Success)
                    {
                        Version v = ParseVer(m.Groups[1].Value);
                        if (v != null && (foundVer == null || v > foundVer))
                        {
                            foundVer = v;
                            foundFile = f;
                        }
                    }
                }

                if (foundFile == null || foundVer == null) continue;

                Version remoteVer = ParseVer(entry.version);
                if (remoteVer != null && remoteVer > foundVer)
                {
                    result.Add(new PendingModUpdate
                    {
                        Remote = entry,
                        LocalFilePath = foundFile,
                        InstalledVersion = foundVer.ToString()
                    });
                }
            }
            return result;
        }

        public static Version ParseVer(string s)
        {
            if (string.IsNullOrEmpty(s)) return null;
            Version v;
            return Version.TryParse(s.TrimStart('v', 'V'), out v) ? v : null;
        }

        public static bool VerifySha256(string filePath, string expectedHex)
        {
            if (!File.Exists(filePath)) return false;
            using (var sha = SHA256.Create())
            using (var fs = File.OpenRead(filePath))
            {
                byte[] hash = sha.ComputeHash(fs);
                StringBuilder sb = new StringBuilder(hash.Length * 2);
                foreach (byte b in hash) sb.Append(b.ToString("x2"));
                return string.Equals(sb.ToString(), expectedHex.Trim(), StringComparison.OrdinalIgnoreCase);
            }
        }

        public static bool VerifyWotmodArchive(string filePath, string expectedId)
        {
            try
            {
                FileInfo fi = new FileInfo(filePath);
                if (!fi.Exists || fi.Length < 64) return false;
                using (ZipArchive zip = ZipFile.OpenRead(filePath))
                {
                    ZipArchiveEntry meta = zip.GetEntry("meta.xml");
                    if (meta == null) return false;
                    using (StreamReader sr = new StreamReader(meta.Open(), Encoding.UTF8))
                    {
                        string xml = sr.ReadToEnd();
                        return Regex.IsMatch(xml, @"<id>\s*" + Regex.Escape(expectedId) + @"\s*</id>", RegexOptions.IgnoreCase);
                    }
                }
            }
            catch { return false; }
        }

        private static void EnsureShortcutsRedirected(string gamePath)
        {
            try
            {
                string launcherExe = Path.Combine(LauncherDir, "WotModLauncher.exe");
                if (!File.Exists(launcherExe)) return;

                string[] candidateShortcuts = new string[]
                {
                    Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), "World of Tanks EU.lnk"),
                    Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), @"Microsoft\Windows\Start Menu\Programs\Wargaming.net\World_of_Tanks_EU\World of Tanks EU.lnk")
                };

                Type shellType = Type.GetTypeFromProgID("WScript.Shell");
                if (shellType == null) return;
                object shell = Activator.CreateInstance(shellType);

                foreach (string lnkPath in candidateShortcuts)
                {
                    if (!File.Exists(lnkPath)) continue;
                    object sc = shellType.InvokeMember("CreateShortcut", BindingFlags.InvokeMethod, null, shell, new object[] { lnkPath });
                    string target = (string)sc.GetType().InvokeMember("TargetPath", BindingFlags.GetProperty, null, sc, null) ?? "";
                    if (target.EndsWith("wgc_api.exe", StringComparison.OrdinalIgnoreCase))
                    {
                        string bkpDir = Path.Combine(LauncherDir, "shortcuts_backup");
                        Directory.CreateDirectory(bkpDir);
                        string bkpName = (lnkPath.IndexOf("Start Menu", StringComparison.OrdinalIgnoreCase) >= 0 ? "startmenu_" : "desktop_") + Path.GetFileName(lnkPath);
                        string bkpPath = Path.Combine(bkpDir, bkpName);
                        if (!File.Exists(bkpPath)) File.Copy(lnkPath, bkpPath, false);

                        string iconFile = Path.Combine(gamePath, "game_metadata", "game.ico");
                        if (!File.Exists(iconFile)) iconFile = Path.Combine(gamePath, "WorldOfTanks.exe");

                        sc.GetType().InvokeMember("TargetPath", BindingFlags.SetProperty, null, sc, new object[] { launcherExe });
                        sc.GetType().InvokeMember("Arguments", BindingFlags.SetProperty, null, sc, new object[] { "" });
                        sc.GetType().InvokeMember("WorkingDirectory", BindingFlags.SetProperty, null, sc, new object[] { gamePath });
                        sc.GetType().InvokeMember("IconLocation", BindingFlags.SetProperty, null, sc, new object[] { iconFile + ",0" });
                        sc.GetType().InvokeMember("Save", BindingFlags.InvokeMethod, null, sc, null);
                    }
                }
            }
            catch { }
        }

        public static void LaunchGame(string gamePath)
        {
            if (string.IsNullOrEmpty(gamePath)) return;
            string exe = Path.Combine(gamePath, "WorldOfTanks.exe");
            if (!File.Exists(exe))
                exe = Path.Combine(gamePath, "win64", "WorldOfTanks.exe");

            if (File.Exists(exe))
            {
                try
                {
                    Process.Start(new ProcessStartInfo
                    {
                        FileName = exe,
                        WorkingDirectory = gamePath
                    });
                    return;
                }
                catch { }
            }

            string wgcApi = Path.Combine(gamePath, "wgc_api.exe");
            if (File.Exists(wgcApi))
            {
                try
                {
                    Process.Start(new ProcessStartInfo
                    {
                        FileName = wgcApi,
                        Arguments = "--open",
                        WorkingDirectory = gamePath
                    });
                }
                catch { }
            }
        }
    }

    public class UpdateDialogForm : Form
    {
        private readonly string gamePath;
        private readonly string gameVer;
        private readonly List<PendingModUpdate> updates;

        private readonly System.Windows.Forms.Timer animTimer;
        private float fadeProgress = 0f;
        private float btnUpdateHover = 0f;
        private float btnSkipHover = 0f;
        private float btnCloseHover = 0f;
        private bool isHoverUpdate = false;
        private bool isHoverSkip = false;
        private bool isHoverClose = false;
        private int hoveredCardIndex = -1;
        private int scrollOffset = 0;
        private int maxScroll = 0;

        private bool isUpdating = false;
        private float targetProgress = 0f;
        private float displayProgress = 0f;
        private float shimmerOffset = 0f;
        private string statusText = "Готово до швидкого оновлення";

        private bool dragging = false;
        private Point dragStart;

        private Rectangle rectHeader;
        private Rectangle rectClose;
        private Rectangle rectListViewport;
        private Rectangle rectBtnUpdate;
        private Rectangle rectBtnSkip;
        private Rectangle rectProgressBar;

        // Pre-allocated GDI+ resources keep 60 FPS OnPaint zero-alloc — 2026-10-24
        private readonly Font fontTitle = new Font("Segoe UI", 13.5f, FontStyle.Bold, GraphicsUnit.Point);
        private readonly Font fontSubtitle = new Font("Segoe UI", 9f, FontStyle.Regular, GraphicsUnit.Point);
        private readonly Font fontModTitle = new Font("Segoe UI", 10f, FontStyle.Bold, GraphicsUnit.Point);
        private readonly Font fontBadge = new Font("Consolas", 9f, FontStyle.Bold, GraphicsUnit.Point);
        private readonly Font fontChanges = new Font("Segoe UI", 8.8f, FontStyle.Regular, GraphicsUnit.Point);
        private readonly Font fontButton = new Font("Segoe UI", 10f, FontStyle.Bold, GraphicsUnit.Point);
        private readonly Font fontStatus = new Font("Segoe UI", 8.8f, FontStyle.Regular, GraphicsUnit.Point);

        private readonly SolidBrush brushBg = new SolidBrush(Color.FromArgb(18, 22, 31));
        private readonly SolidBrush brushHeader = new SolidBrush(Color.FromArgb(24, 30, 43));
        private readonly SolidBrush brushGold = new SolidBrush(Color.FromArgb(229, 154, 40));
        private readonly SolidBrush brushTextMain = new SolidBrush(Color.FromArgb(240, 244, 250));
        private readonly SolidBrush brushTextMuted = new SolidBrush(Color.FromArgb(148, 160, 180));
        private readonly SolidBrush brushBadgeBg = new SolidBrush(Color.FromArgb(32, 54, 44));
        private readonly SolidBrush brushBadgeFg = new SolidBrush(Color.FromArgb(110, 231, 160));
        private readonly Pen penBorder = new Pen(Color.FromArgb(46, 56, 76), 1f);
        private readonly Pen penAccentTop = new Pen(Color.FromArgb(229, 154, 40), 2f);

        private const int CardHeight = 68;
        private const int CardGap = 8;

        public UpdateDialogForm(string gamePath, string gameVer, List<PendingModUpdate> updates)
        {
            this.gamePath = gamePath;
            this.gameVer = gameVer;
            this.updates = updates;

            this.FormBorderStyle = FormBorderStyle.None;
            this.StartPosition = FormStartPosition.CenterScreen;
            this.Size = new Size(560, 440);
            this.DoubleBuffered = true;
            this.SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.UserPaint | ControlStyles.OptimizedDoubleBuffer | ControlStyles.ResizeRedraw, true);
            this.BackColor = Color.FromArgb(18, 22, 31);
            this.Text = "WoT Modpack — Оновлення модів";
            this.TopMost = true;
            this.Opacity = 0.0;

            try
            {
                string ico = Path.Combine(gamePath, "game_metadata", "game.ico");
                if (File.Exists(ico)) this.Icon = new Icon(ico);
            }
            catch { }

            ComputeLayout();

            animTimer = new System.Windows.Forms.Timer();
            animTimer.Interval = 15;
            animTimer.Tick += OnAnimTick;
            this.Shown += (s, e) => animTimer.Start();
        }

        protected override CreateParams CreateParams
        {
            get
            {
                // CS_DROPSHADOW 0x00020000 gives frameless form native OS shadow — 2026-10-24
                CreateParams cp = base.CreateParams;
                cp.ClassStyle |= 0x00020000;
                return cp;
            }
        }

        private void ComputeLayout()
        {
            rectHeader = new Rectangle(0, 0, Width, 68);
            rectClose = new Rectangle(Width - 42, 14, 28, 28);
            rectListViewport = new Rectangle(20, 80, Width - 40, Height - 185);
            rectProgressBar = new Rectangle(20, Height - 92, Width - 40, 14);
            rectBtnUpdate = new Rectangle(20, Height - 60, 315, 42);
            rectBtnSkip = new Rectangle(348, Height - 60, Width - 368, 42);

            int totalListHeight = updates.Count * CardHeight + Math.Max(0, updates.Count - 1) * CardGap;
            maxScroll = Math.Max(0, totalListHeight - rectListViewport.Height);
        }

        private static float Lerp(float cur, float target, float speed)
        {
            float diff = target - cur;
            if (Math.Abs(diff) < 0.004f) return target;
            return cur + diff * speed;
        }

        private void OnAnimTick(object sender, EventArgs e)
        {
            bool dirty = false;

            if (fadeProgress < 1f)
            {
                fadeProgress = Math.Min(1f, fadeProgress + 0.085f);
                float eased = 1f - (float)Math.Pow(1f - fadeProgress, 3);
                this.Opacity = eased;
                dirty = true;
            }

            float nextUpd = Lerp(btnUpdateHover, isHoverUpdate && !isUpdating ? 1f : 0f, 0.22f);
            float nextSkip = Lerp(btnSkipHover, isHoverSkip && !isUpdating ? 1f : 0f, 0.22f);
            float nextClose = Lerp(btnCloseHover, isHoverClose && !isUpdating ? 1f : 0f, 0.22f);
            if (nextUpd != btnUpdateHover || nextSkip != btnSkipHover || nextClose != btnCloseHover)
            {
                btnUpdateHover = nextUpd;
                btnSkipHover = nextSkip;
                btnCloseHover = nextClose;
                dirty = true;
            }

            for (int i = 0; i < updates.Count; i++)
            {
                float target = (i == hoveredCardIndex) ? 1f : 0f;
                float next = Lerp(updates[i].HoverProgress, target, 0.2f);
                if (next != updates[i].HoverProgress)
                {
                    updates[i].HoverProgress = next;
                    dirty = true;
                }
            }

            if (isUpdating)
            {
                displayProgress = Lerp(displayProgress, targetProgress, 0.18f);
                shimmerOffset += 6f;
                if (shimmerOffset > Width) shimmerOffset = -120f;
                dirty = true;
            }

            if (dirty) Invalidate();
        }

        protected override void OnMouseWheel(MouseEventArgs e)
        {
            base.OnMouseWheel(e);
            if (maxScroll <= 0) return;
            scrollOffset = Math.Max(0, Math.Min(maxScroll, scrollOffset - (e.Delta / 3)));
            Invalidate(rectListViewport);
        }

        protected override void OnMouseDown(MouseEventArgs e)
        {
            base.OnMouseDown(e);
            if (e.Button != MouseButtons.Left) return;

            if (rectHeader.Contains(e.Location) && !rectClose.Contains(e.Location))
            {
                dragging = true;
                dragStart = e.Location;
                return;
            }

            if (!isUpdating)
            {
                if (rectBtnUpdate.Contains(e.Location))
                    StartUpdateProcess();
                else if (rectBtnSkip.Contains(e.Location) || rectClose.Contains(e.Location))
                    this.Close();
            }
        }

        protected override void OnMouseMove(MouseEventArgs e)
        {
            base.OnMouseMove(e);
            if (dragging)
            {
                Point p = PointToScreen(e.Location);
                Location = new Point(p.X - dragStart.X, p.Y - dragStart.Y);
                return;
            }

            isHoverUpdate = rectBtnUpdate.Contains(e.Location);
            isHoverSkip = rectBtnSkip.Contains(e.Location);
            isHoverClose = rectClose.Contains(e.Location);

            int newHoverCard = -1;
            if (rectListViewport.Contains(e.Location))
            {
                int relY = e.Y - rectListViewport.Y + scrollOffset;
                int idx = relY / (CardHeight + CardGap);
                int inCardY = relY % (CardHeight + CardGap);
                if (idx >= 0 && idx < updates.Count && inCardY <= CardHeight)
                    newHoverCard = idx;
            }
            hoveredCardIndex = newHoverCard;

            Cursor = (!isUpdating && (isHoverUpdate || isHoverSkip || isHoverClose))
                ? Cursors.Hand
                : Cursors.Default;
        }

        protected override void OnMouseUp(MouseEventArgs e)
        {
            base.OnMouseUp(e);
            dragging = false;
        }

        protected override void OnMouseLeave(EventArgs e)
        {
            base.OnMouseLeave(e);
            isHoverUpdate = isHoverSkip = isHoverClose = false;
            hoveredCardIndex = -1;
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            Graphics g = e.Graphics;
            g.SmoothingMode = SmoothingMode.AntiAlias;
            g.TextRenderingHint = TextRenderingHint.ClearTypeGridFit;

            g.FillRectangle(brushBg, ClientRectangle);
            g.FillRectangle(brushHeader, rectHeader);
            g.DrawLine(penAccentTop, 0, 1, Width, 1);

            g.DrawString("ДОСТУПНІ ОНОВЛЕННЯ МОДІВ", fontTitle, brushTextMain, 20f, 12f);
            g.DrawString(
                string.Format("Знайдено нових оновлень: {0} • Клієнт WoT {1}", updates.Count, gameVer),
                fontSubtitle, brushGold, 21f, 40f);

            DrawCloseButton(g);
            DrawCardsList(g);
            DrawFooter(g);

            g.DrawRectangle(penBorder, 0, 0, Width - 1, Height - 1);
        }

        private void DrawCloseButton(Graphics g)
        {
            if (btnCloseHover > 0.01f)
            {
                int a = (int)(btnCloseHover * 180);
                using (var br = new SolidBrush(Color.FromArgb(a, 190, 50, 50)))
                    FillRoundedRect(g, br, rectClose, 5);
            }
            using (var p = new Pen(Color.FromArgb(200, 210, 225), 1.8f))
            {
                int cx = rectClose.X + rectClose.Width / 2;
                int cy = rectClose.Y + rectClose.Height / 2;
                g.DrawLine(p, cx - 5, cy - 5, cx + 5, cy + 5);
                g.DrawLine(p, cx + 5, cy - 5, cx - 5, cy + 5);
            }
        }

        private void DrawCardsList(Graphics g)
        {
            GraphicsState state = g.Save();
            g.SetClip(rectListViewport);

            for (int i = 0; i < updates.Count; i++)
            {
                PendingModUpdate item = updates[i];
                int cardY = rectListViewport.Y + i * (CardHeight + CardGap) - scrollOffset;
                if (cardY + CardHeight < rectListViewport.Y || cardY > rectListViewport.Bottom)
                    continue;

                Rectangle cardRect = new Rectangle(rectListViewport.X, cardY, rectListViewport.Width - (maxScroll > 0 ? 10 : 0), CardHeight);
                int baseR = 26 + (int)(item.HoverProgress * 12);
                int baseG = 33 + (int)(item.HoverProgress * 15);
                int baseB = 47 + (int)(item.HoverProgress * 20);

                using (var brCard = new SolidBrush(Color.FromArgb(baseR, baseG, baseB)))
                    FillRoundedRect(g, brCard, cardRect, 7);

                Color borderCol = item.HoverProgress > 0.05f
                    ? Color.FromArgb((int)(80 + item.HoverProgress * 140), 229, 154, 40)
                    : Color.FromArgb(42, 52, 72);
                using (var pCard = new Pen(borderCol, 1f))
                    DrawRoundedRect(g, pCard, cardRect, 7);

                g.DrawString(item.Remote.title ?? item.Remote.id, fontModTitle, brushTextMain, cardRect.X + 14, cardRect.Y + 10);

                string badgeText = string.Format("v{0} → v{1}", item.InstalledVersion, item.Remote.version);
                SizeF badgeSize = g.MeasureString(badgeText, fontBadge);
                int badgeW = (int)badgeSize.Width + 14;
                Rectangle badgeRect = new Rectangle(cardRect.Right - badgeW - 14, cardRect.Y + 10, badgeW, 22);
                FillRoundedRect(g, brushBadgeBg, badgeRect, 4);
                g.DrawString(badgeText, fontBadge, brushBadgeFg, badgeRect.X + 7, badgeRect.Y + 3);

                string changes = string.IsNullOrEmpty(item.Remote.changes)
                    ? "Оновлення сумісності та покращення стабільності"
                    : item.Remote.changes;
                RectangleF changesRect = new RectangleF(cardRect.X + 14, cardRect.Y + 36, cardRect.Width - 28, 24);
                StringFormat sf = new StringFormat { Trimming = StringTrimming.EllipsisCharacter, FormatFlags = StringFormatFlags.NoWrap };
                g.DrawString(changes, fontChanges, brushTextMuted, changesRect, sf);
            }

            if (maxScroll > 0)
            {
                int trackX = rectListViewport.Right - 5;
                int thumbH = Math.Max(28, (int)((float)rectListViewport.Height / (rectListViewport.Height + maxScroll) * rectListViewport.Height));
                int thumbY = rectListViewport.Y + (int)((float)scrollOffset / maxScroll * (rectListViewport.Height - thumbH));
                using (var brThumb = new SolidBrush(Color.FromArgb(90, 110, 140)))
                    FillRoundedRect(g, brThumb, new Rectangle(trackX, thumbY, 4, thumbH), 2);
            }

            g.Restore(state);
        }

        private void DrawFooter(Graphics g)
        {
            g.DrawString(statusText, fontStatus, brushTextMuted, 20f, Height - 115f);

            if (isUpdating || displayProgress > 0.01f)
            {
                using (var brTrack = new SolidBrush(Color.FromArgb(28, 35, 48)))
                    FillRoundedRect(g, brTrack, rectProgressBar, 6);

                int fillW = Math.Max(8, (int)(rectProgressBar.Width * (displayProgress / 100f)));
                Rectangle fillRect = new Rectangle(rectProgressBar.X, rectProgressBar.Y, Math.Min(rectProgressBar.Width, fillW), rectProgressBar.Height);
                using (var brFill = new LinearGradientBrush(fillRect, Color.FromArgb(215, 130, 25), Color.FromArgb(245, 180, 55), LinearGradientMode.Horizontal))
                    FillRoundedRect(g, brFill, fillRect, 6);

                GraphicsState st = g.Save();
                g.SetClip(fillRect);
                Rectangle shimRect = new Rectangle((int)shimmerOffset, rectProgressBar.Y, 90, rectProgressBar.Height);
                using (var brShim = new LinearGradientBrush(shimRect, Color.FromArgb(0, 255, 255, 255), Color.FromArgb(95, 255, 255, 255), LinearGradientMode.Horizontal))
                    g.FillRectangle(brShim, shimRect);
                g.Restore(st);
            }

            Color cUpd1 = Color.FromArgb(210 + (int)(btnUpdateHover * 25), 125 + (int)(btnUpdateHover * 25), 22);
            Color cUpd2 = Color.FromArgb(235 + (int)(btnUpdateHover * 20), 162 + (int)(btnUpdateHover * 25), 42);
            if (isUpdating)
                cUpd1 = cUpd2 = Color.FromArgb(75, 85, 100);

            using (var brUpd = new LinearGradientBrush(rectBtnUpdate, cUpd1, cUpd2, LinearGradientMode.Vertical))
                FillRoundedRect(g, brUpd, rectBtnUpdate, 6);

            StringFormat centerSf = new StringFormat { Alignment = StringAlignment.Center, LineAlignment = StringAlignment.Center };
            g.DrawString(isUpdating ? "Оновлюємо моди..." : "Оновити і грати", fontButton, brushTextMain, rectBtnUpdate, centerSf);

            int skipBg = 32 + (int)(btnSkipHover * 18);
            using (var brSkip = new SolidBrush(Color.FromArgb(skipBg, skipBg + 7, skipBg + 18)))
                FillRoundedRect(g, brSkip, rectBtnSkip, 6);
            using (var pSkip = new Pen(Color.FromArgb(60 + (int)(btnSkipHover * 60), 75 + (int)(btnSkipHover * 60), 100), 1f))
                DrawRoundedRect(g, pSkip, rectBtnSkip, 6);
            g.DrawString("Грати без оновлення", fontButton, brushTextMuted, rectBtnSkip, centerSf);
        }

        private static GraphicsPath CreateRoundPath(Rectangle r, int radius)
        {
            int d = radius * 2;
            GraphicsPath path = new GraphicsPath();
            path.AddArc(r.X, r.Y, d, d, 180, 90);
            path.AddArc(r.Right - d, r.Y, d, d, 270, 90);
            path.AddArc(r.Right - d, r.Bottom - d, d, d, 0, 90);
            path.AddArc(r.X, r.Bottom - d, d, d, 90, 90);
            path.CloseFigure();
            return path;
        }

        private static void FillRoundedRect(Graphics g, Brush br, Rectangle r, int radius)
        {
            if (r.Width <= 0 || r.Height <= 0) return;
            using (GraphicsPath path = CreateRoundPath(r, radius))
                g.FillPath(br, path);
        }

        private static void DrawRoundedRect(Graphics g, Pen pen, Rectangle r, int radius)
        {
            if (r.Width <= 0 || r.Height <= 0) return;
            using (GraphicsPath path = CreateRoundPath(r, radius))
                g.DrawPath(pen, path);
        }

        private void StartUpdateProcess()
        {
            if (isUpdating) return;
            isUpdating = true;
            statusText = "Підготовка резервної копії...";
            targetProgress = 5f;
            Invalidate();

            Thread worker = new Thread(RunUpdateWorker);
            worker.IsBackground = true;
            worker.Start();
        }

        private void RunUpdateWorker()
        {
            string stamp = DateTime.Now.ToString("yyyyMMdd_HHmmss");
            string bkpDir = Path.Combine(gamePath, ".backups", "launcher", stamp);
            var replacedPairs = new List<string[]>();

            try
            {
                Directory.CreateDirectory(bkpDir);
                int total = updates.Count;

                for (int i = 0; i < total; i++)
                {
                    PendingModUpdate u = updates[i];
                    ManifestModEntry rem = u.Remote;
                    statusText = string.Format("Завантаження ({0}/{1}): {2} v{3}...", i + 1, total, rem.title ?? rem.id, rem.version);
                    targetProgress = 8f + (i * 85f / total);

                    string tmpFile = Path.Combine(Path.GetTempPath(), "wot-upd-" + Guid.NewGuid().ToString("N") + ".wotmod");
                    DownloadFileWithProgress(rem.url, tmpFile, i, total);

                    if (rem.size > 0 && new FileInfo(tmpFile).Length != rem.size)
                    {
                        File.Delete(tmpFile);
                        throw new InvalidDataException("Розмір файлу не збігається для " + rem.file);
                    }
                    if (!string.IsNullOrEmpty(rem.sha256) && !Program.VerifySha256(tmpFile, rem.sha256))
                    {
                        File.Delete(tmpFile);
                        throw new InvalidDataException("Контрольна сума SHA-256 не збігається для " + rem.file);
                    }
                    if (!Program.VerifyWotmodArchive(tmpFile, rem.id))
                    {
                        File.Delete(tmpFile);
                        throw new InvalidDataException("Пакет .wotmod пошкоджений або має інший ID: " + rem.file);
                    }

                    string relOld = u.LocalFilePath.Substring(gamePath.Length).TrimStart('\\', '/');
                    string bkpFile = Path.Combine(bkpDir, relOld);
                    Directory.CreateDirectory(Path.GetDirectoryName(bkpFile));
                    File.Copy(u.LocalFilePath, bkpFile, true);

                    string destDir = Path.GetDirectoryName(u.LocalFilePath);
                    string newDestPath = Path.Combine(destDir, rem.file);

                    File.Delete(u.LocalFilePath);
                    if (File.Exists(newDestPath)) File.Delete(newDestPath);
                    File.Move(tmpFile, newDestPath);

                    replacedPairs.Add(new string[] { bkpFile, u.LocalFilePath, newDestPath });
                }

                targetProgress = 100f;
                statusText = "Усі моди оновлено! Запускаємо гру...";
                Thread.Sleep(350);
                this.BeginInvoke(new Action(() => this.Close()));
            }
            catch (Exception ex)
            {
                foreach (string[] pair in replacedPairs)
                {
                    try
                    {
                        if (File.Exists(pair[2])) File.Delete(pair[2]);
                        if (File.Exists(pair[0])) File.Copy(pair[0], pair[1], true);
                    }
                    catch { }
                }

                this.BeginInvoke(new Action(() =>
                {
                    MessageBox.Show(
                        "Оновлення не вдалося (" + ex.Message + ").\nВідновлено попередні версії модів, запускаємо гру.",
                        "WoT Modpack Launcher",
                        MessageBoxButtons.OK,
                        MessageBoxIcon.Warning);
                    this.Close();
                }));
            }
        }

        private void DownloadFileWithProgress(string url, string dstPath, int index, int total)
        {
            HttpWebRequest req = (HttpWebRequest)WebRequest.Create(url);
            req.UserAgent = "WotModLauncher/" + Program.LauncherVersion;
            req.Timeout = 15000;
            req.ReadWriteTimeout = 15000;
            using (HttpWebResponse resp = (HttpWebResponse)req.GetResponse())
            using (Stream s = resp.GetResponseStream())
            using (FileStream fs = File.Create(dstPath))
            {
                long len = resp.ContentLength;
                byte[] buf = new byte[16384];
                long readTotal = 0;
                int n;
                while ((n = s.Read(buf, 0, buf.Length)) > 0)
                {
                    fs.Write(buf, 0, n);
                    readTotal += n;
                    if (len > 0)
                    {
                        float fileFrac = (float)readTotal / len;
                        targetProgress = 8f + ((index + fileFrac) * 85f / total);
                    }
                }
            }
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing)
            {
                if (animTimer != null) animTimer.Dispose();
                fontTitle.Dispose();
                fontSubtitle.Dispose();
                fontModTitle.Dispose();
                fontBadge.Dispose();
                fontChanges.Dispose();
                fontButton.Dispose();
                fontStatus.Dispose();
                brushBg.Dispose();
                brushHeader.Dispose();
                brushGold.Dispose();
                brushTextMain.Dispose();
                brushTextMuted.Dispose();
                brushBadgeBg.Dispose();
                brushBadgeFg.Dispose();
                penBorder.Dispose();
                penAccentTop.Dispose();
            }
            base.Dispose(disposing);
        }
    }
}
