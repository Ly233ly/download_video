using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Net;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;
using Microsoft.Win32;

[assembly: AssemblyTitle("留底安装器")]
[assembly: AssemblyDescription("留底下载器一键安装程序")]
[assembly: AssemblyProduct("留底下载器")]
[assembly: AssemblyCompany("阿毅i")]
[assembly: AssemblyVersion("1.6.1.0")]
[assembly: AssemblyFileVersion("1.6.1.0")]

internal static class SetupProgram
{
    internal const string Version = "1.6.1";
    internal const string ProductName = "留底下载器";
    internal const string QuitEventName = @"Local\IdmEagleAutoImportQuit";
    internal const string DefaultIdmRegistry = @"Software\DownloadManager";
    internal const string DefaultStateRegistry = @"Software\IDMEagleAutoImport";
    internal const string DefaultUninstallRegistry = @"Software\Microsoft\Windows\CurrentVersion\Uninstall\IDMEagleAutoImport";

    [STAThread]
    private static int Main(string[] args)
    {
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);

        if (args.Any(value => value == "--test-install"))
        {
            return RunTestInstall();
        }
        if (args.Any(value => value == "--test-uninstall"))
        {
            return RunTestUninstall();
        }
        if (args.Any(value => value == "--test-update"))
        {
            return RunTestUpdate();
        }
        if (args.Any(value => value == "--update"))
        {
            return RunUpdate();
        }
        if (args.Any(value => value == "--install-silent"))
        {
            return RunSilentInstall();
        }
        int workerIndex = Array.IndexOf(args, "--uninstall-worker");
        if (workerIndex >= 0 && workerIndex + 1 < args.Length)
        {
            return RunUninstallWorker(args[workerIndex + 1]);
        }

        string executableName = Path.GetFileNameWithoutExtension(Application.ExecutablePath);
        bool uninstall = args.Any(value => value == "--uninstall")
            || executableName.IndexOf("卸载", StringComparison.OrdinalIgnoreCase) >= 0
            || executableName.IndexOf("uninstall", StringComparison.OrdinalIgnoreCase) >= 0;
        if (uninstall)
        {
            return BeginUninstall();
        }

        Application.Run(new InstallerForm());
        return 0;
    }

    private static int RunUpdate()
    {
        try
        {
            InstallerEngine.Install(false, delegate { }, true);
            return 0;
        }
        catch (Exception exception)
        {
            MessageBox.Show(
                exception.Message,
                "留底下载器更新",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error
            );
            return 1;
        }
    }

    private static int RunSilentInstall()
    {
        try
        {
            InstallerEngine.Install(false, delegate { }, false, false);
            return 0;
        }
        catch (Exception exception)
        {
            MessageBox.Show(
                "安装失败：" + exception.Message,
                "留底下载器",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error
            );
            return 1;
        }
    }

    private static int RunTestInstall()
    {
        try
        {
            InstallResult result = InstallerEngine.Install(true, delegate { });
            File.WriteAllText(
                Path.Combine(result.InstallDirectory, "install-test-result.txt"),
                result.IdmConfigured ? "OK" : "WARNING: " + result.Warning,
                new UTF8Encoding(false)
            );
            return 0;
        }
        catch (Exception exception)
        {
            string resultPath = Environment.GetEnvironmentVariable("IDM_EAGLE_TEST_RESULT") ?? "";
            if (!string.IsNullOrWhiteSpace(resultPath))
            {
                File.WriteAllText(resultPath, exception.ToString(), new UTF8Encoding(false));
            }
            return 1;
        }
    }

    private static int RunTestUninstall()
    {
        try
        {
            InstallerEngine.Uninstall(InstallerEngine.GetInstallDirectory(true), true);
            return 0;
        }
        catch (Exception exception)
        {
            string resultPath = Environment.GetEnvironmentVariable("IDM_EAGLE_TEST_RESULT") ?? "";
            if (!string.IsNullOrWhiteSpace(resultPath))
            {
                File.WriteAllText(resultPath, exception.ToString(), new UTF8Encoding(false));
            }
            return 1;
        }
    }

    private static int RunTestUpdate()
    {
        try
        {
            InstallerEngine.Install(true, delegate { }, true);
            return 0;
        }
        catch (Exception exception)
        {
            string resultPath = Environment.GetEnvironmentVariable("IDM_EAGLE_TEST_RESULT") ?? "";
            if (!string.IsNullOrWhiteSpace(resultPath))
            {
                File.WriteAllText(resultPath, exception.ToString(), new UTF8Encoding(false));
            }
            return 1;
        }
    }

    private static int BeginUninstall()
    {
        if (MessageBox.Show(
            "将移除助手并恢复安装前的 IDM 设置。下载的视频和 Eagle 中已有项目不会删除。是否继续？",
            "卸载留底下载器",
            MessageBoxButtons.YesNo,
            MessageBoxIcon.Question
        ) != DialogResult.Yes)
        {
            return 0;
        }

        string installDirectory = InstallerEngine.GetInstallDirectory(false);
        string temporary = Path.Combine(
            Path.GetTempPath(),
            "IDMEagleUninstall-" + Guid.NewGuid().ToString("N") + ".exe"
        );
        File.Copy(Application.ExecutablePath, temporary, true);
        Process.Start(new ProcessStartInfo
        {
            FileName = temporary,
            Arguments = "--uninstall-worker " + QuoteArgument(installDirectory),
            UseShellExecute = false,
            CreateNoWindow = true,
            WindowStyle = ProcessWindowStyle.Hidden
        });
        return 0;
    }

    private static int RunUninstallWorker(string installDirectory)
    {
        try
        {
            InstallerEngine.Uninstall(installDirectory);
            MessageBox.Show(
                "卸载完成。历史记录和网站规则已保留，重新安装后可以继续使用。",
                "留底下载器",
                MessageBoxButtons.OK,
                MessageBoxIcon.Information
            );
            MoveFileEx(Application.ExecutablePath, null, 0x4);
            return 0;
        }
        catch (Exception exception)
        {
            MessageBox.Show(
                "卸载未完成：" + exception.Message,
                "留底下载器",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error
            );
            return 1;
        }
    }

    internal static string QuoteArgument(string value)
    {
        return "\"" + value.Replace("\"", "\\\"") + "\"";
    }

    [System.Runtime.InteropServices.DllImport("kernel32.dll", CharSet = System.Runtime.InteropServices.CharSet.Unicode)]
    private static extern bool MoveFileEx(string existing, string replacement, int flags);
}

