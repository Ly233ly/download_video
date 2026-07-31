using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Windows.Forms;

[assembly: AssemblyTitle("下载中转站")]
[assembly: AssemblyDescription("把 IDM 下载的视频自动中转导入 Eagle")]
[assembly: AssemblyProduct("下载中转站")]
[assembly: AssemblyCompany("下载中转站")]
[assembly: AssemblyVersion("1.4.8.0")]
[assembly: AssemblyFileVersion("1.4.8.0")]

internal static class Launcher
{
    private const string TrayMutexName = @"Local\IdmEagleAutoImportTray";
    private const string ShowEventName = @"Local\IdmEagleAutoImportShow";
    private const string RulesEventName = @"Local\IdmEagleAutoImportRules";
    private const string UpdateEventName = @"Local\IdmEagleAutoImportUpdate";
    private const string QuitEventName = @"Local\IdmEagleAutoImportQuit";
    private const string WakeEventName = @"Local\IdmEagleAutoImportWake";

    [STAThread]
    private static int Main(string[] args)
    {
        string baseDirectory = AppDomain.CurrentDomain.BaseDirectory.TrimEnd(Path.DirectorySeparatorChar);
        string executableName = Path.GetFileNameWithoutExtension(Application.ExecutablePath);
        bool hookMode = executableName.IndexOf("Hook", StringComparison.OrdinalIgnoreCase) >= 0;
        bool startHidden = args.Any(argument => string.Equals(
            argument,
            "--start-hidden",
            StringComparison.OrdinalIgnoreCase
        ));
        string scriptName = hookMode ? "idm_hook.pyw" : "assistant.pyw";
        string scriptDirectory = baseDirectory;
        string scriptPath = Path.Combine(scriptDirectory, scriptName);
        if (!File.Exists(scriptPath))
        {
            scriptDirectory = Path.Combine(baseDirectory, "launcher");
            scriptPath = Path.Combine(scriptDirectory, scriptName);
        }
        string projectDirectory = string.Equals(
            new DirectoryInfo(scriptDirectory).Name,
            "launcher",
            StringComparison.OrdinalIgnoreCase
        ) ? Directory.GetParent(scriptDirectory).FullName : baseDirectory;

        string backend = FindBackend(baseDirectory);
        string pythonw = "";
        if (string.IsNullOrEmpty(backend))
        {
            pythonw = FindPython(projectDirectory);
            if (!File.Exists(pythonw) || !File.Exists(scriptPath))
            {
                if (!hookMode)
                {
                    MessageBox.Show(
                        "无法找到内置运行环境或 Python 3.11+。请重新运行一键安装程序进行修复。",
                        "下载中转站",
                        MessageBoxButtons.OK,
                        MessageBoxIcon.Error
                    );
                }
                return 2;
            }
        }

        if (hookMode)
        {
            if (!string.IsNullOrEmpty(backend))
            {
                return RunBackendHook(backend, projectDirectory, args);
            }
            return RunHook(pythonw, scriptPath, projectDirectory, args);
        }

        bool createdNew;
        using (Mutex trayMutex = new Mutex(false, TrayMutexName, out createdNew))
        {
            if (!createdNew)
            {
                if (!startHidden)
                {
                    SignalEvent(ShowEventName);
                }
                return 0;
            }

            Process process;
            try
            {
                process = Process.Start(
                    !string.IsNullOrEmpty(backend)
                    ? BuildBackendStartInfo(backend, projectDirectory, args, false)
                    : BuildStartInfo(pythonw, scriptPath, projectDirectory, args, true)
                );
            }
            catch (Exception exception)
            {
                MessageBox.Show(
                    "启动助手失败：" + exception.Message,
                    "下载中转站",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error
                );
                return 1;
            }

            if (process == null)
            {
                return 1;
            }

            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            TrayApplicationContext context = new TrayApplicationContext(process);
            Application.Run(context);
            int exitCode = context.ChildExitCode;
            context.Dispose();
            return exitCode;
        }
    }

    private static int RunHook(
        string pythonw,
        string scriptPath,
        string projectDirectory,
        string[] args
    )
    {
        try
        {
            using (Process process = Process.Start(BuildStartInfo(
                pythonw,
                scriptPath,
                projectDirectory,
                args,
                false
            )))
            {
                if (process == null || !process.WaitForExit(10000))
                {
                    return 3;
                }
                return process.ExitCode;
            }
        }
        catch
        {
            return 1;
        }
    }

