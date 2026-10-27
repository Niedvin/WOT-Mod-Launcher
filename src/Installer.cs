using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.IO;
using System.IO.Compression;
using System.Net;
using System.Reflection;
using System.Text.RegularExpressions;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Win32;

[assembly: AssemblyTitle("WoT Modpack by Niedvin")]
[assembly: AssemblyDescription("Інсталятор модифікацій World of Tanks")]
[assembly: AssemblyCompany("Niedvin")]
[assembly: AssemblyProduct("WoT Modpack by Niedvin")]
[assembly: AssemblyCopyright("Copyright © 2026 Niedvin")]
[assembly: AssemblyFileVersion("1.0.0.0")]
[assembly: AssemblyVersion("1.0.0.0")]

namespace WotModpackInstaller
{
    public class ModItem
    {
        public string id { get; set; }
        public string title { get; set; }
        public string version { get; set; }
        public string author { get; set; }
        public string description { get; set; }
        public bool default_checked { get; set; }
        public bool required { get; set; }
        public object[] clean_patterns { get; set; }
        public object[] clean_res_mods { get; set; }
        public long size_bytes { get; set; }
        public UpdateSource[] updates { get; set; }
        public string FolderPath { get; set; }

        public override string ToString()
        {
            string sizeStr;
            if (size_bytes > 1024 * 1024)
                sizeStr = string.Format("{0:0.1} MB", size_bytes / (1024.0 * 1024.0));
            else
                sizeStr = string.Format("{0} KB", Math.Max(1, size_bytes / 1024));

            return string.Format("{0} v{1} ({2})", title, version, sizeStr);
        }
    }

    public class UpdateSource
    {
        public string id { get; set; }
        public string kind { get; set; }
        public string repo { get; set; }
    }

    public class MainForm : Form
    {
        private Panel headerPanel;
        private Label lblHeaderTitle;
        private Label lblHeaderSubtitle;

        private SectionPanel grpGamePath;
        private TextBox txtGamePath;
        private Button btnBrowse;
        private Label lblGameStatus;

        private SectionPanel grpMods;
        private CheckedListBox chkListMods;
        private Button btnSelectAll;
        private Button btnDeselectAll;
        private Label lblModCounter;
        private Label lblRequiredNote;
        private Label lblModDetailsTitle;
        private Label lblModDetailsMeta;
        private TextBox txtModDescription;

        private SectionPanel grpOptions;
        private CheckBox chkCleanOld;
        private CheckBox chkBackup;
        private CheckBox chkInstallLauncher;
        private CheckBox chkHijackShortcuts;

        private ProgressBar prgInstall;
        private Label lblStatus;
        private TextBox txtLog;

        private Button btnInstall;
        private Button btnLaunchGame;
        private Button btnExit;
        private Button btnRollback;
        private Button btnUninstall;

        private List<ModItem> loadedMods = new List<ModItem>();
        private string detectedGameVersion = "2.4.1.0";
        private string modsRootPath = "";
        private ManualResetEvent prefetchDone = new ManualResetEvent(false);
        private static string payloadDir;

        public MainForm()
        {
            InitializeComponent();
            LocateModsFolder();
            LoadModsList();
            AutoDetectGame();
            Thread prefetch = new Thread(PrefetchUpdates);
            prefetch.IsBackground = true;
            this.Shown += (o, e) => prefetch.Start();
        }