internal sealed class InstallerForm : Form
{
    private readonly Label status;
    private readonly Button installButton;
    private readonly Button closeButton;
    private readonly TextBox instructions;

    internal InstallerForm()
    {
        Text = "留底安装器";
        ClientSize = new Size(620, 410);
        MinimumSize = new Size(620, 410);
        MaximizeBox = false;
        StartPosition = FormStartPosition.CenterScreen;
        Font = new Font("Microsoft YaHei UI", 9F);
        Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);

        Label heading = new Label
        {
            Text = "留底下载器",
            Font = new Font("Microsoft YaHei UI", 18F, FontStyle.Bold),
            AutoSize = true,
            Location = new Point(28, 24)
        };
        Controls.Add(heading);

        Label description = new Label
        {
            Text = "自带运行环境，自动配置 IDM、创建快捷方式并启动助手。不会移动或删除下载文件。",
            AutoSize = false,
            Size = new Size(560, 44),
            Location = new Point(31, 72),
            ForeColor = Color.FromArgb(71, 85, 105)
        };
        Controls.Add(description);

        installButton = new Button
        {
            Text = "一键安装",
            Font = new Font("Microsoft YaHei UI", 13F, FontStyle.Bold),
            Size = new Size(180, 48),
            Location = new Point(31, 122)
        };
        installButton.Click += InstallClicked;
        Controls.Add(installButton);

        closeButton = new Button
        {
            Text = "关闭",
            Size = new Size(90, 32),
            Location = new Point(500, 350),
            Enabled = true
        };
        closeButton.Click += delegate { Close(); };
        Controls.Add(closeButton);

        status = new Label
        {
            Text = "准备就绪",
            AutoSize = false,
            Size = new Size(350, 46),
            Location = new Point(230, 126),
            TextAlign = ContentAlignment.MiddleLeft
        };
        Controls.Add(status);

        instructions = new TextBox
        {
            Multiline = true,
            ReadOnly = true,
            BorderStyle = BorderStyle.FixedSingle,
            Size = new Size(560, 145),
            Location = new Point(31, 190),
            BackColor = Color.White,
            Text = "安装完成后，Chrome 只需最后一步：\r\n\r\n1. 打开“开发者模式”\r\n2. 点击“加载已解压的扩展程序”\r\n3. 选择安装器自动打开的 chrome-extension 文件夹\r\n\r\n扩展加载后会自动安全配对，不需要输入配对码。"
        };
        Controls.Add(instructions);
    }

    private async void InstallClicked(object sender, EventArgs eventArgs)
    {
        installButton.Enabled = false;
        closeButton.Enabled = false;
        status.ForeColor = Color.Black;
        status.Text = "正在安装…";
        try
        {
            InstallResult result = await Task.Run(() => InstallerEngine.Install(false, Report));
            try
            {
                Clipboard.SetText(result.ExtensionDirectory);
            }
            catch
            {
            }
            status.ForeColor = result.IdmConfigured ? Color.DarkGreen : Color.DarkOrange;
            status.Text = result.IdmConfigured
                ? "安装完成，IDM 已自动配置"
                : "安装完成，但 IDM 需要手动确认";
            if (!string.IsNullOrWhiteSpace(result.Warning))
            {
                instructions.Text = result.Warning + "\r\n\r\n" + instructions.Text;
            }
            else
            {
                instructions.Text += "\r\n扩展目录已经复制到剪贴板。";
            }
            installButton.Text = "安装完成";
        }
        catch (Exception exception)
        {
            status.ForeColor = Color.DarkRed;
            status.Text = "安装失败";
            instructions.Text = exception.Message + "\r\n\r\n请保留完整安装包后重试。";
            installButton.Text = "重新安装";
            installButton.Enabled = true;
        }
        finally
        {
            closeButton.Enabled = true;
        }
    }

    private void Report(string message)
    {
        if (IsDisposed) return;
        BeginInvoke((Action)delegate { status.Text = message; });
    }
}

