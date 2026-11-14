"""The dependency gate prints every advisory and fails only on what it must.

``scripts/dependency_audit.py`` audits the npm and cargo trees in CI. What it
reports is anything the tools find; what it fails on is a finding at or above
``--fail-on`` that the allowlist does not name, or an allowlist entry past its
``review_by`` date. These tests drive it as CI does: ``npm`` and ``cargo`` are
stand-ins on ``PATH`` that print a report, and the gate's own output and exit
code are read back.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import stat
import sys
from pathlib import Path

import pytest

from scripts import dependency_audit as audit
from scripts.dependency_audit import AllowEntry, Allowlist, CargoAudit, Finding, Gate, NpmAudit

TODAY = dt.date(2026, 6, 15)


def finding(
    *,
    advisory: str = "GHSA-aaaa",
    package: str = "left-pad",
    severity: str = "critical",
    ecosystem: str = "npm",
    aliases: tuple[str, ...] = (),
) -> Finding:
    return Finding(
        ecosystem=ecosystem,
        package=package,
        version="1.0.0",
        advisory=advisory,
        aliases=aliases,
        severity=severity,
        title=f"{package} is bad",
    )


def entry(
    *,
    advisory: str = "GHSA-aaaa",
    package: str = "left-pad",
    ecosystem: str = "npm",
    review_by: dt.date = dt.date(2026, 12, 31),
    reason: str = "does not reach igni",
) -> AllowEntry:
    return AllowEntry(
        ecosystem=ecosystem,
        advisory=advisory,
        package=package,
        reason=reason,
        review_by=review_by,
    )


@pytest.fixture
def gate_output(capsys: pytest.CaptureFixture[str]):
    def run(
        findings: list[Finding],
        entries: list[AllowEntry] | None = None,
        *,
        fail_on: str = "critical",
        ecosystem: str = "npm",
    ) -> tuple[int, str]:
        failing = Gate(Allowlist(entries or []), fail_on, TODAY).judge(ecosystem, findings)
        return failing, capsys.readouterr().out

    return run


# ── Finding and AllowEntry ────────────────────────────────────────────────────


def test_a_finding_is_known_by_its_advisory_and_every_alias() -> None:
    f = finding(advisory="GHSA-aaaa", aliases=("CVE-1", "https://x/GHSA-aaaa"))
    assert f.ids == {"GHSA-aaaa", "CVE-1", "https://x/GHSA-aaaa"}


@pytest.mark.parametrize("index, name", list(enumerate(audit.SEVERITIES)))
def test_a_finding_ranks_by_its_place_in_the_severities(index: int, name: str) -> None:
    assert finding(severity=name).rank() == index


def test_the_severities_run_from_unknown_up_to_critical() -> None:
    assert audit.SEVERITIES == ("unknown", "low", "moderate", "high", "critical")


def test_an_entry_covers_its_advisory_for_its_package_and_ecosystem() -> None:
    assert entry().covers(finding())


def test_an_entry_covers_a_finding_that_carries_its_advisory_as_an_alias() -> None:
    e = entry(advisory="CVE-2026-1")
    assert e.covers(finding(advisory="GHSA-aaaa", aliases=("CVE-2026-1",)))


@pytest.mark.parametrize(
    "other",
    [
        finding(package="right-pad"),
        finding(ecosystem="cargo"),
        finding(advisory="GHSA-bbbb"),
    ],
    ids=["another package", "another ecosystem", "another advisory"],
)
def test_an_entry_covers_nothing_else(other: Finding) -> None:
    assert not entry().covers(other)


def test_an_entry_expires_the_day_after_its_review_date() -> None:
    e = entry(review_by=dt.date(2026, 6, 15))
    assert not e.expired(dt.date(2026, 6, 14))
    assert not e.expired(dt.date(2026, 6, 15))
    assert e.expired(dt.date(2026, 6, 16))


# ── Allowlist ─────────────────────────────────────────────────────────────────


def test_a_missing_allowlist_file_allows_nothing(tmp_path: Path) -> None:
    assert Allowlist.load(tmp_path / "absent.toml").entries == []


def test_an_allowlist_is_read_entry_by_entry_with_the_reason_on_one_line(tmp_path: Path) -> None:
    path = tmp_path / "allow.toml"
    path.write_text(
        '[[allow]]\necosystem = "npm"\nadvisory = "GHSA-aaaa"\npackage = "left-pad"\n'
        'reason = """does not\n    reach   igni\n"""\nreview_by = 2026-12-31\n'
        '[[allow]]\necosystem = "cargo"\nadvisory = "RUSTSEC-1"\npackage = "rand"\n'
        'reason = "no fix"\nreview_by = 2027-01-31\n'
    )
    loaded = Allowlist.load(path)
    assert loaded.entries == [
        entry(reason="does not reach igni"),
        entry(
            ecosystem="cargo",
            advisory="RUSTSEC-1",
            package="rand",
            reason="no fix",
            review_by=dt.date(2027, 1, 31),
        ),
    ]


def test_a_file_with_no_entries_allows_nothing(tmp_path: Path) -> None:
    path = tmp_path / "allow.toml"
    path.write_text("# nothing is excepted\n")
    assert Allowlist.load(path).entries == []


@pytest.mark.parametrize("key", ["ecosystem", "advisory", "package", "reason", "review_by"])
def test_an_entry_missing_a_key_is_refused_and_names_it(tmp_path: Path, key: str) -> None:
    fields = {
        "ecosystem": '"npm"',
        "advisory": '"GHSA-aaaa"',
        "package": '"left-pad"',
        "reason": '"because"',
        "review_by": "2026-12-31",
    }
    del fields[key]
    path = tmp_path / "allow.toml"
    path.write_text("[[allow]]\n" + "".join(f"{k} = {v}\n" for k, v in fields.items()))
    with pytest.raises(SystemExit, match=key):
        Allowlist.load(path)


@pytest.mark.parametrize("reason", ['""', '"   "', '"""\n  \n"""'])
def test_an_entry_with_a_blank_reason_is_refused(tmp_path: Path, reason: str) -> None:
    path = tmp_path / "allow.toml"
    path.write_text(
        '[[allow]]\necosystem = "npm"\nadvisory = "GHSA-aaaa"\npackage = "left-pad"\n'
        f"reason = {reason}\nreview_by = 2026-12-31\n"
    )
    with pytest.raises(SystemExit, match="empty reason"):
        Allowlist.load(path)


@pytest.mark.parametrize("review_by", ['"2027-01-31"', "2027-01-31T10:00:00", "20270131", "true"])
def test_an_entry_whose_review_by_is_not_a_date_is_refused(tmp_path: Path, review_by: str) -> None:
    """A quoted date would load, then crash the gate comparing it with today."""
    path = tmp_path / "allow.toml"
    path.write_text(
        '[[allow]]\necosystem = "npm"\nadvisory = "GHSA-aaaa"\npackage = "left-pad"\n'
        f'reason = "because"\nreview_by = {review_by}\n'
    )
    with pytest.raises(SystemExit, match="GHSA-aaaa has a review_by that is not a date"):
        Allowlist.load(path)


def test_the_repository_s_own_allowlist_loads() -> None:
    loaded = Allowlist.load(audit.DEFAULT_ALLOWLIST)
    for e in loaded.entries:
        assert e.ecosystem in {"npm", "cargo"}
        assert e.reason
        assert isinstance(e.review_by, dt.date)


def test_matching_finds_the_covering_entry_and_for_ecosystem_lists_one_ecosystem() -> None:
    npm_entry = entry()
    cargo_entry = entry(ecosystem="cargo", advisory="RUSTSEC-1", package="rand")
    allowlist = Allowlist([npm_entry, cargo_entry])
    assert allowlist.matching(finding()) is npm_entry
    assert allowlist.matching(finding(advisory="GHSA-zzzz")) is None
    assert allowlist.for_ecosystem("cargo") == [cargo_entry]
    assert allowlist.for_ecosystem("npm") == [npm_entry]


# ── Gate ──────────────────────────────────────────────────────────────────────


def test_a_critical_finding_with_no_entry_fails_and_is_annotated(gate_output) -> None:
    failing, out = gate_output([finding()])
    assert failing == 1
    assert "FAILS" in out
    assert "::error title=GHSA-aaaa::left-pad 1.0.0: left-pad is bad" in out


def test_a_finding_below_the_threshold_is_reported_and_does_not_fail(gate_output) -> None:
    failing, out = gate_output([finding(severity="high")])
    assert failing == 0
    assert "report " in out
    assert "FAILS" not in out
    assert "::error" not in out


@pytest.mark.parametrize(
    "fail_on, severity, fails",
    [
        ("high", "high", True),
        ("high", "critical", True),
        ("high", "moderate", False),
        ("moderate", "moderate", True),
        ("moderate", "low", False),
        ("low", "low", True),
        ("critical", "high", False),
    ],
)
def test_fail_on_is_the_lowest_severity_that_fails(
    gate_output, fail_on: str, severity: str, fails: bool
) -> None:
    failing, _ = gate_output([finding(severity=severity)], fail_on=fail_on)
    assert failing == (1 if fails else 0)


def test_an_unknown_severity_is_reported_and_never_fails(gate_output) -> None:
    failing, out = gate_output([finding(severity="unknown")], fail_on="low")
    assert failing == 0
    assert "report " in out


def test_an_allowed_finding_is_printed_with_its_reason_and_date_and_does_not_fail(
    gate_output,
) -> None:
    failing, out = gate_output([finding()], [entry(review_by=dt.date(2026, 12, 31))])
    assert failing == 0
    assert "allowed " in out
    assert "allowed until 2026-12-31: does not reach igni" in out
    assert "FAILS" not in out


def test_an_entry_names_one_package_so_another_package_still_fails(gate_output) -> None:
    failing, _ = gate_output([finding(package="right-pad")], [entry()])
    assert failing == 1


def test_an_entry_naming_an_alias_allows_the_finding(gate_output) -> None:
    failing, _ = gate_output([finding(aliases=("CVE-2026-1",))], [entry(advisory="CVE-2026-1")])
    assert failing == 0


def test_an_expired_entry_fails_even_when_it_allows_a_finding(gate_output) -> None:
    failing, out = gate_output([finding()], [entry(review_by=dt.date(2026, 6, 14))])
    assert failing == 1
    assert "allowed " in out
    assert "::error title=allowlist::GHSA-aaaa (left-pad) was to be reviewed by 2026-06-14" in out


def test_an_entry_due_today_has_not_expired(gate_output) -> None:
    failing, out = gate_output([finding()], [entry(review_by=TODAY)])
    assert failing == 0
    assert "::error" not in out


def test_an_entry_that_matches_nothing_is_noticed_and_does_not_fail(gate_output) -> None:
    failing, out = gate_output([], [entry()])
    assert failing == 0
    assert "::notice title=allowlist::GHSA-aaaa (left-pad) no longer matches anything" in out


def test_an_entry_in_use_is_not_noticed(gate_output) -> None:
    _, out = gate_output([finding()], [entry()])
    assert "::notice" not in out


def test_another_ecosystem_s_entries_are_neither_expired_nor_noticed(gate_output) -> None:
    stale = entry(ecosystem="cargo", review_by=dt.date(2020, 1, 1))
    failing, out = gate_output([], [stale], ecosystem="npm")
    assert failing == 0
    assert out == ""


def test_findings_print_by_severity_then_package_then_advisory(gate_output) -> None:
    _, out = gate_output(
        [
            finding(package="b", advisory="2", severity="low"),
            finding(package="b", advisory="1", severity="critical"),
            finding(package="a", advisory="9", severity="critical"),
            finding(package="a", advisory="3", severity="high"),
            finding(package="a", advisory="1", severity="critical"),
        ],
        fail_on="critical",
    )
    lines = [line for line in out.splitlines() if not line.startswith(("::", " "))]
    assert [(w[1], w[2], w[4]) for w in (line.split() for line in lines)] == [
        ("critical", "a", "1"),
        ("critical", "a", "9"),
        ("critical", "b", "1"),
        ("high", "a", "3"),
        ("low", "b", "2"),
    ]


# ── CargoAudit.severity ───────────────────────────────────────────────────────

CVSS3 = "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:{c}/I:{c}/A:{c}"


@pytest.mark.parametrize(
    "vector, expected",
    [
        (CVSS3.format(c="H"), "critical"),
        ("CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:U/C:H/I:H/A:N", "high"),
        ("CVSS:3.1/AV:N/AC:L/PR:L/UI:R/S:U/C:L/I:L/A:N", "moderate"),
        ("CVSS:3.1/AV:L/AC:H/PR:H/UI:R/S:U/C:L/I:N/A:N", "low"),
        (CVSS3.format(c="N"), "low"),
        (
            "CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:H/VA:H/SC:N/SI:N/SA:N",
            "critical",
        ),
        (
            "CVSS:4.0/AV:L/AC:H/AT:P/PR:H/UI:A/VC:L/VI:N/VA:N/SC:N/SI:N/SA:N",
            "low",
        ),
    ],
    ids=["critical", "high", "medium is moderate", "low", "none is low", "v4", "v4 low"],
)
def test_a_cvss_vector_is_scored_into_the_gate_s_severities(vector: str, expected: str) -> None:
    assert CargoAudit.severity(vector) == expected


@pytest.mark.parametrize("vector", [None, ""])
def test_an_advisory_with_no_vector_is_unknown(vector: str | None) -> None:
    assert CargoAudit.severity(vector) == "unknown"


def test_a_version_4_vector_is_scored_as_version_4() -> None:
    """A CVSS 4 vector is not a valid CVSS 3 one: it must reach the CVSS 4 scorer."""
    v4 = "CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:H/VA:H/SC:N/SI:N/SA:N"
    assert CargoAudit.severity(v4) == "critical"


# ── The tools, as stand-ins on PATH ───────────────────────────────────────────


def stand_in(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    stdout: str,
    *,
    stderr: str = "",
    code: int = 1,
) -> Path:
    """Put a program called ``name`` first on PATH that prints ``stdout``.

    It also writes the arguments it was called with, one per line, to the file
    this returns, and exits ``code``: ``npm audit`` exits non-zero whenever it
    finds anything.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    out = tmp_path / f"{name}.out"
    err = tmp_path / f"{name}.err"
    called = tmp_path / f"{name}.args"
    out.write_text(stdout)
    err.write_text(stderr)
    program = bin_dir / name
    program.write_text(
        f'#!/bin/sh\nfor a in "$@"; do echo "$a"; done > "{called}"\n'
        f'cat "{out}"\ncat "{err}" >&2\nexit {code}\n'
    )
    program.chmod(program.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}/usr/bin{os.pathsep}/bin")
    return called


