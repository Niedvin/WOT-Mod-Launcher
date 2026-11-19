using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Net;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;

[assembly: AssemblyTitle("WoT Modpack Launcher")]
[assembly: AssemblyDescription("Лаунчер автооновлення модифікацій World of Tanks")]
[assembly: AssemblyCompany("Niedvin")]
[assembly: AssemblyProduct("WoT Modpack by Niedvin")]
[assembly: AssemblyCopyright("Copyright © 2026 Niedvin")]
[assembly: AssemblyFileVersion("1.4.3.10")]
[assembly: AssemblyVersion("1.4.3.10")]

namespace WotModLauncher
{
    [ComImport, Guid("00021401-0000-0000-C000-000000000046")]
    internal class ShellLinkCoClass { }

    [ComImport, InterfaceType(ComInterfaceType.InterfaceIsIUnknown), Guid("000214F9-0000-0000-C000-000000000046")]
    internal interface IShellLinkW
    {
        void GetPath([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszFile, int cch, IntPtr pfd, uint fFlags);
        void GetIDList(out IntPtr ppidl);
        void SetIDList(IntPtr pidl);
        void GetDescription([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszName, int cch);
        void SetDescription([MarshalAs(UnmanagedType.LPWStr)] string pszName);
        void GetWorkingDirectory([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszDir, int cch);
        void SetWorkingDirectory([MarshalAs(UnmanagedType.LPWStr)] string pszDir);
        void GetArguments([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszArgs, int cch);
        void SetArguments([MarshalAs(UnmanagedType.LPWStr)] string pszArgs);
        void GetHotkey(out short pwHotkey);
        void SetHotkey(short wHotkey);
        void GetShowCmd(out int piShowCmd);
        void SetShowCmd(int iShowCmd);
        void GetIconLocation([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszIconPath, int cch, out int piIcon);
        void SetIconLocation([MarshalAs(UnmanagedType.LPWStr)] string pszIconPath, int iIcon);
        void SetRelativePath([MarshalAs(UnmanagedType.LPWStr)] string pszPathRel, uint dwReserved);
        void Resolve(IntPtr hwnd, uint fFlags);
        void SetPath([MarshalAs(UnmanagedType.LPWStr)] string pszFile);
    }

    [ComImport, InterfaceType(ComInterfaceType.InterfaceIsIUnknown), Guid("0000010b-0000-0000-C000-000000000046")]
    internal interface IPersistFile
    {
        void GetClassID(out Guid pClassID);
        [PreserveSig] int IsDirty();
        void Load([MarshalAs(UnmanagedType.LPWStr)] string pszFileName, uint dwMode);
        void Save([MarshalAs(UnmanagedType.LPWStr)] string pszFileName, [MarshalAs(UnmanagedType.Bool)] bool fRemember);
        void SaveCompleted([MarshalAs(UnmanagedType.LPWStr)] string pszFileName);
        void GetCurFile([MarshalAs(UnmanagedType.LPWStr)] out string ppszFileName);
    }

    public class LauncherConfig
    {
        public string game_path { get; set; }
        public bool hijack_shortcuts { get; set; }
        public string manifest_url { get; set; }
        public List<string> skip_mods { get; set; }
    }

    public class ManifestLauncherInfo
    {
        public string version { get; set; }
        public string url { get; set; }
        public string sha256 { get; set; }
    }

    public class SelfUpdateState
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
        public bool? default_checked { get; set; }
        public bool possible_cheat { get; set; }
        public string possible_cheat_note { get; set; }
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
        public bool IsNew { get; set; }
        public float HoverProgress;
        internal List<string> InstalledFiles { get; set; }
    }

    public static class Program
    {
        public const string RepoOwner = "Niedvin";
        public const string RepoName = "WOT-Mod-Launcher";
        public const string ManifestUrl = "https://github.com/Niedvin/WOT-Mod-Launcher/releases/latest/download/manifest.json";
        public static readonly string LauncherVersion = Assembly.GetExecutingAssembly().GetName().Version.ToString();
        public static string ManifestOverride;
        public static string ManifestLocalDir;

        public static string LauncherDir
        {
            get { return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "WotModpack"); }
        }

        public static string DeclinedModsPath
        {
            get { return Path.Combine(LauncherDir, "declined.json"); }
        }

        public static List<string> LoadDeclinedMods()
        {
            return LoadDeclinedMods(DeclinedModsPath);
        }

        internal static List<string> LoadDeclinedMods(string path)
        {
            try
            {
                return ReadDeclinedMods(path);
            }
            catch
            {
                return new List<string>();
            }
        }

        private static List<string> ReadDeclinedMods(string path)
        {
            if (!File.Exists(path)) return new List<string>();
            var serializer = new JavaScriptSerializer();
            return serializer.Deserialize<List<string>>(File.ReadAllText(path, Encoding.UTF8)) ?? new List<string>();
        }

        private static void ChangeModChoices(string path, Action<HashSet<string>> change)
        {
            using (Mutex mutex = LockModChanges())
            {
                try
                {
                    var choices = new HashSet<string>(ReadDeclinedMods(path), StringComparer.OrdinalIgnoreCase);
                    change(choices);
                    SaveModChoices(path, choices);
                }
                finally { mutex.ReleaseMutex(); }
            }
        }

        internal static Mutex LockModChanges()
        {
            var mutex = new Mutex(false, @"Local\WotModpackLauncherDeclinedMods");
            try
            {
                if (!mutex.WaitOne(1500)) throw new IOException("Налаштування модів наразі зайняті.");
                return mutex;
            }
            catch (AbandonedMutexException) { return mutex; }
            catch
            {
                mutex.Dispose();
                throw;
            }
        }

        internal static void AddDeclinedMods(string path, IEnumerable<string> ids)
        {
            ChangeModChoices(path, choices => choices.UnionWith(ids));
        }

        internal static void RememberDeclinedMods(string path, ModOffer offer)
        {
            ChangeModChoices(path, choices =>
            {
                choices.UnionWith(offer.DeclineIds());
                foreach (PendingModUpdate item in offer.Packages)
                    choices.Remove("enabled:" + item.Remote.id);
            });
        }

        internal static void RememberAddedMods(string path, IEnumerable<PendingModUpdate> packages)
        {
            ChangeModChoices(path, choices =>
            {
                foreach (var item in packages)
                {
                    choices.Remove(item.Remote.id);
                    if (ModOffer.DeclineGroup(item.Remote) == null)
                        choices.Remove(ModOffer.NewOfferId(item.Remote));
                    choices.Remove("removed:" + item.Remote.id);
                    choices.Add("enabled:" + item.Remote.id);
                }
            });
        }

        private static void SaveModChoices(string path, HashSet<string> choices)
        {
            Directory.CreateDirectory(Path.GetDirectoryName(path));
            string pending = path + "." + Guid.NewGuid().ToString("N") + ".tmp";
            try
            {
                var serializer = new JavaScriptSerializer();
                File.WriteAllText(pending, serializer.Serialize(choices.ToArray()), new UTF8Encoding(false));
                if (File.Exists(path)) File.Replace(pending, path, null);
                else File.Move(pending, path);
            }
            finally { TryDeleteFile(pending); }
        }

        private static string CurrentExePath
        {
            get { return Assembly.GetExecutingAssembly().Location; }
        }

        private static string SelfUpdateStatePath
        {
            get { return CurrentExePath + ".selfupdate.json"; }
        }

        [STAThread]
        public static int Main(string[] args)
        {

            // .NET 4.0 defaults to TLS 1.0 which GitHub drops — 2026-10-24
            ServicePointManager.SecurityProtocol = (SecurityProtocolType)3072;
            // Default is 2 per host; the atomic update phase downloads up to 4 packages at once — 2026-11-11
            ServicePointManager.DefaultConnectionLimit = 8;

            bool checkOnly = false;
            bool updateOnly = false;
            bool selfUpdateMode = false;
            bool startWithoutMods = false;
            string argGamePath = null;
            for (int i = 0; i < args.Length; i++)
            {
                if (args[i] == "--check-only") checkOnly = true;
                else if (args[i] == "--update-only") updateOnly = true;
                else if (args[i] == "--self-update") selfUpdateMode = true;
                else if (args[i] == "--no-mods") startWithoutMods = true;
                else if (args[i] == "--game" && i + 1 < args.Length) argGamePath = args[++i];
                else if (args[i] == "--manifest" && i + 1 < args.Length) ManifestOverride = args[++i];
            }

            if (selfUpdateMode)
            {
                return RunSelfUpdate();
            }

            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);

            ApplyPendingSelfUpdate();
            CleanupSelfUpdateOldBinary();

            if (!checkOnly && IsGameAlreadyRunning())
            {
                return 0;
            }

            LauncherConfig cfg = LoadConfig(argGamePath);
            if (cfg == null || string.IsNullOrEmpty(cfg.game_path) || !IsGameDirectory(cfg.game_path))
            {
                if (!checkOnly && !updateOnly)
                {
                    if (!string.IsNullOrEmpty(argGamePath))
                        LaunchGame(argGamePath);
                    else
                        MessageBox.Show(
                            "Не вдалося знайти папку World of Tanks.\nЗапустіть інсталятор модпаку і вкажіть шлях до гри — після цього ярлик працюватиме.",
                            "WoT Modpack Launcher", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                }
                return 1;
            }

            if (string.IsNullOrEmpty(ManifestOverride) && !string.IsNullOrEmpty(cfg.manifest_url))
                ManifestOverride = cfg.manifest_url;

            ManifestRoot fetchedManifest = null;
            Thread manifestThread = new Thread(() => { fetchedManifest = FetchManifestWithTimeout(6000); });
            manifestThread.IsBackground = true;
            manifestThread.Start();

            if (cfg.hijack_shortcuts)
                EnsureShortcutsRedirected(cfg.game_path);

            if (startWithoutMods && !checkOnly && !updateOnly)
            {
                string cleanVer = DetectGameVersion(cfg.game_path);
                DisableMods(cfg.game_path, cleanVer);
                LaunchGame(cfg.game_path);
                return 0;
            }

            string gameVer = DetectGameVersion(cfg.game_path);
            RestoreDisabledMods(cfg.game_path);
            List<string> declinedMods = LoadDeclinedMods();
            if (!string.IsNullOrEmpty(gameVer))
                SyncVersionFolderIfEmpty(cfg.game_path, gameVer, declinedMods);

            string activeVer = gameVer;
            bool applyLauncherUpdate = true;
            SelfUpdateState selfUpdatePlan = null;
            ManifestRoot manifest = manifestThread.Join(6000) ? SanitizeManifest(fetchedManifest) : null;
            if (manifest != null)
            {
                selfUpdatePlan = GetSelfUpdatePlan(manifest.launcher);
                if (string.IsNullOrEmpty(activeVer)) activeVer = manifest.game_version;
                List<PendingModUpdate> catalog = ScanModCatalog(cfg.game_path, activeVer, manifest);
                List<PendingModUpdate> updates = SelectPendingUpdates(catalog, cfg.skip_mods, declinedMods);
                if (selfUpdatePlan == null && !checkOnly && !updateOnly)
                    selfUpdatePlan = LoadPendingUpdateState();
                if (!checkOnly && (updates.Count > 0 || selfUpdatePlan != null || catalog.Any(item => item.IsNew)))
                {
                    using (var form = new UpdateDialogForm(cfg.game_path, activeVer, updates, selfUpdatePlan, LauncherDir, catalog))
                    {
                        Application.Run(form);
                        applyLauncherUpdate = form.ApplyLauncherUpdate;
                    }
                }
            }
            if (selfUpdatePlan == null && !checkOnly && !updateOnly)
                selfUpdatePlan = LoadPendingUpdateState();
            if (!applyLauncherUpdate)
                selfUpdatePlan = null;

            if (!checkOnly && !updateOnly)
            {
                LaunchGame(cfg.game_path);
                if (selfUpdatePlan != null)
                    StartBackgroundSelfUpdate(selfUpdatePlan);
            }

            return 0;
        }

        private static void CleanupSelfUpdateOldBinary()
        {
            try
            {
                string exe = CurrentExePath;
                string oldFile = exe + ".old";
                if (File.Exists(oldFile)) File.Delete(oldFile);
                string dir = Path.GetDirectoryName(exe);
                foreach (string stale in Directory.GetFiles(dir, Path.GetFileName(exe) + ".new.*.tmp"))
                    TryDeleteFile(stale);
            }
            catch { }
        }

        private static bool IsGameAlreadyRunning()
        {
            List<Process> processes = FindGameProcesses();
            try
            {
                return processes.Count > 0;
            }
            finally
            {
                foreach (Process process in processes)
                {
                    try { process.Dispose(); } catch { }
                }
            }
        }

        private static List<Process> FindGameProcesses()
        {
            var result = new List<Process>();
            try
            {
                result.AddRange(Process.GetProcessesByName("WorldOfTanks"));
                result.AddRange(Process.GetProcessesByName("WorldOfTanks32"));
            }
            catch { }
            return result;
        }

        private static bool IsGameDirectory(string path)
        {
            if (string.IsNullOrEmpty(path) || !Directory.Exists(path)) return false;
            return File.Exists(Path.Combine(path, "WorldOfTanks.exe"))
                || File.Exists(Path.Combine(path, "win64", "WorldOfTanks.exe"))
                || File.Exists(Path.Combine(path, "version.xml"));
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

            if (!IsGameDirectory(cfg.game_path))
            {
                // Hijacked shortcuts set the game as the working directory even without launcher.json — 2026-11-11
                string[] candidates = new string[]
                {
                    AppDomain.CurrentDomain.BaseDirectory,
                    Environment.CurrentDirectory
                };
                foreach (string candidate in candidates)
                {
                    if (IsGameDirectory(candidate))
                    {
                        cfg.game_path = candidate;
                        break;
                    }
                }
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

        public static void SyncVersionFolderIfEmpty(string gamePath, string activeVer, List<string> choices = null)
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

                var removed = new HashSet<string>((choices ?? new List<string>())
                    .Where(value => value != null && value.StartsWith("removed:", StringComparison.OrdinalIgnoreCase))
                    .Select(value => value.Substring("removed:".Length)), StringComparer.OrdinalIgnoreCase);
                foreach (string file in Directory.GetFiles(sourceDir, "*", SearchOption.AllDirectories))
                {
                    if (removed.Count > 0 && string.Equals(Path.GetExtension(file), ".wotmod", StringComparison.OrdinalIgnoreCase))
                    {
                        string id = ReadWotmodId(file) ?? PackageFilenameId(Path.GetFileName(file));
                        if (removed.Contains(id)) continue;
                    }
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
            string target = ManifestUrl;
            if (!string.IsNullOrEmpty(ManifestOverride))
            {
                string p = ManifestOverride;
                if (p.StartsWith("file://", StringComparison.OrdinalIgnoreCase))
                {
                    try { p = new Uri(p).LocalPath; }
                    catch
                    {
                        return null;
                    }
                }
                if (p.StartsWith("http://", StringComparison.OrdinalIgnoreCase) || p.StartsWith("https://", StringComparison.OrdinalIgnoreCase))
                {
                    target = p;
                }
                else
                {
                    if (!File.Exists(p) && Directory.Exists(p))
                        p = Path.Combine(p, "manifest.json");
                    if (!File.Exists(p))
                    {
                        return null;
                    }
                    try
                    {
                        ManifestLocalDir = Path.GetDirectoryName(Path.GetFullPath(p));
                        var serLocal = new JavaScriptSerializer();
                        ManifestRoot local = serLocal.Deserialize<ManifestRoot>(File.ReadAllText(p, Encoding.UTF8));
                        return local;
                    }
                    catch
                    {
                        return null;
                    }
                }
            }

            try
            {
                HttpWebRequest req = (HttpWebRequest)WebRequest.Create(AddCacheBuster(target));
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

        private static bool IsSafePathSegment(string segment)
        {
            if (string.IsNullOrEmpty(segment) || segment == "." || segment == ".." || segment.Length > 100)
                return false;
            if (segment.IndexOf(':') >= 0) return false;
            return segment.IndexOfAny(Path.GetInvalidFileNameChars()) < 0;
        }

        private static bool IsSafeManifestFile(string file)
        {
            if (!IsSafePathSegment(file)) return false;
            if (!file.EndsWith(".wotmod", StringComparison.OrdinalIgnoreCase)) return false;
            return Regex.IsMatch(file, @"_[0-9]+(\.[0-9]+)*\.wotmod$", RegexOptions.IgnoreCase);
        }

        private static bool IsSafeRelativeDir(string subdir)
        {
            if (string.IsNullOrEmpty(subdir)) return true;
            if (subdir.Length > 240) return false;
            foreach (string segment in subdir.Split('/', '\\'))
                if (!IsSafePathSegment(segment)) return false;
            return true;
        }

        private static bool IsSafeUrl(string url)
        {
            if (string.IsNullOrEmpty(url)) return false;
            if (url.StartsWith("http://", StringComparison.OrdinalIgnoreCase)
                || url.StartsWith("https://", StringComparison.OrdinalIgnoreCase)
                || url.StartsWith("file://", StringComparison.OrdinalIgnoreCase))
                return true;
            try { return Path.IsPathRooted(url); }
            catch { return false; }
        }

        private static bool IsHexSha256(string value)
        {
            if (string.IsNullOrEmpty(value) || value.Length != 64) return false;
            foreach (char c in value)
                if (!Uri.IsHexDigit(c)) return false;
            return true;
        }

        private static bool IsSafeModId(string id)
        {
            return !string.IsNullOrEmpty(id) && Regex.IsMatch(id, @"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$");
        }

        private static bool IsValidManifestMod(ManifestModEntry entry)
        {
            if (entry == null || !IsSafeModId(entry.id)) return false;
            if (ParseVer(entry.version) == null) return false;
            if (!IsSafeManifestFile(entry.file)) return false;
            if (!IsSafeRelativeDir(entry.subdir)) return false;
            if (!IsSafeUrl(entry.url)) return false;
            if (!IsHexSha256(entry.sha256)) return false;
            return entry.size >= 0;
        }

        private static ManifestRoot SanitizeManifest(ManifestRoot manifest)
        {
            if (manifest == null) return null;
            if (manifest.launcher != null)
            {
                if (string.IsNullOrEmpty(manifest.launcher.url)
                    || !IsSafeUrl(manifest.launcher.url)
                    || !IsHexSha256(manifest.launcher.sha256))
                    manifest.launcher = null;
            }
            if (!string.IsNullOrEmpty(manifest.game_version)
                && !Regex.IsMatch(manifest.game_version, @"^[0-9]+(\.[0-9]+){1,3}$"))
                manifest.game_version = null;
            if (manifest.mods != null)
            {
                var valid = new List<ManifestModEntry>();
                foreach (ManifestModEntry entry in manifest.mods)
                    if (IsValidManifestMod(entry)) valid.Add(entry);
                int skipped = manifest.mods.Count - valid.Count;
                if (skipped > 0)
                    LogSelfUpdate("manifest: skipped " + skipped + " invalid mod entries");
                manifest.mods = valid;
            }
            return manifest;
        }

        private static SelfUpdateState GetSelfUpdatePlan(ManifestLauncherInfo info)
        {
            if (info == null || string.IsNullOrEmpty(info.version) || string.IsNullOrEmpty(info.url))
                return null;
            if (!IsSafeUrl(info.url) || !IsHexSha256(info.sha256))
            {
                LogSelfUpdate("manifest: launcher update ignored, missing url or sha256");
                return null;
            }

            Version curV = Quad(ParseVer(LauncherVersion));
            Version remV = Quad(ParseVer(info.version));
            if (curV == null || remV == null || remV <= curV) return null;

            string url = info.url;
            string localSrc = ResolveLocalUrl(url);
            if (localSrc != null) url = localSrc;

            return new SelfUpdateState { version = remV.ToString(), url = url, sha256 = info.sha256 };
        }

        private static SelfUpdateState LoadSelfUpdateState()
        {
            try
            {
                if (!File.Exists(SelfUpdateStatePath)) return null;
                var ser = new JavaScriptSerializer();
                return ser.Deserialize<SelfUpdateState>(File.ReadAllText(SelfUpdateStatePath, Encoding.UTF8));
            }
            catch { return null; }
        }

        private static SelfUpdateState LoadPendingUpdateState()
        {
            SelfUpdateState state = LoadSelfUpdateState();
            if (state == null || string.IsNullOrEmpty(state.version) || string.IsNullOrEmpty(state.url))
                return null;
            if (!IsSafeUrl(state.url) || !IsHexSha256(state.sha256))
                return null;
            Version curV = Quad(ParseVer(LauncherVersion));
            Version remV = Quad(ParseVer(state.version));
            if (curV == null || remV == null || remV <= curV) return null;
            return state;
        }

        private static void StartBackgroundSelfUpdate(SelfUpdateState plan)
        {
            try
            {
                var ser = new JavaScriptSerializer();
                File.WriteAllText(SelfUpdateStatePath, ser.Serialize(plan), new UTF8Encoding(false));
                string exe = CurrentExePath;
                ProcessStartInfo psi = new ProcessStartInfo
                {
                    FileName = exe,
                    Arguments = "--self-update",
                    WorkingDirectory = Path.GetDirectoryName(exe),
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    WindowStyle = ProcessWindowStyle.Hidden
                };
                Process.Start(psi);
                LogSelfUpdate("background update to " + plan.version + " started");
            }
            catch (Exception ex)
            {
                LogSelfUpdate("cannot start background update: " + ex.Message);
            }
        }

        private static int RunSelfUpdate()
        {
            Mutex mutex = null;
            bool lockTaken = false;
            try
            {
                mutex = new Mutex(false, @"Local\WotModpackLauncherSelfUpdate");
                try { lockTaken = mutex.WaitOne(0); }
                catch (AbandonedMutexException) { lockTaken = true; }
                if (!lockTaken) return 0;

                SelfUpdateState state = LoadSelfUpdateState();
                if (state == null || string.IsNullOrEmpty(state.version) || string.IsNullOrEmpty(state.url))
                    return 0;
                if (!IsSafeUrl(state.url) || !IsHexSha256(state.sha256))
                {
                    LogSelfUpdate("self-update state has no trusted url or sha256, discarded");
                    TryDeleteFile(SelfUpdateStatePath);
                    return 1;
                }

                Version curV = Quad(ParseVer(LauncherVersion));
                Version remV = Quad(ParseVer(state.version));
                if (curV == null || remV == null || remV <= curV)
                {
                    TryDeleteFile(SelfUpdateStatePath);
                    return 0;
                }

                string exe = CurrentExePath;
                string tmp = exe + ".new." + Guid.NewGuid().ToString("N") + ".tmp";
                string newPath = exe + ".new";
                try
                {
                    string localSrc = ResolveLocalUrl(state.url);
                    if (localSrc != null)
                        File.Copy(localSrc, tmp, true);
                    else
                        DownloadLauncherFile(AddCacheBuster(state.url), tmp);

                    if (!VerifySha256(tmp, state.sha256))
                        throw new InvalidDataException("SHA-256 mismatch");
                    Version fileV = Quad(GetExeVersion(tmp));
                    if (fileV == null || fileV < remV)
                        throw new InvalidDataException("downloaded launcher version " + (fileV == null ? "unknown" : fileV.ToString()) + " is older than " + remV);

                    TryDeleteFile(newPath);
                    File.Move(tmp, newPath);
                }
                catch (Exception ex)
                {
                    TryDeleteFile(tmp);
                    LogSelfUpdate("download failed: " + ex.Message);
                    return 1;
                }

                if (!TrySwapLauncher(exe, newPath))
                {
                    LogSelfUpdate("swap deferred to next start");
                    return 1;
                }

                TryDeleteFile(SelfUpdateStatePath);
                LogSelfUpdate("launcher updated to " + remV + ", next start uses it");
                return 0;
            }
            catch (Exception ex)
            {
                LogSelfUpdate("self-update failed: " + ex.Message);
                return 1;
            }
            finally
            {
                if (lockTaken)
                {
                    try { mutex.ReleaseMutex(); } catch { }
                }
                if (mutex != null)
                {
                    try { mutex.Close(); } catch { }
                }
            }
        }

        private static void ApplyPendingSelfUpdate()
        {
            try
            {
                string exe = CurrentExePath;
                string newPath = exe + ".new";
                if (!File.Exists(newPath)) return;

                Version newV = Quad(GetExeVersion(newPath));
                Version curV = Quad(GetExeVersion(exe)) ?? Quad(ParseVer(LauncherVersion));
                if (newV == null || (curV != null && newV <= curV))
                {
                    TryDeleteFile(newPath);
                    return;
                }

                SelfUpdateState state = LoadSelfUpdateState();
                if (state == null || !IsHexSha256(state.sha256))
                {
                    TryDeleteFile(newPath);
                    LogSelfUpdate("pending launcher has no sha256, discarded");
                    return;
                }
                if (!VerifySha256(newPath, state.sha256))
                {
                    TryDeleteFile(newPath);
                    LogSelfUpdate("pending launcher hash mismatch, discarded");
                    return;
                }

                if (TrySwapLauncher(exe, newPath))
                {
                    TryDeleteFile(SelfUpdateStatePath);
                    LogSelfUpdate("applied pending launcher " + newV);
                }
            }
            catch (Exception ex)
            {
                LogSelfUpdate("apply pending failed: " + ex.Message);
            }
        }

        private static bool TrySwapLauncher(string exe, string newPath)
        {
            string oldPath = exe + ".old";
            try
            {
                if (File.Exists(oldPath)) File.Delete(oldPath);
                File.Move(exe, oldPath);
            }
            catch (Exception ex)
            {
                LogSelfUpdate("rename current exe failed: " + ex.Message);
                return false;
            }

            try
            {
                File.Move(newPath, exe);
                return true;
            }
            catch (Exception ex)
            {
                LogSelfUpdate("place new exe failed: " + ex.Message);
                try
                {
                    if (!File.Exists(exe)) File.Copy(oldPath, exe, true);
                }
                catch { }
                return false;
            }
        }

        private static void DownloadLauncherFile(string url, string dst)
        {
            HttpWebRequest req = (HttpWebRequest)WebRequest.Create(url);
            req.UserAgent = "WotModLauncher/" + LauncherVersion;
            req.Timeout = 20000;
            req.ReadWriteTimeout = 20000;
            req.AllowAutoRedirect = true;
            using (HttpWebResponse resp = (HttpWebResponse)req.GetResponse())
            using (Stream s = resp.GetResponseStream())
            using (FileStream fs = File.Create(dst))
            {
                s.CopyTo(fs);
            }
        }

        internal static string AddCacheBuster(string url)
        {
            if (string.IsNullOrEmpty(url)) return url;
            return url + (url.IndexOf('?') >= 0 ? "&" : "?") + "t=" + Environment.TickCount;
        }

        private static Version GetExeVersion(string path)
        {
            try
            {
                FileVersionInfo vi = FileVersionInfo.GetVersionInfo(path);
                return ParseVer(vi.FileVersion);
            }
            catch { return null; }
        }

        private static Version Quad(Version v)
        {
            if (v == null) return null;
            return new Version(v.Major, v.Minor, Math.Max(0, v.Build), Math.Max(0, v.Revision));
        }

        private static void LogSelfUpdate(string message)
        {
            try
            {
                string logPath = Path.Combine(Path.GetDirectoryName(CurrentExePath), "launcher-update.log");
                FileInfo fi = new FileInfo(logPath);
                if (fi.Exists && fi.Length > 64 * 1024) fi.Delete();
                File.AppendAllText(logPath, DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + "  " + message + Environment.NewLine, new UTF8Encoding(false));
            }
            catch { }
        }

        internal static void TryDeleteFile(string path)
        {
            try { if (File.Exists(path)) File.Delete(path); } catch { }
        }

        private static bool IsSkipped(List<string> skipMods, string id)
        {
            if (skipMods == null) return false;
            foreach (string skipped in skipMods)
                if (string.Equals(skipped, id, StringComparison.OrdinalIgnoreCase))
                    return true;
            return false;
        }

        public static List<PendingModUpdate> FindPendingUpdates(string gamePath, string gameVer, ManifestRoot manifest, List<string> skipMods)
        {
            return FindPendingUpdates(gamePath, gameVer, manifest, skipMods, null);
        }

        public static List<PendingModUpdate> FindPendingUpdates(string gamePath, string gameVer, ManifestRoot manifest, List<string> skipMods, List<string> declinedMods)
        {
            return SelectPendingUpdates(ScanModCatalog(gamePath, gameVer, manifest), skipMods, declinedMods);
        }

        private static List<PendingModUpdate> SelectPendingUpdates(IEnumerable<PendingModUpdate> catalog, List<string> skipMods, List<string> declinedMods)
        {
            return catalog.Where(item =>
            {
                ManifestModEntry entry = item.Remote;
                bool enabled = IsSkipped(declinedMods, "enabled:" + entry.id);
                if (!enabled && (IsSkipped(skipMods, entry.id) ||
                    IsSkipped(declinedMods, entry.id) || IsSkipped(declinedMods, ModOffer.DeclineGroup(entry))))
                    return false;
                return item.IsNew
                    ? (enabled || !IsSkipped(declinedMods, ModOffer.NewOfferId(entry))) && (enabled || skipMods != null || entry.default_checked != false)
                    : ParseVer(entry.version) > ParseVer(item.InstalledVersion);
            }).ToList();
        }

        internal static List<PendingModUpdate> ScanModCatalog(string gamePath, string gameVer, ManifestRoot manifest)
        {
            var result = new List<PendingModUpdate>();
            if (manifest == null || manifest.mods == null || string.IsNullOrEmpty(gameVer) ||
                !Regex.IsMatch(gameVer, @"^[0-9]+(\.[0-9]+){1,3}$"))
                return result;

            string verRoot = Path.Combine(gamePath, "mods", gameVer);
            var entries = new Dictionary<string, ManifestModEntry>(StringComparer.OrdinalIgnoreCase);
            foreach (ManifestModEntry candidate in manifest.mods)
            {
                if (!IsValidManifestMod(candidate)) continue;
                ManifestModEntry previous;
                if (!entries.TryGetValue(candidate.id, out previous) || Quad(ParseVer(candidate.version)) > Quad(ParseVer(previous.version)))
                    entries[candidate.id] = candidate;
            }

            foreach (var directory in entries.Values.GroupBy(entry => entry.subdir ?? "", StringComparer.OrdinalIgnoreCase))
            {
                string searchDir = Path.Combine(verRoot, directory.Key.Replace('/', Path.DirectorySeparatorChar));
                string[] files = Directory.Exists(searchDir)
                    ? Directory.GetFiles(searchDir, "*.wotmod", SearchOption.TopDirectoryOnly)
                    : new string[0];
                var identities = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
                foreach (ManifestModEntry entry in directory)
                {
                    var installed = new List<string>();
                    string newest = null;
                    Version installedVersion = null;
                    string filenameId = PackageFilenameId(entry.file);
                    foreach (string file in files)
                    {
                        Match name = Regex.Match(Path.GetFileName(file), @"^(.+?)_([vV]?[0-9]+(?:\.[0-9]+)*)\.wotmod$", RegexOptions.IgnoreCase);
                        if (!name.Success) continue;
                        Version version = ParseVer(name.Groups[2].Value);
                        if (version == null) continue;
                        string localId = name.Groups[1].Value;
                        if (!string.Equals(localId, entry.id, StringComparison.OrdinalIgnoreCase) &&
                            !string.Equals(localId, filenameId, StringComparison.OrdinalIgnoreCase))
                        {
                            string archiveId;
                            if (!identities.TryGetValue(file, out archiveId))
                                identities[file] = archiveId = ReadWotmodId(file);
                            if (!string.Equals(archiveId, entry.id, StringComparison.OrdinalIgnoreCase)) continue;
                        }
                        installed.Add(file);
                        if (installedVersion == null || version > installedVersion)
                        {
                            newest = file;
                            installedVersion = version;
                        }
                    }
                    result.Add(new PendingModUpdate
                    {
                        Remote = entry,
                        LocalFilePath = newest ?? Path.Combine(searchDir, entry.file),
                        InstalledVersion = installedVersion == null ? null : installedVersion.ToString(),
                        IsNew = newest == null,
                        InstalledFiles = installed
                    });
                }
            }
            return result;
        }

        private static string PackageFilenameId(string name)
        {
            return Regex.Replace(name, @"_[vV]?[0-9]+(?:\.[0-9]+)*\.wotmod$", "", RegexOptions.IgnoreCase);
        }

        internal static void RemoveModOffer(string gamePath, string gameVer, string prefsPath, ModOffer offer)
        {
            using (Mutex mutex = LockModChanges())
            {
                try { MoveRemovedPackages(gamePath, gameVer, prefsPath, offer); }
                finally { mutex.ReleaseMutex(); }
            }
        }

        private static void MoveRemovedPackages(string gamePath, string gameVer, string prefsPath, ModOffer offer)
        {
            if (string.IsNullOrEmpty(gameVer) || !Regex.IsMatch(gameVer, @"^[0-9]+(\.[0-9]+){1,3}$"))
                throw new InvalidDataException("Невідома версія гри.");
            var manifest = new ManifestRoot { mods = offer.Packages.Select(item => item.Remote).ToList() };
            var packages = ScanModCatalog(gamePath, gameVer, manifest);
            var installed = packages.SelectMany(item => item.InstalledFiles).Distinct(StringComparer.OrdinalIgnoreCase).ToList();
            if (installed.Count > 0 && IsGameAlreadyRunning())
                throw new IOException("Закрийте гру перед видаленням мода.");

            string modsRoot = Path.GetFullPath(Path.Combine(gamePath, "mods"));
            string versionRoot = Path.Combine(modsRoot, gameVer) + Path.DirectorySeparatorChar;
            string backup = Path.Combine(gamePath, ".backups", "launcher", "dismissed-" + Guid.NewGuid().ToString("N"));
            var moved = new List<KeyValuePair<string, string>>();
            try
            {
                ChangeModChoices(prefsPath, choices =>
                {
                    foreach (string path in installed)
                    {
                        string file = Path.GetFullPath(path);
                        if (!file.StartsWith(versionRoot, StringComparison.OrdinalIgnoreCase) ||
                            !string.Equals(Path.GetExtension(file), ".wotmod", StringComparison.OrdinalIgnoreCase))
                            throw new InvalidDataException("Файл поза папкою модів: " + file);
                        for (string part = file; !string.Equals(part, modsRoot, StringComparison.OrdinalIgnoreCase); part = Path.GetDirectoryName(part))
                        {
                            if ((File.GetAttributes(part) & FileAttributes.ReparsePoint) != 0)
                                throw new IOException("Файл мода використовує посилання: " + file);
                        }
                        if ((File.GetAttributes(modsRoot) & FileAttributes.ReparsePoint) != 0)
                            throw new IOException("Папка модів використовує посилання: " + modsRoot);
                        string destination = Path.Combine(backup, file.Substring(versionRoot.Length));
                        Directory.CreateDirectory(Path.GetDirectoryName(destination));
                        File.Move(file, destination);
                        moved.Add(new KeyValuePair<string, string>(file, destination));
                    }
                    choices.UnionWith(offer.DeclineIds());
                    foreach (var item in packages)
                    {
                        choices.Remove("enabled:" + item.Remote.id);
                        if (!item.IsNew) choices.Add("removed:" + item.Remote.id);
                    }
                });
            }
            catch (Exception error)
            {
                var rollbackErrors = new List<Exception>();
                foreach (var pair in Enumerable.Reverse(moved))
                {
                    try { File.Move(pair.Value, pair.Key); }
                    catch (Exception failure) { rollbackErrors.Add(failure); }
                }
                if (rollbackErrors.Count > 0)
                    throw new IOException("Не всі файли вдалося повернути. Резервна копія: " + backup,
                        new AggregateException(new[] { error }.Concat(rollbackErrors)));
                throw;
            }
        }

        public static Version ParseVer(string s)
        {
            if (string.IsNullOrEmpty(s)) return null;
            Version v;
            return Version.TryParse(s.TrimStart('v', 'V'), out v) ? v : null;
        }

        private static string ReadWotmodId(string filePath)
        {
            try
            {
                using (ZipArchive zip = ZipFile.OpenRead(filePath))
                {
                    ZipArchiveEntry meta = zip.GetEntry("meta.xml");
                    if (meta == null) return null;
                    using (StreamReader sr = new StreamReader(meta.Open(), Encoding.UTF8))
                    {
                        Match m = Regex.Match(sr.ReadToEnd(), @"<id>\s*([^<]+?)\s*</id>", RegexOptions.IgnoreCase);
                        return m.Success ? m.Groups[1].Value.Trim() : null;
                    }
                }
            }
            catch { return null; }
        }

        public static string ResolveLocalUrl(string url)
        {
            if (string.IsNullOrEmpty(url)) return null;
            string p = url;
            try
            {
                if (p.StartsWith("file://", StringComparison.OrdinalIgnoreCase))
                    p = new Uri(p).LocalPath;
            }
            catch { return null; }
            if (File.Exists(p)) return p;
            if (!string.IsNullOrEmpty(ManifestLocalDir))
            {
                string cand = Path.Combine(ManifestLocalDir, p.Replace('/', Path.DirectorySeparatorChar));
                if (File.Exists(cand)) return cand;
            }
            return null;
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

                foreach (string lnkPath in candidateShortcuts)
                {
                    if (!File.Exists(lnkPath)) continue;

                    IShellLinkW link = (IShellLinkW)new ShellLinkCoClass();
                    try
                    {
                        ((IPersistFile)link).Load(lnkPath, 0);
                        StringBuilder target = new StringBuilder(1024);
                        link.GetPath(target, target.Capacity, IntPtr.Zero, 0);
                        if (!target.ToString().EndsWith("wgc_api.exe", StringComparison.OrdinalIgnoreCase)) continue;

                        string bkpDir = Path.Combine(LauncherDir, "shortcuts_backup");
                        Directory.CreateDirectory(bkpDir);
                        string bkpName = (lnkPath.IndexOf("Start Menu", StringComparison.OrdinalIgnoreCase) >= 0 ? "startmenu_" : "desktop_") + Path.GetFileName(lnkPath);
                        string bkpPath = Path.Combine(bkpDir, bkpName);
                        if (!File.Exists(bkpPath)) File.Copy(lnkPath, bkpPath, false);

                        string iconFile = Path.Combine(gamePath, "game_metadata", "game.ico");
                        if (!File.Exists(iconFile)) iconFile = Path.Combine(gamePath, "WorldOfTanks.exe");

                        link.SetPath(launcherExe);
                        link.SetArguments("");
                        link.SetWorkingDirectory(gamePath);
                        link.SetIconLocation(iconFile, 0);
                        ((IPersistFile)link).Save(lnkPath, true);
                    }
                    catch
                    {
                    }
                    finally
                    {
                        Marshal.FinalReleaseComObject(link);
                    }
                }
            }
            catch
            {
            }
        }

        public static void LaunchGame(string gamePath)
        {
            if (string.IsNullOrEmpty(gamePath))
            {
                return;
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
                    return;
                }
                catch
                {
                }
            }

            string exe = Path.Combine(gamePath, "WorldOfTanks.exe");
            if (!File.Exists(exe))
                exe = Path.Combine(gamePath, "win64", "WorldOfTanks.exe");
            if (!File.Exists(exe))
            {
                return;
            }
            try
            {
                Process.Start(new ProcessStartInfo
                {
                    FileName = exe,
                    WorkingDirectory = gamePath
                });
            }
            catch
            {
            }
        }

        private static void CopyMissing(string source, string target)
        {
            Directory.CreateDirectory(target);
            foreach (string file in Directory.GetFiles(source))
            {
                string destination = Path.Combine(target, Path.GetFileName(file));
                if (!File.Exists(destination))
                    File.Copy(file, destination, false);
            }
            foreach (string directory in Directory.GetDirectories(source))
                CopyMissing(directory, Path.Combine(target, Path.GetFileName(directory)));
        }

        public static void RestoreDisabledMods(string gamePath)
        {
            try
            {
                string modsRoot = Path.Combine(gamePath, "mods");
                if (!Directory.Exists(modsRoot)) return;
                foreach (string disabled in Directory.GetDirectories(modsRoot, "*.disabled"))
                {
                    string active = disabled.Substring(0, disabled.Length - ".disabled".Length);
                    if (Directory.Exists(active))
                    {
                        CopyMissing(disabled, active);
                        Directory.Delete(disabled, true);
                    }
                    else
                    {
                        Directory.Move(disabled, active);
                    }
                }
            }
            catch { }
        }

        public static void DisableMods(string gamePath, string gameVer)
        {
            try
            {
                if (string.IsNullOrEmpty(gameVer)) return;
                string modsRoot = Path.Combine(gamePath, "mods");
                string active = Path.Combine(modsRoot, gameVer);
                if (!Directory.Exists(active)) return;
                RestoreDisabledMods(gamePath);
                string disabled = active + ".disabled";
                if (Directory.Exists(disabled)) return;
                Directory.Move(active, disabled);
            }
            catch { }
        }
    }

    internal sealed class ModOffer
    {
        internal readonly string Title;
        internal readonly List<PendingModUpdate> Packages;
        internal readonly HashSet<PendingModUpdate> Selected;

        private ModOffer(IEnumerable<PendingModUpdate> packages)
        {
            Packages = packages.OrderBy(item => item.Remote.id, StringComparer.OrdinalIgnoreCase).ToList();
            ManifestModEntry first = Packages[0].Remote;
            Title = DeclineGroup(first) == "openwg-group:gpu" ? "GPU Boost" : GroupTitle(first) ?? first.title ?? first.id;
            Selected = new HashSet<PendingModUpdate>(Packages.Where(item => !item.IsNew));
        }

        internal bool HasUpdates { get { return Packages.Any(item => !item.IsNew); } }

        internal bool HasWarning { get { return Packages.Any(item => item.Remote.possible_cheat); } }

        internal string Key { get { return DeclineGroup(Packages[0].Remote) ?? Packages[0].Remote.id; } }

        internal static string DeclineGroup(ManifestModEntry remote)
        {
            string title = GroupTitle(remote);
            if (title == "GPU Boost (Anti-Lag + XeSS)") return "openwg-group:gpu";
            if (title == "OpenWG Core & Fixes") return "openwg-group:core";
            return null;
        }

        private static string GroupTitle(ManifestModEntry remote)
        {
            if (remote.title == null || !remote.id.StartsWith("net.openwg.", StringComparison.OrdinalIgnoreCase))
                return null;
            string suffix = " (" + remote.id + ")";
            if (remote.title.EndsWith(suffix, StringComparison.OrdinalIgnoreCase))
                return remote.title.Substring(0, remote.title.Length - suffix.Length);
            return null;
        }

        internal static List<ModOffer> Create(IEnumerable<PendingModUpdate> updates)
        {
            return updates.GroupBy(item => DeclineGroup(item.Remote) ?? item.Remote.id, StringComparer.OrdinalIgnoreCase)
                .Select(group => new ModOffer(group))
                .OrderByDescending(offer => offer.HasUpdates)
                .ThenBy(offer => offer.Title, StringComparer.CurrentCultureIgnoreCase)
                .ToList();
        }

        internal static string NewOfferId(ManifestModEntry remote)
        {
            return "new:" + (DeclineGroup(remote) ?? remote.id);
        }

        internal IEnumerable<string> DeclineIds()
        {
            return Packages.Select(item => NewOfferId(item.Remote)).Distinct(StringComparer.OrdinalIgnoreCase);
        }

        internal static string PackageName(ManifestModEntry package)
        {
            switch (package.id)
            {
                case "net.openwg.common": return "OpenWG Common";
                case "net.openwg.gpu.upscaler": return "Апскейлер";
                case "net.openwg.gpu.upscaler.xess": return "Intel XeSS";
                case "net.openwg.fix.battleresultscache": return "Кеш результатів бою";
                case "net.openwg.fix.battleresultsreplays": return "Результати бою в реплеях";
                case "net.openwg.gameface": return "OpenWG GameFace";
                default: return package.id;
            }
        }

        internal string Description()
        {
            var sections = Packages.Where(item => !string.IsNullOrWhiteSpace(item.Remote.changes))
                .GroupBy(item => item.Remote.changes.Trim(), StringComparer.Ordinal)
                .Select(group => Packages.Count == 1 || group.Count() == Packages.Count
                    ? group.Key : string.Join(", ", group.Select(item => PackageName(item.Remote))) + "\r\n" + group.Key)
                .ToList();
            var notes = Packages.Where(item => item.Remote.possible_cheat)
                .Select(item => string.IsNullOrWhiteSpace(item.Remote.possible_cheat_note)
                    ? "Може детектуватися як чіт. Використовуйте на власний розсуд."
                    : item.Remote.possible_cheat_note.Trim()).Distinct();
            return string.Join("\r\n\r\n", notes.Concat(sections));
        }
    }

    internal sealed class UpdateSplitter : SplitContainer
    {
        private bool hot;

        internal UpdateSplitter()
        {
            SetStyle(ControlStyles.OptimizedDoubleBuffer, true);
            AccessibleName = "Ширина списку й опису";
        }

        protected override void OnMouseMove(MouseEventArgs e)
        {
            base.OnMouseMove(e);
            SetHot(SplitterRectangle.Contains(e.Location));
        }

        protected override void OnMouseLeave(EventArgs e)
        {
            base.OnMouseLeave(e);
            SetHot(false);
        }

        private void SetHot(bool value)
        {
            if (hot == value) return;
            hot = value;
            Invalidate(SplitterRectangle);
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            base.OnPaint(e);
            if (Panel1Collapsed || Panel2Collapsed) return;
            Rectangle bar = SplitterRectangle;
            using (var track = new SolidBrush(hot ? Color.FromArgb(61, 53, 43) : Color.FromArgb(31, 32, 33)))
            using (var grip = new SolidBrush(hot ? Color.FromArgb(239, 168, 79) : Color.FromArgb(126, 126, 125)))
            {
                e.Graphics.FillRectangle(track, bar);
                for (int i = -1; i <= 1; i++)
                    for (int column = 0; column < 2; column++)
                        e.Graphics.FillEllipse(grip, bar.X + (bar.Width - 8) / 2 + column * 5, bar.Y + bar.Height / 2 + i * 6, 3, 3);
            }
        }
    }

    internal sealed class WorkshopHeader : Panel
    {
        private readonly Image artwork;
        private readonly Color accent;

        internal WorkshopHeader(Color background, Color accent)
        {
            BackColor = background;
            this.accent = accent;
            ResizeRedraw = true;
            using (Stream stream = Assembly.GetExecutingAssembly().GetManifestResourceStream("Workshop.Track"))
            {
                if (stream != null)
                    using (Image photo = Image.FromStream(stream)) artwork = new Bitmap(photo);
            }
        }

        protected override void OnPaintBackground(PaintEventArgs e)
        {
            base.OnPaintBackground(e);
            if (artwork != null && Width > 0 && Height > 0)
            {
                int cropHeight = Math.Min(artwork.Height, Math.Max(1, artwork.Width * Height / Width));
                int top = (artwork.Height - cropHeight) * 2 / 5;
                e.Graphics.DrawImage(artwork, ClientRectangle, 0, top, artwork.Width, cropHeight, GraphicsUnit.Pixel);
            }
            using (var rule = new SolidBrush(accent)) e.Graphics.FillRectangle(rule, 0, Height - 2, Width, 2);
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing && artwork != null) artwork.Dispose();
            base.Dispose(disposing);
        }
    }

    public class UpdateDialogForm : Form
    {
        private readonly string gamePath;
        private readonly string gameVer;
        private readonly SelfUpdateState launcherUpdate;
        private readonly string settingsFolder;
        private readonly List<ModOffer> offers;
        private readonly List<PendingModUpdate> catalog;
        private readonly HashSet<PendingModUpdate> restored = new HashSet<PendingModUpdate>();
        private readonly UpdateSplitter splitter;
        private readonly DataGridView list;
        private readonly Label lblSubtitle;
        private readonly CheckBox chkLauncher;
        private readonly Label lblDetailTitle;
        private readonly FlowLayoutPanel packageList;
        private readonly TextBox description;
        private readonly Button btnUpdate;
        private readonly Button btnSkip;
        private readonly Button btnDecline;
        private readonly Button btnCatalog;
        private readonly CheckBox master;
        private readonly ProgressBar progress;
        private readonly Label lblStatus;
        private readonly Font fontBase = new Font("Segoe UI", 12f);
        private readonly Font fontTitle = new Font("Segoe UI", 26f, FontStyle.Bold);
        private readonly Font fontHeader = new Font("Segoe UI", 17f, FontStyle.Bold);
        private readonly Font fontButton = new Font("Segoe UI", 11f, FontStyle.Bold);

        private bool isLoading;
        private bool isUpdating;
        private int lastReportedProgress = -1;

        public bool ApplyLauncherUpdate { get; private set; }

        private static readonly Color ColBg = Color.FromArgb(18, 19, 20);
        private static readonly Color ColPanel = Color.FromArgb(22, 23, 24);
        private static readonly Color ColRow = Color.FromArgb(29, 30, 31);
        private static readonly Color ColList = Color.FromArgb(22, 23, 24);
        private static readonly Color ColText = Color.FromArgb(247, 246, 242);
        private static readonly Color ColMuted = Color.FromArgb(187, 185, 180);
        private static readonly Color ColGold = Color.FromArgb(239, 168, 79);
        private static readonly Color ColButton = Color.FromArgb(31, 32, 33);
        private static readonly Color ColButtonBorder = Color.FromArgb(79, 79, 78);
        private static readonly Color ColRed = Color.FromArgb(157, 45, 54);
        private static readonly Color ColRedHover = Color.FromArgb(191, 57, 67);

        public UpdateDialogForm(string gamePath, string gameVer, List<PendingModUpdate> updates, SelfUpdateState launcherUpdate)
            : this(gamePath, gameVer, updates, launcherUpdate, Program.LauncherDir)
        {
        }

        internal UpdateDialogForm(string gamePath, string gameVer, List<PendingModUpdate> updates, SelfUpdateState launcherUpdate, string settingsFolder,
            List<PendingModUpdate> catalog = null)
        {
            this.gamePath = gamePath;
            this.gameVer = gameVer;
            this.launcherUpdate = launcherUpdate;
            this.settingsFolder = settingsFolder;
            this.catalog = catalog ?? new List<PendingModUpdate>(updates);
            ApplyLauncherUpdate = launcherUpdate != null;
            offers = ModOffer.Create(updates);

            Text = "Майстерня — WoT Modpack";
            StartPosition = FormStartPosition.CenterScreen;
            ClientSize = new Size(1020, Math.Min(630, 450 + Math.Max(2, offers.Count) * 40));
            MinimumSize = new Size(760, 445);
            BackColor = ColBg;
            ForeColor = ColText;
            Font = fontBase;
            AutoScaleMode = AutoScaleMode.Font;
            FormBorderStyle = FormBorderStyle.Sizable;
            MaximizeBox = true;
            MinimizeBox = false;
            DoubleBuffered = true;
            string ico = Path.Combine(gamePath, "game_metadata", "game.ico");
            if (File.Exists(ico))
            {
                try { Icon = new Icon(ico); }
                catch (ArgumentException) { }
                catch (IOException) { }
            }

            var root = MakeLayout(ColBg);
            root.RowStyles.Add(new RowStyle(SizeType.AutoSize));
            root.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
            root.RowStyles.Add(new RowStyle(SizeType.AutoSize));
            Controls.Add(root);

            var masthead = new WorkshopHeader(ColBg, ColGold) { Dock = DockStyle.Top, Height = 87, Margin = new Padding(0) };
            var header = new TableLayoutPanel {
                Dock = DockStyle.Fill, ColumnCount = 3, BackColor = Color.Transparent, Margin = new Padding(0),
                Padding = new Padding(26, 8, 20, 10)
            };
            header.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
            header.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
            header.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
            header.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
            header.RowStyles.Add(new RowStyle(SizeType.AutoSize));
            var title = MakeLabel("Оновлення модів", fontTitle, ColText);
            title.Anchor = AnchorStyles.Left;
            title.Margin = new Padding(0, 0, 14, 0);
            lblSubtitle = MakeLabel("", fontBase, ColMuted);
            lblSubtitle.Anchor = AnchorStyles.Left;
            lblSubtitle.Margin = new Padding(14, 5, 0, 0);
            header.Controls.Add(title, 0, 0);
            header.Controls.Add(new Panel { Width = 1, Height = 24, BackColor = ColMuted, Anchor = AnchorStyles.None, Margin = new Padding(0, 5, 0, 0) }, 1, 0);
            header.Controls.Add(lblSubtitle, 2, 0);
            chkLauncher = new CheckBox {
                Text = launcherUpdate == null ? "" : "Оновити лаунчер до " + launcherUpdate.version,
                AccessibleName = "Оновити лаунчер", AutoSize = true, Checked = launcherUpdate != null,
                Visible = launcherUpdate != null, Anchor = AnchorStyles.Left,
                ForeColor = ColGold, Margin = new Padding(0, 1, 0, 0)
            };
            header.Controls.Add(chkLauncher, 0, 1);
            header.SetColumnSpan(chkLauncher, 3);
            masthead.Controls.Add(header);
            root.Controls.Add(masthead, 0, 0);

            splitter = new UpdateSplitter {
                Size = new Size(1020, 390), Dock = DockStyle.Fill, Margin = new Padding(0),
                BackColor = ColBg, SplitterWidth = 13, Panel1MinSize = 282, Panel2MinSize = 285,
                SplitterDistance = 396
            };
            root.Controls.Add(splitter, 0, 1);

            var listPane = MakeLayout(ColPanel);
            listPane.Padding = new Padding(19, 15, 11, 12);
            listPane.RowStyles.Add(new RowStyle(SizeType.AutoSize));
            listPane.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
            master = new CheckBox {
                Text = "Позначити всі", AccessibleName = "Позначити всі моди", AutoSize = true,
                AutoCheck = false, ThreeState = true, ForeColor = ColText, Margin = new Padding(8, 0, 0, 8)
            };
            master.Click += (s, e) => SetAllChecked(master.CheckState != CheckState.Checked);
            listPane.Controls.Add(master, 0, 0);
            list = CreateList();
            listPane.Controls.Add(list, 0, 1);
            splitter.Panel1.Controls.Add(listPane);

            var detail = MakeLayout(ColPanel);
            detail.Padding = new Padding(23, 15, 24, 19);
            detail.RowStyles.Add(new RowStyle(SizeType.AutoSize));
            detail.RowStyles.Add(new RowStyle(SizeType.AutoSize));
            detail.RowStyles.Add(new RowStyle(SizeType.AutoSize));
            detail.RowStyles.Add(new RowStyle(SizeType.AutoSize));
            detail.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
            lblDetailTitle = MakeLabel("Зміни", fontHeader, ColText);
            detail.Controls.Add(lblDetailTitle, 0, 0);
            description = new TextBox {
                Dock = DockStyle.Top, ReadOnly = true, Multiline = true, BorderStyle = BorderStyle.None,
                WordWrap = true, BackColor = ColPanel,
                ForeColor = ColText, Font = fontBase, AccessibleName = "Опис змін",
                Margin = new Padding(0, 8, 0, 16)
            };
            detail.Controls.Add(description, 0, 1);
            packageList = new FlowLayoutPanel {
                BackColor = ColRow, Dock = DockStyle.Top, AutoSize = true, AutoSizeMode = AutoSizeMode.GrowAndShrink,
                WrapContents = true, Padding = new Padding(10, 9, 9, 9), Margin = new Padding(0, 0, 0, 13)
            };
            detail.Controls.Add(packageList, 0, 2);
            btnDecline = CreateButton("Більше не пропонувати", 220, false);
            btnDecline.Anchor = AnchorStyles.Left;
            btnDecline.BackColor = ColRed;
            btnDecline.FlatAppearance.BorderSize = 0;
            btnDecline.FlatAppearance.MouseOverBackColor = ColRedHover;
            btnDecline.FlatAppearance.MouseDownBackColor = ColRed;
            btnDecline.Click += (s, e) => OnDecline(SelectedOffer);
            detail.Controls.Add(btnDecline, 0, 3);
            splitter.Panel2.Controls.Add(detail);
            detail.SizeChanged += (s, e) =>
            {
                int width = Math.Max(1, detail.ClientSize.Width - detail.Padding.Horizontal);
                var maximum = new Size(width, 0);
                if (lblDetailTitle.MaximumSize != maximum) lblDetailTitle.MaximumSize = maximum;
                foreach (Control control in packageList.Controls)
                    control.MaximumSize = new Size(Math.Max(160, width - packageList.Padding.Horizontal), 0);
                ResizeDescription(SelectedOffer);
            };
            packageList.SizeChanged += (s, e) => ResizeDescription(SelectedOffer);

            var footer = new TableLayoutPanel {
                Dock = DockStyle.Top, AutoSize = true, ColumnCount = 2, Margin = new Padding(0),
                Padding = new Padding(20, 12, 17, 14), BackColor = ColBg
            };
            footer.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
            footer.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
            btnCatalog = CreateButton("Доступні й відхилені", 201, false);
            btnCatalog.Anchor = AnchorStyles.Left;
            btnCatalog.Click += (s, e) => ShowCatalog();
            footer.Controls.Add(btnCatalog, 0, 0);
            lblStatus = MakeLabel("", fontBase, ColMuted);
            lblStatus.Anchor = AnchorStyles.Left;
            lblStatus.Visible = false;
            footer.Controls.Add(lblStatus, 0, 1);
            footer.SetColumnSpan(lblStatus, 2);
            progress = new ProgressBar { Dock = DockStyle.Top, Height = 8, Style = ProgressBarStyle.Continuous, Visible = false };
            footer.Controls.Add(progress, 0, 2);
            footer.SetColumnSpan(progress, 2);
            var playActions = MakeActions();
            playActions.FlowDirection = FlowDirection.RightToLeft;
            btnUpdate = CreateButton("Грати", 206, true);
            btnSkip = CreateButton("Без оновлень", 148, false);
            playActions.Controls.Add(btnUpdate);
            playActions.Controls.Add(btnSkip);
            footer.Controls.Add(playActions, 1, 0);
            root.Controls.Add(footer, 0, 2);

            btnUpdate.Click += (s, e) => OnPrimary();
            btnSkip.Click += (s, e) => OnSkip();
            chkLauncher.CheckedChanged += (s, e) => UpdateState();
            Shown += (s, e) => RestoreSplit();
            AcceptButton = btnUpdate;
            CancelButton = btnSkip;
            LoadItems();
        }

        private static TableLayoutPanel MakeLayout(Color background)
        {
            var layout = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 1, BackColor = background, Margin = new Padding(0) };
            layout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
            return layout;
        }

        private static Label MakeLabel(string text, Font font, Color color)
        {
            return new Label { Text = text, UseMnemonic = false, Font = font, ForeColor = color, AutoSize = true, Margin = new Padding(0, 0, 0, 3) };
        }

        private static FlowLayoutPanel MakeActions()
        {
            return new FlowLayoutPanel {
                AutoSize = true, AutoSizeMode = AutoSizeMode.GrowAndShrink, Dock = DockStyle.Top,
                WrapContents = false, Margin = new Padding(0)
            };
        }

        private Button CreateButton(string title, int width, bool primary)
        {
            var button = new Button {
                Text = title, Width = width, Height = 40, Margin = new Padding(0, 4, 8, 0),
                Font = fontButton, FlatStyle = FlatStyle.Flat, UseVisualStyleBackColor = false,
                BackColor = primary ? ColGold : ColButton, ForeColor = primary ? ColBg : ColText
            };
            button.FlatAppearance.BorderSize = primary ? 0 : 1;
            button.FlatAppearance.BorderColor = ColButtonBorder;
            button.FlatAppearance.MouseOverBackColor = primary ? Color.FromArgb(252, 190, 112) : Color.FromArgb(48, 47, 45);
            return button;
        }

        private DataGridView CreateList()
        {
            var grid = new DataGridView {
                Dock = DockStyle.Fill, BorderStyle = BorderStyle.None,
                BackgroundColor = ColList, GridColor = ColButtonBorder, CellBorderStyle = DataGridViewCellBorderStyle.SingleHorizontal,
                ColumnHeadersVisible = false, RowHeadersVisible = false, AllowUserToAddRows = false,
                AllowUserToDeleteRows = false, AllowUserToResizeColumns = false, AllowUserToResizeRows = false,
                SelectionMode = DataGridViewSelectionMode.FullRowSelect, MultiSelect = false,
                ReadOnly = true, AccessibleName = "Моди для встановлення або оновлення",
                Margin = new Padding(0, 6, 0, 5)
            };
            grid.RowTemplate.Height = 62;
            grid.DefaultCellStyle.BackColor = ColList;
            grid.DefaultCellStyle.ForeColor = ColText;
            grid.DefaultCellStyle.SelectionBackColor = Color.FromArgb(54, 43, 30);
            grid.DefaultCellStyle.SelectionForeColor = ColText;
            grid.DefaultCellStyle.Font = fontBase;
            grid.Columns.Add(new DataGridViewCheckBoxColumn {
                Name = "Install", HeaderText = "Позначка встановлення", Width = 41, ThreeState = true,
                TrueValue = CheckState.Checked, FalseValue = CheckState.Unchecked, IndeterminateValue = CheckState.Indeterminate
            });
            grid.Columns.Add(new DataGridViewTextBoxColumn {
                Name = "Title", HeaderText = "Мод", ReadOnly = true, AutoSizeMode = DataGridViewAutoSizeColumnMode.Fill
            });
            grid.Columns.Add(new DataGridViewButtonColumn {
                Name = "Decline", HeaderText = "Більше не пропонувати", Width = 40
            });
            grid.CellPainting += PaintOfferRow;
            grid.CellClick += (s, e) =>
            {
                if (e.RowIndex < 0) return;
                DataGridViewRow row = grid.Rows[e.RowIndex];
                if (e.ColumnIndex == 0) ToggleOffer(row);
                if (e.ColumnIndex == 2)
                {
                    var offer = row.Tag as ModOffer;
                    if (offer != null) BeginInvoke(new Action(() => OnDecline(offer)));
                }
            };
            grid.CellMouseEnter += (s, e) =>
            {
                if (e.RowIndex < 0 || e.ColumnIndex != 2 || !(grid.Rows[e.RowIndex].Tag is ModOffer)) return;
                grid.Cursor = Cursors.Hand;
                grid.InvalidateCell(e.ColumnIndex, e.RowIndex);
            };
            grid.CellMouseLeave += (s, e) =>
            {
                if (e.RowIndex < 0 || e.ColumnIndex != 2) return;
                grid.Cursor = Cursors.Default;
                grid.InvalidateCell(e.ColumnIndex, e.RowIndex);
            };
            grid.KeyDown += (s, e) =>
            {
                if (grid.CurrentRow == null) return;
                if (e.KeyCode == Keys.Up || e.KeyCode == Keys.Down)
                {
                    int step = e.KeyCode == Keys.Up ? -1 : 1;
                    MoveToOffer(grid.CurrentRow.Index + step, step);
                    e.SuppressKeyPress = true;
                    return;
                }
                if (e.KeyCode != Keys.Space && e.KeyCode != Keys.Delete) return;
                e.SuppressKeyPress = true;
                if (e.KeyCode == Keys.Delete || grid.CurrentCell.ColumnIndex == 2) OnDecline(grid.CurrentRow.Tag as ModOffer);
                else ToggleOffer(grid.CurrentRow);
            };
            grid.CurrentCellChanged += (s, e) =>
            {
                if (isLoading || grid.CurrentRow == null) return;
                if (grid.CurrentRow.Tag is string) NavQueueSection(grid.CurrentRow.Index);
                else RenderDetail();
            };
            return grid;
        }

        private void NavQueueSection(int index)
        {
            BeginInvoke(new Action(() =>
            {
                if (list.CurrentRow != null && list.CurrentRow.Index == index && list.CurrentRow.Tag is string)
                    MoveToOffer(index + 1, 1);
            }));
        }

        private void MoveToOffer(int index, int step)
        {
            for (; index >= 0 && index < list.Rows.Count; index += step)
            {
                DataGridViewRow row = list.Rows[index];
                if (!(row.Tag is ModOffer)) continue;
                list.CurrentCell = row.Cells[1];
                return;
            }
        }

        private void ToggleOffer(DataGridViewRow row)
        {
            var offer = row.Tag as ModOffer;
            if (isUpdating || offer == null) return;
            SetOfferChecked(offer, offer.Selected.Count != offer.Packages.Count);
            RefreshRow(row, offer);
            RenderDetail();
            UpdateState();
        }

        private static string VersionLabel(PendingModUpdate item)
        {
            return item.IsNew ? item.Remote.version
                : string.Format("{0} → {1}", item.InstalledVersion ?? "?", item.Remote.version);
        }

        private static string CommonVersion(ModOffer offer)
        {
            return offer.Packages.Select(VersionLabel).Distinct().Count() == 1 ? VersionLabel(offer.Packages[0]) : null;
        }

        private static string RowVersion(ModOffer offer)
        {
            return (offer.HasWarning ? "Увага · " : "") + (CommonVersion(offer) ?? "Кілька пакетів");
        }

        private void PaintOfferRow(object sender, DataGridViewCellPaintingEventArgs e)
        {
            if (e.RowIndex < 0 || e.ColumnIndex < 0) return;
            var grid = (DataGridView)sender;
            object tag = grid.Rows[e.RowIndex].Tag;
            string section = tag as string;
            var flags = TextFormatFlags.SingleLine | TextFormatFlags.EndEllipsis | TextFormatFlags.NoPrefix | TextFormatFlags.VerticalCenter;
            if (section != null)
            {
                e.PaintBackground(e.CellBounds, false);
                if (e.ColumnIndex == 1)
                {
                    TextRenderer.DrawText(e.Graphics, section, fontButton, e.CellBounds, ColMuted, flags);
                    int length = TextRenderer.MeasureText(section, fontButton).Width;
                    int y = e.CellBounds.Top + e.CellBounds.Height / 2;
                    using (var pen = new Pen(ColButtonBorder))
                        e.Graphics.DrawLine(pen, Math.Min(e.CellBounds.Left + length + 9, e.CellBounds.Right), y, e.CellBounds.Right - 2, y);
                }
                e.Handled = true;
                return;
            }
            var offer = tag as ModOffer;
            if (offer == null) return;

            if (e.ColumnIndex == 0)
            {
                e.Paint(e.CellBounds, e.PaintParts);
                if ((e.State & DataGridViewElementStates.Selected) != 0)
                    using (var strip = new SolidBrush(ColGold)) e.Graphics.FillRectangle(strip, e.CellBounds.Left, e.CellBounds.Top, 4, e.CellBounds.Height);
                e.Handled = true;
                return;
            }

            e.PaintBackground(e.CellBounds, true);
            if (e.ColumnIndex == 2)
            {
                int size = Math.Min(28, e.CellBounds.Width - 8);
                var button = new Rectangle(e.CellBounds.Left + (e.CellBounds.Width - size) / 2,
                    e.CellBounds.Top + (e.CellBounds.Height - size) / 2, size, size);
                bool hot = e.CellBounds.Contains(grid.PointToClient(Cursor.Position));
                using (var red = new SolidBrush(hot ? ColRedHover : ColRed)) e.Graphics.FillRectangle(red, button);
                int x = button.Left + button.Width / 2;
                int y = button.Top + button.Height / 2;
                using (var cross = new Pen(ColText, 2))
                {
                    e.Graphics.DrawLine(cross, x - 4, y - 4, x + 4, y + 4);
                    e.Graphics.DrawLine(cross, x - 4, y + 4, x + 4, y - 4);
                }
                e.Paint(e.CellBounds, DataGridViewPaintParts.Border | DataGridViewPaintParts.Focus);
                e.Handled = true;
                return;
            }
            var titleBounds = new Rectangle(e.CellBounds.Left + 3, e.CellBounds.Top + 9, Math.Max(1, e.CellBounds.Width - 11), 21);
            var versionBounds = new Rectangle(titleBounds.Left, titleBounds.Bottom + 2, titleBounds.Width, 19);
            TextRenderer.DrawText(e.Graphics, offer.Title, fontButton, titleBounds, ColText, flags);
            Color versionColor = offer.HasWarning ? ColGold : ColMuted;
            TextRenderer.DrawText(e.Graphics, RowVersion(offer), fontBase, versionBounds, versionColor, flags);
            e.Paint(e.CellBounds, DataGridViewPaintParts.Border | DataGridViewPaintParts.Focus);
            e.Handled = true;
        }

        private ModOffer SelectedOffer
        {
            get { return list.CurrentRow == null ? null : list.CurrentRow.Tag as ModOffer; }
        }

        private void LoadItems(int selectedIndex = 0)
        {
            isLoading = true;
            list.Rows.Clear();
            var offerRows = new List<DataGridViewRow>();
            foreach (var group in offers.GroupBy(item => item.HasUpdates))
            {
                string caption = group.Key ? "ОНОВЛЕННЯ" : "НОВІ МОДИ";
                DataGridViewRow heading = list.Rows[list.Rows.Add(null, caption)];
                heading.Tag = caption;
                heading.Height = 32;
                foreach (ModOffer offer in group)
                {
                    DataGridViewRow row = list.Rows[list.Rows.Add(CheckState.Unchecked, offer.Title, "×")];
                    row.Tag = offer;
                    row.Cells[1].ToolTipText = offer.Title + "\n" + RowVersion(offer);
                    row.Cells[2].ToolTipText = offer.HasUpdates ? "Видалити з гри й більше не пропонувати" : "Більше не пропонувати";
                    RefreshRow(row, offer);
                    offerRows.Add(row);
                }
            }
            splitter.Panel1Collapsed = offerRows.Count == 0;
            if (!splitter.Panel1Collapsed)
                list.CurrentCell = offerRows[Math.Min(selectedIndex, offerRows.Count - 1)].Cells[1];
            isLoading = false;
            RenderDetail();
            UpdateState();
        }

        private void RenderDetail()
        {
            ModOffer offer = SelectedOffer;
            lblDetailTitle.Text = offer == null ? "Оновлень для модів немає" : "Зміни";
            description.Visible = offer != null;
            string changes = offer == null ? "" : offer.Description();
            description.Text = offer != null && string.IsNullOrWhiteSpace(changes) ? "Опис випуску відсутній." : changes;
            btnDecline.Visible = offer != null;
            btnDecline.Enabled = !isUpdating && offer != null;
            packageList.SuspendLayout();
            while (packageList.Controls.Count > 0) packageList.Controls[0].Dispose();
            bool showPackages = offer != null && offer.Packages.Count > 1;
            packageList.Visible = showPackages;
            if (showPackages)
            {
                bool showVersions = CommonVersion(offer) == null;
                var packagesTitle = MakeLabel("Пакети", fontButton, ColText);
                packagesTitle.Margin = new Padding(0, 0, 0, 7);
                packageList.Controls.Add(packagesTitle);
                packageList.SetFlowBreak(packagesTitle, true);
                foreach (PendingModUpdate package in offer.Packages)
                {
                    string version = showVersions ? " · " + (package.IsNew && offer.HasUpdates ? "Новий · " : "") + VersionLabel(package) : "";
                    var check = new CheckBox {
                        Text = ModOffer.PackageName(package.Remote) + version, AutoSize = true, UseMnemonic = false,
                        ForeColor = ColText, Checked = offer.Selected.Contains(package), Margin = new Padding(0, 2, 13, 2),
                        MaximumSize = new Size(Math.Max(160, packageList.Width - packageList.Padding.Horizontal), 0)
                    };
                    check.CheckedChanged += (s, e) =>
                    {
                        if (check.Checked) offer.Selected.Add(package);
                        else offer.Selected.Remove(package);
                        RefreshRow(list.CurrentRow, offer);
                        UpdateState();
                    };
                    packageList.Controls.Add(check);
                }
            }
            packageList.ResumeLayout();
            ResizeDescription(offer);
        }

        private void ResizeDescription(ModOffer offer)
        {
            var detail = description.Parent as TableLayoutPanel;
            if (offer == null || detail == null) return;
            int width = Math.Max(1, detail.DisplayRectangle.Width - description.Margin.Horizontal);
            var area = new Size(width, int.MaxValue);
            var flags = TextFormatFlags.WordBreak | TextFormatFlags.TextBoxControl | TextFormatFlags.NoPrefix;
            int needed = TextRenderer.MeasureText(description.Text, description.Font, area, flags).Height + description.Font.Height;
            int available = detail.DisplayRectangle.Height - lblDetailTitle.Height - lblDetailTitle.Margin.Vertical - description.Margin.Vertical;
            if (offer.Packages.Count > 1) available -= packageList.Height + packageList.Margin.Vertical;
            available -= btnDecline.Height + btnDecline.Margin.Vertical;
            int height = Math.Max(description.Font.Height, Math.Min(available, needed));
            if (description.Height != height) description.Height = height;
            ScrollBars bars = needed > height ? ScrollBars.Vertical : ScrollBars.None;
            if (description.ScrollBars != bars) description.ScrollBars = bars;
        }

        private void RefreshRow(DataGridViewRow row, ModOffer offer)
        {
            bool previous = isLoading;
            isLoading = true;
            row.Cells[0].Value = offer.Selected.Count == 0 ? CheckState.Unchecked
                : offer.Selected.Count == offer.Packages.Count ? CheckState.Checked : CheckState.Indeterminate;
            row.Cells[0].ToolTipText = offer.Selected.Count > 0 && offer.Selected.Count < offer.Packages.Count
                ? string.Format("Позначено пакетів: {0} із {1}", offer.Selected.Count, offer.Packages.Count) : "";
            if (row.DataGridView != null) row.DataGridView.InvalidateRow(row.Index);
            isLoading = previous;
        }

        private static void SetOfferChecked(ModOffer offer, bool value)
        {
            offer.Selected.Clear();
            if (value) offer.Selected.UnionWith(offer.Packages);
        }

        private void SetAllChecked(bool value)
        {
            if (isUpdating) return;
            foreach (DataGridViewRow row in list.Rows)
            {
                var offer = row.Tag as ModOffer;
                if (offer == null) continue;
                SetOfferChecked(offer, value);
                RefreshRow(row, offer);
            }
            RenderDetail();
            UpdateState();
        }

        private List<PendingModUpdate> GetChecked()
        {
            return offers.SelectMany(offer => offer.Packages.Where(item => offer.Selected.Contains(item))).ToList();
        }

        private void UpdateState()
        {
            if (isUpdating) return;
            int ready = offers.Count(offer => offer.Selected.Count > 0);
            lblSubtitle.Text = "WoT " + gameVer;
            bool launcherChecked = launcherUpdate != null && chkLauncher.Checked;
            btnUpdate.Text = ready > 0 || launcherChecked ? "Оновити й грати" : "Грати";
            btnSkip.Visible = ready > 0 || launcherUpdate != null;
            master.CheckState = ready == 0 ? CheckState.Unchecked
                : offers.All(offer => offer.Selected.Count == offer.Packages.Count) ? CheckState.Checked : CheckState.Indeterminate;
        }

        private void OnPrimary()
        {
            if (isUpdating) return;
            var selected = GetChecked();
            if (selected.Count > 0) StartUpdateProcess(selected);
            else Close();
        }

        private void OnSkip()
        {
            if (isUpdating) return;
            chkLauncher.Checked = false;
            Close();
        }

        private void OnDecline(ModOffer selected)
        {
            if (isUpdating || selected == null || !offers.Contains(selected)) return;
            if (selected.HasUpdates)
            {
                string message = "Видалити «" + selected.Title + "» з гри й більше не пропонувати?\n" +
                    "Мод можна додати знову через «Доступні й відхилені».";
                DialogResult answer = MessageBox.Show(this, message, "WoT Modpack",
                    MessageBoxButtons.YesNo, MessageBoxIcon.Warning, MessageBoxDefaultButton.Button2);
                if (answer != DialogResult.Yes) return;
            }
            try
            {
                DismissOffer(selected);
            }
            catch (Exception error)
            {
                MessageBox.Show(this, "Не вдалося відхилити мод.\n" + error.Message, "WoT Modpack",
                    MessageBoxButtons.OK, MessageBoxIcon.Warning);
            }
        }

        internal bool DismissOffer(ModOffer selected)
        {
            if (isUpdating || selected == null) return false;
            int index = offers.IndexOf(selected);
            if (index < 0) return false;
            string choicesPath = Path.Combine(settingsFolder, "declined.json");
            if (selected.HasUpdates)
            {
                var group = catalog.Where(item => string.Equals(ModOffer.DeclineGroup(item.Remote) ?? item.Remote.id,
                    selected.Key, StringComparison.OrdinalIgnoreCase)).ToList();
                Program.RemoveModOffer(gamePath, gameVer, choicesPath, ModOffer.Create(group).Single());
                foreach (var item in group)
                {
                    item.IsNew = true;
                    item.InstalledVersion = null;
                    item.InstalledFiles = null;
                    item.LocalFilePath = Path.Combine(gamePath, "mods", gameVer, item.Remote.subdir ?? "", item.Remote.file);
                }
            }
            else Program.RememberDeclinedMods(choicesPath, selected);
            restored.ExceptWith(selected.Packages);
            offers.Remove(selected);
            LoadItems(index);
            return true;
        }

        private void ShowCatalog()
        {
            using (Form dialog = CreateCatalogDialog()) dialog.ShowDialog(this);
        }

        internal Form CreateCatalogDialog()
        {
            var dialog = new Form {
                Text = "Доступні й відхилені моди", StartPosition = FormStartPosition.CenterParent, ClientSize = new Size(730, 425),
                MinimumSize = new Size(545, 340), BackColor = ColBg, ForeColor = ColText, Font = fontBase,
                ShowInTaskbar = false, MinimizeBox = false, MaximizeBox = false, Icon = Icon
            };
            var root = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 2, Padding = new Padding(18) };
            root.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 39));
            root.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 61));
            root.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
            root.RowStyles.Add(new RowStyle(SizeType.AutoSize));
            dialog.Controls.Add(root);

