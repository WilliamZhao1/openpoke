# Retained live evidence

Real model responses; all Gmail effects are fake. `results.json.gz` decompresses byte-for-byte to the original run's `results.json`. `original-artifacts.json` is the unmodified original manifest, whose `results.json` hash applies after decompression. The report-bundle manifest verifies the compressed file and copied evidence. The generated live report's `results.json` link requires this decompression.
