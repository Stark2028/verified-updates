# Demonstration guide

Run `.\.venv\Scripts\python.exe -m verified_updates demo --summary` from the project root. Open the resulting report.html. Every update uses a fresh process and a real HTTP repository; no browser animation supplies a security result.

1. Show the initial authorized installation and an actual installed application's output.
2. Inspect artifact substitution. The candidate hash differs and the active sequence remains 1.
3. Restore the genuine bytes. The same client successfully installs sequence 2.
4. Replay the earlier timestamp in another client process. Retained trust rejects the metadata rollback.
5. Inspect the expired-metadata and one-signer failures. Explain valid signatures versus authorization/freshness.
6. Inspect inconsistent snapshot metadata. This client starts on an older release so the inconsistent new snapshot actually has to be fetched. A client with a valid cached snapshot correctly need not refetch it.
7. Show authorized release-key replacement through root version 2 and installation of sequence 3.
8. Show process exit 73 before the active-pointer commit. Sequence 3 remains active; a new process recovers and installs sequence 4.
9. Show the authorized sequence-5 application's self-test exiting 17. The application remains at display version 1.3.0 / sequence 4 and still processes the sample CSV.
10. Compare unsigned checksums, signatures without replay policy, and the TUF client. Explain the actual decisions, then show the assumptions and implementation limits.

The demo's encrypted keys are disposable and their random passphrase is not retained. Re-run the lab for a new experiment, or use the documented manual publisher workflow for ongoing development. The server has stopped by the time the report opens; existing app execution is offline:

```powershell
.\.venv\Scripts\python.exe -m verified_updates client run --client .runtime/YOUR-RUN/clients/main -- demo_app/sample.csv
```

Expected application output includes version 1.3.0, four records, and score summaries with mean 89.5. Use the actual run directory, not a placeholder copied literally.

The report is a reader for completed runs. A live operator console and a packaged desktop application remain planned.

For a short viva, open the first installation and the one-signer rejection. Both evidence records contain the release details, artifact digest and verified approval count. Then show the comparison table and replay an older signed publication. This gives you three questions to answer in order. Did the file change? Who approved it? Has the client seen a newer release?

A practical extension is to put the two signing keys on separate machines and show two maintainers approving the same digest. Use the existing three-way comparison as the main result. If adding performance data, report the median end-to-end time for a fixed bundle size over several runs on the same machine. Label it as update time, which includes transport and installation.

