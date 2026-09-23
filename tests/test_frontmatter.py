from cud.tools._frontmatter import parse_frontmatter, render_frontmatter


def test_parse_frontmatter_empty() -> None:
    meta, body = parse_frontmatter("")
    assert meta == {}
    assert body == ""


def test_parse_frontmatter_no_delimiter() -> None:
    text = "# Just markdown\nNo frontmatter here."
    meta, body = parse_frontmatter(text)
    assert meta == {}
    assert body == text


def test_parse_frontmatter_valid() -> None:
    text = "---\nname: test-skill\ndescription: Test description\n---\nSkill body content\n"
    meta, body = parse_frontmatter(text)
    assert meta == {"name": "test-skill", "description": "Test description"}
    assert body == "Skill body content\n"


def test_parse_frontmatter_invalid_yaml() -> None:
    text = "---\n: : [invalid\n---\nBody text\n"
    meta, body = parse_frontmatter(text)
    assert meta == {}
    assert body == "Body text\n"


def test_parse_frontmatter_non_dict_yaml() -> None:
    text = "---\n- item 1\n- item 2\n---\nBody text\n"
    meta, body = parse_frontmatter(text)
    assert meta == {}
    assert body == "Body text\n"


def test_render_frontmatter_empty_metadata() -> None:
    assert render_frontmatter({}, "Hello body") == "Hello body"


def test_render_frontmatter_with_metadata() -> None:
    result = render_frontmatter({"name": "sample", "count": 3}, "Body content")
    assert result == "---\nname: sample\ncount: 3\n---\nBody content"


def test_frontmatter_roundtrip() -> None:
    original_meta = {"name": "test-task", "schedule": "0 * * * *", "enabled": True}
    original_body = "Execute hourly task instructions.\nLine 2.\n"
    rendered = render_frontmatter(original_meta, original_body)
    meta, body = parse_frontmatter(rendered)
    assert meta == original_meta
    assert body == original_body