    private static int RunBackendHook(
        string backend,
        string projectDirectory,
        string[] args
    )
    {
        try
        {
            using (Process process = Process.Start(BuildBackendStartInfo(
                backend,
                projectDirectory,
                args,
                true
            )))
            {
                if (process == null || !process.WaitForExit(10000))
                {
                    return 3;
                }
                return process.ExitCode;
            }
        }
        catch
        {
            return 1;
        }
    }

    private static ProcessStartInfo BuildBackendStartInfo(
        string backend,
        string projectDirectory,
        string[] args,
        bool receiveMode
    )
    {
        StringBuilder arguments = new StringBuilder();
        arguments.Append(receiveMode ? "--receive" : "--external-tray");
        foreach (string argument in args)
        {
            arguments.Append(' ');
            arguments.Append(QuoteArgument(argument));
        }
        return new ProcessStartInfo
        {
            FileName = backend,
            Arguments = arguments.ToString(),
            WorkingDirectory = projectDirectory,
            UseShellExecute = false,
            CreateNoWindow = true,
            WindowStyle = ProcessWindowStyle.Hidden
        };
    }

    private static ProcessStartInfo BuildStartInfo(
        string pythonw,
        string scriptPath,
        string projectDirectory,
        string[] args,
        bool externalTray
    )
    {
        StringBuilder arguments = new StringBuilder();
        arguments.Append(QuoteArgument(scriptPath));
        if (externalTray)
        {
            arguments.Append(" --external-tray");
        }
        foreach (string argument in args)
        {
            arguments.Append(' ');
            arguments.Append(QuoteArgument(argument));
        }

        return new ProcessStartInfo
        {
            FileName = pythonw,
            Arguments = arguments.ToString(),
            WorkingDirectory = projectDirectory,
            UseShellExecute = false,
            CreateNoWindow = true,
            WindowStyle = ProcessWindowStyle.Hidden
        };
    }

    internal static bool SignalEvent(string name)
    {
        try
        {
            using (EventWaitHandle handle = EventWaitHandle.OpenExisting(name))
            {
                return handle.Set();
            }
        }
        catch (WaitHandleCannotBeOpenedException)
        {
            return false;
        }
        catch (UnauthorizedAccessException)
        {
            return false;
        }
    }

    private sealed class TrayApplicationContext : ApplicationContext
    {
        private readonly Process child;
        private readonly NotifyIcon notifyIcon;
        private readonly ContextMenuStrip menu;
        private readonly System.Windows.Forms.Timer monitorTimer;
        private DateTime? forceExitAfter;
        private bool cleaned;

        public int ChildExitCode { get; private set; }

        public TrayApplicationContext(Process childProcess)
        {
            child = childProcess;
            ChildExitCode = 0;

            ToolStripMenuItem statusItem = new ToolStripMenuItem("下载中转站 1.4.8");
            statusItem.Enabled = false;
            ToolStripMenuItem openItem = new ToolStripMenuItem("显示窗口");
            openItem.Font = new Font(openItem.Font, FontStyle.Bold);
            openItem.Click += delegate { OpenRecords(); };
            ToolStripMenuItem checkItem = new ToolStripMenuItem("唤醒处理");
            checkItem.Click += delegate { SignalEvent(WakeEventName); };
            ToolStripMenuItem rulesItem = new ToolStripMenuItem("网站规则");
            rulesItem.Click += delegate { SignalEvent(RulesEventName); };
            ToolStripMenuItem updateItem = new ToolStripMenuItem("检查软件更新");
            updateItem.Click += delegate { SignalEvent(UpdateEventName); };
            ToolStripMenuItem exitItem = new ToolStripMenuItem("退出助手");
            exitItem.Click += delegate { RequestExit(); };

            menu = new ContextMenuStrip();
            menu.ShowImageMargin = false;
            menu.Items.Add(statusItem);
            menu.Items.Add(new ToolStripSeparator());
            menu.Items.Add(openItem);
            menu.Items.Add(rulesItem);
            menu.Items.Add(checkItem);
            menu.Items.Add(updateItem);
            menu.Items.Add(new ToolStripSeparator());
            menu.Items.Add(exitItem);

            notifyIcon = new NotifyIcon();
            notifyIcon.Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath)
                ?? SystemIcons.Application;
            notifyIcon.Text = "下载中转站 · IDM 视频自动导入 Eagle";
            notifyIcon.ContextMenuStrip = menu;
            notifyIcon.MouseClick += delegate(object sender, MouseEventArgs eventArgs)
            {
                if (eventArgs.Button == MouseButtons.Left)
                {
                    OpenRecords();
                }
            };
            notifyIcon.Visible = true;

