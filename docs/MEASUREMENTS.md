# Update performance on Windows

The benchmark installed v1 first, then measured the same signed v2 bundle on 15 prepared clients. One earlier v2 update warmed the environment and was excluded. Each recorded update refreshed and verified metadata, fetched and verified the ZIP, ran the app self-test, and committed activation over the normal client path. The repository served real loopback HTTP traffic. The ZIP held about 1 MiB of stored data and the actual reference app.

Environment was an Intel Core i7-13645HX with 20 logical CPUs, Windows 11 build 26200, Python 3.12.10, and python-tuf 7.0.1.

| Phase | Median time |
| --- | ---: |
| Metadata fetch, verification and target selection | 70.6 ms |
| Artifact download and verification | 16.5 ms |
| Extraction, self-test and activation | 93.8 ms |
| End-to-end update | 203.0 ms |

The verifier consumed **1,803 bytes of metadata** and **1,050,391 bytes of artifact data** per measured update. Metadata was about **0.17%** of artifact size. The counts cover HTTP response bodies read by the verifier. Headers, unsuccessful probe responses, and transport framing are outside this count.

The total includes client state and evidence writes. Each phase has its own median, so summing the phase medians does not reproduce the total median. The timings measure python-tuf operations as called by this project. They do not isolate Ed25519 or SHA-256 CPU time and do not predict performance over the internet.

```powershell
.\.venv\Scripts\python.exe -m verified_updates benchmark --samples 15 --payload-kib 1024
```

Every run saves all individual timings and byte counts in `benchmark.json`. Use the same payload, sample count and environment when comparing results. [Recorded raw samples](evidence/benchmark-windows-1mib.json)
