# EXP-010 SSR finishing chain: wait for us_ssr completion -> LLM rater -> score
Set-Location C:\dev\idea
$retries = 0
while ($true) {
    $alive = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -match 'exp010_run' }
    $n = 0
    if (Test-Path "data\exp010\us_ssr_raw.jsonl") {
        $n = [int](python -c "import json;print(sum(1 for l in open(r'data/exp010/us_ssr_raw.jsonl',encoding='utf-8') if json.loads(l).get('text')))")
    }
    "$(Get-Date -Format 'HH:mm') ssr_ok=$n alive=$([bool]$alive)" | Out-File data\exp010\ssr_chain_watch.log -Append -Encoding utf8
    if (-not $alive) {
        if ($n -ge 9050) { break }
        elseif ($retries -lt 2) {
            $retries++
            python scripts/exp010_run.py --track us --channel ssr --full *>> data\exp010\us_ssr_run.log
        } else { break }
    }
    Start-Sleep -Seconds 300
}
python scripts/exp010_ssr_rate.py *> data\exp010\ssr_rate.log
python scripts/exp010_us_score.py --raw us_ssr_scored.jsonl --out us_ssr_score.json *> data\exp010\us_ssr_score_console.txt
"SSR chain done $(Get-Date -Format 'MM-dd HH:mm')" | Out-File data\exp010\ssr_chain_done.txt -Encoding utf8
