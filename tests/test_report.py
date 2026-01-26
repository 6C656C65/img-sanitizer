from img_sanitizer.report import Report


def test_report_display_outputs_table(capsys):
    r = Report()
    r.copied = 2
    r.ignored = 1
    r.failed = 0

    r.display()

    captured = capsys.readouterr()
    assert captured.out.strip() != ""
    assert "Copied files" in captured.out
    assert "Ignored files" in captured.out
    assert "Failed files" in captured.out
