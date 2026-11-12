using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Text;
using System.IO;
using System.IO.Compression;
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
[assembly: AssemblyFileVersion("1.4.4.0")]
[assembly: AssemblyVersion("1.4.4.0")]
[assembly: AssemblyMetadata("LucideIconLicense", "ISC License\n\nCopyright (c) 2026 Lucide Icons and Contributors\n\nPermission to use, copy, modify, and/or distribute this software for any\npurpose with or without fee is hereby granted, provided that the above\ncopyright notice and this permission notice appear in all copies.\n\nTHE SOFTWARE IS PROVIDED \"AS IS\" AND THE AUTHOR DISCLAIMS ALL WARRANTIES\nWITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF\nMERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR\nANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES\nWHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN\nACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF\nOR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.")]

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
        public string description { get; set; }
        public string summary { get; set; }
        public string author { get; set; }
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
            try
            {
                if (!File.Exists(DeclinedModsPath)) return new List<string>();
                var serializer = new JavaScriptSerializer();
                List<string> result = serializer.Deserialize<List<string>>(File.ReadAllText(DeclinedModsPath, Encoding.UTF8));
                return result ?? new List<string>();
            }
            catch
            {
                return new List<string>();
            }
        }

        public static bool AddDeclinedMods(List<string> ids)
        {
            List<string> current = LoadDeclinedMods();
            foreach (string id in ids)
            {
                if (string.IsNullOrEmpty(id)) continue;
                bool found = false;
                foreach (string existing in current)
                {
                    if (string.Equals(existing, id, StringComparison.OrdinalIgnoreCase))
                    {
                        found = true;
                        break;
                    }
                }
                if (!found) current.Add(id);
            }
            try
            {
                var serializer = new JavaScriptSerializer();
                Directory.CreateDirectory(LauncherDir);
                File.WriteAllText(DeclinedModsPath, serializer.Serialize(current), new UTF8Encoding(false));
                return true;
            }
            catch
            {
                return false;
            }
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
            if (!string.IsNullOrEmpty(gameVer))
                SyncVersionFolderIfEmpty(cfg.game_path, gameVer);

            string activeVer = gameVer;
            bool launchWithoutMods = false;
            bool applyLauncherUpdate = true;
            SelfUpdateState selfUpdatePlan = null;
            List<string> declinedMods = LoadDeclinedMods();
            ManifestRoot manifest = manifestThread.Join(6000) ? SanitizeManifest(fetchedManifest) : null;
            if (manifest != null)
            {
                selfUpdatePlan = GetSelfUpdatePlan(manifest.launcher);
                if (string.IsNullOrEmpty(activeVer)) activeVer = manifest.game_version;
                List<PendingModUpdate> updates = FindPendingUpdates(cfg.game_path, activeVer, manifest, cfg.skip_mods, declinedMods);
                if (selfUpdatePlan == null && !checkOnly && !updateOnly)
                    selfUpdatePlan = LoadPendingUpdateState();
                if (!checkOnly && (updates.Count > 0 || selfUpdatePlan != null))
                {
                    using (var form = new UpdateDialogForm(cfg.game_path, activeVer, updates, selfUpdatePlan))
                    {
                        Application.Run(form);
                        launchWithoutMods = form.LaunchWithoutMods;
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
                if (launchWithoutMods)
                    DisableMods(cfg.game_path, activeVer);
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
            var result = new List<PendingModUpdate>();
            if (manifest == null || manifest.mods == null || string.IsNullOrEmpty(gameVer))
                return result;
            if (!Regex.IsMatch(gameVer, @"^[0-9]+(\.[0-9]+){1,3}$"))
                return result;

            string verRoot = Path.Combine(gamePath, "mods", gameVer);
            Directory.CreateDirectory(verRoot);
            var idIndex = new Dictionary<string, Dictionary<string, string>>(StringComparer.OrdinalIgnoreCase);

            foreach (ManifestModEntry entry in manifest.mods)
            {
                if (!IsValidManifestMod(entry))
                    continue;
                if (IsSkipped(skipMods, entry.id) || IsSkipped(declinedMods, entry.id))
                    continue;

                string searchDir = string.IsNullOrEmpty(entry.subdir)
                    ? verRoot
                    : Path.Combine(verRoot, entry.subdir.Replace('/', Path.DirectorySeparatorChar));

                string rx = "^" + Regex.Escape(entry.id) + @"_([0-9]+(?:\.[0-9]+)*)\.wotmod$";
                string foundFile = null;
                Version foundVer = null;

                if (Directory.Exists(searchDir))
                {
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
                    // manifest ids were shortened to server_online while files keep ua.* names — 2026-11-09
                    if (foundFile == null)
                    {
                        Dictionary<string, string> ids;
                        if (!idIndex.TryGetValue(searchDir, out ids))
                        {
                            ids = BuildWotmodIdIndex(searchDir);
                            idIndex[searchDir] = ids;
                        }
                        string candidate;
                        if (ids.TryGetValue(entry.id, out candidate))
                        {
                            Match mv = Regex.Match(Path.GetFileName(candidate), @"_([0-9]+(?:\.[0-9]+)*)\.wotmod$", RegexOptions.IgnoreCase);
                            if (mv.Success)
                            {
                                foundVer = ParseVer(mv.Groups[1].Value);
                                if (foundVer != null) foundFile = candidate;
                            }
                        }
                    }
                }

                if (foundFile == null)
                {
                    if (skipMods == null && entry.default_checked == false)
                        continue;
                    result.Add(new PendingModUpdate
                    {
                        Remote = entry,
                        LocalFilePath = Path.Combine(searchDir, entry.file),
                        InstalledVersion = null,
                        IsNew = true
                    });
                    continue;
                }

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

        private static Dictionary<string, string> BuildWotmodIdIndex(string directory)
        {
            var result = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            if (!Directory.Exists(directory)) return result;
            foreach (string file in Directory.GetFiles(directory, "*.wotmod", SearchOption.TopDirectoryOnly))
            {
                string id = ReadWotmodId(file);
                if (string.IsNullOrEmpty(id)) continue;
                Match mv = Regex.Match(Path.GetFileName(file), @"_([0-9]+(?:\.[0-9]+)*)\.wotmod$", RegexOptions.IgnoreCase);
                Version version = mv.Success ? ParseVer(mv.Groups[1].Value) : null;
                string existing;
                if (result.TryGetValue(id, out existing))
                {
                    Match ev = Regex.Match(Path.GetFileName(existing), @"_([0-9]+(?:\.[0-9]+)*)\.wotmod$", RegexOptions.IgnoreCase);
                    Version existingVersion = ev.Success ? ParseVer(ev.Groups[1].Value) : null;
                    if (version == null || (existingVersion != null && version <= existingVersion))
                        continue;
                }
                result[id] = file;
            }
            return result;
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

    public class UpdateDialogForm : Form
    {
        private readonly string gamePath;
        private readonly SelfUpdateState launcherUpdate;
        private readonly List<PendingModUpdate> updateItems = new List<PendingModUpdate>();
        private readonly List<PendingModUpdate> newItems = new List<PendingModUpdate>();
        private readonly Dictionary<PendingModUpdate, ModUpdateRow> rows = new Dictionary<PendingModUpdate, ModUpdateRow>();
        private readonly CheckBox chkLauncher;
        private readonly Label lblUpdatesHeader;
        private readonly Label lblNewHeader;
        private readonly TableLayoutPanel modStack;
        private readonly Panel modScroll;
        private readonly Label lblEmpty;
        private readonly Label lblDetailsTitle;
        private readonly Label lblDetailsMeta;
        private readonly Label lblChanges;
        private readonly Label lblDescription;
        private readonly Label lblWarning;
        private readonly Button btnUpdate;
        private readonly Button btnSkip;
        private readonly Button btnOther;
        private readonly Button btnSelectAll;
        private readonly Button btnSelectNone;
        private readonly ContextMenuStrip otherMenu;
        private readonly ToolTip toolTip = new ToolTip();
        private readonly ProgressBar progress;
        private readonly Label lblStatus;
        private readonly TableLayoutPanel footer;
        private PendingModUpdate selectedItem;

        private readonly Font fontBase = new Font("Segoe UI", 14f);
        private readonly Font fontTitle = new Font("Segoe UI", 23f, FontStyle.Bold);
        private readonly Font fontHeader = new Font("Segoe UI", 17f, FontStyle.Bold);
        private readonly Font fontReading = new Font("Segoe UI", 16f);
        private readonly Panel reading;
        private readonly Font fontButton = new Font("Segoe UI", 12f, FontStyle.Bold);
        private readonly Image declineIcon = LoadIcon("iVBORw0KGgoAAAANSUhEUgAAABgAAAAYCAMAAADXqc3KAAAAIGNIUk0AAHomAACAhAAA+gAAAIDoAAB1MAAA6mAAADqYAAAXcJy6UTwAAACiUExURQAAAPCqqvCqqvCqqvCqqvCqqvCqqvCqqvCqqvCqqvCqqvCqqvCqqvCqqvCqqvCqqvCqqvCqqvCqqvCqqvCqqvCqqvCqqvCqqvCqqvCqqvCqqvCqqvCqqvCqqvCqqvCqqvCqqvCqqvCqqvCqqvCqqvCqqvCqqvCqqvCqqvCqqvCqqvCqqvCqqvCqqvCqqvCqqvCqqvCqqvCqqvCqqvCqqgAAAPpCPqAAAAA0dFJOUwABHVB8jn9THgLw9FHa8qeSqvbfL4AYMR8hIhAP9d7xfZB+F3uri5Wo79ncLjDzqZTbjFK31fRQAAAAAWJLR0QAiAUdSAAAAAd0SU1FB+oLDAgpFviMZ+8AAAD3SURBVCjPhZLrUoQwDIVTWLkIi1Ldiii6rKx7Udfbef9nMylYoOOM+VHSb5LmJIHoP1NBuDiL4kTNcRqeo7csTyc8WDIqLi5Lzd+rxPFrvq6MdU3E/s3AK46+dVF1BvQ56RL6bvLufYMHWycG6pmSGshF5yPWo4o24HODRtkKT44DrSiwVXJoNXJIhtKIiTpsPU5UYkP0jJ3PqZUXO5Q+p71khGh8rjLRmwDGZjs+qFIHRK6D3lYoRGj+R+ehndXRm1WBl34nXCWbTFeP1V5ZUWRs/2bN/puLSo58Pb1/bGWDn9Vs54dh56c4nSmRv6T7WnxXvwP9AWF1HydNzyQcAAAAAElFTkSuQmCC");
        private readonly Image checkedIcon = LoadIcon("iVBORw0KGgoAAAANSUhEUgAAABgAAAAYBAMAAAASWSDLAAAAIGNIUk0AAHomAACAhAAA+gAAAIDoAAB1MAAA6mAAADqYAAAXcJy6UTwAAAAeUExURQAAAOWaKOWaKOWaKOWaKOWaKOWaKOWaKOWaKAAAABJPWSQAAAAIdFJOUwADVZDZlx0IWf1KIAAAAAFiS0dEAIgFHUgAAAAHdElNRQfqCwwIMAJ5VhqKAAAAaklEQVQY02NgwA0YlY0hQBHIEemAghYBBgaNVoiEaYcCA4NFAFR9hAGQYwDlWGDnsJkhcTKaERy2jjYoB6gkoyMBymHuSANKwGSA1ifATcsAScA4bCAJuGnleFwA4yC7GsU/KD5FCQMkAABNpinsWcvDrAAAAABJRU5ErkJggg==");
        private readonly Image uncheckedIcon = LoadIcon("iVBORw0KGgoAAAANSUhEUgAAABgAAAAYBAMAAAASWSDLAAAAIGNIUk0AAHomAACAhAAA+gAAAIDoAAB1MAAA6mAAADqYAAAXcJy6UTwAAAAYUExURQAAAKizxqizxqizxqizxqizxqizxgAAAMNqlWgAAAAGdFJOUwADVZDZlxZXQpAAAAABYktHRACIBR1IAAAAB3RJTUUH6gsMCDACeVYaigAAADxJREFUGNNjYMANGJWNIUARyBFJg4IUAQYGtVSIhGmaAgODWQBUfZgBkGMA5ZgNdg6yq1H8g+JTlDBAAgBmRBwpTSPR5wAAAABJRU5ErkJggg==");
        private bool isLoading;
        private bool isUpdating;
        private int lastReportedProgress = -1;

        public bool LaunchWithoutMods { get; private set; }
        public bool ApplyLauncherUpdate { get; private set; }

        private static readonly Color ColBg = Color.FromArgb(18, 22, 31);
        private static readonly Color ColPanel = Color.FromArgb(24, 30, 43);
        private static readonly Color ColText = Color.FromArgb(240, 244, 250);
        private static readonly Color ColMuted = Color.FromArgb(168, 179, 198);
        private static readonly Color ColGold = Color.FromArgb(229, 154, 40);
        private static readonly Color ColGreen = Color.FromArgb(110, 231, 160);
        private static readonly Color ColButton = Color.FromArgb(34, 42, 58);
        private static readonly Color ColBorder = Color.FromArgb(60, 72, 94);

        public UpdateDialogForm(string gamePath, string gameVer, List<PendingModUpdate> updates, SelfUpdateState launcherUpdate)
        {
            this.gamePath = gamePath;
            this.launcherUpdate = launcherUpdate;
            ApplyLauncherUpdate = launcherUpdate != null;
            foreach (PendingModUpdate item in updates)
            {
                if (item.IsNew) newItems.Add(item);
                else updateItems.Add(item);
            }

            Text = "WoT Modpack | by Niedvin — Оновлення модів";
            StartPosition = FormStartPosition.CenterScreen;
            AutoScaleDimensions = new SizeF(96f, 96f);
            AutoScaleMode = AutoScaleMode.Dpi;
            ClientSize = new Size(1280, 960);
            MinimumSize = new Size(1100, 680);
            Rectangle screen = Screen.PrimaryScreen.WorkingArea;
            Size = new Size(Math.Max(MinimumSize.Width, Math.Min(Width, screen.Width - 48)),
                Math.Max(MinimumSize.Height, Math.Min(Height, screen.Height - 48)));
            BackColor = ColBg;
            ForeColor = ColText;
            Font = fontBase;
            DoubleBuffered = true;
            try
            {
                string ico = Path.Combine(gamePath, "game_metadata", "game.ico");
                if (File.Exists(ico)) Icon = new Icon(ico);
            }
            catch { }

            TableLayoutPanel root = MakeTable(1, 4);
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, 84));
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, launcherUpdate == null ? 0 : 66));
            root.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, 116));
            Controls.Add(root);

            TableLayoutPanel header = MakeTable(2, 1);
            header.Padding = new Padding(24, 12, 24, 12);
            header.BackColor = ColPanel;
            header.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 290));
            header.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
            Label title = MakeLabel("Оновлення модів", fontTitle, ColText);
            Label location = MakeLabel("Папка гри: " + gamePath + "\nВерсія гри: " + gameVer, fontBase, ColMuted);
            location.TextAlign = ContentAlignment.MiddleRight;
            toolTip.SetToolTip(location, gamePath);
            header.Controls.Add(title, 0, 0);
            header.Controls.Add(location, 1, 0);
            root.Controls.Add(header, 0, 0);

            TableLayoutPanel launcherPanel = MakeTable(2, 1);
            launcherPanel.Padding = new Padding(24, 8, 24, 8);
            launcherPanel.BackColor = ColPanel;
            launcherPanel.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 200));
            launcherPanel.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
            chkLauncher = new CheckBox();
            chkLauncher.Text = "Оновити лаунчер";
            chkLauncher.Checked = launcherUpdate != null;
            chkLauncher.Dock = DockStyle.Fill;
            chkLauncher.ForeColor = ColText;
            chkLauncher.CheckedChanged += (sender, e) => UpdateState();
            Label launcherInfo = MakeLabel(launcherUpdate == null ? "" : string.Format(
                "{0} → {1}\nЗавантажиться після запуску гри та застосується при наступному старті.",
                Program.LauncherVersion, launcherUpdate.version), fontBase, ColMuted);
            launcherPanel.Controls.Add(chkLauncher, 0, 0);
            launcherPanel.Controls.Add(launcherInfo, 1, 0);
            launcherPanel.Visible = launcherUpdate != null;
            root.Controls.Add(launcherPanel, 0, 1);

            TableLayoutPanel workspace = MakeTable(2, 1);
            workspace.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 62));
            workspace.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 38));
            root.Controls.Add(workspace, 0, 2);

            TableLayoutPanel selection = MakeTable(1, 2);
            selection.Padding = new Padding(16, 14, 16, 0);
            selection.RowStyles.Add(new RowStyle(SizeType.Absolute, 52));
            selection.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
            FlowLayoutPanel toolbar = new FlowLayoutPanel();
            toolbar.Dock = DockStyle.Fill;
            toolbar.WrapContents = false;
            btnSelectAll = CreateButton("Вибрати всі", 130, false);
            btnSelectNone = CreateButton("Зняти всі", 130, false);
            btnSelectAll.Click += (sender, e) => SetAllChecked(true);
            btnSelectNone.Click += (sender, e) => SetAllChecked(false);
            toolbar.Controls.Add(btnSelectAll);
            toolbar.Controls.Add(btnSelectNone);
            selection.Controls.Add(toolbar, 0, 0);

            modScroll = new Panel();
            modScroll.Dock = DockStyle.Fill;
            modScroll.AutoScroll = true;
            modScroll.Name = "ModSelection";
            modStack = MakeTable(1, 0);
            modStack.Dock = DockStyle.Top;
            modStack.AutoSize = true;
            modStack.AutoSizeMode = AutoSizeMode.GrowAndShrink;
            modStack.GrowStyle = TableLayoutPanelGrowStyle.AddRows;
            modStack.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
            modScroll.Controls.Add(modStack);
            selection.Controls.Add(modScroll, 0, 1);
            workspace.Controls.Add(selection, 0, 0);
            lblUpdatesHeader = MakeLabel("", fontHeader, ColText);
            lblNewHeader = MakeLabel("", fontHeader, ColText);
            lblEmpty = MakeLabel("Усі моди оновлені", fontBase, ColMuted);

            Panel details = new Panel();
            details.Dock = DockStyle.Fill;
            details.Padding = new Padding(25, 20, 24, 16);
            details.Paint += (sender, e) =>
            {
                using (Pen border = new Pen(ColBorder))
                    e.Graphics.DrawLine(border, 0, 0, 0, details.Height);
            };
            TableLayoutPanel detailLayout = MakeTable(1, 3);
            detailLayout.RowStyles.Add(new RowStyle(SizeType.Absolute, 46));
            detailLayout.RowStyles.Add(new RowStyle(SizeType.Absolute, 38));
            detailLayout.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
            lblDetailsTitle = MakeLabel("Оберіть мод", fontTitle, ColText);
            lblDetailsTitle.Name = "ModTitle";
            lblDetailsMeta = MakeLabel("", fontBase, ColGreen);
            detailLayout.Controls.Add(lblDetailsTitle, 0, 0);
            detailLayout.Controls.Add(lblDetailsMeta, 0, 1);
            reading = new Panel();
            reading.Dock = DockStyle.Fill;
            reading.AutoScroll = true;
            TableLayoutPanel paragraphs = MakeTable(1, 0);
            paragraphs.Dock = DockStyle.Top;
            paragraphs.AutoSize = true;
            paragraphs.AutoSizeMode = AutoSizeMode.GrowAndShrink;
            paragraphs.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
            Label changesHeading = MakeParagraph("Що зміниться", fontHeader, ColText, 18);
            lblChanges = MakeParagraph("", fontReading, ColText, 8);
            lblChanges.Name = "ModChanges";
            Label descriptionHeading = MakeParagraph("Для чого цей мод", fontHeader, ColText, 26);
            lblDescription = MakeParagraph("Оберіть мод зі списку, щоб прочитати опис і зміни.", fontReading, ColText, 8);
            lblDescription.Name = "ModDescription";
            lblWarning = MakeParagraph("", fontBase, Color.FromArgb(240, 170, 170), 24);
            foreach (Label label in new[] { changesHeading, lblChanges, descriptionHeading, lblDescription, lblWarning })
                paragraphs.Controls.Add(label);
            reading.Controls.Add(paragraphs);
            reading.SizeChanged += (sender, e) =>
            {
                int width = Math.Max(100, reading.ClientSize.Width - SystemInformation.VerticalScrollBarWidth - 8);
                foreach (Control label in paragraphs.Controls)
                    label.MaximumSize = new Size(width, 0);
            };
            detailLayout.Controls.Add(reading, 0, 2);
            details.Controls.Add(detailLayout);
            workspace.Controls.Add(details, 1, 0);

            footer = MakeTable(1, 3);
            footer.Padding = new Padding(24, 6, 24, 12);
            footer.BackColor = ColPanel;
            footer.RowStyles.Add(new RowStyle(SizeType.Absolute, 28));
            footer.RowStyles.Add(new RowStyle(SizeType.Absolute, 0));
            footer.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
            lblStatus = MakeLabel("", fontBase, ColMuted);
            progress = new ProgressBar();
            progress.Dock = DockStyle.Fill;
            progress.Visible = false;
            progress.Margin = new Padding(0, 2, 0, 4);
            TableLayoutPanel actions = MakeTable(2, 1);
            actions.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
            actions.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
            FlowLayoutPanel buttons = new FlowLayoutPanel();
            buttons.AutoSize = true;
            buttons.Dock = DockStyle.Fill;
            buttons.FlowDirection = FlowDirection.LeftToRight;
            buttons.WrapContents = false;
            btnUpdate = CreateButton("Оновити й грати", 220, true);
            btnSkip = CreateButton("Без оновлення", 180, false);
            btnOther = CreateButton("Інші дії", 140, false);
            otherMenu = new ContextMenuStrip();
            otherMenu.Items.Add("Запустити без модів", null, (sender, e) => OnNoMods());
            btnOther.Click += (sender, e) => otherMenu.Show(btnOther, new Point(0, -otherMenu.PreferredSize.Height));
            btnUpdate.Click += (sender, e) => OnPrimary();
            btnSkip.Click += (sender, e) => OnSkip();
            buttons.Controls.Add(btnOther);
            buttons.Controls.Add(btnSkip);
            buttons.Controls.Add(btnUpdate);
            Label backup = MakeLabel("Бекап перед заміною модів увімкнено", fontBase, ColMuted);
            actions.Controls.Add(backup, 0, 0);
            actions.Controls.Add(buttons, 1, 0);
            footer.Controls.Add(lblStatus, 0, 0);
            footer.Controls.Add(progress, 0, 1);
            footer.Controls.Add(actions, 0, 2);
            root.Controls.Add(footer, 0, 3);
            AcceptButton = btnUpdate;
            CancelButton = btnSkip;
            LoadItems();
        }

        private static TableLayoutPanel MakeTable(int columns, int rowCount)
        {
            TableLayoutPanel table = new TableLayoutPanel();
            table.ColumnCount = columns;
            table.RowCount = rowCount;
            table.Dock = DockStyle.Fill;
            table.Margin = Padding.Empty;
            table.Padding = Padding.Empty;
            return table;
        }

        private static Label MakeLabel(string text, Font font, Color color)
        {
            Label label = new Label();
            label.Text = text;
            label.Font = font;
            label.ForeColor = color;
            label.Dock = DockStyle.Fill;
            label.Margin = Padding.Empty;
            label.AutoEllipsis = true;
            label.TextAlign = ContentAlignment.MiddleLeft;
            return label;
        }

        private static Label MakeParagraph(string text, Font font, Color color, int top)
        {
            Label label = MakeLabel(text, font, color);
            label.AutoSize = true;
            label.AutoEllipsis = false;
            label.Dock = DockStyle.None;
            label.Anchor = AnchorStyles.Top | AnchorStyles.Left | AnchorStyles.Right;
            label.Margin = new Padding(0, top, 0, 0);
            label.UseCompatibleTextRendering = true;
            return label;
        }

        private Button CreateButton(string text, int width, bool primary)
        {
            Button button = new Button();
            button.Text = text;
            button.Width = width;
            button.Height = 42;
            button.Margin = new Padding(0, 4, 10, 4);
            button.FlatStyle = FlatStyle.Flat;
            button.UseVisualStyleBackColor = false;
            button.Font = fontButton;
            button.BackColor = primary ? ColGold : ColButton;
            button.ForeColor = primary ? ColBg : ColText;
            button.FlatAppearance.BorderSize = primary ? 0 : 1;
            button.FlatAppearance.BorderColor = ColBorder;
            button.FlatAppearance.MouseOverBackColor = primary ? Color.FromArgb(246, 174, 58) : Color.FromArgb(46, 56, 75);
            return button;
        }

        // Lucide icons, ISC license: docs/licenses/lucide.txt; embedded for single-file csc builds — 2026-11-12
        private static Image LoadIcon(string encoded)
        {
            using (MemoryStream stream = new MemoryStream(Convert.FromBase64String(encoded)))
            using (Image source = Image.FromStream(stream))
                return new Bitmap(source);
        }

        private void LoadItems()
        {
            isLoading = true;
            foreach (PendingModUpdate item in updateItems) AddRow(item, true);
            foreach (PendingModUpdate item in newItems) AddRow(item, false);
            isLoading = false;
            RebuildList();
            if (updateItems.Count > 0) SelectItem(updateItems[0]);
            else if (newItems.Count > 0) SelectItem(newItems[0]);
            else SelectItem(null);
            UpdateState();
        }

        private void AddRow(PendingModUpdate item, bool isChecked)
        {
            ModUpdateRow row = new ModUpdateRow(item, isChecked, fontHeader, fontBase, declineIcon, checkedIcon, uncheckedIcon, toolTip);
            row.CheckChanged += (sender, e) => { if (!isLoading) UpdateState(); };
            row.ItemSelected += (sender, e) => SelectItem(item);
            row.Declined += (sender, e) => OnDecline(item);
            rows.Add(item, row);
        }

        private void AddStackControl(Control control, int height)
        {
            int index = modStack.RowCount++;
            modStack.RowStyles.Add(new RowStyle(SizeType.Absolute, height));
            control.Dock = DockStyle.Fill;
            control.Margin = Padding.Empty;
            modStack.Controls.Add(control, 0, index);
        }

        private void RebuildList()
        {
            modStack.SuspendLayout();
            modStack.Controls.Clear();
            modStack.RowStyles.Clear();
            modStack.RowCount = 0;
            if (updateItems.Count > 0)
            {
                AddStackControl(lblUpdatesHeader, 46);
                foreach (PendingModUpdate item in updateItems) AddStackControl(rows[item], 90);
            }
            if (newItems.Count > 0)
            {
                AddStackControl(lblNewHeader, 52);
                foreach (PendingModUpdate item in newItems) AddStackControl(rows[item], 90);
            }
            if (rows.Count == 0) AddStackControl(lblEmpty, 80);
            modStack.ResumeLayout(true);
        }

        private void SelectItem(PendingModUpdate item)
        {
            selectedItem = item;
            reading.AutoScrollPosition = Point.Empty;
            reading.Visible = item != null;
            foreach (KeyValuePair<PendingModUpdate, ModUpdateRow> entry in rows)
                entry.Value.SetSelected(entry.Key == item);
            if (item == null)
            {
                lblDetailsTitle.Text = "Усі моди оновлені";
                lblDetailsMeta.Text = "";
                lblChanges.Text = "Немає вибраного мода.";
                lblDescription.Text = "";
                lblWarning.Visible = false;
                return;
            }
            ManifestModEntry remote = item.Remote;
            lblDetailsTitle.Text = remote.title ?? remote.id;
            toolTip.SetToolTip(lblDetailsTitle, lblDetailsTitle.Text);
            lblDetailsMeta.Text = (string.IsNullOrWhiteSpace(remote.author) ? "" : remote.author + " · ")
                + (item.IsNew ? "Новий мод · " + remote.version : (item.InstalledVersion ?? "?") + " → " + remote.version);
            lblChanges.Text = string.IsNullOrWhiteSpace(remote.changes) ? "Зміни не вказані в маніфесті." : remote.changes;
            lblDescription.Text = string.IsNullOrWhiteSpace(remote.description) ? "Опис мода відсутній у цьому маніфесті." : remote.description;
            lblWarning.Visible = remote.possible_cheat;
            lblWarning.Text = string.IsNullOrWhiteSpace(remote.possible_cheat_note)
                ? "Може визначатися як чіт. Використовуйте на власний ризик." : remote.possible_cheat_note;
        }

        private List<PendingModUpdate> GetChecked()
        {
            List<PendingModUpdate> result = new List<PendingModUpdate>();
            foreach (PendingModUpdate item in updateItems)
                if (rows[item].IsChecked) result.Add(item);
            foreach (PendingModUpdate item in newItems)
                if (rows[item].IsChecked) result.Add(item);
            return result;
        }

        private void SetAllChecked(bool value)
        {
            if (isUpdating) return;
            isLoading = true;
            foreach (ModUpdateRow row in rows.Values) row.IsChecked = value;
            isLoading = false;
            UpdateState();
        }

        private void UpdateState()
        {
            if (isUpdating || lblStatus == null) return;
            int checkedCount = GetChecked().Count;
            lblUpdatesHeader.Text = "Оновлення · " + updateItems.Count;
            lblNewHeader.Text = "Нові моди · " + newItems.Count;
            lblStatus.Text = rows.Count == 0 ? "Усі моди оновлені" : string.Format("Вибрано: {0} із {1}", checkedCount, rows.Count);
            bool launcherChecked = launcherUpdate != null && chkLauncher.Checked;
            btnUpdate.Text = checkedCount > 0 ? "Оновити й грати" : launcherChecked ? "Оновити лаунчер й грати" : "Грати";
            btnSkip.Visible = rows.Count > 0 || launcherUpdate != null;
            btnSelectAll.Enabled = rows.Count > 0;
            btnSelectNone.Enabled = rows.Count > 0;
        }

        private void OnPrimary()
        {
            if (isUpdating) return;
            List<PendingModUpdate> selected = GetChecked();
            if (selected.Count > 0) StartUpdateProcess(selected);
            else Close();
        }

        private void OnSkip()
        {
            if (isUpdating) return;
            chkLauncher.Checked = false;
            Close();
        }

        private void OnNoMods()
        {
            if (isUpdating) return;
            LaunchWithoutMods = true;
            Close();
        }

        private void OnDecline(PendingModUpdate item)
        {
            if (isUpdating || !rows.ContainsKey(item)) return;
            if (!ConfirmDecline(item)) return;
            if (!Program.AddDeclinedMods(new List<string> { item.Remote.id }))
            {
                MessageBox.Show(this, "Не вдалося зберегти вибір. Мод залишився у списку.", "WoT Modpack",
                    MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }
            RemoveItem(item);
        }

        protected virtual bool ConfirmDecline(PendingModUpdate item)
        {
            return MessageBox.Show(this,
                "Більше не пропонувати «" + (item.Remote.title ?? item.Remote.id)
                + "»?\nМод більше не встановлюватиметься й не оновлюватиметься. Встановлені файли залишаться у грі.",
                "WoT Modpack", MessageBoxButtons.YesNo, MessageBoxIcon.Question, MessageBoxDefaultButton.Button2) == DialogResult.Yes;
        }

        protected virtual void ShowUpdateFailure(string reason)
        {
            MessageBox.Show(this, "Оновлення не вдалося (" + reason
                + ").\nВідновлено попередні версії модів, запускаємо гру.",
                "WoT Modpack Launcher", MessageBoxButtons.OK, MessageBoxIcon.Warning);
        }

        private void RemoveItem(PendingModUpdate item)
        {
            ModUpdateRow row = rows[item];
            updateItems.Remove(item);
            newItems.Remove(item);
            rows.Remove(item);
            RebuildList();
            row.Dispose();
            if (selectedItem == item)
                SelectItem(updateItems.Count > 0 ? updateItems[0] : newItems.Count > 0 ? newItems[0] : null);
            UpdateState();
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
        }

        private void StartUpdateProcess(List<PendingModUpdate> selected)
        {
            if (isUpdating) return;
            isUpdating = true;
            btnUpdate.Enabled = false;
            btnSkip.Enabled = false;
            btnOther.Enabled = false;
            btnSelectAll.Enabled = false;
            btnSelectNone.Enabled = false;
            foreach (ModUpdateRow row in rows.Values) row.Enabled = false;
            chkLauncher.Enabled = false;
            ControlBox = false;
            progress.Value = 0;
            progress.Visible = true;
            footer.RowStyles[1].Height = 18;
            lblStatus.Text = "Підготовка резервної копії...";
            Thread worker = new Thread(() => RunUpdateWorker(selected));
            worker.IsBackground = true;
            worker.Start();
        }

        private sealed class ModUpdateRow : UserControl
        {
            private bool isSelected;
            private readonly CheckBox check;
            private readonly TableLayoutPanel layout;
            private readonly TableLayoutPanel text;
            public event EventHandler CheckChanged;
            public event EventHandler ItemSelected;
            public event EventHandler Declined;

            public bool IsChecked
            {
                get { return check.Checked; }
                set { check.Checked = value; }
            }

            public ModUpdateRow(PendingModUpdate item, bool isChecked, Font titleFont, Font bodyFont, Image icon, Image checkedIcon, Image uncheckedIcon, ToolTip toolTip)
            {
                DoubleBuffered = true;
                BackColor = ColBg;
                AccessibleName = item.Remote.title ?? item.Remote.id;
                Padding = new Padding(4, 0, 4, 1);
                layout = MakeTable(3, 1);
                layout.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 40));
                layout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
                layout.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 42));
                check = new CheckBox();
                check.Checked = isChecked;
                check.Size = new Size(36, 36);
                check.Anchor = AnchorStyles.None;
                check.Appearance = Appearance.Button;
                check.AccessibleRole = AccessibleRole.CheckButton;
                check.FlatStyle = FlatStyle.Flat;
                check.FlatAppearance.BorderSize = 0;
                check.FlatAppearance.CheckedBackColor = ColPanel;
                check.Image = isChecked ? checkedIcon : uncheckedIcon;
                check.ForeColor = ColGold;
                check.AccessibleName = "Оновити «" + AccessibleName + "»";
                check.CheckedChanged += (sender, e) => { check.Image = check.Checked ? checkedIcon : uncheckedIcon; if (CheckChanged != null) CheckChanged(this, EventArgs.Empty); };
                text = MakeTable(2, 2);
                text.Padding = new Padding(6, 17, 10, 15);
                text.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
                text.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
                text.RowStyles.Add(new RowStyle(SizeType.Percent, 52));
                text.RowStyles.Add(new RowStyle(SizeType.Percent, 48));
                Label title = MakeLabel((item.Remote.possible_cheat ? "[!] " : "") + AccessibleName, titleFont, ColText);
                Label version = MakeLabel(item.IsNew ? item.Remote.version : (item.InstalledVersion ?? "?") + " → " + item.Remote.version, bodyFont, ColGreen);
                version.AutoSize = true;
                version.TextAlign = ContentAlignment.MiddleRight;
                version.Margin = new Padding(8, 0, 0, 0);
                string purpose = string.IsNullOrWhiteSpace(item.Remote.summary) ? item.Remote.description : item.Remote.summary;
                Label summary = MakeLabel(string.IsNullOrWhiteSpace(purpose)
                    ? "Опис мода відсутній у цьому маніфесті." : purpose, bodyFont, ColMuted);
                text.Controls.Add(title, 0, 0);
                text.Controls.Add(version, 1, 0);
                text.Controls.Add(summary, 0, 1);
                text.SetColumnSpan(summary, 2);
                Button decline = new Button();
                decline.Name = "DeclineMod";
                decline.Size = new Size(36, 36);
                decline.Anchor = AnchorStyles.None;
                decline.FlatStyle = FlatStyle.Flat;
                decline.FlatAppearance.BorderSize = 0;
                decline.FlatAppearance.MouseOverBackColor = Color.FromArgb(70, 49, 53);
                decline.Image = icon;
                decline.AccessibleName = "Більше не пропонувати «" + AccessibleName + "»";
                toolTip.SetToolTip(decline, "Більше не пропонувати цей мод");
                toolTip.SetToolTip(title, AccessibleName);
                toolTip.SetToolTip(version, version.Text);
                toolTip.SetToolTip(summary, summary.Text);
                decline.Click += (sender, e) => { if (Declined != null) Declined(this, EventArgs.Empty); };
                foreach (Control control in new Control[] { this, layout, text, title, version, summary })
                {
                    control.Click += (sender, e) => { if (ItemSelected != null) ItemSelected(this, EventArgs.Empty); };
                }
                check.Enter += (sender, e) => { if (ItemSelected != null) ItemSelected(this, EventArgs.Empty); };
                layout.Controls.Add(check, 0, 0);
                layout.Controls.Add(text, 1, 0);
                layout.Controls.Add(decline, 2, 0);
                Controls.Add(layout);
            }

            public void SetSelected(bool selected)
            {
                isSelected = selected;
                BackColor = selected ? Color.FromArgb(55, 45, 28) : ColBg;
                layout.BackColor = BackColor;
                text.BackColor = layout.BackColor;
                Invalidate();
            }

            protected override void OnPaint(PaintEventArgs e)
            {
                base.OnPaint(e);
                if (isSelected)
                    using (SolidBrush accent = new SolidBrush(ColGold))
                        e.Graphics.FillRectangle(accent, 0, 0, 4, Height - 1);
                using (Pen border = new Pen(ColBorder))
                    e.Graphics.DrawLine(border, 4, Height - 1, Width - 4, Height - 1);
            }
        }

        private void RunUpdateWorker(List<PendingModUpdate> selected)
        {
            string stamp = DateTime.Now.ToString("yyyyMMdd_HHmmss");
            string bkpDir = Path.Combine(gamePath, ".backups", "launcher", stamp);
            var tempFiles = new List<string>();
            var replacedPairs = new List<string[]>();
            bool backupReady = false;
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

                SetProgress(100);
                SetStatus("Усі вибрані моди оновлено. Запускаємо гру...");
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
                        ShowUpdateFailure(actual.Message);
                        Close();
                    }));
                }
                catch { }
            }
            finally
            {
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
            base.Dispose(disposing);
            if (disposing)
            {
                lblUpdatesHeader.Dispose();
                lblNewHeader.Dispose();
                lblEmpty.Dispose();
                toolTip.Dispose();
                otherMenu.Dispose();
                declineIcon.Dispose();
                checkedIcon.Dispose();
                uncheckedIcon.Dispose();
                fontBase.Dispose();
                fontTitle.Dispose();
                fontHeader.Dispose();
                fontButton.Dispose();
                fontReading.Dispose();
            }
        }
    }
}
