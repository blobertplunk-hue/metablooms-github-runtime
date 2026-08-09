param(
    [Parameter(Mandatory=$true)][string]$PdfPigDll,
    [Parameter(Mandatory=$true)][string]$OutputDir,
    [switch]$NegativeControl
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$fixtureDir = Join-Path $OutputDir 'fixtures'
New-Item -ItemType Directory -Force -Path $fixtureDir | Out-Null

$fixtures = @{
    'synthetic_text.pdf' = 'JVBERi0xLjMKJZOMi54gUmVwb3J0TGFiIEdlbmVyYXRlZCBQREYgZG9jdW1lbnQgKG9wZW5zb3VyY2UpCjEgMCBvYmoKPDwKL0YxIDIgMCBSCj4+CmVuZG9iagoyIDAgb2JqCjw8Ci9CYXNlRm9udCAvSGVsdmV0aWNhIC9FbmNvZGluZyAvV2luQW5zaUVuY29kaW5nIC9OYW1lIC9GMSAvU3VidHlwZSAvVHlwZTEgL1R5cGUgL0ZvbnQKPj4KZW5kb2JqCjMgMCBvYmoKPDwKL0NvbnRlbnRzIDcgMCBSIC9NZWRpYUJveCBbIDAgMCA1OTUuMjc1NiA4NDEuODg5OCBdIC9QYXJlbnQgNiAwIFIgL1Jlc291cmNlcyA8PAovRm9udCAxIDAgUiAvUHJvY1NldCBbIC9QREYgL1RleHQgL0ltYWdlQiAvSW1hZ2VDIC9JbWFnZUkgXQo+PiAvUm90YXRlIDAgL1RyYW5zIDw8Cgo+PiAKICAvVHlwZSAvUGFnZQo+PgplbmRvYmoKNCAwIG9iago8PAovUGFnZU1vZGUgL1VzZU5vbmUgL1BhZ2VzIDYgMCBSIC9UeXBlIC9DYXRhbG9nCj4+CmVuZG9iago1IDAgb2JqCjw8Ci9BdXRob3IgKGFub255bW91cykgL0NyZWF0aW9uRGF0ZSAoRDoyMDI2MDgwNzIxMzg0OSswMCcwMCcpIC9DcmVhdG9yIChhbm9ueW1vdXMpIC9LZXl3b3JkcyAoKSAvTW9kRGF0ZSAoRDoyMDI2MDgwNzIxMzg0OSswMCcwMCcpIC9Qcm9kdWNlciAoUmVwb3J0TGFiIFBERiBMaWJyYXJ5IC0gXChvcGVuc291cmNlXCkpIAogIC9TdWJqZWN0ICh1bnNwZWNpZmllZCkgL1RpdGxlICh1bnRpdGxlZCkgL1RyYXBwZWQgL0ZhbHNlCj4+CmVuZG9iago2IDAgb2JqCjw8Ci9Db3VudCAxIC9LaWRzIFsgMyAwIFIgXSAvVHlwZSAvUGFnZXMKPj4KZW5kb2JqCjcgMCBvYmoKPDwKL0ZpbHRlciBbIC9BU0NJSTg1RGVjb2RlIC9GbGF0ZURlY29kZSBdIC9MZW5ndGggMTY2Cj4+CnN0cmVhbQpHYXJwIlltUz8lKF4vZDE6TjlsZVlrX2QlWihrOGEtbmI9JitOLlcnMGUlYzhxIj1wVlRWKjpbRTgzclszVjc0UEpOXWJoJmtJWVlUUidPaCM5OjdwNCJdJmJVTVVedFVHVjRUT2NYUEk0NyYzKydtS2VgSXQ2b0YzKlMkVmJWUSZhVXNXVF4paFoqL1NlZ2VdPyF1Ry0xTixnNiEjLipcaVw+Wn4+ZW5kc3RyZWFtCmVuZG9iagp4cmVmCjAgOAowMDAwMDAwMDAwIDY1NTM1IGYgCjAwMDAwMDAwNjEgMDAwMDAgbiAKMDAwMDAwMDA5MiAwMDAwMCBuIAowMDAwMDAwMTk5IDAwMDAwIG4gCjAwMDAwMDA0MDIgMDAwMDAgbiAKMDAwMDAwMDQ3MCAwMDAwMCBuIAowMDAwMDAwNzMxIDAwMDAwIG4gCjAwMDAwMDA3OTAgMDAwMDAgbiAKdHJhaWxlcgo8PAovSUQgCls8NjVhN2IxNjBlNmY2YTU1NWZiODM2NmYyZjFkOTQzYjM+PDY1YTdiMTYwZTZmNmE1NTVmYjgzNjZmMmYxZDk0M2IzPl0KJSBSZXBvcnRMYWIgZ2VuZXJhdGVkIFBERiBkb2N1bWVudCAtLSBkaWdlc3QgKG9wZW5zb3VyY2UpCgovSW5mbyA1IDAgUgovUm9vdCA0IDAgUgovU2l6ZSA4Cj4+CnN0YXJ0eHJlZgoxMDQ2CiUlRU9GCg=='
    'synthetic_multicol.pdf' = 'JVBERi0xLjMKJZOMi54gUmVwb3J0TGFiIEdlbmVyYXRlZCBQREYgZG9jdW1lbnQgKG9wZW5zb3VyY2UpCjEgMCBvYmoKPDwKL0YxIDIgMCBSCj4+CmVuZG9iagoyIDAgb2JqCjw8Ci9CYXNlRm9udCAvSGVsdmV0aWNhIC9FbmNvZGluZyAvV2luQW5zaUVuY29kaW5nIC9OYW1lIC9GMSAvU3VidHlwZSAvVHlwZTEgL1R5cGUgL0ZvbnQKPj4KZW5kb2JqCjMgMCBvYmoKPDwKL0NvbnRlbnRzIDcgMCBSIC9NZWRpYUJveCBbIDAgMCA1OTUuMjc1NiA4NDEuODg5OCBdIC9QYXJlbnQgNiAwIFIgL1Jlc291cmNlcyA8PAovRm9udCAxIDAgUiAvUHJvY1NldCBbIC9QREYgL1RleHQgL0ltYWdlQiAvSW1hZ2VDIC9JbWFnZUkgXQo+PiAvUm90YXRlIDAgL1RyYW5zIDw8Cgo+PiAKICAvVHlwZSAvUGFnZQo+PgplbmRvYmoKNCAwIG9iago8PAovUGFnZU1vZGUgL1VzZU5vbmUgL1BhZ2VzIDYgMCBSIC9UeXBlIC9DYXRhbG9nCj4+CmVuZG9iago1IDAgb2JqCjw8Ci9BdXRob3IgKGFub255bW91cykgL0NyZWF0aW9uRGF0ZSAoRDoyMDI2MDgwNzIxNDE0NSswMCcwMCcpIC9DcmVhdG9yIChhbm9ueW1vdXMpIC9LZXl3b3JkcyAoKSAvTW9kRGF0ZSAoRDoyMDI2MDgwNzIxNDE0NSswMCcwMCcpIC9Qcm9kdWNlciAoUmVwb3J0TGFiIFBERiBMaWJyYXJ5IC0gXChvcGVuc291cmNlXCkpIAogIC9TdWJqZWN0ICh1bnNwZWNpZmllZCkgL1RpdGxlICh1bnRpdGxlZCkgL1RyYXBwZWQgL0ZhbHNlCj4+CmVuZG9iago2IDAgb2JqCjw8Ci9Db3VudCAxIC9LaWRzIFsgMyAwIFIgXSAvVHlwZSAvUGFnZXMKPj4KZW5kb2JqCjcgMCBvYmoKPDwKL0ZpbHRlciBbIC9BU0NJSTg1RGVjb2RlIC9GbGF0ZURlY29kZSBdIC9MZW5ndGggMjc1Cj4+CnN0cmVhbQpHYXMyRGI2bCo/JjRRPkJgRWZMOlNPbSRZXClJS1UyanRoRUQ2dCVaOmE9dVdnTHE5L1Y/cGNGY0ZMaDUidVZgU0RmdT5eJyNCMTkhcUg+T2BZJThNRjRrQC5mcUY2Zk9xP1tsckdvOXEuWHRpLFdhZzFeUlBNZGRePilGO0ozNistcy1XPzJndGhaT1NKYTdzVVVwNkluYEgvJ2xHYDM1UHBzKTJbRlZAXEZSPkYqL1smZDs6UG1gKTlbXkFUWEF1RiooJjhTR2wiOjxvci9nK2EvYz0jIUkyI1VNaVdpKGJJdXJGJ10yJHVqZWNQZkhBJSpnWCI2KVMtbkJBPi8/XjpkQGI+Kkxnb1ViPTxQX2Z+PmVuZHN0cmVhbQplbmRvYmoKeHJlZgowIDgKMDAwMDAwMDAwMCA2NTUzNSBmIAowMDAwMDAwMDYxIDAwMDAwIG4gCjAwMDAwMDAwOTIgMDAwMDAgbiAKMDAwMDAwMDE5OSAwMDAwMCBuIAowMDAwMDAwNDAyIDAwMDAwIG4gCjAwMDAwMDA0NzAgMDAwMDAgbiAKMDAwMDAwMDczMSAwMDAwMCBuIAowMDAwMDAwNzkwIDAwMDAwIG4gCnRyYWlsZXIKPDwKL0lEIApbPDIzZGUxYjVlMDFmOWZiN2RkOWZhYmY3NGI3OWEzYjI2PjwyM2RlMWI1ZTAxZjlmYjdkZDlmYWJmNzRiNzlhM2IyNj5dCiUgUmVwb3J0TGFiIGdlbmVyYXRlZCBQREYgZG9jdW1lbnQgLS0gZGlnZXN0IChvcGVuc291cmNlKQoKL0luZm8gNSAwIFIKL1Jvb3QgNCAwIFIKL1NpemUgOAo+PgpzdGFydHhyZWYKMTE1NQolJUVPRgo='
    'synthetic_blank.pdf' = 'JVBERi0xLjMKJZOMi54gUmVwb3J0TGFiIEdlbmVyYXRlZCBQREYgZG9jdW1lbnQgKG9wZW5zb3VyY2UpCjEgMCBvYmoKPDwKL0YxIDIgMCBSCj4+CmVuZG9iagoyIDAgb2JqCjw8Ci9CYXNlRm9udCAvSGVsdmV0aWNhIC9FbmNvZGluZyAvV2luQW5zaUVuY29kaW5nIC9OYW1lIC9GMSAvU3VidHlwZSAvVHlwZTEgL1R5cGUgL0ZvbnQKPj4KZW5kb2JqCjMgMCBvYmoKPDwKL0NvbnRlbnRzIDcgMCBSIC9NZWRpYUJveCBbIDAgMCA1OTUuMjc1NiA4NDEuODg5OCBdIC9QYXJlbnQgNiAwIFIgL1Jlc291cmNlcyA8PAovRm9udCAxIDAgUiAvUHJvY1NldCBbIC9QREYgL1RleHQgL0ltYWdlQiAvSW1hZ2VDIC9JbWFnZUkgXQo+PiAvUm90YXRlIDAgL1RyYW5zIDw8Cgo+PiAKICAvVHlwZSAvUGFnZQo+PgplbmRvYmoKNCAwIG9iago8PAovUGFnZU1vZGUgL1VzZU5vbmUgL1BhZ2VzIDYgMCBSIC9UeXBlIC9DYXRhbG9nCj4+CmVuZG9iago1IDAgb2JqCjw8Ci9BdXRob3IgKGFub255bW91cykgL0NyZWF0aW9uRGF0ZSAoRDoyMDI2MDgwNzIxMzg0OSswMCcwMCcpIC9DcmVhdG9yIChhbm9ueW1vdXMpIC9LZXl3b3JkcyAoKSAvTW9kRGF0ZSAoRDoyMDI2MDgwNzIxMzg0OSswMCcwMCcpIC9Qcm9kdWNlciAoUmVwb3J0TGFiIFBERiBMaWJyYXJ5IC0gXChvcGVuc291cmNlXCkpIAogIC9TdWJqZWN0ICh1bnNwZWNpZmllZCkgL1RpdGxlICh1bnRpdGxlZCkgL1RyYXBwZWQgL0ZhbHNlCj4+CmVuZG9iago2IDAgb2JqCjw8Ci9Db3VudCAxIC9LaWRzIFsgMyAwIFIgXSAvVHlwZSAvUGFnZXMKPj4KZW5kb2JqCjcgMCBvYmoKPDwKL0ZpbHRlciBbIC9BU0NJSTg1RGVjb2RlIC9GbGF0ZURlY29kZSBdIC9MZW5ndGggODEKPj4Kc3RyZWFtCkdhcFFoMEU9RiwwVVxIM1RccE5ZVF5RS2s/dGM+SVAsO1cjVTFeMjNpaFBFTV9OaCQsRFBVWlghKXM8RC0zYWZHVz0kSUgkPSFSblNkXnF+PmVuZHN0cmVhbQplbmRvYmoKeHJlZgowIDgKMDAwMDAwMDAwMCA2NTUzNSBmIAowMDAwMDAwMDYxIDAwMDAgbiAKMDAwMDAwMDA5MiAwMDAwMCBuIAowMDAwMDAwMTk5IDAwMDAwIG4gCjAwMDAwMDA0MDIgMDAwMDAgbiAKMDAwMDAwMDQ3MCAwMDAwMCBuIAowMDAwMDAwNzMxIDAwMDAwIG4gCjAwMDAwMDA3OTAgMDAwMDAgbiAKdHJhaWxlcgo8PAovSUQgCls8ODQ4Y2MxNDYzYWIyZjRhOWQ1NjUxNjM5Y2RmY2QyNWQ+PDg0OGNjMTQ2M2FiMmY0YTlkNTY1MTYzOWNkZmNkMjVkPl0KJSBSZXBvcnRMYWIgZ2VuZXJhdGVkIFBERiBkb2N1bWVudCAtLSBkaWdlc3QgKG9wZW5zb3VyY2UpCgovSW5mbyA1IDAgUgovUm9vdCA0IDAgUgovU2l6ZSA4Cj4+CnN0YXJ0eHJlZgo5NjAKJSVFT0YK'
    'synthetic_password.pdf' = 'JVBERi0xLjMKJeLjz9MKMSAwIG9iago8PAovUHJvZHVjZXIgPGZkYmNmYTJjNWY+Cj4+CmVuZG9iagoyIDAgb2JqCjw8Ci9UeXBlIC9QYWdlcwovQ291bnQgMQovS2lkcyBbIDQgMCBSIF0KPj4KZW5kb2JqCjMgMCBvYmoKPDwKL1R5cGUgL0NhdGFsb2cKL1BhZ2VzIDIgMCBSCj4+CmVuZG9iago0IDAgb2JqCjw8Ci9Db250ZW50cyA1IDAgUgovTWVkaWFCb3ggWyAwIDAgNTk1LjI3NTYgODQxLjg4OTggXQovUmVzb3VyY2VzIDw8Ci9Gb250IDYgMCBSCi9Qcm9jU2V0IFsgL1BERiAvVGV4dCAvSW1hZ2VCIC9JbWFnZUMgL0ltYWdlSSBdCj4+Ci9Sb3RhdGUgMAovVHJhbnMgPDwKPj4KL1R5cGUgL1BhZ2UKL1BhcmVudCAyIDAgUgo+PgplbmRvYmoKNSAwIG9iago8PAovRmlsdGVyIFsgL0FTQ0lJODVEZWNvZGUgL0ZsYXRlRGVjb2RlIF0KL0xlbmd0aCAxMjIKPj4Kc3RyZWFtCqfDfmlgc/kl8NG1hGIbBvcSu6lKHQrlZ24q96v0Amec1mzDEBqZFtq4pz8OeSL6O0QZiAlzNNF+hEgtEFqc6UnMKTpbxwPNP+ihREztPB8guplY/lhRc7VHbLsHdBhIudN/0+p9ltsC8TylXTVRYMuOlqMVq4S+UluVCmVuZHN0cmVhbQplbmRvYmoKNiAwIG9iago8PAovRjEgNyAwIFIKPj4KZW5kb2JqCjcgMCBvYmoKPDwKL0Jhc2VGb250IC9IZWx2ZXRpY2EKL0VuY29kaW5nIC9XaW5BbnNpRW5jb2RpbmcKL05hbWUgL0YxCi9TdWJ0eXBlIC9UeXBlMQovVHlwZSAvRm9udAo+PgplbmRvYmoKOCAwIG9iago8PAovViAyCi9SIDMKL0xlbmd0aCAxMjgKL1AgNDI5NDk2NzI5MgovRmlsdGVyIC9TdGFuZGFyZAovTyA8ODgxNjQ3MDc0ODg2MjFjYmE0MjdiNDY2YjI5Nzg3MTU0YjA0NDMyZDljNjJlNmI3YzBkMWM3NWE5MmNjYWJiOT4KL1UgPDI4ZTBlNzFhMDQzMWZjYTM1ZTY0NGM0NDc1NzEyMjBlMjhiZjRlNWU0ZTc1OGE0MTY0MDA0ZTU2ZmZmYTAxMDg+Cj4+CmVuZG9iagp4cmVmCjAgOQowMDAwMDAwMDAwIDY1NTM1IGYgCjAwMDAwMDAwMTUgMDAwMDAgbiAKMDAwMDAwMDA1OSAwMDAwMCBuIAowMDAwMDAwMTE4IDAwMDAwIG4gCjAwMDAwMDAxNjcgMDAwMDAgbiAKMDAwMDAwMDM2NiAwMDAwMCBuIAowMDAwMDAwNTc5IDAwMDAwIG4gCjAwMDAwMDA2MTAgMDAwMDAgbiAKMDAwMDAwMDcxNyAwMDAwMCBuIAp0cmFpbGVyCjw8Ci9TaXplIDkKL1Jvb3QgMyAwIFIKL0luZm8gMSAwIFIKL0lEIFsgPDM3NjE2MTM4MzYzMTMxMzkzMDM1MzE2NTY2NjUzMTMxNjYzNTYxNjIzMjY1MzAzOTMzMzczMjYzMzYzNTYxMzk+IDwzNzYxNjEzODM2MzEzMTM5MzAzNTMxNjU2NjY1MzEzMTY2MzU2MTYyMzI2NTMwMzkzMzM3MzI2MzM2MzU2MTM5PiBdCi9FbmNyeXB0IDggMCBSCj4+CnN0YXJ0eHJlZgo5MzIKJSVFT0YK'
}

foreach ($entry in $fixtures.GetEnumerator()) {
    [IO.File]::WriteAllBytes((Join-Path $fixtureDir $entry.Key), [Convert]::FromBase64String($entry.Value))
}

if (-not (Test-Path -LiteralPath $PdfPigDll -PathType Leaf)) {
    throw "PdfPig DLL not found: $PdfPigDll"
}

Add-Type -Path $PdfPigDll

function Get-PdfPigEvidence {
    param([Parameter(Mandatory=$true)][string]$Path)

    $doc = [UglyToad.PdfPig.PdfDocument]::Open($Path)
    try {
        $pages = @()
        foreach ($page in $doc.GetPages()) {
            $contentText = [UglyToad.PdfPig.DocumentLayoutAnalysis.TextExtractor.ContentOrderTextExtractor]::GetText($page)
            $words = @($page.GetWords([UglyToad.PdfPig.DocumentLayoutAnalysis.WordExtractor.NearestNeighbourWordExtractor]::Instance))
            $coord = @($words | Sort-Object @{Expression={$_.BoundingBox.Bottom};Descending=$true}, @{Expression={$_.BoundingBox.Left};Descending=$false} | ForEach-Object { $_.Text })
            $pages += [ordered]@{
                page_number = $page.Number
                letter_count = @($page.Letters).Count
                word_count = $words.Count
                content_order_text = [string]$contentText
                coordinate_word_text = ($coord -join ' ')
            }
        }
        return [ordered]@{
            path = [IO.Path]::GetFileName($Path)
            page_count = $doc.NumberOfPages
            pages = $pages
        }
    }
    finally {
        $doc.Dispose()
    }
}

$results = [ordered]@{}
foreach ($name in @('synthetic_text.pdf','synthetic_multicol.pdf','synthetic_blank.pdf')) {
    $results[$name] = Get-PdfPigEvidence -Path (Join-Path $fixtureDir $name)
}

$text = [string]$results['synthetic_text.pdf'].pages[0].content_order_text
$multiContent = [string]$results['synthetic_multicol.pdf'].pages[0].content_order_text
$multiCoord = [string]$results['synthetic_multicol.pdf'].pages[0].coordinate_word_text
$blankLetters = [int]$results['synthetic_blank.pdf'].pages[0].letter_count
$blankWords = [int]$results['synthetic_blank.pdf'].pages[0].word_count
$blankContent = [string]$results['synthetic_blank.pdf'].pages[0].content_order_text

$assertions = [System.Collections.Generic.List[object]]::new()
function Add-Assertion([string]$Name, [bool]$Passed, [string]$Observed) {
    $assertions.Add([ordered]@{name=$Name;passed=$Passed;observed=$Observed}) | Out-Null
}

Add-Assertion 'TEXT_LAYER_STUDENT_ID' ($text -match '\b9001\b') $text
Add-Assertion 'TEXT_LAYER_SCALE_SCORE' ($text -match '\b512\b') $text
Add-Assertion 'MULTICOLUMN_HEADERS' (($multiContent -match 'Diagnostic\s*1') -and ($multiContent -match 'Diagnostic\s*2')) $multiContent
Add-Assertion 'MULTICOLUMN_SCORES' ((($multiContent + ' ' + $multiCoord) -match '\b450\b') -and (($multiContent + ' ' + $multiCoord) -match '\b475\b')) ($multiContent + ' || ' + $multiCoord)
Add-Assertion 'MULTICOLUMN_DATES' ((($multiContent + ' ' + $multiCoord) -match '09/01/2025') -and (($multiContent + ' ' + $multiCoord) -match '01/10/2026')) ($multiContent + ' || ' + $multiCoord)
Add-Assertion 'BLANK_HAS_NO_TEXT_GLYPHS' (($blankLetters -eq 0) -and ($blankWords -eq 0) -and [string]::IsNullOrWhiteSpace($blankContent)) "letters=$blankLetters words=$blankWords text=[$blankContent]"

if ($NegativeControl) {
    Add-Assertion 'NEGATIVE_CONTROL_MUST_FAIL' ($text -match 'TOKEN_THAT_DOES_NOT_EXIST_9F18') $text
}

$failed = @($assertions | Where-Object { -not $_.passed })
$evidence = [ordered]@{
    schema = 'mb.lakeland.pdfpig.windows_probe.v1'
    created_at_utc = [DateTime]::UtcNow.ToString('o')
    powershell = [ordered]@{
        version = $PSVersionTable.PSVersion.ToString()
        edition = $PSVersionTable.PSEdition
        platform = [Environment]::OSVersion.ToString()
    }
    pdfpig_dll = [ordered]@{
        path = [IO.Path]::GetFileName($PdfPigDll)
        sha256 = (Get-FileHash -LiteralPath $PdfPigDll -Algorithm SHA256).Hash.ToLowerInvariant()
        assembly_version = ([Reflection.AssemblyName]::GetAssemblyName($PdfPigDll)).Version.ToString()
    }
    negative_control = [bool]$NegativeControl
    assertions = $assertions
    failed_count = $failed.Count
    results = $results
}

$evidencePath = Join-Path $OutputDir ($(if ($NegativeControl) {'PDFPIG_NEGATIVE_CONTROL.json'} else {'PDFPIG_PROBE_RESULT.json'}))
$evidence | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $evidencePath -Encoding UTF8

foreach ($a in $assertions) {
    $status = if ($a.passed) {'PASS'} else {'FAIL'}
    Write-Host "$status $($a.name)"
}

if ($NegativeControl) {
    if ($failed.Count -eq 1 -and $failed[0].name -eq 'NEGATIVE_CONTROL_MUST_FAIL') {
        Write-Host 'PASS negative control was detected by the probe.'
        exit 86
    }
    Write-Error "Negative control did not fail exactly as expected. failed=$($failed.Count)"
    exit 87
}

if ($failed.Count -gt 0) {
    Write-Error "PdfPig probe failed assertions=$($failed.Count)"
    exit 1
}

Write-Host "PDFPIG PROBE PASS assertions=$($assertions.Count)"
exit 0
