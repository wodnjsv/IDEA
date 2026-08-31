# EXP-010 KR chain: dist full -> ssr full (sequential, shares OpenAI TPM)
Set-Location C:\dev\idea
python scripts/exp010_run.py --track kr --channel dist --full *> data\exp010\kr_dist_run.log
python scripts/exp010_run.py --track kr --channel ssr --full *> data\exp010\kr_ssr_run.log
"KR chain done $(Get-Date -Format 'MM-dd HH:mm')" | Out-File data\exp010\kr_chain_done.txt -Encoding utf8
