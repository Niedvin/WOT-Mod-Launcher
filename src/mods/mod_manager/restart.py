from __future__ import unicode_literals

import base64
import json
import os
import subprocess
import sys
import tempfile


WORKER = r'''
$ErrorActionPreference = 'Stop'
$job = [IO.File]::ReadAllText($jobPath) | ConvertFrom-Json
function Write-Log($message) {
    try { [IO.File]::AppendAllText($job.log, [DateTime]::Now.ToString('s') + ' ' + $message + [Environment]::NewLine) } catch {}
}
try {
    $client = $null
    try { $client = [Diagnostics.Process]::GetProcessById($job.pid) } catch [ArgumentException] {}
    if ($client) { $client.WaitForExit(); $client.Dispose() }
    foreach ($plan in $job.plans) {
        $done = [Collections.Generic.Stack[object]]::new()
        $temporary = $plan.path + '.' + [Guid]::NewGuid().ToString('N') + '.tmp'
        $previous = $temporary + '.previous'
        try {
            foreach ($move in $plan.moves) {
                [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($move[1])) | Out-Null
                [IO.File]::Move($move[0], $move[1])
                $done.Push($move)
            }
            [IO.File]::WriteAllText($temporary, $plan.value)
            if ([IO.File]::Exists($plan.path)) {
                [IO.File]::Replace($temporary, $plan.path, $previous)
            } else {
                [IO.File]::Move($temporary, $plan.path)
            }
            Write-Log ('Applied ' + [IO.Path]::GetFileName($plan.path) + ' (' + $done.Count + ' moves)')
        } catch {
            Write-Log $_.Exception.Message
            while ($done.Count) {
                $move = $done.Pop()
                try { [IO.File]::Move($move[1], $move[0]) } catch { Write-Log $_.Exception.Message }
            }
        } finally {
            [IO.File]::Delete($temporary)
            [IO.File]::Delete($previous)
        }
    }
} catch {
    Write-Log $_.Exception.Message
} finally {
    [IO.File]::Delete($jobPath)
}
if ($job.exe) {
    try {
        $start = [Diagnostics.ProcessStartInfo]::new($job.exe)
        $start.WorkingDirectory = $job.root
        $start.UseShellExecute = $false
        $launch = [Diagnostics.Process]::Start($start)
        Write-Log ('Restarted game as PID ' + $launch.Id)
        $launch.Dispose()
    } catch {
        Write-Log $_.Exception.Message
    }
}
'''


def schedule(root, plans, restart):
    folder = os.path.join(root, 'mods', 'configs', 'mod_manager')
    if not os.path.isdir(folder):
        os.makedirs(folder)
    executable = ''
    if restart:
        executable = sys.executable
        if os.path.basename(executable).lower() != 'worldoftanks.exe' or not os.path.isfile(executable):
            executable = os.path.join(root, 'win64', 'WorldOfTanks.exe')
        if not os.path.isfile(executable):
            raise IOError('Game executable missing: ' + executable)
    payload = dict(pid=os.getpid(), root=root, exe=executable, log=os.path.join(folder, 'package-switch.log'),
                   plans=[dict(plan, value=json.dumps(plan['value'], ensure_ascii=True)) for plan in plans])
    fd, path = tempfile.mkstemp(prefix='.exit-', suffix='.json', dir=folder)
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(json.dumps(payload, ensure_ascii=True).encode('ascii'))
        script = "$jobPath = '" + path.replace("'", "''") + "'\n" + WORKER
        encoded = base64.b64encode(script.encode('utf-16le'))
        powershell = os.path.join(os.environ['SystemRoot'], 'System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe')
        subprocess.Popen([powershell, '-NoLogo', '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded],
                         creationflags=0x08000000)
    except Exception:
        os.remove(path)
        raise