            var available = new ListBox {
                Dock = DockStyle.Fill, BackColor = ColPanel, ForeColor = ColText, IntegralHeight = false,
                BorderStyle = BorderStyle.FixedSingle, AccessibleName = "Доступні для встановлення моди",
                Margin = new Padding(0, 0, 16, 0), DrawMode = DrawMode.OwnerDrawFixed, ItemHeight = 52
            };
            var entries = ModOffer.Create(catalog.Where(item => item.IsNew));
            var choices = new HashSet<string>(Program.LoadDeclinedMods(Path.Combine(settingsFolder, "declined.json")),
                StringComparer.OrdinalIgnoreCase);
            available.Items.AddRange(entries.Select(offer => (object)offer.Title).ToArray());
            available.DrawItem += (s, e) =>
            {
                if (e.Index < 0) return;
                Color background = (e.State & DrawItemState.Selected) != 0 ? Color.FromArgb(54, 43, 30) : ColPanel;
                using (var brush = new SolidBrush(background)) e.Graphics.FillRectangle(brush, e.Bounds);
                var entry = entries[e.Index];
                var bounds = new Rectangle(e.Bounds.X + 10, e.Bounds.Y + 6, Math.Max(1, e.Bounds.Width - 20), 20);
                const TextFormatFlags flags = TextFormatFlags.SingleLine | TextFormatFlags.EndEllipsis | TextFormatFlags.NoPrefix;
                TextRenderer.DrawText(e.Graphics, entry.Title, fontButton, bounds, ColText, flags);
                bounds.Offset(0, 22);
                bool queued = offers.Any(offer => string.Equals(offer.Key, entry.Key, StringComparison.OrdinalIgnoreCase)
                    && offer.Selected.Any(entry.Packages.Contains));
                bool declined = entry.Packages.Any(item => !choices.Contains("enabled:" + item.Remote.id) &&
                    (choices.Contains(entry.Key) || choices.Contains(item.Remote.id) || choices.Contains(ModOffer.NewOfferId(item.Remote))));
                string status = queued ? "До встановлення" : declined ? "Відхилено" : "Доступний";
                Color statusColor = queued ? ColGold : declined ? Color.FromArgb(243, 134, 142) : ColMuted;
                TextRenderer.DrawText(e.Graphics, status, fontBase, bounds, statusColor, flags);
                e.DrawFocusRectangle();
            };
            root.Controls.Add(available, 0, 0);

