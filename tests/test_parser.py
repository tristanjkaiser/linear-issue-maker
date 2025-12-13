from linear_issue_maker.parser import IssueSpec, parse_issue_spec


def test_parse_success() -> None:
    text = (
        "Team: Backend\n"
        "Project: Payments\n"
        "Template: Story\n"
        "Title: Upgrade checkout flow\n"
        "Summary:\n"
        "First line.\n"
        "Second line.\n"
    )

    spec = parse_issue_spec(text)

    assert spec == IssueSpec(
        team="Backend",
        project="Payments",
        template="Story",
        title="Upgrade checkout flow",
        summary="First line.\nSecond line.",
    )


def test_missing_summary() -> None:
    text = (
        "Team: Backend\n"
        "Project: Payments\n"
        "Template: Story\n"
        "Title: Upgrade checkout flow\n"
    )

    try:
        parse_issue_spec(text)
    except ValueError as exc:  # pragma: no cover - we expect this branch
        assert "Summary" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Missing summary should raise a ValueError")
