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


def test_wrapup_dsml_filtered_and_retried():
    from unittest.mock import MagicMock, patch

    import digillm
    import digillm.client as client_mod

    def chunk(content=None, tool_calls=None):
        delta = MagicMock()
        delta.content = content
        delta.tool_calls = tool_calls
        delta.reasoning_content = None
        delta.reasoning = None
        ch = MagicMock()
        ch.choices = [MagicMock(delta=delta, finish_reason=None)]
        ch.usage = None
        return ch

    tc = MagicMock(index=0, id="c1", type="function")
    tc.function = MagicMock(arguments='{"q": "x"}')
    tc.function.name = "lookup"
    round1 = [chunk(tool_calls=[tc])]
    leak = [
        chunk(content="Paging on.\n<\uff5cDSML"),
        chunk(
            content='\uff5ctool_calls><\uff5cDSML\uff5cinvoke name="lookup"></\uff5cDSML\uff5cinvoke></\uff5cDSML\uff5ctool_calls>'
        ),
    ]
    fake = MagicMock()
    fake.chat.completions.create.side_effect = [round1, leak]
    seen = []
    tools = [{"type": "function", "function": {"name": "lookup", "parameters": {}}}]
    with patch.object(client_mod, "get_client_for_model", return_value=fake):
        out = digillm.run_tools(
            "gpt-4o-mini",
            [{"role": "user", "content": "go"}],
            tools,
            execute_tool=lambda n, a: "r",
            on_tool_step=lambda k, p: seen.append((k, p)),
            stream_deltas=True,
            max_tool_rounds=1,
        )
    assert out == "Paging on."
    streamed = "".join(p for k, p in seen if k == "content")
    assert "DSML" not in streamed and streamed == "Paging on.\n"


def test_mangled_double_bar_variant():
    raw = (
        '<｜｜DSML｜｜ calls> <｜｜DSML｜｜ invoke name="get_skill"> '
        '<｜｜DSML｜｜ parameter name="name" string="true">present-results</｜｜DSML｜｜ parameter> '
        "</｜｜DSML｜｜ invoke>"
    )
    content, calls = _parse_dsml_tool_calls(raw)
    assert content == ""
    assert calls[0]["function"]["name"] == "get_skill"
