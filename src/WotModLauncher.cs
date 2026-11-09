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
using System.Runtime.InteropServices;
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
[assembly: AssemblyFileVersion("1.4.2.0")]
[assembly: AssemblyVersion("1.4.2.0")]

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

        public static void AddDeclinedMods(List<string> ids)
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
                File.WriteAllText(DeclinedModsPath, serializer.Serialize(current), new UTF8Encoding(false));
            }
            catch
            {
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
            if (cfg == null || string.IsNullOrEmpty(cfg.game_path) || !Directory.Exists(cfg.game_path))
            {
                if (!checkOnly && !updateOnly && !string.IsNullOrEmpty(argGamePath))
                    LaunchGame(argGamePath);
                return 1;
            }

            if (string.IsNullOrEmpty(ManifestOverride) && !string.IsNullOrEmpty(cfg.manifest_url))
                ManifestOverride = cfg.manifest_url;

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
            ManifestRoot manifest = FetchManifestWithTimeout(4000);
            if (manifest != null)
            {
                selfUpdatePlan = GetSelfUpdatePlan(manifest.launcher);
                if (string.IsNullOrEmpty(activeVer)) activeVer = manifest.game_version;
                List<PendingModUpdate> updates = FindPendingUpdates(cfg.game_path, activeVer, manifest, cfg.skip_mods, declinedMods);
                foreach (PendingModUpdate update in updates)
                {
                }
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
            else
            {
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
                HttpWebRequest req = (HttpWebRequest)WebRequest.Create(target + "?t=" + Environment.TickCount);
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

        private static SelfUpdateState GetSelfUpdatePlan(ManifestLauncherInfo info)
        {
            if (info == null || string.IsNullOrEmpty(info.version) || string.IsNullOrEmpty(info.url))
                return null;

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

                    if (!string.IsNullOrEmpty(state.sha256) && !VerifySha256(tmp, state.sha256))
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
                if (state != null && !string.IsNullOrEmpty(state.sha256) && !VerifySha256(newPath, state.sha256))
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

        private static string AddCacheBuster(string url)
        {
            if (string.IsNullOrEmpty(url) || url.IndexOf('?') >= 0) return url;
            return url + "?t=" + Environment.TickCount;
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

        private static void TryDeleteFile(string path)
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

            string verRoot = Path.Combine(gamePath, "mods", gameVer);
            Directory.CreateDirectory(verRoot);

            foreach (ManifestModEntry entry in manifest.mods)
            {
                if (entry == null || string.IsNullOrEmpty(entry.id) || string.IsNullOrEmpty(entry.version) || string.IsNullOrEmpty(entry.file))
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
                        foreach (string f in Directory.GetFiles(searchDir, "*.wotmod", SearchOption.TopDirectoryOnly))
                        {
                            if (!string.Equals(ReadWotmodId(f), entry.id, StringComparison.OrdinalIgnoreCase))
                                continue;
                            Match mv = Regex.Match(Path.GetFileName(f), @"_([0-9]+(?:\.[0-9]+)*)\.wotmod$", RegexOptions.IgnoreCase);
                            if (!mv.Success) continue;
                            Version v = ParseVer(mv.Groups[1].Value);
                            if (v != null && (foundVer == null || v > foundVer))
                            {
                                foundVer = v;
                                foundFile = f;
                            }
                        }
                    }
                }

                if (foundFile == null)
                {
                    // Without an explicit installer selection, only default-checked mods are auto-added
                    if (skipMods == null && entry.default_checked == false)
                        continue;
                    // Mods present on GitHub but missing locally are installed on the next launch
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
        private readonly string gameVer;
        private readonly SelfUpdateState launcherUpdate;
        private readonly List<PendingModUpdate> updateItems = new List<PendingModUpdate>();
        private readonly List<PendingModUpdate> newItems = new List<PendingModUpdate>();

        private readonly Label lblTitle;
        private readonly Label lblSubtitle;
        private readonly CheckBox chkLauncher;
        private readonly Label lblLauncher;
        private readonly Label lblUpdatesHeader;
        private readonly Label lblNewHeader;
        private readonly ListView listUpdates;
        private readonly ListView listNew;
        private readonly Label lblUpdatesEmpty;
        private readonly Label lblNewEmpty;
        private readonly Button btnUpdate;
        private readonly Button btnSkip;
        private readonly Button btnNoMods;
        private readonly Button btnDecline;
        private readonly Button btnSelectAll;
        private readonly Button btnSelectNone;
        private readonly ProgressBar progress;
        private readonly Label lblStatus;

        private readonly Font fontBase = new Font("Segoe UI", 9f);
        private readonly Font fontTitle = new Font("Segoe UI", 14f, FontStyle.Bold);
        private readonly Font fontHeader = new Font("Segoe UI", 9f, FontStyle.Bold);
        private readonly Font fontButton = new Font("Segoe UI", 9.5f, FontStyle.Bold);

        private bool isLoading;
        private bool isUpdating;

        public bool LaunchWithoutMods { get; private set; }
        public bool ApplyLauncherUpdate { get; private set; }

        private static readonly Color ColBg = Color.FromArgb(18, 22, 31);
        private static readonly Color ColPanel = Color.FromArgb(24, 30, 43);
        private static readonly Color ColRow = Color.FromArgb(28, 36, 50);
        private static readonly Color ColList = Color.FromArgb(22, 28, 40);
        private static readonly Color ColText = Color.FromArgb(240, 244, 250);
        private static readonly Color ColMuted = Color.FromArgb(148, 160, 180);
        private static readonly Color ColGold = Color.FromArgb(229, 154, 40);
        private static readonly Color ColGreen = Color.FromArgb(110, 231, 160);
        private static readonly Color ColButton = Color.FromArgb(34, 42, 58);
        private static readonly Color ColButtonBorder = Color.FromArgb(60, 72, 94);

        public UpdateDialogForm(string gamePath, string gameVer, List<PendingModUpdate> updates, SelfUpdateState launcherUpdate)
        {
            this.gamePath = gamePath;
            this.gameVer = gameVer;
            this.launcherUpdate = launcherUpdate;
            this.ApplyLauncherUpdate = launcherUpdate != null;

            foreach (PendingModUpdate item in updates)
            {
                if (item.IsNew) newItems.Add(item);
                else updateItems.Add(item);
            }

            Text = "WoT Modpack — Оновлення модів";
            StartPosition = FormStartPosition.CenterScreen;
            Size = new Size(1020, 720);
            MinimumSize = new Size(820, 600);
            BackColor = ColBg;
            ForeColor = ColText;
            Font = fontBase;
            AutoScaleMode = AutoScaleMode.None;
            FormBorderStyle = FormBorderStyle.Sizable;
            MaximizeBox = true;
            MinimizeBox = false;
            TopMost = true;
            DoubleBuffered = true;

            try
            {
                string ico = Path.Combine(gamePath, "game_metadata", "game.ico");
                if (File.Exists(ico)) Icon = new Icon(ico);
            }
            catch { }

            TableLayoutPanel root = new TableLayoutPanel();
            root.Dock = DockStyle.Fill;
            root.ColumnCount = 1;
            root.RowCount = 4;
            root.BackColor = ColBg;
            root.Margin = new Padding(0);
            root.Padding = new Padding(0);
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, 74));
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, 62));
            root.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, 136));
            Controls.Add(root);

            Panel header = new Panel();
            header.Dock = DockStyle.Fill;
            header.BackColor = ColPanel;
            header.Margin = new Padding(0);
            TableLayoutPanel headerLayout = new TableLayoutPanel();
            headerLayout.Dock = DockStyle.Fill;
            headerLayout.ColumnCount = 1;
            headerLayout.RowCount = 2;
            headerLayout.Padding = new Padding(20, 8, 20, 6);
            headerLayout.RowStyles.Add(new RowStyle(SizeType.Absolute, 36));
            headerLayout.RowStyles.Add(new RowStyle(SizeType.Absolute, 24));
            lblTitle = new Label();
            lblTitle.Text = "ДОСТУПНІ ОНОВЛЕННЯ МОДІВ";
            lblTitle.Font = fontTitle;
            lblTitle.ForeColor = ColText;
            lblTitle.Dock = DockStyle.Fill;
            lblTitle.TextAlign = ContentAlignment.MiddleLeft;
            lblSubtitle = new Label();
            lblSubtitle.Font = fontBase;
            lblSubtitle.ForeColor = ColGold;
            lblSubtitle.Dock = DockStyle.Fill;
            lblSubtitle.TextAlign = ContentAlignment.MiddleLeft;
            headerLayout.Controls.Add(lblTitle, 0, 0);
            headerLayout.Controls.Add(lblSubtitle, 0, 1);
            header.Controls.Add(headerLayout);
            root.Controls.Add(header, 0, 0);

            Panel launcherPanel = new Panel();
            launcherPanel.Dock = DockStyle.Fill;
            launcherPanel.BackColor = ColRow;
            launcherPanel.Margin = new Padding(0);
            TableLayoutPanel launcherLayout = new TableLayoutPanel();
            launcherLayout.Dock = DockStyle.Fill;
            launcherLayout.ColumnCount = 2;
            launcherLayout.RowCount = 1;
            launcherLayout.Padding = new Padding(20, 8, 20, 8);
            launcherLayout.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
            launcherLayout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
            chkLauncher = new CheckBox();
            chkLauncher.AutoSize = true;
            chkLauncher.Text = "Оновити лаунчер";
            chkLauncher.ForeColor = ColText;
            chkLauncher.Checked = launcherUpdate != null;
            chkLauncher.Enabled = launcherUpdate != null;
            chkLauncher.Visible = launcherUpdate != null;
            chkLauncher.Anchor = AnchorStyles.Left;
            chkLauncher.CheckedChanged += (s, e) => UpdateState();
            lblLauncher = new Label();
            lblLauncher.Dock = DockStyle.Fill;
            lblLauncher.TextAlign = ContentAlignment.MiddleLeft;
            lblLauncher.ForeColor = ColMuted;
            if (launcherUpdate != null)
                lblLauncher.Text = string.Format("Лаунчер: {0} → {1} — завантажиться після запуску, застосується при наступному старті", Program.LauncherVersion, launcherUpdate.version);
            else
                lblLauncher.Text = "Лаунчер актуальний: " + Program.LauncherVersion;
            launcherLayout.Controls.Add(chkLauncher, 0, 0);
            launcherLayout.Controls.Add(lblLauncher, 1, 0);
            launcherPanel.Controls.Add(launcherLayout);
            root.Controls.Add(launcherPanel, 0, 1);

            lblUpdatesHeader = CreateHeaderLabel("ОНОВЛЕННЯ", ColGold);
            lblNewHeader = CreateHeaderLabel("НОВІ МОДИ", ColGreen);
            listUpdates = CreateList();
            listNew = CreateList();
            lblUpdatesEmpty = CreateEmptyLabel("Немає оновлень");
            lblNewEmpty = CreateEmptyLabel("Немає нових модів");

            TableLayoutPanel lists = new TableLayoutPanel();
            lists.Dock = DockStyle.Fill;
            lists.ColumnCount = 2;
            lists.RowCount = 1;
            lists.BackColor = ColBg;
            lists.Padding = new Padding(16, 10, 16, 6);
            lists.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 50));
            lists.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 50));
            lists.Controls.Add(CreateColumn(lblUpdatesHeader, listUpdates, lblUpdatesEmpty, new Padding(0, 0, 8, 0)), 0, 0);
            lists.Controls.Add(CreateColumn(lblNewHeader, listNew, lblNewEmpty, new Padding(8, 0, 0, 0)), 1, 0);
            root.Controls.Add(lists, 0, 2);

            Panel footer = new Panel();
            footer.Dock = DockStyle.Fill;
            footer.BackColor = ColBg;
            footer.Padding = new Padding(16, 4, 16, 10);
            TableLayoutPanel footerLayout = new TableLayoutPanel();
            footerLayout.Dock = DockStyle.Fill;
            footerLayout.ColumnCount = 1;
            footerLayout.RowCount = 3;
            footerLayout.RowStyles.Add(new RowStyle(SizeType.Absolute, 22));
            footerLayout.RowStyles.Add(new RowStyle(SizeType.Absolute, 16));
            footerLayout.RowStyles.Add(new RowStyle(SizeType.Percent, 100));

            lblStatus = new Label();
            lblStatus.Dock = DockStyle.Fill;
            lblStatus.TextAlign = ContentAlignment.MiddleLeft;
            lblStatus.ForeColor = ColMuted;
            progress = new ProgressBar();
            progress.Dock = DockStyle.Fill;
            progress.Minimum = 0;
            progress.Maximum = 100;
            progress.Value = 0;
            progress.Style = ProgressBarStyle.Continuous;

            FlowLayoutPanel buttons = new FlowLayoutPanel();
            buttons.Dock = DockStyle.Fill;
            buttons.FlowDirection = FlowDirection.LeftToRight;
            buttons.WrapContents = true;
            buttons.AutoScroll = false;
            buttons.Padding = new Padding(0);
            buttons.Margin = new Padding(0);

            btnUpdate = CreateButton("Грати", 220, true);
            btnSkip = CreateButton("Без оновлення", 150, false);
            btnNoMods = CreateButton("Без модів", 130, false);
            btnDecline = CreateButton("Більше не пропонувати", 180, false);
            btnSelectAll = CreateButton("Вибрати все", 120, false);
            btnSelectNone = CreateButton("Зняти все", 120, false);
            btnDecline.BackColor = Color.FromArgb(54, 36, 42);
            btnDecline.ForeColor = Color.FromArgb(240, 170, 170);
            btnDecline.FlatAppearance.BorderColor = Color.FromArgb(96, 62, 70);

            btnUpdate.Click += (s, e) => OnPrimary();
            btnSkip.Click += (s, e) => OnSkip();
            btnNoMods.Click += (s, e) => OnNoMods();
            btnDecline.Click += (s, e) => OnDecline();
            btnSelectAll.Click += (s, e) => SetAllChecked(true);
            btnSelectNone.Click += (s, e) => SetAllChecked(false);

            buttons.Controls.Add(btnUpdate);
            buttons.Controls.Add(btnSkip);
            buttons.Controls.Add(btnNoMods);
            buttons.Controls.Add(btnDecline);
            buttons.Controls.Add(btnSelectAll);
            buttons.Controls.Add(btnSelectNone);
            footerLayout.Controls.Add(lblStatus, 0, 0);
            footerLayout.Controls.Add(progress, 0, 1);
            footerLayout.Controls.Add(buttons, 0, 2);
            footer.Controls.Add(footerLayout);
            root.Controls.Add(footer, 0, 3);

            AcceptButton = btnUpdate;
            CancelButton = btnSkip;

            LoadItems();
        }

        private Label CreateHeaderLabel(string text, Color color)
        {
            Label label = new Label();
            label.Text = text;
            label.Dock = DockStyle.Fill;
            label.TextAlign = ContentAlignment.MiddleLeft;
            label.Font = fontHeader;
            label.ForeColor = color;
            return label;
        }

        private Label CreateEmptyLabel(string text)
        {
            Label label = new Label();
            label.Text = text;
            label.Dock = DockStyle.Fill;
            label.TextAlign = ContentAlignment.MiddleCenter;
            label.ForeColor = ColMuted;
            label.BackColor = ColList;
            label.Visible = false;
            return label;
        }

        private ListView CreateList()
        {
            ListView list = new ListView();
            list.Dock = DockStyle.Fill;
            list.View = View.Details;
            list.FullRowSelect = true;
            list.CheckBoxes = true;
            list.HideSelection = false;
            list.MultiSelect = false;
            list.BorderStyle = BorderStyle.FixedSingle;
            list.BackColor = ColList;
            list.ForeColor = ColText;
            list.Font = fontBase;
            list.HeaderStyle = ColumnHeaderStyle.Nonclickable;
            list.ShowItemToolTips = true;
            list.Columns.Add("Мод", 160);
            list.Columns.Add("Версія", 100);
            list.Columns.Add("Зміни", 160);
            list.Resize += (s, e) => FitColumns(list);
            list.ItemChecked += List_ItemChecked;
            return list;
        }

        private Control CreateColumn(Label header, ListView list, Label empty, Padding margin)
        {
            TableLayoutPanel col = new TableLayoutPanel();
            col.Dock = DockStyle.Fill;
            col.ColumnCount = 1;
            col.RowCount = 2;
            col.Margin = margin;
            col.BackColor = ColBg;
            col.RowStyles.Add(new RowStyle(SizeType.Absolute, 28));
            col.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
            Panel box = new Panel();
            box.Dock = DockStyle.Fill;
            box.BackColor = ColBg;
            box.Controls.Add(list);
            box.Controls.Add(empty);
            empty.BringToFront();
            col.Controls.Add(header, 0, 0);
            col.Controls.Add(box, 0, 1);
            return col;
        }

        private Button CreateButton(string text, int width, bool primary)
        {
            Button button = new Button();
            button.Text = text;
            button.Width = width;
            button.Height = 36;
            button.Margin = new Padding(0, 4, 8, 4);
            button.FlatStyle = FlatStyle.Flat;
            button.UseVisualStyleBackColor = false;
            button.Font = fontButton;
            if (primary)
            {
                button.BackColor = ColGold;
                button.ForeColor = Color.FromArgb(20, 24, 32);
                button.FlatAppearance.BorderSize = 0;
            }
            else
            {
                button.BackColor = ColButton;
                button.ForeColor = ColText;
                button.FlatAppearance.BorderSize = 1;
                button.FlatAppearance.BorderColor = ColButtonBorder;
            }
            return button;
        }

        private void LoadItems()
        {
            isLoading = true;
            foreach (PendingModUpdate item in updateItems)
            {
                ListViewItem row = new ListViewItem(item.Remote.title ?? item.Remote.id);
                row.SubItems.Add(string.Format("{0} → {1}", item.InstalledVersion ?? "?", item.Remote.version));
                row.SubItems.Add(item.Remote.changes ?? "Оновлення сумісності та покращення стабільності");
                row.ToolTipText = item.Remote.changes ?? "";
                row.Tag = item;
                row.Checked = true;
                listUpdates.Items.Add(row);
            }
            foreach (PendingModUpdate item in newItems)
            {
                ListViewItem row = new ListViewItem(item.Remote.title ?? item.Remote.id);
                row.SubItems.Add("новий • " + item.Remote.version);
                row.SubItems.Add(item.Remote.changes ?? "");
                row.ToolTipText = item.Remote.changes ?? "";
                row.Tag = item;
                row.Checked = false;
                listNew.Items.Add(row);
            }
            isLoading = false;
            RefreshEmptyStates();
            FitColumns(listUpdates);
            FitColumns(listNew);
            UpdateState();
        }

        private void RefreshEmptyStates()
        {
            listUpdates.Visible = updateItems.Count > 0;
            lblUpdatesEmpty.Visible = updateItems.Count == 0;
            listNew.Visible = newItems.Count > 0;
            lblNewEmpty.Visible = newItems.Count == 0;
            if (lblUpdatesEmpty.Visible) lblUpdatesEmpty.BringToFront();
            if (lblNewEmpty.Visible) lblNewEmpty.BringToFront();
        }

        private static void FitColumns(ListView list)
        {
            if (list.Columns.Count < 3) return;
            int width = list.ClientSize.Width - list.Columns[0].Width - list.Columns[1].Width - 24;
            if (width > 80) list.Columns[2].Width = width;
        }

        private void List_ItemChecked(object sender, ItemCheckedEventArgs e)
        {
            if (isLoading) return;
            UpdateState();
        }

        private List<PendingModUpdate> GetChecked()
        {
            List<PendingModUpdate> result = new List<PendingModUpdate>();
            foreach (ListViewItem row in listUpdates.CheckedItems)
            {
                PendingModUpdate item = row.Tag as PendingModUpdate;
                if (item != null) result.Add(item);
            }
            foreach (ListViewItem row in listNew.CheckedItems)
            {
                PendingModUpdate item = row.Tag as PendingModUpdate;
                if (item != null) result.Add(item);
            }
            return result;
        }

        private void SetAllChecked(bool value)
        {
            if (isUpdating) return;
            isLoading = true;
            foreach (ListViewItem row in listUpdates.Items) row.Checked = value;
            foreach (ListViewItem row in listNew.Items) row.Checked = value;
            isLoading = false;
            UpdateState();
        }

        private void UpdateState()
        {
            if (isUpdating || lblStatus == null) return;
            int total = updateItems.Count + newItems.Count;
            int checkedCount = GetChecked().Count;
            lblUpdatesHeader.Text = "ОНОВЛЕННЯ (" + updateItems.Count + ")";
            lblNewHeader.Text = "НОВІ МОДИ (" + newItems.Count + ")";
            if (total == 0)
                lblSubtitle.Text = "Оновлень модів немає • Клієнт WoT " + gameVer;
            else
                lblSubtitle.Text = string.Format("Оновлень: {0} • нових: {1} • Клієнт WoT {2}", updateItems.Count, newItems.Count, gameVer);
            lblStatus.Text = total == 0
                ? (launcherUpdate == null ? "Усі моди оновлені" : "Оновлень модів немає")
                : string.Format("Вибрано: {0} із {1}", checkedCount, total);
            bool launcherChecked = launcherUpdate != null && chkLauncher.Checked;
            if (checkedCount > 0) btnUpdate.Text = "Оновити вибране і грати";
            else if (launcherChecked) btnUpdate.Text = "Оновити лаунчер і грати";
            else btnUpdate.Text = "Грати";
            btnDecline.Enabled = checkedCount > 0;
            btnSkip.Visible = total > 0;
            btnDecline.Visible = total > 0;
            btnSelectAll.Enabled = total > 0;
            btnSelectNone.Enabled = total > 0;
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

        private void OnDecline()
        {
            if (isUpdating) return;
            List<PendingModUpdate> selected = GetChecked();
            if (selected.Count == 0)
            {
                MessageBox.Show("Познач моди, які більше не пропонувати.", "WoT Modpack",
                    MessageBoxButtons.OK, MessageBoxIcon.Information);
                return;
            }
            DialogResult answer = MessageBox.Show(
                string.Format("Більше не пропонувати {0} мод(ів)?\nВони не будуть встановлюватися, оновлюватися чи пропонуватися.", selected.Count),
                "WoT Modpack", MessageBoxButtons.YesNo, MessageBoxIcon.Question);
            if (answer != DialogResult.Yes) return;

            List<string> ids = new List<string>();
            foreach (PendingModUpdate item in selected) ids.Add(item.Remote.id);
            Program.AddDeclinedMods(ids);
            isLoading = true;
            foreach (PendingModUpdate item in selected)
            {
                RemoveRow(listUpdates, item);
                RemoveRow(listNew, item);
                updateItems.Remove(item);
                newItems.Remove(item);
            }
            isLoading = false;
            RefreshEmptyStates();
            UpdateState();
        }

        private static void RemoveRow(ListView list, PendingModUpdate target)
        {
            for (int i = list.Items.Count - 1; i >= 0; i--)
            {
                PendingModUpdate item = list.Items[i].Tag as PendingModUpdate;
                if (item == target)
                {
                    list.Items.RemoveAt(i);
                    return;
                }
            }
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
            btnNoMods.Enabled = false;
            btnDecline.Enabled = false;
            btnSelectAll.Enabled = false;
            btnSelectNone.Enabled = false;
            listUpdates.Enabled = false;
            listNew.Enabled = false;
            ControlBox = false;
            progress.Value = 0;
            lblStatus.Text = "Підготовка резервної копії...";
            Thread worker = new Thread(() => RunUpdateWorker(selected));
            worker.IsBackground = true;
            worker.Start();
        }

        private void RunUpdateWorker(List<PendingModUpdate> selected)
        {
            string stamp = DateTime.Now.ToString("yyyyMMdd_HHmmss");
            string bkpDir = Path.Combine(gamePath, ".backups", "launcher", stamp);
            List<string[]> replacedPairs = new List<string[]>();

            try
            {
                Directory.CreateDirectory(bkpDir);
                int total = selected.Count;
                for (int i = 0; i < total; i++)
                {
                    PendingModUpdate update = selected[i];
                    ManifestModEntry remote = update.Remote;
                    SetStatus(string.Format("Завантаження ({0}/{1}): {2} v{3}...", i + 1, total, remote.title ?? remote.id, remote.version));

                    string tmpFile = Path.Combine(Path.GetTempPath(), "wot-upd-" + Guid.NewGuid().ToString("N") + ".wotmod");
                    DownloadFileWithProgress(remote.url, tmpFile, i, total);

                    if (remote.size > 0 && new FileInfo(tmpFile).Length != remote.size)
                    {
                        File.Delete(tmpFile);
                        throw new InvalidDataException("Розмір файлу не збігається для " + remote.file);
                    }
                    if (!string.IsNullOrEmpty(remote.sha256) && !Program.VerifySha256(tmpFile, remote.sha256))
                    {
                        File.Delete(tmpFile);
                        throw new InvalidDataException("Контрольна сума SHA-256 не збігається для " + remote.file);
                    }
                    if (!Program.VerifyWotmodArchive(tmpFile, remote.id))
                    {
                        File.Delete(tmpFile);
                        throw new InvalidDataException("Пакет .wotmod пошкоджений або має інший ID: " + remote.file);
                    }

                    string destDir = Path.GetDirectoryName(update.LocalFilePath);
                    Directory.CreateDirectory(destDir);
                    if (update.IsNew)
                    {
                        string newFile = Path.Combine(destDir, remote.file);
                        if (File.Exists(newFile)) File.Delete(newFile);
                        File.Move(tmpFile, newFile);
                        replacedPairs.Add(new string[] { null, newFile, newFile });
                        SetProgress((int)((i + 1) * 100.0 / total));
                        continue;
                    }

                    string relOld = update.LocalFilePath.Substring(gamePath.Length).TrimStart('\\', '/');
                    string bkpFile = Path.Combine(bkpDir, relOld);
                    Directory.CreateDirectory(Path.GetDirectoryName(bkpFile));
                    File.Copy(update.LocalFilePath, bkpFile, true);

                    string newDestPath = Path.Combine(destDir, remote.file);
                    File.Delete(update.LocalFilePath);
                    if (File.Exists(newDestPath)) File.Delete(newDestPath);
                    File.Move(tmpFile, newDestPath);
                    replacedPairs.Add(new string[] { bkpFile, update.LocalFilePath, newDestPath });
                    SetProgress((int)((i + 1) * 100.0 / total));
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
                foreach (string[] pair in replacedPairs)
                {
                    try
                    {
                        if (File.Exists(pair[2])) File.Delete(pair[2]);
                        if (pair[0] != null && File.Exists(pair[0])) File.Copy(pair[0], pair[1], true);
                    }
                    catch { }
                }

                BeginInvoke(new Action(() =>
                {
                    isUpdating = false;
                    MessageBox.Show(
                        "Оновлення не вдалося (" + ex.Message + ").\nВідновлено попередні версії модів, запускаємо гру.",
                        "WoT Modpack Launcher", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                    Close();
                }));
            }
        }

        private void DownloadFileWithProgress(string url, string dstPath, int index, int total)
        {
            string localSrc = Program.ResolveLocalUrl(url);
            if (localSrc != null)
            {
                File.Copy(localSrc, dstPath, true);
                SetProgress((int)((index + 1) * 100.0 / total));
                return;
            }

            HttpWebRequest req = (HttpWebRequest)WebRequest.Create(url);
            req.UserAgent = "WotModLauncher/" + Program.LauncherVersion;
            req.Timeout = 15000;
            req.ReadWriteTimeout = 15000;
            using (HttpWebResponse resp = (HttpWebResponse)req.GetResponse())
            using (Stream stream = resp.GetResponseStream())
            using (FileStream file = File.Create(dstPath))
            {
                long length = resp.ContentLength;
                byte[] buffer = new byte[16384];
                long readTotal = 0;
                int lastPct = -1;
                int n;
                while ((n = stream.Read(buffer, 0, buffer.Length)) > 0)
                {
                    file.Write(buffer, 0, n);
                    readTotal += n;
                    if (length > 0)
                    {
                        int pct = (int)((index + (float)readTotal / length) * 100.0 / total);
                        if (pct != lastPct)
                        {
                            lastPct = pct;
                            SetProgress(pct);
                        }
                    }
                }
            }
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