            monitorTimer = new System.Windows.Forms.Timer();
            monitorTimer.Interval = 500;
            monitorTimer.Tick += delegate { MonitorChild(); };
            monitorTimer.Start();
        }

        private void OpenRecords()
        {
            SignalEvent(ShowEventName);
            try
            {
                child.Refresh();
                IntPtr window = child.MainWindowHandle;
                if (window != IntPtr.Zero)
                {
                    ShowWindow(window, 5);
                    SetForegroundWindow(window);
                }
            }
            catch (InvalidOperationException)
            {
            }
        }

        private void RequestExit()
        {
            if (forceExitAfter.HasValue)
            {
                return;
            }
            SignalEvent(QuitEventName);
            forceExitAfter = DateTime.UtcNow.AddSeconds(5);
        }

        private void MonitorChild()
        {
            try
            {
                if (child.HasExited)
                {
                    ChildExitCode = child.ExitCode;
                    ExitThread();
                    return;
                }
                if (forceExitAfter.HasValue && DateTime.UtcNow >= forceExitAfter.Value)
                {
                    child.Kill();
                }
            }
            catch (InvalidOperationException)
            {
                ExitThread();
            }
        }

        protected override void ExitThreadCore()
        {
            Cleanup();
            base.ExitThreadCore();
        }

        private void Cleanup()
        {
            if (cleaned)
            {
                return;
            }
            cleaned = true;
            monitorTimer.Stop();
            monitorTimer.Dispose();
            notifyIcon.Visible = false;
            notifyIcon.Dispose();
            menu.Dispose();
            child.Dispose();
        }

        [DllImport("user32.dll")]
        private static extern bool ShowWindow(IntPtr window, int command);

        [DllImport("user32.dll")]
        private static extern bool SetForegroundWindow(IntPtr window);
    }

    private static string FindPython(string projectDirectory)
    {
        string localAppData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        List<string> candidates = new List<string>
        {
            Path.Combine(projectDirectory, "runtime", "pythonw.exe")
        };

        string[] roots = new[]
        {
            Path.Combine(localAppData, "Python"),
            Path.Combine(localAppData, "Programs", "Python")
        };
        foreach (string root in roots)
        {
            if (!Directory.Exists(root)) continue;
            candidates.AddRange(
                Directory.GetDirectories(root)
                    .OrderByDescending(path => path, StringComparer.OrdinalIgnoreCase)
                    .Select(path => Path.Combine(path, "pythonw.exe"))
            );
        }

        candidates.Add(Path.Combine(localAppData, "Microsoft", "WindowsApps", "pythonw.exe"));
        string pathValue = Environment.GetEnvironmentVariable("PATH") ?? "";
        foreach (string pathEntry in pathValue.Split(Path.PathSeparator))
        {
            if (!string.IsNullOrWhiteSpace(pathEntry))
            {
                candidates.Add(Path.Combine(pathEntry.Trim(), "pythonw.exe"));
            }
        }
        return candidates.FirstOrDefault(File.Exists) ?? "";
    }

    private static string FindBackend(string baseDirectory)
    {
        List<string> roots = new List<string> { baseDirectory };
        DirectoryInfo directory = new DirectoryInfo(baseDirectory);
        if (string.Equals(directory.Name, "launcher", StringComparison.OrdinalIgnoreCase)
            && directory.Parent != null)
        {
            roots.Add(directory.Parent.FullName);
        }
        foreach (string root in roots)
        {
            string[] candidates = new[]
            {
                Path.Combine(root, "runtime", "下载中转站后台", "下载中转站后台.exe"),
                Path.Combine(root, "runtime", "IdmEagleBackend", "IdmEagleBackend.exe")
            };
            foreach (string candidate in candidates)
            {
                if (File.Exists(candidate))
                {
                    return candidate;
                }
            }
        }
        return "";
    }

    private static string QuoteArgument(string argument)
    {
        if (argument.Length > 0 && argument.IndexOfAny(new[] { ' ', '\t', '\n', '\v', '"' }) < 0)
        {
            return argument;
        }

        StringBuilder result = new StringBuilder();
        result.Append('"');
        int backslashes = 0;
        foreach (char character in argument)
        {
            if (character == '\\')
            {
                backslashes += 1;
            }
            else if (character == '"')
            {
                result.Append('\\', backslashes * 2 + 1);
                result.Append('"');
                backslashes = 0;
            }
            else
            {
                result.Append('\\', backslashes);
                backslashes = 0;
                result.Append(character);
            }
        }
        result.Append('\\', backslashes * 2);
        result.Append('"');
        return result.ToString();
    }
}