internal sealed class InstallResult
{
    internal string InstallDirectory = "";
    internal string ExtensionDirectory = "";
    internal bool IdmConfigured;
    internal string Warning = "";
}

internal static class InstallerEngine
{
    private const string EmbeddedPayloadResource = "LiudiDownloader.Payload.zip";

    internal static string GetInstallDirectory(bool testMode)
    {
        if (testMode)
        {
            string overridePath = Environment.GetEnvironmentVariable("IDM_EAGLE_INSTALL_ROOT") ?? "";
            if (string.IsNullOrWhiteSpace(overridePath))
            {
                throw new InvalidOperationException("测试安装目录未设置");
            }
            return Path.GetFullPath(overridePath);
        }
        return Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "IDM-Eagle自动导入助手"
        );
    }

    internal static InstallResult Install(
        bool testMode,
        Action<string> report,
        bool updateMode = false,
        bool openChromeSetup = true
    )
    {
        string payload = ExtractEmbeddedPayload();
        if (!File.Exists(Path.Combine(payload, "留底下载器.exe"))
            || !File.Exists(Path.Combine(payload, "runtime", "留底桌面端后台", "留底桌面端后台.exe"))
            || !File.Exists(Path.Combine(payload, "media-tools", "ffmpeg.exe"))
            || !File.Exists(Path.Combine(payload, "media-tools", "ffprobe.exe"))
            || !File.Exists(Path.Combine(payload, "media-tools", "yt-dlp.exe"))
            || !File.Exists(Path.Combine(payload, "media-tools", "deno.exe"))
            || !File.Exists(Path.Combine(payload, "chrome-extension", "manifest.json")))
        {
            throw new InvalidOperationException("安装器内嵌载荷不完整，请重新下载安装包。");
        }

        string installDirectory = GetInstallDirectory(testMode);
        string backupDirectory = installDirectory + ".update-backup";
        report("正在停止旧版本…");
        SignalQuit();
        Thread.Sleep(testMode ? 50 : (updateMode ? 2500 : 1000));
        CleanupWechatCapture(installDirectory, testMode, updateMode);

        if (updateMode)
        {
            if (!Directory.Exists(installDirectory))
            {
                throw new InvalidOperationException("没有找到已安装的旧版本，请改用一键安装。 ");
            }
            TryDeleteDirectory(backupDirectory);
            MoveDirectoryWithRetries(installDirectory, backupDirectory);
        }

        try
        {
            report("正在复制程序文件…");
            Directory.CreateDirectory(installDirectory);
            CopyDirectory(payload, installDirectory);
            DeleteObsoleteOwnedExtensionFiles(installDirectory);

            report("正在准备 Chrome 配对…");
            string extensionDirectory = Path.Combine(installDirectory, "chrome-extension");
            if (updateMode)
            {
                string previousBootstrap = Path.Combine(
                    backupDirectory,
                    "chrome-extension",
                    "bootstrap.js"
                );
                if (File.Exists(previousBootstrap))
                {
                    File.Copy(previousBootstrap, Path.Combine(extensionDirectory, "bootstrap.js"), true);
                }
            }
            else
            {
                WriteBootstrapPairing(extensionDirectory, testMode);
            }

            report("正在配置 IDM…");
            string warning;
            bool configured = ConfigureIdm(installDirectory, testMode, out warning);
            if (updateMode && testMode)
            {
                if (string.Equals(
                    Environment.GetEnvironmentVariable("IDM_EAGLE_TEST_UPDATE_FAIL"),
                    "1",
                    StringComparison.Ordinal
                ))
                {
                    throw new InvalidOperationException("模拟更新失败");
                }
                WriteBootstrapPairing(extensionDirectory, true);
                TryDeleteDirectory(backupDirectory);
            }

            if (!testMode && !updateMode)
            {
                report("正在创建快捷方式…");
                InstallUninstaller(installDirectory);
                CreateShortcuts(installDirectory);
                RegisterUninstaller(installDirectory);
            }

            if (!testMode)
            {
                report("正在启动助手…");
                StartAssistant(installDirectory);
                report("正在确认后端、数据库与 FFmpeg…");
                if (!WaitForHealthyVersion(SetupProgram.Version, TimeSpan.FromSeconds(25)))
                {
                    throw new InvalidOperationException("新版本后端、数据库或 FFmpeg 健康检查未通过");
                }
                if (updateMode)
                {
                    InstallUninstaller(installDirectory);
                    CreateShortcuts(installDirectory);
                    RegisterUninstaller(installDirectory);
                    WriteBootstrapPairing(extensionDirectory, false);
                    TryDeleteDirectory(backupDirectory);
                }
                else if (openChromeSetup)
                {
                    OpenChromeSetup(extensionDirectory);
                }
            }

            return new InstallResult
            {
                InstallDirectory = installDirectory,
                ExtensionDirectory = extensionDirectory,
                IdmConfigured = configured,
                Warning = warning
            };
        }
        catch (Exception exception)
        {
            if (!updateMode)
            {
                throw;
            }
            RollBackUpdate(installDirectory, backupDirectory, testMode);
            throw new InvalidOperationException(
                "更新没有完成，已自动恢复旧版本。\r\n\r\n" + exception.Message,
                exception
            );
        }
    }

    private static string ExtractEmbeddedPayload()
    {
        string temporaryRoot = Path.Combine(
            Path.GetTempPath(),
            "LiudiDownloader-Install-" + Guid.NewGuid().ToString("N")
        );
        Directory.CreateDirectory(temporaryRoot);
        try
        {
            using (Stream resource = Assembly.GetExecutingAssembly().GetManifestResourceStream(EmbeddedPayloadResource))
            {
                if (resource == null)
                {
                    throw new InvalidOperationException("安装器缺少内嵌程序载荷。");
                }
                using (ZipArchive archive = new ZipArchive(resource, ZipArchiveMode.Read, false))
                {
                    string allowedPrefix = temporaryRoot.TrimEnd(Path.DirectorySeparatorChar)
                        + Path.DirectorySeparatorChar;
                    foreach (ZipArchiveEntry entry in archive.Entries)
                    {
                        string relative = entry.FullName.Replace('/', Path.DirectorySeparatorChar);
                        if (string.IsNullOrWhiteSpace(relative)) continue;
                        string destination = Path.GetFullPath(Path.Combine(temporaryRoot, relative));
                        if (!destination.StartsWith(allowedPrefix, StringComparison.OrdinalIgnoreCase))
                        {
                            throw new InvalidOperationException("安装载荷包含不安全路径。");
                        }
                        if (string.IsNullOrEmpty(entry.Name))
                        {
                            Directory.CreateDirectory(destination);
                            continue;
                        }
                        Directory.CreateDirectory(Path.GetDirectoryName(destination));
                        using (Stream input = entry.Open())
                        using (FileStream output = new FileStream(destination, FileMode.Create, FileAccess.Write, FileShare.None))
                        {
                            input.CopyTo(output);
                        }
                    }
                }
            }
            string payload = Path.Combine(temporaryRoot, "app");
            AppDomain.CurrentDomain.ProcessExit += delegate { TryDeleteDirectory(temporaryRoot); };
            return payload;
        }
        catch
        {
            TryDeleteDirectory(temporaryRoot);
            throw;
        }
    }

    private static void StartAssistant(string installDirectory)
    {
        Process.Start(new ProcessStartInfo
        {
            FileName = Path.Combine(installDirectory, "留底下载器.exe"),
            WorkingDirectory = installDirectory,
            UseShellExecute = true
        });
    }

    private static void DeleteObsoleteOwnedExtensionFiles(string installDirectory)
    {
        string extensionDirectory = Path.GetFullPath(Path.Combine(installDirectory, "chrome-extension"));
        string extensionPrefix = extensionDirectory.TrimEnd(Path.DirectorySeparatorChar)
            + Path.DirectorySeparatorChar;
        string[] obsoleteFiles =
        {
            "background.js",
            "downloader.html",
            "install.html",
            "json.html",
            "m3u8.html",
            "mpd.html",
            "options.html",
            "preview.html",
            "popup.js",
            "popup.css",
            Path.Combine("catch-script", "catch.js"),
            Path.Combine("catch-script", "i18n.js"),
            Path.Combine("catch-script", "recorder.js"),
            Path.Combine("catch-script", "recorder2.js"),
            Path.Combine("catch-script", "webrtc.js"),
            Path.Combine("css", "install.css"),
            Path.Combine("css", "mobile.css"),
            Path.Combine("css", "options.css"),
            Path.Combine("css", "popup.css"),
            Path.Combine("css", "preview.css"),
            Path.Combine("css", "public.css"),
            Path.Combine("js", "desktop-parser-route.js"),
            Path.Combine("js", "downloader.js"),
            Path.Combine("js", "i18n.js"),
            Path.Combine("js", "install.js"),
            Path.Combine("js", "json.js"),
            Path.Combine("js", "m3u8.downloader.js"),
            Path.Combine("js", "m3u8.js"),
            Path.Combine("js", "mpd.js"),
            Path.Combine("js", "options.js"),
            Path.Combine("js", "popup.js"),
            Path.Combine("js", "popup-utils.js"),
            Path.Combine("js", "preview.js"),
            Path.Combine("js", "templates.js"),
            Path.Combine("js", "media-control.js"),
        };

        foreach (string relativePath in obsoleteFiles)
        {
            string target = Path.GetFullPath(Path.Combine(extensionDirectory, relativePath));
            if (!target.StartsWith(extensionPrefix, StringComparison.OrdinalIgnoreCase))
            {
                throw new InvalidOperationException("拒绝清理安装目录之外的文件。 ");
            }
            if (File.Exists(target))
            {
                File.Delete(target);
            }
        }

        string[] obsoleteDirectories = { "img", "lib", "tools", "_locales" };
        foreach (string relativePath in obsoleteDirectories)
        {
            string target = Path.GetFullPath(Path.Combine(extensionDirectory, relativePath));
            if (!target.StartsWith(extensionPrefix, StringComparison.OrdinalIgnoreCase))
            {
                throw new InvalidOperationException("拒绝清理安装目录之外的目录。 ");
            }
            if (Directory.Exists(target))
            {
                Directory.Delete(target, true);
            }
        }
    }

    private static bool WaitForHealthyVersion(string version, TimeSpan timeout)
    {
        DateTime deadline = DateTime.UtcNow.Add(timeout);
        while (DateTime.UtcNow < deadline)
        {
            try
            {
                HttpWebRequest request = (HttpWebRequest)WebRequest.Create(
                    "http://127.0.0.1:47652/health"
                );
                request.Timeout = 1000;
                request.ReadWriteTimeout = 1000;
                using (HttpWebResponse response = (HttpWebResponse)request.GetResponse())
                using (StreamReader reader = new StreamReader(response.GetResponseStream()))
                {
                    string body = reader.ReadToEnd();
                    bool versionMatches = body.Contains("\"version\": \"" + version + "\"")
                        || body.Contains("\"version\":\"" + version + "\"");
                    bool mediaReady = body.Contains("\"mediaReady\": true")
                        || body.Contains("\"mediaReady\":true");
                    bool youtubeResolverReady = body.Contains("\"youtubeResolverReady\": true")
                        || body.Contains("\"youtubeResolverReady\":true");
                    bool databaseReady = body.Contains("\"databaseSchema\": 6")
                        || body.Contains("\"databaseSchema\":6");
                    bool protocolReady = body.Contains("\"extensionProtocol\": 1")
                        || body.Contains("\"extensionProtocol\":1");
                    bool downloadEngineReady = body.Contains("\"downloadEngine\": \"desktop_ffmpeg\"")
                        || body.Contains("\"downloadEngine\":\"desktop_ffmpeg\"");
                    bool wechatModuleReady = Regex.IsMatch(
                        body,
                        "\\\"bridgeHash\\\"\\s*:\\s*\\\"[0-9a-fA-F]{16}\\\""
                    );
                    if (versionMatches && mediaReady && youtubeResolverReady && databaseReady && protocolReady && downloadEngineReady && wechatModuleReady)
                    {
                        return true;
                    }
                }
            }
            catch (WebException)
            {
            }
            Thread.Sleep(500);
        }
        return false;
    }

    private static void RollBackUpdate(
        string installDirectory,
        string backupDirectory,
        bool testMode
    )
    {
        SignalQuit();
        Thread.Sleep(1500);
        TryDeleteDirectory(installDirectory);
        if (Directory.Exists(backupDirectory))
        {
            MoveDirectoryWithRetries(backupDirectory, installDirectory);
            if (!testMode)
            {
                StartAssistant(installDirectory);
            }
        }
    }

    private static void MoveDirectoryWithRetries(string source, string destination)
    {
        Exception lastError = null;
        for (int attempt = 0; attempt < 20; attempt++)
        {
            try
            {
                Directory.Move(source, destination);
                return;
            }
            catch (IOException exception)
            {
                lastError = exception;
                Thread.Sleep(250);
            }
            catch (UnauthorizedAccessException exception)
            {
                lastError = exception;
                Thread.Sleep(250);
            }
        }
        throw lastError ?? new IOException("无法移动程序目录");
    }

    private static void TryDeleteDirectory(string directory)
    {
        if (!Directory.Exists(directory)) return;
        for (int attempt = 0; attempt < 20; attempt++)
        {
            try
            {
                Directory.Delete(directory, true);
                return;
            }
            catch (IOException)
            {
                Thread.Sleep(250);
            }
            catch (UnauthorizedAccessException)
            {
                Thread.Sleep(250);
            }
        }
    }

    private static void SignalQuit()
    {
        try
        {
            using (EventWaitHandle handle = EventWaitHandle.OpenExisting(SetupProgram.QuitEventName))
            {
                handle.Set();
            }
        }
        catch (WaitHandleCannotBeOpenedException)
        {
        }
        catch (UnauthorizedAccessException)
        {
        }
    }

    private static void CleanupWechatCapture(
        string installDirectory,
        bool testMode,
        bool preserveInactiveCertificate = false
    )
    {
        if (testMode) return;
        string captureRoot = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "IdmEagleAutoImport",
            "wechat-channels"
        );
        if (!Directory.Exists(captureRoot)) return;
        if (preserveInactiveCertificate
            && !File.Exists(Path.Combine(captureRoot, "proxy-lease.json")))
        {
            return;
        }
        string backend = Path.Combine(
            installDirectory,
            "runtime",
            "留底桌面端后台",
            "留底桌面端后台.exe"
        );
        if (!File.Exists(backend))
        {
            throw new InvalidOperationException("检测到视频号捕获状态，但旧版后端缺失，无法安全恢复系统代理。请先修复安装。 ");
        }
        using (Process process = Process.Start(new ProcessStartInfo
        {
            FileName = backend,
            Arguments = "--cleanup-wechat-capture",
            WorkingDirectory = installDirectory,
            UseShellExecute = false,
            CreateNoWindow = true,
            WindowStyle = ProcessWindowStyle.Hidden
        }))
        {
            bool exited = process != null && process.WaitForExit(20000);
            if (process != null && !exited)
            {
                try
                {
                    process.Kill();
                    process.WaitForExit(5000);
                }
                catch
                {
                }
            }
            if (process == null || !exited || process.ExitCode != 0)
            {
                throw new InvalidOperationException("视频号捕获清理未完成；为保护系统代理设置，已中止安装或卸载。 ");
            }
        }
    }

    private static void CopyDirectory(string source, string destination)
    {
        foreach (string directory in Directory.GetDirectories(source, "*", SearchOption.AllDirectories))
        {
            string relative = directory.Substring(source.Length).TrimStart(Path.DirectorySeparatorChar);
            Directory.CreateDirectory(Path.Combine(destination, relative));
        }
        foreach (string file in Directory.GetFiles(source, "*", SearchOption.AllDirectories))
        {
            string relative = file.Substring(source.Length).TrimStart(Path.DirectorySeparatorChar);
            string target = Path.Combine(destination, relative);
            Directory.CreateDirectory(Path.GetDirectoryName(target));
            Exception lastError = null;
            for (int attempt = 0; attempt < 10; attempt++)
            {
                try
                {
                    File.Copy(file, target, true);
                    lastError = null;
                    break;
                }
                catch (IOException exception)
                {
                    lastError = exception;
                    Thread.Sleep(200);
                }
            }
            if (lastError != null) throw lastError;
        }
    }

    private static bool ConfigureIdm(
        string installDirectory,
        bool testMode,
        out string warning
    )
    {
        warning = "";
        string idmSubkey = testMode
            ? (Environment.GetEnvironmentVariable("IDM_EAGLE_IDM_REGISTRY_SUBKEY") ?? @"Software\IDMEagleAutoImport\InstallerTest\IDM")
            : SetupProgram.DefaultIdmRegistry;
        string stateSubkey = testMode
            ? (Environment.GetEnvironmentVariable("IDM_EAGLE_STATE_REGISTRY_SUBKEY") ?? @"Software\IDMEagleAutoImport\InstallerTest\State")
            : SetupProgram.DefaultStateRegistry;
        string hook = Path.Combine(installDirectory, "IdmEagleHook.exe");

        using (RegistryKey idm = Registry.CurrentUser.CreateSubKey(idmSubkey))
        using (RegistryKey state = Registry.CurrentUser.CreateSubKey(stateSubkey))
        {
            string currentProgram = Convert.ToString(idm.GetValue("VScannerProgram", ""));
            string currentParameters = Convert.ToString(idm.GetValue("VScannerParameters", ""));
            bool ours = string.Equals(
                Path.GetFileName(currentProgram),
                "IdmEagleHook.exe",
                StringComparison.OrdinalIgnoreCase
            );
            if (!string.IsNullOrWhiteSpace(currentProgram) && !ours)
            {
                warning = "检测到 IDM 已配置其他病毒扫描程序，为避免覆盖安全软件，本安装器没有修改该项。请在 IDM > 选项 > 下载 > 病毒检查选项中手动确认。";
                return false;
            }

            if (Convert.ToInt32(state.GetValue("BackupSaved", 0)) != 1)
            {
                bool assumeOriginallyEmpty = ours;
                state.SetValue("HadProgram", assumeOriginallyEmpty ? 0 : (string.IsNullOrEmpty(currentProgram) ? 0 : 1), RegistryValueKind.DWord);
                state.SetValue("PreviousProgram", assumeOriginallyEmpty ? "" : currentProgram, RegistryValueKind.String);
                state.SetValue("HadParameters", assumeOriginallyEmpty ? 0 : (string.IsNullOrEmpty(currentParameters) ? 0 : 1), RegistryValueKind.DWord);
                state.SetValue("PreviousParameters", assumeOriginallyEmpty ? "" : currentParameters, RegistryValueKind.String);
                state.SetValue("BackupSaved", 1, RegistryValueKind.DWord);
            }
            state.SetValue("InstallDirectory", installDirectory, RegistryValueKind.String);
            idm.SetValue("VScannerProgram", hook, RegistryValueKind.String);
            idm.SetValue("VScannerParameters", "[File]", RegistryValueKind.String);
        }
        return true;
    }

    private static void WriteBootstrapPairing(string extensionDirectory, bool testMode)
    {
        byte[] secretBytes = new byte[32];
        using (RandomNumberGenerator random = RandomNumberGenerator.Create())
        {
            random.GetBytes(secretBytes);
        }
        string secret = ToHex(secretBytes);
        File.WriteAllText(
            Path.Combine(extensionDirectory, "bootstrap.js"),
            "globalThis.IDM_EAGLE_BOOTSTRAP_SECRET = \"" + secret + "\";\r\n",
            new UTF8Encoding(false)
        );

        string dataDirectory = testMode
            ? Path.Combine(GetInstallDirectory(true), "test-data")
            : Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "IdmEagleAutoImport"
            );
        Directory.CreateDirectory(dataDirectory);
        byte[] hash;
        using (SHA256 sha = SHA256.Create())
        {
            hash = sha.ComputeHash(Encoding.UTF8.GetBytes(secret));
        }
        long expiresAt = (long)(DateTime.UtcNow.AddDays(7) - new DateTime(1970, 1, 1)).TotalSeconds;
        string json = "{\"secretHash\":\"" + ToHex(hash) + "\",\"expiresAt\":" + expiresAt + "}";
        File.WriteAllText(
            Path.Combine(dataDirectory, "pairing-bootstrap.json"),
            json,
            new UTF8Encoding(false)
        );
    }

    private static string ToHex(byte[] bytes)
    {
        StringBuilder builder = new StringBuilder(bytes.Length * 2);
        foreach (byte value in bytes) builder.Append(value.ToString("x2"));
        return builder.ToString();
    }

    private static void InstallUninstaller(string installDirectory)
    {
        string target = Path.Combine(installDirectory, "卸载助手.exe");
        File.Copy(Application.ExecutablePath, target, true);
    }

    private static void CreateShortcuts(string installDirectory)
    {
        DeleteLegacyShortcuts();
        string target = Path.Combine(installDirectory, "留底下载器.exe");
        string desktop = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory),
            "留底下载器.lnk"
        );
        string startFolder = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.StartMenu),
            "Programs",
            "留底下载器"
        );
        Directory.CreateDirectory(startFolder);
        CreateShortcut(desktop, target, "", installDirectory);
        CreateShortcut(Path.Combine(startFolder, "打开留底桌面端.lnk"), target, "", installDirectory);
        CreateShortcut(
            Path.Combine(startFolder, "卸载助手.lnk"),
            Path.Combine(installDirectory, "卸载助手.exe"),
            "--uninstall",
            installDirectory
        );
    }

    private static void DeleteLegacyShortcuts()
    {
        string desktopDirectory = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
        foreach (string legacyName in new[]
        {
            "IDM → Eagle 自动导入助手.lnk",
            "下载中转站.lnk"
        })
        {
            string legacyDesktop = Path.Combine(desktopDirectory, legacyName);
            if (File.Exists(legacyDesktop)) File.Delete(legacyDesktop);
        }
        string programsDirectory = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.StartMenu),
            "Programs"
        );
        foreach (string legacyName in new[]
        {
            "下载中转站",
            "IDM → Eagle 自动导入助手"
        })
        {
            string legacyStartFolder = Path.Combine(programsDirectory, legacyName);
            if (Directory.Exists(legacyStartFolder)) Directory.Delete(legacyStartFolder, true);
        }
    }

    private static void CreateShortcut(string path, string target, string arguments, string workingDirectory)
    {
        Type shellType = Type.GetTypeFromProgID("WScript.Shell");
        dynamic shell = Activator.CreateInstance(shellType);
        dynamic shortcut = shell.CreateShortcut(path);
        shortcut.TargetPath = target;
        shortcut.Arguments = arguments;
        shortcut.WorkingDirectory = workingDirectory;
        shortcut.IconLocation = target + ",0";
        shortcut.Save();
    }

    private static void RegisterUninstaller(string installDirectory)
    {
        using (RegistryKey key = Registry.CurrentUser.CreateSubKey(SetupProgram.DefaultUninstallRegistry))
        {
            key.SetValue("DisplayName", SetupProgram.ProductName, RegistryValueKind.String);
            key.SetValue("DisplayVersion", SetupProgram.Version, RegistryValueKind.String);
            key.SetValue("Publisher", "阿毅i", RegistryValueKind.String);
            key.SetValue("InstallLocation", installDirectory, RegistryValueKind.String);
            key.SetValue(
                "UninstallString",
                SetupProgram.QuoteArgument(Path.Combine(installDirectory, "卸载助手.exe")) + " --uninstall",
                RegistryValueKind.String
            );
            key.SetValue("NoModify", 1, RegistryValueKind.DWord);
            key.SetValue("NoRepair", 0, RegistryValueKind.DWord);
        }
    }

    private static void OpenChromeSetup(string extensionDirectory)
    {
        try
        {
            Process.Start("explorer.exe", SetupProgram.QuoteArgument(extensionDirectory));
        }
        catch
        {
        }
        string chrome = FindChrome();
        try
        {
            if (!string.IsNullOrEmpty(chrome))
            {
                Process.Start(chrome, "chrome://extensions/");
            }
        }
        catch
        {
        }
    }

    private static string FindChrome()
    {
        string[] candidates = new[]
        {
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), "Google", "Chrome", "Application", "chrome.exe"),
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86), "Google", "Chrome", "Application", "chrome.exe"),
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Google", "Chrome", "Application", "chrome.exe")
        };
        return candidates.FirstOrDefault(File.Exists) ?? "";
    }

    internal static void Uninstall(string installDirectory, bool testMode = false)
    {
        string fullInstall = Path.GetFullPath(installDirectory).TrimEnd(Path.DirectorySeparatorChar);
        string expected = (testMode
            ? GetInstallDirectory(true)
            : Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "IDM-Eagle自动导入助手"
            )).TrimEnd(Path.DirectorySeparatorChar);
        if (!string.Equals(fullInstall, expected, StringComparison.OrdinalIgnoreCase)
            || !File.Exists(Path.Combine(fullInstall, "留底下载器.exe")))
        {
            throw new InvalidOperationException("安装目录校验失败，未删除任何文件。");
        }

        SignalQuit();
        Thread.Sleep(testMode ? 50 : 1200);
        CleanupWechatCapture(fullInstall, testMode);
        RestoreIdm(fullInstall, testMode);
        if (!testMode)
        {
            DeleteShortcuts();
            Registry.CurrentUser.DeleteSubKeyTree(SetupProgram.DefaultUninstallRegistry, false);
        }

        Exception lastError = null;
        for (int attempt = 0; attempt < 15; attempt++)
        {
            try
            {
                Directory.Delete(fullInstall, true);
                lastError = null;
                break;
            }
            catch (IOException exception)
            {
                lastError = exception;
                Thread.Sleep(300);
            }
            catch (UnauthorizedAccessException exception)
            {
                lastError = exception;
                Thread.Sleep(300);
            }
        }
        if (lastError != null) throw lastError;
    }

    private static void RestoreIdm(string installDirectory, bool testMode)
    {
        string idmSubkey = testMode
            ? (Environment.GetEnvironmentVariable("IDM_EAGLE_IDM_REGISTRY_SUBKEY") ?? @"Software\IDMEagleAutoImport\InstallerTest\IDM")
            : SetupProgram.DefaultIdmRegistry;
        string stateSubkey = testMode
            ? (Environment.GetEnvironmentVariable("IDM_EAGLE_STATE_REGISTRY_SUBKEY") ?? @"Software\IDMEagleAutoImport\InstallerTest\State")
            : SetupProgram.DefaultStateRegistry;
        using (RegistryKey state = Registry.CurrentUser.OpenSubKey(stateSubkey, false))
        using (RegistryKey idm = Registry.CurrentUser.CreateSubKey(idmSubkey))
        {
            if (state == null) return;
            string current = Convert.ToString(idm.GetValue("VScannerProgram", ""));
            string installedHook = Path.Combine(installDirectory, "IdmEagleHook.exe");
            if (!string.Equals(current, installedHook, StringComparison.OrdinalIgnoreCase)) return;

            if (Convert.ToInt32(state.GetValue("HadProgram", 0)) == 1)
                idm.SetValue("VScannerProgram", Convert.ToString(state.GetValue("PreviousProgram", "")), RegistryValueKind.String);
            else
                idm.DeleteValue("VScannerProgram", false);

            if (Convert.ToInt32(state.GetValue("HadParameters", 0)) == 1)
                idm.SetValue("VScannerParameters", Convert.ToString(state.GetValue("PreviousParameters", "")), RegistryValueKind.String);
            else
                idm.DeleteValue("VScannerParameters", false);
        }
        Registry.CurrentUser.DeleteSubKeyTree(stateSubkey, false);
    }

    private static void DeleteShortcuts()
    {
        DeleteLegacyShortcuts();
        string desktop = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory),
            "留底下载器.lnk"
        );
        if (File.Exists(desktop)) File.Delete(desktop);
        string startFolder = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.StartMenu),
            "Programs",
            "留底下载器"
        );
        if (Directory.Exists(startFolder)) Directory.Delete(startFolder, true);
    }
}
