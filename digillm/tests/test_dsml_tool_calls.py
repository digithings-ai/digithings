import json

from digillm.client import _parse_dsml_tool_calls

SAMPLE = (
    "Let me pull the tickets.\n"
    "<｜DSML｜tool_calls>\n"
    '<｜DSML｜invoke name="zammad_search_tickets">\n'
    '<｜DSML｜parameter name="query" string="true">created_at:>now-30d</｜DSML｜parameter>\n'
    '<｜DSML｜parameter name="limit" string="false">50</｜DSML｜parameter>\n'
    "</｜DSML｜invoke>\n"
    '<｜DSML｜invoke name="get_skill">\n'
    '<｜DSML｜parameter name="name" string="true">summarize-tickets-by-topic</｜DSML｜parameter>\n'
    "</｜DSML｜invoke>\n"
    "</｜DSML｜tool_calls>"
)


def test_dsml_lifted_into_tool_calls():
    content, calls = _parse_dsml_tool_calls(SAMPLE)
    assert content == "Let me pull the tickets."
    assert [c["function"]["name"] for c in calls] == ["zammad_search_tickets", "get_skill"]
    assert json.loads(calls[0]["function"]["arguments"]) == {
        "query": "created_at:>now-30d",
        "limit": 50,
    }


def test_function_calls_wrapper_and_unterminated():
    raw = '<｜DSML｜function_calls><｜DSML｜invoke name="x"><｜DSML｜parameter name="a" string="true">1</｜DSML｜parameter>'
    content, calls = _parse_dsml_tool_calls(raw)
    assert content == "" and calls[0]["function"]["name"] == "x"


def test_plain_content_untouched():
    assert _parse_dsml_tool_calls("hello") == ("hello", [])