            var notes = new TextBox {
                Dock = DockStyle.Fill, BackColor = ColPanel, ForeColor = ColText, Multiline = true, ReadOnly = true,
                BorderStyle = BorderStyle.None, WordWrap = true,
                AccessibleName = "Опис мода", Margin = new Padding(0)
            };
            var preview = new Panel { Dock = DockStyle.Fill, BackColor = ColPanel, Padding = new Padding(14), Margin = new Padding(0) };
            preview.Controls.Add(notes);
            root.Controls.Add(preview, 1, 0);
            Action resizeNotes = () =>
            {
                if (notes.Width < 1 || notes.Height < 1) return;
                var area = new Size(notes.Width, int.MaxValue);
                var flags = TextFormatFlags.TextBoxControl | TextFormatFlags.WordBreak | TextFormatFlags.NoPrefix;
                int needed = TextRenderer.MeasureText(notes.Text, notes.Font, area, flags).Height + notes.Font.Height;
                ScrollBars bars = needed > notes.Height ? ScrollBars.Vertical : ScrollBars.None;
                if (notes.ScrollBars != bars) notes.ScrollBars = bars;
            };
            notes.SizeChanged += (s, e) => resizeNotes();
            notes.TextChanged += (s, e) => resizeNotes();

            var actions = MakeActions();
            actions.FlowDirection = FlowDirection.RightToLeft;
            actions.Margin = new Padding(0, 12, 0, 0);
            var add = CreateButton("Додати до встановлення", 240, true);
            var cancel = CreateButton("Закрити", 91, false);
            cancel.DialogResult = DialogResult.Cancel;
            actions.Controls.Add(add);
            actions.Controls.Add(cancel);
            root.Controls.Add(actions, 0, 1);
            root.SetColumnSpan(actions, 2);
            dialog.AcceptButton = add;
            dialog.CancelButton = cancel;

