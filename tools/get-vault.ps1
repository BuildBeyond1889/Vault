param([string]$Set = '', [switch]$Menu, [switch]$Updates, [switch]$CopyDrive, [switch]$Zip)
# Archie Vault downloader: free offline libraries from Kiwix and World Possible (RACHEL).
# Every file comes from its official server; nothing is hosted by this project.
# Resumable: close the window any time and run it again, it picks up where it stopped.
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$items = Import-Csv (Join-Path $here 'packs.csv') -Delimiter '|'
$cfgFile = Join-Path $here 'vault-folder.txt'
$onWindows = ($env:OS -eq 'Windows_NT')
$curl = if ($onWindows) { 'curl.exe' } else { 'curl' }
$tar = if ($onWindows) { 'tar.exe' } else { 'tar' }

$sets = [ordered]@{
  core = 'Core knowledge: Wikipedia, dictionaries, free books, travel'
  health = 'Health and medicine'
  land = 'Farming, water, energy and survival'
  repair = 'Repair, salvage and electronics'
  code = 'Coding: language docs, Q&A, algorithms'
  learn = 'Learning for every age: textbooks, courses, simulations'
  kids = "Kids: storybooks, simple encyclopedias, science sims, first coding"
  maps = 'Maps: Kenya, Tanzania, Uganda, Africa, USA'
  shelter = 'Shelters and soup kitchens (US): first aid, medicines, food, disasters, jobs, English, phones'
  pocket = 'Pocket set: small versions for a phone, SD card or old computer'
  everything = 'Everything shareable (all of the above, except the big libraries)'
  big = 'Big libraries: full Wikipedia, Khan Academy, Stack Overflow, Gutenberg... (asks for each)'
}
$verdictNote = @{ green = ''; yellow = ''; orange = '[ask first]'; grey = '[licence unclear]' }

