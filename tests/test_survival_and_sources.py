import numpy as np
import pandas as pd

from conftest import write
from tripwire.contract import Change
from tripwire.detect import detect_changes
from tripwire.findings import build
from tripwire.questions import BY_ID
from tripwire.release import Release
from tripwire.sources import slide_url
from tripwire.validate import challenge_dir, validate


def survival(dest, clinical, events_every=4, seed=0):
    rng = np.random.default_rng(seed)
    n = len(clinical)
    sv = pd.DataFrame({"sample": clinical.sampleID, "_PATIENT": clinical.sampleID.str[:12],
                       "OS": [1 if i % events_every == 0 else 0 for i in range(n)],
                       "OS.time": rng.integers(100, 3000, n), "Redaction": [""] * n})
    sv.to_csv(dest / "survival.tsv", sep="\t", index=False)
    return sv


def q(doc, qid):
    return next(x for x in doc["questions"] if x["id"] == qid)


def test_survival_question_uses_survival_file_and_counts_events(releases):
    a, _, clinical, protein = releases
    survival(a, clinical, events_every=2)
    doc = build([], Release(a), Release(a, name="again"))
    s = q(doc, "os_by_subtype")
    ec = next(c for c in s["checks"] if c["name"] == "event_count")
    assert s["verdict"] == "Ready" and ec["status"] == "pass" and "median follow-up" in ec["summary"]


def test_too_few_events_is_insufficient(releases):
    a, _, clinical, protein = releases
    survival(a, clinical, events_every=50)
    s = q(build([], Release(a), Release(a, name="again")), "os_by_subtype")
    assert s["verdict"] == "Insufficient Evidence"


def test_survival_change_reaches_the_survival_question(releases):
    a, b, clinical, protein = releases
    sv = survival(a, clinical, events_every=2)
    write(b, clinical, protein)
    sv2 = sv.copy()
    sv2.loc[3, "OS"] = 1 - sv2.loc[3, "OS"]
    sv2.to_csv(b / "survival.tsv", sep="\t", index=False)
    ch = detect_changes(Release(a), Release(b))
    assert [(c.change_type, c.file) for c in ch] == [("label_change", "survival.tsv")]
    doc = build(ch, Release(a), Release(b))
    assert q(doc, "os_by_subtype")["verdict"] == "Blocked"           # its records changed
    assert q(doc, "subtype_mix")["verdict"] == "Ready"                # doesn't read survival


def test_cited_samples_link_to_their_slide():
    if challenge_dir() is None:
        return
    url = slide_url("TCGA-A8-A09K-01")
    assert url and url.startswith("https://viewer.imaging.datacommons.cancer.gov/")
    assert slide_url("TCGA-NO-SUCH-01") is None
