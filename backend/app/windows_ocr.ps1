param([string]$InputPath, [string]$Language = "auto", [string]$PageNumbers = "", [switch]$Capabilities)
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType=WindowsRuntime]
$null = [Windows.Globalization.Language, Windows.Foundation, ContentType=WindowsRuntime]
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType=WindowsRuntime]
$null = [Windows.Storage.Streams.IRandomAccessStream, Windows.Storage.Streams, ContentType=WindowsRuntime]
$null = [Windows.Storage.Streams.IRandomAccessStreamWithContentType, Windows.Storage.Streams, ContentType=WindowsRuntime]
$null = [Windows.Storage.Streams.InMemoryRandomAccessStream, Windows.Storage.Streams, ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.SoftwareBitmap, Windows.Graphics.Imaging, ContentType=WindowsRuntime]
$null = [Windows.Data.Pdf.PdfDocument, Windows.Data.Pdf, ContentType=WindowsRuntime]
$null = [Windows.Data.Pdf.PdfPageRenderOptions, Windows.Data.Pdf, ContentType=WindowsRuntime]
$languages = @([Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages | ForEach-Object { $_.LanguageTag })
if ($Capabilities) {
    @{ available = ($languages.Count -gt 0); languages = $languages; engine = "Windows OCR" } | ConvertTo-Json -Compress
    exit 0
}
$asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq "AsTask" -and $_.IsGenericMethod -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
} | Select-Object -First 1
$asActionTask = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq "AsTask" -and -not $_.IsGenericMethod -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncAction'
} | Select-Object -First 1
function Wait-Operation($operation, [Type]$resultType) {
    $task = $asTask.MakeGenericMethod($resultType).Invoke($null, @($operation))
    $task.GetAwaiter().GetResult()
}
function Wait-Action($operation) {
    $task = $asActionTask.Invoke($null, @($operation))
    $null = $task.GetAwaiter().GetResult()
}
if ($Language -eq "auto") {
    $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
    if (-not $engine -and $languages.Count) {
        $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new($languages[0]))
    }
} else {
    $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new($Language))
}
if (-not $engine) { throw "No installed OCR language is available." }
function Read-OcrStream($stream) {
    $decoder = Wait-Operation ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
    if ($decoder.PixelWidth -gt [Windows.Media.Ocr.OcrEngine]::MaxImageDimension -or $decoder.PixelHeight -gt [Windows.Media.Ocr.OcrEngine]::MaxImageDimension) {
        throw "Image dimensions exceed the local OCR limit. Resize the image or paste its text."
    }
    $bitmap = Wait-Operation ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
    try {
        $result = Wait-Operation ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
        return (@($result.Lines | ForEach-Object { $_.Text }) -join "`n")
    } finally { $bitmap.Dispose() }
}
try {
    $file = Wait-Operation ([Windows.Storage.StorageFile]::GetFileFromPathAsync($InputPath)) ([Windows.Storage.StorageFile])
    $pages = @()
    if ([System.IO.Path]::GetExtension($InputPath).ToLowerInvariant() -eq ".pdf") {
        $document = Wait-Operation ([Windows.Data.Pdf.PdfDocument]::LoadFromFileAsync($file)) ([Windows.Data.Pdf.PdfDocument])
        $indices = @($PageNumbers.Split(',') | Where-Object { $_ -match '^\d+$' } | ForEach-Object { [int]$_ })
        foreach ($index in $indices | Select-Object -First 5) {
            if ($index -lt 1 -or $index -gt $document.PageCount) { continue }
            $page = $document.GetPage($index - 1)
            $stream = [Windows.Storage.Streams.InMemoryRandomAccessStream]::new()
            try {
                $options = [Windows.Data.Pdf.PdfPageRenderOptions]::new()
                $longSide = [Math]::Min(2200, [Windows.Media.Ocr.OcrEngine]::MaxImageDimension)
                $scale = $longSide / [Math]::Max($page.Size.Width, $page.Size.Height)
                $options.DestinationWidth = [uint32]($page.Size.Width * $scale)
                $options.DestinationHeight = [uint32]($page.Size.Height * $scale)
                Wait-Action ($page.RenderToStreamAsync($stream, $options))
                $stream.Seek(0)
                $pages += @{ page = $index; text = (Read-OcrStream $stream) }
            } finally { $stream.Dispose(); $page.Dispose() }
        }
    } else {
        $stream = Wait-Operation ($file.OpenReadAsync()) ([Windows.Storage.Streams.IRandomAccessStreamWithContentType])
        try { $pages += @{ page = 1; text = (Read-OcrStream $stream) } }
        finally { $stream.Dispose() }
    }
    @{ pages = $pages; language = $engine.RecognizerLanguage.LanguageTag; engine = "Windows OCR" } | ConvertTo-Json -Depth 6 -Compress
} catch {
    @{ error = $_.Exception.Message; pages = @() } | ConvertTo-Json -Compress
    exit 1
}
