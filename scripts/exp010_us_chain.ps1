# EXP-010 US chain: wait for EXP-009 US completion -> score -> smoke -> dist full -> ssr full
Set-Location C:\dev\idea
$countOk = { python -c "import json,sys;print(sum(1 for l in open(r'data/exp009/us_raw.jsonl',encoding='utf-8') if (lambda r: r.get('pred') is not None)(json.loads(l))))" }
$retries = 0
while ($true) {
    $alive = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -match 'exp009_us_run' }
    $ok = [int](& $countOk)
    "$(Get-Date -Format 'HH:mm') ok=$ok alive=$([bool]$alive)" | Out-File data\exp010\us_chain_watch.log -Append -Encoding utf8
    if (-not $alive) {
        if ($ok -ge 45200) { break }
        elseif ($retries -lt 2) {
            # runner died with work remaining: resume inline (blocks until done)
            $retries++
            python scripts/exp009_us_run.py --full --model llama-3.2-90b --rpm 40 --concurrency 48 *>> data\exp009\us_run_chain.log
        } else { break }
    }
    Start-Sleep -Seconds 180
}
# EXP-009 US scoring
python scripts/exp009_us_score.py *> data\exp009\us_score_console.txt
# EXP-010 US: smoke gate then full runs
python scripts/exp010_run.py --track us --channel dist --smoke *> data\exp010\us_dist_smoke.log
$smokeOk = [int](python -c "import json;print(sum(1 for l in open(r'data/exp010/us_dist_raw_smoke.jsonl',encoding='utf-8') if json.loads(l).get('dist')))")
if ($smokeOk -ge 6) {
    python scripts/exp010_run.py --track us --channel dist --full *> data\exp010\us_dist_run.log
} else { "SMOKE FAIL dist ($smokeOk/8)" | Out-File data\exp010\us_chain_error.txt -Encoding utf8 }
python scripts/exp010_run.py --track us --channel ssr --smoke *> data\exp010\us_ssr_smoke.log
$smokeOk2 = [int](python -c "import json;print(sum(1 for l in open(r'data/exp010/us_ssr_raw_smoke.jsonl',encoding='utf-8') if json.loads(l).get('text')))")
if ($smokeOk2 -ge 6) {
    python scripts/exp010_run.py --track us --channel ssr --full *> data\exp010\us_ssr_run.log
} else { "SMOKE FAIL ssr ($smokeOk2/8)" | Out-File data\exp010\us_chain_error.txt -Append -Encoding utf8 }
"US chain done $(Get-Date -Format 'MM-dd HH:mm')" | Out-File data\exp010\us_chain_done.txt -Encoding utf8