def npm_report(vulnerabilities: dict) -> str:
    return json.dumps({"vulnerabilities": vulnerabilities})


def test_npm_is_asked_for_what_ships_in_the_tree_it_is_pointed_at(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    called = stand_in(tmp_path, monkeypatch, "npm", npm_report({}))
    assert NpmAudit(tmp_path).findings() == []
    assert called.read_text().split() == ["audit", "--omit=dev", "--json"]


def test_an_npm_advisory_is_a_finding_named_by_the_last_part_of_its_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = "https://github.com/advisories/GHSA-xxxx-yyyy"
    stand_in(
        tmp_path,
        monkeypatch,
        "npm",
        npm_report(
            {
                "left-pad": {
                    "range": "<2.0.0",
                    "via": [
                        {
                            "source": 1234,
                            "url": url,
                            "range": "<1.5.0",
                            "severity": "high",
                            "title": "pads too far",
                        }
                    ],
                }
            }
        ),
    )
    assert NpmAudit(tmp_path).findings() == [
        Finding("npm", "left-pad", "<1.5.0", "GHSA-xxxx-yyyy", (url,), "high", "pads too far")
    ]


def test_an_npm_pointer_to_another_package_is_not_an_advisory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stand_in(
        tmp_path,
        monkeypatch,
        "npm",
        npm_report({"top": {"range": "*", "via": ["left-pad", "right-pad"]}}),
    )
    assert NpmAudit(tmp_path).findings() == []


def test_an_npm_advisory_without_a_url_is_named_by_its_source_and_a_missing_severity_is_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stand_in(
        tmp_path,
        monkeypatch,
        "npm",
        npm_report({"left-pad": {"range": "<2", "via": [{"source": 77, "title": "t"}]}}),
    )
    assert NpmAudit(tmp_path).findings() == [
        Finding("npm", "left-pad", "<2", "77", (), "unknown", "t")
    ]


def test_every_via_of_a_package_is_its_own_finding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stand_in(
        tmp_path,
        monkeypatch,
        "npm",
        npm_report(
            {
                "left-pad": {
                    "range": "*",
                    "via": [
                        {"url": "https://x/A", "severity": "low"},
                        "dep",
                        {"url": "https://x/B", "severity": "critical"},
                    ],
                }
            }
        ),
    )
    assert [f.advisory for f in NpmAudit(tmp_path).findings()] == ["A", "B"]


def test_npm_saying_nothing_is_no_findings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stand_in(tmp_path, monkeypatch, "npm", "", code=0)
    assert NpmAudit(tmp_path).findings() == []


def test_npm_reporting_an_error_stops_the_audit_with_its_words(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stand_in(tmp_path, monkeypatch, "npm", json.dumps({"error": {"code": "ENOLOCK"}}))
    with pytest.raises(SystemExit, match="npm audit failed in .*ENOLOCK"):
        NpmAudit(tmp_path).findings()


def cargo_report(vulnerabilities: list[dict], warnings: dict | None = None) -> str:
    return json.dumps({"vulnerabilities": {"list": vulnerabilities}, "warnings": warnings or {}})


def vulnerability(**advisory: object) -> dict:
    return {
        "package": {"name": "rand", "version": "0.7.0"},
        "advisory": {"id": "RUSTSEC-2026-1", "title": "unsound", **advisory},
    }


def test_a_cargo_vulnerability_is_a_finding_scored_from_its_vector(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    called = stand_in(
        tmp_path,
        monkeypatch,
        "cargo",
        cargo_report([vulnerability(aliases=["CVE-2026-9", "GHSA-q"], cvss=CVSS3.format(c="H"))]),
    )
    assert CargoAudit(tmp_path).findings() == [
        Finding(
            "cargo",
            "rand",
            "0.7.0",
            "RUSTSEC-2026-1",
            ("CVE-2026-9", "GHSA-q"),
            "critical",
            "unsound",
        )
    ]
    assert called.read_text().split() == ["audit", "--json"]


def test_a_cargo_vulnerability_with_no_vector_or_aliases_is_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stand_in(tmp_path, monkeypatch, "cargo", cargo_report([vulnerability(aliases=None)]))
    [found] = CargoAudit(tmp_path).findings()
    assert (found.severity, found.aliases) == ("unknown", ())


def test_cargo_with_no_vulnerabilities_has_no_findings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stand_in(tmp_path, monkeypatch, "cargo", json.dumps({"vulnerabilities": {}}), code=0)
    assert CargoAudit(tmp_path).findings() == []


def test_cargo_s_warnings_are_counted_by_kind_and_never_findings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stand_in(
        tmp_path,
        monkeypatch,
        "cargo",
        cargo_report([], {"unsound": [{}], "unmaintained": [{}, {}, {}]}),
    )
    assert CargoAudit(tmp_path).findings() == []
    out = capsys.readouterr().out.splitlines()
    assert len(out) == 2
    assert out[0].split()[:3] == ["report", "unmaintained", "3"]
    assert out[1].split()[:3] == ["report", "unsound", "1"]
    assert all("not gated" in line for line in out)


def test_cargo_not_answering_in_json_stops_the_audit_with_its_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stand_in(tmp_path, monkeypatch, "cargo", "", stderr="no Cargo.lock found")
    with pytest.raises(SystemExit, match="(?s)cargo audit failed in .*no Cargo.lock found"):
        CargoAudit(tmp_path).findings()


# ── main ──────────────────────────────────────────────────────────────────────


def run_main(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    *args: str | Path,
) -> tuple[int, str]:
    monkeypatch.setattr(sys, "argv", ["dependency_audit.py", *map(str, args)])
    code = audit.main()
    return code, capsys.readouterr().out


def critical_npm(name: str = "left-pad", advisory: str = "GHSA-aaaa") -> dict:
    return {
        name: {
            "range": "*",
            "via": [
                {
                    "url": f"https://x/{advisory}",
                    "severity": "critical",
                    "title": "bad",
                    "range": "<2",
                }
            ],
        }
    }


def test_main_fails_on_a_critical_advisory_the_allowlist_does_not_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stand_in(tmp_path, monkeypatch, "npm", npm_report(critical_npm()))
    code, out = run_main(
        monkeypatch, capsys, "npm", tmp_path, "--allowlist", tmp_path / "none.toml"
    )
    assert code == 1
    assert "1 advisory" in out
    assert "1 finding(s) at or above critical with no allowlist entry, or expired entries" in out


def test_main_passes_when_the_allowlist_names_the_advisory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stand_in(tmp_path, monkeypatch, "npm", npm_report(critical_npm()))
    allow = tmp_path / "allow.toml"
    allow.write_text(
        '[[allow]]\necosystem = "npm"\nadvisory = "GHSA-aaaa"\npackage = "left-pad"\n'
        'reason = "not reached"\nreview_by = 2999-01-01\n'
    )
    code, out = run_main(monkeypatch, capsys, "npm", tmp_path, "--allowlist", allow)
    assert code == 0
    assert "nothing at or above critical outside the allowlist" in out


def test_main_fails_on_an_allowlist_entry_past_its_review_date(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stand_in(tmp_path, monkeypatch, "npm", npm_report(critical_npm()))
    allow = tmp_path / "allow.toml"
    allow.write_text(
        '[[allow]]\necosystem = "npm"\nadvisory = "GHSA-aaaa"\npackage = "left-pad"\n'
        'reason = "not reached"\nreview_by = 2000-01-01\n'
    )
    code, _ = run_main(monkeypatch, capsys, "npm", tmp_path, "--allowlist", allow)
    assert code == 1


def test_main_fail_on_defaults_to_critical_and_takes_a_lower_threshold(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    report = critical_npm()
    report["left-pad"]["via"][0]["severity"] = "high"
    stand_in(tmp_path, monkeypatch, "npm", npm_report(report))
    none = tmp_path / "none.toml"
    assert run_main(monkeypatch, capsys, "npm", tmp_path, "--allowlist", none)[0] == 0
    code, out = run_main(
        monkeypatch, capsys, "npm", tmp_path, "--allowlist", none, "--fail-on", "high"
    )
    assert code == 1
    assert "at or above high" in out


@pytest.mark.parametrize("level", ["unknown", "urgent"])
def test_main_refuses_a_fail_on_that_is_not_low_to_critical(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    level: str,
) -> None:
    with pytest.raises(SystemExit) as stopped:
        run_main(monkeypatch, capsys, "npm", tmp_path, "--fail-on", level)
    assert stopped.value.code == 2


def test_main_refuses_an_ecosystem_that_is_not_npm_or_cargo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as stopped:
        run_main(monkeypatch, capsys, "pip", tmp_path)
    assert stopped.value.code == 2


def test_main_judges_the_findings_of_all_the_directories_together(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stand_in(tmp_path, monkeypatch, "npm", npm_report(critical_npm()))
    first, second = tmp_path / "a", tmp_path / "b"
    first.mkdir()
    second.mkdir()
    code, out = run_main(
        monkeypatch, capsys, "npm", first, second, "--allowlist", tmp_path / "none.toml"
    )
    assert code == 1
    assert f"npm audit: {first}" in out
    assert f"npm audit: {second}" in out
    assert "2 finding(s)" in out


@pytest.mark.parametrize(
    "count, words", [(0, "0 advisories"), (1, "1 advisory"), (2, "2 advisories")]
)
def test_main_counts_advisories_in_the_singular_and_the_plural(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    count: int,
    words: str,
) -> None:
    report: dict = {}
    for i in range(count):
        report.update(critical_npm(f"pkg{i}", f"GHSA-{i}"))
    stand_in(tmp_path, monkeypatch, "npm", npm_report(report))
    _, out = run_main(
        monkeypatch,
        capsys,
        "npm",
        tmp_path,
        "--allowlist",
        tmp_path / "none.toml",
        "--fail-on",
        "low",
    )
    assert f"   {words}\n" in out


def test_main_audits_cargo_trees_with_cargo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stand_in(
        tmp_path,
        monkeypatch,
        "cargo",
        cargo_report([vulnerability(cvss=CVSS3.format(c="H"))]),
    )
    code, out = run_main(
        monkeypatch, capsys, "cargo", tmp_path, "--allowlist", tmp_path / "none.toml"
    )
    assert code == 1
    assert "cargo audit:" in out
    assert "RUSTSEC-2026-1" in out
