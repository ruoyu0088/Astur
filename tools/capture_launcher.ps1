param(
    [int]$Delay = 8,
    [string]$Out = "$env:USERPROFILE\Desktop\launcher.png"
)

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class DpiAwareness {
    [DllImport("user32.dll")]
    public static extern bool SetProcessDPIAware();
}
"@
[DpiAwareness]::SetProcessDPIAware() | Out-Null

$bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
Write-Host "Capturing the primary screen in $Delay seconds."
Write-Host "Press Alt+Space, type a query, and wait for the beep."

for ($i = $Delay; $i -gt 0; $i--) {
    Write-Host ("{0}..." -f $i)
    Start-Sleep -Seconds 1
}

[console]::Beep(880, 120)

$bmp = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose()
$bmp.Dispose()

Write-Host "Saved $Out"