            available.SelectedIndexChanged += (s, e) =>
            {
                string changes = available.SelectedIndex < 0 ? "" : entries[available.SelectedIndex].Description();
                notes.Text = available.SelectedIndex < 0 ? "Немає доступних модів для встановлення."
                    : string.IsNullOrWhiteSpace(changes) ? "Опис випуску відсутній." : changes;
                add.Enabled = available.SelectedIndex >= 0;
            };
            add.Click += (s, e) =>
            {
                if (available.SelectedIndex < 0) return;
                QueueAvailableOffer(entries[available.SelectedIndex]);
                dialog.Close();
            };
            if (entries.Count > 0) available.SelectedIndex = 0;
            else
            {
                add.Enabled = false;
                notes.Text = "Немає доступних модів для встановлення.";
            }
            return dialog;
        }

        private void QueueAvailableOffer(ModOffer available)
        {
            var current = offers.FirstOrDefault(offer => string.Equals(offer.Key, available.Key, StringComparison.OrdinalIgnoreCase));
            var packages = current == null ? available.Packages : current.Packages.Union(available.Packages).ToList();
            var queued = ModOffer.Create(packages).Single();
            queued.Selected.Clear();
            if (current != null)
            {
                queued.Selected.UnionWith(current.Selected);
                offers.Remove(current);
            }
            queued.Selected.UnionWith(available.Packages);
            restored.UnionWith(available.Packages);
            offers.Add(queued);
            var ordered = offers.OrderByDescending(offer => offer.HasUpdates)
                .ThenBy(offer => offer.Title, StringComparer.CurrentCultureIgnoreCase).ToList();
            offers.Clear();
            offers.AddRange(ordered);
            LoadItems(offers.IndexOf(queued));
        }

        private void RestoreSplit()
        {
            if (splitter.Panel1Collapsed) return;
            int percent = 39;
            string path = Path.Combine(settingsFolder, "update-split.txt");
            try
            {
                int saved;
                if (File.Exists(path) && int.TryParse(File.ReadAllText(path), out saved) && saved > 0 && saved < 100)
                    percent = saved;
            }
            catch (IOException) { }
            catch (UnauthorizedAccessException) { }
            int maximum = splitter.Width - splitter.SplitterWidth - splitter.Panel2MinSize;
            if (maximum >= splitter.Panel1MinSize)
                splitter.SplitterDistance = Math.Max(splitter.Panel1MinSize, Math.Min(maximum, splitter.Width * percent / 100));
        }

        protected override void OnFormClosing(FormClosingEventArgs e)
        {
            if (isUpdating)
            {
                e.Cancel = true;
                return;
            }
            ApplyLauncherUpdate = launcherUpdate != null && chkLauncher.Checked;
            base.OnFormClosing(e);
            if (!e.Cancel && !splitter.Panel1Collapsed && splitter.Width > 0)
            {
                try
                {
                    Directory.CreateDirectory(settingsFolder);
                    File.WriteAllText(Path.Combine(settingsFolder, "update-split.txt"),
                        (splitter.SplitterDistance * 100 / splitter.Width).ToString());
                }
                catch (IOException) { }
                catch (UnauthorizedAccessException) { }
            }
        }

        private void StartUpdateProcess(List<PendingModUpdate> selected)
        {
            if (isUpdating) return;
            isUpdating = true;
            foreach (Control control in new Control[] { btnUpdate, btnSkip, btnDecline, btnCatalog, master, list, packageList, chkLauncher })
                control.Enabled = false;
            ControlBox = false;
            progress.Value = 0;
            lblStatus.Visible = true;
            progress.Visible = true;
            lblStatus.Text = "Підготовка резервної копії...";
            var worker = new Thread(() => RunUpdateWorker(selected)) { IsBackground = true };
            worker.Start();
        }

        private void RunUpdateWorker(List<PendingModUpdate> selected)
        {
            string stamp = DateTime.Now.ToString("yyyyMMdd_HHmmss_fff") + "-" + Guid.NewGuid().ToString("N");
            string bkpDir = Path.Combine(gamePath, ".backups", "launcher", stamp);
            var tempFiles = new List<string>();
            var replacedPairs = new List<string[]>();
            bool backupReady = false;
            Mutex mutation = null;
            lastReportedProgress = -1;

            try
            {
                int total = selected.Count;
                string[] downloaded = new string[total];
                long totalBytes = 0;
                for (int i = 0; i < total; i++)
                    totalBytes += Math.Max(1L, selected[i].Remote.size);
                long doneBytes = 0;
                var errors = new ConcurrentQueue<Exception>();
                var tempLock = new object();

                ParallelOptions options = new ParallelOptions { MaxDegreeOfParallelism = 4 };
                Parallel.For(0, total, options, i =>
                {
                    PendingModUpdate update = selected[i];
                    ManifestModEntry remote = update.Remote;
                    string tmpFile = Path.Combine(Path.GetTempPath(), "wot-upd-" + Guid.NewGuid().ToString("N") + ".wotmod");
                    lock (tempLock) tempFiles.Add(tmpFile);
                    try
                    {
                        SetStatus(string.Format("Завантаження ({0}/{1}): {2} v{3}...", i + 1, total, remote.title ?? remote.id, remote.version));
                        DownloadFileWithProgress(remote.url, tmpFile, remote.size, ref doneBytes, totalBytes);

                        if (remote.size > 0 && new FileInfo(tmpFile).Length != remote.size)
                            throw new InvalidDataException("Розмір файлу не збігається для " + remote.file);
                        if (!Program.VerifySha256(tmpFile, remote.sha256))
                            throw new InvalidDataException("Контрольна сума SHA-256 не збігається для " + remote.file);
                        if (!Program.VerifyWotmodArchive(tmpFile, remote.id))
                            throw new InvalidDataException("Пакет .wotmod пошкоджений або має інший ID: " + remote.file);
                        downloaded[i] = tmpFile;
                    }
                    catch (Exception ex)
                    {
                        errors.Enqueue(ex);
                    }
                });

                Exception downloadError;
                if (errors.TryDequeue(out downloadError))
                    throw downloadError;

                mutation = Program.LockModChanges();
                for (int i = 0; i < total; i++)
                {
                    PendingModUpdate update = selected[i];
                    ManifestModEntry remote = update.Remote;
                    string tmpFile = downloaded[i];
                    if (string.IsNullOrEmpty(tmpFile))
                        throw new InvalidDataException("Пакет не завантажено: " + remote.file);

                    string destDir = Path.GetDirectoryName(update.LocalFilePath);
                    if (File.Exists(destDir))
                        throw new InvalidDataException("Не вдалося оновити " + remote.file + ": шлях " + destDir + " зайнятий файлом.");
                    Directory.CreateDirectory(destDir);

                    if (update.IsNew)
                    {
                        string newFile = Path.Combine(destDir, remote.file);
                        if (File.Exists(newFile) || Directory.Exists(newFile))
                        {
                            if (!backupReady) { Directory.CreateDirectory(bkpDir); backupReady = true; }
                            string bkpFile = Path.Combine(bkpDir, GetBackupRelativePath(newFile));
                            Directory.CreateDirectory(Path.GetDirectoryName(bkpFile));
                            BackupPath(newFile, bkpFile);
                            replacedPairs.Add(new string[] { bkpFile, newFile, newFile });
                            DeletePath(newFile);
                        }
                        else
                        {
                            replacedPairs.Add(new string[] { null, newFile, newFile });
                        }
                        File.Move(tmpFile, newFile);
                    }
                    else
                    {
                        if (!backupReady) { Directory.CreateDirectory(bkpDir); backupReady = true; }
                        string newDestPath = Path.Combine(destDir, remote.file);
                        string relOld = GetBackupRelativePath(update.LocalFilePath);
                        string bkpFile = Path.Combine(bkpDir, relOld);

                        if (!SamePath(update.LocalFilePath, newDestPath)
                            && (File.Exists(newDestPath) || Directory.Exists(newDestPath)))
                        {
                            string collisionBkp = Path.Combine(bkpDir, "_collisions", Guid.NewGuid().ToString("N"), GetBackupRelativePath(newDestPath));
                            Directory.CreateDirectory(Path.GetDirectoryName(collisionBkp));
                            BackupPath(newDestPath, collisionBkp);
                            replacedPairs.Add(new string[] { collisionBkp, newDestPath, newDestPath });
                            DeletePath(newDestPath);
                        }

                        Directory.CreateDirectory(Path.GetDirectoryName(bkpFile));
                        File.Copy(update.LocalFilePath, bkpFile, true);
                        replacedPairs.Add(new string[] { bkpFile, update.LocalFilePath, newDestPath });
                        if (!SamePath(update.LocalFilePath, newDestPath))
                            DeletePath(update.LocalFilePath);
                        else
                            DeletePath(newDestPath);
                        File.Move(tmpFile, newDestPath);
                    }

                    lock (tempLock) tempFiles.Remove(tmpFile);
                    SetProgress(80 + (int)((i + 1) * 20.0 / total));
                }

                var added = selected.Where(restored.Contains).ToList();
                if (added.Count > 0)
                    Program.RememberAddedMods(Path.Combine(settingsFolder, "declined.json"), added);
                SetProgress(100);
                SetStatus("Зміни застосовано. Запускаємо гру...");
                Thread.Sleep(350);
                BeginInvoke(new Action(() =>
                {
                    isUpdating = false;
                    Close();
                }));
            }
            catch (Exception ex)
            {
                Exception actual = Unwrap(ex);
                for (int i = replacedPairs.Count - 1; i >= 0; i--)
                {
                    string[] pair = replacedPairs[i];
                    try
                    {
                        DeletePath(pair[2]);
                        if (pair[0] == null) continue;
                        if (File.Exists(pair[0]))
                        {
                            if (Directory.Exists(pair[1])) Directory.Delete(pair[1], true);
                            Directory.CreateDirectory(Path.GetDirectoryName(pair[1]));
                            File.Copy(pair[0], pair[1], true);
                        }
                        else if (Directory.Exists(pair[0]))
                        {
                            DeletePath(pair[1]);
                            CopyDirectory(pair[0], pair[1]);
                        }
                    }
                    catch { }
                }

                try
                {
                    BeginInvoke(new Action(() =>
                    {
                        isUpdating = false;
                        MessageBox.Show(
                            "Оновлення не вдалося (" + actual.Message + ").\nВідновлено попередні версії модів, запускаємо гру.",
                            "WoT Modpack Launcher", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                        Close();
                    }));
                }
                catch { }
            }
            finally
            {
                if (mutation != null)
                {
                    mutation.ReleaseMutex();
                    mutation.Dispose();
                }
                foreach (string temp in tempFiles)
                    Program.TryDeleteFile(temp);
            }
        }

        private static Exception Unwrap(Exception ex)
        {
            AggregateException aggregate = ex as AggregateException;
            if (aggregate != null && aggregate.InnerExceptions.Count > 0)
                return aggregate.InnerExceptions[0];
            return ex;
        }

        private string GetBackupRelativePath(string filePath)
        {
            string root = Path.GetFullPath(gamePath).TrimEnd('\\', '/') + Path.DirectorySeparatorChar;
            string full = Path.GetFullPath(filePath);
            if (!full.StartsWith(root, StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException("Файл поза папкою гри: " + filePath);
            return full.Substring(root.Length);
        }

        private static bool SamePath(string first, string second)
        {
            return string.Equals(Path.GetFullPath(first), Path.GetFullPath(second), StringComparison.OrdinalIgnoreCase);
        }

        private static void DeletePath(string path)
        {
            if (File.Exists(path)) File.Delete(path);
            else if (Directory.Exists(path)) Directory.Delete(path, true);
        }

        private static void BackupPath(string source, string target)
        {
            if (File.Exists(source))
            {
                Directory.CreateDirectory(Path.GetDirectoryName(target));
                File.Copy(source, target, true);
            }
            else if (Directory.Exists(source))
            {
                CopyDirectory(source, target);
            }
        }

        private static void CopyDirectory(string source, string target)
        {
            Directory.CreateDirectory(target);
            foreach (string file in Directory.GetFiles(source))
                File.Copy(file, Path.Combine(target, Path.GetFileName(file)), true);
            foreach (string directory in Directory.GetDirectories(source))
                CopyDirectory(directory, Path.Combine(target, Path.GetFileName(directory)));
        }

        private void DownloadFileWithProgress(string url, string dstPath, long expectedSize, ref long doneBytes, long totalBytes)
        {
            string localSrc = Program.ResolveLocalUrl(url);
            if (localSrc != null)
            {
                File.Copy(localSrc, dstPath, true);
                ReportByteProgress(ref doneBytes, expectedSize > 0 ? expectedSize : new FileInfo(dstPath).Length, totalBytes);
                return;
            }

            HttpWebRequest req = (HttpWebRequest)WebRequest.Create(Program.AddCacheBuster(url));
            req.UserAgent = "WotModLauncher/" + Program.LauncherVersion;
            req.Timeout = 15000;
            req.ReadWriteTimeout = 15000;
            using (HttpWebResponse resp = (HttpWebResponse)req.GetResponse())
            using (Stream stream = resp.GetResponseStream())
            using (FileStream file = File.Create(dstPath))
            {
                byte[] buffer = new byte[16384];
                int n;
                while ((n = stream.Read(buffer, 0, buffer.Length)) > 0)
                {
                    file.Write(buffer, 0, n);
                    ReportByteProgress(ref doneBytes, n, totalBytes);
                }
            }
        }

        private void ReportByteProgress(ref long doneBytes, long added, long totalBytes)
        {
            long done = Interlocked.Add(ref doneBytes, added);
            int pct = totalBytes > 0 ? (int)(done * 80L / totalBytes) : 0;
            int previous;
            do
            {
                previous = lastReportedProgress;
                if (pct <= previous) return;
            }
            while (Interlocked.CompareExchange(ref lastReportedProgress, pct, previous) != previous);
            SetProgress(pct);
        }

        private void SetStatus(string text)
        {
            try
            {
                if (IsDisposed) return;
                BeginInvoke(new Action(() => { lblStatus.Text = text; }));
            }
            catch { }
        }

        private void SetProgress(int value)
        {
            try
            {
                if (IsDisposed) return;
                BeginInvoke(new Action(() => { progress.Value = Math.Max(0, Math.Min(100, value)); }));
            }
            catch { }
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing)
            {
                fontBase.Dispose();
                fontTitle.Dispose();
                fontHeader.Dispose();
                fontButton.Dispose();
            }
            base.Dispose(disposing);
        }
    }
}