        private void InitializeComponent()
        {
            this.Text = "WoT Modpack by Niedvin — Інсталятор модів";
            this.ClientSize = new Size(856, 748);
            this.StartPosition = FormStartPosition.CenterScreen;
            this.FormBorderStyle = FormBorderStyle.FixedSingle;
            this.MaximizeBox = false;
            this.Font = new Font("Segoe UI", 9F, FontStyle.Regular, GraphicsUnit.Point);
            this.BackColor = Color.FromArgb(20, 25, 38);
            this.DoubleBuffered = true;

            headerPanel = new Panel();
            headerPanel.Dock = DockStyle.Top;
            headerPanel.Height = 84;
            headerPanel.BackColor = Color.FromArgb(15, 19, 29);
            headerPanel.Paint += (s, e) =>
            {
                using (var br = new SolidBrush(Color.FromArgb(229, 160, 40)))
                    e.Graphics.FillRectangle(br, 0, headerPanel.Height - 2, headerPanel.Width, 2);
            };

            lblHeaderTitle = new Label();
            lblHeaderTitle.Text = "WORLD OF TANKS — MODPACK";
            lblHeaderTitle.Font = new Font("Segoe UI", 15F, FontStyle.Bold, GraphicsUnit.Point);
            lblHeaderTitle.ForeColor = Color.White;
            lblHeaderTitle.Location = new Point(24, 16);
            lblHeaderTitle.AutoSize = true;

            lblHeaderSubtitle = new Label();
            lblHeaderSubtitle.Text = "Збірка модифікацій від Niedvin • інсталятор з лаунчером автооновлення через GitHub";
            lblHeaderSubtitle.Font = new Font("Segoe UI", 9F, FontStyle.Regular, GraphicsUnit.Point);
            lblHeaderSubtitle.ForeColor = Color.FromArgb(229, 160, 40);
            lblHeaderSubtitle.Location = new Point(26, 52);
            lblHeaderSubtitle.AutoSize = true;

            headerPanel.Controls.Add(lblHeaderTitle);
            headerPanel.Controls.Add(lblHeaderSubtitle);
            this.Controls.Add(headerPanel);

            grpGamePath = new SectionPanel("Папка гри World of Tanks");
            grpGamePath.Location = new Point(16, 100);
            grpGamePath.Size = new Size(824, 92);

            txtGamePath = new TextBox();
            txtGamePath.Location = new Point(14, 32);
            txtGamePath.Size = new Size(668, 25);
            txtGamePath.BackColor = Color.FromArgb(35, 43, 61);
            txtGamePath.ForeColor = Color.White;
            txtGamePath.BorderStyle = BorderStyle.FixedSingle;
            txtGamePath.TextChanged += (s, e) => ValidateGamePath();

            btnBrowse = MakeButton("Огляд...", Color.FromArgb(39, 48, 67), Color.FromArgb(233, 237, 245), false);
            btnBrowse.Location = new Point(692, 31);
            btnBrowse.Size = new Size(112, 27);
            btnBrowse.Click += BtnBrowse_Click;

            lblGameStatus = new Label();
            lblGameStatus.Location = new Point(14, 64);
            lblGameStatus.Size = new Size(792, 20);
            lblGameStatus.ForeColor = Color.FromArgb(150, 162, 186);
            lblGameStatus.Text = "Пошук гри...";

            grpGamePath.Controls.Add(txtGamePath);
            grpGamePath.Controls.Add(btnBrowse);
            grpGamePath.Controls.Add(lblGameStatus);
            this.Controls.Add(grpGamePath);

            grpMods = new SectionPanel("Модифікації");
            grpMods.Location = new Point(16, 202);
            grpMods.Size = new Size(824, 242);

            lblModCounter = new Label();
            lblModCounter.Location = new Point(520, 8);
            lblModCounter.Size = new Size(290, 18);
            lblModCounter.TextAlign = ContentAlignment.MiddleRight;
            lblModCounter.ForeColor = Color.FromArgb(229, 160, 40);
            lblModCounter.Font = new Font("Segoe UI", 9F, FontStyle.Bold, GraphicsUnit.Point);
            lblModCounter.Text = "Вибрано: 0 з 0";

            chkListMods = new CheckedListBox();
            chkListMods.Location = new Point(14, 32);
            chkListMods.Size = new Size(470, 156);
            chkListMods.CheckOnClick = true;
            chkListMods.BorderStyle = BorderStyle.FixedSingle;
            chkListMods.SelectedIndexChanged += ChkListMods_SelectedIndexChanged;
            chkListMods.ItemCheck += (s, e) => BeginInvoke(new Action(UpdateModCounter));

            btnSelectAll = MakeButton("Вибрати всі", Color.FromArgb(39, 48, 67), Color.FromArgb(233, 237, 245), false);
            btnSelectAll.Location = new Point(14, 196);
            btnSelectAll.Size = new Size(108, 26);
            btnSelectAll.Click += (s, e) => { for (int i = 0; i < chkListMods.Items.Count; i++) chkListMods.SetItemChecked(i, true); };

            btnDeselectAll = MakeButton("Зняти всі", Color.FromArgb(39, 48, 67), Color.FromArgb(233, 237, 245), false);
            btnDeselectAll.Location = new Point(130, 196);
            btnDeselectAll.Size = new Size(108, 26);
            btnDeselectAll.Click += (s, e) => { for (int i = 0; i < chkListMods.Items.Count; i++) chkListMods.SetItemChecked(i, false); };

            lblRequiredNote = new Label();
            lblRequiredNote.Location = new Point(252, 194);
            lblRequiredNote.Size = new Size(232, 34);
            lblRequiredNote.ForeColor = Color.FromArgb(120, 132, 156);
            lblRequiredNote.Font = new Font("Segoe UI", 8F, FontStyle.Regular, GraphicsUnit.Point);
            lblRequiredNote.Text = "Системні API (ModsSettings, ModsList, OpenWG) встановлюються завжди";

            Panel pnlModInfo = new Panel();
            pnlModInfo.Location = new Point(496, 32);
            pnlModInfo.Size = new Size(314, 190);
            pnlModInfo.BackColor = Color.FromArgb(244, 246, 250);
            pnlModInfo.BorderStyle = BorderStyle.FixedSingle;

            lblModDetailsTitle = new Label();
            lblModDetailsTitle.Location = new Point(10, 10);
            lblModDetailsTitle.Size = new Size(292, 22);
            lblModDetailsTitle.Font = new Font("Segoe UI", 9.5F, FontStyle.Bold, GraphicsUnit.Point);
            lblModDetailsTitle.ForeColor = Color.FromArgb(30, 36, 48);
            lblModDetailsTitle.Text = "Оберіть мод зі списку";

            lblModDetailsMeta = new Label();
            lblModDetailsMeta.Location = new Point(10, 34);
            lblModDetailsMeta.Size = new Size(292, 20);
            lblModDetailsMeta.Font = new Font("Segoe UI", 8.5F, FontStyle.Regular, GraphicsUnit.Point);
            lblModDetailsMeta.ForeColor = Color.FromArgb(106, 118, 136);
            lblModDetailsMeta.Text = "";

            txtModDescription = new TextBox();
            txtModDescription.Location = new Point(10, 58);
            txtModDescription.Size = new Size(294, 122);
            txtModDescription.Multiline = true;
            txtModDescription.ReadOnly = true;
            txtModDescription.BorderStyle = BorderStyle.None;
            txtModDescription.BackColor = Color.FromArgb(244, 246, 250);
            txtModDescription.ForeColor = Color.FromArgb(42, 51, 72);
            txtModDescription.Font = new Font("Segoe UI", 8.8F, FontStyle.Regular, GraphicsUnit.Point);

            pnlModInfo.Controls.Add(lblModDetailsTitle);
            pnlModInfo.Controls.Add(lblModDetailsMeta);
            pnlModInfo.Controls.Add(txtModDescription);

            grpMods.Controls.Add(lblModCounter);
            grpMods.Controls.Add(chkListMods);
            grpMods.Controls.Add(btnSelectAll);
            grpMods.Controls.Add(btnDeselectAll);
            grpMods.Controls.Add(lblRequiredNote);
            grpMods.Controls.Add(pnlModInfo);
            this.Controls.Add(grpMods);

            grpOptions = new SectionPanel("Параметри встановлення");
            grpOptions.Location = new Point(16, 454);
            grpOptions.Size = new Size(824, 106);

            chkCleanOld = new CheckBox();
            chkCleanOld.Text = "Очищати старі версії модів (рекомендовано)";
            chkCleanOld.Location = new Point(14, 34);
            chkCleanOld.AutoSize = true;
            chkCleanOld.Checked = true;
            chkCleanOld.ForeColor = Color.FromArgb(233, 237, 245);

            chkBackup = new CheckBox();
            chkBackup.Text = "Бекап перед заміною (.backups)";
            chkBackup.Location = new Point(436, 34);
            chkBackup.AutoSize = true;
            chkBackup.Checked = true;
            chkBackup.ForeColor = Color.FromArgb(233, 237, 245);

            chkInstallLauncher = new CheckBox();
            chkInstallLauncher.Text = "Встановити лаунчер автооновлення";
            chkInstallLauncher.Location = new Point(14, 68);
            chkInstallLauncher.AutoSize = true;
            chkInstallLauncher.Checked = true;
            chkInstallLauncher.ForeColor = Color.FromArgb(233, 237, 245);
            chkInstallLauncher.CheckedChanged += (s, e) => { chkHijackShortcuts.Enabled = chkInstallLauncher.Checked; };

            chkHijackShortcuts = new CheckBox();
            chkHijackShortcuts.Text = "Вбудувати у стандартні ярлики гри";
            chkHijackShortcuts.Location = new Point(436, 68);
            chkHijackShortcuts.AutoSize = true;
            chkHijackShortcuts.Checked = true;
            chkHijackShortcuts.ForeColor = Color.FromArgb(233, 237, 245);

            grpOptions.Controls.Add(chkCleanOld);
            grpOptions.Controls.Add(chkBackup);
            grpOptions.Controls.Add(chkInstallLauncher);
            grpOptions.Controls.Add(chkHijackShortcuts);
            this.Controls.Add(grpOptions);

            lblStatus = new Label();
            lblStatus.Location = new Point(16, 570);
            lblStatus.Size = new Size(824, 18);
            lblStatus.ForeColor = Color.FromArgb(150, 162, 186);
            lblStatus.Text = "Готово до встановлення";

            prgInstall = new ProgressBar();
            prgInstall.Location = new Point(16, 592);
            prgInstall.Size = new Size(824, 18);

            SectionPanel grpLog = new SectionPanel(null);
            grpLog.Location = new Point(16, 618);
            grpLog.Size = new Size(824, 66);

            txtLog = new TextBox();
            txtLog.Location = new Point(10, 8);
            txtLog.Size = new Size(804, 50);
            txtLog.Multiline = true;
            txtLog.ReadOnly = true;
            txtLog.ScrollBars = ScrollBars.Vertical;
            txtLog.Font = new Font("Consolas", 8.5F, FontStyle.Regular, GraphicsUnit.Point);
            txtLog.BackColor = Color.FromArgb(15, 19, 29);
            txtLog.ForeColor = Color.FromArgb(143, 162, 191);
            txtLog.BorderStyle = BorderStyle.None;
            grpLog.Controls.Add(txtLog);
            this.Controls.Add(grpLog);
            this.Controls.Add(lblStatus);
            this.Controls.Add(prgInstall);

            btnInstall = MakeButton("Встановити вибрані моди", Color.FromArgb(47, 125, 58), Color.White, true);
            btnInstall.Location = new Point(16, 694);
            btnInstall.Size = new Size(210, 40);
            btnInstall.Click += BtnInstall_Click;

            btnLaunchGame = MakeButton("Запустити World of Tanks", Color.FromArgb(39, 48, 67), Color.FromArgb(233, 237, 245), false);
            btnLaunchGame.Location = new Point(236, 694);
            btnLaunchGame.Size = new Size(200, 40);
            btnLaunchGame.Enabled = false;
            btnLaunchGame.Click += BtnLaunchGame_Click;

            btnRollback = MakeButton("Відкат до бекапу", Color.FromArgb(39, 48, 67), Color.FromArgb(233, 237, 245), false);
            btnRollback.Location = new Point(446, 694);
            btnRollback.Size = new Size(130, 40);
            btnRollback.Click += BtnRollback_Click;

            btnUninstall = MakeButton("Видалити...", Color.FromArgb(39, 48, 67), Color.FromArgb(224, 108, 108), false);
            btnUninstall.Location = new Point(586, 694);
            btnUninstall.Size = new Size(130, 40);
            btnUninstall.Click += BtnUninstall_Click;

            btnExit = MakeButton("Вихід", Color.FromArgb(39, 48, 67), Color.FromArgb(150, 162, 186), false);
            btnExit.Location = new Point(726, 694);
            btnExit.Size = new Size(114, 40);
            btnExit.Click += (s, e) => this.Close();

            this.Controls.Add(btnInstall);
            this.Controls.Add(btnLaunchGame);
            this.Controls.Add(btnRollback);
            this.Controls.Add(btnUninstall);
            this.Controls.Add(btnExit);
        }

        internal static Button MakeButton(string text, Color back, Color fore, bool bold)
        {
            Button b = new Button();
            b.Text = text;
            b.BackColor = back;
            b.ForeColor = fore;
            b.FlatStyle = FlatStyle.Flat;
            b.FlatAppearance.BorderColor = Color.FromArgb(57, 68, 95);
            b.FlatAppearance.MouseOverBackColor = ControlPaint.Light(back, 0.12F);
            b.FlatAppearance.MouseDownBackColor = ControlPaint.Dark(back, 0.05F);
            b.Cursor = Cursors.Hand;
            if (bold) b.Font = new Font("Segoe UI", 10F, FontStyle.Bold, GraphicsUnit.Point);
            return b;
        }

        private void UpdateModCounter()
        {
            int count = 0;
            long bytes = 0;
            for (int i = 0; i < chkListMods.Items.Count; i++)
            {
                if (chkListMods.GetItemChecked(i))
                {
                    count++;
                    bytes += ((ModItem)chkListMods.Items[i]).size_bytes;
                }
            }
            lblModCounter.Text = string.Format("Вибрано: {0} з {1}  •  {2:0.0} МБ", count, chkListMods.Items.Count, bytes / (1024.0 * 1024.0));
        }

        private class SectionPanel : Panel
        {
            public string Title;

            public SectionPanel(string title)
            {
                Title = title;
                BackColor = Color.FromArgb(27, 34, 51);
                SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.UserPaint | ControlStyles.OptimizedDoubleBuffer | ControlStyles.ResizeRedraw, true);
            }

            protected override void OnPaint(PaintEventArgs e)
            {
                Graphics g = e.Graphics;
                g.SmoothingMode = SmoothingMode.AntiAlias;
                Rectangle rect = new Rectangle(1, 1, Width - 3, Height - 3);
                using (GraphicsPath path = new GraphicsPath())
                {
                    int d = 16;
                    path.AddArc(rect.X, rect.Y, d, d, 180, 90);
                    path.AddArc(rect.Right - d, rect.Y, d, d, 270, 90);
                    path.AddArc(rect.Right - d, rect.Bottom - d, d, d, 0, 90);
                    path.AddArc(rect.X, rect.Bottom - d, d, d, 90, 90);
                    path.CloseFigure();
                    using (var br = new SolidBrush(BackColor)) g.FillPath(br, path);
                    using (var pen = new Pen(Color.FromArgb(45, 56, 84), 1.4f)) g.DrawPath(pen, path);
                }
                if (!string.IsNullOrEmpty(Title))
                    using (var f = new Font("Segoe UI", 8.25F, FontStyle.Bold, GraphicsUnit.Point))
                    using (var br = new SolidBrush(Color.FromArgb(150, 162, 186)))
                        g.DrawString(Title.ToUpper(), f, br, 14f, 8f);
            }
        }

