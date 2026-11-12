# Shared change contract

Status: **draft from PLAN.md, to be confirmed by all four at Thursday morning's 30-minute meeting.** Changing it after that requires a plan-change proposal (see [CONTRIBUTING.md](../CONTRIBUTING.md)).

The detector (Role 1) emits a list of these, the Mutation Lab (Role 3) uses them as its answer key, and the impact and findings layer (Role 2) builds `findings.json` from them. The Python form is `tripwire.contract.Change`.

```json
{
  "sample_id": "TCGA-XX-XXXX-01A",
  "change_type": "swap",
  "file": "protein",
  "fields": ["ER-alpha"],
  "evidence": "fingerprint matches TCGA-YY-YYYY-01A in release A",
  "before": "...",
  "after": "..."
}
```

## Field rules

| Field | Rule |
| --- | --- |
| `sample_id` | Sample barcode as it appears in the file, which is usually 15 characters (`TCGA-XX-XXXX-01`). Don't normalise it here: a case or whitespace change is itself a change to report. |
| `change_type` | One of the values in the table below. |
| `file` | The file name exactly as in the release folder, e.g. `protein_rppa.tsv.gz`, `clinical.tsv`. |
| `fields` | The rows (protein or gene names) or clinical columns that changed. An empty list means the whole sample profile. |
| `evidence` | One human-readable sentence. |
| `before`, `after` | A short value or a summary. `null` when the sample doesn't exist on that side. |
| `related_sample_id` | *Optional, proposed by Role 2 (pending agreement).* The other sample in a swap, or the source of a duplicate. Lets findings point at both samples without parsing `evidence`. |

## Change types

| `change_type` | Meaning | `findings.json` kind |
| --- | --- | --- |
| `swap` | Sample X in B carries the profile that belonged to Y in A, and vice versa | `sample_swap` |
| `duplicate` | A sample in B has the same (or near-identical) profile as another sample | `duplicate` |
| `appeared` | Sample is in B's file, not in A's | `membership_change` |
| `disappeared` | Sample is in A's file, not in B's | `membership_change` |
| `label_change` | A clinical field's value changed for the sample | `label_conflict` |
| `sample_type_change` | Barcode sample-type code changed (01 / 11 / 06) | `label_conflict` |
| `id_format_change` | Same sample, ID changed by case or whitespace | `other` |
| `value_shift` | Values changed for the sample without a swap or duplicate (e.g. unit shift) | `other` |
| `coverage_loss` | Missing-data rate rose for a subgroup (sample_id is the subgroup's sample that lost data) | `missing_data` |
