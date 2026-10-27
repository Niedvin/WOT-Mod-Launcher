import os
import shutil
import subprocess
import zipfile

csc_path = r'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe'
cert_thumb = 'AA591F513F66919CF86F337114D9A360991A24E7'
sign_environment = dict(os.environ)
sign_environment['PSModulePath'] = os.path.join(os.environ['SystemRoot'], 'System32/WindowsPowerShell/v1.0/Modules')

subprocess.check_call(['python', 'scratch/stage_mods.py'])

os.makedirs(r'staging_modpack\Launcher', exist_ok=True)
subprocess.check_call([
    csc_path, '/target:winexe', '/platform:anycpu', '/optimize+', '/codepage:65001', '/win32manifest:scratch\\app.manifest',
    '/win32icon:scratch\\app.ico',
    '/r:System.Web.Extensions.dll', '/r:System.IO.Compression.dll',
    '/r:System.IO.Compression.FileSystem.dll', r'/out:staging_modpack\Launcher\WotModLauncher.exe',
    r'scratch\WotModLauncher.cs'
])
cert_cmd = 'Set-AuthenticodeSignature -FilePath staging_modpack\\Launcher\\WotModLauncher.exe -Certificate (Get-Item Cert:\\CurrentUser\\My\\' + cert_thumb + ')'
subprocess.check_call([os.path.join(os.environ['SystemRoot'], 'System32/WindowsPowerShell/v1.0/powershell.exe'), '-NoLogo', '-NoProfile', '-NonInteractive', '-Command', "$ErrorActionPreference = 'Stop'; Import-Module Microsoft.PowerShell.Security -ErrorAction Stop; " + cert_cmd], env=sign_environment)
print('Compiled and signed staging_modpack/Launcher/WotModLauncher.exe.')

subprocess.check_call([
    csc_path, '/target:winexe', '/platform:anycpu', '/optimize+', '/codepage:65001', '/win32manifest:scratch\\app.manifest',
    '/win32icon:scratch\\app.ico',
    '/r:System.Web.Extensions.dll', '/r:System.IO.Compression.dll',
    '/r:System.IO.Compression.FileSystem.dll', r'/out:staging_modpack\Installer.exe',
    r'scratch\Installer.cs'
])
cert_cmd = 'Set-AuthenticodeSignature -FilePath staging_modpack\\Installer.exe -Certificate (Get-Item Cert:\\CurrentUser\\My\\' + cert_thumb + ')'
subprocess.check_call([os.path.join(os.environ['SystemRoot'], 'System32/WindowsPowerShell/v1.0/powershell.exe'), '-NoLogo', '-NoProfile', '-NonInteractive', '-Command', "$ErrorActionPreference = 'Stop'; Import-Module Microsoft.PowerShell.Security -ErrorAction Stop; " + cert_cmd], env=sign_environment)
print('Compiled and signed staging_modpack/Installer.exe.')

payload_zip = 'build/payload.zip'
if os.path.exists(payload_zip):
    os.remove(payload_zip)
with zipfile.ZipFile(payload_zip, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
    for root, dirs, files in os.walk('staging_modpack'):
        for f in files:
            if f == 'Installer.exe':
                continue
            full_path = os.path.join(root, f)
            z.write(full_path, os.path.relpath(full_path, 'staging_modpack'))

setup_exe = 'WoT_Modpack_by_Niedvin_Setup.exe'
subprocess.check_call([
    csc_path, '/target:winexe', '/platform:anycpu', '/optimize+', '/codepage:65001',
    '/win32manifest:scratch\\app.manifest', '/win32icon:scratch\\app.ico',
    '/r:System.Web.Extensions.dll', '/r:System.IO.Compression.dll',
    '/r:System.IO.Compression.FileSystem.dll',
    r'/resource:build\payload.zip,WotModpackInstaller.payload.zip',
    '/out:' + setup_exe, r'scratch\Installer.cs'
])
cert_cmd = 'Set-AuthenticodeSignature -FilePath ' + setup_exe + ' -Certificate (Get-Item Cert:\\CurrentUser\\My\\' + cert_thumb + ')'
subprocess.check_call([os.path.join(os.environ['SystemRoot'], 'System32/WindowsPowerShell/v1.0/powershell.exe'), '-NoLogo', '-NoProfile', '-NonInteractive', '-Command', "$ErrorActionPreference = 'Stop'; Import-Module Microsoft.PowerShell.Security -ErrorAction Stop; " + cert_cmd], env=sign_environment)
subprocess.check_call([os.path.abspath(setup_exe), '--selftest'])
selftest_report = os.path.join(os.environ.get('TEMP', '.'), 'wot_setup_selftest.txt')
print('Selftest:', open(selftest_report, encoding='utf-8').read().strip())
print(f'Built single-file {setup_exe} ({os.path.getsize(setup_exe) / (1024*1024):.2f} MB).')

def make_modpack_zip(target_zip):
    if os.path.exists(target_zip):
        os.remove(target_zip)
    src_dir = 'staging_modpack'
    with zipfile.ZipFile(target_zip, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for root, dirs, files in os.walk(src_dir):
            for f in files:
                full_path = os.path.join(root, f)
                rel_path = os.path.relpath(full_path, src_dir)
                arcname = os.path.join('WoT modpack by Niedvin', rel_path)
                z.write(full_path, arcname)

root_zip = 'WoT_Modpack_by_Niedvin.zip'
make_modpack_zip(root_zip)
print(f'Repacked {root_zip} ({os.path.getsize(root_zip) / (1024*1024):.2f} MB).')

desktop = os.path.expanduser('~\\Desktop')
desktop_zip = os.path.join(desktop, 'WoT modpack by Niedvin.zip')
make_modpack_zip(desktop_zip)
print(f'Repacked {desktop_zip} ({os.path.getsize(desktop_zip) / (1024*1024):.2f} MB).')

desktop_dir = os.path.join(desktop, 'WoT modpack by Niedvin')
if os.path.exists(desktop_dir):
    shutil.rmtree(desktop_dir)
shutil.copytree('staging_modpack', desktop_dir)
print('Updated extracted folder on Desktop successfully.')
print('INSTALLER BUILD FINISHED: staging, signed exes, setup payload and archives are ready.')