function GB($mb) { '{0:N1} GB' -f ($mb / 1024) }
function Log($t) {
  Write-Host $t
  try { Add-Content -Path (Join-Path $script:dest 'vault-log.txt') -Value ("{0}  {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm'), $t) } catch { }
}
function Sum($list) { [double](($list | Measure-Object -Property mb -Sum).Sum) }
function InSet($it, $name) {
  if ($name -eq 'everything') { return ($it.big -ne '1' -and $it.alt -ne '1') }
  if ($name -eq 'big') { return ($it.big -eq '1') }
  return (" " + $it.sets + " ").Contains(" $name ")
}
function Shareable($it) { $it.verdict -eq 'green' -or $it.verdict -eq 'yellow' }

# ---- where to save (asked once, remembered) ----
$dest = ''
if (Test-Path $cfgFile) { $dest = (Get-Content $cfgFile -Raw).Trim() }
if (-not $dest) {
  Write-Host ''
  Write-Host 'Where should the vault go? Type a folder on a big drive, like E:\Vault (it will be created).'
  Write-Host 'Sizes: the pocket set is about 31 GB, everything shareable about 165 GB, and the big libraries up to 650 GB more.'
  $dest = (Read-Host 'Folder').Trim('"', ' ')
  if (-not $dest) { Write-Host 'No folder given, stopping.'; exit }
  Set-Content $cfgFile $dest
}
$zimDir = Join-Path $dest 'zim'; $rachDir = Join-Path $dest 'rachel'
New-Item -ItemType Directory -Force -Path $zimDir, $rachDir | Out-Null
$script:dest = $dest
function FreeGB {
  try { $d = (Get-Item $dest).PSDrive; return [math]::Floor($d.Free / 1GB) } catch { return 99999 }
}

# ---- newest versions from the Kiwix catalog (falls back to the saved list when offline) ----
$latest = @{}
function KeyOf($p) { (($p -split '/')[-1]) -replace '_\d{4}-\d{2}[a-z]?$', '' }
function Load-Catalog {
  if ($script:catalogLoaded) { return }
  $script:catalogLoaded = $true
  try {
    Write-Host 'Checking the Kiwix catalog for the newest versions...'
    $resp = Invoke-RestMethod -TimeoutSec 180 'https://library.kiwix.org/catalog/v2/entries?count=10000'
    if ($resp -is [string]) { $entries = ([xml]$resp).feed.entry } elseif ($resp -is [xml]) { $entries = $resp.feed.entry } else { $entries = @($resp) }
    foreach ($e in $entries) {
      foreach ($l in @($e.link)) {
        $href = $l.GetAttribute('href')
        if ($l.GetAttribute('type') -eq 'application/x-zim' -and $href) {
          $p = ($href -replace '^https?://[^/]+/zim/', '') -replace '\.zim(\.meta4)?$', ''
          $k = KeyOf $p
          if (-not $latest.ContainsKey($k) -or $p -gt $latest[$k].path) { $latest[$k] = @{ path = $p; bytes = [int64]('0' + $l.GetAttribute('length')); exact = $true } }
        }
      }
    }
    Write-Host ("The catalog lists {0} files." -f $latest.Count)
  } catch { Write-Host 'The catalog is not reachable right now, so the saved list is used.' }
}
function Resolve($it) {
  $k = KeyOf $it.path
  if ($latest.ContainsKey($k)) { return $latest[$k] }
  return @{ path = $it.path; bytes = [int64]$it.mb * 1MB; exact = $false }
}

function Get-Kiwix($it) {
  $r = Resolve $it
  $name = ($r.path -split '/')[-1] + '.zim'
  $out = Join-Path $zimDir $name
  if (Test-Path $out) { Write-Host "  have   $name"; if (Test-Path "$out.part") { Remove-Item "$out.part" -ErrorAction SilentlyContinue }; return }
  $part = "$out.part"
  Log ("  get    {0}  ({1})" -f $it.title, (GB ($r.bytes / 1MB)))
  & $curl -L --fail --retry 10 --retry-delay 15 -C - -o $part ('https://download.kiwix.org/zim/' + $r.path + '.zim')
  if ($LASTEXITCODE -ne 0) { Log "  FAILED $name (run again to resume)"; return }
  # Only the catalog knows exact sizes; the saved list is rounded to whole MB, so it can't judge small files.
  if ($r.exact -and (Get-Item $part).Length -lt ($r.bytes * 0.99)) { Log "  $name looks incomplete, run again to resume"; return }
  Rename-Item $part $name
  Log "  done   $name"
}

function Get-Rachel($it) {
  $dir = Join-Path $rachDir $it.path
  if (Test-Path (Join-Path $dir '.done')) { Write-Host "  have   $($it.path)"; return }
  $zip = Join-Path $rachDir ($it.path + '.zip')
  Log ("  get    {0}  (about {1})" -f $it.title, (GB $it.mb))
  & $curl -L --fail --retry 10 --retry-delay 15 -C - -o $zip ('https://rachel.worldpossible.org/zipped-modules/' + $it.path + '.zip')
  if ($LASTEXITCODE -ne 0) { Log "  FAILED $($it.path) (run again to resume)"; return }
  New-Item -ItemType Directory -Force -Path $dir | Out-Null
  & $tar -xf $zip -C $dir
  if ($LASTEXITCODE -ne 0) { Log "  could not unpack $($it.path)"; return }
  Remove-Item $zip; Set-Content (Join-Path $dir '.done') (Get-Date)
  Log "  done   $($it.path)"
}

function Download($sel) {
  $sel = @($sel)
  if (-not $sel.Count) { Write-Host 'Nothing selected.'; return }
  Load-Catalog
  Write-Host ("{0} packs, about {1}. Free space: {2} GB." -f $sel.Count, (GB (Sum $sel)), (FreeGB))
  if ((Sum $sel) / 1024 -gt (FreeGB)) { Write-Host 'Not enough space for all of it. It downloads until the drive is nearly full.' }
  foreach ($it in $sel) {
    if ((FreeGB) -lt 20) { Log 'Stopping: less than 20 GB free.'; break }
    try { if ($it.kind -eq 'kiwix') { Get-Kiwix $it } else { Get-Rachel $it } } catch { Log "  error on $($it.title): $_" }
  }
  Log 'Finished this round. Run it again any time to resume, or to fetch new versions.'
  Write-Host 'Open the library with Open Vault.bat.'
}

function Confirm-AskFirst($sel) {
  $ask = @($sel | Where-Object { -not (Shareable $_) })
  if (-not $ask.Count) { return $true }
  Write-Host ''
  Write-Host 'These packs are fine for your own reading, but their owners have not given permission to hand out copies:'
  foreach ($it in $ask) { Write-Host ("  {0} {1}  ({2})" -f $verdictNote[$it.verdict], $it.title, $it.license) }
  Write-Host 'Do not put them on drives or boxes you give away unless you get written permission. See PACK-LICENSES.md.'
  return ((Read-Host 'Download them for your own use? (Y/N)').Trim().ToUpper() -eq 'Y')
}

function Run-Set($name) {
  if (-not $sets.Contains($name)) { Write-Host "Unknown set: $name"; return }
  $sel = @($items | Where-Object { (InSet $_ $name) -and (Shareable $_) })
  Write-Host ''
  Write-Host $sets[$name]
  if ($name -eq 'big') {
    $pick = @()
    foreach ($it in $sel) {
      if ((Read-Host ("  {0}, {1}. Get it? (Y/N)" -f $it.title, (GB $it.mb))).Trim().ToUpper() -eq 'Y') { $pick += $it }
    }
    Download $pick; return
  }
  foreach ($it in $sel) { Write-Host ("  {0,-70} {1,9}" -f $it.title, (GB $it.mb)) }
  $skipped = @($items | Where-Object { (InSet $_ $name) -and -not (Shareable $_) })
  if ($skipped.Count) { Write-Host ("  ({0} more packs in this subject need permission to share; pick them in Choose Packs.bat if you want them for yourself.)" -f $skipped.Count) }
  Write-Host ("Total: about {0}." -f (GB (Sum $sel)))
  if ((Read-Host 'Start? (Y/N)').Trim().ToUpper() -eq 'Y') { Download $sel }
}

function Parse-Numbers($text, $max) {
  $out = @()
  foreach ($part in ($text -split '[,\s]+')) {
    if ($part -match '^(\d+)-(\d+)$') { $out += [int]$matches[1]..[int]$matches[2] }
    elseif ($part -match '^\d+$') { $out += [int]$part }
  }
  return @($out | Where-Object { $_ -ge 1 -and $_ -le $max } | Select-Object -Unique)
}

function Run-Menu {
  $order = 'core', 'health', 'land', 'repair', 'code', 'learn', 'maps'
  $list = @()
  foreach ($sh in $order) {
    Write-Host ''
    Write-Host $sets[$sh].ToUpper()
    foreach ($it in ($items | Where-Object shelf -eq $sh)) {
      $list += $it
      Write-Host ("  {0,4}  {1,-62} {2,9}  {3}" -f $list.Count, $it.title, (GB $it.mb), $verdictNote[$it.verdict])
    }
  }
  Write-Host ''
  $nums = Parse-Numbers (Read-Host 'Type the numbers you want, like 1,4,7-9') $list.Count
  $sel = @($nums | ForEach-Object { $list[$_ - 1] })
  if (-not $sel.Count) { Write-Host 'Nothing picked.'; return }
  if (-not (Confirm-AskFirst $sel)) { $sel = @($sel | Where-Object { Shareable $_ }) }
  Download $sel
}

function Check-Updates {
  Load-Catalog
  $old = @()
  foreach ($f in Get-ChildItem $zimDir -Filter *.zim) {
    $k = KeyOf $f.BaseName
    if ($latest.ContainsKey($k) -and (($latest[$k].path -split '/')[-1]) -ne $f.BaseName) { $old += $f.Name }
  }
  if (-not $old) { Write-Host 'Everything you have is the newest version.'; return }
  Write-Host 'Newer versions exist for:'; $old | ForEach-Object { Write-Host "  $_" }
  Write-Host 'Run the same Get file again to fetch them. The Vault then shows them as UPDATED and tells you which old file to delete.'
}

function Copy-Drive {
  Write-Host ''
  Write-Host 'Make a Vault drive: put the library and Vault Search on a USB drive, SD card, hard drive or a folder'
  Write-Host 'you then copy to another computer. Only packs you have already downloaded are copied.'
  $names = @($sets.Keys | Where-Object { $_ -ne 'big' })
  for ($i = 0; $i -lt $names.Count; $i++) { Write-Host ("  {0,2}  {1}" -f ($i + 1), $sets[$names[$i]]) }
  $c = (Read-Host 'Which one? Type its number').Trim()
  if ($c -notmatch '^\d+$' -or [int]$c -lt 1 -or [int]$c -gt $names.Count) { return }
  $pick = $names[[int]$c - 1]
  $target = (Read-Host 'Copy to which drive or folder? (like E:\ or D:\Shelter Vault)').Trim('"', ' ')
  if (-not $target) { return }
  $chosen = @($items | Where-Object { (InSet $_ $pick) -and (Shareable $_) })
  $need = 0
  foreach ($f in Get-ChildItem $zimDir -Filter *.zim) {
    if ($chosen | Where-Object { $_.kind -eq 'kiwix' -and (KeyOf $_.path) -eq (KeyOf $f.BaseName) }) { $need += $f.Length }
  }
  Write-Host ("About {0} to copy." -f (GB ($need / 1MB)))
  $tz = Join-Path $target 'zim'; New-Item -ItemType Directory -Force -Path $tz | Out-Null
  try { $free = (Get-Item $target).PSDrive.Free; if ($free -lt $need) { Write-Host ("Warning: only {0} free there. It copies until it's full." -f (GB ($free / 1MB))) } } catch { }
  $n = 0
  foreach ($f in Get-ChildItem $zimDir -Filter *.zim) {
    $it = $chosen | Where-Object { $_.kind -eq 'kiwix' -and (KeyOf $_.path) -eq (KeyOf $f.BaseName) } | Select-Object -First 1
    if (-not $it) { continue }
    $n++
    if (-not (Test-Path (Join-Path $tz $f.Name))) { Write-Host ("  copy {0}  ({1})" -f $it.title, (GB ($f.Length / 1MB))); Copy-Item $f.FullName $tz }
  }
  foreach ($d in Get-ChildItem $rachDir -Directory -ErrorAction SilentlyContinue) {
    $it = $chosen | Where-Object { $_.kind -eq 'rachel' -and $_.path -eq $d.Name } | Select-Object -First 1
    if ($it -and (Test-Path (Join-Path $d.FullName '.done'))) {
      $n++
      $tr = Join-Path $target 'rachel'; New-Item -ItemType Directory -Force -Path $tr | Out-Null
      if (-not (Test-Path (Join-Path $tr $d.Name))) { Write-Host "  copy $($d.Name)"; Copy-Item $d.FullName $tr -Recurse }
    }
  }
  $missing = $chosen.Count - $n
  if ($missing -gt 0) { Write-Host ("({0} packs in this set aren't downloaded yet, so they were skipped. Run its Get file first if you want them.)" -f $missing) }
  $root = Split-Path $here -Parent
  $exe = Join-Path $root 'Vault Search.exe'
  if (Test-Path $exe) { Copy-Item $exe $target } else { Write-Host '  (Vault Search.exe is not in this folder yet. Download it from the project page and put it on the drive too.)' }
  Copy-Item (Join-Path $here 'DRIVE README.txt') (Join-Path $target 'README.txt') -ErrorAction SilentlyContinue
  Copy-Item (Join-Path $root 'PACK-LICENSES.md') $target -ErrorAction SilentlyContinue
  Write-Host 'Done. On a computer: double-click Vault Search.exe on the drive. On a phone: open the zim files with the free Kiwix app.'
  Write-Host 'README.txt and PACK-LICENSES.md on the drive carry the credits. Never sell or charge for copies.'
}

function Make-Zip {
  Write-Host ''
  Write-Host 'Make one .zip with Vault Search and a set, to upload to Google Drive, OneDrive or Dropbox and download on'
  Write-Host 'another computer. (Too big to attach to an email: send yourself the share link instead.)'
  $names = @($sets.Keys | Where-Object { $_ -ne 'big' -and $_ -ne 'everything' })
  for ($i = 0; $i -lt $names.Count; $i++) { Write-Host ("  {0,2}  {1}" -f ($i + 1), $sets[$names[$i]]) }
  $c = (Read-Host 'Which one? Type its number').Trim()
  if ($c -notmatch '^\d+$' -or [int]$c -lt 1 -or [int]$c -gt $names.Count) { return }
  $pick = $names[[int]$c - 1]
  $root = Split-Path $here -Parent
  $exe = Join-Path $root 'Vault Search.exe'
  if (-not (Test-Path $exe)) { Write-Host 'Vault Search.exe is missing. Run Build Vault Search.bat first.'; return }
  $chosen = @($items | Where-Object { (InSet $_ $pick) -and (Shareable $_) -and $_.kind -eq 'kiwix' })
  $files = @(); $need = 0
  foreach ($f in Get-ChildItem $zimDir -Filter *.zim) {
    if ($chosen | Where-Object { (KeyOf $_.path) -eq (KeyOf $f.BaseName) }) { $files += ('zim/' + $f.Name); $need += $f.Length }
  }
  if (-not $files.Count) { Write-Host 'None of this set is downloaded yet. Run its Get file first.'; return }
  if ($files.Count -lt $chosen.Count) { Write-Host ("({0} packs in this set aren't downloaded yet, so they're left out.)" -f ($chosen.Count - $files.Count)) }
  $out = Join-Path $root 'out'; New-Item -ItemType Directory -Force -Path $out | Out-Null
  $extra = Join-Path $out 'extra'; New-Item -ItemType Directory -Force -Path $extra | Out-Null
  Copy-Item (Join-Path $here 'DRIVE README.txt') (Join-Path $extra 'README.txt')
  Copy-Item (Join-Path $root 'PACK-LICENSES.md') $extra -ErrorAction SilentlyContinue
  Copy-Item $exe $extra
  $title = (Get-Culture).TextInfo.ToTitleCase($pick)
  $zipPath = Join-Path $out ("Vault - {0}.zip" -f $title)
  if (Test-Path $zipPath) { Remove-Item $zipPath }
  Write-Host ("Packing {0} packs, about {1}. This takes a few minutes; the window shows nothing until it's done." -f $files.Count, (GB ($need / 1MB)))
  $common = @('-C', $extra, 'Vault Search.exe', 'README.txt', 'PACK-LICENSES.md', '-C', $dest) + $files
  & $tar --options 'zip:compression=store' -a -c -f $zipPath @common
  if ($LASTEXITCODE -ne 0) { if (Test-Path $zipPath) { Remove-Item $zipPath }; & $tar -a -c -f $zipPath @common }
  Remove-Item $extra -Recurse -ErrorAction SilentlyContinue
  if ($LASTEXITCODE -ne 0 -or -not (Test-Path $zipPath)) { Write-Host 'Packing failed. Is there enough free space on this drive?'; return }
  Write-Host ''
  Write-Host ("Done: {0}  ({1})" -f $zipPath, (GB ((Get-Item $zipPath).Length / 1MB)))
  Write-Host 'Next: upload it to Google Drive (or OneDrive), then email yourself the share link.'
  Write-Host 'On the other computer: download it, right-click > Extract All, open the folder, double-click Vault Search.exe.'
  Start-Process explorer.exe $out
}

if ($Set) { Run-Set $Set.ToLower(); exit }
if ($Menu) { Run-Menu; exit }
if ($Updates) { Check-Updates; exit }
if ($CopyDrive) { Copy-Drive; exit }
if ($Zip) { Make-Zip; exit }
Write-Host 'Use one of the Get ... .bat files, or Choose Packs.bat.'