        internal static bool IsValidModsRoot(string dir)
        {
            if (string.IsNullOrEmpty(dir) || !Directory.Exists(dir)) return false;
            foreach (string sub in Directory.GetDirectories(dir))
            {
                if (File.Exists(Path.Combine(sub, "info.json"))) return true;
            }
            return false;
        }

        internal static string ResolveModsRoot()
        {
            string exeDir = "";
            try
            {
                exeDir = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
            }
            catch { }
            if (string.IsNullOrEmpty(exeDir))
            {
                exeDir = AppDomain.CurrentDomain.BaseDirectory;
            }

            string[] candidates = new string[] {
                Path.Combine(exeDir, "Mods"),
                Path.Combine(exeDir, "staging_modpack", "Mods"),
                Path.Combine(exeDir, "WoT modpack by Niedvin", "Mods"),
                Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "Mods"),
                Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "staging_modpack", "Mods")
            };

            foreach (string cand in candidates)
            {
                if (IsValidModsRoot(cand)) return cand;
            }

            try
            {
                string parentCandidate = Path.Combine(Directory.GetParent(exeDir).FullName, "Mods");
                if (IsValidModsRoot(parentCandidate)) return parentCandidate;
            }
            catch { }

            string payload = ExtractEmbeddedPayload();
            if (payload != null)
            {
                string payloadMods = Path.Combine(payload, "Mods");
                if (IsValidModsRoot(payloadMods)) return payloadMods;
            }
            return null;
        }

        private void LocateModsFolder()
        {
            modsRootPath = ResolveModsRoot();
            if (modsRootPath != null)
            {
                Log("[Джерело модів] " + modsRootPath);
            }
            else
            {
                modsRootPath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "Mods");
            }
        }

        private void LoadModsList()
        {
            chkListMods.Items.Clear();
            loadedMods.Clear();

            if (!Directory.Exists(modsRootPath))
            {
                Log("УВАГА: Папку Mods не знайдено за шляхом: " + modsRootPath);
                Log("Переконайтеся, що архів розархівовано повністю перед запуском.");
                return;
            }

            var dirs = Directory.GetDirectories(modsRootPath);
            Array.Sort(dirs);

            JavaScriptSerializer serializer = new JavaScriptSerializer();

            foreach (var dir in dirs)
            {
                string infoFile = Path.Combine(dir, "info.json");
                if (File.Exists(infoFile))
                {
                    try
                    {
                        string json = File.ReadAllText(infoFile, System.Text.Encoding.UTF8);
                        ModItem item = serializer.Deserialize<ModItem>(json);
                        item.FolderPath = dir;
                        loadedMods.Add(item);
                        if (item.required) continue;

                        int idx = chkListMods.Items.Add(item);
                        chkListMods.SetItemChecked(idx, item.default_checked);
                    }
                    catch (Exception ex)
                    {
                        Log("Помилка читання info.json в " + Path.GetFileName(dir) + ": " + ex.Message);
                    }
                }
            }

            if (chkListMods.Items.Count > 0)
            {
                chkListMods.SelectedIndex = 0;
            }
            UpdateModCounter();

            var req = loadedMods.FindAll(m => m.required).ConvertAll(m => m.title);
            Log(string.Format("Модів на вибір: {0}", loadedMods.Count - req.Count));
            if (req.Count > 0)
                Log("Встановлюються автоматично: " + string.Join(", ", req.ToArray()));
        }

        private void ChkListMods_SelectedIndexChanged(object sender, EventArgs e)
        {
            ModItem item = chkListMods.SelectedItem as ModItem;
            if (item != null)
            {
                lblModDetailsTitle.Text = item.title;
                lblModDetailsMeta.Text = string.Format("Версія: {0}  |  Автор: {1}", item.version, item.author);
                txtModDescription.Text = item.description;
            }
        }

        private void AutoDetectGame()
        {
            string foundPath = FindWotPath();
            if (!string.IsNullOrEmpty(foundPath))
            {
                txtGamePath.Text = foundPath;
            }
            else
            {
                txtGamePath.Text = "";
                ValidateGamePath();
            }
        }

        private string CleanCandidatePath(string path)
        {
            if (string.IsNullOrEmpty(path)) return "";
            path = path.Trim('"', ' ', '\t', '\r', '\n');
            try
            {
                int commaIdx = path.IndexOf(',');
                if (commaIdx > 0) path = path.Substring(0, commaIdx).Trim('"', ' ');
                if (File.Exists(path))
                    path = Path.GetDirectoryName(path);
                if (Directory.Exists(path))
                {
                    if (string.Equals(Path.GetFileName(path), "win64", StringComparison.OrdinalIgnoreCase) ||
                        string.Equals(Path.GetFileName(path), "win32", StringComparison.OrdinalIgnoreCase))
                    {
                        var p = Directory.GetParent(path);
                        if (p != null && IsValidWotDir(p.FullName)) return p.FullName;
                    }
                    if (IsValidWotDir(path)) return path;
                }
            }
            catch { }
            return "";
        }

        private string ExtractDirectoryFromCommand(string cmd)
        {
            if (string.IsNullOrEmpty(cmd)) return "";
            cmd = cmd.Trim();
            try
            {
                string exePath = "";
                if (cmd.StartsWith("\""))
                {
                    int closeQuote = cmd.IndexOf('"', 1);
                    if (closeQuote > 1) exePath = cmd.Substring(1, closeQuote - 1);
                }
                else
                {
                    int spaceIdx = cmd.IndexOf(' ');
                    exePath = spaceIdx > 0 ? cmd.Substring(0, spaceIdx) : cmd;
                }
                return CleanCandidatePath(exePath);
            }
            catch { }
            return "";
        }

        private string FindWotPathFromWgcApps()
        {
            string[] appDirs = new string[] {
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), @"Wargaming.net\GameCenter\apps"),
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), @"Lesta\GameCenter\apps"),
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), @"Wargaming.net\GameCenter\apps"),
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), @"Lesta\GameCenter\apps")
            };

            foreach (var baseDir in appDirs)
            {
                try
                {
                    if (!Directory.Exists(baseDir)) continue;
                    foreach (var sub in Directory.GetDirectories(baseDir))
                    {
                        string folderName = Path.GetFileName(sub).ToLowerInvariant();
                        if (folderName.StartsWith("wot") || folderName.Contains("tank"))
                        {
                            foreach (var f in Directory.GetFiles(sub))
                            {
                                try
                                {
                                    string raw = File.ReadAllText(f).Trim();
                                    string cleaned = CleanCandidatePath(raw);
                                    if (!string.IsNullOrEmpty(cleaned)) return cleaned;
                                }
                                catch { }
                            }
                        }
                    }
                }
                catch { }
            }
            return "";
        }

        private string FindWotPathFromRegistry()
        {
            RegistryKey[] rootHives = new RegistryKey[] {
                Registry.CurrentUser,
                Registry.LocalMachine
            };

            string[] uninstallKeys = new string[] {
                @"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
                @"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"
            };

            foreach (var hive in rootHives)
            {
                foreach (var keyPath in uninstallKeys)
                {
                    try
                    {
                        using (var regKey = hive.OpenSubKey(keyPath))
                        {
                            if (regKey == null) continue;
                            foreach (var sub in regKey.GetSubKeyNames())
                            {
                                try
                                {
                                    using (var app = regKey.OpenSubKey(sub))
                                    {
                                        if (app == null) continue;
                                        var disp = app.GetValue("DisplayName") as string;
                                        if (string.IsNullOrEmpty(disp)) continue;
                                        if (disp.IndexOf("World of Tanks", StringComparison.OrdinalIgnoreCase) >= 0 ||
                                            disp.IndexOf("Мир танков", StringComparison.OrdinalIgnoreCase) >= 0)
                                        {
                                            var loc = app.GetValue("InstallLocation") as string;
                                            string cleaned = CleanCandidatePath(loc);
                                            if (!string.IsNullOrEmpty(cleaned)) return cleaned;

                                            var icon = app.GetValue("DisplayIcon") as string;
                                            cleaned = CleanCandidatePath(icon);
                                            if (!string.IsNullOrEmpty(cleaned)) return cleaned;

                                            var uninst = app.GetValue("UninstallString") as string;
                                            cleaned = ExtractDirectoryFromCommand(uninst);
                                            if (!string.IsNullOrEmpty(cleaned)) return cleaned;
                                        }
                                    }
                                }
                                catch { }
                            }
                        }
                    }
                    catch { }
                }
            }
            return "";
        }

        private string FindWotPathFromRunningProcess()
        {
            string[] procNames = new string[] { "WorldOfTanks", "WorldOfTanks32" };
            foreach (var name in procNames)
            {
                try
                {
                    var procs = Process.GetProcessesByName(name);
                    foreach (var p in procs)
                    {
                        try
                        {
                            string fn = p.MainModule.FileName;
                            string cleaned = CleanCandidatePath(fn);
                            if (!string.IsNullOrEmpty(cleaned)) return cleaned;
                        }
                        catch { }
                    }
                }
                catch { }
            }
            return "";
        }

        private string FindWotPathFromDrives()
        {
            string[] subPaths = new string[] {
                @"Games\World_of_Tanks_EU",
                @"Games\World_of_Tanks",
                @"Games\World of Tanks EU",
                @"Games\World of Tanks",
                @"Games\World_of_Tanks_NA",
                @"Games\World_of_Tanks_ASIA",
                @"Games\World_of_Tanks_RU",
                @"Games\Мир танков",
                @"Games\Mir Tankov",
                @"Games\WoT",
                @"Games\Tanki",
                @"World_of_Tanks_EU",
                @"World_of_Tanks",
                @"World of Tanks EU",
                @"World of Tanks",
                @"Мир танков",
                @"Mir Tankov",
                @"WoT",
                @"Program Files\World_of_Tanks_EU",
                @"Program Files\World of Tanks",
                @"Program Files (x86)\World_of_Tanks_EU",
                @"Program Files (x86)\World of Tanks",
                @"Wargaming.net\GameCenter\games\wot_eu",
                @"Wargaming.net\GameCenter\games\wot_na",
                @"Wargaming.net\GameCenter\games\wot_asia",
                @"Games\Wargaming.net\GameCenter\games\wot_eu"
            };

            try
            {
                foreach (var d in DriveInfo.GetDrives())
                {
                    if (!d.IsReady) continue;
                    string root = d.RootDirectory.FullName;
                    foreach (var sub in subPaths)
                    {
                        string candidate = Path.Combine(root, sub);
                        if (IsValidWotDir(candidate)) return candidate;
                    }
                }
            }
            catch { }
            return "";
        }

        private string FindWotPathFromAppDomain()
        {
            try
            {
                string current = AppDomain.CurrentDomain.BaseDirectory;
                string cleaned = CleanCandidatePath(current);
                if (!string.IsNullOrEmpty(cleaned)) return cleaned;

                var p = Directory.GetParent(current);
                if (p != null)
                {
                    cleaned = CleanCandidatePath(p.FullName);
                    if (!string.IsNullOrEmpty(cleaned)) return cleaned;

                    var pp = p.Parent;
                    if (pp != null)
                    {
                        cleaned = CleanCandidatePath(pp.FullName);
                        if (!string.IsNullOrEmpty(cleaned)) return cleaned;
                    }
                }
            }
            catch { }
            return "";
        }

        private string FindWotPath()
        {
            string path = FindWotPathFromWgcApps();
            if (!string.IsNullOrEmpty(path)) return path;

            path = FindWotPathFromRegistry();
            if (!string.IsNullOrEmpty(path)) return path;

            path = FindWotPathFromRunningProcess();
            if (!string.IsNullOrEmpty(path)) return path;

            path = FindWotPathFromDrives();
            if (!string.IsNullOrEmpty(path)) return path;

            path = FindWotPathFromAppDomain();
            if (!string.IsNullOrEmpty(path)) return path;

            return "";
        }

        private bool IsValidWotDir(string path)
        {
            if (string.IsNullOrEmpty(path) || !Directory.Exists(path)) return false;
            return File.Exists(Path.Combine(path, "WorldOfTanks.exe")) ||
                   File.Exists(Path.Combine(path, "version.xml")) ||
                   File.Exists(Path.Combine(path, "paths.xml")) ||
                   File.Exists(Path.Combine(path, "win64", "WorldOfTanks.exe"));
        }

        private void ValidateGamePath()
        {
            string raw = txtGamePath.Text.Trim();
            string cleaned = CleanCandidatePath(raw);
            if (!string.IsNullOrEmpty(cleaned) && cleaned != raw)
            {
                txtGamePath.Text = cleaned;
                return;
            }
            if (IsValidWotDir(cleaned))
            {
                detectedGameVersion = DetectGameVersion(cleaned);
                lblGameStatus.ForeColor = Color.FromArgb(111, 207, 139);
                lblGameStatus.Text = string.Format("✔ Клієнт World of Tanks знайдено! Версія гри: {0}", detectedGameVersion);
                btnInstall.Enabled = true;
            }
            else
            {
                lblGameStatus.ForeColor = Color.FromArgb(224, 122, 122);
                lblGameStatus.Text = "⚠ Папку гри не розпізнано. Вкажіть правильний шлях через кнопку 'Огляд...'";
                btnInstall.Enabled = false;
            }
        }

        private string DetectGameVersion(string gamePath)
        {
            string vXml = Path.Combine(gamePath, "version.xml");
            if (File.Exists(vXml))
            {
                try
                {
                    string content = File.ReadAllText(vXml);
                    var m = Regex.Match(content, @"v\.([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)");
                    if (m.Success) return m.Groups[1].Value;
                }
                catch { }
            }

            string pathsXml = Path.Combine(gamePath, "paths.xml");
            if (File.Exists(pathsXml))
            {
                try
                {
                    string content = File.ReadAllText(pathsXml);
                    var m = Regex.Match(content, @"(?:mods|res_mods)[/\\]([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)");
                    if (m.Success) return m.Groups[1].Value;
                }
                catch { }
            }

            string modsDir = Path.Combine(gamePath, "mods");
            if (Directory.Exists(modsDir))
            {
                try
                {
                    var dirs = Directory.GetDirectories(modsDir);
                    List<string> versions = new List<string>();
                    foreach (var d in dirs)
                    {
                        string name = Path.GetFileName(d);
                        if (Regex.IsMatch(name, @"^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$"))
                            versions.Add(name);
                    }
                    if (versions.Count > 0)
                    {
                        versions.Sort();
                        return versions[versions.Count - 1];
                    }
                }
                catch { }
            }

            return "2.4.1.0";
        }

        private void BtnBrowse_Click(object sender, EventArgs e)
        {
            using (FolderBrowserDialog dlg = new FolderBrowserDialog())
            {
                dlg.Description = "Оберіть кореневу папку гри World of Tanks:";
                if (!string.IsNullOrEmpty(txtGamePath.Text) && Directory.Exists(txtGamePath.Text))
                    dlg.SelectedPath = txtGamePath.Text;

                if (dlg.ShowDialog() == DialogResult.OK)
                {
                    txtGamePath.Text = dlg.SelectedPath;
                    ValidateGamePath();
                }
            }
        }

        private void BtnInstall_Click(object sender, EventArgs e)
        {
            List<ModItem> selected = new List<ModItem>();
            for (int i = 0; i < chkListMods.Items.Count; i++)
            {
                if (chkListMods.GetItemChecked(i))
                {
                    selected.Add((ModItem)chkListMods.Items[i]);
                }
            }

            if (selected.Count == 0)
            {
                MessageBox.Show("Будь ласка, оберіть хоча б один мод для встановлення.", "Попередження", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }
            foreach (var m in loadedMods)
                if (m.required) selected.Insert(0, m);

            string gamePath = txtGamePath.Text.Trim();
            if (!IsValidWotDir(gamePath))
            {
                MessageBox.Show("Шлях до гри недійсний. Вкажіть кореневу папку World of Tanks.", "Помилка", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return;
            }

            Process[] runningProcs = new Process[0];
            try
            {
                var list = new List<Process>();
                list.AddRange(Process.GetProcessesByName("WorldOfTanks"));
                list.AddRange(Process.GetProcessesByName("WorldOfTanks32"));
                runningProcs = list.ToArray();
            }
            catch { }

            if (runningProcs.Length > 0)
            {
                DialogResult dr = MessageBox.Show(
                    "Виявлено запущений процес World of Tanks!\n\nПід час роботи гри файли модифікацій заблоковані.\nЗакрити World of Tanks автоматично перед встановленням?",
                    "Гра запущена",
                    MessageBoxButtons.YesNoCancel,
                    MessageBoxIcon.Warning
                );

                if (dr == DialogResult.Yes)
                {
                    foreach (var p in runningProcs)
                    {
                        try
                        {
                            p.CloseMainWindow();
                            if (!p.WaitForExit(3000))
                            {
                                p.Kill();
                                p.WaitForExit(2000);
                            }
                        }
                        catch { }
                    }
                    Thread.Sleep(800);
                }
                else
                {
                    return;
                }
            }

            btnInstall.Enabled = false;
            btnBrowse.Enabled = false;
            btnSelectAll.Enabled = false;
            btnDeselectAll.Enabled = false;
            chkListMods.Enabled = false;

            bool installLauncher = chkInstallLauncher.Checked;
            bool hijackShortcuts = chkHijackShortcuts.Checked;
            Thread worker = new Thread(() => RunInstallation(gamePath, selected, chkCleanOld.Checked, chkBackup.Checked, installLauncher, hijackShortcuts));
            worker.IsBackground = true;
            worker.Start();
        }

        private void RunInstallation(string gamePath, List<ModItem> mods, bool cleanOld, bool doBackup, bool installLauncher, bool hijackShortcuts)
        {
            try
            {
                if (!prefetchDone.WaitOne(0))
                {
                    UpdateStatus("Очікування завантаження оновлень...");
                    if (!prefetchDone.WaitOne(90000))
                        Log("[Оновлення] Завантаження не завершилось за 90 с, ставлю версії з архіву");
                }
                UpdateStatus("Початок встановлення...");
                Log("=== ПОЧАТОК ВСТАНОВЛЕННЯ МОДІВ ===");
                Log("Шлях до гри: " + gamePath);
                Log("Цільова версія гри: " + detectedGameVersion);

                string backupDir = "";
                if (doBackup)
                {
                    string backupsRoot = Path.Combine(gamePath, ".backups");
                    if (Directory.Exists(backupsRoot))
                    {
                        try
                        {
                            string[] oldBackups = Directory.GetDirectories(backupsRoot, "modpack_*");
                            foreach (string oldBkp in oldBackups)
                            {
                                try
                                {
                                    Directory.Delete(oldBkp, true);
                                    Log("Видалено попередню резервну копію: " + Path.GetFileName(oldBkp));
                                }
                                catch (Exception ex)
                                {
                                    Log("Не вдалося видалити старий бекап " + Path.GetFileName(oldBkp) + ": " + ex.Message);
                                }
                            }
                        }
                        catch { }
                    }

                    backupDir = Path.Combine(backupsRoot, "modpack_" + DateTime.Now.ToString("yyyyMMdd_HHmmss"));
                    Directory.CreateDirectory(backupDir);
                    Log("Папка резервного копіювання: " + backupDir);
                }

                int totalSteps = mods.Count * 2;
                int currentStep = 0;

                foreach (var mod in mods)
                {
                    UpdateStatus("Обробка: " + mod.title);

                    if (cleanOld)
                    {
                        CleanModOldVersions(gamePath, mod, backupDir);
                    }

                    currentStep++;
                    UpdateProgress((int)((currentStep / (double)totalSteps) * 100));

                    InstallModFiles(gamePath, mod, backupDir);

                    currentStep++;
                    UpdateProgress((int)((currentStep / (double)totalSteps) * 100));
                }

                if (!string.IsNullOrEmpty(backupDir) && Directory.Exists(backupDir))
                {
                    try
                    {
                        if (Directory.GetFiles(backupDir, "*", SearchOption.AllDirectories).Length == 0)
                        {
                            Directory.Delete(backupDir, true);
                        }
                    }
                    catch { }
                }

                if (installLauncher)
                    InstallLauncherAndShortcuts(gamePath, hijackShortcuts);

                UpdateProgress(100);
                UpdateStatus("Встановлення успішно завершено!");
                Log("=== УСПІШНО! ВСІ ВИБРАНІ МОДИ ВСТАНОВЛЕНО ===");

                this.Invoke(new Action(() => {
                    btnInstall.Enabled = true;
                    btnBrowse.Enabled = true;
                    btnSelectAll.Enabled = true;
                    btnDeselectAll.Enabled = true;
                    chkListMods.Enabled = true;
                    btnLaunchGame.Enabled = true;
                    MessageBox.Show(
                        string.Format("Моди успішно встановлені у World of Tanks!\nВстановлено модифікацій: {0}\nВерсія гри: {1}", mods.Count, detectedGameVersion),
                        "Встановлення завершено",
                        MessageBoxButtons.OK,
                        MessageBoxIcon.Information
                    );
                }));
            }
            catch (Exception ex)
            {
                Log("КРИТИЧНА ПОМИЛКА: " + ex.Message);
                UpdateStatus("Помилка під час встановлення.");
                this.Invoke(new Action(() => {
                    btnInstall.Enabled = true;
                    btnBrowse.Enabled = true;
                    btnSelectAll.Enabled = true;
                    btnDeselectAll.Enabled = true;
                    chkListMods.Enabled = true;
                    MessageBox.Show("Під час встановлення виникла помилка:\n" + ex.Message, "Помилка", MessageBoxButtons.OK, MessageBoxIcon.Error);
                }));
            }
        }

        internal void CleanModOldVersions(string gamePath, ModItem mod, string backupDir)
        {
            if (mod.clean_patterns != null)
            {
                string targetVerDir = Path.Combine(gamePath, "mods", detectedGameVersion);
                if (Directory.Exists(targetVerDir))
                {
                    foreach (var pObj in mod.clean_patterns)
                    {
                        string pat = pObj.ToString();
                        CleanByPattern(targetVerDir, pat, backupDir, gamePath);
                    }
                }

                string modsBase = Path.Combine(gamePath, "mods");
                if (Directory.Exists(modsBase))
                {
                    foreach (var vDir in Directory.GetDirectories(modsBase))
                    {
                        string vName = Path.GetFileName(vDir);
                        if (Regex.IsMatch(vName, @"^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$") && vName != detectedGameVersion)
                        {
                            foreach (var pObj in mod.clean_patterns)
                            {
                                CleanByPattern(vDir, pObj.ToString(), backupDir, gamePath);
                            }
                        }
                    }
                }
            }

            if (mod.clean_res_mods != null)
            {
                string resBase = Path.Combine(gamePath, "res_mods");
                var verDirs = new List<string>();
                string targetResVerDir = Path.Combine(resBase, detectedGameVersion);
                if (Directory.Exists(targetResVerDir)) verDirs.Add(targetResVerDir);
                if (Directory.Exists(resBase))
                {
                    foreach (var vDir in Directory.GetDirectories(resBase))
                    {
                        string vName = Path.GetFileName(vDir);
                        if (Regex.IsMatch(vName, @"^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$") && !verDirs.Contains(vDir))
                        {
                            verDirs.Add(vDir);
                        }
                    }
                }

                foreach (var resVerDir in verDirs)
                {
                    string vName = Path.GetFileName(resVerDir);
                    foreach (var rObj in mod.clean_res_mods)
                    {
                        string rel = rObj.ToString();
                        string fullPath = Path.Combine(resVerDir, rel);
                        if (File.Exists(fullPath))
                        {
                            try
                            {
                                if (!string.IsNullOrEmpty(backupDir))
                                {
                                    string bkp = Path.Combine(backupDir, "res_mods", vName, rel);
                                    Directory.CreateDirectory(Path.GetDirectoryName(bkp));
                                    File.Copy(fullPath, bkp, true);
                                }
                                File.Delete(fullPath);
                                Log("[Очищення res_mods] Видалено: " + vName + "/" + rel);
                            }
                            catch (Exception ex)
                            {
                                Log("[Очищення res_mods] Не вдалося видалити: " + rel + " (" + ex.Message + ")");
                            }
                        }
                        else if (Directory.Exists(fullPath))
                        {
                            try
                            {
                                Directory.Delete(fullPath, true);
                                Log("[Очищення res_mods] Видалено теку: " + vName + "/" + rel);
                            }
                            catch { }
                        }
                    }
                }
            }
        }

        private void CleanByPattern(string baseDir, string pattern, string backupDir, string gamePath)
        {
            string dirToSearch = baseDir;
            string searchPattern = pattern;

            if (pattern.Contains("/") || pattern.Contains("\\"))
            {
                string sub = Path.GetDirectoryName(pattern);
                dirToSearch = Path.Combine(baseDir, sub);
                searchPattern = Path.GetFileName(pattern);
            }

            if (Directory.Exists(dirToSearch))
            {
                try
                {
                    var list = new List<string>(Directory.GetFiles(dirToSearch, searchPattern));
                    if (searchPattern.EndsWith(".wotmod", StringComparison.OrdinalIgnoreCase))
                    {
                        list.AddRange(Directory.GetFiles(dirToSearch, searchPattern + ".new"));
                        list.AddRange(Directory.GetFiles(dirToSearch, searchPattern + ".tmp"));
                    }
                    var files = list.ToArray();
                    foreach (var f in files)
                    {
                        try
                        {
                            if (!string.IsNullOrEmpty(backupDir) && !string.IsNullOrEmpty(gamePath) && File.Exists(f))
                            {
                                string rel = f.StartsWith(gamePath, StringComparison.OrdinalIgnoreCase)
                                    ? f.Substring(gamePath.Length).TrimStart('\\', '/')
                                    : Path.GetFileName(f);
                                string bkp = Path.Combine(backupDir, rel);
                                Directory.CreateDirectory(Path.GetDirectoryName(bkp));
                                File.Copy(f, bkp, true);
                            }
                            File.Delete(f);
                            Log("[Очищення] Видалено стару версію: " + Path.GetFileName(f));
                        }
                        catch (Exception ex)
                        {
                            Log("[Очищення] Не вдалося видалити: " + Path.GetFileName(f) + " (" + ex.Message + ")");
                        }
                    }
                }
                catch { }
            }
        }

        private void InstallModFiles(string gamePath, ModItem mod, string backupDir)
        {
            string srcRoot = Path.Combine(mod.FolderPath, "game_files");
            if (!Directory.Exists(srcRoot))
            {
                Log("УВАГА: Не знайдено game_files для " + mod.title);
                return;
            }

            var allFiles = Directory.GetFiles(srcRoot, "*", SearchOption.AllDirectories);
            foreach (var file in allFiles)
            {
                string rel = file.Substring(srcRoot.Length).TrimStart(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
                rel = rel.Replace("_VERSION_", detectedGameVersion);

                string destPath = Path.Combine(gamePath, rel);
                string destDir = Path.GetDirectoryName(destPath);
                if (!Directory.Exists(destDir))
                {
                    Directory.CreateDirectory(destDir);
                }

                if (!string.IsNullOrEmpty(backupDir) && File.Exists(destPath))
                {
                    string bkpFile = Path.Combine(backupDir, rel);
                    string bkpFileDir = Path.GetDirectoryName(bkpFile);
                    if (!Directory.Exists(bkpFileDir)) Directory.CreateDirectory(bkpFileDir);
                    File.Copy(destPath, bkpFile, true);
                }

                bool isNew = !File.Exists(destPath);
                try
                {
                    File.Copy(file, destPath, true);
                    if (isNew && !string.IsNullOrEmpty(backupDir))
                        File.AppendAllText(Path.Combine(backupDir, NewFilesManifest), rel + Environment.NewLine, System.Text.Encoding.UTF8);
                    Log(string.Format("[Встановлено] {0} -> {1}", mod.title, rel));
                }
                catch (Exception ex)
                {
                    Log(string.Format("[Помилка запису] {0}: {1}", rel, ex.Message));
                }
            }
        }

        internal static string GetLauncherInstallDir()
        {
            return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "WotModpack");
        }

        private string LocateStagedLauncherExe()
        {
            string exeDir = AppDomain.CurrentDomain.BaseDirectory;
            var candidates = new List<string>
            {
                Path.Combine(exeDir, "Launcher", "WotModLauncher.exe"),
                Path.Combine(exeDir, "staging_modpack", "Launcher", "WotModLauncher.exe"),
                Path.Combine(exeDir, "WoT modpack by Niedvin", "Launcher", "WotModLauncher.exe")
            };
            string payload = ExtractEmbeddedPayload();
            if (payload != null)
                candidates.Add(Path.Combine(payload, "Launcher", "WotModLauncher.exe"));
            foreach (string c in candidates)
                if (File.Exists(c)) return c;
            return null;
        }

        private void InstallLauncherAndShortcuts(string gamePath, bool hijackStandard)
        {
            string srcExe = LocateStagedLauncherExe();
            if (srcExe == null)
            {
                Log("[Лаунчер] Файл Launcher\\WotModLauncher.exe не знайдено в папці інсталятора.");
                return;
            }

            string targetDir = GetLauncherInstallDir();
            Directory.CreateDirectory(targetDir);
            string dstExe = Path.Combine(targetDir, "WotModLauncher.exe");
            File.Copy(srcExe, dstExe, true);

            var ser = new JavaScriptSerializer();
            string cfgJson = ser.Serialize(new Dictionary<string, object>
            {
                { "game_path", gamePath },
                { "hijack_shortcuts", hijackStandard }
            });
            File.WriteAllText(Path.Combine(targetDir, "launcher.json"), cfgJson, System.Text.Encoding.UTF8);
            Log("[Лаунчер] Встановлено у: " + dstExe);

            string iconFile = Path.Combine(gamePath, "game_metadata", "game.ico");
            if (!File.Exists(iconFile)) iconFile = Path.Combine(gamePath, "WorldOfTanks.exe");

            string desktopDir = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
            string modShortcut = Path.Combine(desktopDir, "World of Tanks EU (модпак).lnk");
            CreateOrUpdateShortcut(modShortcut, dstExe, "", gamePath, iconFile + ",0", "Запуск World of Tanks з автооновленням модів");
            Log("[Лаунчер] Створено ярлик: World of Tanks EU (модпак).lnk");

            if (hijackStandard)
            {
                string bkpDir = Path.Combine(targetDir, "shortcuts_backup");
                Directory.CreateDirectory(bkpDir);

                string[] stdShortcuts = new string[]
                {
                    Path.Combine(desktopDir, "World of Tanks EU.lnk"),
                    Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), @"Microsoft\Windows\Start Menu\Programs\Wargaming.net\World_of_Tanks_EU\World of Tanks EU.lnk")
                };

                foreach (string lnk in stdShortcuts)
                {
                    if (!File.Exists(lnk)) continue;
                    string prefix = lnk.IndexOf("Start Menu", StringComparison.OrdinalIgnoreCase) >= 0 ? "startmenu_" : "desktop_";
                    string bkpPath = Path.Combine(bkpDir, prefix + Path.GetFileName(lnk));
                    if (!File.Exists(bkpPath))
                        File.Copy(lnk, bkpPath, false);

                    CreateOrUpdateShortcut(lnk, dstExe, "", gamePath, iconFile + ",0", "World of Tanks EU");
                    Log("[Лаунчер] Вбудовано у стандартний ярлик: " + Path.GetFileName(lnk));
                }
            }
        }

        internal static void CreateOrUpdateShortcut(string lnkPath, string targetPath, string args, string workDir, string iconLocation, string description)
        {
            Type shellType = Type.GetTypeFromProgID("WScript.Shell");
            if (shellType == null) return;
            object shell = Activator.CreateInstance(shellType);
            object sc = shellType.InvokeMember("CreateShortcut", BindingFlags.InvokeMethod, null, shell, new object[] { lnkPath });
            sc.GetType().InvokeMember("TargetPath", BindingFlags.SetProperty, null, sc, new object[] { targetPath });
            sc.GetType().InvokeMember("Arguments", BindingFlags.SetProperty, null, sc, new object[] { args ?? "" });
            sc.GetType().InvokeMember("WorkingDirectory", BindingFlags.SetProperty, null, sc, new object[] { workDir ?? "" });
            if (!string.IsNullOrEmpty(iconLocation))
                sc.GetType().InvokeMember("IconLocation", BindingFlags.SetProperty, null, sc, new object[] { iconLocation });
            if (!string.IsNullOrEmpty(description))
                sc.GetType().InvokeMember("Description", BindingFlags.SetProperty, null, sc, new object[] { description });
            sc.GetType().InvokeMember("Save", BindingFlags.InvokeMethod, null, sc, null);
        }

        public static void UninstallLauncherAndRestoreShortcuts(string gamePath, Action<string> logger)
        {
            string targetDir = GetLauncherInstallDir();
            string desktopDir = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
            string startMenuLnk = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), @"Microsoft\Windows\Start Menu\Programs\Wargaming.net\World_of_Tanks_EU\World of Tanks EU.lnk");
            string desktopLnk = Path.Combine(desktopDir, "World of Tanks EU.lnk");

            string bkpDir = Path.Combine(targetDir, "shortcuts_backup");
            string bkpDesktop = Path.Combine(bkpDir, "desktop_World of Tanks EU.lnk");
            string bkpStart = Path.Combine(bkpDir, "startmenu_World of Tanks EU.lnk");

            if (File.Exists(bkpDesktop))
            {
                File.Copy(bkpDesktop, desktopLnk, true);
                logger("[Видалення] Відновлено оригінальний ярлик на робочому столі.");
            }
            else if (File.Exists(desktopLnk) && !string.IsNullOrEmpty(gamePath))
            {
                string wgcApi = Path.Combine(gamePath, "wgc_api.exe");
                string ico = Path.Combine(gamePath, "game_metadata", "game.ico");
                if (File.Exists(wgcApi))
                    CreateOrUpdateShortcut(desktopLnk, wgcApi, "--open", gamePath, ico + ",0", "World of Tanks EU");
            }

            if (File.Exists(bkpStart))
            {
                Directory.CreateDirectory(Path.GetDirectoryName(startMenuLnk));
                File.Copy(bkpStart, startMenuLnk, true);
                logger("[Видалення] Відновлено оригінальний ярлик у меню Пуск.");
            }

            string modShortcut = Path.Combine(desktopDir, "World of Tanks EU (модпак).lnk");
            if (File.Exists(modShortcut))
            {
                File.Delete(modShortcut);
                logger("[Видалення] Прибрано ярлик World of Tanks EU (модпак).lnk");
            }

            if (Directory.Exists(targetDir))
            {
                try
                {
                    Directory.Delete(targetDir, true);
                    logger("[Видалення] Видалено папку лаунчера: " + targetDir);
                }
                catch (Exception ex)
                {
                    logger("[Видалення] Не вдалося повністю видалити папку лаунчера: " + ex.Message);
                }
            }
        }

        private WebClient NewWebClient()
        {
            var wc = new WebClient();
            wc.Headers[HttpRequestHeader.UserAgent] = "wot-modpack-installer";
            wc.Encoding = System.Text.Encoding.UTF8;
            return wc;
        }

        private static Version ParseVersion(string s)
        {
            Version v;
            return Version.TryParse(s.TrimStart('v', 'V'), out v) ? v : null;
        }

        private string[] GetLatestRelease(UpdateSource src)
        {
            var json = new JavaScriptSerializer();
            var assets = new List<string[]>();
            using (var wc = NewWebClient())
            {
                if (src.kind == "github")
                {
                    var rel = (Dictionary<string, object>)json.DeserializeObject(
                        wc.DownloadString("https://api.github.com/repos/" + src.repo + "/releases/latest"));
                    foreach (Dictionary<string, object> a in (object[])rel["assets"])
                        assets.Add(new[] { (string)a["name"], (string)a["browser_download_url"] });
                }
                else
                {
                    string enc = Uri.EscapeDataString(src.repo);
                    var proj = (Dictionary<string, object>)json.DeserializeObject(
                        wc.DownloadString("https://gitlab.com/api/v4/projects/" + enc));
                    var rels = (object[])json.DeserializeObject(
                        wc.DownloadString("https://gitlab.com/api/v4/projects/" + enc + "/releases?per_page=1"));
                    if (rels.Length == 0) return null;
                    var rel = (Dictionary<string, object>)rels[0];
                    string desc = rel.ContainsKey("description") ? (rel["description"] as string ?? "") : "";
                    foreach (Match m in Regex.Matches(desc, @"\((/uploads/[0-9a-f]+/([^)\s]+\.wotmod))\)"))
                        assets.Add(new[] { m.Groups[2].Value, "https://gitlab.com/-/project/" + proj["id"] + m.Groups[1].Value });
                }
            }
            string rx = "^" + Regex.Escape(src.id) + @"_(.+)\.wotmod$";
            foreach (var a in assets)
            {
                string name = Uri.UnescapeDataString(a[0]);
                if (Regex.IsMatch(name, rx)) return new[] { name, a[1] };
            }
            return null;
        }

        private static bool IsWotmodWithId(string path, string id)
        {
            if (new FileInfo(path).Length == 0) return false;
            using (var zip = ZipFile.OpenRead(path))
            {
                var meta = zip.GetEntry("meta.xml");
                if (meta == null) return false;
                using (var sr = new StreamReader(meta.Open()))
                    return Regex.IsMatch(sr.ReadToEnd(), @"<id>\s*" + Regex.Escape(id) + @"\s*</id>");
            }
        }

        private void PrefetchUpdates()
        {
            try
            {
                foreach (var mod in loadedMods)
                {
                    if (mod.updates == null) continue;
                    foreach (var src in mod.updates)
                        PrefetchSource(mod, src);
                }
            }
            catch (Exception ex)
            {
                Log("[Оновлення] Помилка перевірки: " + ex.Message);
            }
            finally
            {
                prefetchDone.Set();
            }
        }

        private void PrefetchSource(ModItem mod, UpdateSource src)
        {
            try
            {
                string rx = "^" + Regex.Escape(src.id) + @"_(.+)\.wotmod$";
                string filesRoot = Path.Combine(mod.FolderPath, "game_files");
                if (!Directory.Exists(filesRoot)) return;
                string cur = null;
                foreach (var f in Directory.GetFiles(filesRoot, src.id + "_*.wotmod", SearchOption.AllDirectories))
                    if (Regex.IsMatch(Path.GetFileName(f), rx)) { cur = f; break; }
                if (cur == null) return;

                Version curV = ParseVersion(Regex.Match(Path.GetFileName(cur), rx).Groups[1].Value);
                string[] latest = GetLatestRelease(src);
                if (latest == null) return;
                Version newV = ParseVersion(Regex.Match(latest[0], rx).Groups[1].Value);
                if (newV == null || (curV != null && newV <= curV))
                {
                    Log(string.Format("[Оновлення] {0} {1} - актуальна", src.id, curV));
                    return;
                }

                string tmp = Path.Combine(Path.GetTempPath(), "wot-modpack-" + Guid.NewGuid().ToString("N") + ".wotmod");
                using (var wc = NewWebClient()) wc.DownloadFile(latest[1], tmp);
                if (!IsWotmodWithId(tmp, src.id))
                {
                    File.Delete(tmp);
                    Log("[Оновлення] " + src.id + ": завантажений файл пошкоджений, лишаю версію з архіву");
                    return;
                }
                string target = Path.Combine(Path.GetDirectoryName(cur), latest[0]);
                if (File.Exists(target)) File.Delete(target);
                File.Move(tmp, target);
                File.Delete(cur);
                if (mod.updates.Length == 1) mod.version = newV.ToString();
                Log(string.Format("[Оновлення] {0}: {1} -> {2}", src.id, curV, newV));
            }
            catch (Exception ex)
            {
                Log("[Оновлення] " + src.id + ": не вдалося оновити (" + ex.Message + "), лишаю версію з архіву");
            }
        }

        private const string NewFilesManifest = "_new_files.txt";

        private void BtnRollback_Click(object sender, EventArgs e)
        {
            string gamePath = txtGamePath.Text.Trim();
            if (!IsValidWotDir(gamePath))
            {
                MessageBox.Show("Спершу вкажіть папку World of Tanks.", "Відкат", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }
            string root = Path.Combine(gamePath, ".backups");
            string[] dirs = Directory.Exists(root) ? Directory.GetDirectories(root, "modpack_*") : new string[0];
            if (dirs.Length == 0)
            {
                MessageBox.Show("Бекапу модпаку не знайдено.", "Відкат", MessageBoxButtons.OK, MessageBoxIcon.Information);
                return;
            }
            Array.Sort(dirs);
            string bkp = dirs[dirs.Length - 1];
            if (Process.GetProcessesByName("WorldOfTanks").Length > 0)
            {
                MessageBox.Show("Закрийте World of Tanks перед відкатом.", "Відкат", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }
            if (MessageBox.Show("Повернути файли гри до стану перед встановленням (" + Path.GetFileName(bkp) + ")?",
                    "Відкат", MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes)
                return;

            int removed = 0, restored = 0;
            try
            {
                string manifest = Path.Combine(bkp, NewFilesManifest);
                if (File.Exists(manifest))
                {
                    foreach (string line in File.ReadAllLines(manifest, System.Text.Encoding.UTF8))
                    {
                        string rel = line.Trim();
                        if (rel.Length == 0) continue;
                        string f = Path.Combine(gamePath, rel);
                        if (File.Exists(f)) { File.Delete(f); removed++; }
                    }
                }
                foreach (string f in Directory.GetFiles(bkp, "*", SearchOption.AllDirectories))
                {
                    if (string.Equals(f, manifest, StringComparison.OrdinalIgnoreCase)) continue;
                    string rel = f.Substring(bkp.Length).TrimStart('\\', '/');
                    string dst = Path.Combine(gamePath, rel);
                    Directory.CreateDirectory(Path.GetDirectoryName(dst));
                    File.Copy(f, dst, true);
                    restored++;
                }
                Log(string.Format("[Відкат] {0}: прибрано {1}, повернуто {2} файлів", Path.GetFileName(bkp), removed, restored));
                MessageBox.Show(string.Format("Відкат завершено.\nПрибрано файлів модпаку: {0}\nПовернуто файлів: {1}", removed, restored),
                    "Відкат", MessageBoxButtons.OK, MessageBoxIcon.Information);
            }
            catch (Exception ex)
            {
                Log("[Відкат] Помилка: " + ex.Message);
                MessageBox.Show("Помилка відкату: " + ex.Message, "Відкат", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }

        private void BtnUninstall_Click(object sender, EventArgs e)
        {
            string gamePath = txtGamePath.Text.Trim();
            if (!IsValidWotDir(gamePath))
            {
                MessageBox.Show("Спершу вкажіть папку World of Tanks.", "Видалення", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }
            if (Process.GetProcessesByName("WorldOfTanks").Length > 0 || Process.GetProcessesByName("WorldOfTanks32").Length > 0)
            {
                MessageBox.Show("Закрийте World of Tanks перед видаленням модів.", "Видалення", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }

            using (UninstallForm dlg = new UninstallForm(this, gamePath, loadedMods, detectedGameVersion))
            {
                if (!dlg.HasItems)
                {
                    MessageBox.Show("Не знайдено жодного компонента модпаку для видалення.", "Видалення", MessageBoxButtons.OK, MessageBoxIcon.Information);
                    return;
                }
                dlg.ShowDialog(this);
            }
        }

        private void BtnLaunchGame_Click(object sender, EventArgs e)
        {
            string gamePath = txtGamePath.Text.Trim();
            string installedLauncher = Path.Combine(GetLauncherInstallDir(), "WotModLauncher.exe");
            if (File.Exists(installedLauncher))
            {
                try
                {
                    ProcessStartInfo psiL = new ProcessStartInfo();
                    psiL.FileName = installedLauncher;
                    psiL.WorkingDirectory = Path.GetDirectoryName(installedLauncher);
                    Process.Start(psiL);
                    this.Close();
                    return;
                }
                catch { }
            }

            string exe = Path.Combine(gamePath, "WorldOfTanks.exe");
            if (!File.Exists(exe))
            {
                exe = Path.Combine(gamePath, "win64", "WorldOfTanks.exe");
            }

            if (File.Exists(exe))
            {
                try
                {
                    ProcessStartInfo psi = new ProcessStartInfo();
                    psi.FileName = exe;
                    psi.WorkingDirectory = gamePath;
                    Process.Start(psi);
                    this.Close();
                }
                catch (Exception ex)
                {
                    MessageBox.Show("Не вдалося запустити гру: " + ex.Message, "Помилка", MessageBoxButtons.OK, MessageBoxIcon.Error);
                }
            }
            else
            {
                MessageBox.Show("Файл WorldOfTanks.exe не знайдено в папці гри.", "Помилка", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }

        private void UpdateStatus(string text)
        {
            if (this.InvokeRequired)
            {
                this.Invoke(new Action<string>(UpdateStatus), text);
                return;
            }
            lblStatus.Text = text;
        }

        private void UpdateProgress(int value)
        {
            if (this.InvokeRequired)
            {
                this.Invoke(new Action<int>(UpdateProgress), value);
                return;
            }
            prgInstall.Value = Math.Min(100, Math.Max(0, value));
        }

        internal void Log(string msg)
        {
            if (this.InvokeRequired)
            {
                this.Invoke(new Action<string>(Log), msg);
                return;
            }
            txtLog.AppendText(string.Format("[{0}] {1}\r\n", DateTime.Now.ToString("HH:mm:ss"), msg));
        }

        [STAThread]
        public static void Main(string[] args)
        {
            ServicePointManager.SecurityProtocol = (SecurityProtocolType)3072;
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            if (args != null && args.Length > 0 && Array.IndexOf(args, "--selftest") >= 0)
            {
                Environment.Exit(RunSelfTest());
                return;
            }
            Application.Run(new MainForm());
        }

        private static int RunSelfTest()
        {
            string report = Path.Combine(Path.GetTempPath(), "wot_setup_selftest.txt");
            try
            {
                string dir = ExtractEmbeddedPayload();
                if (dir == null)
                {
                    File.WriteAllText(report, "FAIL: embedded payload resource not found");
                    return 1;
                }
                string[] modDirs = Directory.GetDirectories(Path.Combine(dir, "Mods"));
                bool launcher = File.Exists(Path.Combine(dir, "Launcher", "WotModLauncher.exe"));
                string resolved = ResolveModsRoot();
                bool resolvedValid = resolved != null && IsValidModsRoot(resolved);
                File.WriteAllText(report, string.Format(
                    "OK payload_mods={0} launcher={1} resolved={2} resolved_valid={3}",
                    modDirs.Length, launcher, resolved ?? "null", resolvedValid));
                return (modDirs.Length > 0 && launcher && resolvedValid) ? 0 : 2;
            }
            catch (Exception ex)
            {
                File.WriteAllText(report, "FAIL: " + ex.Message);
                return 3;
            }
        }

        internal static string ExtractEmbeddedPayload()
        {
            if (payloadDir != null) return payloadDir;
            try
            {
                string resName = null;
                foreach (string n in Assembly.GetExecutingAssembly().GetManifestResourceNames())
                    if (n.EndsWith("payload.zip", StringComparison.OrdinalIgnoreCase)) { resName = n; break; }
                if (resName == null) return null;

                string dir = Path.Combine(GetLauncherInstallDir(), "payload");
                if (Directory.Exists(dir)) Directory.Delete(dir, true);
                Directory.CreateDirectory(dir);

                using (Stream s = Assembly.GetExecutingAssembly().GetManifestResourceStream(resName))
                using (ZipArchive zip = new ZipArchive(s, ZipArchiveMode.Read))
                {
                    foreach (ZipArchiveEntry entry in zip.Entries)
                    {
                        if (entry.FullName.Contains("..")) continue;
                        string dest = Path.Combine(dir, entry.FullName);
                        Directory.CreateDirectory(Path.GetDirectoryName(dest));
                        using (Stream es = entry.Open())
                        using (FileStream fs = File.Create(dest))
                            es.CopyTo(fs);
                    }
                }
                payloadDir = dir;
                return dir;
            }
            catch { return null; }
        }
    }

    public class UninstallForm : Form
    {
        private class UninstallItem
        {
            public string Display;
            public ModItem Mod;
            public bool IsLauncher;
            public bool IsConfigs;
        }

        private readonly MainForm owner;
        private readonly string gamePath;
        private readonly string gameVersion;
        private readonly List<UninstallItem> items = new List<UninstallItem>();
        private CheckedListBox chkList;

        public bool HasItems
        {
            get { return items.Count > 0; }
        }

        public UninstallForm(MainForm owner, string gamePath, List<ModItem> loadedMods, string gameVersion)
        {
            this.owner = owner;
            this.gamePath = gamePath;
            this.gameVersion = gameVersion;
            BuildItems(loadedMods);
            InitializeComponent();
        }

        private void BuildItems(List<ModItem> loadedMods)
        {
            string desktopDir = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
            string launcherExe = Path.Combine(MainForm.GetLauncherInstallDir(), "WotModLauncher.exe");
            string modpackLnk = Path.Combine(desktopDir, "World of Tanks EU (модпак).lnk");
            if (File.Exists(launcherExe) || File.Exists(modpackLnk))
                items.Add(new UninstallItem { Display = "[Лаунчер] Автооновлення модів + відновлення оригінальних ярликів гри", IsLauncher = true });

            string verDir = Path.Combine(gamePath, "mods", gameVersion);
            foreach (ModItem mod in loadedMods)
            {
                if (mod.clean_patterns == null) continue;
                bool installed = false;
                foreach (object pObj in mod.clean_patterns)
                {
                    string pat = pObj.ToString();
                    string dir = verDir;
                    string filePat = pat;
                    if (pat.Contains("/") || pat.Contains("\\"))
                    {
                        dir = Path.Combine(verDir, Path.GetDirectoryName(pat));
                        filePat = Path.GetFileName(pat);
                    }
                    if (Directory.Exists(dir) && Directory.GetFiles(dir, filePat).Length > 0)
                    {
                        installed = true;
                        break;
                    }
                }
                if (installed)
                    items.Add(new UninstallItem { Display = string.Format("{0} (v{1})", mod.title, mod.version), Mod = mod });
            }

            if (Directory.Exists(Path.Combine(gamePath, "mods", "configs")))
                items.Add(new UninstallItem { Display = @"[Налаштування] Збережені конфіги модів (mods\configs\...)", IsConfigs = true });
        }

        private void InitializeComponent()
        {
            this.Text = "Видалення компонентів модпаку";
            this.ClientSize = new Size(660, 420);
            this.StartPosition = FormStartPosition.CenterParent;
            this.FormBorderStyle = FormBorderStyle.FixedSingle;
            this.MaximizeBox = false;
            this.Font = new Font("Segoe UI", 9F, FontStyle.Regular, GraphicsUnit.Point);
            this.BackColor = Color.FromArgb(20, 25, 38);

            Label lblHint = new Label();
            lblHint.Text = "Позначте компоненти, які потрібно видалити:";
            lblHint.Location = new Point(15, 12);
            lblHint.AutoSize = true;
            lblHint.ForeColor = Color.FromArgb(233, 237, 245);

            chkList = new CheckedListBox();
            chkList.Location = new Point(15, 38);
            chkList.Size = new Size(630, 310);
            chkList.CheckOnClick = true;
            chkList.BorderStyle = BorderStyle.FixedSingle;

            for (int i = 0; i < items.Count; i++)
            {
                int idx = chkList.Items.Add(items[i]);
                chkList.SetItemChecked(idx, !items[i].IsConfigs);
            }

            Button btnSelectAll = MainForm.MakeButton("Вибрати все", Color.FromArgb(39, 48, 67), Color.FromArgb(233, 237, 245), false);
            btnSelectAll.Location = new Point(15, 360);
            btnSelectAll.Size = new Size(120, 32);
            btnSelectAll.Click += (s, e) => { for (int i = 0; i < chkList.Items.Count; i++) chkList.SetItemChecked(i, true); };

            Button btnDeselectAll = MainForm.MakeButton("Зняти все", Color.FromArgb(39, 48, 67), Color.FromArgb(233, 237, 245), false);
            btnDeselectAll.Location = new Point(145, 360);
            btnDeselectAll.Size = new Size(120, 32);
            btnDeselectAll.Click += (s, e) => { for (int i = 0; i < chkList.Items.Count; i++) chkList.SetItemChecked(i, false); };

            Button btnDelete = MainForm.MakeButton("Видалити вибране", Color.FromArgb(120, 45, 45), Color.White, true);
            btnDelete.Location = new Point(360, 360);
            btnDelete.Size = new Size(150, 32);
            btnDelete.Click += BtnDelete_Click;

            Button btnCancel = MainForm.MakeButton("Скасувати", Color.FromArgb(39, 48, 67), Color.FromArgb(150, 162, 186), false);
            btnCancel.Location = new Point(525, 360);
            btnCancel.Size = new Size(120, 32);
            btnCancel.Click += (s, e) => Close();

            this.Controls.Add(lblHint);
            this.Controls.Add(chkList);
            this.Controls.Add(btnSelectAll);
            this.Controls.Add(btnDeselectAll);
            this.Controls.Add(btnDelete);
            this.Controls.Add(btnCancel);
        }

        private void BtnDelete_Click(object sender, EventArgs e)
        {
            var selected = new List<UninstallItem>();
            for (int i = 0; i < chkList.Items.Count; i++)
                if (chkList.GetItemChecked(i)) selected.Add((UninstallItem)chkList.Items[i]);

            if (selected.Count == 0)
            {
                MessageBox.Show("Не вибрано жодного компонента.", "Видалення", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }

            DialogResult confirm = MessageBox.Show(
                "Видалити вибрані компоненти?\nПеред видаленням буде створено резервну копію у .backups.",
                "Підтвердження", MessageBoxButtons.YesNo, MessageBoxIcon.Question);
            if (confirm != DialogResult.Yes) return;

            string backupDir = Path.Combine(gamePath, ".backups", "uninstall_" + DateTime.Now.ToString("yyyyMMdd_HHmmss"));
            Directory.CreateDirectory(backupDir);
            int removed = 0;

            foreach (UninstallItem item in selected)
            {
                try
                {
                    if (item.IsLauncher)
                    {
                        MainForm.UninstallLauncherAndRestoreShortcuts(gamePath, owner.Log);
                        removed++;
                    }
                    else if (item.Mod != null)
                    {
                        owner.CleanModOldVersions(gamePath, item.Mod, backupDir);
                        owner.Log("[Видалення] Мод видалено: " + item.Mod.title);
                        removed++;
                    }
                    else if (item.IsConfigs)
                    {
                        BackupAndCleanConfigs(backupDir);
                        removed++;
                    }
                }
                catch (Exception ex)
                {
                    owner.Log("[Видалення] Помилка: " + ex.Message);
                }
            }

            MessageBox.Show(
                string.Format("Видалено компонентів: {0}\nРезервна копія: {1}", removed, backupDir),
                "Видалення завершено", MessageBoxButtons.OK, MessageBoxIcon.Information);
            DialogResult = DialogResult.OK;
            Close();
        }

        private void BackupAndCleanConfigs(string backupDir)
        {
            string src = Path.Combine(gamePath, "mods", "configs");
            if (!Directory.Exists(src)) return;

            string bkp = Path.Combine(backupDir, "configs");
            CopyDirectory(src, bkp);

            string[] configDirs = new string[]
            {
                "server_online", "platoon_autostart", "armor_flashlight",
                "spectator_teammate_hud", "background_fps_limiter", "research_button"
            };
            foreach (string sub in configDirs)
            {
                string dir = Path.Combine(src, sub);
                if (Directory.Exists(dir))
                {
                    Directory.Delete(dir, true);
                    owner.Log(@"[Видалення] Видалено конфіги: mods\configs\" + sub);
                }
            }
        }

        private static void CopyDirectory(string srcDir, string dstDir)
        {
            Directory.CreateDirectory(dstDir);
            foreach (string file in Directory.GetFiles(srcDir))
                File.Copy(file, Path.Combine(dstDir, Path.GetFileName(file)), true);
            foreach (string dir in Directory.GetDirectories(srcDir))
                CopyDirectory(dir, Path.Combine(dstDir, Path.GetFileName(dir)));
        }
    }
}
